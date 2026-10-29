"""Draws the integration icon: a venetian blind with tilted slats and a sun.

Rendered at 2048 px and downsampled for smooth edges.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

N = 2048
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)

THEMES = {
    "": {  # light background
        "frame": (55, 71, 92),
        "slat": (74, 111, 165),
        "slat_edge": (52, 82, 128),
        "cord": (55, 71, 92),
        "sun": (245, 166, 35),
    },
    "dark_": {  # dark background
        "frame": (205, 214, 226),
        "slat": (126, 166, 222),
        "slat_edge": (96, 136, 196),
        "cord": (205, 214, 226),
        "sun": (255, 190, 70),
    },
}


def draw(theme):
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = N / 256  # design on a 256 grid

    # sun peeking out top right, behind the blind
    cx, cy, r = 196 * s, 58 * s, 34 * s
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=theme["sun"])
    for i in range(8):
        import math

        deg = i * 45 - 22.5
        if 90 < deg < 270:  # rays pointing into the blind would peek between the slats
            continue
        a = math.radians(deg)
        r1, r2 = 44 * s, 58 * s
        w = 9 * s
        x1, y1 = cx + r1 * math.cos(a), cy + r1 * math.sin(a)
        x2, y2 = cx + r2 * math.cos(a), cy + r2 * math.sin(a)
        d.line([x1, y1, x2, y2], fill=theme["sun"], width=int(w))
        for x, y in ((x1, y1), (x2, y2)):
            d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=theme["sun"])

    left, right = 28 * s, 196 * s

    # head box
    d.rounded_rectangle([left - 6 * s, 30 * s, right + 6 * s, 56 * s], radius=7 * s, fill=theme["frame"])

    # slats: tilted bands (parallelograms), slightly rounded via a thick outline
    top, gap, depth, tilt = 72 * s, 25 * s, 13 * s, 7 * s
    for i in range(7):
        y = top + i * gap
        poly = [(left, y), (right, y - tilt), (right, y - tilt + depth), (left, y + depth)]
        d.polygon(poly, fill=theme["slat"])
        d.line(poly + [poly[0]], fill=theme["slat"], width=int(4 * s), joint="curve")
        # lower edge darker for depth
        d.line([(left, y + depth), (right, y - tilt + depth)], fill=theme["slat_edge"], width=int(4 * s))

    # ladder cords
    bottom = top + 6 * gap + depth + 4 * s
    for x in (70 * s, 154 * s):
        d.line([(x, 56 * s), (x, bottom)], fill=theme["cord"], width=int(5 * s))

    # bottom rail
    d.rounded_rectangle([left - 4 * s, bottom, right + 4 * s, bottom + 14 * s], radius=6 * s, fill=theme["frame"])
    return img


for prefix, theme in THEMES.items():
    big = draw(theme)
    for size, suffix in ((256, ""), (512, "@2x")):
        big.resize((size, size), Image.LANCZOS).save(out / f"{prefix}icon{suffix}.png", optimize=True)

# preview sheet on light and dark background
sheet = Image.new("RGBA", (1100, 540), (255, 255, 255, 255))
ImageDraw.Draw(sheet).rectangle([550, 0, 1100, 540], fill=(28, 28, 30, 255))
sheet.alpha_composite(Image.open(out / "icon@2x.png"), (19, 14))
sheet.alpha_composite(Image.open(out / "dark_icon@2x.png"), (569, 14))
sheet.convert("RGB").save(out.parent / "icon_preview.png")
