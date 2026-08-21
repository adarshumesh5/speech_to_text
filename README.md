# Grogu

> **Speak. The Force types.**

Grogu is a push-to-talk dictation app for Windows with a modern, Star
Wars-inspired interface: a near-black space palette, chrome accents, and a
cyan **lightsaber** that ignites and glows in time with your voice while you
record.

Hold a hotkey anywhere, speak naturally, release, and polished text appears at
the cursor in whatever app you're in. Transcription runs **locally on your
GPU** (faster-whisper on CUDA); cleanup is a **model-free rules engine** —
no cloud, no LLM, nothing to install.

The interface is a real Windows application: a standard resizable main window
with a menu bar, taskbar icon, Settings on `Ctrl+,`, plus a secondary system
tray icon for status and dictation while you work in other apps.

## Features

- **Lightsaber recording indicator** — ignites and glows when you speak
- **Local transcription** — your voice never leaves your computer
- **Smart cleanup** — removes filler words ("um", "like", "you know") and turns spoken "comma", "question mark", "new line" into real punctuation
- **Custom dictionary** — teach it names, jargon, and corrections (import/export as JSON)
- **Learn from corrections** — auto-add every fired correction to the dictionary
- **History export** — save transcriptions to text, Markdown, or CSV
- **Global hotkey** — works in any app (Ctrl+Shift+Space)
- **System tray** — dictate without opening the window
- **Start with Windows** — optional auto-start
- **Sound cues** — lightsaber ignite/retract sounds
- **Undo** — Ctrl+Z reverses the last dictation

## Quick Install (Pre-built)

