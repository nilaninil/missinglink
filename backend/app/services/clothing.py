"""Normalise free-text clothing into (category, garment, colour) items."""
import re

COLOR_SYN = {
    "navy": "blue", "sky": "blue", "skyblue": "blue", "royal": "blue", "denim": "blue", "blue": "blue",
    "black": "black", "white": "white", "cream": "white", "offwhite": "white",
    "red": "red", "maroon": "red", "crimson": "red", "green": "green", "olive": "green",
    "yellow": "yellow", "mustard": "yellow", "grey": "grey", "gray": "grey", "ash": "grey",
    "brown": "brown", "khaki": "brown", "beige": "brown", "tan": "brown",
    "pink": "pink", "orange": "orange", "purple": "purple", "violet": "purple",
    "dark": "dark", "light": "light",
}
UNCLEAR = ("unclear", "unknown", "not clear", "unsure")
GARMENTS = {
    "t-shirt": ("upper", "t-shirt"), "tshirt": ("upper", "t-shirt"), "tee": ("upper", "t-shirt"),
    "shirt": ("upper", "shirt"), "kurta": ("upper", "kurta"), "top": ("upper", "top"),
    "jacket": ("upper", "jacket"), "hoodie": ("upper", "jacket"), "sweater": ("upper", "jacket"),
    "blouse": ("upper", "top"),
    "trousers": ("lower", "trousers"), "pants": ("lower", "trousers"), "pant": ("lower", "trousers"),
    "jeans": ("lower", "jeans"), "shorts": ("lower", "shorts"), "skirt": ("lower", "skirt"),
    "lungi": ("lower", "lungi"), "dhoti": ("lower", "lungi"), "leggings": ("lower", "trousers"),
    "saree": ("full", "saree"), "sari": ("full", "saree"), "dress": ("full", "dress"),
    "uniform": ("full", "uniform"), "raincoat": ("upper", "jacket"),
}
DARK_FAMILY = {"black", "blue", "grey", "brown"}
LIGHT_FAMILY = {"white", "yellow", "pink", "grey"}


def parse(text):
    """Return list of dicts {cat, garment, color|None}. One item per category (first wins,
    but a later item with a known colour replaces an earlier colourless one)."""
    if not text:
        return []
    t = text.lower().replace("t shirt", "t-shirt")
    items = []
    # split on separators so colours don't leak across garments
    for chunk in re.split(r"[,;/&+]| and | with ", t):
        unclear = any(u in chunk for u in UNCLEAR)
        words = re.findall(r"[a-z\-]+", chunk)
        color = None
        for w in words:
            if w in COLOR_SYN and color is None:
                color = COLOR_SYN[w]
        for w in words:
            if w in GARMENTS:
                cat, g = GARMENTS[w]
                items.append({"cat": cat, "garment": g, "color": None if unclear else color})
                break
    merged = {}
    for it in items:
        cur = merged.get(it["cat"])
        if cur is None or (cur["color"] is None and it["color"] is not None):
            merged[it["cat"]] = it
    return list(merged.values())


def merge(a: list, b: list) -> list:
    """Union of items; known colour beats unknown."""
    out = {i["cat"]: dict(i) for i in a}
    for it in b:
        cur = out.get(it["cat"])
        if cur is None or (cur["color"] is None and it["color"]):
            out[it["cat"]] = dict(it)
    return list(out.values())


def color_sim(a, b):
    if a is None or b is None:
        return 0.5
    if a == b:
        return 1.0
    pair = {a, b}
    if "dark" in pair:
        other = (pair - {"dark"}).pop()
        return 0.6 if other in DARK_FAMILY else 0.1
    if "light" in pair:
        other = (pair - {"light"}).pop()
        return 0.6 if other in LIGHT_FAMILY else 0.1
    if pair <= {"black", "grey"} or pair <= {"blue", "grey"}:
        return 0.3
    return 0.0


def garment_sim(a, b):
    if a == b:
        return 1.0
    if {a, b} <= {"trousers", "jeans"}:
        return 0.8
    if {a, b} <= {"shirt", "t-shirt", "top", "kurta"}:
        return 0.7
    return 0.4


def describe(items):
    return ", ".join(f"{i['color'] or 'unclear-colour'} {i['garment']}" for i in items) or "—"
