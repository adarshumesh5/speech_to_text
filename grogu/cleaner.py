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
* Spoken punctuation: Whisper writes out "comma", "question mark", etc. as
  words; the cleaner converts the unambiguous ones (comma, question mark,
  exclamation, new line) and only converts the ambiguous ones (period,
  colon, semicolon) when they clearly act as punctuation — at the end of
  the dictation or directly before another punctuation command — so real
  words like "colon cancer" or "that period of history" are never mangled.
"""

from __future__ import annotations

import re

# Spoken punctuation words → the character they stand for.
# ``_AMBIGUOUS`` is applied conditionally (see module docstring); everything
# else is converted unconditionally (word-boundary matched, case-insensitive).
SPOKEN_PUNCTUATION: dict[str, str] = {
    "comma": ",",
    "question mark": "?",
    "exclamation mark": "!",
    "exclamation point": "!",
    "new line": "\n",
    "new paragraph": "\n\n",
    "ellipsis": "…",
    "dot dot dot": "…",
    # ambiguous — only converted in a clearly-punctuation position
    "period": ".",
    "full stop": ".",
    "colon": ":",
    "semicolon": ";",
}

_AMBIGUOUS = {"period", "full stop", "colon", "semicolon"}

# Longest phrase first so "question mark" wins over a hypothetical "mark".
# Ambiguous words (period/colon/semicolon) are NOT here — they are handled
# by _GUARDED_PATTERN below so real words like "colon cancer" survive.
_UNCONDITIONAL = {w for w in SPOKEN_PUNCTUATION if w not in _AMBIGUOUS}
_PUNCT_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(re.escape(w) for w in sorted(_UNCONDITIONAL, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)

# Ambiguous words only become punctuation at the end of the dictation or when
# directly followed by another punctuation command ("define fn colon new line").
_PUNCT_AFTER = (
    r"comma|question mark|exclamation mark|exclamation point|new line|"
    r"new paragraph|ellipsis|dot dot dot|period|full stop|colon|semicolon"
)
_GUARDED_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in sorted(_AMBIGUOUS, key=len, reverse=True))
    + r")\b(?=\s*(?:$|" + _PUNCT_AFTER + r"))",
    re.IGNORECASE,
)

# Collapse whitespace around punctuation produced above:
# "hello , world" → "hello, world", "are you free ?" → "are you free?"
_PUNCT_WS = re.compile(r"\s+([,.;:!?…])(?=\s|$)")

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


def _replace_punct(m: re.Match) -> str:
    """Map a matched spoken-punctuation word to its character."""
    return SPOKEN_PUNCTUATION[m.group(0).lower()]


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

        # 0. spoken punctuation → real characters.
        # Guarded words first (period/colon/semicolon check what follows),
        # then the unconditional ones (comma, new line, …) so "colon new line"
        # still sees "new line" as the following punctuation command.
        text = _GUARDED_PATTERN.sub(_replace_punct, text)
        text = _PUNCT_PATTERN.sub(_replace_punct, text)
        text = _PUNCT_WS.sub(r"\1 ", text).strip()

        # 1. hard fillers anywhere
        text = _HARD_PATTERN.sub("", text)

        # 2. per-paragraph polish — "new line" / "new paragraph" produced
        #    literal newlines above, so treat each line independently.
        paragraphs: list[str] = []
        for paragraph in text.split("\n"):
            raw = paragraph
            paragraph = paragraph.strip()
            if not paragraph:
                # a literal blank line from "new paragraph" — keep it
                if not raw.strip():
                    paragraphs.append("")
                continue
            sentences = _SENT_SPLIT.split(paragraph)
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
                # capitalise + terminal punctuation (not after "::" or ";")
                sent = sent[0].upper() + sent[1:]
                if sent[-1] not in ".!?…:;":
                    sent += "."
                out.append(sent)
            if out:
                paragraphs.append(" ".join(out))

        return "\n".join(paragraphs)


def build_cleaner(name: str = "rules") -> TextCleaner:
    if name == "passthrough":
        return PassthroughCleaner()
    return RulesCleaner()
