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

Also provides plain-text / Markdown / CSV export for the history tab.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import os
import time
from typing import Any

from grogu.config import APP_DATA_DIR

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

    # -- export -------------------------------------------------------------
    def export(self, entries: list[dict[str, Any]], fmt: str = "txt",
               path: str | None = None) -> str:
        """Serialize ``entries`` to text/markdown/csv.

        Returns the formatted string; writes it to ``path`` when given.
        ``fmt`` is one of "txt", "md", "csv".
        """
        fmt = fmt.lower()
        if fmt == "csv":
            out = self._to_csv(entries)
        elif fmt == "md":
            out = self._to_markdown(entries)
        else:
            out = self._to_text(entries)
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(out)
        return out

    @staticmethod
    def _fmt_ts(ts: float) -> str:
        try:
            return _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, ValueError):
            return ""

    @staticmethod
    def _corrections_str(entry: dict[str, Any]) -> str:
        fired = entry.get("corrections") or []
        return "; ".join(
            f"{c.get('heard', '')} → {c.get('write', '')}"
            for c in fired
        )

    def _to_text(self, entries: list[dict[str, Any]]) -> str:
        blocks: list[str] = []
        for e in entries:
            lines = [
                f"{self._fmt_ts(e.get('ts', 0))}  [{e.get('source', 'hotkey')}]",
                e.get("text", ""),
            ]
            corr = self._corrections_str(e)
            if corr:
                lines.append(f"corrections: {corr}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks) + ("\n" if blocks else "")

    def _to_markdown(self, entries: list[dict[str, Any]]) -> str:
        blocks: list[str] = []
        for e in entries:
            lines = [
                f"## {self._fmt_ts(e.get('ts', 0))} — {e.get('source', 'hotkey')}",
                "",
                e.get("text", ""),
            ]
            corr = self._corrections_str(e)
            if corr:
                lines += ["", f"*Corrections applied: {corr}*"]
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks) + ("\n" if blocks else "")

    def _to_csv(self, entries: list[dict[str, Any]]) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(["timestamp", "source", "text", "corrections"])
        for e in entries:
            writer.writerow([
                self._fmt_ts(e.get("ts", 0)),
                e.get("source", "hotkey"),
                e.get("text", ""),
                self._corrections_str(e),
            ])
        return buf.getvalue()
