"""Server-side game logic for SKINRUSH (backed by the real cs-shot.pro data).

Draw odds and prices come straight from the seeded CaseItem rows, so the
outcome economics match the source exactly.
"""
import random

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


def reset_cache():
    global _UNIVERSE
    _UNIVERSE = None
