"""Tests for the voice command layer (grogu/commands.py)."""

from grogu.commands import command_label, parse_commands


def test_single_commands():
    assert parse_commands("undo last") == ["undo"]
    assert parse_commands("undo") == ["undo"]
    assert parse_commands("select all") == ["select_all"]
    assert parse_commands("caps on") == ["caps_on"]
    assert parse_commands("caps lock off") == ["caps_off"]
    assert parse_commands("new line") == ["new_line"]
    assert parse_commands("new paragraph") == ["new_paragraph"]
    assert parse_commands("delete word") == ["delete_word"]


def test_cleaner_output_still_parses():
    # the rules cleaner capitalises and adds terminal punctuation
    assert parse_commands("Undo last.") == ["undo"]
    assert parse_commands("Select all!") == ["select_all"]
    assert parse_commands("Delete the last word?") == ["delete_word"]


def test_chained_commands():
    assert parse_commands("select all and delete") == [
        "select_all", "delete_selection",
    ]
    assert parse_commands("undo last then new paragraph") == [
        "undo", "new_paragraph",
    ]


def test_regular_speech_not_eaten():
    assert parse_commands("i want to undo last week's meeting") is None
    assert parse_commands("the quick brown fox") is None
    assert parse_commands("please select all the files") is None
    assert parse_commands("new line for the boss") is None


def test_empty_and_junk():
    assert parse_commands("") is None
    assert parse_commands("   ") is None
    assert parse_commands("...") is None


def test_longest_phrase_wins():
    # "undo last" must not be split into "undo" + unknown "last"
    assert parse_commands("undo last") == ["undo"]
    assert parse_commands("undo that") == ["undo"]
    assert parse_commands("delete last") == ["delete_word"]


def test_command_label():
    assert command_label(["undo"]) == "Undo last"
    assert command_label(["undo", "select_all"]) == "Undo last · Select all"


def test_sequences_exist_for_every_command():
    from grogu.commands import _COMMAND_SEQUENCES, _LABELS

    assert set(_COMMAND_SEQUENCES) == set(_LABELS)
    for command, events in _COMMAND_SEQUENCES.items():
        assert events, f"{command} has no key events"
