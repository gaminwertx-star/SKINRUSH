"""Template helpers for the server-rendered SKINRUSH site."""
from django import template

register = template.Library()

STEAM_BASE = "https://community.steamstatic.com/economy/image/"


@register.filter
def fmt(n):
    """Thousands separated by spaces, matching the old JS ``fmt`` (ru-RU style)."""
    try:
        return f"{int(n):,}".replace(",", " ")
    except (TypeError, ValueError):
        return n


@register.filter
def wearabbr(w):
    """Wear name -> 2-letter badge (Factory New -> FN)."""
    table = {"Factory New": "FN", "Minimal Wear": "MW", "Field-Tested": "FT",
             "Well-Worn": "WW", "Battle-Scarred": "BS"}
    if not w:
        return ""
    return table.get(w) or "".join(p[0] for p in w.split())[:2].upper()


@register.filter
def img(val):
    """Resolve an image reference to a usable URL.

    - full URLs pass through unchanged
    - local project assets (``images/cases/X.png``) get a leading slash so they
      resolve from the site root on every page, not relative to the current path
    - anything else is treated as a Steam economy image hash and expanded to the
      Steam CDN URL (this is how the scraped skin images are stored)
    """
    if not val:
        return ""
    val = str(val)
    if val.startswith(("http://", "https://", "/")):
        return val
    if "images/" in val or val.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "/" + val
    return f"{STEAM_BASE}{val}/360fx360f"
