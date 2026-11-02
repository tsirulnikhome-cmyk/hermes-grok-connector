import datetime as dt
import itertools
import re

import pytest

from hermes_grok_connector import config as cfg
from hermes_grok_connector.honcho_memory import HonchoMemory, memory_for
from hermes_grok_connector.memory import Memory, MemoryError_


class FakeHoncho:
    """Just enough of the Honcho v3 API: conclusions (word overlap stands in for meaning), cards, context."""

    def __init__(self):
        self.facts, self.cards, self.ids = {}, {}, itertools.count(1)

    @staticmethod
    def _dist(a, b):
        wa, wb = set(re.findall(r"\w+", a.lower())), set(re.findall(r"\w+", b.lower()))
        return 1 - len(wa & wb) / len(wa | wb) if wa and wb else 1.0

    def __call__(self, method, path, body=None, **q):
        if path == "/peers":
            return {"id": body["id"]}
        if path == "/conclusions" and method == "POST":
            for c in body["conclusions"]:
                i = f"c{next(self.ids):07d}"
                self.facts[i] = {"id": i, "content": c["content"], "observer": c["observer_id"],
                                 "observed": c["observed_id"], "created_at": "2026-01-05T00:00:00Z"}
            return None

        def mine(f):
            return [c for c in self.facts.values() if c["observer"] == f["observer"] and c["observed"] == f["observed"]]
        if path == "/conclusions/list":
            return {"items": mine(body["filters"]), "pages": 1}
        if path == "/conclusions/query":
            hits = sorted(mine(body["filters"]), key=lambda c: self._dist(body["query"], c["content"]))
            if "distance" in body:
                hits = [c for c in hits if self._dist(body["query"], c["content"]) <= body["distance"]]
            return hits[: body["top_k"]]
        if path.startswith("/conclusions/") and method == "DELETE":
            self.facts.pop(path.rsplit("/", 1)[1])
            return None
        m = re.fullmatch(r"/peers/([\w-]+)/(card|context)", path)
        key = (m.group(1), q["target"])
        if m.group(2) == "card" and method == "PUT":
            self.cards[key] = body["peer_card"]
            return None
        if m.group(2) == "card":
            return {"peer_card": self.cards.get(key)}
        rep = "## Explicit\n" + "\n".join(f"[2026-01-05 10:00:00] {c['content']}" for c in mine({"observer": key[0], "observed": key[1]}))
        return {"peer_card": self.cards.get(key), "representation": rep}


@pytest.fixture
def fake(monkeypatch):
    f = FakeHoncho()
    monkeypatch.setattr(HonchoMemory, "_api", lambda self, *a, **k: f(*a, **k))
    monkeypatch.setattr("hermes_grok_connector.honcho_memory.SAME", 0.2)
    return f


@pytest.fixture
def mem():
    return HonchoMemory(cfg.HonchoServer(), "alice-agent", "alice")


def test_profile_on_card_and_in_briefing_without_repeats(fake, mem):
    assert "profile" in mem.remember("Prefers aisle seats", "preference")
    assert "notebook" in mem.remember("Dentist appointment planned for March 3", "plan")
    b = mem.briefing("Alice", now=dt.datetime(2026, 1, 5, 9, 30))
    assert b.count("Prefers aisle seats") == 1 and "Dentist appointment" in b and "Speaking with Alice" in b
    assert "##" not in b and "2026-01-05 10:00" not in b


def test_facts_belong_to_the_observer(fake, mem):
    mem.remember("Likes short answers", "preference")
    (c,) = fake.facts.values()
    assert (c["observer"], c["observed"]) == ("alice-agent", "alice")


def test_update_by_replaces_and_by_same_meaning(fake, mem):
    mem.remember("Soccer practice is on Tuesdays")
    assert mem.remember("Soccer practice is on Wednesdays", "fact", "soccer practice").startswith("Updated")
    assert mem.remember("soccer practice is on wednesdays.").startswith("Updated")
    assert [n["text"] for n in mem.dump()["notes"]] == ["soccer practice is on wednesdays."]


def test_different_facts_stay_separate(fake, mem):
    mem.remember("Dana's piano lesson is on Tuesdays")
    mem.remember("Sam's piano lesson is on Tuesdays")
    assert len(mem.dump()["notes"]) == 2


def test_people_are_separate(fake, mem):
    bob = HonchoMemory(cfg.HonchoServer(), "bob-agent", "bob")
    bob.remember("Keeps the cabin at 70", "preference")
    assert "cabin" not in mem.briefing("Alice") and mem.recall("cabin") == [] and "cabin" in bob.recall("cabin")[0]


def test_forget_needs_one_match_and_clears_the_card(fake, mem):
    mem.remember("Gate code is on the fridge", "about")
    mem.remember("Gate repair is booked")
    assert mem.forget("gate").startswith("Several")
    assert mem.forget("fridge").startswith("Forgot")
    assert mem.dump()["profile"] == []


def test_version_changes_with_memory(fake, mem):
    v = mem.version()
    mem.remember("Something new")
    assert mem.version() != v


def test_server_down_is_a_memory_error(monkeypatch):
    m = HonchoMemory(cfg.HonchoServer(base_url="http://127.0.0.1:9"), "a", "b")
    with pytest.raises(MemoryError_):
        m.recall("x")


def test_config_picks_the_backend_per_person(tmp_path):
    p = tmp_path / "people.yaml"
    p.write_text("""
server: {public_host: agent.example.com}
honcho: {base_url: "http://127.0.0.1:8000", workspace: family}
people:
  alice: {url_key: "env:A", honcho: {observer: alice-agent, peer: alice}}
  bob: {url_key: "env:B"}
""")
    c = cfg.load(p)
    assert isinstance(memory_for(c.people["alice"]), HonchoMemory)
    assert isinstance(memory_for(c.people["bob"]), Memory)


def test_honcho_block_without_a_server_is_refused(tmp_path):
    p = tmp_path / "people.yaml"
    p.write_text("server: {public_host: x}\npeople:\n  alice: {url_key: 'env:A', honcho: {peer: alice}}\n")
    with pytest.raises(cfg.ConfigError):
        cfg.load(p)
