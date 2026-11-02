import json

import pytest
from starlette.testclient import TestClient

from hermes_grok_connector import config as config_mod
from hermes_grok_connector import server
from hermes_grok_connector.agent import final_text

KEY_A, KEY_B = "a" * 32, "b" * 32
HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("HGC_KEY_ALICE", KEY_A)
    monkeypatch.setenv("HGC_KEY_BOB", KEY_B)
    p = tmp_path / "people.yaml"
    p.write_text(f"""
server: {{public_host: agent.example.com}}
memory_root: {tmp_path}/memory
backlog_file: {tmp_path}/backlog.json
people:
  alice: {{name: Alice, url_key: "env:HGC_KEY_ALICE", topics: "her garden"}}
  bob: {{name: Bob, url_key: "env:HGC_KEY_BOB", agent: {{path: /p/bob/v1/responses}}}}
""")
    return config_mod.load(p)


def rpc(client, key, method, params=None):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    r = client.post(f"/c/{key}/mcp", headers=HEADERS, content=json.dumps(body))
    assert r.status_code == 200, r.text
    data = [line[6:] for line in r.text.splitlines() if line.startswith("data: ")]
    return json.loads(data[0] if data else r.text)["result"]


def call(client, key, tool, **args):
    return rpc(client, key, "tools/call", {"name": tool, "arguments": args})["content"][0]["text"]


def test_tools_and_identity_by_address(cfg, monkeypatch):
    asked = []
    monkeypatch.setattr(server.AgentClient, "ask", lambda self, person, req: asked.append(person.id) or "ok")
    with TestClient(server.build_app(cfg)) as c:
        names = [t["name"] for t in rpc(c, KEY_A, "tools/list")["tools"]]
        assert names == ["my_context", "ask_my_agent", "send_to_backlog", "remember", "recall", "forget"]
        assert call(c, KEY_A, "remember", text="Grows tomatoes every summer", kind="preference").startswith("Remembered")
        assert "Grows tomatoes" in call(c, KEY_A, "my_context")
        assert "tomatoes" not in call(c, KEY_B, "my_context")      # Bob's address reaches Bob's memory only
        call(c, KEY_B, "ask_my_agent", request="hi")
        assert asked == ["bob"]


def test_live_briefing_in_instructions(cfg):
    with TestClient(server.build_app(cfg)) as c:
        call(c, KEY_A, "remember", text="Allergic to cats", kind="about")
        server_info = rpc(c, KEY_A, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                    "clientInfo": {"name": "t", "version": "1"}})
        assert "Allergic to cats" in server_info["instructions"]


def test_unknown_address_is_404(cfg):
    with TestClient(server.build_app(cfg)) as c:
        assert c.post("/c/wrong/mcp", headers=HEADERS, content="{}").status_code == 404
        assert c.get("/").status_code == 404


def test_short_or_missing_key_refused(cfg, monkeypatch):
    monkeypatch.setenv("HGC_KEY_BOB", "short")
    with pytest.raises(SystemExit):
        server.build_app(cfg)


def test_secrets_must_be_references():
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve_secret("plain-secret-value")


def test_final_text_skips_commentary():
    out = {"output": [
        {"type": "message", "phase": "commentary", "content": [{"type": "output_text", "text": "working..."}]},
        {"type": "function_call", "name": "x"},
        {"type": "message", "content": [{"type": "output_text", "text": "You have 3 reminders."}]}]}
    assert final_text(out) == "You have 3 reminders."
