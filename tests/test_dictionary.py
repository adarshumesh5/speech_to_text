"""Tests for grogu.dictionary."""

import pytest

from grogu.dictionary import (
    BIASING_MAX_WORDS,
    Dictionary,
    WordEntry,
)


def make_dict(tmp_path, words=(), corrections=()):
    d = Dictionary(str(tmp_path / "dictionary.json"))
    for w in words:
        d.add_word(w)
    for heard, write in corrections:
        d.add_correction(heard, write)
    return d


# --- corrections: spaced ---------------------------------------------------

def test_basic_correction(tmp_path):
    d = make_dict(tmp_path, corrections=[("cloud code", "Claude Code")])
    out, fired = d.apply_corrections("I use cloud code daily.")
    assert out == "I use Claude Code daily."
    assert fired == [{"heard": "cloud code", "write": "Claude Code", "count": 1}]


def test_identical_heard_write_catches_glued(tmp_path):
    # heard == write is allowed and still catches glued forms of the phrase
    d = make_dict(tmp_path, corrections=[("Claude Code", "Claude Code")])
    out, fired = d.apply_corrections("try ClaudeCode now")
    assert out == "try Claude Code now"
    assert fired[0]["count"] == 1


def test_glued_forms(tmp_path):
    # the user's example: hear "cloud code" → write "Claude Code", and it
    # must catch every glued/hyphenated/cased variant
    d = make_dict(tmp_path, corrections=[("cloud code", "Claude Code")])
    for glued in ("CloudCode", "Cloud-Code", "cloud code", "CLOUD CODE",
                  "cloud-code"):
        out, fired = d.apply_corrections(f"try {glued} now")
        assert out == "try Claude Code now", glued
        assert fired[0]["count"] == 1


def test_never_touches_real_words(tmp_path):
    d = make_dict(tmp_path, corrections=[("Claude Code", "Claude Code")])
    out, fired = d.apply_corrections("Cloudflare and the cloud both matter")
    assert out == "Cloudflare and the cloud both matter"
    assert fired == []


def test_single_word_whole_word(tmp_path):
    d = make_dict(tmp_path, corrections=[("supabase", "Supabase")])
    out, fired = d.apply_corrections("we use Supabase and supabase")
    assert out == "we use Supabase and Supabase"
    assert fired[0]["count"] == 2


def test_word_inside_larger_word_safe(tmp_path):
    d = make_dict(tmp_path, corrections=[("app", "App")])
    out, fired = d.apply_corrections("my apple app is nice")
    assert out == "my apple App is nice"  # 'apple' untouched


def test_case_insensitive_heard(tmp_path):
    d = make_dict(tmp_path, corrections=[("CLOUD CODE", "Claude Code")])
    out, _ = d.apply_corrections("cloud code rocks")
    assert out == "Claude Code rocks"


def test_longest_match_first(tmp_path):
    d = make_dict(tmp_path, corrections=[("code", "Code"),
                                         ("cloud code", "Claude Code")])
    out, fired = d.apply_corrections("cloud code is code")
    # longest ("cloud code") applied first; the remaining standalone 'code'
    assert out == "Claude Code is Code"


def test_empty_text(tmp_path):
    d = make_dict(tmp_path, corrections=[("a", "b")])
    assert d.apply_corrections("") == ("", [])


# --- biasing prompt --------------------------------------------------------

def test_biasing_prompt(tmp_path):
    d = make_dict(tmp_path, words=["Anthropic", "Vercel", "Supabase"])
    assert d.biasing_prompt() == "Anthropic, Vercel, Supabase"


def test_biasing_prompt_none_when_empty(tmp_path):
    d = make_dict(tmp_path)
    assert d.biasing_prompt() is None


def test_biasing_prompt_dedupes(tmp_path):
    d = make_dict(tmp_path, words=["Anthropic", "anthropic", "Claude"])
    assert d.biasing_prompt() == "Anthropic, Claude"


