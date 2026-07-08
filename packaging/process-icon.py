#!/usr/bin/env python3
"""Turn a raw AI-generated icon PNG into a clean macOS iconset.

Masks the squircle so the corners become transparent (AI icons ship with
near-black corners that would render as black triangles in the Dock), then
emits the full AppIcon.iconset.

Usage: python process-icon.py <source.png> [radius_fraction]
"""
import os
import sys
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ICONSET = os.path.join(HERE, "AppIcon.iconset")

src = sys.argv[1]
radius_frac = float(sys.argv[2]) if len(sys.argv) > 2 else 0.185

img = Image.open(src).convert("RGBA")
W, H = img.size
print("source size:", W, H)

# Detect the squircle's bounding box: pixels brighter than near-black.
gray = img.convert("L")
bbox = gray.point(lambda p: 255 if p > 24 else 0).getbbox()
print("content bbox:", bbox)
if bbox is None:
    bbox = (0, 0, W, H)

x0, y0, x1, y1 = bbox
radius = int((x1 - x0) * radius_frac)

mask = Image.new("L", (W, H), 0)
ImageDraw.Draw(mask).rounded_rectangle([x0, y0, x1 - 1, y1 - 1], radius=radius, fill=255)
out = img.copy()
out.putalpha(mask)

# Crop to the squircle bbox so it's centered / full-bleed, then square it.
out = out.crop(bbox)
side = max(out.size)
square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
square.paste(out, ((side - out.size[0]) // 2, (side - out.size[1]) // 2))

master = square.resize((1024, 1024), Image.LANCZOS)
master.save(os.path.join(HERE, "icon_master_1024.png"))
square.resize((512, 512), Image.LANCZOS).save(
    os.path.join(HERE, "icon_preview_512.png"))

os.makedirs(ICONSET, exist_ok=True)
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
