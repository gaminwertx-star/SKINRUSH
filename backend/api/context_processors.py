"""Template context shared by every server-rendered page.

Puts the language catalog, the current player / balance and the live TOP DROPS
feed into every template so `base.html` can render the header, nav and footer
without any client-side JavaScript.
"""
from django.urls import reverse

from . import i18n
from .auth_telegram import current_player
from .models import Drop
from .templatetags.skinrush_extras import img as _img
from .views import get_state

# How many drops the marquee holds. It shows every drop now, not just rare ones —
# the point is the live feed of what real players are actually opening.
FEED_LIMIT = 30


def top_feed(limit=FEED_LIMIT):
    """The live TOP DROPS feed: newest real drops first, every rarity.

    Shared by this context processor (first paint) and the JSON endpoint the
    strip polls, so both always agree on shape and ordering.
    """
    rows = (Drop.objects.select_related("item", "player")
            .order_by("-id")[:limit])
    return [{
        "id": d.id,
        "name": d.item.name,
        "img": _img(d.item.image),
        "color": d.item.color or "#b0c3d9",
        "href": reverse("drop", args=[d.id]),
    } for d in rows]


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
    }
