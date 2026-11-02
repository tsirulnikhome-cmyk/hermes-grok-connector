"""Optional memory backend: a self-hosted Honcho (https://github.com/plastic-labs/honcho) instead of plain files.

Same interface as memory.Memory. The difference is an organizing layer between the model and the raw text: Honcho's
worker turns conversations into separate facts, keeps a short card per person, and searches by meaning ("car" finds
"Tesla"). If the person's Hermes agent uses Honcho too, the connector and the agent share one memory: set `observer`
to the agent's `aiPeer` and `peer` to the person's peer.

Facts are conclusions (observer -> peer); profile-kind facts also go on the peer card, which is always loaded.
Standard library only, so the default install stays small.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from .config import HonchoServer, Person, resolve_secret
from .memory import PROFILE_KINDS, Memory, MemoryError_

CARD_LIMIT = 40      # card lines kept
SAME = 0.12          # cosine distance under which a new fact replaces an old one (tune for your embedding model)
TIMEOUT = 20


class HonchoMemory:
    def __init__(self, server: HonchoServer, observer: str, peer: str):
        self.server, self.observer, self.peer = server, observer, peer

    def _api(self, method: str, path: str, body: dict | None = None, **query):
        url = f"{self.server.base_url.rstrip('/')}/v3/workspaces/{self.server.workspace}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {"Content-Type": "application/json", "User-Agent": "hermes-grok-connector"}
        key = resolve_secret(self.server.api_key)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None, headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read()
        except (OSError, urllib.error.URLError) as e:
            raise MemoryError_(f"memory is unavailable right now ({e})") from None
        return json.loads(raw) if raw else None

    def _peers(self) -> None:
        for p in {self.observer, self.peer}:
            self._api("POST", "/peers", {"id": p})   # get-or-create

    def _filters(self) -> dict:
        return {"observer": self.observer, "observed": self.peer}

    def _card(self) -> list[str]:
        return (self._api("GET", f"/peers/{self.observer}/card", target=self.peer) or {}).get("peer_card") or []

    def _set_card(self, card: list[str]) -> None:
        self._api("PUT", f"/peers/{self.observer}/card", {"peer_card": card[-CARD_LIMIT:]}, target=self.peer)

    def _query(self, text: str, top_k: int = 5, distance: float | None = None) -> list[dict]:
        body = {"query": text, "top_k": top_k, "filters": self._filters()}
        if distance is not None:
            body["distance"] = distance
        return self._api("POST", "/conclusions/query", body) or []

    def _all(self) -> list[dict]:
        out, page = [], 1
        while True:
            d = self._api("POST", "/conclusions/list", {"filters": self._filters()}, page=page, size=100) or {}
            out += d.get("items", [])
            if page >= (d.get("pages") or 1):
                return out
            page += 1

    @staticmethod
    def _match(items: list[dict], ref: str) -> list[dict]:
        r = ref.strip().lower()
        return [c for c in items if r and (c["id"].lower().startswith(r) or r in c["content"].lower())]

    def remember(self, text: str, kind: str = "fact", replaces: str = "") -> str:
        """Save one lasting fact. `replaces` updates the named fact; one that means the same as an existing fact
        (by meaning, not wording) replaces it too."""
        text = " ".join((text or "").split())
        if not text:
            raise MemoryError_("nothing to remember")
        self._peers()
        old = (self._match(self._all(), replaces) if replaces else []) or self._query(text, 1, SAME)
        for c in old[:1]:
            self._api("DELETE", f"/conclusions/{c['id']}")
        self._api("POST", "/conclusions", {"conclusions": [{"content": text, "observer_id": self.observer,
                                                             "observed_id": self.peer}]})
        card = self._card()
        if kind in PROFILE_KINDS or (old and old[0]["content"] in card):
            self._set_card([line for line in card if not old or line != old[0]["content"]] + [text])
        if old:
            return f"Updated: {old[0]['content']!r} -> {text!r}"
        return f"Remembered ({'profile' if kind in PROFILE_KINDS else 'notebook'})."

    def recall(self, query: str, limit: int = 5) -> list[str]:
        self._peers()
        return [f"[{c['id'][:8]}] {c['content']} ({(c.get('created_at') or '')[:10]})" for c in self._query(query, limit)]

    def forget(self, item: str) -> str:
        """Remove one fact by id, or by words when exactly one fact contains them."""
        self._peers()
        found = self._match(self._all(), item)
        if not found:
            return "Nothing matched; nothing was removed."
        if len(found) > 1:
            return "Several items match; say which one:\n" + "\n".join(f"[{c['id'][:8]}] {c['content']}" for c in found)
        c = found[0]
        self._api("DELETE", f"/conclusions/{c['id']}")
        card = self._card()
        if c["content"] in card:
            self._set_card([line for line in card if line != c["content"]])
        return f"Forgot: {c['content']}"

    def briefing(self, name: str, extra: list[str] | None = None, now: dt.datetime | None = None) -> str:
        """The card, then the rest of Honcho's picture without repeats, short enough for a voice assistant."""
        self._peers()
        now = now or dt.datetime.now().astimezone()
        d = self._api("GET", f"/peers/{self.observer}/context", target=self.peer, max_conclusions=15,
                      include_most_frequent="true") or {}
        card = d.get("peer_card") or []
        facts = [re.sub(r"^\[[^\]]*\]\s*", "", line).strip() for line in (d.get("representation") or "").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]   # drop section headers and timestamps
        rest = [f for f in dict.fromkeys(facts) if f not in card]
        lines = [f"Speaking with {name}. Now: {now:%A %B %-d, %Y %-I:%M %p %Z}."]
        if card:
            lines += ["About them:"] + [f"- {t}" for t in card]
        if extra:
            lines += extra
        if rest:
            lines += ["What else is known (most relevant first):"] + [f"- {t}" for t in rest]
        lines.append("Use recall for anything else they may have told you before; save new lasting facts with remember.")
        return "\n".join(lines)

    def version(self) -> str:
        """Changes whenever the card or the facts change (lets callers cache the briefing safely)."""
        self._peers()
        ids = sorted(c["id"] for c in self._all())
        return hashlib.sha1(json.dumps([self._card(), ids]).encode()).hexdigest()[:16]

    def dump(self) -> dict:
        self._peers()
        return {"profile": [{"id": "card", "text": t} for t in self._card()],
                "notes": [{"id": c["id"], "text": c["content"], "created": c.get("created_at")} for c in self._all()]}


def memory_for(person: Person) -> Memory | HonchoMemory:
    """The person's memory: plain files unless their config has a `honcho:` block."""
    if person.honcho:
        return HonchoMemory(person.honcho.server, person.honcho.observer, person.honcho.peer)
    return Memory(person.memory_dir)
