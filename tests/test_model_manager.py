"""Tests for grogu.model_manager (UI-free core)."""

import os

import grogu.model_manager as mm


def test_model_repo_mapping():
    assert mm.model_repo("small.en") == "Systran/faster-whisper-small.en"
    assert mm.model_repo("distil-medium.en") == "distil-whisper/distil-medium.en"
    assert mm.model_repo("large-v3-turbo") == "Systran/faster-whisper-large-v3-turbo"


def test_cache_dir_naming():
    d = mm.model_cache_dir("small.en")
    assert "models--Systran--faster-whisper-small.en" in d
    d2 = mm.model_cache_dir("distil-medium.en")
    assert "models--distil-whisper--distil-medium.en" in d2


def test_approx_sizes_present_for_all_models():
    from grogu.config import MODELS

    for m in MODELS:
        assert mm.APPROX_SIZES_MB.get(m), f"missing approx size for {m}"


def test_model_size_bytes_positive():
    for m in ("tiny.en", "small.en", "large-v3-turbo"):
        assert mm.model_size_bytes(m) > 0


def test_model_downloaded_false_for_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(mm, "_hf_cache_dir", lambda: str(tmp_path))
    assert mm.model_downloaded("small.en") is False


def test_model_downloaded_detects_cache_files(tmp_path, monkeypatch):
    monkeypatch.setattr(mm, "_hf_cache_dir", lambda: str(tmp_path))
    # fake a downloaded model: create a snapshot file big enough
    base = mm.model_cache_dir("tiny.en")
    snap = os.path.join(base, "snapshots", "abc123")
    os.makedirs(snap)
    with open(os.path.join(snap, "model.bin"), "wb") as f:
        f.write(b"\0" * (mm.APPROX_SIZES_MB["tiny.en"] * 1024 * 1024))
    monkeypatch.setattr(mm, "model_size_bytes",
                        lambda m: mm.APPROX_SIZES_MB["tiny.en"] * 1024 * 1024)
    assert mm.model_downloaded("tiny.en") is True


def test_delete_model_removes_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(mm, "_hf_cache_dir", lambda: str(tmp_path))
    base = mm.model_cache_dir("tiny.en")
    os.makedirs(os.path.join(base, "snapshots"))
    assert os.path.isdir(base)
    mm.delete_model("tiny.en")
    assert not os.path.isdir(base)
