#!/usr/bin/env python3
"""Generate USDZ Forge's app icon: an isometric 'forged metal' cube on a dark
squircle. Renders a 1024px master and the full .iconset needed for macOS.

Run with the bundled interpreter (Pillow is already installed there):
  engine/python/bin/python3.14 packaging/make-icon.py
Then: iconutil -c icns packaging/AppIcon.iconset -o packaging/AppIcon.icns
"""
import math
import os
from PIL import Image, ImageDraw, ImageFilter

S = 1024
HERE = os.path.dirname(os.path.abspath(__file__))
ICONSET = os.path.join(HERE, "AppIcon.iconset")

# ---- palette ---------------------------------------------------------------
BG_TOP = (34, 30, 40)       # deep warm charcoal
BG_BOT = (14, 12, 16)
GLOW = (255, 120, 24)       # forge glow
FACE_TOP = (255, 196, 92)   # bright amber (lit top)
FACE_LEFT = (233, 108, 34)  # orange
FACE_RIGHT = (176, 66, 26)  # burnt orange (shadowed)
EDGE_HI = (255, 224, 160)   # warm highlight on top edges


def squircle_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def vertical_gradient(size, top, bottom):
    grad = Image.new("RGB", (1, size))
    px = grad.load()
    for y in range(size):
        t = y / (size - 1)
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return grad.resize((size, size))


def render():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # Background squircle with vertical gradient.
    bg = vertical_gradient(S, BG_TOP, BG_BOT).convert("RGBA")
    mask = squircle_mask(S, radius=int(S * 0.225))
    img.paste(bg, (0, 0), mask)

    # Warm glow behind the cube (sells the 'forge' heat).
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([S * 0.22, S * 0.30, S * 0.78, S * 0.86], fill=GLOW + (150,))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    img = Image.alpha_composite(img, Image.composite(
        glow, Image.new("RGBA", (S, S), (0, 0, 0, 0)), mask))

    # Isometric cube geometry.
    cx, cy, r = S * 0.5, S * 0.52, S * 0.30
    dx, dy = 0.86602540 * r, 0.5 * r
    top = (cx, cy - r)
    ur = (cx + dx, cy - dy)
    lr = (cx + dx, cy + dy)
    bot = (cx, cy + r)
    ll = (cx - dx, cy + dy)
    ul = (cx - dx, cy - dy)
    ctr = (cx, cy)

    d = ImageDraw.Draw(img)
    d.polygon([top, ur, ctr, ul], fill=FACE_TOP)     # top face
    d.polygon([ul, ctr, bot, ll], fill=FACE_LEFT)    # left face
    d.polygon([ur, lr, bot, ctr], fill=FACE_RIGHT)   # right face

    # Subtle bright highlight along the two upper silhouette edges, and the
    # real vertical front edge (center -> bottom) for crisp cube definition.
    w = int(S * 0.012)
    d.line([ul, top], fill=EDGE_HI, width=w)
    d.line([top, ur], fill=EDGE_HI, width=w)
    d.line([ctr, bot], fill=(120, 44, 18), width=max(2, w // 2))

    # Forge spark: a clean 4-point sparkle above the apex, with a soft halo.
    spark = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(spark)
    sx, sy = top[0] + S * 0.11, top[1] + S * 0.02
    R, rr = S * 0.05, S * 0.011
    star = [
        (sx, sy - R), (sx + rr, sy - rr), (sx + R, sy), (sx + rr, sy + rr),
        (sx, sy + R), (sx - rr, sy + rr), (sx - R, sy), (sx - rr, sy - rr),
    ]
    sd.polygon(star, fill=(255, 247, 228, 255))
    img = Image.alpha_composite(img, spark.filter(ImageFilter.GaussianBlur(16)))
    img = Image.alpha_composite(img, spark)

    # Keep everything inside the squircle.
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def main():
    master = render()
    os.makedirs(ICONSET, exist_ok=True)
    master.save(os.path.join(HERE, "icon_master_1024.png"))
    specs = [
        (16, "icon_16x16.png"), (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"), (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png"),
    ]
    for size, name in specs:
        master.resize((size, size), Image.LANCZOS).save(os.path.join(ICONSET, name))
    print("wrote", ICONSET)


if __name__ == "__main__":
    main()
