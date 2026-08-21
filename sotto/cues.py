"""Sound cues — a lightsaber ignite on record start, a retract on stop.

Synthesized with numpy (no audio files, no deps), played through winsound.
Ignite is a rising sweep with a soft noise burst; retract is a falling sweep.
Deliberately short and low-volume so cues never drown speech or register on
the mic as words.
"""

from __future__ import annotations

import io
import logging
import struct
import wave

import numpy as np

log = logging.getLogger(__name__)

_RATE = 44100


def _wav_bytes(samples: np.ndarray) -> bytes:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _sweep(duration: float, f0: float, f1: float, punch: float = 1.0) -> bytes:
    n = int(_RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    # linear frequency sweep
    phase = 2 * np.pi * (f0 * t + (f1 - f0) * t**2 / (2 * duration))
    tone = np.sin(phase)
    # rise/fall envelope so it sounds like a blade, not a siren
    env = np.sin(np.pi * t / duration) ** 0.7
    # a whisper of noise gives it that "hum" body
    noise = np.random.default_rng(7).normal(0, 0.35, n) * env * 0.25
    return _wav_bytes((tone * env + noise) * 0.45 * punch)


_START = _sweep(0.34, 180.0, 1500.0, punch=1.0)
_STOP = _sweep(0.30, 1400.0, 120.0, punch=0.85)


def _play(data: bytes) -> None:
    try:
        import winsound
        import threading
        import tempfile
        import os
        import time

        def play_and_cleanup():
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                f.write(data)
                tmp = f.name
            try:
                winsound.PlaySound(tmp, winsound.SND_ASYNC)
                # Wait a bit for the sound to finish, then cleanup
                time.sleep(0.5)
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

        threading.Thread(target=play_and_cleanup, daemon=True).start()
    except Exception:  # noqa: BLE001 - audio is cosmetic
        log.debug("sound cue unavailable", exc_info=True)


def play_start() -> None:
    _play(_START)


def play_stop() -> None:
    _play(_STOP)
