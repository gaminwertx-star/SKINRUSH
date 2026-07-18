"""Template helpers for the server-rendered SKINRUSH site."""
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

STEAM_BASE = "https://community.steamstatic.com/economy/image/"


# ---------------------------------------------------------------- icons
# One inline-SVG set instead of emoji: emoji render as somebody else's artwork
# — a different picture per platform, coloured in, and out of key with the rest
# of the UI. These are stroked paths on a 24-grid that take `currentColor` and
# size with the text around them, like the icons already in base.html.
ICONS = {
    "gift": '<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M12 8v13"/>'
            '<path d="M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7"/>'
            '<path d="M7.5 8a2.5 2.5 0 0 1 0-5C11 3 12 8 12 8"/>'
            '<path d="M16.5 8a2.5 2.5 0 0 0 0-5C13 3 12 8 12 8"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "arrow-up": '<path d="M12 19V5M5 12l7-7 7 7"/>',
    "arrow-right": '<path d="M5 12h14M12 5l7 7-7 7"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "cart": '<circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/>'
            '<path d="M2 2h2l2.7 12.4a2 2 0 0 0 2 1.6h9.8a2 2 0 0 0 1.9-1.6L22 7H5.1"/>',
    "box": '<path d="M21 8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/>'
           '<path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "tag": '<path d="M12.6 2.6A2 2 0 0 0 11.2 2H4a2 2 0 0 0-2 2v7.2a2 2 0 0 0 .6 1.4l8.7 8.7a2.4 2.4 0 0 0 3.4 0l6.6-6.6a2.4 2.4 0 0 0 0-3.4z"/>'
           '<circle cx="7.5" cy="7.5" r="1"/>',
    "dollar": '<path d="M12 2v20"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
    "trophy": '<path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/>'
              '<path d="M4 22h16"/><path d="M10 14.7V17c0 .6-.5 1-1 1.2C7.9 18.8 7 20.2 7 22"/>'
              '<path d="M14 14.7V17c0 .6.5 1 1 1.2 1.1.6 2 2 2 3.8"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/>',
    "hourglass": '<path d="M5 22h14M5 2h14"/>'
                 '<path d="M17 22v-4.2a2 2 0 0 0-.6-1.4L12 12l-4.4 4.4a2 2 0 0 0-.6 1.4V22"/>'
                 '<path d="M7 2v4.2a2 2 0 0 0 .6 1.4L12 12l4.4-4.4a2 2 0 0 0 .6-1.4V2"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>',
    "lock": '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "coins": '<circle cx="8" cy="8" r="6"/><path d="M18.1 10.4A6 6 0 1 1 10.3 18"/>'
             '<path d="M7 6h1v4"/><path d="m16.7 13.9.7.7-2.8 2.8"/>',
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "swords": '<path d="M14.5 17.5 3 6V3h3l11.5 11.5"/><path d="m13 19 6-6"/>'
              '<path d="m16 16 4 4"/><path d="m19 21 2-2"/>',
    "external": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/>'
                '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "alert": '<path d="M12 9v4"/><circle cx="12" cy="17" r="0.5" fill="currentColor"/>'
             '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
}


@register.simple_tag
def icon(name, cls=""):
    """Inline SVG by name: ``{% icon "gift" %}`` / ``{% icon "x" "big" %}``.

    Unknown names render nothing rather than a broken glyph.
    """
    path = ICONS.get(name)
    if not path:
        return ""
    css = f"ic {cls}".strip()
    return mark_safe(
        f'<svg class="{css}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{path}</svg>'
    )


@register.filter
def fmt(n):
    """Thousands separated by spaces, matching the old JS ``fmt`` (ru-RU style)."""
    try:
        return f"{int(n):,}".replace(",", " ")
    except (TypeError, ValueError):
        return n


@register.filter
def sub(a, b):
    """Subtract b from a (used for the 'need X more coins' hint)."""
    try:
        return int(a) - int(b)
    except (TypeError, ValueError):
        return ""


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
