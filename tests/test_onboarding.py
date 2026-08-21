"""Tests for the onboarding wizard (offscreen Qt)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import grogu.ui.onboarding as ob  # noqa: E402
from grogu.config import Config  # noqa: E402
from grogu.dictation import DictationService  # noqa: E402
from grogu.dictionary import Dictionary  # noqa: E402

_APP = None


def _get_app():
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP


def _wizard(tmp_path, hotkey="Alt+F12"):
    cfg = Config()
    cfg.hotkey = hotkey
    dictionary = Dictionary(str(tmp_path / "dictionary.json"))
    service = DictationService(cfg, dictionary=dictionary)
    return cfg, service, ob.OnboardingWizard(cfg, service)


def test_three_pages(tmp_path):
    _get_app()
    _cfg, _svc, w = _wizard(tmp_path)
    assert len(w._pages) == 3
    assert w._page == 0


def test_next_navigates(tmp_path):
    _get_app()
    cfg, _svc, w = _wizard(tmp_path)
    w._go_next()
    assert w._page == 1
    w._go_next()
    assert w._page == 2
    assert w.next_btn.text() == "Finish"


def test_back_navigates(tmp_path):
    _get_app()
    _cfg, _svc, w = _wizard(tmp_path)
    w._go_next()
    w._go_back()
    assert w._page == 0
    assert w.back_btn.isEnabled() is False


def test_hotkey_saved_on_next(tmp_path):
    _get_app()
    cfg, _svc, w = _wizard(tmp_path)
    w._go_next()  # page 0 -> 1; saves hotkey
    assert cfg.hotkey == "Alt+F12"


def test_hotkey_saved_even_when_in_use(tmp_path, monkeypatch):
    _get_app()
    # conflict path: register fails, user clicks Yes to apply anyway
    monkeypatch.setattr(ob, "test_register", lambda spec: (False, "in use"))
    cfg, _svc, w = _wizard(tmp_path, hotkey="Alt+F12")
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        ob.QMessageBox, "question",
        lambda *a, **k: QMessageBox.StandardButton.Yes,
    )
    assert w._save_hotkey() is True
    assert cfg.hotkey == "Alt+F12"


def test_hotkey_invalid_rejected(tmp_path, monkeypatch):
    _get_app()
    monkeypatch.setattr(ob, "parse_hotkey",
                        lambda spec: (_ for _ in ()).throw(ValueError("bad")))
    _cfg, _svc, w = _wizard(tmp_path)
    w.hotkey_edit.setKeySequence("NOT_A_KEY")
    assert w._save_hotkey() is False


def test_finish_sets_flag(tmp_path):
    _get_app()
    _cfg, _svc, w = _wizard(tmp_path)
    w._go_next()
    w._go_next()
    w._go_next()  # Finish
    assert w.finished_ok is True
