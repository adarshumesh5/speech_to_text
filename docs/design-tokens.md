# Grogu Design System — "The Saber" (modern Star Wars)

Deep-space dark UI with a single glowing accent: the **cyan lightsaber**. It
is the recording instrument — it ignites when you speak, glows in time with
your voice, and retracts on the way out. Everything else is restrained: cool
chrome neutrals, generous dark panels, no decorative glow beyond the blade.

**Excluded, permanently:** the 1980s field-recorder language is retired. No
brushed aluminum, no silkscreen-on-paper, no tape windows, no red record
light. Also no neon/synthwave gradients, no purple-pink, no glassmorphism.
One blade, one glow.

The canonical tokens live in `sotto/ui/design_tokens.py`. This document is the
spec; the code is the single source of truth. **If it isn't a token, it
doesn't exist** — components never carry one-off values.

---

## 1. Color

Cool, blue-black neutrals. One accent: **cyan** (the saber). One signal
color: **amber** (warnings, corrections, fired dictionary entries).

| Token | Hex | Use |
|---|---|---|
| `Color.INK` | `#0B0E13` | Deep-space body (window background) |
| `Color.PANEL` | `#131720` | Secondary panels |
| `Color.PANEL_RAISED` | `#1C2230` | Raised faces — buttons, headers |
| `Color.WELL` | `#07090D` | Recessed wells — inputs, meters, history pane |
| `Color.SEAM_DARK` | `#04060A` | Bottom edge, recessed shadow line |
| `Color.SEAM_LIGHT` | `#28303E` | Top lit edge, panel boundary |
| `Color.ALUMINUM` | `#45E3C8` | **The saber cyan.** Primary accent, selection |
| `Color.ALUMINUM_LT` | `#8DF3E3` | Hot core / highlight |
| `Color.ALUMINUM_DK` | `#1E8F80` | Dimmed accent / pressed |
| `Color.TEXT` | `#E9EEF5` | Primary text (cool white) |
| `Color.TEXT_DIM` | `#A9B4C4` | Secondary text, captions |
| `Color.TEXT_FAINT` | `#6E7A90` | Disabled-ish captions |
| `Color.TEXT_ON_LIGHT` | `#0B0E13` | Text on cyan faces |
| `Color.SABER` | `#45E3C8` | **The only glowing thing.** Blade mid-glow |
| `Color.SABER_LT` | `#A6F7EA` | White-hot blade core |
| `Color.SABER_DK` | `#1E8F80` | Retracted / dim emitter |
| `Color.LEVEL_GREEN` | `#6FD08C` | Level safe zone |
| `Color.LEVEL_AMBER` | `#F0B44B` | Level warning zone |
| `Color.WARNING` | `#F0B44B` | Amber signal: errors, corrections, warnings |
| `Color.SELECT_BG` | `#45E3C8` | Selected row = cyan face |
| `Color.SELECT_TEXT` | `#0B0E13` | Text on selected row |
| `Color.HOVER_BG` | `#232B3A` | Row hover |
| `Color.FOCUS` | `#45E3C8` | Focus outline |
| `Color.DISABLED` | `#3A4354` | Disabled controls |

Rules:
- Cyan is **the** accent — recording, selection, focus, the saber. It does
  not appear in levels (levels stay green/amber).
- Amber is the signal color — warnings, corrections, anything worth noticing.
- In Windows high-contrast mode, text tokens brighten to full-white families
  (`apply_high_contrast()` mutates the tokens at startup).

## 2. Type

| Token | Value | Use |
|---|---|---|
| `Type.FONT_UI` | Bahnschrift → Segoe UI → Arial | All UI |
| `Type.FONT_MONO` | Cascadia Mono → Consolas → Courier New | Counters, timings, search input |
| `Type.MICRO` | 9px | Small labels |
| `Type.LABEL` | 10px | Captions |
| `Type.BODY` | 12px | Default |
| `Type.SUB` | 13px | Section headers |
| `Type.TITLE` | 16px | Panel titles |
| `Type.DISPLAY` | 20px, mono | Counters, big numerals |
| `Type.WEIGHT_BOLD` | 600 | Labels, emphasis |

