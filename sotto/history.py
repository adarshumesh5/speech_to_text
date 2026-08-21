"""Transcription history — append-only JSONL under %APPDATA%/Grogu.

Each line is one dictation:

    {
      "ts": 1724000000.0,
      "raw": "um so like we should ship it",
      "text": "We should ship it.",
      "corrections": [{"heard": "cloud code", "write": "Claude Code", "count": 1}],
      "source": "hotkey",
      "duration": 3.2
    }
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from sotto.config import APP_DATA_DIR

HISTORY_PATH = os.path.join(APP_DATA_DIR, "history.jsonl")

HISTORY_LIMIT = 1000  # lines kept; older lines pruned on append


class HistoryStore:
    def __init__(self, path: str | None = None, limit: int = HISTORY_LIMIT):
        self.path = path or HISTORY_PATH
        self.limit = limit

    def append(self, entry: dict[str, Any]) -> None:
        entry = dict(entry)
        entry.setdefault("ts", time.time())
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._prune()

    def _prune(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return
        if len(lines) <= self.limit:
            return
        with open(self.path, "w", encoding="utf-8") as f:
            f.writelines(lines[-self.limit:])

    def load(self, newest_first: bool = True) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except ValueError:
                        continue
        except OSError:
            return []
        if newest_first:
            entries.reverse()
        return entries

    def search(self, query: str, newest_first: bool = True) -> list[dict[str, Any]]:
        q = query.strip().lower()
        if not q:
            return self.load(newest_first=newest_first)
        return [
            e for e in self.load(newest_first=newest_first)
            if q in e.get("text", "").lower() or q in e.get("raw", "").lower()
        ]

    def clear(self) -> None:
        try:
            os.remove(self.path)
        except OSError:
            pass
