"""Tests for grogu.history."""

from grogu.history import HistoryStore


def test_append_and_load(tmp_path):
    h = HistoryStore(str(tmp_path / "h.jsonl"))
    h.append({"ts": 1.0, "raw": "um hi", "text": "Hi.", "source": "button"})
    h.append({"ts": 2.0, "raw": "yo", "text": "Yo.", "source": "hotkey"})
    entries = h.load()
    assert [e["text"] for e in entries] == ["Yo.", "Hi."]  # newest first


def test_search(tmp_path):
    h = HistoryStore(str(tmp_path / "h.jsonl"))
    h.append({"ts": 1.0, "raw": "cloud code", "text": "Claude Code."})
    h.append({"ts": 2.0, "raw": "other", "text": "Ship it."})
    assert len(h.search("claude")) == 1
    assert len(h.search("cloud")) == 1  # raw text is searched too
    assert len(h.search("zzz")) == 0
    assert len(h.search("")) == 2


def test_prune(tmp_path):
    h = HistoryStore(str(tmp_path / "h.jsonl"), limit=5)
    for i in range(20):
        h.append({"ts": float(i), "text": f"entry {i}"})
    entries = h.load()
    assert len(entries) == 5
    assert entries[0]["text"] == "entry 19"


def test_clear(tmp_path):
    h = HistoryStore(str(tmp_path / "h.jsonl"))
    h.append({"ts": 1.0, "text": "x"})
    h.clear()
    assert h.load() == []


def test_missing_file(tmp_path):
    h = HistoryStore(str(tmp_path / "nope.jsonl"))
    assert h.load() == []
