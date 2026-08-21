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


# --- export ----------------------------------------------------------------

def _entries():
    return [
        {"ts": 1724000000.0, "raw": "um hi", "text": "Hi.",
         "source": "button",
         "corrections": [{"heard": "cloud code", "write": "Claude Code",
                          "count": 1}]},
        {"ts": 1724000060.0, "raw": "yo", "text": "Yo.",
         "source": "hotkey"},
    ]


def test_export_txt(tmp_path):
    h = HistoryStore(str(tmp_path / "h.jsonl"))
    out = h.export(_entries(), "txt")
    assert "Hi." in out and "Yo." in out
    assert "[button]" in out and "[hotkey]" in out
    assert "cloud code → Claude Code" in out


def test_export_markdown(tmp_path):
    h = HistoryStore(str(tmp_path / "h.jsonl"))
    out = h.export(_entries(), "md")
    assert out.startswith("## ")
    assert "Hi." in out and "Yo." in out
    assert "Corrections applied" in out


def test_export_csv(tmp_path):
    h = HistoryStore(str(tmp_path / "h.jsonl"))
    out = h.export(_entries(), "csv")
    lines = out.strip().splitlines()
    assert lines[0] == "timestamp,source,text,corrections"
    assert len(lines) == 3  # header + 2 entries
    assert "Hi." in out and "Yo." in out
    assert "cloud code → Claude Code" in out


def test_export_writes_file(tmp_path):
    h = HistoryStore(str(tmp_path / "h.jsonl"))
    target = tmp_path / "out.md"
    h.export(_entries(), "md", path=str(target))
    assert target.exists()
    assert "Hi." in target.read_text(encoding="utf-8")


def test_export_empty(tmp_path):
    h = HistoryStore(str(tmp_path / "h.jsonl"))
    assert h.export([], "txt") == ""
    assert h.export([], "csv") == "timestamp,source,text,corrections\n"
