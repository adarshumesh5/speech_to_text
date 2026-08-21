"""Configuration handling: JSON in %APPDATA%/Grogu/config.json.

The config is a dataclass with defaults; loading merges on top of defaults so
new keys appear automatically after upgrades.

On first run after the rename from Sotto, ``migrate_from_sotto`` copies the
config, dictionary and history into the Grogu data folder.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass, field
from typing import Any

log = logging.getLogger(__name__)

_APPDATA = os.environ.get("APPDATA") or os.path.expanduser("~")
APP_DATA_DIR = os.path.join(_APPDATA, "Grogu")
CONFIG_PATH = os.path.join(APP_DATA_DIR, "config.json")

# previous app data folder — migrated from on first run of Grogu
LEGACY_DATA_DIR = os.path.join(_APPDATA, "Sotto")

MODELS = [
    "tiny.en",
    "base.en",
    "small.en",
    "medium.en",
    "large-v3-turbo",
    "distil-medium.en",
]

LANGUAGES = {
    "auto": "Auto-detect",
    "en": "English",
    "de": "Deutsch",
    "es": "Español",
    "fr": "Français",
    "it": "Italiano",
    "pt": "Português",
    "nl": "Nederlands",
    "ja": "日本語",
    "ko": "한국어",
    "zh": "中文",
}

CLEANERS = {
    "rules": "Smart rules (offline, no model)",
    "passthrough": "Raw transcript (no cleanup)",
}

INSERTION_MODES = {
    "clipboard": "Clipboard paste (most reliable)",
    "keystrokes": "Keystrokes (Ctrl+Z undoable, but less reliable)",
    "smart": "Smart (try keystrokes, fallback to clipboard)",
}


@dataclass
class Config:
    hotkey: str = "Ctrl+Shift+Space"
    mute_hotkey: str | None = None  # optional global kill/mute combo
    mode: str = "hold"  # "hold" | "toggle"
    model: str = "small.en"
    language: str = "auto"
    cleaner: str = "rules"
    tone: str = "casual"
    mic_device: str | None = None  # device name, or None for default
    device: str = "auto"  # "auto" | "cuda" | "cpu"
    compute_type: str = "auto"  # "auto" | "float16" | "int8"
    vad_filter: bool = True
    sound_cues: bool = True
    notify_on_dictation: bool = True
    start_with_windows: bool = False
    start_minimized: bool = False
    insertion_mode: str = "clipboard"  # "clipboard" | "keystrokes" | "smart"
    log_level: str = "INFO"
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, path: str | None = None) -> "Config":
        path = path or CONFIG_PATH
        cfg = cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return cfg
        known = {f for f in cls.__dataclass_fields__ if not f.startswith("_")}
        for key, value in data.items():
            if key in known:
                setattr(cfg, key, value)
            else:
                cfg._extra[key] = value
        return cfg

    def save(self, path: str | None = None) -> None:
        path = path or CONFIG_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = asdict(self)
        data.pop("_extra", None)
        data.update(self._extra)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def resolve_device(self) -> str:
        """Resolve 'auto' to an explicit faster-whisper device string."""
        if self.device != "auto":
            return self.device
        return "cuda"

    def resolve_compute_type(self, device: str) -> str:
        if self.compute_type != "auto":
            return self.compute_type
        return "float16" if device == "cuda" else "int8"


def migrate_from_sotto() -> None:
    """Copy the old Sotto data folder into Grogu on first run.

    Runs once: only when the Grogu folder does not exist yet. The Sotto folder
    is left untouched as a backup. Never raises.
    """
    if not os.path.isdir(LEGACY_DATA_DIR):
        return
    if os.path.exists(APP_DATA_DIR):
        return
    try:
        os.makedirs(APP_DATA_DIR, exist_ok=True)
        for name in ("config.json", "dictionary.json", "history.jsonl"):
            src = os.path.join(LEGACY_DATA_DIR, name)
            dst = os.path.join(APP_DATA_DIR, name)
            if os.path.isfile(src):
                shutil.copy2(src, dst)
                log.info("migrated %s → %s", src, dst)
        log.info("migrated data from %s to %s", LEGACY_DATA_DIR, APP_DATA_DIR)
    except OSError as e:  # noqa: BLE001
        log.warning("data migration failed: %s", e)
