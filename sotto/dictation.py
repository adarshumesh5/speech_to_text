"""DictationService — the orchestration layer.

Owns the pipeline: hotkey events → mic capture → Whisper transcription →
cleanup → text injection. Runs capture on PortAudio's callback thread, model
loading/transcription/typing on worker threads, and keeps Qt on the GUI
thread. Hotkey events arrive on a background thread and are drained here via
a QTimer poll, so all state transitions happen on the GUI thread.

States: idle → listening → (preparing) → transcribing → cleaning → typing → idle
"""

from __future__ import annotations

import logging
import queue
import threading
import time

from PySide6.QtCore import QObject, QTimer, Signal

from sotto.audio import MicRecorder
from sotto.cleaner import build_cleaner
from sotto.cues import play_start as _cue_start, play_stop as _cue_stop
from sotto.dictionary import Dictionary
from sotto.hotkey import HotkeyListener, is_key_down
from sotto.injector import (
    get_foreground_hwnd,
    get_window_title,
    is_own_window,
    select_back,
    send_text,
)
from sotto.stt import SttEngine

log = logging.getLogger(__name__)

VK_ESCAPE = 0x1B

STATE_IDLE = "idle"
STATE_PREPARING = "preparing"
STATE_LISTENING = "listening"
STATE_TRANSCRIBING = "transcribing"
STATE_CLEANING = "cleaning"
STATE_TYPING = "typing"

STATE_LABELS = {
    STATE_IDLE: "Ready",
    STATE_PREPARING: "Preparing engine…",
    STATE_LISTENING: "Listening…",
    STATE_TRANSCRIBING: "Transcribing…",
    STATE_CLEANING: "Polishing…",
    STATE_TYPING: "Typing…",
}


