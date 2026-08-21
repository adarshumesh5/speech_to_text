"""Tests for sotto.config."""

import json

from sotto.config import Config


def test_defaults():
    cfg = Config()
    assert cfg.hotkey == "Ctrl+Shift+Space"
    assert cfg.mode == "hold"
    assert cfg.model == "small.en"
    assert cfg.cleaner == "rules"
    assert cfg.vad_filter is True


def test_round_trip(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config()
    cfg.hotkey = "Alt+F9"
    cfg.model = "medium.en"
    cfg.mic_device = "Microphone (Realtek)"
    cfg.save(str(path))

    loaded = Config.load(str(path))
    assert loaded.hotkey == "Alt+F9"
    assert loaded.model == "medium.en"
    assert loaded.mic_device == "Microphone (Realtek)"


def test_unknown_keys_survive_round_trip(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config()
    cfg._extra["first_run_done"] = True
    cfg.save(str(path))

    loaded = Config.load(str(path))
    assert loaded._extra["first_run_done"] is True


def test_missing_file_returns_defaults(tmp_path):
    loaded = Config.load(str(tmp_path / "nope.json"))
    assert loaded.hotkey == "Ctrl+Shift+Space"


def test_corrupt_file_returns_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json!!")
    loaded = Config.load(str(path))
    assert loaded.model == "small.en"


def test_auto_device_resolution():
    cfg = Config()
    assert cfg.resolve_device() == "cuda"
    cfg.device = "cpu"
    assert cfg.resolve_device() == "cpu"
    assert cfg.resolve_compute_type("cuda") == "float16"
    assert cfg.resolve_compute_type("cpu") == "int8"


def test_migrate_from_sotto(tmp_path, monkeypatch):
    """First run of Grogu copies the old Sotto data folder over."""
    import sotto.config as cfg

    old = tmp_path / "Sotto"
    old.mkdir()
    (old / "config.json").write_text('{"hotkey": "Alt+F9"}', encoding="utf-8")
    (old / "dictionary.json").write_text('{"words": []}', encoding="utf-8")
    (old / "history.jsonl").write_text('{"text": "hi"}\n', encoding="utf-8")
    monkeypatch.setattr(cfg, "LEGACY_DATA_DIR", str(old))
    new = tmp_path / "Grogu"
    monkeypatch.setattr(cfg, "APP_DATA_DIR", str(new))

    cfg.migrate_from_sotto()

    assert (new / "config.json").exists()
    assert (new / "dictionary.json").exists()
    assert (new / "history.jsonl").exists()
    # the source folder is left untouched as a backup
    assert (old / "config.json").exists()


def test_migrate_skips_when_target_exists(tmp_path, monkeypatch):
    import sotto.config as cfg

    old = tmp_path / "Sotto"
    old.mkdir()
    (old / "config.json").write_text('{"hotkey": "Alt+F9"}', encoding="utf-8")
    new = tmp_path / "Grogu"
    new.mkdir()
    (new / "config.json").write_text('{"hotkey": "Ctrl+F9"}', encoding="utf-8")
    monkeypatch.setattr(cfg, "LEGACY_DATA_DIR", str(old))
    monkeypatch.setattr(cfg, "APP_DATA_DIR", str(new))

    cfg.migrate_from_sotto()

    assert (new / "config.json").read_text() == '{"hotkey": "Ctrl+F9"}'


def test_migrate_noop_without_legacy(tmp_path, monkeypatch):
    import sotto.config as cfg

    monkeypatch.setattr(cfg, "LEGACY_DATA_DIR", str(tmp_path / "nope"))
    monkeypatch.setattr(cfg, "APP_DATA_DIR", str(tmp_path / "Grogu"))
    cfg.migrate_from_sotto()  # must not raise
    assert not (tmp_path / "Grogu").exists()
