import json
import threading
import time
from pathlib import Path

import pytest

from hermes_grok_connector import backlog, cli
from hermes_grok_connector import config as config_mod
from hermes_grok_connector import agent as agent_mod
from hermes_grok_connector.agent import AgentClient


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_mod, "NOTIFY_AFTER", 0.05)
    monkeypatch.setenv("HGC_KEY_ALICE", "a" * 32)
    monkeypatch.setenv("HGC_KEY_BOB", "b" * 32)
    p = tmp_path / "people.yaml"
    p.write_text(f"""
server: {{public_host: agent.example.com}}
memory_root: {tmp_path}/memory
backlog_file: {tmp_path}/backlog.json
agent_defaults: {{wait_seconds: 0.05, repeat_wait_seconds: 0.05}}
people:
  alice: {{name: Alice, url_key: "env:HGC_KEY_ALICE", notify_command: ["tee", "{tmp_path}/late.txt"]}}
  bob: {{name: Bob, url_key: "env:HGC_KEY_BOB"}}
""")
    return config_mod.load(p)


def wait_until(check):
    for _ in range(300):
        if check():
            return
        time.sleep(0.01)
    raise AssertionError("never happened")


def gated(client, gate, seen=None):
    def ask(person, request):
        (seen if seen is not None else []).append(request)
        gate.wait(5)
        return f"answer to {request}"
    client.ask = ask


def test_quick_answer_comes_straight_back(cfg):
    a = AgentClient(cfg)
    a.ask = lambda person, request: "three"
    assert a.ask_soon(cfg.people["alice"], "how many") == "three"


def test_slow_answer_says_call_again_then_notifies_and_reads_it_out_next(cfg):
    a, gate, alice = AgentClient(cfg), threading.Event(), cfg.people["alice"]
    gated(a, gate)
    reply = a.ask_soon(alice, "big check")
    assert "call ask_my_agent again" in reply
    gate.set()
    late = Path(cfg.backlog_file).parent / "late.txt"
    wait_until(lambda: late.exists() and "answer to big check" in late.read_text())
    wait_until(lambda: alice.id not in a._jobs)
    next_reply = a.ask_soon(alice, "battery")
    assert "answer to big check" in next_reply and "answer to battery" in next_reply
    assert "answer to big check" not in a.ask_soon(alice, "again")          # read out once


def test_repeat_calls_change_the_line_then_stop(cfg):
    a, gate, seen, bob = AgentClient(cfg), threading.Event(), [], cfg.people["bob"]
    gated(a, gate, seen)
    assert a.ask_soon(bob, "big check") == agent_mod.LATE
    assert a.ask_soon(bob, "big check") == agent_mod.LATE_AGAIN
    stop = a.ask_soon(bob, "big check")
    assert "next request" in stop and "don't call again" in stop
    assert seen == ["big check"]
    gate.set()


def test_asking_again_collects_the_answer_and_nothing_is_notified(cfg, monkeypatch):
    monkeypatch.setattr(agent_mod, "NOTIFY_AFTER", 0.2)
    a, gate, seen, alice = AgentClient(cfg), threading.Event(), [], cfg.people["alice"]
    gated(a, gate, seen)
    a.ask_soon(alice, "Read the email, then compare")
    gate.set()
    wait_until(lambda: alice.id not in a._jobs)
    assert "answer to Read the email" in a.ask_soon(alice, "Read the email. Then compare")
    assert seen == ["Read the email, then compare"]
    time.sleep(0.3)
    assert not (Path(cfg.backlog_file).parent / "late.txt").exists()


@pytest.mark.parametrize("answer, tools, flagged", [
    ("Your reminder is set for five.", [], True),
    ("Your reminder is set for five.", [("mcp__x__set_reminder", True)], False),
    ("Your reminder is set for five.", [("mcp__x__set_reminder", False)], True),
    ("I've locked the car.", [("mcp__x__car_lock", True)], False),
    ("I've locked the car.", [], True),
    ("I'll let you know when it arrives.", [], True),
    ("I'll text her no thanks. Okay?", [], False),
    ("Want me to set a reminder?", [], False),
    ("I didn't set a reminder.", [], False),
    ("You have a reminder set for five.", [("mcp__x__list_reminders", True)], False),
    ("The estimate pays nothing.", [], False),
])
def test_what_it_says_it_did_is_checked_against_the_tools(answer, tools, flagged):
    assert bool(agent_mod.unconfirmed(answer, tools)) is flagged


def test_no_tool_record_means_no_check():
    assert agent_mod.unconfirmed("Your reminder is set.", None) == ""


def test_a_claim_with_no_tool_is_spoken_with_the_warning(cfg):
    a = AgentClient(cfg)
    def ask(person, request):
        agent_mod._ran.tools = []
        return "Your reminder is set for five."
    a.ask = ask
    cfg.people["bob"].agent.wait_seconds = 1
    assert agent_mod.UNCONFIRMED.strip() in a.ask_soon(cfg.people["bob"], "set it")


def test_repeats_while_running_are_not_started(cfg):
    a, gate, seen, alice = AgentClient(cfg), threading.Event(), [], cfg.people["alice"]
    gated(a, gate, seen)
    a.ask_soon(alice, "big check")
    assert "not started" in a.ask_soon(alice, "big check, reworded")
    assert seen == ["big check"]
    gate.set()


def test_people_do_not_block_each_other(cfg):
    a, gate = AgentClient(cfg), threading.Event()
    a.ask = lambda person, request: gate.wait(5) and "late" if person.id == "alice" else "for bob"
    a.ask_soon(cfg.people["alice"], "big check")
    assert a.ask_soon(cfg.people["bob"], "hi") == "for bob"
    gate.set()


def test_agent_failure_still_says_something(cfg):
    a = AgentClient(cfg)
    def boom(person, request):
        raise RuntimeError("x")
    a.ask = boom
    assert "had a problem" in a.ask_soon(cfg.people["alice"], "hi")


def test_backlog_add_resend_show_close(tmp_path):
    f = tmp_path / "b.json"
    one = backlog.add(f, "Alice", "bug", "The door note is wrong", "Asked: x")
    assert backlog.add(f, "Alice", "bug", "the door note is wrong")["n"] == one["n"]      # a re-send
    assert backlog.add(f, "Bob", "idea", "The door note is wrong")["n"] == 2              # someone else
    assert "Asked: x" in backlog.show(f, 1)
    assert backlog.close(f, 1, "fixed") == "Closed 1."
    assert [i["status"] for i in backlog.items(f)] == ["done", "open"]
    assert f.stat().st_mode & 0o777 == 0o600
    assert backlog.close(f, 9, "x") == "No item 9."


def test_cli_lists_and_closes(cfg, tmp_path, capsys):
    backlog.add(cfg.backlog_file, "Alice", "question", "Check these numbers")
    conf = ["--config", str(tmp_path / "people.yaml")]
    assert cli.main(["backlog", *conf]) == 0
    assert "Check these numbers" in capsys.readouterr().out
    assert cli.main(["backlog", "close", "1", "done", *conf]) == 0
    capsys.readouterr()
    assert cli.main(["backlog", *conf]) == 0
    assert capsys.readouterr().out == ""
