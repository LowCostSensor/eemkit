"""Draw the eemkit logo and write every icon file made from it.

The logo is the contour plot of a fluorescence peak: four nested ellipses,
coloured from blue (low intensity) to yellow (the maximum), on a dark rounded
square. Its geometry is defined once below; this script writes

* ``eemkit.svg`` (the logo), ``eemkit.ico`` (Windows), ``eemkit.icns`` (macOS)
  and ``eemkit-<size>.png`` here, in ``packaging/icons``;
* the PNGs the application loads for its window, in ``src/eemkit/gui/icons``;
* ``logo.svg`` and ``logo-256.png`` for the documentation, in ``docs/img``.

It needs only Pillow (``pip install pillow``)::

    python packaging/icons/make_icons.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

#: The logo is drawn on a 64 x 64 grid.
GRID = 64
BACKGROUND = "#14243d"
CORNER = 14
ANGLE = -35  # degrees, rotation of the ellipses about the centre (SVG convention)
#: (centre x before the rotation, half-axis x, half-axis y, colour), outermost first.
ELLIPSES = ((32, 26, 15, "#2a6fb8"),
            (34, 18, 10.5, "#22a39a"),
            (36, 10.5, 6.5, "#9bd645"),
            (37, 4.5, 3, "#fde34a"))

PNG_SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
APP_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def svg() -> str:
    shapes = "\n".join(f'    <ellipse cx="{cx:g}" cy="32" rx="{rx:g}" ry="{ry:g}" fill="{c}"/>'
                       for cx, rx, ry, c in ELLIPSES)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {GRID} {GRID}">\n'
            f"  <title>eemkit</title>\n"
            f'  <rect width="{GRID}" height="{GRID}" rx="{CORNER}" fill="{BACKGROUND}"/>\n'
            f'  <g transform="rotate({ANGLE} 32 32)">\n{shapes}\n  </g>\n</svg>\n')


def draw(size: int) -> Image.Image:
    """The logo as an RGBA image of ``size`` pixels, drawn large and reduced (anti-aliasing)."""
    big = max(2048, size * 4)
    k = big / GRID
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, big - 1, big - 1), radius=CORNER * k, fill=BACKGROUND)
    a = math.radians(ANGLE)
    cos, sin = math.cos(a), math.sin(a)
    for cx, rx, ry, colour in ELLIPSES:
        points = []
        for i in range(720):
            t = 2 * math.pi * i / 720
            x, y = cx + rx * math.cos(t) - 32, ry * math.sin(t)
            points.append(((32 + x * cos - y * sin) * k, (32 + x * sin + y * cos) * k))
        d.polygon(points, fill=colour)
    return im.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    images = {s: draw(s) for s in PNG_SIZES}
    (HERE / "eemkit.svg").write_text(svg(), encoding="utf-8")
    for s, im in images.items():
        im.save(HERE / f"eemkit-{s}.png", optimize=True)
    images[256].save(HERE / "eemkit.ico", sizes=[(s, s) for s in ICO_SIZES],
                     append_images=[images[s] for s in ICO_SIZES if s != 256])
    images[1024].save(HERE / "eemkit.icns",
                      append_images=[images[s] for s in (16, 32, 64, 128, 256, 512)])
    app = ROOT / "src" / "eemkit" / "gui" / "icons"
    app.mkdir(exist_ok=True)
    for s in APP_SIZES:
        images[s].save(app / f"eemkit-{s}.png", optimize=True)
    docs = ROOT / "docs" / "img"
    (docs / "logo.svg").write_text(svg(), encoding="utf-8")
    images[256].save(docs / "logo-256.png", optimize=True)
    print("icons written to", HERE, app, docs, sep="\n  ")


if __name__ == "__main__":
    main()
