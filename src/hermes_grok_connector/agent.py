"""The agent side: an OpenAI-style Responses endpoint. Hermes' API server is the default; anything that speaks
POST /v1/responses with `previous_response_id` works.

Replies are chained for the rest of the day (up to 6 hours), so a spoken "yes" reaches the question the agent asked
and "what we talked about this morning" still has context.

Voice can't sit silent: Grok re-sends a request when a tool stalls (docs/lessons-learned.md). So ask_soon always
returns within the person's wait_seconds. A long job keeps running, its answer goes to notify_command and is read out
at the next request, and repeats while it runs aren't started.
"""
from __future__ import annotations

import collections
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from .config import Config, Person, resolve_secret

CHAIN_SECONDS = 6 * 3600
DIALOG_SECONDS = 2 * 3600
LATE = ("That one is taking a while, so it keeps running in the background. {how} Tell the person that now, and don't "
        "ask again for this request.")
STILL = ("The last request is still running, so this one was not started: {about}. Tell the person, and don't repeat "
         "the request.")


class _Job:
    def __init__(self, request: str) -> None:
        self.request, self.answer, self.late, self.done = request, "", False, threading.Event()


class AgentClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._last: dict[str, tuple[str, float]] = {}
        self._jobs: dict[str, _Job] = {}        # person -> the request running now
        self._earlier: dict[str, str] = {}      # person -> a late answer not yet read out
        self._dialog: dict[str, collections.deque] = collections.defaultdict(lambda: collections.deque(maxlen=12))
        self._lock = threading.Lock()

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

    def ask_soon(self, person: Person, request: str) -> str:
        """ask, but always back within wait_seconds; see the module docstring."""
        with self._lock:
            running = self._jobs.get(person.id)
            if running:
                return STILL.format(about=running.request[:80])
            job = self._jobs[person.id] = _Job(request)
            earlier = self._earlier.pop(person.id, "")
        threading.Thread(target=self._run, args=(person, job), daemon=True).start()
        before = f"The answer to the earlier request: {earlier}\n\nAnd for this request: " if earlier else ""
        if not job.done.wait(person.agent.wait_seconds):
            with self._lock:
                if not job.done.is_set():
                    job.late = True
                    how = "The answer will arrive by message when it's ready." if person.notify_command else \
                          "The answer can be read out at the next request."
                    return before + LATE.format(how=how)
        return before + job.answer

    def _run(self, person: Person, job: _Job) -> None:
        try:
            job.answer = self.ask(person, job.request)
        except Exception as e:  # the speaker must always hear something
            print(f"agent call failed for {person.id}: {e!r}", file=sys.stderr, flush=True)
            job.answer = "Your agent had a problem with that. Try again in a minute."
        self._dialog[person.id].append((time.time(), job.request, job.answer))
        with self._lock:
            self._jobs.pop(person.id, None)
            if job.late:
                self._earlier[person.id] = job.answer
            job.done.set()
        if job.late and person.notify_command:
            try:
                subprocess.run(person.notify_command, input=f"You asked: {job.request[:200]}\nAnswer: {job.answer}",
                               text=True, capture_output=True, timeout=60)
            except (OSError, subprocess.TimeoutExpired) as e:
                print(f"notify_command failed for {person.id}: {e!r}", file=sys.stderr, flush=True)

    def recent_dialog(self, person: Person) -> str:
        """What went through the agent lately, saved with a backlog item."""
        now = time.time()
        lines = [f"[{time.strftime('%H:%M', time.localtime(t))}] Asked: {q}\nAnswered: {a}"
                 for t, q, a in self._dialog[person.id] if now - t < DIALOG_SECONDS]
        with self._lock:
            if person.id in self._jobs:
                lines.append(f"Still running: {self._jobs[person.id].request}")
        return "\n\n".join(lines)


def final_text(response: dict) -> str:
    """The last assistant message in a Responses payload, skipping progress commentary."""
    texts = [c.get("text", "") for item in response.get("output", [])
             if item.get("type") == "message" and item.get("phase") != "commentary"
             for c in item.get("content", []) if c.get("type") == "output_text"]
    return (texts[-1] if texts else "").strip()


def _same_day(ts: float) -> bool:
    return time.localtime(ts).tm_yday == time.localtime().tm_yday
