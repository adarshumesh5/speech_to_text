"""The Grogu Dictionary — teach the engine words and correct what it hears.

Two entry types, persisted together as one plain JSON file:

* **words**  — names/jargon the engine should know. Fed to faster-whisper as
  ``initial_prompt`` context before transcription (capped, so the prompt stays
  short and can't make the model drift on quiet audio). A nudge, not a promise.
* **corrections** — "when you hear X, write Y" pairs. Applied as a guaranteed
  post-transcription pass: whole-word, case-insensitive, longest match first,
  tolerant of the model gluing words together (whitespace *or* hyphens between
  the parts, or none at all).

The file is plain JSON at ``%APPDATA%/Grogu/dictionary.json`` and is safe to
edit by hand:

    {
      "words": [{"text": "Anthropic", "created": 1724000000.0}],
      "corrections": [{"heard": "cloud code", "write": "Claude Code", "created": 1724000000.0}]
    }
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from grogu.config import APP_DATA_DIR

DICTIONARY_PATH = os.path.join(APP_DATA_DIR, "dictionary.json")

# Soft cap for the biasing prompt — long context makes Whisper drift and
# invent text on quiet audio, so we keep the list short on purpose.
BIASING_MAX_WORDS = 10
BIASING_MAX_CHARS = 160

# Words so common that a correction targeting them (or a part of them) is
# likely to rewrite ordinary usage. Used only for UI warnings — never to block.
COMMON_WORDS = {
    # function words
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "for", "with",
    "on", "at", "in", "by", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "am", "do", "does", "did", "have", "has", "had", "will",
    "would", "could", "should", "shall", "can", "may", "might", "must",
    "not", "no", "yes", "so", "because", "while", "when", "where", "why",
    "how", "what", "who", "which", "this", "that", "these", "those", "there",
    "their", "they", "them", "we", "you", "your", "yours", "i", "me", "my",
    "mine", "he", "him", "his", "she", "her", "hers", "it", "its", "us",
    "our", "ours",
    # frequent content words
    "about", "after", "again", "all", "also", "any", "around", "back",
    "before", "between", "both", "come", "day", "down", "each", "even",
    "every", "first", "get", "give", "go", "going", "good", "great", "here",
    "home", "just", "know", "like", "little", "long", "look", "make", "man",
    "many", "more", "most", "much", "new", "now", "old", "one", "only",
    "other", "out", "over", "own", "people", "right", "said", "same", "say",
    "see", "should", "show", "still", "such", "take", "than", "then", "think",
    "thing", "things", "time", "two", "up", "use", "very", "want", "way",
    "well", "work", "world", "would", "year", "years",
    # work / tech vocabulary that correction entries commonly target
    "app", "api", "code", "cloud", "email", "file", "files", "meeting",
    "message", "messages", "send", "sent", "team", "call", "calls", "build",
    "ship", "launch", "test", "tests", "bug", "fix", "plan", "plans",
    "week", "month", "friday", "monday", "tuesday", "wednesday", "thursday",
    "saturday", "sunday", "morning", "afternoon", "evening", "today",
    "tomorrow", "yesterday", "now", "okay", "ok",
}


@dataclass
class WordEntry:
    text: str
    created: float = field(default_factory=time.time)


@dataclass
class CorrectionEntry:
    heard: str
    write: str
    created: float = field(default_factory=time.time)


class Dictionary:
    """Owns the word + correction lists and the plain-JSON file."""

    def __init__(self, path: str | None = None):
        self.path = path or DICTIONARY_PATH
        self.words: list[WordEntry] = []
        self.corrections: list[CorrectionEntry] = []
        self._patterns: list[tuple[CorrectionEntry, re.Pattern]] = []
        self.load()

    # -- persistence --------------------------------------------------------
    def load(self) -> None:
        self.words = []
        self.corrections = []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            self._rebuild_patterns()
            return
        for item in data.get("words", []):
            if isinstance(item, dict) and item.get("text"):
                self.words.append(WordEntry(text=str(item["text"]),
                                            created=float(item.get("created", time.time()))))
        for item in data.get("corrections", []):
            if isinstance(item, dict) and item.get("heard") and item.get("write"):
                self.corrections.append(CorrectionEntry(
                    heard=str(item["heard"]), write=str(item["write"]),
                    created=float(item.get("created", time.time()))))
        self._rebuild_patterns()

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    def to_dict(self) -> dict[str, Any]:
        """The full dictionary as a plain dict (same shape as the JSON file)."""
        return {
            "words": [asdict(w) for w in self.words],
            "corrections": [asdict(c) for c in self.corrections],
        }

    # -- import / export ----------------------------------------------------
    def export_to(self, path: str) -> None:
        """Write the dictionary to ``path`` as plain JSON (same format as the
        live file, so a backup can be restored with :meth:`import_from`)."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    def import_from(self, path: str) -> dict[str, int]:
        """Merge a dictionary JSON file into this one (no overwrites).

        Words are added when the same text isn't already present; corrections
        are added when the same heard→write pair isn't already present. Both
        comparisons are case-insensitive. Returns counts added as
        {"words": n, "corrections": m}.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        added_words = 0
        for item in data.get("words", []):
            if not isinstance(item, dict) or not item.get("text"):
                continue
            text = str(item["text"]).strip()
            if not text:
                continue
            if any(w.text.lower() == text.lower() for w in self.words):
                continue
            self.words.append(WordEntry(text=text,
                                        created=float(item.get("created", time.time()))))
            added_words += 1
        added_corr = 0
        for item in data.get("corrections", []):
            if not isinstance(item, dict) or not item.get("heard") or not item.get("write"):
                continue
            heard, write = str(item["heard"]).strip(), str(item["write"]).strip()
            if not heard or not write:
                continue
            if any(c.heard.lower() == heard.lower() and c.write.lower() == write.lower()
                   for c in self.corrections):
                continue
            self.corrections.append(CorrectionEntry(
                heard=heard, write=write,
                created=float(item.get("created", time.time()))))
            added_corr += 1
        self._rebuild_patterns()
        if added_words or added_corr:
            self.save()
        return {"words": added_words, "corrections": added_corr}

    # -- CRUD ---------------------------------------------------------------
    def add_word(self, text: str) -> WordEntry:
        text = text.strip()
        if not text:
            raise ValueError("Word cannot be empty")
        entry = WordEntry(text=text)
        self.words.append(entry)
        self.save()
        return entry

    def update_word(self, index: int, text: str) -> None:
        text = text.strip()
        if not text:
            raise ValueError("Word cannot be empty")
        self.words[index].text = text
        self.save()

    def delete_word(self, index: int) -> None:
        del self.words[index]
        self.save()

    def add_correction(self, heard: str, write: str) -> CorrectionEntry:
        heard, write = heard.strip(), write.strip()
        if not heard or not write:
            raise ValueError("Both 'heard' and 'write' are required")
        entry = CorrectionEntry(heard=heard, write=write)
        self.corrections.append(entry)
        self._rebuild_patterns()
        self.save()
        return entry

    def update_correction(self, index: int, heard: str, write: str) -> None:
        heard, write = heard.strip(), write.strip()
        if not heard or not write:
            raise ValueError("Both 'heard' and 'write' are required")
        self.corrections[index].heard = heard
        self.corrections[index].write = write
        self._rebuild_patterns()
        self.save()

    def delete_correction(self, index: int) -> None:
        del self.corrections[index]
        self._rebuild_patterns()
        self.save()

    # -- search -------------------------------------------------------------
    def search_words(self, query: str) -> list[WordEntry]:
        q = query.strip().lower()
        if not q:
            return list(self.words)
        return [w for w in self.words if q in w.text.lower()]

    def search_corrections(self, query: str) -> list[CorrectionEntry]:
        q = query.strip().lower()
        if not q:
            return list(self.corrections)
        return [c for c in self.corrections
                if q in c.heard.lower() or q in c.write.lower()]

    # -- engine biasing -----------------------------------------------------
    def biasing_prompt(self) -> str | None:
        """Short comma-joined list of words to bias the engine toward.

        Returns None when there is nothing to pass. Capped so the prompt stays
        tiny — long context makes Whisper drift on quiet audio.
        """
        seen: set[str] = set()
        chosen: list[str] = []
        for w in self.words:
            key = w.text.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            chosen.append(w.text.strip())
            if len(chosen) >= BIASING_MAX_WORDS:
                break
        if not chosen:
            return None
        prompt = ", ".join(chosen)
        if len(prompt) > BIASING_MAX_CHARS:
            prompt = prompt[: BIASING_MAX_CHARS].rstrip(", ")
        return prompt

    # -- correction pass ----------------------------------------------------
    def _rebuild_patterns(self) -> None:
        self._patterns = []
        for c in self.corrections:
            parts = [re.escape(p) for p in c.heard.split()]
            if not parts:
                continue
            # whitespace *or* hyphens between parts — catches "CloudCode",
            # "Cloud-Code", "cloud code"; never matches inside other words.
            pattern = re.compile(r"\b" + r"[\s\-]*".join(parts) + r"\b",
                                 re.IGNORECASE)
            self._patterns.append((c, pattern))
        # longest heard-phrase first so "Claude Code" beats "Code" etc.
        self._patterns.sort(key=lambda pc: len(pc[0].heard), reverse=True)

    def apply_corrections(self, text: str) -> tuple[str, list[dict[str, Any]]]:
        """Rewrite ``text``; returns (corrected, fired).

        ``fired`` is a list of {"heard", "write", "count"} for every
        correction that matched, in application order.
        """
        if not text or not self._patterns:
            return text, []
        fired: list[dict[str, Any]] = []
        result = text
        for entry, pattern in self._patterns:
            result, count = pattern.subn(entry.write, result)
            if count:
                fired.append({"heard": entry.heard, "write": entry.write,
                              "count": count})
        return result, fired

    # -- undo support -------------------------------------------------------
    def compute_undo(self, text: str) -> tuple[str, int, str] | None:
        """Find the correction whose 'write' appears last in ``text``.

        Returns (heard, span_start, write) so the caller can select the span
        backwards from the cursor and re-type the heard text — reversing one
        correction in place. None when nothing to undo.
        """
        if not text or not self.corrections:
            return None
        best: tuple[str, int, str] | None = None
        for c in self.corrections:
            idx = text.rfind(c.write)
            if idx >= 0 and (best is None or idx > best[1]):
                best = (c.heard, idx, c.write)
        return best

    # -- warnings -----------------------------------------------------------
    def check_warning(self, heard: str) -> list[str]:
        """Amber warnings when an entry looks like it would hit common usage.

        Returns a list of human-readable warnings (empty = safe-looking).
        """
        heard = heard.strip()
        if not heard:
            return []
        warnings: list[str] = []
        parts = [p.strip(" .,;:") for p in re.split(r"[\s\-]+", heard.lower())
                 if p.strip(" .,;:")]
        common_parts = [p for p in parts if p in COMMON_WORDS]
        if len(parts) == 1 and common_parts:
            warnings.append(
                f"'{heard}' is a common English word — this correction will "
                "rewrite ordinary usage everywhere it appears. Consider a "
                "longer phrase."
            )
        elif common_parts:
            warnings.append(
                "Part(s) " + ", ".join(f"'{p}'" for p in common_parts) +
                " are common words. The pattern requires the full phrase, so "
                "standalone usage stays untouched — verify that's what you want."
            )
        # single-word heard that is a common PREFIX of another common word
        # (e.g. 'cloud' inside 'cloudflare') is safe because of \b boundaries,
        # but the user may be surprised — mention it for single tokens.
        if len(parts) == 1 and not common_parts:
            prefix_hits = [w for w in COMMON_WORDS
                           if w != parts[0] and w.startswith(parts[0])]
            if prefix_hits:
                warnings.append(
                    f"'{heard}' starts common words like "
                    + ", ".join(f"'{w}'" for w in prefix_hits[:3])
                    + " — whole-word matching keeps those safe."
                )
        return warnings