def test_biasing_prompt_capped(tmp_path):
    words = [f"Word{i}" for i in range(50)]
    d = make_dict(tmp_path, words=words)
    prompt = d.biasing_prompt()
    assert prompt is not None
    assert len(prompt.split(", ")) <= BIASING_MAX_WORDS


# --- warnings --------------------------------------------------------------

def test_warning_common_word(tmp_path):
    d = make_dict(tmp_path)
    warnings = d.check_warning("cloud")
    assert any("common" in w.lower() for w in warnings)


def test_warning_multipart_common(tmp_path):
    d = make_dict(tmp_path)
    warnings = d.check_warning("cloud code")
    assert warnings  # mentions the common parts


def test_no_warning_for_specific_name(tmp_path):
    d = make_dict(tmp_path)
    assert d.check_warning("Anthropic") == []


# --- persistence -----------------------------------------------------------

def test_round_trip(tmp_path):
    d = make_dict(tmp_path, words=["Anthropic"],
                  corrections=[("cloud code", "Claude Code")])
    d2 = Dictionary(str(tmp_path / "dictionary.json"))
    assert [w.text for w in d2.words] == ["Anthropic"]
    assert [(c.heard, c.write) for c in d2.corrections] == [
        ("cloud code", "Claude Code")
    ]
    out, fired = d2.apply_corrections("cloud code")
    assert out == "Claude Code"


def test_hand_edited_file(tmp_path):
    path = tmp_path / "dictionary.json"
    path.write_text('{"words": [{"text": "Vercel", "created": 1.0}], '
                    '"corrections": [{"heard": "vercel", "write": "Vercel", '
                    '"created": 1.0}]}', encoding="utf-8")
    d = Dictionary(str(path))
    assert d.words[0].text == "Vercel"
    out, fired = d.apply_corrections("vercel")
    assert out == "Vercel"


def test_corrupt_file_recovers(tmp_path):
    path = tmp_path / "dictionary.json"
    path.write_text("{nope", encoding="utf-8")
    d = Dictionary(str(path))
    assert d.words == []
    assert d.corrections == []


def test_word_entry_validation(tmp_path):
    d = Dictionary(str(tmp_path / "dictionary.json"))
    with pytest.raises(ValueError):
        d.add_word("   ")
    with pytest.raises(ValueError):
        d.add_correction("a", "")
    # identical heard/write is allowed — it still catches glued forms
    d.add_correction("Claude Code", "Claude Code")


# --- undo support ----------------------------------------------------------

def test_compute_undo_basic(tmp_path):
    d = make_dict(tmp_path, corrections=[("cloud code", "Claude Code")])
    result = d.compute_undo("I use Claude Code daily.")
    assert result is not None
    heard, span_start, write = result
    assert heard == "cloud code"
    assert write == "Claude Code"
    assert span_start >= 0
    # span_start points at the start of the written text
    assert "I use Claude Code daily."[span_start:] == "Claude Code daily."


def test_compute_undo_none_when_no_match(tmp_path):
    d = make_dict(tmp_path, corrections=[("cloud code", "Claude Code")])
    assert d.compute_undo("nothing to undo here") is None


def test_compute_undo_empty(tmp_path):
    d = make_dict(tmp_path)
    assert d.compute_undo("anything") is None


def test_compute_undo_picks_last_occurrence(tmp_path):
    d = make_dict(tmp_path, corrections=[("supabase", "Supabase")])
    text = "Supabase is fine but Supabase wins"
    heard, span_start, _ = d.compute_undo(text)
    assert span_start == text.rfind("Supabase")


def test_compute_undo_multiple_entries_picks_latest_span(tmp_path):
    d = make_dict(tmp_path, corrections=[("cloud code", "Claude Code"),
                                         ("anthropic", "Anthropic")])
    text = "Anthropic builds Claude Code."
    heard, span_start, _ = d.compute_undo(text)
    # the later correction in the text wins (Claude Code starts later)
    assert heard == "cloud code"
    assert span_start == text.find("Claude Code")
