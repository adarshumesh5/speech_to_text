"""Text cleanup: turn raw Whisper output into something that reads written.

``TextCleaner`` is the pluggable interface (a cloud-LLM cleaner can be added
later without touching the rest of the pipeline). The default
``RulesCleaner`` is fully offline and model-free: it strips filler words,
collapses stutters/repeats, normalises whitespace, capitalises sentences and
adds terminal punctuation.

Design notes
------------
* Filler words are split into two buckets:
  * HARD_FILLERS — never meaningful in dictation ("um", "uh") → removed
    anywhere.
  * SOFT_FILLERS — can be meaningful mid-sentence ("like", "so", "just") →
    only stripped at the start of a sentence.
* Multi-word phrases ("you know", "i mean") are matched as whole phrases.
* Corrections like "at 5... actually 6pm" need an LLM; out of scope here.
"""

from __future__ import annotations

import re

HARD_FILLERS = [
    "um", "umm", "ummm", "uhm", "uh", "uhh", "er", "erm", "hmm", "hm",
    "mm", "mhm", "uh-huh", "uh huh", "ah",
]

SOFT_FILLERS = [
    "you know", "i mean", "sort of", "kind of", "like", "actually",
    "basically", "literally", "so", "well", "just", "okay", "ok", "oh",
    "anyway", "anyways",
]

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WS = re.compile(r"\s+")
_REPEAT = re.compile(r"\b(\w+)(\s+\1)+\b", re.IGNORECASE)
_LEADING_PUNCT = re.compile(r"^[\s,;:—–-]+")


def _filler_pattern(fillers: list[str]) -> re.Pattern:
    ordered = sorted(fillers, key=len, reverse=True)
    return re.compile(
        r"\b(?:" + "|".join(re.escape(f) for f in ordered) + r")\b",
        re.IGNORECASE,
    )


_HARD_PATTERN = _filler_pattern(HARD_FILLERS)

# Soft fillers are only removed at the START of a sentence (they can be
# meaningful mid-sentence: "I like pizza", "we are so ready").
_SOFT_START = re.compile(
    r"^\s*(?:"
    + "|".join(re.escape(f) for f in sorted(SOFT_FILLERS, key=len, reverse=True))
    + r")(?=[\s,;:—–-]|$)",
    re.IGNORECASE,
)


class TextCleaner:
    """Interface for dictation cleanup backends."""

    name = "base"

    def clean(self, text: str, tone: str | None = None) -> str:
        raise NotImplementedError


class PassthroughCleaner(TextCleaner):
    """Returns the raw transcript unchanged."""

    name = "passthrough"

    def clean(self, text: str, tone: str | None = None) -> str:
        return text.strip()


class RulesCleaner(TextCleaner):
    """Offline, model-free cleanup: fillers, repeats, punctuation."""

    name = "rules"

    def clean(self, text: str, tone: str | None = None) -> str:
        text = text.strip()
        if not text:
            return ""

        # 1. hard fillers anywhere
        text = _HARD_PATTERN.sub("", text)

        # 2. per-sentence polish
        sentences = _SENT_SPLIT.split(text)
        out: list[str] = []
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            # strip leading soft fillers repeatedly ("so like actually …")
            prev = None
            while sent != prev:
                prev = sent
                sent = _SOFT_START.sub("", sent)
                sent = _LEADING_PUNCT.sub("", sent).strip()
            # collapse repeats: "the the" → "the", "no no no" → "no"
            sent = _REPEAT.sub(lambda m: m.group(1), sent)
            sent = _WS.sub(" ", sent).strip()
            if not sent:
                continue
            # capitalise + terminal punctuation
            sent = sent[0].upper() + sent[1:]
            if sent[-1] not in ".!?…":
                sent += "."
            out.append(sent)

        return " ".join(out)


def build_cleaner(name: str = "rules") -> TextCleaner:
    if name == "passthrough":
        return PassthroughCleaner()
    return RulesCleaner()
