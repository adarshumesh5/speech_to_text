"""Tests for grogu.cleaner."""

from grogu.cleaner import PassthroughCleaner, RulesCleaner, build_cleaner


def clean(text, tone=None):
    return RulesCleaner().clean(text, tone=tone)


# --- fillers ---------------------------------------------------------------

def test_leading_fillers_removed():
    assert clean("um so uh like we should ship it") == "We should ship it."


def test_multiple_leading_fillers():
    assert clean("so like actually you know i mean just say it") == "Say it."


def test_hard_fillers_removed_anywhere():
    assert clean("I um think uh it works") == "I think it works."
    assert clean("Uhm, so like, we go") == "We go."


def test_mid_sentence_soft_filler_kept():
    # "like" mid-sentence can be meaningful — must survive
    assert clean("I like pizza") == "I like pizza."


def test_filler_not_stripped_inside_word():
    assert clean("we heard the music") == "We heard the music."


# --- repeats ---------------------------------------------------------------

def test_repeated_word_collapsed():
    assert clean("the the launch is slipping") == "The launch is slipping."


def test_triple_repeat_collapsed():
    assert clean("no no no we go now") == "No we go now."


def test_repeat_case_insensitive():
    assert clean("I I think so") == "I think so."


# --- punctuation & case ----------------------------------------------------

def test_capitalise_and_period():
    assert clean("hello world") == "Hello world."


def test_keeps_question_mark():
    assert clean("are you free tomorrow?") == "Are you free tomorrow?"


def test_keeps_exclamation():
    assert clean("that was amazing!") == "That was amazing!"


def test_keeps_existing_punctuation():
    assert clean("Let's meet at 5. Then we leave at six.") == (
        "Let's meet at 5. Then we leave at six."
    )


def test_empty_input():
    assert clean("") == ""
    assert clean("   ") == ""


def test_only_fillers():
    assert clean("um uh like so") == ""


def test_mixed_dirty_sentence():
    raw = "um actually so the the meeting is at noon"
    assert clean(raw) == "The meeting is at noon."


# --- spoken punctuation -----------------------------------------------------

def test_spoken_comma():
    assert clean("hello comma how are you") == "Hello, how are you."


def test_spoken_question_mark():
    assert clean("are you free question mark") == "Are you free?"


def test_spoken_exclamation():
    assert clean("that was great exclamation mark") == "That was great!"


def test_spoken_new_line():
    assert clean("first line new line second line") == "First line.\nSecond line."


def test_spoken_new_paragraph():
    assert clean("first line new paragraph second line") == (
        "First line.\n\nSecond line."
    )


def test_spoken_period_at_end():
    assert clean("we should ship period") == "We should ship."


def test_spoken_colon_before_new_line():
    # colon acts as punctuation when a punctuation command follows
    assert clean("define fn colon new line return x") == "Define fn:\nReturn x."


def test_spoken_period_not_corrupted_mid_sentence():
    # "period" / "colon" as real words must survive
    assert clean("the period of history matters") == "The period of history matters."
    assert clean("colon cancer is serious") == "Colon cancer is serious."


def test_spoken_punctuation_with_fillers():
    assert clean("um so hello comma how are you question mark") == "Hello, how are you?"


def test_spoken_ellipsis():
    assert clean("it goes dot dot dot") == "It goes…"


# --- passthrough -----------------------------------------------------------

def test_passthrough_returns_raw():
    assert PassthroughCleaner().clean("  um so Hello   ") == "um so Hello"


def test_build_cleaner():
    assert isinstance(build_cleaner("rules"), RulesCleaner)
    assert isinstance(build_cleaner("passthrough"), PassthroughCleaner)
    assert isinstance(build_cleaner("nonsense"), RulesCleaner)  # safe default
