"""The agent side: an OpenAI-style Responses endpoint. Hermes' API server is the default; anything that speaks
POST /v1/responses with `previous_response_id` works.

Replies are chained for the rest of the day (up to 6 hours), so a spoken "yes" reaches the question the agent asked
and "what we talked about this morning" still has context.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .config import Config, Person, resolve_secret

CHAIN_SECONDS = 6 * 3600


class AgentClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._last: dict[str, tuple[str, float]] = {}

    def ask(self, person: Person, request: str) -> str:
        a = person.agent
        body = {"model": a.model, "input": request, "instructions": self.cfg.voice.format(name=person.name),
                "store": True}
        prev = self._last.get(person.id)
        if prev and time.time() - prev[1] < CHAIN_SECONDS and _same_day(prev[1]):
            body["previous_response_id"] = prev[0]
        headers = {"Content-Type": "application/json", "X-Hermes-Session-Key": a.session_key}
        key = resolve_secret(a.api_key)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(a.base_url.rstrip("/") + a.path, json.dumps(body).encode(), headers)
        try:
            with urllib.request.urlopen(req, timeout=a.timeout) as r:
                out = json.loads(r.read())
        except urllib.error.HTTPError as e:
            return f"Your agent didn't answer (error {e.code}). Try again in a minute."
        except TimeoutError:
            return "Your agent took too long to answer. Try again in a minute."
        except urllib.error.URLError:
            return "Your agent isn't reachable right now. Try again in a few minutes."
        self._last[person.id] = (out.get("id", ""), time.time())
        return final_text(out) or "Your agent had no answer."


def final_text(response: dict) -> str:
    """The last assistant message in a Responses payload, skipping progress commentary."""
    texts = [c.get("text", "") for item in response.get("output", [])
             if item.get("type") == "message" and item.get("phase") != "commentary"
             for c in item.get("content", []) if c.get("type") == "output_text"]
    return (texts[-1] if texts else "").strip()


def _same_day(ts: float) -> bool:
    return time.localtime(ts).tm_yday == time.localtime().tm_yday
