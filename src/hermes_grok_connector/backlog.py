"""The backlog: things people ask, from the car, to be followed up later at a computer. One JSON file that anything on
the machine can read, such as your coding assistant's sessions, through `hermes-grok-connector backlog`. Saving is
instant, so Grok has something to say right away. Nothing is built or acted on automatically.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import json
import time
from pathlib import Path

KINDS = ("bug", "question", "idea", "concern")
RESEND_SECONDS = 600                # Grok re-sends; the same note this soon is the same item


@contextlib.contextmanager
def _locked(file: Path):
    file.parent.mkdir(parents=True, exist_ok=True)
    with open(file.with_suffix(".lock"), "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def items(file: Path) -> list[dict]:
    return json.loads(file.read_text()) if file.exists() else []


def _save(file: Path, data: list[dict]) -> None:
    tmp = file.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    tmp.chmod(0o600)
    tmp.replace(file)


def add(file: Path, who: str, kind: str, note: str, dialog: str = "") -> dict:
    with _locked(file):
        data = items(file)
        now = time.time()
        same = next((i for i in reversed(data) if i["from"] == who and i["note"].lower() == note.lower()
                     and now - i["at"] < RESEND_SECONDS), None)
        if same:
            return same
        item = {"n": max((i["n"] for i in data), default=0) + 1, "type": kind if kind in KINDS else "question",
                "from": who, "note": note[:2000], "dialog": dialog[:30000], "status": "open", "at": now,
                "logged": dt.datetime.now().isoformat(timespec="minutes")}
        data.append(item)
        _save(file, data)
        return item


def close(file: Path, n: int, note: str) -> str:
    with _locked(file):
        data = items(file)
        item = next((i for i in data if i["n"] == n), None)
        if not item:
            return f"No item {n}."
        item.update(status="done", done=note, closed=dt.datetime.now().isoformat(timespec="minutes"))
        _save(file, data)
    return f"Closed {n}."


def show(file: Path, n: int) -> str:
    i = next((i for i in items(file) if i["n"] == n), None)
    if not i:
        return f"No item {n}."
    return (f"#{i['n']} [{i['type']}] {i['status']} {i['logged']} from {i['from']}\n{i['note']}"
            + (f"\n\nConversation:\n{i['dialog']}" if i.get("dialog") else "")
            + (f"\n\nDone: {i['done']}" if i.get("done") else ""))
