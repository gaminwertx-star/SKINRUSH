"""API views for SKINRUSH.

Every case serves its own real skins with the source's real drop chance and
price. The draw is weighted by those real chances on the server.
"""
import random
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from . import game, i18n
from .auth_telegram import current_player
from .models import Battle, Case, CaseItem, Drop, OpenRecord, Player
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
        """Real open: charge the case price (real balance), draw by real chance.
        The won skin is NOT added to the inventory yet — the player then chooses
        to keep it (claim/ = "Olish") or sell it (sell/)."""
        case = self.get_object()
        items = list(case.items.all())
        if not items:
            return Response({"error": "Bo'sh keys"}, status=400)

        price = case.price
        player = current_player(request)
        # --- charge the price against the real balance (player or guest session) ---
        if player:
            if player.balance < price:
                return Response({"error": "Balans yetmadi", "code": "insufficient"}, status=400)
            player.balance -= price
            player.save(update_fields=["balance", "last_seen"])
            balance = player.balance
        else:
            state = get_state(request)
            if state["balance"] < price:
                return Response({"error": "Balans yetmadi", "code": "insufficient"}, status=400)
            state["balance"] -= price
            save_state(request, state)
            balance = state["balance"]

        winner = game.draw_item(items)
        Drop.objects.create(case=case, item=winner)
        Case.objects.filter(pk=case.pk).update(opens=case.opens + 1)

        # Remember this drop so claim/ or sell/ can only act on a real opening.
        request.session["pending_win"] = {
            "skin_id": winner.id, "case_id": case.id, "case_name": case.name,
            "name": winner.name, "image": winner.image, "price": winner.price,
            "rarity": winner.rarity, "color": winner.color, "wear": winner.wear,
        }
        request.session.modified = True

        reel = [game.draw_item(items) for _ in range(60)]
        reel[50] = winner

        payload = item_payload(winner)
        payload["wear"] = {"name": winner.wear or "—", "float": game.wear_float(winner.wear)}
        return Response({
            "case": {"id": case.id, "name": case.name},
            "winner": payload,
            "reel": [item_payload(it) for it in reel],
            "winner_index": 50,
            "balance": balance,
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
    player = current_player(request)
    if player:
        return Response({
            "authenticated": True, "name": player.display_name,
            "photo": player.photo_url, "balance": player.balance,
            "streak": player.streak, "invited": player.invited_count,
            "total_won": player.total_won,
        })
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


def _credit(request, player, amount):
    """Add coins to the balance (real player or guest session) and return it."""
    if player:
        player.balance += amount
        player.total_won += amount
        player.save(update_fields=["balance", "total_won", "last_seen"])
        return player.balance, player.total_won
    state = get_state(request)
    state["balance"] += amount
    state["total_won"] += amount
    save_state(request, state)
    return state["balance"], state["total_won"]


@api_view(["POST"])
def sell(request):
    """Sell a skin for coins. Targets either an inventory record (record_id) or
    the just-opened drop (pending_win in the session)."""
    player = current_player(request)
    rec_id = _int(request.data.get("record_id"))

    # 1) Selling an item already in the inventory.
    if rec_id and player:
        rec = player.opens.filter(pk=rec_id, sold=False).first()
        if not rec:
            return Response({"error": "Topilmadi"}, status=400)
        rec.sold = True
        rec.save(update_fields=["sold"])
        balance, total_won = _credit(request, player, rec.skin_price)
        return Response({"sold": rec.skin_price, "name": rec.skin_name,
                         "balance": balance, "total_won": total_won})
    if rec_id and not player:
        inv = request.session.get("inv", [])
        row = next((r for r in inv if r["id"] == rec_id), None)
        if not row:
            return Response({"error": "Topilmadi"}, status=400)
        request.session["inv"] = [r for r in inv if r["id"] != rec_id]
        request.session.modified = True
        balance, total_won = _credit(request, None, row["price"])
        return Response({"sold": row["price"], "name": row["name"],
                         "balance": balance, "total_won": total_won})

    # 2) Selling the freshly-opened drop.
    pw = request.session.get("pending_win")
    if not pw:
        return Response({"error": "Sotish uchun narsa yo'q"}, status=400)
    request.session.pop("pending_win")
    request.session.modified = True
    balance, total_won = _credit(request, player, pw["price"])
    return Response({"sold": pw["price"], "name": pw["name"],
                     "balance": balance, "total_won": total_won})


@api_view(["POST"])
def claim(request):
    """"Olish" — keep the just-opened drop in the player's personal inventory."""
    pw = request.session.get("pending_win")
    if not pw:
        return Response({"error": "Olish uchun narsa yo'q"}, status=400)
    request.session.pop("pending_win")
    request.session.modified = True

    player = current_player(request)
    if player:
        case = Case.objects.filter(pk=pw["case_id"]).first()
        rec = OpenRecord.objects.create(
            player=player, case=case, case_name=pw["case_name"],
            skin_name=pw["name"], skin_image=pw["image"], skin_price=pw["price"],
            rarity=pw["rarity"], color=pw["color"], wear=pw["wear"], sold=False,
        )
        count = player.opens.filter(sold=False).count()
        return Response({"ok": True, "record_id": rec.id, "count": count})

    # guest inventory lives in the session
    inv = request.session.get("inv", [])
    uid = request.session.get("inv_uid", 0) + 1
    inv.append({"id": uid, **{k: pw[k] for k in
                ("name", "image", "price", "rarity", "color", "wear", "case_name")}})
    request.session["inv"] = inv
    request.session["inv_uid"] = uid
    request.session.modified = True
    return Response({"ok": True, "count": len(inv)})


def _inv_item(rec_id, name, image, price, rarity, color, wear, case_name):
    parts = name.split(" | ")
    return {
        "id": rec_id, "name": name, "weapon": parts[0],
        "finish": parts[1] if len(parts) > 1 else name,
        "img": image, "price": price, "tier_label": rarity or "",
        "color": color or "#b0c3d9", "wear": wear or "", "case_name": case_name,
    }


@api_view(["GET"])
def inventory(request):
    """The player's personal inventory (skins kept via "Olish")."""
    player = current_player(request)
    if player:
        items = [_inv_item(r.id, r.skin_name, r.skin_image, r.skin_price,
                           r.rarity, r.color, r.wear, r.case_name)
                 for r in player.opens.filter(sold=False).order_by("-created_at")]
    else:
        items = [_inv_item(r["id"], r["name"], r["image"], r["price"],
                           r["rarity"], r["color"], r["wear"], r["case_name"])
                 for r in reversed(request.session.get("inv", []))]
    return Response({"items": items, "count": len(items),
                     "total": sum(i["price"] for i in items)})


# ---------- case battles ----------
# Every skin dropped inside a battle is valued 5% below its catalog price — a
# flat house rake applied to all cases.
BATTLE_VALUE_MULT = 0.95


def _clamp(v, lo, hi, default):
    n = _int(v)
    if n is None:
        return default
    return max(lo, min(hi, n))


def _seat_of(player, seat_index):
    """Build a seat entry (stored on Battle.seats) for a real logged-in player."""
    return {
        "seat": seat_index,
        "player_id": player.id,
        "name": player.display_name,
        "photo": player.photo_url or "",
        "streak": player.streak or 0,
    }


def _resolve_battle(battle):
    """Every seated player opens the same rounds; the highest total drop value
    wins ALL the dropped skins (they land in the winner's inventory). Idempotent
    via battle.paid, so a double-join can't pay out twice."""
    if battle.paid:
        return
    uniq = {c.id: c for c in Case.objects.filter(id__in=set(battle.case_ids))}
    ordered = [uniq[cid] for cid in battle.case_ids if cid in uniq]
    items_by_case = {cid: list(c.items.all()) for cid, c in uniq.items()}

    results = []
    for s in battle.seats or []:
        owner = {"name": s.get("name", ""), "photo": s.get("photo", "")}
        drops, total = [], 0
        for c in ordered:
            w = game.draw_item(items_by_case[c.id])
            it = item_payload(w)
            it["price"] = int(round(w.price * BATTLE_VALUE_MULT))   # 5% battle rake
            it["float"] = game.wear_float(w.wear)
            it["case_img"] = c.image
            it["owner"] = owner
            drops.append(it)
            total += it["price"]
        results.append({
            "seat": s.get("seat"), "player_id": s.get("player_id"),
            "name": s.get("name", ""), "photo": s.get("photo", ""),
            "streak": s.get("streak", 0), "drops": drops, "total": total,
        })

    winner_index = max(range(len(results)), key=lambda i: results[i]["total"]) if results else 0
    pot = sum(r["total"] for r in results)

    battle.winner_index = winner_index
    battle.pot = pot
    battle.status = "completed"
    battle.paid = True
    battle.data = {
        "cases": [{"name": c.name, "image": c.image} for c in ordered],
        "results": results,
    }
    battle.save(update_fields=["winner_index", "pot", "status", "paid", "data"])

    # All skins from every seat move into the winner's inventory.
    wp = Player.objects.filter(pk=results[winner_index].get("player_id")).first() if results else None
    if wp:
        for r in results:
            for i, it in enumerate(r["drops"]):
                case = ordered[i] if i < len(ordered) else None
                OpenRecord.objects.create(
                    player=wp, case=case,
                    case_name=(case.name if case else ""),
                    skin_name=it.get("name", ""), skin_image=it.get("img", ""),
                    skin_price=it.get("price", 0), rarity=it.get("tier_label", ""),
                    color=it.get("color", ""), wear=it.get("wear", ""), sold=False)


def _battle_card(b):
    """Compact card for the battles list: cases, price, filled/empty seats."""
    seats = b.seats or []
    by_seat = {s.get("seat"): s for s in seats}
    slots = []
    for pi in range(b.n_players):
        s = by_seat.get(pi)
        if s:
            slots.append({"filled": True, "name": s.get("name", ""),
                          "photo": s.get("photo", ""), "streak": s.get("streak", 0),
                          "won": b.status == "completed" and b.winner_index == pi})
        else:
            slots.append({"filled": False})
    return {
        "id": b.id, "price": b.total_cost, "rounds": len(b.case_ids or []),
        "cases": (b.data or {}).get("cases") or _card_cases(b),
        "slots": slots, "status": b.status,
        "full": len(seats) >= b.n_players,
    }


def _card_cases(b):
    """Case thumbnails for a battle that hasn't been resolved yet (no data.cases)."""
    uniq = {c.id: c for c in Case.objects.filter(id__in=set(b.case_ids or []))}
    return [{"name": uniq[cid].name, "image": uniq[cid].image}
            for cid in (b.case_ids or []) if cid in uniq]


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


def _seconds_to_midnight():
    now = timezone.now()
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((nxt - now).total_seconds())


def _player_daily(player, today):
    """Real per-player day states: (days, active_day, claimed_today)."""
    claimed_today = player.daily_claimed_date == today
    if claimed_today:
        last_day, active_day = player.daily_day, None
    elif player.daily_claimed_date == today - timedelta(days=1):
        last_day, active_day = player.daily_day, (player.daily_day % 14) + 1
    else:
        last_day, active_day = 0, 1
    days = []
    for d, r, base in DAILY_DAYS:
        if d <= last_day:
            state = "claimed"
        elif d == active_day:
            state = "active"
        elif base == "special":
            state = "special"
        else:
            state = "locked"
        days.append({"d": d, "r": r, "state": state})
    return days, active_day, claimed_today


@api_view(["GET"])
def daily(request):
    lang = i18n.get_lang(request)
    player = current_player(request)
    if player:
        today = timezone.now().date()
        days, _, claimed_today = _player_daily(player, today)
        return Response({"days": days, "tasks": _daily_tasks(lang),
                         "timer_seconds": _seconds_to_midnight(), "claimed": claimed_today})
    claimed = request.session.get("daily_claimed", False)
    return Response({"days": _daily_days(claimed), "tasks": _daily_tasks(lang),
                     "timer_seconds": DAILY_TIMER_SECONDS, "claimed": claimed})


@api_view(["POST"])
def daily_claim(request):
    player = current_player(request)
    if player:
        today = timezone.now().date()
        if player.daily_claimed_date == today:
            return Response({"claimed": True, "reward": 0, "balance": player.balance})
        if player.daily_claimed_date == today - timedelta(days=1):
            new_day = (player.daily_day % 14) + 1
            player.streak += 1
        else:
            new_day = 1
            player.streak = 1
        reward = DAILY_DAYS[new_day - 1][1]
        player.balance += reward
        player.daily_day = new_day
        player.daily_claimed_date = today
        player.save(update_fields=["balance", "daily_day", "daily_claimed_date",
                                   "streak", "last_seen"])
        days, _, _ = _player_daily(player, today)
        return Response({"claimed": True, "reward": reward,
                         "balance": player.balance, "days": days})
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


# Upgrade now runs on the player's REAL personal inventory (the skins kept via
# "Olish"): the source skin is consumed and, on a win, the target is added.
def _owned_rows(request):
    """Real owned inventory, newest first: [{uid, value, name, image, rarity, color, wear}]."""
    player = current_player(request)
    if player:
        return [{"uid": r.id, "value": r.skin_price, "name": r.skin_name,
                 "image": r.skin_image, "rarity": r.rarity, "color": r.color, "wear": r.wear}
                for r in player.opens.filter(sold=False).order_by("-created_at")]
    return [{"uid": r["id"], "value": r["price"], "name": r["name"], "image": r["image"],
             "rarity": r["rarity"], "color": r["color"], "wear": r["wear"]}
            for r in reversed(request.session.get("inv", []))]


def _owned_skin_payload(row):
    parts = row["name"].split(" | ")
    return {"id": row["uid"], "name": row["name"], "weapon": parts[0],
            "finish": parts[1] if len(parts) > 1 else row["name"],
            "wear": row["wear"] or "", "tier_label": row["rarity"] or "",
            "color": row["color"] or "#b0c3d9", "img": row["image"],
            "price": row["value"], "chance": None}


def _upg_inv(rows):
    return [{"uid": r["uid"], "value": r["value"], "skin": _owned_skin_payload(r)} for r in rows]


@api_view(["GET"])
def upgrade_inventory(request):
    return Response({"inventory": _upg_inv(_owned_rows(request))})


@api_view(["GET"])
def upgrade_targets(request):
    """Realistic upgrade targets: skins priced just above the selected source
    (cheapest achievable first), so the odds are meaningful — not only millionaire
    knives. `from` = the source skin's value; `q` = name search."""
    q = (request.query_params.get("q") or "").strip().lower()
    fromv = _int(request.query_params.get("from")) or 0
    universe = game.get_universe()
    if q:
        universe = [it for it in universe if q in it.name.lower()]
    universe = [it for it in universe if it.price > fromv]
    universe.sort(key=lambda it: it.price)   # cheapest achievable first
    universe = universe[:60]
    return Response({"targets": [{"skin": item_payload(it), "value": it.price}
                                 for it in universe]})


def _odds(from_value, to_value):
    chance = min(0.9, (from_value / to_value) * UPGRADE_EDGE)
    return chance, to_value / from_value


@api_view(["POST"])
def upgrade_compute(request):
    rows = _owned_rows(request)
    from_item = next((r for r in rows if r["uid"] == _int(request.data.get("from_uid"))), None)
    to = CaseItem.objects.filter(pk=_int(request.data.get("to_skin_id"))).first()
    if not from_item or not to or to.price <= from_item["value"]:
        return Response({"valid": False})
    chance, mult = _odds(from_item["value"], to.price)
    return Response({"valid": True, "chance": chance, "mult": mult})


@api_view(["POST"])
def upgrade_play(request):
    rows = _owned_rows(request)
    from_uid = _int(request.data.get("from_uid"))
    from_item = next((r for r in rows if r["uid"] == from_uid), None)
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

    player = current_player(request)
    if player:
        player.opens.filter(pk=from_uid).update(sold=True)   # consume the source skin
        if won:
            OpenRecord.objects.create(
                player=player, case=to.case, case_name=to.case.name if to.case else "",
                skin_name=to.name, skin_image=to.image, skin_price=to.price,
                rarity=to.rarity, color=to.color, wear=to.wear, sold=False)
    else:
        inv = [r for r in request.session.get("inv", []) if r["id"] != from_uid]
        if won:
            uid = request.session.get("inv_uid", 0) + 1
            inv.append({"id": uid, "name": to.name, "image": to.image, "price": to.price,
                        "rarity": to.rarity, "color": to.color, "wear": to.wear,
                        "case_name": to.case.name if to.case else ""})
            request.session["inv_uid"] = uid
        request.session["inv"] = inv
        request.session.modified = True

    return Response({
        "won": won, "chance": chance, "landing_deg": landing,
        "target": {"skin": item_payload(to), "value": to.price},
        "inventory": _upg_inv(_owned_rows(request)),
    })
