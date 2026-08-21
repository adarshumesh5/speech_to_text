"""Grogu design tokens — modern Star Wars, cyan lightsaber accent.

Single source of truth for the visual language. Every view pulls colors, type,
spacing, radii, borders, shadows and motion from here. No one-off values in
components — if it isn't a token, it doesn't exist.

Direction: deep-space dark UI with a cyan lightsaber as the one glowing accent.
Cool neutral chrome, generous dark panels, one signal color (cyan) for
recording/primary, amber reserved for warnings/corrections.

The lightsaber is the recording instrument: it ignites and glows while you
speak, dims on the way out.
"""

# ---------------------------------------------------------------------------
# COLOR — deep space, cool chrome, one cyan accent.
# ---------------------------------------------------------------------------
class Color:
    # surfaces (dark, cool, deep)
    INK           = "#0B0E13"   # deep space body
    PANEL         = "#131720"   # secondary panels
    PANEL_RAISED  = "#1C2230"   # raised faces (buttons, headers)
    WELL          = "#07090D"   # recessed wells (inputs, windows)
    SEAM_DARK     = "#04060A"   # bottom edge / recessed shadow line
    SEAM_LIGHT    = "#28303E"   # top lit edge / panel boundary

    # chrome (cool silver)
    ALUMINUM      = "#45E3C8"   # primary accent / selection (the saber cyan)
    ALUMINUM_LT   = "#8DF3E3"   # hot core / highlight
    ALUMINUM_DK   = "#1E8F80"   # dimmed accent / pressed

    # text (cool white family)
    TEXT          = "#E9EEF5"
    TEXT_DIM      = "#A9B4C4"
    TEXT_FAINT    = "#6E7A90"
    TEXT_ON_LIGHT = "#0B0E13"

    # the saber — the only glowing thing in the app
    SABER         = "#45E3C8"
    SABER_LT      = "#A6F7EA"   # white-hot core
    SABER_DK      = "#1E8F80"   # retracted / dim emitter

    # levels — green/amber only (cyan is for the saber, not levels)
    LEVEL_GREEN   = "#6FD08C"
    LEVEL_AMBER   = "#F0B44B"

    # interaction states
    SELECT_BG     = "#45E3C8"   # selected row = cyan face, ink text
    SELECT_TEXT   = "#0B0E13"
    HOVER_BG      = "#232B3A"
    FOCUS         = "#45E3C8"
    DISABLED      = "#3A4354"
    WARNING       = "#F0B44B"   # amber: the signal color (errors, corrections)

    # back-compat aliases (older widgets read RECORD for the record lamp)
    RECORD        = SABER
    RECORD_DARK   = SABER_DK

    @classmethod
    def apply_high_contrast(cls) -> None:
        """Bump text contrast when Windows high-contrast mode is active.

        Mutates the class attributes; custom widgets read them at paint time,
        so the change applies app-wide without a rebuild.
        """
        cls.TEXT = "#FFFFFF"
        cls.TEXT_DIM = "#E9EEF5"
        cls.TEXT_FAINT = "#C9D2E0"
        cls.FOCUS = "#FFFFFF"
        cls.SEAM_LIGHT = "#6E7A90"


# ---------------------------------------------------------------------------
# TYPE — industrial grotesque for UI, monospaced for counters/timings.
# Bahnschrift ships with Windows 10+; Consolas is the guaranteed mono fallback.
# ---------------------------------------------------------------------------
class Type:
    FONT_UI = '"Bahnschrift", "Segoe UI", "Arial", sans-serif'
    FONT_MONO = '"Cascadia Mono", "Consolas", "Courier New", monospace'

    # px scale (design grid is 1px at 96dpi; Qt DPI-scales automatically)
    MICRO   = 9    # silkscreen labels
    LABEL   = 10   # small labels / captions
    BODY    = 12   # default text
    SUB     = 13   # section headers
    TITLE   = 16   # window / panel titles
    DISPLAY = 20   # counters, big numerals

    WEIGHT_REGULAR = 400
    WEIGHT_MEDIUM  = 500
    WEIGHT_BOLD    = 600

    # silkscreen label style
    LABEL_WEIGHT = 600
    LABEL_TRACKING_PX = 1.0    # tight uppercase tracking
    LABEL_CASE = "uppercase"


