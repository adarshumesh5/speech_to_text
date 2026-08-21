"""Microphone capture via sounddevice (PortAudio), preferring WASAPI.

Records 16 kHz mono float32 into a ring buffer while listening; ``stop()``
returns the full clip as a numpy array ready for faster-whisper.
"""

from __future__ import annotations

import logging
import threading

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000


def resample_to_16k(data: np.ndarray, source_rate: int) -> np.ndarray:
    """Linear-interpolation resample to Whisper's 16 kHz input rate."""
    if source_rate == SAMPLE_RATE or data.size == 0:
        return data
    n_out = int(round(data.size * SAMPLE_RATE / source_rate))
    x_old = np.arange(data.size, dtype=np.float64)
    x_new = np.linspace(0.0, data.size - 1, n_out)
    return np.interp(x_new, x_old, data).astype(np.float32)


def _wasapi_default_input() -> int | None:
    """Index of the WASAPI host API's default input device, if any."""
    try:
        for i, hapi in enumerate(sd.query_hostapis()):
            if "wasapi" in hapi["name"].lower():
                idx = hapi["default_input_device"]
                if idx >= 0:
                    return idx
    except Exception:
        log.exception("query_hostapis failed")
    return None


def default_input_device() -> int | None:
    """Best default input device index (WASAPI preferred, else PortAudio's)."""
    idx = _wasapi_default_input()
    if idx is not None:
        return idx
    try:
        return sd.default.device[0] if sd.default.device[0] is not None else None
    except Exception:
        return None


def list_input_devices() -> list[str]:
    """Human-readable names of every usable input device."""
    names: list[str] = []
    try:
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:
                names.append(dev["name"])
    except Exception:
        log.exception("query_devices failed")
    return names


def resolve_input_device(name: str | None) -> int | None:
    """Resolve a saved device name to an index; prefer WASAPI on collisions.

    Returns None (meaning "use default") for a missing/unknown device.
    """
    if not name:
        return default_input_device()
    try:
        devices = sd.query_devices()
    except Exception:
        log.exception("query_devices failed")
        return default_input_device()
    wasapi_names: list[int] = []
    other_names: list[int] = []
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0 and dev["name"] == name:
            hostapi = sd.query_hostapis(dev["hostapi"])["name"].lower()
            (wasapi_names if "wasapi" in hostapi else other_names).append(i)
    pool = wasapi_names or other_names
    if pool:
        return pool[0]
    log.warning("Saved mic device %r not found; using default", name)
    return default_input_device()


class MicRecorder:
    """Non-blocking microphone recorder accumulating a clip in a callback."""

    def __init__(self, device: str | None = None):
        self.device = device  # saved name from config (optional)
        self._stream: sd.InputStream | None = None
        self._frames: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._device_index: int | None = None
        self._sample_rate = SAMPLE_RATE

    def start(self) -> None:
        self._device_index = resolve_input_device(self.device)
        if self._device_index is None:
            self._device_index = sd.default.device[0]
        if self._device_index is None:
            raise RuntimeError("No microphone input device is available")
        dev = sd.query_devices(self._device_index)
        self._sample_rate = int(dev["default_samplerate"])
        self._frames = []

        def callback(indata, frames, time_info, status):
            if status:
                log.debug("stream status: %s", status)
            with self._lock:
                self._frames.append(indata.copy())

        try:
            # Open at the device's native rate (WASAPI rejects arbitrary rates)
            # and resample to 16 kHz in stop().
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="float32",
                device=self._device_index,
                callback=callback,
            )
            self._stream.start()
        except Exception:
            log.exception("failed to open input stream")
            raise

    def stop(self) -> np.ndarray:
        """Stop recording and return the clip as a 1-D float32 array."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                log.exception("error closing stream")
            self._stream = None
        with self._lock:
            if not self._frames:
                return np.zeros(0, dtype=np.float32)
            data = np.concatenate(self._frames)
            self._frames = []
        return resample_to_16k(data.ravel(), self._sample_rate)

    def cancel(self) -> None:
        """Discard the current clip without returning it."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                log.exception("error closing stream")
            self._stream = None
        with self._lock:
            self._frames = []

    def level(self) -> float:
        """Current RMS-ish level (0..1) of the most recent audio block."""
        with self._lock:
            if not self._frames:
                return 0.0
            block = self._frames[-1]
            peak = float(np.abs(block).max())
        # crude normalisation; typical speech peaks sit well below 1.0
        return min(1.0, peak * 4.0)

    def recent(self, seconds: float = 3.0) -> np.ndarray:
        """Tail of the recorded samples (device rate, mono) for display."""
        with self._lock:
            if not self._frames:
                return np.zeros(0, dtype=np.float32)
            data = np.concatenate(self._frames)
        n = int(seconds * self._sample_rate)
        return data[-n:] if data.size > n else data
