"""Tests for DictationService._learn_fired_corrections."""

from grogu.config import Config
from grogu.dictation import DictationService
from grogu.dictionary import Dictionary


def _service(tmp_path):
    config = Config()
    dictionary = Dictionary(str(tmp_path / "dictionary.json"))
    service = DictationService(config, dictionary=dictionary)
    return service, dictionary


def test_learns_new_corrections(tmp_path):
    service, dictionary = _service(tmp_path)
    fired = [
        {"heard": "cloud code", "write": "Claude Code", "count": 2},
        {"heard": "vercel", "write": "Vercel", "count": 1},
    ]
    service._learn_fired_corrections(fired)
    pairs = [(c.heard, c.write) for c in dictionary.corrections]
    assert ("cloud code", "Claude Code") in pairs
    assert ("vercel", "Vercel") in pairs


def test_learn_skips_existing_case_insensitive(tmp_path):
    service, dictionary = _service(tmp_path)
    dictionary.add_correction("cloud code", "Claude Code")
    service._learn_fired_corrections(
        [{"heard": "CLOUD CODE", "write": "claude code", "count": 1}]
    )
    assert len(dictionary.corrections) == 1  # no duplicate added


def test_learn_skips_empty(tmp_path):
    service, dictionary = _service(tmp_path)
    service._learn_fired_corrections([{"heard": "", "write": "X", "count": 1}])
    service._learn_fired_corrections([{"heard": "X", "write": "", "count": 1}])
    assert dictionary.corrections == []


def test_learn_persists_to_disk(tmp_path):
    service, dictionary = _service(tmp_path)
    service._learn_fired_corrections(
        [{"heard": "cloud code", "write": "Claude Code", "count": 1}]
    )
    reloaded = Dictionary(str(tmp_path / "dictionary.json"))
    assert [(c.heard, c.write) for c in reloaded.corrections] == [
        ("cloud code", "Claude Code")
    ]