Labels stay small and uppercase with tight tracking (silkscreen heritage,
modernized). Counters and timings are monospaced.

## 3. Spacing

4px grid: `XS 2 · SM 4 · MD 8 · LG 12 · XL 16 · XXL 24 · HUGE 32 · MASSIVE 48`.

## 4. Radius

`SM 6 · MD 8 · LG 12`. Controls 6px, panels 8px, cards 12px. No pill shapes.

## 5. Border

`THIN 1px` hairline seams; `THICK 2px` for prominent frames (the level-meter
bezel, the saber window). Seams read as `SEAM_LIGHT` line over `SEAM_DARK`
line.

## 6. Shadow

Soft, modern depth:

| Token | Value | Use |
|---|---|---|
| `Shadow.WELL` | inset 0 1px 3px, 60% | Recessed wells |
| `Shadow.RAISED` | 0 1px 0, 5% white | Lit top edge of raised faces |
| `Shadow.PRESSED` | inset 0 1px 3px, 55% | Button pressed |
| `Shadow.POP` | 0 6px 24px + 0 1px 3px, ~50% | Floating menus |
| `Shadow.FRAME` | inset ring + inset 1px 3px | Meter bezel |

## 7. Motion

Fast, mechanical, no bounce. The saber has its own ballistics.

| Token | Value |
|---|---|
| `Motion.PRESS_MS` | 60ms, linear — button press |
| `Motion.STATE_MS` | 120ms — lamps, indicators |
| `Motion.PANEL_MS` | 150ms — panel/tab changes |
| `Motion.SABER_IGNITE_MS` | 320ms — blade ignition |
| `Motion.SABER_RETRACT_MS` | 260ms — blade retract |
| `Motion.SABER_PULSE_MS` | 120ms — glow pulse tied to mic level |
| `Motion.VU_ATTACK_S` | 0.25s — VU needle attack |
| `Motion.VU_DECAY_S` | 1.8s — VU needle decay (analog ballistics) |
| `Motion.BLINK_MS` | 500ms — standby blink |

Button press = content shifts + `PRESSED` shadow. The VU needle and the saber
are the only breathing animations; everything else snaps.

## 8. Components (derived tokens)

- **Transport buttons** — dark modern faces (`BTN_FACE`), cyan face when
  active (`BTN_FACE_ACT` + `BTN_TEXT_ACT` ink text). Pressed = `PRESSED`
  shadow + 1px shift.
- **Record button** — `REC_FACE` saber cyan when armed, `REC_TEXT` deep ink.
- **Wells** — text fields, search, level meter, history pane: `WELL_BG`,
  `WELL_BORDER`, `Shadow.WELL` inset. Cursor = block/beam (mono).
- **Lightsaber** — custom-painted hilt + three-layer blade (wide soft halo →
  mid glow → white-hot core). Ignites on record, pulses with mic level,
  retracts on stop. Drawn at 60fps in `sotto/ui/lightsaber.py`.
- **Level meter** — needle VU, green → amber scale, cyan frame.
- **Selection** — cyan face (`SELECT_BG`) + ink text; focus = cyan outline.

## 9. Layout principles

- The deck strip (transport + saber + level meter + counter) is the top of
  the main window — always visible. History and Dictionary below.
- Panels stack like layered glass on deep space: `PANEL` on `INK`, separated
  by hairline seams.
- Window chrome: standard native frame (resizable, snap, taskbar) with a dark
  title bar. The app behaves like a normal Windows application.
- The tray icon is secondary: status + hotkey while working elsewhere.

## 10. Copy / voice

Star Wars-adjacent but sober: "REC", "STOP", "LEVEL", "COUNTER", "HISTORY",
"DICTIONARY", "DICTATE". No exclamation marks, no gimmicks. The tagline:
**Speak. The Force types.**
