"""Speech-to-text via faster-whisper (CTranslate2).

Loads CUDA/float16 by default and transparently falls back to CPU/int8 so the
app still works on machines without a usable GPU. The model is downloaded from
Hugging Face on first use (cached under %USERPROFILE%\\.cache\\huggingface).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

log = logging.getLogger(__name__)


def _ensure_cuda_dlls() -> None:
    """Make NVIDIA DLLs from pip ``nvidia-*`` wheels loadable by ctranslate2.

    On Windows the ctranslate2 wheel bundles cuDNN but not cuBLAS; the
    ``nvidia-cublas-cu12`` pip package supplies ``cublas64_12.dll``. We add
    its bin dir to the process DLL search path so ``device="cuda"`` works
    with no manual CUDA Toolkit install.
    """
    if os.name != "nt":
        return
    bins: list[str] = []
    # frozen (PyInstaller onedir): DLLs shipped next to the exe
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        bins.append(os.path.join(exe_dir, "nvidia", "cublas", "bin"))
    try:
        import importlib.util

        spec = importlib.util.find_spec("nvidia.cublas")
        if spec and spec.submodule_search_locations:
            base = list(spec.submodule_search_locations)[0]
            bins.append(os.path.join(base, "bin"))
    except Exception:  # noqa: BLE001
        pass
    if not bins:
        # fallback: walk every site-packages/nvidia/*/bin
        import site

        for sp in list(site.getsitepackages()) + [site.getusersitepackages()]:
            nvidia = os.path.join(sp, "nvidia")
            if not os.path.isdir(nvidia):
                continue
            for root, _dirs, _files in os.walk(nvidia):
                if os.path.basename(root) == "bin":
                    bins.append(root)
    for d in bins:
        if not os.path.isdir(d):
            continue
        if d not in os.environ.get("PATH", ""):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        try:
            os.add_dll_directory(d)
        except (OSError, ValueError):
            pass


class SttEngine:
    """Thin wrapper around a faster-whisper model."""

    def __init__(self, model: str, device: str = "cpu", compute_type: str = "int8"):
        from faster_whisper import WhisperModel

        _ensure_cuda_dlls()
        log.info("Loading Whisper model %r on %s (%s)…", model, device, compute_type)
        self._model: WhisperModel = WhisperModel(
            model, device=device, compute_type=compute_type
        )
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        log.info("Model %r ready (%s/%s)", model, device, compute_type)

    @classmethod
    def create(cls, model: str, device: str = "auto", compute_type: str = "auto") -> "SttEngine":
        """Create an engine, trying CUDA first and falling back to CPU.

        ``device``/``compute_type`` may be "auto" to pick sensible defaults.
        """
        if device == "auto":
            attempts = ["cuda", "cpu"]
        else:
            attempts = [device]
        last_error: Exception | None = None
        for dev in attempts:
            try:
                ct = compute_type
                if ct == "auto":
                    ct = "float16" if dev == "cuda" else "int8"
                return cls(model, device=dev, compute_type=ct)
            except Exception as e:  # noqa: BLE001 - deliberate fallback chain
                log.warning("Whisper on %s failed: %s", dev, e)
                last_error = e
        raise RuntimeError(f"Could not load Whisper model {model!r}") from last_error

    def transcribe(self, audio: np.ndarray, language: str | None = None,
                   vad: bool = True, prompt: str | None = None) -> str:
        """Transcribe a 1-D float32 array (any sample rate) to text.

        ``prompt`` is passed as ``initial_prompt`` — a short context nudge
        (the dictionary's biasing words) to steer the model's vocabulary.
        """
        if audio.size == 0:
            return ""
        segments, _info = self._model.transcribe(
            audio,
            language=None if language in (None, "", "auto") else language,
            vad_filter=vad,
            beam_size=5,
            condition_on_previous_text=False,
            initial_prompt=prompt,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
