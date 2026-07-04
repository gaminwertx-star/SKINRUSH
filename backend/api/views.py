"""API views for SKINRUSH.

Every case serves its own real skins with the source's real drop chance and
price. The draw is weighted by those real chances on the server.
"""
import random

from rest_framework import viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from . import game, i18n
from .models import Case, CaseItem, Drop
from .serializers import CaseSerializer, DropSerializer

TOP_RARITIES = ["Covert", "Extraordinary", "Classified", "Exceptional",
                "Master", "Superior", "Distinguished", "Exotic", "Remarkable"]

DEFAULT_STATE = {"balance": 12540, "streak": 3, "invited": 12, "total_won": 1250}


# ---------- payload helpers ----------
def item_payload(it, chance=None):
    """Serialize a CaseItem for the front-end."""
    return {
        "id": it.id,
        "name": it.name,
        "weapon": it.weapon,
        "finish": it.finish,
        "wear": it.wear,
        "tier_label": it.rarity,
        "color": it.color or "#b0c3d9",
        "img": it.image,
        "price": it.price,
        "chance": it.chance if chance is None else chance,
    }


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_state(request):
    return {**DEFAULT_STATE, **request.session.get("state", {})}


def save_state(request, state):
    request.session["state"] = state
    request.session.modified = True


