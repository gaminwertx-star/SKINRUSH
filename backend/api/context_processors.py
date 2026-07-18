"""Template context shared by every server-rendered page.

Puts the language catalog, the current player / balance and the live TOP DROPS
feed into every template so `base.html` can render the header, nav and footer
without any client-side JavaScript.
"""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from . import i18n
from .auth_telegram import current_player
from .models import Drop
from .templatetags.skinrush_extras import img as _img
from .views import get_state

FEED_LIMIT = 30
# A drop must age this long before it enters the feed, so a player's own opening
# never shows in the strip before their reveal animation (~5.85s) finishes.
FEED_DELAY_SECONDS = 7
# The floor for the TOP strip: only genuinely valuable wins belong there.
TOP_MIN_PRICE = 1_000_000
TOP_LIMIT = 30


def _card(d):
    return {
        "id": d.id,
        "name": d.item.name,
        "img": _img(d.item.image),
        "color": d.item.color or "#b0c3d9",
        "price": d.item.price,
        "href": reverse("drop", args=[d.id]),
    }


def top_feed(limit=FEED_LIMIT):
    """The LIVE feed: newest real drops first, every rarity, but only ones old
    enough that the opener has already seen their reveal (see FEED_DELAY)."""
    cutoff = timezone.now() - timedelta(seconds=FEED_DELAY_SECONDS)
    rows = (Drop.objects.select_related("item", "player")
            .filter(created_at__lte=cutoff).order_by("-id")[:limit])
    return [_card(d) for d in rows]


def top_expensive(limit=TOP_LIMIT):
    """The TOP strip: the most valuable wins (>= TOP_MIN_PRICE), dearest first.

    Distinct by skin name so the same trophy skin does not fill the row."""
    rows = (Drop.objects.select_related("item", "player")
            .filter(item__price__gte=TOP_MIN_PRICE).order_by("-item__price", "-id"))
    seen, out = set(), []
    for d in rows:
        if d.item.name in seen:
            continue
        seen.add(d.item.name)
        out.append(_card(d))
        if len(out) >= limit:
            break
    return out


def site(request):
    lang = i18n.get_lang(request)
    player = current_player(request)
    if player:
        me = {
            "authenticated": True, "name": player.display_name,
            "photo": player.photo_url, "balance": player.balance,
            "streak": player.streak, "invited": player.invited_count,
            "total_won": player.total_won,
        }
    else:
        st = get_state(request)
        me = {
            "authenticated": False, "name": "", "photo": "",
            "balance": st["balance"], "streak": st["streak"],
            "invited": st["invited"], "total_won": st["total_won"],
        }

    return {
        "S": i18n.strings_for(lang),
        "LANG": lang,
        "LANGS": [{"code": c, "name": i18n.STRINGS[c]["lang_name"]} for c in i18n.LANGS],
        "ME": me,
        "PLAYER": player,
        "TOP_DROPS": top_feed(),
        "TOP_EXPENSIVE": top_expensive(),
    }
