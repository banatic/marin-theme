"""Pixel-exact SVG: every pixel of a picture drawn as vector marks.

Claude Desktop's backdrop takes SVG only, scrubbed of every picture a mod
could embed (image, feImage, foreignObject, CSS url(), data: fonts). So a
lossless picture is drawn pixel by pixel, one grey level at a time:

- short runs (1 to 3 pixels) as the vertices of an invisible path, each vertex
  carrying a 1x1 square marker in the level's colour. The path snakes through
  the level's pixels row by row, so a vertex costs about two characters;
- longer runs as 1px-high stroked segments ("m dx dy h n").

Levels are painted most-common first. A long run may cover pixels of levels
painted later, which shortens it; the later levels then overpaint them. With
crisp edges and whole-pixel placement, at 100% display scale the screen equals
the master bitmap value for value.

elements(master) -> the marks of one picture.
pack(pictures) -> SVG documents holding several placed pictures, each under the
131,072 character limit of one Svg, to be stacked in order.
encode(master, place) -> pack() for one picture at the bottom right.
decode(layers, w, h) -> the bitmap those documents paint, to prove it.
"""
import re

import numpy as np

LIMIT = 131072
SHORT = 3      # runs up to this long are drawn as marker points
CHUNK = 1200   # marks per <path>, so a path is small enough to pack whole
GUTTER = 14    # pixels kept clear at the right edge, where the scrollbar draws


def _runs(mask, free):
    """Runs covering every True of `mask`, allowed to cross `free` pixels."""
    out = []
    ok = mask | free
    width = mask.shape[1]
    for y in np.nonzero(mask.any(axis=1))[0]:
        need, can = mask[y], ok[y]
        xs = np.nonzero(need)[0]
        i, n = 0, len(xs)
        while i < n:
            x0 = int(xs[i])
            x1 = last = x0 + 1
            while x1 < width and can[x1]:
                if need[x1]:
                    last = x1 + 1
                x1 += 1
            out.append((int(y), x0, last))
            while i < n and xs[i] < last:
                i += 1
    return out


def _snake(pixels):
    """Order (y, x) pixels row by row, alternating direction, so steps stay short."""
    rows = {}
    for y, x in pixels:
        rows.setdefault(y, []).append(x)
    out = []
    for k, y in enumerate(sorted(rows)):
        xs = sorted(rows[y], reverse=k % 2 == 1)
        out.extend((y, x) for x in xs)
    return out


def _join(numbers):
    """Numbers side by side: a minus sign separates as well as a space."""
    out = []
    for i, n in enumerate(numbers):
        s = str(n)
        out.append(s if i == 0 or s.startswith("-") else " " + s)
    return "".join(out)


def _points(pixels):
    """Path data with one vertex per (y, x) pixel: h steps in a row, l between rows."""
    (y0, x0), rest = pixels[0], pixels[1:]
    out = [f"M{x0} {y0}"]
    px, py, cmd, args = x0, y0, None, []

    def flush():
        if args:
            out.append(cmd + _join(args))

    for y, x in rest:
        want = "h" if y == py else "l"
        if want != cmd:
            flush()
            cmd, args = want, []
        args.extend([x - px] if want == "h" else [x - px, y - py])
        px, py = x, y
    flush()
    return "".join(out)


def _segments(runs):
    """Path data stroking each (y, x0, x1) run."""
    out, px, py = [], 0, 0
    for k, (y, x0, x1) in enumerate(runs):
        out.append(f"M{x0} {y}h{x1 - x0}" if k == 0 else f"m{_join([x0 - px, y - py])}h{x1 - x0}")
        px, py = x1, y
    return "".join(out)


def _hex(g):
    return f"#{g:02x}{g:02x}{g:02x}"


def _chunks(items):
    return [items[i:i + CHUNK] for i in range(0, len(items), CHUNK)]


def elements(master):
    """master: HxWx2 uint8 (grey, alpha) -> [(kind, element text)] in paint order.

    kind "s" is stroked segments, "p" is marker points. Alpha-255 pixels are
    drawn exactly by grey level. Pixels with alpha 1 to 254 are the sticker's
    soft rim, drawn in their grey at their own opacity.
    """
    grey, alpha = master[..., 0].astype(np.int16), master[..., 1]
    solid = alpha == 255
    out = []

    levels, counts = np.unique(grey[solid], return_counts=True)
    pending = solid.copy()
    for level in (int(l) for l in levels[np.argsort(-counts)]):
        mask = solid & (grey == level)
        pending &= ~mask
        runs = _runs(mask, pending)
        long = [r for r in runs if r[2] - r[1] > SHORT]
        # A short run only needs its own pixels, never the ones it crossed.
        short = [(y, x) for y, x0, x1 in runs if x1 - x0 <= SHORT for x in range(x0, x1) if mask[y, x]]
        for part in _chunks(long):
            out.append(("s", f"<path stroke='{_hex(level)}' d='{_segments(part)}'/>"))
        for part in _chunks(_snake(short)):
            out.append(("p", f"<path stroke='{_hex(level)}' d='{_points(part)}'/>"))

    soft = (alpha > 0) & (alpha < 255)
    if soft.any():
        pairs = np.unique(np.stack([grey[soft], alpha[soft].astype(np.int16)], axis=1), axis=0)
        for g, a in pairs:
            ys, xs = np.nonzero(soft & (grey == g) & (alpha == a))
            for part in _chunks(_snake(list(zip(ys.tolist(), xs.tolist())))):
                out.append(("p", f"<path stroke='{_hex(int(g))}' opacity='{int(a) / 255:.4f}' d='{_points(part)}'/>"))
    return out


