"""Procedural synthetic imagery. No real people are ever depicted."""
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageFont

W, H = 240, 360


def font(size, bold=False):
    names = ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", "arialbd.ttf" if bold else "arial.ttf",
             "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"]
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def person_card(p: dict, transparent=False) -> Image.Image:
    """p keys: skin, hair, hair_style, shirt, pattern, lower, lower_type, build, bag, bg."""
    mode = "RGBA" if transparent else "RGB"
    bg = (0, 0, 0, 0) if transparent else tuple(p.get("bg", (228, 230, 234)))
    im = Image.new(mode, (W, H), bg)
    d = ImageDraw.Draw(im)
    b = p.get("build", 1.0)
    cx = 120
    skin, shirt, lower = tuple(p["skin"]), tuple(p["shirt"]), tuple(p["lower"])
    if not transparent:
        d.ellipse((cx - 60, 330, cx + 60, 348), fill=tuple(max(0, c - 30) for c in bg))
    # legs / lower garment
    lt = p.get("lower_type", "trousers")
    if lt == "saree":
        d.polygon([(cx - 40 * b, 150), (cx + 40 * b, 150), (cx + 52 * b, 330), (cx - 52 * b, 330)], fill=lower)
        d.polygon([(cx - 40 * b, 110), (cx - 10, 110), (cx + 40 * b, 215), (cx + 20, 215)], fill=lower)
    elif lt == "shorts":
        d.rectangle((cx - 36 * b, 212, cx + 36 * b, 262), fill=lower)
        d.rectangle((cx - 30 * b, 262, cx - 6, 325), fill=skin)
        d.rectangle((cx + 6, 262, cx + 30 * b, 325), fill=skin)
    else:
        d.rectangle((cx - 36 * b, 212, cx - 3, 325), fill=lower)
        d.rectangle((cx + 3, 212, cx + 36 * b, 325), fill=lower)
    d.rectangle((cx - 38 * b, 322, cx - 3, 334), fill=(40, 35, 30))
    d.rectangle((cx + 3, 322, cx + 38 * b, 334), fill=(40, 35, 30))
    # torso
    if lt != "saree":
        d.polygon([(cx - 46 * b, 112), (cx + 46 * b, 112), (cx + 38 * b, 218), (cx - 38 * b, 218)], fill=shirt)
    else:
        d.polygon([(cx - 40 * b, 112), (cx + 40 * b, 112), (cx + 36 * b, 150), (cx - 36 * b, 150)], fill=shirt)
    pat = p.get("pattern", "plain")
    if pat in ("checked", "striped") and lt != "saree":
        dark = tuple(max(0, c - 70) for c in shirt)
        for x in range(int(cx - 44 * b), int(cx + 44 * b), 12):
            d.line((x, 114, x, 216), fill=dark, width=3)
        if pat == "checked":
            for y in range(118, 216, 12):
                d.line((cx - 42 * b, y, cx + 42 * b, y), fill=dark, width=3)
    # arms
    d.polygon([(cx - 46 * b, 114), (cx - 60 * b, 120), (cx - 66 * b, 205), (cx - 50 * b, 205)], fill=shirt)
    d.polygon([(cx + 46 * b, 114), (cx + 60 * b, 120), (cx + 66 * b, 205), (cx + 50 * b, 205)], fill=shirt)
    d.ellipse((cx - 70 * b, 200, cx - 48 * b, 222), fill=skin)
    d.ellipse((cx + 48 * b, 200, cx + 70 * b, 222), fill=skin)
    # neck + head
    d.rectangle((cx - 10, 92, cx + 10, 114), fill=skin)
    hair = tuple(p["hair"])
    hs = p.get("hair_style", "short")
    if hs == "long":
        d.rectangle((cx - 32, 50, cx + 32, 128), fill=hair)
    d.ellipse((cx - 27, 42, cx + 27, 100), fill=skin)
    if hs in ("short", "long"):
        d.chord((cx - 29, 36, cx + 29, 84), 180, 360, fill=hair)
    elif hs == "cap":
        d.chord((cx - 30, 34, cx + 30, 80), 180, 360, fill=tuple(p.get("cap", (180, 30, 30))))
        d.rectangle((cx - 2, 56, cx + 40, 62), fill=tuple(p.get("cap", (180, 30, 30))))
    elif hs == "bun":
        d.chord((cx - 29, 38, cx + 29, 82), 180, 360, fill=hair)
        d.ellipse((cx - 12, 24, cx + 12, 46), fill=hair)
    d.ellipse((cx - 13, 66, cx - 7, 72), fill=(30, 25, 20))
    d.ellipse((cx + 7, 66, cx + 13, 72), fill=(30, 25, 20))
    d.line((cx - 8, 86, cx + 8, 86), fill=(120, 60, 50), width=2)
    if p.get("bag"):
        bc = tuple(p["bag"])
        d.line((cx - 40 * b, 114, cx + 40 * b, 200), fill=bc, width=5)
        d.rectangle((cx + 36 * b, 190, cx + 64 * b, 228), fill=bc)
    if not transparent:
        d.text((6, H - 16), "SYNTHETIC", fill=(150, 150, 150), font=font(10))
    return im


def lowlight(im, factor=0.3, seed=0):
    im = ImageEnhance.Brightness(im).enhance(factor)
    arr = np.asarray(im).astype(np.float32)
    arr += np.random.default_rng(seed).normal(0, 9, arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def blurry(im, r=4):
    return im.filter(ImageFilter.GaussianBlur(r))


def side_angle(im):
    w, h = im.size
    im = im.transform((w, h), Image.AFFINE, (1, 0.18, -30, 0, 1, 0), fillcolor=im.getpixel((2, 2)))
    return im.crop((10, 0, w - 10, h)).resize((w, h))


def document(title: str, lines: list, quality="good", seed=1) -> Image.Image:
    im = Image.new("RGB", (900, 120 + 62 * len(lines) + 80), (250, 248, 240))
    d = ImageDraw.Draw(im)
    d.rectangle((20, 20, 880, im.height - 20), outline=(60, 60, 60), width=3)
    d.text((50, 45), title, fill=(20, 20, 20), font=font(30, True))
    d.line((40, 100, 860, 100), fill=(60, 60, 60), width=2)
    y = 125
    for label, value in lines:
        d.text((50, y), f"{label}:", fill=(40, 40, 40), font=font(26, True))
        d.text((360, y), value, fill=(10, 10, 60), font=font(26))
        d.line((355, y + 36, 860, y + 36), fill=(180, 180, 180), width=1)
        y += 62
    d.text((50, im.height - 60), "SYNTHETIC DEMO DOCUMENT", fill=(160, 160, 160), font=font(16))
    if quality == "poor":
        im = im.rotate(2.5, expand=False, fillcolor=(240, 240, 235))
        im = im.filter(ImageFilter.GaussianBlur(1.6))
        im = ImageEnhance.Contrast(im).enhance(0.55)
        arr = np.asarray(im).astype(np.float32)
        arr += np.random.default_rng(seed).normal(0, 14, arr.shape)
        im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        d = ImageDraw.Draw(im)
        d.rectangle((500, 300, 900, 520), fill=(235, 232, 225))  # torn / missing section
    return im
