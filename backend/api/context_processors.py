"""Template context shared by every server-rendered page.

Puts the language catalog, the current player / balance and the live TOP DROPS
feed into every template so `base.html` can render the header, nav and footer
without any client-side JavaScript.
"""
from . import i18n
from .auth_telegram import current_player
from .models import Drop
from .views import TOP_RARITIES, get_state


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

    tops = (Drop.objects.filter(item__rarity__in=TOP_RARITIES)
            .select_related("item", "case")[:20])
    top_drops = [{
        "name": d.item.name, "img": d.item.image, "price": d.item.price,
        "color": d.item.color or "#b0c3d9", "case": d.case.name,
    } for d in tops]

    return {
        "S": i18n.strings_for(lang),
        "LANG": lang,
        "LANGS": [{"code": c, "name": i18n.STRINGS[c]["lang_name"]} for c in i18n.LANGS],
        "ME": me,
        "PLAYER": player,
        "TOP_DROPS": top_drops,
    }
