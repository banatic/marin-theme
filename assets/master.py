"""master(path, height): the display-size bitmap a picture is drawn from.

The cut-out, tilted by `angle` degrees, scaled to `height` (Lanczos) and
flattened onto sticker-white paper with a white edge about twice `edge`
pixels wide whose outline is anti-aliased.
Returns HxWx2 uint8 (grey, alpha).
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

GREY = np.array([0.299, 0.587, 0.114], dtype=np.float32)


def load(path):
    im = Image.open(path)
    if "A" in im.getbands():
        return im.convert("RGBA")
    # No alpha (the nun): flood the white paper from the border.
    rgb = im.convert("RGB")
    pad = Image.new("RGB", (rgb.width + 4, rgb.height + 4), (255, 255, 255))
    pad.paste(rgb, (2, 2))
    key = (255, 0, 255)
    ImageDraw.floodfill(pad, (0, 0), key, thresh=36)
    outside = (np.array(pad)[2:-2, 2:-2] == np.array(key)).all(axis=-1)
    alpha = Image.fromarray(np.where(outside, 0, 255).astype(np.uint8))
    out = rgb.convert("RGBA")
    out.putalpha(alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8)))
    return out


SUPER = 4  # the sticker's outline is worked out at this many times the size


def master(path, height, edge=2, angle=0):
    im = load(path)
    if angle:
        # Tilted while still full size, so the tilt costs no sharpness.
        im = im.rotate(angle, Image.BICUBIC, expand=True)
    im = im.crop(im.getchannel("A").getbbox())
    w = round(im.width * height / im.height)
    pad = int(edge * 2) + 2
    size = (w + pad * 2, height + pad * 2)
    small = im.resize((w, height), Image.LANCZOS)
    canvas = Image.new("RGBA", size, (255, 255, 255, 0))
    canvas.paste(small, (pad, pad))
    a = np.array(canvas).astype(np.float32)
    al = a[..., 3] / 255.0
    grey = (a[..., :3] @ GREY) * al + 255.0 * (1 - al)

    # The paper: the cut-out grown by `edge` pixels, traced SUPER times larger
    # and averaged down, so its outline is anti-aliased rather than stepped.
    big = Image.new("L", (size[0] * SUPER, size[1] * SUPER), 0)
    shape = im.getchannel("A").resize((w * SUPER, height * SUPER), Image.LANCZOS).point(lambda v: 255 if v > 96 else 0)
    big.paste(shape, (pad * SUPER, pad * SUPER))
    # A blur and a low threshold grow the shape by about 1.9 * edge, round at the corners.
    grown = big.filter(ImageFilter.GaussianBlur(edge * SUPER)).point(lambda v: 255 if v > 8 else 0)
    cover = np.array(grown.resize(size, Image.BOX)).astype(np.float32)
    # Five steps of opacity keep the outline's marks few.
    alpha = np.where(cover >= 230, 255, np.round(cover / 51) * 51)
    return np.dstack([np.clip(grey.round(), 0, 255), alpha]).astype(np.uint8)
