"""Tests for per-app insertion-mode profiles."""

import json

from grogu.config import Config
from grogu.dictation import DictationService
from grogu.dictionary import Dictionary


def test_app_modes_default_empty():
    cfg = Config()
    assert cfg.app_modes == {}


def test_app_modes_persist(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config()
    cfg.app_modes["notepad.exe"] = "keystrokes"
    cfg.app_modes["code.exe"] = "clipboard"
    cfg.save(str(path))

    loaded = Config.load(str(path))
    assert loaded.app_modes == {
        "notepad.exe": "keystrokes",
        "code.exe": "clipboard",
    }
    # raw JSON shape — plain editable file
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["app_modes"]["notepad.exe"] == "keystrokes"


def test_resolution_uses_override(tmp_path, monkeypatch):
    config = Config()
    config.insertion_mode = "clipboard"
    config.app_modes["notepad.exe"] = "keystrokes"
    service = DictationService(config, dictionary=Dictionary(str(tmp_path / "d.json")))
    monkeypatch.setattr("grogu.dictation.hwnd_exe_name", lambda hwnd: "notepad.exe")
    assert service._resolve_insertion_mode(12345) == "keystrokes"


def test_resolution_falls_back_to_global(tmp_path, monkeypatch):
    config = Config()
    config.insertion_mode = "smart"
    config.app_modes["notepad.exe"] = "keystrokes"
    service = DictationService(config, dictionary=Dictionary(str(tmp_path / "d.json")))
    monkeypatch.setattr("grogu.dictation.hwnd_exe_name", lambda hwnd: "chrome.exe")
    assert service._resolve_insertion_mode(12345) == "smart"


def test_resolution_unknown_exe_falls_back(tmp_path, monkeypatch):
    config = Config()
    config.insertion_mode = "clipboard"
    service = DictationService(config, dictionary=Dictionary(str(tmp_path / "d.json")))
    monkeypatch.setattr("grogu.dictation.hwnd_exe_name", lambda hwnd: None)
    assert service._resolve_insertion_mode(0) == "clipboard"
