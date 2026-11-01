"""Lasting personal memory, two layers (the pattern ChatGPT and Letta use):
  profile   short, always loaded at the start of a conversation (preferences, people, standing facts); capped
  notebook  everything else, searched only when needed (facts, plans, events)

One folder per person (profile.json, notes.json, 0600). No AI model involved: saving, searching and the briefing
are plain file operations, so they are instant and free.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import json
import re
import uuid
from pathlib import Path

PROFILE_KINDS = ("preference", "person", "about")
NOTE_KINDS = ("fact", "plan", "event")
PROFILE_LIMIT = 1500   # characters across profile items (~250 words), so a voice briefing stays fast
NOTE_LIMIT = 400       # notebook items; least-used, oldest drop off past this
SIMILAR = 0.9          # near-identical repeats merge automatically; real updates name the old item in `replaces`
STOP = set("a an the and or of to in on at for with my me i is are was be it that this from by about as".split())


class MemoryError_(ValueError):
    pass


class Memory:
    def __init__(self, folder: Path, profile_limit: int = PROFILE_LIMIT, note_limit: int = NOTE_LIMIT):
        self.folder = Path(folder)
        self.profile_limit, self.note_limit = profile_limit, note_limit

    @contextlib.contextmanager
    def _store(self):
        self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (self.folder / ".lock").open("w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            data = {n: (json.loads((self.folder / f"{n}.json").read_text())
                        if (self.folder / f"{n}.json").exists() else []) for n in ("profile", "notes")}
            yield data
            for n, items in data.items():
                f = self.folder / f"{n}.json"
                f.write_text(json.dumps(items, indent=1, ensure_ascii=False) + "\n")
                f.chmod(0o600)

    def remember(self, text: str, kind: str = "fact", replaces: str = "") -> str:
        """Save one lasting fact. `replaces` (an id or a few words of the old item) updates that item; a
        near-identical repeat updates itself. Word overlap alone never merges different facts (e.g. two people
        with the same weekday)."""
        text = " ".join((text or "").split())
        if not text:
            raise MemoryError_("nothing to remember")
        kind = kind if kind in (*PROFILE_KINDS, *NOTE_KINDS) else "fact"
        now = _now()
        with self._store() as s:
            for layer in ("profile", "notes"):
                for it in s[layer]:
                    named = bool(replaces) and (it["id"].startswith(replaces) or replaces.lower() in it["text"].lower())
                    if named or _similar(it["text"], text) >= SIMILAR:
                        old, it["text"], it["updated"] = it["text"], text, now
                        return f"Updated: {old!r} -> {text!r}"
            item = {"id": uuid.uuid4().hex[:8], "text": text, "kind": kind, "created": now, "updated": now, "used": 0}
            if kind in PROFILE_KINDS:
                s["profile"].append(item)
                while _size(s["profile"]) > self.profile_limit and len(s["profile"]) > 1:
                    s["notes"].append(s["profile"].pop(0))   # the oldest profile item moves to the notebook
                where = "profile" if item in s["profile"] else "notebook"
            else:
                s["notes"].append(item)
                where = "notebook"
            if len(s["notes"]) > self.note_limit:
                s["notes"].sort(key=lambda i: (i.get("used", 0), i["updated"]))
                del s["notes"][: len(s["notes"]) - self.note_limit]
        return f"Remembered ({where})."

    def recall(self, query: str, limit: int = 5) -> list[str]:
        q = _words(query)
        with self._store() as s:
            scored = []
            for it in s["profile"] + s["notes"]:
                score = len(q & _words(it["text"])) + (0.5 if query.lower() in it["text"].lower() else 0)
                if score:
                    scored.append((score, it["updated"], it))
            scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
            hits = [it for _, _, it in scored[:limit]]
            for it in hits:
                it["used"] = it.get("used", 0) + 1
            return [f"[{it['id']}] {it['text']} ({it['updated'][:10]})" for it in hits]

    def forget(self, item: str) -> str:
        """Remove one item by id, or by text when exactly one item matches."""
        with self._store() as s:
            found = [(layer, it) for layer in ("profile", "notes") for it in s[layer]
                     if item and (it["id"].startswith(item) or item.lower() in it["text"].lower())]
            if not found:
                return "Nothing matched; nothing was removed."
            if len(found) > 1:
                return "Several items match; say which one:\n" + "\n".join(f"[{i['id']}] {i['text']}" for _, i in found)
            layer, it = found[0]
            s[layer].remove(it)
            return f"Forgot: {it['text']}"

    def briefing(self, name: str, extra: list[str] | None = None, now: dt.datetime | None = None) -> str:
        """What is loaded at the start of every conversation: short enough for a voice assistant."""
        now = now or dt.datetime.now().astimezone()
        with self._store() as s:
            prof = [it["text"] for it in s["profile"]]
            recent = [it["text"] for it in sorted(s["notes"], key=lambda i: i["updated"], reverse=True)[:5]]
        lines = [f"Speaking with {name}. Now: {now:%A %B %-d, %Y %-I:%M %p %Z}."]
        if prof:
            lines += ["About them:"] + [f"- {t}" for t in prof]
        if extra:
            lines += extra
        if recent:
            lines += ["Recently remembered:"] + [f"- {t}" for t in recent]
        lines.append("Use recall for anything else they may have told you before; save new lasting facts with remember.")
        return "\n".join(lines)

    def version(self) -> tuple:
        """Changes whenever the memory files change (lets callers cache the briefing safely)."""
        return tuple((self.folder / f"{n}.json").stat().st_mtime_ns if (self.folder / f"{n}.json").exists() else 0
                     for n in ("profile", "notes"))

    def dump(self) -> dict:
        with self._store() as s:
            return {"profile": s["profile"], "notes": s["notes"]}


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", s.lower()) if w not in STOP and len(w) > 1}


def _similar(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def _size(items: list[dict]) -> int:
    return sum(len(i["text"]) for i in items)


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="minutes")
