"""Generate Grogu branding assets.

Design: a dark space tile with a diagonal cyan lightsaber — a metallic hilt
and a glowing blade drawn as layered alpha strokes (soft halo → mid glow →
white-hot core). Produces multi-size PNGs, an .ico for the app, and the three
tray states (idle / recording-glowing / muted-dim).

Usage: python scripts/make_assets.py
Requires: Pillow (dev dependency).
"""

from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "sotto", "ui", "assets")

# palette mirrors sotto.ui.design_tokens (duplicated here only so the asset
# script has no runtime dependency on the app)
INK = (11, 14, 19)
PANEL = (19, 23, 32)
SEAM_LIGHT = (40, 48, 62)
SABER = (69, 227, 200)      # #45E3C8
SABER_LT = (166, 247, 234)  # #A6F7EA
SABER_DK = (30, 143, 128)   # #1E8F80
HILT = (168, 178, 192)
HILT_DK = (96, 106, 122)

SIZES = [16, 24, 32, 48, 64, 128, 256]


def _blade_line(d: ImageDraw.ImageDraw, p0, p1, color, width, alpha):
    c = color + (alpha,)
    d.line([p0, p1], fill=c, width=max(1, int(width)))


def draw_saber(size: int, lit: float = 1.0) -> Image.Image:
    """``lit`` 1.0 = fully glowing blade, 0.0 = dim/muted, -1 = none."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # dark tile
    d.rounded_rectangle([0, 0, size - 1, size - 1],
                        radius=max(4, round(size * 0.22)),
                        fill=INK + (255,), outline=SEAM_LIGHT + (255,),
                        width=max(1, size // 96))

    # geometry: diagonal saber, hilt at bottom-left
    s = size
    x0, y0 = s * 0.20, s * 0.80          # hilt start
    x1, y1 = s * 0.42, s * 0.58          # emitter
    x2, y2 = s * 0.82, s * 0.18          # blade tip
    angle = math.atan2(y1 - y0, x1 - x0)

    # hilt: thick line with a slightly larger collar
    hilt_w = max(3, round(s * 0.075))
    d.line([(x0, y0), (x1, y1)], fill=HILT_DK + (255,), width=hilt_w)
    d.line([(x0, y0), (x1, y1)], fill=HILT + (255,), width=max(1, hilt_w - 2))
    # emitter ring
    er = max(2, round(s * 0.055))
    d.ellipse([x1 - er, y1 - er, x1 + er, y1 + er],
              fill=SABER_DK + (255,))

    if lit < 0:
        return img

    # blade glow: layered alpha strokes
    core_w = max(2, round(s * 0.045))
    if lit > 0:
        halo_w = max(4, core_w * 5)
        mid_w = max(3, core_w * 2.6)
        a_halo = int(46 * lit)
        a_mid = int(130 * lit)
        a_core = int(235 * lit)
        _blade_line(d, (x1, y1), (x2, y2), SABER, halo_w, a_halo)
        _blade_line(d, (x1, y1), (x2, y2), SABER, mid_w, a_mid)
        _blade_line(d, (x1, y1), (x2, y2), SABER_LT, core_w, a_core)
        # rounded tip
        tr = core_w
        d.ellipse([x2 - tr, y2 - tr, x2 + tr, y2 + tr],
                  fill=SABER_LT + (a_core,))
    else:
        # muted blade: thin, desaturated
        d.line([(x1, y1), (x2, y2)], fill=(120, 132, 150, 200), width=core_w)

    return img


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for size in SIZES:
        draw_saber(size).save(os.path.join(OUT, f"icon-{size}.png"))
    draw_saber(32).save(os.path.join(OUT, "tray.png"))
    draw_saber(32, lit=1.35).save(os.path.join(OUT, "tray-rec.png"))
    draw_saber(32, lit=0.0).save(os.path.join(OUT, "tray-muted.png"))
    draw_saber(256).save(
        os.path.join(OUT, "app.ico"),
        sizes=[(s, s) for s in SIZES],
    )
    print(f"Assets written to {OUT}")


if __name__ == "__main__":
    main()
