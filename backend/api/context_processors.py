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
from .models import Drop, Player, TopUpMessage, TopUpRequest
from .templatetags.skinrush_extras import img as _img
from .views import get_state

FEED_LIMIT = 30
# A drop must age this long before it enters the feed, so a player's own opening
# never shows in the strip before their reveal animation (~5.85s) finishes.
FEED_DELAY_SECONDS = 7
# The floor for the TOP strip: only genuinely valuable wins belong there.
TOP_MIN_PRICE = 1_000_000
TOP_LIMIT = 30
# The LIVE feed only carries drops worth at least this — cheap "junk" (charms,
# throwaway skins) is filtered out so the strip reads as real, quality wins.
FEED_MIN_PRICE = 1_000
# Players seen within this window count as "online now".
ONLINE_WINDOW_MIN = 15


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
    """The LIVE feed: newest real *quality* drops first (>= FEED_MIN_PRICE, so
    cheap junk is dropped), but only ones old enough that the opener has already
    seen their reveal (see FEED_DELAY)."""
    cutoff = timezone.now() - timedelta(seconds=FEED_DELAY_SECONDS)
    rows = (Drop.objects.select_related("item", "player")
            .filter(created_at__lte=cutoff, item__price__gte=FEED_MIN_PRICE)
            .order_by("-id")[:limit])
    return [_card(d) for d in rows]


def live_stats():
    """Real, honest activity numbers for the strip counter."""
    now = timezone.now()
    return {
        "online": Player.objects.filter(
            last_seen__gte=now - timedelta(minutes=ONLINE_WINDOW_MIN)).count(),
        "today": Drop.objects.filter(created_at__gte=now - timedelta(hours=24)).count(),
    }


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


def _chat_state(player):
    """The player's open top-up conversation for the nav badge, or None."""
    if not player:
        return None
    req = (player.topups.filter(status__in=TopUpRequest.OPEN_STATUSES)
           .order_by("-created_at").first())
    if not req:
        return None
    unread = req.messages.filter(
        sender=TopUpMessage.ADMIN, read_by_user=False).count()
    return {"active": True, "unread": unread, "status": req.status}


def site(request):
    lang = i18n.get_lang(request)
    player = current_player(request)
    if player:
        me = {
            "authenticated": True, "name": player.display_name,
            "photo": player.photo, "balance": player.balance,
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
        "CHAT": _chat_state(player),
        # LIVE drops strip (the TOP tab was removed; only LIVE remains).
        "TOP_DROPS": top_feed(),
        "LIVE_STATS": live_stats(),
    }
