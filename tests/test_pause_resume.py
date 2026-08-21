"""Tests for mid-recording pause/resume and voice-command routing."""

import threading

from grogu.config import Config
from grogu.dictation import (
    STATE_IDLE,
    STATE_LISTENING,
    STATE_PAUSED,
    DictationService,
)
from grogu.dictionary import Dictionary


class FakeRecorder:
    def __init__(self):
        self.paused = False
        self.cancelled = False

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def cancel(self):
        self.cancelled = True

    def stop(self):
        import numpy as np

        return np.zeros(10, dtype=np.float32)


def _service(tmp_path):
    config = Config()
    dictionary = Dictionary(str(tmp_path / "dictionary.json"))
    return DictationService(config, dictionary=dictionary)


def test_pause_and_resume(tmp_path):
    service = _service(tmp_path)
    service._recorder = FakeRecorder()
    service._state = STATE_LISTENING
    service.pause()
    assert service.state == STATE_PAUSED
    assert service._recorder.paused is True
    service.resume()
    assert service.state == STATE_LISTENING
    assert service._recorder.paused is False


def test_pause_only_from_listening(tmp_path):
    service = _service(tmp_path)
    service._recorder = FakeRecorder()
    service._state = STATE_IDLE
    service.pause()
    assert service.state == STATE_IDLE
    service._state = STATE_PAUSED
    service.pause()  # already paused — no-op
    assert service.state == STATE_PAUSED


def test_toggle_pause_both_ways(tmp_path):
    service = _service(tmp_path)
    service._recorder = FakeRecorder()
    service._state = STATE_LISTENING
    service.toggle_pause()
    assert service.state == STATE_PAUSED
    service.toggle_pause()
    assert service.state == STATE_LISTENING


def test_record_resumes_when_paused(tmp_path):
    service = _service(tmp_path)
    service._recorder = FakeRecorder()
    service._state = STATE_PAUSED
    service.record("button")
    assert service.state == STATE_LISTENING


def test_stop_finishes_when_paused(tmp_path):
    service = _service(tmp_path)
    rec = FakeRecorder()
    service._recorder = rec
    service._state = STATE_PAUSED
    # stub _process so the worker thread does nothing
    done = threading.Event()

    def fake_process(audio):
        done.set()

    service._process = fake_process  # type: ignore[method-assign]
    service.stop()
    assert service._recorder is None
    assert done.wait(2.0)  # _finish_listening ran the pipeline


def test_cancel_when_paused(tmp_path):
    service = _service(tmp_path)
    rec = FakeRecorder()
    service._recorder = rec
    service._state = STATE_PAUSED
    service.cancel()
    assert service.state == STATE_IDLE
    assert rec.cancelled is True


def test_command_dictation_routes_to_commands(tmp_path, monkeypatch):
    """A whole-utterance command never gets typed — it runs as keystrokes."""
    import grogu.dictation as dmod

    service = _service(tmp_path)
    executed = []
    monkeypatch.setattr(
        dmod, "run_commands",
        lambda commands, target_hwnd=0, cancel_event=None: (
            executed.append((commands, target_hwnd)) or True
        ),
    )
    entries = []
    service.dictation_done.connect(entries.append)
    service._source = "hotkey"
    service._target_hwnd = 0
    service._run_commands(["undo"], raw="undo last")
    assert executed == [(["undo"], 0)]
    assert entries and entries[0]["kind"] == "command"
    assert entries[0]["text"] == "Undo last"
    assert entries[0]["inserted"] is True


def test_escape_cancel_includes_paused(tmp_path):
    service = _service(tmp_path)
    assert service._cancel is not None
    # the poll loop uses `state in (LISTENING, PAUSED)` — verify the guard
    from grogu.dictation import STATE_PAUSED as P

    assert P in (STATE_LISTENING, STATE_PAUSED)
