"""Model manager — inspect, download, and remove Whisper models.

faster-whisper pulls models from Hugging Face as ``Systran/faster-whisper-*``
repos (``distil-whisper/*`` for the distilled ones) into the shared HF cache
under ``~/.cache/huggingface``. This module wraps that so the UI can show
sizes, download progress, cancel, and retry without touching the engine.

Everything here is UI-free and testable; the dialog lives in
``grogu.ui.model_manager``.
"""

from __future__ import annotations

import os
import threading
from typing import Callable

from grogu.config import MODELS

# Approximate download sizes (MB) used when the Hugging Face API is
# unreachable — good enough for a pre-download estimate in the UI.
APPROX_SIZES_MB: dict[str, int] = {
    "tiny.en": 75,
    "base.en": 145,
    "small.en": 466,
    "medium.en": 1500,
    "large-v3-turbo": 1600,
    "distil-medium.en": 1400,
}


def model_repo(model: str) -> str:
    """HF repo id for a config model name."""
    if model.startswith("distil-"):
        return f"distil-whisper/{model}"
    return f"Systran/faster-whisper-{model}"


def _hf_cache_dir() -> str:
    try:
        from huggingface_hub.constants import HF_HUB_CACHE

        return HF_HUB_CACHE
    except Exception:  # noqa: BLE001
        return os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")


def model_cache_dir(model: str) -> str:
    """Local HF cache dir for a model repo (``models--Org--Name``)."""
    repo = model_repo(model)
    org, name = repo.split("/")
    return os.path.join(_hf_cache_dir(), f"models--{org}--{name}")


def fetch_repo_size(model: str) -> int | None:
    """Total download size in bytes from the HF API (None on failure)."""
    try:
        from huggingface_hub import HfApi

        info = HfApi().model_info(model_repo(model), files_metadata=True)
        sizes = [s.size for s in (info.siblings or []) if s.size]
        if sizes:
            return int(sum(sizes))
    except Exception:  # noqa: BLE001 - offline / transient errors
        pass
    return None


def model_size_bytes(model: str) -> int:
    """Best-known size: live API first, approximate table as fallback."""
    live = fetch_repo_size(model)
    if live:
        return live
    mb = APPROX_SIZES_MB.get(model, 500)
    return mb * 1024 * 1024


def model_downloaded(model: str) -> bool:
    """True when the model's files exist locally and cover its size.

    Counts every file under the model's cache dir (snapshots on Windows,
    blobs elsewhere) and compares to the known size.
    """
    base = model_cache_dir(model)
    if not os.path.isdir(base):
        return False
    total = 0
    for root, _dirs, files in os.walk(base):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    expected = model_size_bytes(model)
    return expected > 0 and total >= expected * 0.95


def download_model(
    model: str,
    progress: Callable[[int, int], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> bool:
    """Download a model into the HF cache; returns True when complete.

    ``progress(done_bytes, total_bytes)`` is called after each file.
    ``cancel_event`` (when set) stops between files; already-cached files
    are skipped by ``hf_hub_download`` so retry resumes cleanly.
    """
    repo = model_repo(model)
    try:
        from huggingface_hub import HfApi, hf_hub_download
    except Exception:  # noqa: BLE001
        return False
    try:
        info = HfApi().model_info(repo, files_metadata=True)
        files = [(s.rfilename, s.size or 0) for s in (info.siblings or [])]
    except Exception:  # noqa: BLE001
        return False
    if not files:
        return False
    total = sum(size for _, size in files) or model_size_bytes(model)
    done = 0
    for filename, _size in files:
        if cancel_event is not None and cancel_event.is_set():
            return False
        try:
            hf_hub_download(repo_id=repo, filename=filename)
        except Exception:  # noqa: BLE001
            return False
        done += _size
        if progress:
            progress(min(done, total), total)
    return True


def delete_model(model: str) -> None:
    """Remove a model's cache dir so it can be re-downloaded."""
    base = model_cache_dir(model)
    if os.path.isdir(base):
        import shutil

        shutil.rmtree(base, ignore_errors=True)
