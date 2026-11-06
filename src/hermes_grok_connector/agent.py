"""The agent side: an OpenAI-style Responses endpoint. Hermes' API server is the default; anything that speaks
POST /v1/responses with `previous_response_id` works.

Replies are chained for the rest of the day (up to 6 hours), so a spoken "yes" reaches the question the agent asked
and "what we talked about this morning" still has context.

Voice can't sit silent: Grok re-sends a request when a tool stalls (docs/lessons-learned.md). So ask_soon always
returns within the person's wait_seconds. A long job keeps running and Grok is told to say so and call again, at most
twice more; a repeat waits for that job instead of starting another. The answer is read out on the repeat or at the next
request, and goes to notify_command only if nobody collected it within NOTIFY_AFTER seconds.

The agent's own words aren't proof: unconfirmed() compares what it says it did with the tools it really ran, and a claim
with no tool behind it is spoken with a warning.
"""
from __future__ import annotations

import collections
import difflib
import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from .config import Config, Person, resolve_secret

CHAIN_SECONDS = 6 * 3600
DIALOG_SECONDS = 2 * 3600
NOTIFY_AFTER = 120
LATE = ("Still working on that, it needs a few more seconds. Tell the person that now, then call ask_my_agent again "
        "with the same request to get the answer. That won't start it twice.")
LATE_AGAIN = ("Still working on that. Say two or three words, not the same ones as last time, then call ask_my_agent "
              "again with the same request.")
LATE_STOP = ("Still working on that, and it's taking a while. {how} Tell the person in a few words, and don't call again "
             "for this one.")
STILL = ("Still working on the last request, so this one was not started: {about}. Tell the person that now, then call "
         "ask_my_agent again in a moment.")
DONE = "The answer to \"{about}\": {answer}"  # names the request, so a near-identical one that got this answer is audible
UNCONFIRMED = " But I can't confirm that actually happened, so don't count on it."
_CLAIMS = ((r"\bI(?:'ve| have)? (?:set|added|created|scheduled|cancel+ed|removed|deleted)\b.*\breminder|\breminder(?:'s| is| has been) "
            r"(?:set|added|created|cancel+ed|removed)", r"remind"),
           (r"\b(?:it's|it is|that's|text|message|copy|draft)\b.{0,30}\bon your phone\b|\bI(?:'ve| have)? (?:texted|sent|emailed)\b",
            r"send|text|message|mail|draft"),
           (r"\bI(?:'ve| have)? (?:locked|started|stopped|turned|set|sent)\b.*\b(?:car|doors?|climate|heat|ac|charging|destination|navigation)\b"
            r"|\bcar(?:'s| is) (?:now )?locked\b", r"car|vehicle|climate|charg|lock|navigat"),
           (r"\bI(?:'ve| have) (?:saved|noted)\b", r"memory|remember|note|save"))
_PROMISES = ((r"\bI(?:'ll| will) (?:remind you|let you know|tell you when|keep an eye|watch|check back|get back to you|follow up)\b",
              r"remind|watch|schedule"),
             (r"\bI(?:'ll| will) (?:text|send|email)\b", r"send|text|message|mail|draft"))
_NOT = re.compile(r"\b(?:not|never|can't|cannot|couldn't|didn't|won't|wasn't|haven't)\b", re.I)
_FAILED = re.compile(r"\A.{0,300}?(?:\"error\"\s*:|\berror:|\bfailed\b)", re.I | re.S)
_ran = threading.local()  # the tools the agent ran for this thread's request, as (name, worked); unset when not known


class _Job:
    def __init__(self, request: str) -> None:
        self.request, self.answer, self.late, self.done = request, "", False, threading.Event()
        self.repeats = 0


class AgentClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._last: dict[str, tuple[str, float]] = {}
        self._jobs: dict[str, _Job] = {}        # person -> the request running now
        self._earlier: dict[str, tuple[str, str]] = {}  # person -> (request, late answer), not yet read out
        self._dialog: dict[str, collections.deque] = collections.defaultdict(lambda: collections.deque(maxlen=12))
        self._lock = threading.Lock()

    def ask(self, person: Person, request: str) -> str:
        a = person.agent
        body = {"model": a.model, "input": request, "instructions": self.cfg.voice.format(name=person.name),
                "store": True}
        if a.reasoning_effort:      # someone is waiting on the line: thinking between tool steps is most of the wait
            body["model_options"] = {"reasoning_effort": a.reasoning_effort}
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
        outputs = {i.get("call_id"): str(i.get("output", "")) for i in out.get("output", []) if i.get("type") == "function_call_output"}
        _ran.tools = [(i.get("name", ""), i.get("status") == "completed" and not _FAILED.search(outputs.get(i.get("call_id"), "")))
                      for i in out.get("output", []) if i.get("type") == "function_call"]
        return final_text(out) or "Your agent had no answer."

    def ask_soon(self, person: Person, request: str) -> str:
        """ask, but always back within wait_seconds; see the module docstring."""
        start = time.monotonic()
        with self._lock:
            was = self._jobs.get(person.id)
        if was:
            was.done.wait(person.agent.repeat_wait_seconds)
        with self._lock:
            running = self._jobs.get(person.id)
            if running:
                if not _same(running.request, request):
                    return STILL.format(about=running.request[:80])
                running.repeats += 1
                if running.repeats < 2:
                    return LATE_AGAIN
                how = "The answer will arrive by message if it isn't asked for." if person.notify_command else \
                      "The answer can be read out at the next request."
                return LATE_STOP.format(how=how)
            kept = self._earlier.get(person.id)
            if was and _same(was.request, request):
                self._earlier.pop(person.id, None)
                return DONE.format(about=was.request[:80], answer=was.answer)
            if kept and _same(kept[0], request):
                del self._earlier[person.id]
                return DONE.format(about=kept[0][:80], answer=kept[1])
            job = self._jobs[person.id] = _Job(request)
            kept = self._earlier.pop(person.id, None)
        threading.Thread(target=self._run, args=(person, job), daemon=True).start()
        before = DONE.format(about=kept[0][:80], answer=kept[1]) + "\n\nAnd for this request: " if kept else ""
        if not job.done.wait(max(0, person.agent.wait_seconds - (time.monotonic() - start))):
            with self._lock:
                if not job.done.is_set():
                    job.late = True
                    return before + LATE
        return before + job.answer

    def _run(self, person: Person, job: _Job) -> None:
        started = time.time()
        try:
            job.answer = self.ask(person, job.request)
        except Exception as e:  # the speaker must always hear something
            print(f"agent call failed for {person.id}: {e!r}", file=sys.stderr, flush=True)
            job.answer = "Your agent had a problem with that. Try again in a minute."
        tools = getattr(_ran, "tools", None)
        flagged = bool(person.agent.check_claims and unconfirmed(job.answer, tools))
        if flagged:
            job.answer += UNCONFIRMED
        print(f"JOB {time.strftime('%Y-%m-%d %H:%M:%S')} {person.id} agent_ms={int((time.time() - started) * 1000)} "
              f"tools={[name.split('__')[-1] for name, _ in tools or []]} unconfirmed={flagged}", file=sys.stderr, flush=True)
        self._dialog[person.id].append((time.time(), job.request, job.answer))
        with self._lock:
            self._jobs.pop(person.id, None)
            if job.late:
                self._earlier[person.id] = (job.request, job.answer)
            job.done.set()
        if job.late and person.notify_command:
            threading.Timer(NOTIFY_AFTER, self._notify_unheard, args=(person, job)).start()

    def _notify_unheard(self, person: Person, job: _Job) -> None:
        with self._lock:
            if self._earlier.get(person.id) != (job.request, job.answer):
                return
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


def unconfirmed(answer: str, tools: list[tuple[str, bool]] | None) -> str:
    """The sentence that says something was done or promised with no matching tool behind it, else "". Tools are matched
    by name, so it's a hint rather than proof; no tool record means no check."""
    if tools is None:
        return ""
    worked = [name for name, ok in tools if ok]
    sentences = [t.strip() for t in re.split(r"(?<=[.!?])\s+", answer or "") if t.strip()]
    claims = _CLAIMS if sentences and sentences[-1].endswith("?") else _CLAIMS + _PROMISES  # "I'll text her. OK?" is a read-back
    for t in sentences:
        if t.endswith("?") or _NOT.search(t):
            continue
        for said, tool in claims:
            if re.search(said, t, re.I) and not any(re.search(tool, name, re.I) for name in worked):
                return t[:200]
    return ""


def _same(a: str, b: str) -> bool:
    """Grok rewords a repeat slightly ("about insurance, then" / "about insurance. Then")."""
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.8


def final_text(response: dict) -> str:
    """The last assistant message in a Responses payload, skipping progress commentary."""
    texts = [c.get("text", "") for item in response.get("output", [])
             if item.get("type") == "message" and item.get("phase") != "commentary"
             for c in item.get("content", []) if c.get("type") == "output_text"]
    return (texts[-1] if texts else "").strip()


def _same_day(ts: float) -> bool:
    return time.localtime(ts).tm_yday == time.localtime().tm_yday
