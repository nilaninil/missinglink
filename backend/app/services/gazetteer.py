"""Offline Chennai locality gazetteer. No geocoding API is ever called."""
import math
import re

LOCALITIES = {
    "Anna Nagar": (13.0850, 80.2101), "Koyambedu": (13.0694, 80.1948),
    "Kilpauk": (13.0827, 80.2419), "Egmore": (13.0732, 80.2609),
    "T. Nagar": (13.0418, 80.2341), "Vadapalani": (13.0500, 80.2121),
    "Aminjikarai": (13.0732, 80.2238), "Chetpet": (13.0714, 80.2417),
    "Villivakkam": (13.1082, 80.2064), "Mylapore": (13.0339, 80.2619),
    "Adyar": (13.0012, 80.2565), "Guindy": (13.0067, 80.2206),
    "Tambaram": (12.9249, 80.1000), "Velachery": (12.9815, 80.2180),
    "Perambur": (13.1210, 80.2330), "Royapettah": (13.0540, 80.2640),
    "Nungambakkam": (13.0569, 80.2425), "Ashok Nagar": (13.0370, 80.2120),
    "KK Nagar": (13.0410, 80.1990), "Porur": (13.0359, 80.1567),
    "Saidapet": (13.0213, 80.2231), "Central": (13.0827, 80.2757),
    "Tondiarpet": (13.1260, 80.2880), "Ambattur": (13.1143, 80.1548),
    "Mogappair": (13.0837, 80.1750),
}
ALIASES = {
    "kilpauk gh": "Kilpauk", "govt hospital kilpauk": "Kilpauk", "government hospital kilpauk": "Kilpauk",
    "kmc": "Kilpauk", "anna nagar 2nd avenue": "Anna Nagar", "anna nagar west": "Anna Nagar",
    "anna nagar east": "Anna Nagar", "annanagar": "Anna Nagar", "tnagar": "T. Nagar", "t nagar": "T. Nagar",
    "chennai central": "Central", "central station": "Central", "cmbt": "Koyambedu",
    "koyambedu bus stand": "Koyambedu", "kk nagar": "KK Nagar", "k.k. nagar": "KK Nagar",
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).strip()


def resolve(name):
    """Return canonical locality name, or None if unknown (never raises)."""
    if not name:
        return None
    n = _norm(str(name))
    n = re.sub(r"\s+", " ", n)
    for alias, canon in sorted(ALIASES.items(), key=lambda kv: -len(kv[0])):
        if _norm(alias) in n:
            return canon
    for canon in sorted(LOCALITIES, key=len, reverse=True):
        if _norm(canon).replace(" ", "") in n.replace(" ", ""):
            return canon
    return None


def coords(name):
    c = resolve(name)
    return LOCALITIES.get(c) if c else None


def distance_km(a, b):
    ca, cb = coords(a), coords(b)
    if not ca or not cb:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (*ca, *cb))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def find_in_text(text: str):
    return resolve(text)
