"""Voice command layer — spoken editing commands for dictation.

When the *entire* dictation is one command phrase (or a chain joined by
"and"/"then") — "undo last", "select all and delete", "caps on" — Grogu
executes the matching editing keystrokes in the target app instead of typing
text. Anything else is dictated normally: commands are only recognised as
whole utterances, so real speech like "I want to undo last week's meeting"
is never eaten.

Commands are executed with the same focus dance as ``send_text``, so they
land in the app the user was working in. Esc (or the cancel event) aborts
mid-chain; commands already sent stay.
"""

from __future__ import annotations

import logging
import re

from grogu.injector import (
    VK_A,
    VK_BACK,
    VK_CAPITAL,
    VK_CONTROL,
    VK_DELETE,
    VK_RETURN,
    VK_Z,
    focus_window_with_retry,
    get_foreground_hwnd,
    get_window_title,
    is_own_window,
    press_combo,
    set_caps_lock,
)

log = logging.getLogger(__name__)

# canonical command name -> human label (shown in history / notifications)
_LABELS = {
    "undo": "Undo last",
    "select_all": "Select all",
    "delete_word": "Delete last word",
    "delete_selection": "Delete selection",
    "caps_on": "Caps lock on",
    "caps_off": "Caps lock off",
    "new_line": "New line",
    "new_paragraph": "New paragraph",
}

# canonical command -> key events. Each event is either a chord
# (modifiers | None, vk) or ("caps", bool) for a state-setting toggle.
_COMMAND_SEQUENCES: dict[str, list[tuple]] = {
    "undo": [([VK_CONTROL], VK_Z)],
    "select_all": [([VK_CONTROL], VK_A)],
    "delete_word": [([VK_CONTROL], VK_BACK)],
    "delete_selection": [(None, VK_DELETE)],
    "caps_on": [("caps", True)],
    "caps_off": [("caps", False)],
    "new_line": [([], VK_RETURN)],
    "new_paragraph": [([], VK_RETURN), ([], VK_RETURN)],
}

# spoken phrase -> canonical command. Longest phrases first so "undo last"
# beats "undo", "delete the last word" beats "delete word", etc.
_PHRASES: list[tuple[str, str]] = [
    ("undo last", "undo"),
    ("undo that", "undo"),
    ("undo it", "undo"),
    ("undo", "undo"),
    ("select all", "select_all"),
    ("delete the last word", "delete_word"),
    ("delete last word", "delete_word"),
    ("delete previous word", "delete_word"),
    ("delete last", "delete_word"),
    ("delete word", "delete_word"),
    ("delete", "delete_selection"),
    ("caps lock on", "caps_on"),
    ("caps on", "caps_on"),
    ("caps lock off", "caps_off"),
    ("caps off", "caps_off"),
    ("new paragraph", "new_paragraph"),
    ("new line", "new_line"),
]

_CHAIN_SPLIT = re.compile(r"\s+(?:and|then)\s+")
_TRAILING = re.compile(r"[.!?…;:,]+$")
_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Lowercase, collapse whitespace, strip terminal punctuation.

    The rules cleaner capitalises sentences and adds periods, so "Undo
    last." must still parse as a command.
    """
    t = text.strip().lower()
    t = _TRAILING.sub("", t).strip()
    return _WS.sub(" ", t)


def _match(token: str) -> str | None:
    for phrase, command in _PHRASES:
        if token == phrase:
            return command
    return None


def parse_commands(text: str) -> list[str] | None:
    """Parse ``text`` as a whole-utterance voice command (or chain).

    Returns the canonical command list when the *entire* text is commands,
    else None (dictate normally).
    """
    norm = _normalize(text)
    if not norm:
        return None
    commands: list[str] = []
    for token in _CHAIN_SPLIT.split(norm):
        token = token.strip()
        if not token:
            return None
        command = _match(token)
        if command is None:
            return None
        commands.append(command)
    return commands or None


def command_label(commands: list[str]) -> str:
    """Human label for history/notifications: "Undo last · Select all"."""
    return " · ".join(_LABELS.get(c, c) for c in commands)


def execute(commands: list[str], target_hwnd: int = 0, cancel_event=None) -> bool:
    """Run the editing keystrokes for ``commands`` in ``target_hwnd``.

    Brings the target to the foreground first (same dance as ``send_text``),
    then sends each chord. Returns False only when the target could not be
    focused — the keystrokes themselves are fire-and-forget SendInput.
    """
    target = target_hwnd
    if target and is_own_window(target):
        target = 0
    focused = True
    if target:
        cur = get_foreground_hwnd()
        if cur != target:
            focused = focus_window_with_retry(target, retries=3, delay=0.1)
            log.info("voice command: focus target=%s title=%r focused=%s",
                     target, get_window_title(target), focused)
    if not focused:
        log.warning("voice command: could not focus hwnd=%s title=%r",
                    target, get_window_title(target))
        return False
    for command in commands:
        for event in _COMMAND_SEQUENCES.get(command, []):
            if cancel_event is not None and cancel_event.is_set():
                return False
            if event[0] == "caps":
                set_caps_lock(event[1])
            else:
                mods, key = event
                press_combo(mods, key)
    log.info("voice command executed: %s", command_label(commands))
    return True
