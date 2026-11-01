import datetime as dt

import pytest

from hermes_grok_connector.memory import Memory, MemoryError_


@pytest.fixture
def mem(tmp_path):
    return Memory(tmp_path / "alice")


def test_profile_and_notebook_layers(mem):
    assert "profile" in mem.remember("Prefers aisle seats", "preference")
    assert "notebook" in mem.remember("Dentist appointment planned for March 3", "plan")
    b = mem.briefing("Alice")
    assert "Speaking with Alice" in b and "Prefers aisle seats" in b and "Dentist appointment" in b


def test_update_by_replaces_and_identical_repeat(mem):
    mem.remember("Soccer practice is on Tuesdays", "fact")
    assert mem.remember("Soccer practice is on Wednesdays", "fact", replaces="soccer practice").startswith("Updated")
    assert mem.remember("soccer practice is on wednesdays.", "fact").startswith("Updated")
    assert [i["text"] for i in mem.dump()["notes"]] == ["soccer practice is on wednesdays."]


def test_different_facts_with_shared_words_stay_separate(mem):
    mem.remember("Dana's piano lesson is on Tuesdays", "fact")
    mem.remember("Sam's piano lesson is on Tuesdays", "fact")
    assert len(mem.dump()["notes"]) == 2


def test_profile_cap_moves_oldest_to_notebook(tmp_path):
    mem = Memory(tmp_path / "bob", profile_limit=60)
    mem.remember("First preference about hotels and points", "preference")
    mem.remember("Second preference about coffee orders daily", "preference")
    d = mem.dump()
    assert [i["text"] for i in d["profile"]] == ["Second preference about coffee orders daily"]
    assert d["notes"][0]["text"].startswith("First preference")


def test_recall_and_forget(mem):
    mem.remember("Gate code at the lake house changed in spring", "fact")
    mem.remember("Lake house HOA is Pine Ridge", "fact")
    assert len(mem.recall("lake house")) == 2
    assert mem.forget("lake").startswith("Several")
    assert mem.forget("gate code").startswith("Forgot")
    assert mem.recall("gate") == []


def test_people_are_separate(tmp_path):
    a, b = Memory(tmp_path / "alice"), Memory(tmp_path / "bob")
    a.remember("Likes the cabin at 70 degrees", "preference")
    assert b.recall("cabin") == [] and "cabin" not in b.briefing("Bob")


def test_files_are_private(mem):
    mem.remember("x y z words here", "fact")
    assert oct((mem.folder / "notes.json").stat().st_mode)[-3:] == "600"


def test_briefing_extra_lines_and_time(mem):
    b = mem.briefing("Alice", ["Today:", "- 17:00 call the plumber"], now=dt.datetime(2026, 1, 5, 9, 30))
    assert "Monday January 5, 2026 9:30 AM" in b and "call the plumber" in b


def test_empty_rejected(mem):
    with pytest.raises(MemoryError_):
        mem.remember("   ")