# ---------- catalog ----------
class CaseViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/cases/ with ?q=&min=&max= search, plus contents/ and open/."""

    queryset = Case.objects.all()
    serializer_class = CaseSerializer
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("q"):
            qs = qs.filter(name__icontains=p["q"])
        if p.get("min"):
            qs = qs.filter(price__gte=p["min"])
        if p.get("max"):
            qs = qs.filter(price__lte=p["max"])
        return qs

    @action(detail=True, methods=["get"])
    def contents(self, request, pk=None):
        """Real items of a case, rarest (lowest chance) first — as on the source."""
        case = self.get_object()
        items = list(case.items.all())
        items.sort(key=lambda it: (it.chance, -it.price))
        data = [{"idx": i, "chance": it.chance, "skin": item_payload(it)}
                for i, it in enumerate(items)]
        return Response({"count": len(data), "items": data})

    @action(detail=True, methods=["post"])
    def open(self, request, pk=None):
        """Weighted draw by real chance. Records a Drop, returns the won skin."""
        case = self.get_object()
        items = list(case.items.all())
        if not items:
            return Response({"error": "Bo'sh keys"}, status=400)
        winner = game.draw_item(items)
        Drop.objects.create(case=case, item=winner)
        Case.objects.filter(pk=case.pk).update(opens=case.opens + 1)

        reel = [game.draw_item(items) for _ in range(60)]
        reel[50] = winner

        payload = item_payload(winner)
        payload["wear"] = {"name": winner.wear or "—", "float": game.wear_float(winner.wear)}
        return Response({
            "case": {"id": case.id, "name": case.name},
            "winner": payload,
            "reel": [item_payload(it) for it in reel],
            "winner_index": 50,
        })


# ---------- feeds & stats ----------
@api_view(["GET"])
def top_drops(request):
    qs = (Drop.objects.filter(item__rarity__in=TOP_RARITIES)
          .select_related("item", "case")[:40])
    return Response(DropSerializer(qs, many=True).data)


@api_view(["GET"])
def stats(request):
    return Response({
        "keyslar": Case.objects.count(),
        "skinlar": CaseItem.objects.values("name").distinct().count(),
        "janglar": Drop.objects.count(),
        "online": random.randint(900, 2200),
    })


@api_view(["GET"])
def me(request):
    return Response(get_state(request))


# ---------- i18n ----------
@api_view(["GET"])
def i18n_strings(request):
    lang = i18n.get_lang(request)
    return Response({
        "lang": lang,
        "langs": [{"code": c, "name": i18n.STRINGS[c]["lang_name"]} for c in i18n.LANGS],
        "strings": i18n.strings_for(lang),
    })


@api_view(["POST"])
def set_lang(request):
    lang = request.data.get("lang")
    if lang in i18n.STRINGS:
        request.session["lang"] = lang
        request.session.modified = True
    lang = i18n.get_lang(request)
    return Response({"lang": lang, "strings": i18n.strings_for(lang)})


@api_view(["POST"])
def sell(request):
    item = CaseItem.objects.filter(pk=_int(request.data.get("skin_id"))).first()
    if item is None:
        return Response({"error": "Skin topilmadi"}, status=400)
    state = get_state(request)
    state["balance"] += item.price
    state["total_won"] += item.price
    save_state(request, state)
    return Response({"sold": item.price, "balance": state["balance"],
                     "total_won": state["total_won"]})


# ---------- daily reward + tasks ----------
DAILY_DAYS = [
    (1, 10, "claimed"), (2, 25, "claimed"), (3, 50, "active"), (4, 75, "locked"),
    (5, 100, "locked"), (6, 150, "locked"), (7, 250, "special"), (8, 300, "locked"),
    (9, 400, "locked"), (10, 500, "locked"), (11, 650, "locked"), (12, 800, "locked"),
    (13, 1000, "locked"), (14, 1500, "special"),
]
DAILY_TASKS = [
    {"icon": "globe", "key": "task_login", "reward": 5},
    {"icon": "user", "key": "task_profile", "reward": 15},
    {"icon": "send", "key": "task_telegram", "reward": 20},
    {"icon": "users", "key": "task_invite", "reward": 50},
]
DAILY_TIMER_SECONDS = 15 * 3600 + 47 * 60 + 32
DAILY_ACTIVE_REWARD = 50


def _daily_days(claimed):
    days = []
    for d, r, state in DAILY_DAYS:
        if claimed and state == "active":
            state = "claimed"
        days.append({"d": d, "r": r, "state": state})
    return days


def _daily_tasks(lang):
    return [{"icon": t["icon"], "label": i18n.t(lang, t["key"]), "reward": t["reward"]}
            for t in DAILY_TASKS]


@api_view(["GET"])
def daily(request):
    claimed = request.session.get("daily_claimed", False)
    return Response({
        "days": _daily_days(claimed),
        "tasks": _daily_tasks(i18n.get_lang(request)),
        "timer_seconds": DAILY_TIMER_SECONDS,
        "claimed": claimed,
    })


@api_view(["POST"])
def daily_claim(request):
    if request.session.get("daily_claimed", False):
        return Response({"claimed": True, "reward": 0, "balance": get_state(request)["balance"]})
    request.session["daily_claimed"] = True
    state = get_state(request)
    state["balance"] += DAILY_ACTIVE_REWARD
    save_state(request, state)
    return Response({"claimed": True, "reward": DAILY_ACTIVE_REWARD,
                     "balance": state["balance"], "days": _daily_days(True)})


# ---------- upgrade ----------
UPGRADE_EDGE = 0.9


def _universe_by_id():
    return {it.id: it for it in game.get_universe()}


def _seed_inventory(request):
    universe = game.get_universe()
    pool = [it for it in universe if 1000 <= it.price <= 60000] or universe
    picks = random.sample(pool, min(8, len(pool)))
    inventory = [{"uid": i + 1, "skin_id": it.id, "value": it.price}
                 for i, it in enumerate(picks)]
    inventory.sort(key=lambda x: x["value"])
    request.session["upg_inv"] = inventory
    request.session["upg_uid"] = len(inventory) + 1
    request.session.modified = True
    return inventory


def _inventory(request):
    if "upg_inv" not in request.session:
        return _seed_inventory(request)
    return request.session["upg_inv"]


def _inv_payload(inventory, byid):
    out = []
    for row in inventory:
        it = byid.get(row["skin_id"]) or CaseItem.objects.filter(pk=row["skin_id"]).first()
        if it:
            out.append({"uid": row["uid"], "value": row["value"], "skin": item_payload(it)})
    return out


@api_view(["GET"])
def upgrade_inventory(request):
    return Response({"inventory": _inv_payload(_inventory(request), _universe_by_id())})


@api_view(["GET"])
def upgrade_targets(request):
    q = (request.query_params.get("q") or "").strip().lower()
    universe = sorted(game.get_universe(), key=lambda it: -it.price)
    if q:
        universe = [it for it in universe if q in it.name.lower()]
    universe = universe[:60]
    return Response({"targets": [{"skin": item_payload(it), "value": it.price}
                                 for it in universe]})


def _odds(from_value, to_value):
    chance = min(0.9, (from_value / to_value) * UPGRADE_EDGE)
    return chance, to_value / from_value


@api_view(["POST"])
def upgrade_compute(request):
    inventory = _inventory(request)
    from_item = next((r for r in inventory if r["uid"] == _int(request.data.get("from_uid"))), None)
    to = CaseItem.objects.filter(pk=_int(request.data.get("to_skin_id"))).first()
    if not from_item or not to or to.price <= from_item["value"]:
        return Response({"valid": False})
    chance, mult = _odds(from_item["value"], to.price)
    return Response({"valid": True, "chance": chance, "mult": mult})


@api_view(["POST"])
def upgrade_play(request):
    inventory = _inventory(request)
    from_uid = _int(request.data.get("from_uid"))
    from_item = next((r for r in inventory if r["uid"] == from_uid), None)
    to = CaseItem.objects.filter(pk=_int(request.data.get("to_skin_id"))).first()
    if not from_item or not to or to.price <= from_item["value"]:
        return Response({"error": "Nishon qimmatroq bo'lishi kerak"}, status=400)

    chance, _ = _odds(from_item["value"], to.price)
    won = random.random() < chance
    chance_deg = chance * 360
    if won:
        landing = random.random() * max(2, chance_deg - 4) + 2
    else:
        landing = chance_deg + 3 + random.random() * max(2, 360 - chance_deg - 6)

    inventory = [r for r in inventory if r["uid"] != from_uid]
    if won:
        uid = request.session.get("upg_uid", len(inventory) + 1)
        inventory.append({"uid": uid, "skin_id": to.id, "value": to.price})
        request.session["upg_uid"] = uid + 1
    inventory.sort(key=lambda x: x["value"])
    request.session["upg_inv"] = inventory
    request.session.modified = True

    return Response({
        "won": won, "chance": chance, "landing_deg": landing,
        "target": {"skin": item_payload(to), "value": to.price},
        "inventory": _inv_payload(inventory, _universe_by_id()),
    })
