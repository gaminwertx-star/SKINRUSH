"""Server-side game logic for SKINRUSH (backed by the real cs-shot.pro data).

Draw odds and prices come straight from the seeded CaseItem rows, so the
outcome economics match the source exactly.
"""
import random
import re

from .models import CaseItem

# Wear -> float band, used only to show a realistic float on the reveal card.
WEAR_BANDS = {
    "Factory New": (0.00, 0.07), "Minimal Wear": (0.07, 0.15),
    "Field-Tested": (0.15, 0.38), "Well-Worn": (0.38, 0.45),
    "Battle-Scarred": (0.45, 1.00),
}


def wear_float(wear):
    band = WEAR_BANDS.get(wear)
    if not band:
        return "—"
    return f"{band[0] + random.random() * (band[1] - band[0]):.4f}"


def draw_item(items):
    """Weighted random draw of one CaseItem using its real drop chance."""
    total = sum(it.chance for it in items) or 1.0
    r = random.random() * total
    for it in items:
        r -= it.chance
        if r <= 0:
            return it
    return items[-1]


# ---------- Skin universe for the Upgrade game (deduped by name) ----------
_UNIVERSE = None


def get_universe():
    """One representative row per distinct skin (highest-priced wear), cached."""
    global _UNIVERSE
    if _UNIVERSE is None:
        best = {}
        for it in CaseItem.objects.all().only(
            "id", "name", "weapon", "finish", "wear", "price", "color", "image", "rarity"
        ):
            cur = best.get(it.name)
            if cur is None or it.price > cur.price:
                best[it.name] = it
        _UNIVERSE = sorted(best.values(), key=lambda it: it.price)
    return _UNIVERSE


# ---------- Shop catalog (one card per skin name, all wears priced) ----------
_CATALOG = None

_CAT_RIFLE = {"AK-47", "M4A4", "M4A1-S", "AWP", "SSG 08", "SG 553", "AUG",
              "FAMAS", "Galil AR", "G3SG1", "SCAR-20"}
_CAT_PISTOL = {"Desert Eagle", "Glock-18", "USP-S", "P2000", "P250",
               "Five-SeveN", "Tec-9", "CZ75-Auto", "Dual Berettas", "R8 Revolver"}
_CAT_SMG = {"MAC-10", "MP9", "MP7", "MP5-SD", "UMP-45", "P90", "PP-Bizon"}
_CAT_HEAVY = {"Nova", "XM1014", "MAG-7", "Sawed-Off", "M249", "Negev"}
_OTHER_RE = re.compile(
    r"Sticker|Capsule|Graffiti|Patch|Music Kit|Charm|Case|Package|Pin|Zeus|Souvenir|Sealed")


def base_weapon(weapon):
    w = re.sub(r"^StatTrak™\s*", "", weapon or "")
    return re.sub(r"^★\s*", "", w).strip()


def categorize(weapon):
    w = base_weapon(weapon)
    if w in _CAT_RIFLE:
        return "rifle"
    if w in _CAT_PISTOL:
        return "pistol"
    if w in _CAT_SMG:
        return "smg"
    if w in _CAT_HEAVY:
        return "heavy"
    if "Gloves" in w or "Hand Wraps" in w:
        return "gloves"
    if (weapon and "★" in weapon) or w.endswith("Knife") or w in {"Bayonet", "Karambit", "Shadow Daggers"}:
        return "knife"
    if _OTHER_RE.search(weapon or ""):
        return "other"
    return "agent"


def get_catalog():
    """One entry per skin name for the shop, cached. Each entry keeps the
    cheapest listing per wear so the shop can show a 'from' price and filter
    by condition. `image` is taken from the priciest wear (best art)."""
    global _CATALOG
    if _CATALOG is None:
        by = {}
        for it in CaseItem.objects.all().only(
            "id", "name", "weapon", "finish", "wear", "price", "color", "image", "rarity"
        ):
            e = by.get(it.name)
            if e is None:
                e = by[it.name] = {
                    "name": it.name, "weapon": it.weapon, "finish": it.finish,
                    "rarity": it.rarity, "color": it.color or "#b0c3d9",
                    "image": it.image, "_topprice": it.price, "wears": {},
                    "category": categorize(it.weapon),
                    "stattrak": "StatTrak™" in (it.weapon or ""),
                }
            if it.price > e["_topprice"]:
                e["_topprice"] = it.price
                e["image"] = it.image
            w = it.wear or ""
            cur = e["wears"].get(w)
            if cur is None or it.price < cur[0]:
                e["wears"][w] = (it.price, it.id)
        out = []
        for e in by.values():
            prices = [p for p, _ in e["wears"].values()]
            e["min_price"] = min(prices)
            e["max_price"] = max(prices)
            e["item_id"] = min(e["wears"].values(), key=lambda t: t[0])[1]
            e.pop("_topprice", None)
            out.append(e)
        _CATALOG = out
    return _CATALOG


def reset_cache():
    global _UNIVERSE, _CATALOG
    _UNIVERSE = None
    _CATALOG = None
