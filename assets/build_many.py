"""Build the backdrop layers that scatter the Marin pictures.

Usage: build_many.py <source dir> <out dir>

The pictures are strewn over the whole window, each placed by a fraction of
the window's width and height, so they spread with it and some stay in view
whatever panels are open. Each is drawn pixel for pixel (see exact.py) from a
master of equal area, its greys gathered into LEVELS tones. Like stickers
stuck on by hand, each has a thick white edge and its own slight tilt.

Eight that fine do not fit the 262,144 characters a backdrop tree may hold. The
two places behind the chat column are seen through the app's frosted panel,
which blurs them anyway, so a picture there is drawn from a master half the
size in SOFT_LEVELS tones, each pixel twice as large: a fraction of the
characters, and the six in the clear margins keep all of theirs.

The source pictures are taken in name order.

Writes `many-R-K.svg` (rotation R, layer K: in rotation R, place i shows
picture (R + 3i) mod 8), `master-N.png` (what the screen shows for picture N
in a margin) and `many.json` (the layer count of each rotation).
"""
import glob
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exact import decode, elements, encode, pack  # noqa: E402
from master import master  # noqa: E402

src_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)

BUDGET = 246_000  # of 262,144: the rest is the ground layer and the tree itself
LEVELS = 16
SOFT_LEVELS = 8   # tones of a picture behind the frosted panel
SOFT_SCALE = 2    # and how many times larger its pixels are drawn
MAX_WIDTH = 190
EDGE = 3.5         # the white sticker edge comes out about twice this wide
# Each picture's tilt in degrees, anticlockwise: fixed, so a picture keeps its
# tilt as it moves from place to place.
TILTS = [-9, 7, -6, 11, -8, 6, 9, -7]
STEP = 3  # place i shows picture (rotation + STEP * i): neighbours differ, and all eight show
# Where each picture sits: (across, down) as fractions of the room the window
# leaves it, 0 at the left or top edge and 1 at the right or bottom; and
# whether the place is behind the chat column's frosted panel.
PLACES = [
    (0.16, 0.06, False), (0.93, 0.05, False),
    (0.23, 0.46, False), (0.56, 0.36, True), (0.97, 0.48, False),
    (0.15, 0.86, False), (0.50, 0.92, True), (0.92, 0.91, False),
]

paths = sorted(glob.glob(os.path.join(src_dir, "*.png")))
assert len(paths) == len(PLACES)
aspect = []  # height / width of each cut-out
assert len(TILTS) == len(paths)
for p, tilt in zip(paths, TILTS):
    m = master(p, 200, EDGE, tilt)
    aspect.append(m.shape[0] / m.shape[1])


def quantised(path, height, levels, tilt):
    """The master with its greys gathered into `levels` tones, chosen where its pixels are."""
    m = master(path, height, EDGE, tilt)
    tones = Image.fromarray(m[..., 0], "L").convert("RGB").quantize(levels, dither=Image.Dither.NONE, kmeans=3)
    grey = np.array(tones.convert("L"))
    grey[grey >= 250] = 255  # the paper stays pure white
    return np.dstack([grey, m[..., 1]])


def build(side):
    """Every picture at area side*side, capped to MAX_WIDTH: (master, marks, soft marks)."""
    out = []
    for p, a, tilt in zip(paths, aspect, TILTS):
        height = round(min(side * a ** 0.5, MAX_WIDTH * a))
        m = quantised(p, height, LEVELS, tilt)
        soft = quantised(p, round(height / SOFT_SCALE), SOFT_LEVELS, tilt)
        out.append((m, elements(m), elements(soft)))
    return out


def layers(pictures, turn):
    placed = []
    for i, (across, down, is_soft) in enumerate(PLACES):
        m, els, soft = pictures[(i * STEP + turn) % len(pictures)]
        h, w = m.shape[:2]
        marks, scale = (soft, SOFT_SCALE) if is_soft else (els, 1)
        placed.append((f"x='{across * 100:g}%' y='{down * 100:g}%'", -round(across * w), -round(down * h), marks, scale))
    return pack(placed)


def largest(pictures):
    # Every rotation must fit, and they differ: each draws three other pictures soft.
    return max(sum(map(len, layers(pictures, t))) for t in range(len(pictures)))


lo, hi, best = 120, 300, None
while hi - lo > 1:
    mid = (lo + hi) // 2
    pictures = build(mid)
    if largest(pictures) <= BUDGET:
        lo, best = mid, pictures
    else:
        hi = mid
pictures = best or build(lo)

for n, (m, els, _) in enumerate(pictures):
    h, w = m.shape[:2]
    grey, alpha = decode(encode(m, "x='0' y='0'"), w, h)
    seen = m[..., 1] > 0
    assert np.array_equal(grey[seen], m[..., 0][seen].astype(float)), "grey differs"
    assert np.allclose(alpha, m[..., 1] / 255, atol=1e-4), "alpha differs"
    Image.fromarray(m, "LA").save(os.path.join(out_dir, f"master-{n}.png"))
    print(f"#{n}: {w}x{h}, decode check passed", flush=True)

manifest = []
for turn in range(len(pictures)):
    docs = layers(pictures, turn)
    assert sum(map(len, docs)) <= BUDGET, "a rotation is over budget"
    for k, svg in enumerate(docs):
        open(os.path.join(out_dir, f"many-{turn}-{k}.svg"), "w", encoding="utf-8").write(svg)
    manifest.append(len(docs))
    print(f"rotation {turn}: {len(docs)} layers, {sum(map(len, docs))} chars", flush=True)
json.dump(manifest, open(os.path.join(out_dir, "many.json"), "w"))