# ---------------------------------------------------------------------------
# SPACING — 4px grid.
# ---------------------------------------------------------------------------
class Space:
    XS      = 2
    SM      = 4
    MD      = 8
    LG      = 12
    XL      = 16
    XXL     = 24
    HUGE    = 32
    MASSIVE = 48


# ---------------------------------------------------------------------------
# RADIUS — modern, softly rounded. Controls 6px, panels 8px.
# ---------------------------------------------------------------------------
class Radius:
    NONE = 0
    SM   = 6
    MD   = 8
    LG   = 12


# ---------------------------------------------------------------------------
# BORDER — thin hairline seams; the saber blade is its own thing.
# ---------------------------------------------------------------------------
class Border:
    THIN  = 1
    THICK = 2


# ---------------------------------------------------------------------------
# SHADOW — soft depth for modern panels, inset for wells.
# ---------------------------------------------------------------------------
class Shadow:
    WELL    = "inset 0 1px 3px rgba(0, 0, 0, 0.6)"
    RAISED  = "0 1px 0 rgba(255, 255, 255, 0.05)"
    PRESSED = "inset 0 1px 3px rgba(0, 0, 0, 0.55)"
    POP     = "0 6px 24px rgba(0, 0, 0, 0.55), 0 1px 3px rgba(0, 0, 0, 0.4)"
    FRAME   = "inset 0 0 0 1px rgba(0, 0, 0, 0.5), inset 0 1px 3px rgba(0, 0, 0, 0.5)"


# ---------------------------------------------------------------------------
# MOTION — fast, mechanical, no bounce. The saber has its own ballistics.
# ---------------------------------------------------------------------------
class Motion:
    PRESS_MS   = 60     # button press feedback
    STATE_MS   = 120    # lamp / indicator state changes
    PANEL_MS   = 150    # panel / tab transitions

    EASE_PRESS = "linear"
    EASE_STATE = "cubic-bezier(0.33, 1, 0.68, 1)"  # ease-out, mechanical

    # saber — ignite is fast, retract is smooth
    SABER_IGNITE_MS  = 320
    SABER_RETRACT_MS = 260
    SABER_PULSE_MS   = 120   # glow pulse tied to the mic level

    # level-meter ballistics — analog standard: fast attack, slow decay
    VU_ATTACK_S  = 0.25
    VU_DECAY_S   = 1.8

    BLINK_MS   = 500    # standby blink


# ---------------------------------------------------------------------------
# COMPONENT TOKENS — derived from the primitives above.
# ---------------------------------------------------------------------------
class Component:
    # transport buttons: dark modern pill, cyan face when active
    BTN_FACE      = Color.PANEL_RAISED
    BTN_FACE_ACT  = Color.ALUMINUM
    BTN_TEXT      = Color.TEXT
    BTN_TEXT_ACT  = Color.TEXT_ON_LIGHT
    BTN_BORDER    = Color.SEAM_LIGHT
    BTN_TOP_EDGE  = Color.SEAM_LIGHT

    # record button (turns saber-cyan when armed)
    REC_FACE      = Color.SABER
    REC_FACE_DARK = Color.SABER_DK
    REC_TEXT      = "#06221E"

    # recessed wells: text fields, search, the level meter, history pane
    WELL_BG       = Color.WELL
    WELL_BORDER   = Color.SEAM_LIGHT

    # silkscreen label style (QSS-ready string)
    SILKSCREEN    = (
        f"font-family: {Type.FONT_UI}; font-size: {Type.MICRO}px;"
        f"font-weight: {Type.LABEL_WEIGHT}; letter-spacing: {Type.LABEL_TRACKING_PX}px;"
        f"color: {Color.TEXT_DIM};"
    )

    # counter numerals (segmented/mono look)
    COUNTER       = (
        f"font-family: {Type.FONT_MONO}; font-size: {Type.DISPLAY}px;"
        f"font-weight: {Type.WEIGHT_MEDIUM}; color: {Color.TEXT};"
    )

    # level meter bezel frame (QSS-ready)
    VU_BEZEL      = (
        f"background-color: {Color.WELL}; border: {Border.THICK}px solid {Color.SEAM_DARK};"
    )