HEAD = (
    "<svg xmlns='http://www.w3.org/2000/svg' width='100%' height='100%'>"
    "<marker id='k' markerUnits='userSpaceOnUse' markerWidth='1' markerHeight='1' refX='.5' refY='.5'>"
    "<rect width='1' height='1' fill='context-stroke'/></marker>"
)
TAIL = "</svg>"
GROUP = {
    "s": "<g transform='translate(0 .5)' stroke-width='1'>",
    "p": "<g transform='translate(.5 .5)' stroke-width='0' marker-start='url(#k)' marker-mid='url(#k)' marker-end='url(#k)'>",
}


def pack(pictures):
    """pictures: [(place, dx, dy, elements, scale)] -> SVG documents to stack in order.

    Each picture is a nested <svg {place}> whose marks are shifted by (dx, dy)
    whole pixels and drawn `scale` times their size (1 is pixel for pixel). A picture that does not fit the document it started in
    carries on in the next. The engine re-serialises the source: each
    `<path .../>` comes out as `<path ...></path>`, 7 characters longer, and
    that is what the 131,072 character limit of one Svg counts.
    """
    room = LIMIT - len(HEAD) - len(TAIL) - 600
    docs, body = [], ""
    grown = 0
    for place, dx, dy, els, scale in pictures:
        grow = "" if scale == 1 else f" scale({scale})"
        wrap = f"<svg {place} overflow='visible'><g transform='translate({dx} {dy}){grow}' shape-rendering='crispEdges' fill='none'>"
        close = "</g></g></svg>"
        opened = None  # the mark group open inside this picture's wrapper, if any
        started = False
        for kind, el in els:
            lead = ("" if started else wrap) + ("" if opened == kind else ("</g>" if opened else "") + GROUP[kind])
            if len(body) + grown + len(lead) + len(el) + 7 + len(close) > room:
                if started:
                    body += close
                docs.append(HEAD + body + TAIL)
                body, grown = "", 0
                lead = wrap + GROUP[kind]
            body += lead + el
            grown += 7
            opened, started = kind, True
        if started:
            body += close
    if body:
        docs.append(HEAD + body + TAIL)
    return docs


def encode(master, place):
    """One picture, its bottom-right corner GUTTER pixels left of `place`."""
    h, w = master.shape[:2]
    return pack([(place, -w - GUTTER, -h, elements(master), 1)])


_NUMBER = re.compile(r"-?\d+")


def _marks(kind, data):
    """Yield (x, y, n) for each mark the path data paints."""
    x = y = 0
    for cmd, args in re.findall(r"([Mmhl])([-\d ]*)", data):
        v = [int(t) for t in _NUMBER.findall(args)]
        if cmd == "M":
            x, y = v
            if kind == "p":
                yield x, y, 1
        elif cmd == "m":
            x, y = x + v[0], y + v[1]
        elif cmd == "h":
            if kind == "s":
                yield x, y, v[0]
                x += v[0]
            else:
                for d in v:
                    x += d
                    yield x, y, 1
        else:
            for dx, dy in zip(v[::2], v[1::2]):
                x, y = x + dx, y + dy
                yield x, y, 1


def decode(layers, w, h):
    """Paint the layers back into (grey, alpha) float arrays, alpha in 0..1."""
    grey = np.zeros((h, w))
    alpha = np.zeros((h, w))
    for layer in layers:
        for shift, group in re.findall(r"<g transform='translate\((0|\.5) \.5\)'[^>]*>(.*?)</g>", layer):
            kind = "s" if shift == "0" else "p"
            for g, op, data in re.findall(r"<path stroke='#(..)....'(?: opacity='([\d.]+)')? d='([^']*)'/>", group):
                for x, y, n in _marks(kind, data):
                    grey[y, x:x + n] = int(g, 16)
                    alpha[y, x:x + n] = float(op) if op else 1.0
    return grey, alpha