class DictationService(QObject):
    state_changed = Signal(str)
    mic_level = Signal(float)
    status = Signal(str)
    error = Signal(str)
    muted_changed = Signal(bool)
    dictation_done = Signal(dict)  # {raw, text, corrections, duration, source, ts}

    def __init__(self, config, dictionary: Dictionary | None = None, parent=None):
        super().__init__(parent)
        self.config = config
        self.dictionary = dictionary or Dictionary()
        self._state = STATE_IDLE
        self._lock = threading.RLock()
        self._recorder: MicRecorder | None = None
        self._cleaner = build_cleaner(config.cleaner)
        self._source = "hotkey"
        self._engine: SttEngine | None = None
        self._engine_error: Exception | None = None
        self._engine_ready = threading.Event()
        self._listener: HotkeyListener | None = None
        self._mute_listener: HotkeyListener | None = None
        self._muted = False
        self._cancel = threading.Event()
        self._hotkey_events: queue.Queue[tuple[str, ...]] = queue.Queue()
        self._mute_events: queue.Queue[tuple[str, ...]] = queue.Queue()
        self._last_error: str | None = None
        self.last_dictation: dict | None = None
        self._target_hwnd = 0   # window focused when dictation started
        self._foreign_hwnd = 0  # last external window (when Grogu had focus)

        self._level_timer = QTimer(self)
        self._level_timer.setInterval(60)
        self._level_timer.timeout.connect(self._tick_level)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(20)
        self._poll_timer.timeout.connect(self._poll_hotkeys)

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        self._start_engine_load()
        self._register_hotkey(self.config.hotkey)
        self._register_mute_hotkey(self.config.mute_hotkey)
        self._poll_timer.start()
        self._level_timer.start()
        log.info("DictationService started")

    def shutdown(self) -> None:
        self._poll_timer.stop()
        self._level_timer.stop()
        self.cancel()
        self._unregister_hotkey()
        self._unregister_mute_hotkey()

    # -- engine loading -----------------------------------------------------
    def _start_engine_load(self) -> None:
        def load() -> None:
            try:
                self._engine = SttEngine.create(
                    self.config.model,
                    device=self.config.device,
                    compute_type=self.config.compute_type,
                )
            except Exception as e:  # noqa: BLE001
                log.exception("engine load failed")
                self._engine_error = e
            finally:
                self._engine_ready.set()

        threading.Thread(target=load, name="sotto-engine", daemon=True).start()

    def _ensure_engine(self) -> SttEngine:
        if self._engine is None:
            self._engine_ready.wait()
            if self._engine_error is not None:
                raise self._engine_error
        return self._engine

    # -- hotkey -------------------------------------------------------------
    def _register_hotkey(self, spec: str) -> None:
        self._unregister_hotkey()
        try:
            self._listener = HotkeyListener(
                spec,
                on_down=lambda fg_hwnd=0: self._hotkey_events.put(("down", fg_hwnd)),
                on_up=lambda: self._hotkey_events.put(("up", 0)),
                on_error=self._on_hotkey_error,
                on_registered=lambda s: self._set_error(None),
            )
            self._listener.start()
        except ValueError as e:
            self.error.emit(f"Invalid hotkey: {e}")

    def _unregister_hotkey(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def restart_hotkey(self, spec: str) -> None:
        self.config.hotkey = spec
        self._register_hotkey(spec)
        log.info("Hotkey changed to %s", spec)

    def _on_hotkey_error(self, message: str) -> None:
        self._set_error(f"HOTKEY: {message}")
        self.error.emit(message)

    def _set_error(self, message: str | None) -> None:
        self._last_error = message
        self.status.emit(message or "READY")

    def set_cleaner(self, name: str) -> None:
        self.config.cleaner = name
        self._cleaner = build_cleaner(name)
        log.info("Cleaner set to %s", name)

    def _poll_hotkeys(self) -> None:
        try:
            while True:
                ev = self._hotkey_events.get_nowait()
                kind = ev[0]
                fg_hwnd = ev[1] if len(ev) > 1 else 0
                self._handle_hotkey(kind, fg_hwnd=fg_hwnd)
        except queue.Empty:
            pass
        # Continuously track the last external window so foreign_hwnd is
        # always fresh, even if ApplicationInactive never fires.
        cur_fg = get_foreground_hwnd()
        if cur_fg and not is_own_window(cur_fg):
            self._foreign_hwnd = cur_fg
        try:
            while True:
                ev = self._mute_events.get_nowait()
                self._handle_mute_hotkey()
        except queue.Empty:
            pass
        # Escape cancels an active dictation
        if self._state == STATE_LISTENING and is_key_down(VK_ESCAPE):
            self.cancel()

    def _handle_mute_hotkey(self) -> None:
        # mute hotkey = instant kill: cancel anything in flight, then toggle
        self.cancel()
        self._cancel.set()
        self.set_muted(not self._muted)

    def _handle_hotkey(self, kind: str, fg_hwnd: int = 0) -> None:
        with self._lock:
            if kind == "down":
                if self.config.mode == "toggle":
                    if self._state == STATE_LISTENING:
                        self._finish_listening()
                    elif self._state == STATE_IDLE:
                        self._start_listening("hotkey", fg_hwnd=fg_hwnd)
                elif self._state == STATE_IDLE:
                    self._start_listening("hotkey", fg_hwnd=fg_hwnd)
            elif self._state == STATE_LISTENING:
                self._finish_listening()

    # -- recording ----------------------------------------------------------
    def record(self, source: str = "button") -> None:
        """Public: start dictation from the UI (REC button / tray)."""
        with self._lock:
            if self._state == STATE_IDLE:
                self._start_listening(source)
            elif self._state == STATE_LISTENING:
                self._finish_listening()

    def stop(self) -> None:
        """Public: finish the current dictation, or cancel processing."""
        with self._lock:
            if self._state == STATE_LISTENING:
                self._finish_listening()
            else:
                self._cancel.set()

    def remember_foreign_hwnd(self, hwnd: int) -> None:
        """Remember the last non-Grogu foreground window.

        Called when the app loses focus; used to restore the target when the
        user starts dictation from Grogu's own REC button (which has focus).
        """
        if hwnd and not is_own_window(hwnd):
            log.debug("remember_foreign_hwnd: hwnd=%s title=%r", hwnd, get_window_title(hwnd))
            self._foreign_hwnd = hwnd

    def _start_listening(self, source: str = "hotkey", fg_hwnd: int = 0) -> None:
        if self._state != STATE_IDLE or self._muted:
            return
        self._source = source

        # Use the HWND captured at hotkey-fire time if available.
        # This is the window the user was in when they pressed the hotkey.
        if fg_hwnd and not is_own_window(fg_hwnd):
            self._target_hwnd = fg_hwnd
            log.info("_start_listening: using hotkey-captured fg_hwnd=%s title=%r",
                     fg_hwnd, get_window_title(fg_hwnd))
        else:
            # Fallback: capture current foreground window
            fg_hwnd = get_foreground_hwnd()
            fg_title = get_window_title(fg_hwnd)
            own_fg = is_own_window(fg_hwnd)

            log.info("_start_listening: source=%s, fg_hwnd=%s fg_title=%r is_own=%s",
                     source, fg_hwnd, fg_title, own_fg)

            if own_fg:
                # Grogu has focus — use the last known external window instead
                log.info("_start_listening: Grogu is focused, using foreign_hwnd=%s",
                         self._foreign_hwnd)
                self._target_hwnd = self._foreign_hwnd
            else:
                # External app is focused — capture it as the target
                self._target_hwnd = fg_hwnd

        log.info("_start_listening: final target_hwnd=%s title=%r",
                 self._target_hwnd, get_window_title(self._target_hwnd))

        self._cancel.clear()
        try:
            self._recorder = MicRecorder(self.config.mic_device)
            self._recorder.start()
        except Exception as e:  # noqa: BLE001
            self._recorder = None
            self.error.emit(f"Could not start the microphone: {e}")
            return
        self._set_state(STATE_LISTENING)
        if self.config.sound_cues:
            _cue_start()

    def _finish_listening(self) -> None:
        rec = self._recorder
        self._recorder = None
        if rec is None:
            return
        try:
            audio = rec.stop()
        except Exception as e:  # noqa: BLE001
            self._set_state(STATE_IDLE)
            self.error.emit(f"Could not read the microphone: {e}")
            return
        if self.config.sound_cues:
            _cue_stop()
        threading.Thread(
            target=self._process,
            args=(audio,),
            name="sotto-dictation",
            daemon=True,
        ).start()

    def cancel(self) -> None:
        """Cancel recording or abort typing."""
        if self._state == STATE_LISTENING:
            rec = self._recorder
            self._recorder = None
            if rec is not None:
                try:
                    rec.cancel()
                except Exception:  # noqa: BLE001
                    log.exception("recorder cancel failed")
            self._set_state(STATE_IDLE)
        else:
            self._cancel.set()

    def toggle(self) -> None:
        """Manual toggle (tray icon / tray menu)."""
        with self._lock:
            if self._state == STATE_LISTENING:
                self._finish_listening()
            elif self._state == STATE_IDLE:
                self._start_listening("tray")

    # -- pipeline -----------------------------------------------------------
    def _process(self, audio) -> None:
        source = self._source
        try:
            if not self._engine_ready.is_set():
                self._set_state(STATE_PREPARING)
            engine = self._ensure_engine()
            self._set_state(STATE_TRANSCRIBING)
            raw = engine.transcribe(
                audio,
                language=self.config.language,
                vad=self.config.vad_filter,
                prompt=self.dictionary.biasing_prompt(),
            )
            if not raw:
                self._set_state(STATE_IDLE)
                return
            self._set_state(STATE_CLEANING)
            final = self._cleaner.clean(raw, tone=self.config.tone)
            if not final:
                self._set_state(STATE_IDLE)
                return
            # guaranteed correction pass — biasing is only a nudge
            final, fired = self.dictionary.apply_corrections(final)
            self._set_state(STATE_TYPING)
            self._cancel.clear()

            target = self._target_hwnd
            log.info("_process: target_hwnd=%s target_title=%r",
                     target, get_window_title(target))

            if is_own_window(target):
                log.info("_process: target is own window, switching to foreign_hwnd=%s",
                         self._foreign_hwnd)
                target = self._foreign_hwnd  # Grogu had focus — use last app

            log.info("_process: final target=%s title=%r", target, get_window_title(target))

            ok = send_text(
                final,
                cancel_event=self._cancel,
                mode=self.config.insertion_mode,
                target_hwnd=target,
            )
            duration = len(audio) / 16000.0 if audio.size else 0.0
            log.info("typed %r (completed=%s, corrections=%d)",
                     final, ok, len(fired))
            if ok:
                entry = {
                    "raw": raw,
                    "text": final,
                    "corrections": fired,
                    "duration": duration,
                    "source": source,
                    "ts": time.time(),
                }
                self.last_dictation = entry
                self.dictation_done.emit(entry)
        except Exception as e:  # noqa: BLE001
            log.exception("dictation failed")
            self.error.emit(str(e))
        finally:
            self._set_state(STATE_IDLE)

    # -- state --------------------------------------------------------------
    def _set_state(self, state: str) -> None:
        if self._state == state:
            return
        self._state = state
        self.status.emit(STATE_LABELS.get(state, state))
        self.state_changed.emit(state)

    def _tick_level(self) -> None:
        if self._state == STATE_LISTENING and self._recorder is not None:
            self.mic_level.emit(self._recorder.level())

    # -- misc ---------------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    @property
    def recorder(self) -> MicRecorder | None:
        return self._recorder

    @property
    def muted(self) -> bool:
        return self._muted

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def set_muted(self, muted: bool) -> None:
        with self._lock:
            if muted == self._muted:
                return
            self._muted = muted
            if muted:
                self.cancel()
        self.muted_changed.emit(muted)
        self.status.emit("MUTED" if muted else "READY")
        log.info("muted=%s", muted)

    def toggle_muted(self) -> None:
        self.set_muted(not self._muted)

    def _register_mute_hotkey(self, spec: str | None) -> None:
        self._unregister_mute_hotkey()
        if not spec:
            return
        try:
            self._mute_listener = HotkeyListener(
                spec,
                on_down=lambda: self._mute_events.put(("down",)),
                on_error=self._on_hotkey_error,
                hotkey_id=2,
            )
            self._mute_listener.start()
        except ValueError as e:
            self.error.emit(f"Invalid mute hotkey: {e}")

    def _unregister_mute_hotkey(self) -> None:
        if self._mute_listener is not None:
            self._mute_listener.stop()
            self._mute_listener = None

    def restart_mute_hotkey(self, spec: str | None) -> None:
        self.config.mute_hotkey = spec
        self._register_mute_hotkey(spec)
        log.info("Mute hotkey set to %r", spec)

    def undo_last_correction(self) -> None:
        """Reverse the last fired correction in place (in the focused app)."""
        if not self.last_dictation:
            return
        full = self.last_dictation.get("text", "")
        found = self.dictionary.compute_undo(full)
        if not found:
            return
        heard, span_start, _write = found
        self._cancel.clear()

        def work() -> None:
            try:
                self._set_state(STATE_TYPING)
                ok = select_back(len(full) - span_start, cancel_event=self._cancel)
                if ok:
                    send_text(heard, cancel_event=self._cancel)
            except Exception as e:  # noqa: BLE001
                log.exception("undo correction failed")
                self.error.emit(str(e))
            finally:
                self._set_state(STATE_IDLE)

        threading.Thread(target=work, name="sotto-undo", daemon=True).start()