Download the latest installer from [Releases](https://github.com/adarshumesh5/speech_to_text/releases):

1. Download `Grogu-0.3.0.msi` (or latest version)
2. Run the installer
3. Pin Grogu to your Start menu or Taskbar
4. Hold `Ctrl+Shift+Space` and speak
5. Release to type

**Note:** First run downloads the Whisper model (~500 MB). Subsequent runs are instant.

## Changelog

### v0.3.0 — Phase 1 Polish (Latest)

> Merged via [PR #3](https://github.com/adarshumesh5/speech_to_text/pull/3) on Aug 21, 2026.

Five user-visible improvements:

- **Spoken punctuation** — say "comma", "question mark", "exclamation mark", "new line", "new paragraph", "dot dot dot" and Grogu types the real characters. Ambiguous words (period, colon, semicolon) only convert when they clearly act as punctuation, so "colon cancer" and "the period of history" are never mangled
- **History export** — the Transcriptions tab can save the current list to **plain text, Markdown, or CSV**
- **Dictionary import/export** — write a JSON backup and merge another dictionary in (case-insensitive, no overwrites)
- **Learn from corrections** — Settings toggle that auto-adds every fired correction to the dictionary
- **Failure toasts** — if insertion fails (elevated app, focus lock), Grogu copies the text to your clipboard and notifies you instead of failing silently; history rows are marked **NOT INSERTED**

### v0.2.1 — Pointer Fix

> Merged via [PR #1](https://github.com/adarshumesh5/speech_to_text/pull/1) on Aug 21, 2026.

**The fix:** dictated text now lands **exactly where your cursor is blinking**, even when another window has focus when you press the hotkey.

What changed:

- **Caret tracking** — Grogu watches all visible windows for the one with the blinking cursor and remembers it, so it knows where you were typing even if you switch apps before dictating
- **Direct paste into the text control** — text is pasted straight into the target app's edit control (works in Notepad, browsers, editors) without needing to steal focus first
- **Verified delivery** — Grogu checks that the text actually landed and only reports success when it did
- **Never targets terminal windows** — Freebuff, cmd.exe, Windows Terminal, and other console windows are ignored as dictation targets
- **No more focus-stealing on startup** — Grogu starts hidden and stays out of the way
- **Clipboard fallback** — if an app blocks direct insertion, text goes to your clipboard with a notification (just press `Ctrl+V`)

**How to install this build:**

```powershell
# From source
git clone https://github.com/adarshumesh5/speech_to_text.git
cd speech_to_text
git checkout master          # pointer fix is on master
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python scripts\make_assets.py
python -m grogu
```

Or download the latest MSI from [Releases](https://github.com/adarshumesh5/speech_to_text/releases) and run it.

### v0.2.0 — Grogu (Star Wars Edition)

- Renamed to **Grogu** with a full Star Wars-inspired UI
- **Lightsaber recording indicator** — ignites and glows while you speak
- Local GPU transcription (faster-whisper on CUDA)
- Smart cleanup (filler-word removal)
- Custom dictionary (words + corrections)
- Global hotkey (`Ctrl+Shift+Space`)
- System tray, start-with-Windows, sound cues, undo

## Install from Source (For Developers)

### Prerequisites

- **Windows 10/11** (64-bit)
- **Python 3.11+** ([Download Python](https://www.python.org/downloads/))
- **NVIDIA GPU with CUDA** (recommended) — CPU fallback available but slower
- **Git** ([Download Git](https://git-scm.com/download/win))

### Setup Steps

1. **Clone the repository:**
   ```powershell
   git clone https://github.com/adarshumesh5/speech_to_text.git
   cd speech_to_text
   ```

2. **Create a virtual environment:**
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```powershell
   pip install -e ".[dev]"
   ```

4. **Generate app icons:**
   ```powershell
   python scripts\make_assets.py
   ```

5. **Run Grogu:**
   ```powershell
   python -m grogu
   ```

6. **Run tests (optional):**
   ```powershell
   pytest
   ```

### Build Installer

To build the MSI installer for distribution:

```powershell
.\scripts\build.ps1
```

This creates:
- `dist\Grogu\Grogu.exe` — portable build
- `dist\Grogu-0.3.0.msi` — installer (Windows 10/11)

## Usage

### Basic Dictation

1. Hold `Ctrl+Shift+Space` (the default hotkey)
2. Speak clearly
3. Release to type at your cursor

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+Space` | Dictate (hold to record) |
| `F7` | Toggle recording |
| `Esc` | Cancel recording |
| `Ctrl+Z` | Undo last dictation |
| `Ctrl+,` | Open Settings |
| `Ctrl+F` | Search history |

### Custom Dictionary

Open Settings (`Ctrl+,`) → Dictionary tab to add:

- **Words** — names, jargon, brand names the engine should know
- **Corrections** — fix misheard words (e.g., "cloud code" → "Claude Code")

Example corrections:
```json
{
  "heard": "cloud code",
  "write": "Claude Code"
}
```

## Troubleshooting

**Hotkey doesn't work:**
- Another app may have grabbed it — change it in Settings
- Use "Test hotkey" in Settings to verify registration

**Text doesn't appear at cursor:**
- Target app may be running elevated (Grogu can't type into admin windows)
- Try enabling "Clipboard fallback" in Settings (uses Ctrl+V instead of keystrokes)
- Some apps block keyboard input — try pasting manually
- If text appears in wrong window, ensure the target window was focused when you pressed the hotkey
- Check Settings → "Test hotkey" to verify the hotkey is working

**Text appears in wrong location:**
- Grogu captures the foreground window when you press the hotkey
- If you switch windows while holding the hotkey, text may land in the wrong place
- Release the hotkey quickly after pressing it for best results
- Enable "Clipboard fallback" for apps that don't accept synthetic keystrokes

**Dictation is slow:**
- First run downloads the model — be patient
- Ensure your NVIDIA GPU drivers are up to date
- CPU fallback is available in Settings

**Bluetooth mic issues:**
- Bluetooth compresses audio — use built-in mic or wired headset
- Check Windows Sound settings for correct input device

## Architecture

```
Hotkey (Win32 RegisterHotKey) → Mic capture (WASAPI)
  → faster-whisper (CUDA/CPU) → Rules cleanup
    → Dictionary correction → Type at cursor
```

| Module | Purpose |
|--------|---------|
| `grogu/hotkey.py` | Global hotkey registration |
| `grogu/audio.py` | Microphone capture |
| `grogu/stt.py` | Speech-to-text (Whisper) |
| `grogu/cleaner.py` | Filler word removal |
| `grogu/dictionary.py` | Custom words & corrections |
| `grogu/injector.py` | Text typing at cursor |
| `grogu/ui/` | Lightsaber UI, settings, history |

## Testing

Run the test suite:

```powershell
pytest -v
```

71 tests covering: hotkey registration, config migration, dictionary matching, history storage, and more.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Acknowledgments

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — Fast Whisper implementation
- [PySide6](https://doc.qt.io/qtforpython-6/) — Qt for Python
- Star Wars inspiration — May the Force be with you
