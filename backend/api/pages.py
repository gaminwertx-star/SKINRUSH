"""Server-side rendered pages for SKINRUSH — no client-side JavaScript.

Every screen is a real Django page reached by its own URL. All game logic
(charging the balance, drawing the winner, computing odds, resolving battles)
runs here on the server and the result is baked into the HTML before it is
sent; CSS handles the reveal animations. Forms POST back to these views.
"""
import random
import re
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import game, i18n
from .auth_account import EMAIL_RE, USERNAME_RE, _norm_phone
from .auth_telegram import current_player, verify_webapp
from .templatetags.skinrush_extras import img as _img_url
from .models import (
    Battle, Case, CaseItem, Drop, OpenRecord, Player, WithdrawRequest,
)
from .telegram_bot import notify_withdraw
from .views import (
    DAILY_DAYS, DAILY_TASKS, UPGRADE_EDGE,
    _battle_card, _card_cases, _clamp, _credit, _daily_days, _int,
    _odds, _owned_rows, _owned_skin_payload, _player_daily, _resolve_battle,
    _seat_of, get_state, item_payload, save_state,
)


# ---------------------------------------------------------------- helpers
def _charge(request, player, amount):
    """Deduct `amount` from the real balance (player or guest). Returns (ok, balance)."""
    if player:
        if player.balance < amount:
            return False, player.balance
        player.balance -= amount
        player.save(update_fields=["balance", "last_seen"])
        return True, player.balance
    st = get_state(request)
    if st["balance"] < amount:
        return False, st["balance"]
    st["balance"] -= amount
    save_state(request, st)
    return True, st["balance"]


def _tasks(lang):
    return [{"icon": t["icon"], "label": i18n.t(lang, t["key"]), "reward": t["reward"]}
            for t in DAILY_TASKS]


def _bank_pending(request):
    """Move the unclaimed drop (session pending_win) into the inventory.

    Returns the banked payload, or None if there was nothing pending.
    Used by `claim` and called defensively before a new open so an
    unclaimed drop is never silently overwritten and lost.
    """
    pw = request.session.pop("pending_win", None)
    request.session.pop("reel", None)
    request.session.modified = True
    if not pw:
        return None
    player = current_player(request)
    if player:
        case = Case.objects.filter(pk=pw["case_id"]).first()
        OpenRecord.objects.create(
            player=player, case=case, case_name=pw["case_name"],
            skin_name=pw["name"], skin_image=pw["image"], skin_price=pw["price"],
            rarity=pw["rarity"], color=pw["color"], wear=pw["wear"], sold=False)
    else:
        inv = request.session.get("inv", [])
        uid = request.session.get("inv_uid", 0) + 1
        inv.append({"id": uid, "name": pw["name"], "image": pw["image"],
                    "price": pw["price"], "rarity": pw["rarity"], "color": pw["color"],
                    "wear": pw["wear"], "case_name": pw["case_name"]})
        request.session["inv"] = inv
        request.session["inv_uid"] = uid
        request.session.modified = True
    return pw


# ---------------------------------------------------------------- home
def home(request):
    lang = i18n.get_lang(request)
    player = current_player(request)

    qs = Case.objects.all()
    q = (request.GET.get("q") or "").strip()
    mn = request.GET.get("min")
    mx = request.GET.get("max")
    if q:
        qs = qs.filter(name__icontains=q)
    if mn and _int(mn) is not None:
        qs = qs.filter(price__gte=_int(mn))
    if mx and _int(mx) is not None:
        qs = qs.filter(price__lte=_int(mx))
    cases = list(qs)

    if player:
        today = timezone.now().date()
        days, _, claimed_today = _player_daily(player, today)
    else:
        claimed_today = request.session.get("daily_claimed", False)
        days = _daily_days(claimed_today)

    return render(request, "home.html", {
        "ACTIVE": "bonuslar", "cases": cases,
        "q": q, "min": mn or "", "max": mx or "",
        "days": days, "tasks": _tasks(lang), "daily_claimed": claimed_today,
    })


@require_POST
def daily_claim(request):
    player = current_player(request)
    if player:
        today = timezone.now().date()
        if player.daily_claimed_date == today:
            messages.info(request, "Bugungi sovg'a allaqachon olingan")
            return redirect("home")
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
        messages.success(request, i18n.t(i18n.get_lang(request), "toast_daily").format(n=reward))
        return redirect("home")

    if request.session.get("daily_claimed", False):
        messages.info(request, "Bugungi sovg'a allaqachon olingan")
        return redirect("home")
    request.session["daily_claimed"] = True
    st = get_state(request)
    st["balance"] += 50
    save_state(request, st)
    messages.success(request, i18n.t(i18n.get_lang(request), "toast_daily").format(n=50))
    return redirect("home")


# ---------------------------------------------------------------- cases
def case_detail(request, slug):
    case = get_object_or_404(Case, slug=slug)
    items = sorted(case.items.all(), key=lambda it: (it.chance, -it.price))
    contents = [item_payload(it) for it in items]
    return render(request, "case.html", {
        "ACTIVE": "keyslar", "case": case, "contents": contents,
    })


# ---------------------------------------------------------------- skin detail
_WEAR_ORDER = ["Factory New", "Minimal Wear", "Field-Tested",
               "Well-Worn", "Battle-Scarred"]


_WEAR_TONE = {
    "Factory New": "#4ade80", "Minimal Wear": "#a3e635",
    "Field-Tested": "#fbbf24", "Well-Worn": "#fb923c",
    "Battle-Scarred": "#f87171",
}


def _wear_row(wear, price, item_id, case_id):
    band = game.WEAR_BANDS.get(wear or "")
    return {
        "wear": wear or "", "abbr": _wearabbr(wear), "price": price,
        "item_id": item_id, "case_id": case_id,
        "tone": _WEAR_TONE.get(wear or "", "#8b93a7"),
        "lo": f"{band[0]:.2f}" if band else None,
        "hi": f"{band[1]:.2f}" if band else None,
        "width": round((band[1] - band[0]) * 100, 2) if band else None,
    }


def _wearabbr(w):
    table = {"Factory New": "FN", "Minimal Wear": "MW", "Field-Tested": "FT",
             "Well-Worn": "WW", "Battle-Scarred": "BS"}
    return table.get(w or "", "")


def skin_detail(request):
    """Skin dossier. Outside a case → every wear condition + price (a float
    ladder). From inside a case (`?case=`) → only the condition that case drops."""
    item = None
    item_pk = _int(request.GET.get("item"))
    if item_pk:
        item = CaseItem.objects.filter(pk=item_pk).first()
    name = request.GET.get("name") or (item.name if item else "")
    if not name:
        return redirect("home")
    rows = list(CaseItem.objects.filter(name=name))
    if not rows:
        return redirect("home")

    case_id = _int(request.GET.get("case"))
    base = item or max(rows, key=lambda r: r.price)

    # full spread: cheapest listing per wear, ordered FN→BS
    spread = {}
    for r in rows:
        w = r.wear or ""
        if w not in spread or r.price < spread[w]["price"]:
            spread[w] = _wear_row(w, r.price, r.id, r.case_id)
    conditions = [spread[w] for w in sorted(
        spread, key=lambda w: _WEAR_ORDER.index(w) if w in _WEAR_ORDER else 99)]
    laddered = [c for c in conditions if c["width"] is not None]

    in_case = None
    back_case = None
    if case_id:
        crow = next((r for r in rows if r.case_id == case_id), None) or item
        back_case = Case.objects.filter(pk=case_id).first()
        if crow:
            in_case = _wear_row(crow.wear, crow.price, crow.id, crow.case_id)
            in_case["chance"] = crow.chance
            in_case["case"] = back_case
            base = crow

    cases_qs = Case.objects.filter(items__name=name).distinct()
    prices = [c["price"] for c in conditions]
    return render(request, "skin.html", {
        "ACTIVE": "keyslar",
        "skin": item_payload(base), "sname": name,
        "weapon": base.weapon, "finish": base.finish or name,
        "rarity": base.rarity, "color": base.color or "#b0c3d9",
        "conditions": conditions, "ladder": laddered,
        "in_case": in_case, "back_case": back_case,
        "min_price": min(prices) if prices else 0,
        "max_price": max(prices) if prices else 0,
        "cases": list(cases_qs[:14]), "cases_count": cases_qs.count(),
    })


@require_POST
def case_open(request, slug):
    case = get_object_or_404(Case, slug=slug)
    items = list(case.items.all())
    if not items:
        messages.error(request, "Bo'sh keys")
        return redirect("case", slug=slug)

    player = current_player(request)
    ok, _ = _charge(request, player, case.price)
    if not ok:
        messages.error(request, i18n.t(i18n.get_lang(request), "not_enough"))
        return redirect("case", slug=slug)

    # An unclaimed previous drop must not be lost when the session
    # pending_win is overwritten below — bank it into the inventory.
    _bank_pending(request)

    winner = game.draw_item(items)
    Drop.objects.create(case=case, item=winner)
    Case.objects.filter(pk=case.pk).update(opens=case.opens + 1)

    request.session["pending_win"] = {
        "skin_id": winner.id, "case_id": case.id, "case_name": case.name,
        "case_slug": case.slug, "name": winner.name, "image": winner.image,
        "price": winner.price, "rarity": winner.rarity, "color": winner.color,
        "wear": winner.wear, "float": game.wear_float(winner.wear),
        "weapon": winner.weapon, "finish": winner.finish,
    }
    reel = [game.draw_item(items) for _ in range(60)]
    reel[50] = winner
    request.session["reel"] = [item_payload(it) for it in reel]
    # "Skip animation" checkbox — remembered for the next opens too.
    fast = bool(request.POST.get("fast"))
    request.session["skip_anim"] = fast
    request.session.modified = True
    return redirect(reverse("result") + ("?fast=1" if fast else ""))


def result(request):
    pw = request.session.get("pending_win")
    reel = request.session.get("reel")
    if not pw or not reel:
        return redirect("home")
    case = Case.objects.filter(pk=pw["case_id"]).first()
    return render(request, "result.html", {
        "ACTIVE": "keyslar", "pw": pw, "reel": reel, "winner_index": 50,
        "fast": request.GET.get("fast") == "1",
        "case_price": case.price if case else 0,
    })


@require_POST
def claim(request):
    pw = _bank_pending(request)
    if not pw:
        return redirect("home")
    messages.success(request, f'"{pw["name"]}" inventarga qo\'shildi')
    return redirect("case", slug=pw["case_slug"]) if pw.get("case_slug") else redirect("home")


@require_POST
def sell(request):
    player = current_player(request)
    rec_id = _int(request.POST.get("record_id"))

    if rec_id and player:
        # is_locked → promised to a withdraw request, not the player's to sell.
        rec = player.opens.filter(pk=rec_id, sold=False, is_locked=False).first()
        if rec:
            rec.sold = True
            rec.save(update_fields=["sold"])
            _credit(request, player, rec.skin_price)
            messages.success(request, f"Sotildi: {rec.skin_name} · +{rec.skin_price}")
        return redirect("inventory")
    if rec_id and not player:
        inv = request.session.get("inv", [])
        row = next((r for r in inv if r["id"] == rec_id), None)
        if row:
            request.session["inv"] = [r for r in inv if r["id"] != rec_id]
            request.session.modified = True
            _credit(request, None, row["price"])
            messages.success(request, f"Sotildi: {row['name']} · +{row['price']}")
        return redirect("inventory")

    # Selling the freshly-opened drop.
    pw = request.session.get("pending_win")
    if not pw:
        return redirect("home")
    request.session.pop("pending_win", None)
    request.session.pop("reel", None)
    request.session.modified = True
    _credit(request, player, pw["price"])
    messages.success(request, f"Sotildi: {pw['name']} · +{pw['price']}")
    return redirect("case", slug=pw.get("case_slug") or "") if pw.get("case_slug") else redirect("home")


# ---------------------------------------------------------------- inventory
def _inv_row(rid, name, image, price, rarity, color, wear, case_name, locked=False):
    parts = name.split(" | ")
    return {"id": rid, "name": name, "weapon": parts[0],
            "finish": parts[1] if len(parts) > 1 else name,
            "img": image, "price": price, "tier_label": rarity,
            "color": color or "#b0c3d9", "wear": wear, "case_name": case_name,
            "locked": locked}


def _inv_rows(request):
    """Inventory as shown on the page. Unlike `_owned_rows` this keeps skins held
    by an open withdraw request — the player should see where their skin went,
    the template just swaps the actions for a "being withdrawn" badge."""
    player = current_player(request)
    if player:
        return [_inv_row(r.id, r.skin_name, r.skin_image, r.skin_price,
                         r.rarity, r.color, r.wear, r.case_name, r.is_locked)
                for r in player.opens.filter(sold=False).order_by("-created_at")]
    return [_inv_row(r["id"], r["name"], r["image"], r["price"],
                     r["rarity"], r["color"], r["wear"], r["case_name"])
            for r in reversed(request.session.get("inv", []))]


def inventory(request):
    rows = _inv_rows(request)
    return render(request, "inventory.html", {
        "ACTIVE": "inventar", "items": rows,
        "total": sum(r["price"] for r in rows),
        # Guests have no withdraw flow at all — the button needs an account.
        "can_withdraw": current_player(request) is not None,
    })


# ---------------------------------------------------------------- withdraw
# Steam's own trade-offer URL shape. Anything else cannot receive an offer, so
# it is rejected at the form rather than wasting an admin's time.
TRADE_URL_RE = re.compile(
    r"^https://steamcommunity\.com/tradeoffer/new/\?partner=\d+&token=\w+$")


def _withdrawable(player, rec_id):
    """The player's skin `rec_id`, if it is theirs to withdraw. None otherwise."""
    return player.opens.filter(pk=rec_id, sold=False, is_locked=False).first()


def _active_withdraw(player):
    """The player's in-flight request, if any — one at a time (see OPEN_STATUSES)."""
    return player.withdraws.filter(
        status__in=WithdrawRequest.OPEN_STATUSES).select_related("record").first()


def withdraw(request):
    """Withdraw a skin to Steam. Shows the skin card, asks for the trade URL the
    first time round, then hands over to `withdraw_create` to file the request."""
    player = current_player(request)
    if not player:
        messages.error(request, "Skin yechib olish uchun hisobingizga kiring")
        return redirect("login")

    rec = _withdrawable(player, _int(request.GET.get("id")))
    if not rec:
        messages.error(request, "Skin topilmadi yoki allaqachon band qilingan")
        return redirect("inventory")

    return render(request, "withdraw.html", {
        "ACTIVE": "inventar",
        "skin": _inv_row(rec.id, rec.skin_name, rec.skin_image, rec.skin_price,
                         rec.rarity, rec.color, rec.wear, rec.case_name),
        "trade_url": player.trade_url,
        "active": _active_withdraw(player),
        # No URL saved yet, or the player asked to change the one on file.
        "editing": not player.trade_url or bool(request.GET.get("edit")),
    })


@require_POST
def withdraw_trade_url(request):
    """Save (or replace) the player's Steam trade URL, then return to the card."""
    player = current_player(request)
    if not player:
        return redirect("login")
    rec_id = _int(request.POST.get("record_id"))
    url = (request.POST.get("trade_url") or "").strip()
    back = f"{reverse('withdraw')}?id={rec_id}"

    if not TRADE_URL_RE.match(url):
        messages.error(
            request,
            "Trade URL noto'g'ri. U quyidagi ko'rinishda bo'lishi kerak: "
            "https://steamcommunity.com/tradeoffer/new/?partner=123456&token=AbCdEfGh")
        return redirect(f"{back}&edit=1")

    player.trade_url = url
    player.save(update_fields=["trade_url", "last_seen"])
    messages.success(request, "Trade URL saqlandi ✅")
    return redirect(back)


@require_POST
def withdraw_create(request):
    """File the withdraw request and lock the skin behind it."""
    player = current_player(request)
    if not player:
        return redirect("login")
    rec_id = _int(request.POST.get("record_id"))
    if not player.trade_url:
        return redirect(f"{reverse('withdraw')}?id={rec_id}")

    with transaction.atomic():
        # Re-read under a row lock: two quick submits must not file two requests
        # for one skin (no-op on SQLite, real on the server's Postgres).
        rec = (player.opens.select_for_update()
               .filter(pk=rec_id, sold=False, is_locked=False).first())
        if not rec:
            messages.error(request, "Skin topilmadi yoki allaqachon band qilingan")
            return redirect("inventory")
        if player.withdraws.filter(status__in=WithdrawRequest.OPEN_STATUSES).exists():
            messages.error(request, "Sizda hozircha faol so'rov bor, iltimos kuting")
            return redirect("inventory")

        WithdrawRequest.objects.create(
            player=player, record=rec, case_name=rec.case_name,
            trade_url=player.trade_url)
        rec.is_locked = True
        rec.save(update_fields=["is_locked"])

    notify_withdraw(player.telegram_id, WithdrawRequest.PENDING, rec.skin_name)
    messages.success(
        request,
        "So'rovingiz qabul qilindi ✅. Adminlarimiz tez orada ko'rib chiqib, "
        "skiningizni Steam inventaringizga tushirib beradi.")
    return redirect("inventory")


# ---------------------------------------------------------------- upgrade
_UPG_MULTS = [2, 3, 5, 10, 20]


def upgrade(request):
    rows = _owned_rows(request)
    inv = [_owned_skin_payload(r) for r in rows]
    from_uid = _int(request.GET.get("from"))
    from_item = next((r for r in rows if r["uid"] == from_uid), None)
    from_skin = _owned_skin_payload(from_item) if from_item else None
    from_value = from_item["value"] if from_item else 0

    to_id = _int(request.GET.get("to"))
    mult_sel = request.GET.get("mult")
    q = (request.GET.get("q") or "").strip().lower()
    targets, mult_opts, target = [], [], None

    if from_item:
        universe = game.get_universe()
        pool = [it for it in universe if it.price > from_value]

        # quick multiplier picks: the skin closest to from_value * m
        for m in _UPG_MULTS:
            tv = from_value * m
            cand = min(pool, key=lambda it: abs(it.price - tv)) if pool else None
            if cand:
                ch, _ = _odds(from_value, cand.price)
                mult_opts.append({"m": m, "to_id": cand.id, "pct": round(ch * 100),
                                  "active": mult_sel == str(m)})
        if mult_sel and not to_id:
            mo = next((o for o in mult_opts if o["active"]), None)
            if mo:
                to_id = mo["to_id"]

        # browsable target grid
        gpool = [it for it in pool if q in it.name.lower()] if q else pool
        for it in sorted(gpool, key=lambda it: it.price)[:40]:
            ch, mu = _odds(from_value, it.price)
            targets.append({"skin": item_payload(it), "value": it.price, "to_id": it.id,
                            "chance": ch, "mult": mu, "pct": round(ch * 100),
                            "sel": it.id == to_id})

        # selected target preview
        if to_id:
            tit = CaseItem.objects.filter(pk=to_id).first()
            if tit and tit.price > from_value:
                ch, mu = _odds(from_value, tit.price)
                target = {"skin": item_payload(tit), "value": tit.price, "to_id": tit.id,
                          "chance": ch, "pct": round(ch * 100), "mult": mu,
                          "chance_deg": round(ch * 360, 2)}

    result = request.session.pop("upg_result", None)
    request.session.modified = True
    return render(request, "upgrade.html", {
        "ACTIVE": "yaxshilash", "inv": inv, "targets": targets, "mult_opts": mult_opts,
        "from_uid": from_uid, "from_skin": from_skin, "from_value": from_value,
        "target": target, "q": request.GET.get("q") or "", "result": result,
    })


@require_POST
def upgrade_play(request):
    rows = _owned_rows(request)
    from_uid = _int(request.POST.get("from_uid"))
    from_item = next((r for r in rows if r["uid"] == from_uid), None)
    to = CaseItem.objects.filter(pk=_int(request.POST.get("to_skin_id"))).first()
    if not from_item or not to or to.price <= from_item["value"]:
        messages.error(request, "Nishon qimmatroq bo'lishi kerak")
        return redirect("upgrade")

    chance, _mult = _odds(from_item["value"], to.price)
    won = random.random() < chance
    chance_deg = chance * 360
    if won:
        landing = random.random() * max(2, chance_deg - 4) + 2
    else:
        landing = chance_deg + 3 + random.random() * max(2, 360 - chance_deg - 6)

    player = current_player(request)
    if player:
        player.opens.filter(pk=from_uid).update(sold=True)
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

    request.session["upg_result"] = {
        "won": won, "chance": chance, "pct": round(chance * 100),
        "landing": round(landing, 2), "chance_deg": round(chance_deg, 2),
        "target": item_payload(to), "value": to.price,
    }
    request.session.modified = True
    return redirect("upgrade")


# ---------------------------------------------------------------- battles
def _in_battle(player, b):
    """Is this logged-in player seated in battle `b` (as creator or joiner)?"""
    if not player:
        return False
    if b.player_id == player.id:
        return True
    return any(s.get("player_id") == player.id for s in (b.seats or []))


def battles(request):
    tab = request.GET.get("tab", "active")
    player = current_player(request)

    if tab == "my":
        cards = []
        if player:
            for b in Battle.objects.all()[:300]:
                if _in_battle(player, b):
                    cards.append(_battle_card(b))
                    if len(cards) >= 40:
                        break
    elif tab == "completed":
        cards = [_battle_card(b) for b in Battle.objects.filter(status="completed")[:40]]
    else:  # active / faol — every open lobby, from any player, waiting for seats
        cards = [_battle_card(b) for b in Battle.objects.filter(status="waiting")[:40]]

    return render(request, "battles.html", {
        "ACTIVE": "janglar", "cards": cards, "tab": tab,
    })


def battle_create(request):
    player = current_player(request)
    if request.method == "POST":
        if not player:
            messages.error(request, "Avval tizimga kiring")
            return redirect("login")
        raw = request.POST.getlist("case_ids")
        case_ids = [c for c in (_int(x) for x in raw) if c][:8]
        if not case_ids:
            messages.error(request, "Kamida 1 ta keys tanlang")
            return redirect("battle-create")
        n = _clamp(request.POST.get("players"), 2, 4, 2)
        uniq = {c.id: c for c in Case.objects.filter(id__in=set(case_ids))}
        if not all(cid in uniq for cid in case_ids):
            messages.error(request, "Keys topilmadi")
            return redirect("battle-create")
        total = sum(uniq[cid].price for cid in case_ids)
        if player.balance < total:
            messages.error(request, i18n.t(i18n.get_lang(request), "not_enough"))
            return redirect("battle-create")

        player.balance -= total
        player.save(update_fields=["balance", "last_seen"])
        if not request.session.session_key:
            request.session.save()
        b = Battle.objects.create(
            player=player, session_key=request.session.session_key, n_players=n,
            case_ids=case_ids, total_cost=total, status="waiting",
            seats=[_seat_of(player, 0)])
        return redirect("battle", pk=b.id)

    return render(request, "battle_create.html", {
        "ACTIVE": "janglar", "cases": list(Case.objects.all()),
        "is_auth": bool(player),
    })


@require_POST
def battle_join(request, pk):
    """A real player takes an open seat. When the last seat fills, the battle
    resolves immediately."""
    player = current_player(request)
    if not player:
        messages.error(request, "Avval tizimga kiring")
        return redirect("login")
    with transaction.atomic():
        b = get_object_or_404(Battle.objects.select_for_update(), pk=pk)
        if b.status != "waiting":
            messages.info(request, "Bu jang allaqachon boshlangan")
            return redirect("battle", pk=pk)
        seats = list(b.seats or [])
        if any(s.get("player_id") == player.id for s in seats):
            messages.info(request, "Siz allaqachon bu jangdasiz")
            return redirect("battle", pk=pk)
        if len(seats) >= b.n_players:
            messages.info(request, "Jang to'lgan")
            return redirect("battle", pk=pk)
        if player.balance < b.total_cost:
            messages.error(request, i18n.t(i18n.get_lang(request), "not_enough"))
            return redirect("battle", pk=pk)

        player.balance -= b.total_cost
        player.save(update_fields=["balance", "last_seen"])
        seats.append(_seat_of(player, len(seats)))
        b.seats = seats
        b.save(update_fields=["seats"])
        resolved = len(seats) >= b.n_players
        if resolved:
            _resolve_battle(b)
    if resolved:
        # this join filled & resolved the battle → play the reveal once
        return redirect(reverse("battle", args=[pk]) + "?reveal=1")
    return redirect("battle", pk=pk)


@require_POST
def battle_cancel(request, pk):
    """The creator may cancel a lobby while still alone, getting a full refund."""
    player = current_player(request)
    if not player:
        return redirect("login")
    with transaction.atomic():
        b = get_object_or_404(Battle.objects.select_for_update(), pk=pk)
        if b.player_id != player.id or b.status != "waiting" or len(b.seats or []) > 1:
            messages.info(request, "Bu jangni bekor qilib bo'lmaydi")
            return redirect("battle", pk=pk)
        b.status = "cancelled"
        b.save(update_fields=["status"])
        _credit(request, player, b.total_cost)
    messages.success(request, f"Jang bekor qilindi · +{b.total_cost}")
    return redirect("battles")


def battle_detail(request, pk):
    b = get_object_or_404(Battle, pk=pk)
    player = current_player(request)
    data = b.data or {}
    seats = b.seats or []
    is_participant = _in_battle(player, b)

    ctx = {
        "ACTIVE": "janglar", "b": b, "cases": data.get("cases") or _card_cases(b),
        "seats": seats, "is_participant": is_participant,
        "is_creator": bool(player and b.player_id == player.id),
        "can_afford": bool(player and player.balance >= b.total_cost),
    }

    if b.status == "completed":
        results = data.get("results", [])
        ctx["results"] = results
        ctx["rounds"] = len(b.case_ids or [])
        wi = b.winner_index or 0
        if 0 <= wi < len(results):
            winner = dict(results[wi])
            # winner takes every seat's drops, richest shown first
            all_drops = [d for r in results for d in r.get("drops", [])]
            all_drops.sort(key=lambda d: d.get("price", 0), reverse=True)
            winner["all_drops"] = all_drops
            ctx["winner"] = winner
            if is_participant:
                ctx["you_won"] = bool(player and results[wi].get("player_id") == player.id)

        # Compact payload for the round-by-round reveal animation (client JS).
        ctx["reel_json"] = {
            "rounds": ctx["rounds"],
            "winner_index": wi,
            "seats": [{
                "name": r.get("name", ""),
                "drops": [{
                    "img": _img_url(d.get("img", "")),
                    "color": d.get("color") or "#b0c3d9",
                    "price": d.get("price", 0),
                } for d in r.get("drops", [])],
            } for r in results],
        }
    else:
        # empty seats to render as dotted placeholders
        ctx["empty_seats"] = range(max(0, b.n_players - len(seats)))

    return render(request, "battle.html", ctx)


# ---------------------------------------------------------------- contracts
CONTRACT_MIN = 2
CONTRACT_MAX = 10


def _pick_uids(values, by_uid):
    """Sanitize a list of raw uid strings: keep owned, dedupe, cap at MAX."""
    seen, out = set(), []
    for x in values:
        u = _int(x)
        if u in by_uid and u not in seen:
            seen.add(u)
            out.append(u)
    return out[:CONTRACT_MAX]


def _contract_outcome(total):
    """Draw the single output value for a contract of `total` input value.

    Slight house edge (mean return ~0.95) with a long jackpot tail, so a
    contract is a real gamble: usually you get back less than you put in,
    sometimes much more.
    """
    r = random.random()
    if r < 0.55:
        mult = random.uniform(0.20, 0.80)    # loss
    elif r < 0.85:
        mult = random.uniform(0.80, 1.30)    # near-even
    elif r < 0.97:
        mult = random.uniform(1.30, 2.50)    # win
    else:
        mult = random.uniform(2.50, 6.00)    # jackpot
    return max(1, round(total * mult))


def kontraktlar(request):
    lang = i18n.get_lang(request)
    rows = _owned_rows(request)
    by_uid = {r["uid"]: r for r in rows}
    picked = _pick_uids(request.GET.getlist("pick"), by_uid)
    picked_set = set(picked)
    total = sum(by_uid[u]["value"] for u in picked)

    inv = []
    for r in rows:
        sel = r["uid"] in picked_set
        nxt = [u for u in picked if u != r["uid"]] if sel else picked + [r["uid"]]
        inv.append({
            "skin": _owned_skin_payload(r), "uid": r["uid"],
            "value": r["value"], "selected": sel,
            "toggle_qs": "?" + "&".join(f"pick={u}" for u in nxt),
            "disabled": (not sel) and len(picked) >= CONTRACT_MAX,
        })

    result = request.session.pop("contract_result", None)
    request.session.modified = True
    return render(request, "contracts.html", {
        "ACTIVE": "kontraktlar", "inv": inv, "picked": picked,
        "picked_count": len(picked), "total": total,
        "can_run": len(picked) >= CONTRACT_MIN,
        "min": CONTRACT_MIN, "max": CONTRACT_MAX, "result": result,
        "pick_hint": i18n.t(lang, "con_pick_hint").format(
            min=CONTRACT_MIN, max=CONTRACT_MAX),
    })


@require_POST
def kontrakt_play(request):
    rows = _owned_rows(request)
    by_uid = {r["uid"]: r for r in rows}
    picked = _pick_uids(request.POST.getlist("pick"), by_uid)
    if len(picked) < CONTRACT_MIN:
        messages.error(request, i18n.t(i18n.get_lang(request), "con_need_min")
                       .format(min=CONTRACT_MIN))
        return redirect("kontraktlar")

    total = sum(by_uid[u]["value"] for u in picked)
    target = _contract_outcome(total)
    universe = game.get_universe()
    out = min(universe, key=lambda it: abs(it.price - target))
    out_value = out.price
    inputs = [_owned_skin_payload(by_uid[u]) for u in picked]

    player = current_player(request)
    if player:
        player.opens.filter(pk__in=picked).update(sold=True)
        OpenRecord.objects.create(
            player=player, case=out.case,
            case_name=out.case.name if out.case else "",
            skin_name=out.name, skin_image=out.image, skin_price=out.price,
            rarity=out.rarity, color=out.color, wear=out.wear, sold=False)
    else:
        drop = set(picked)
        inv = [r for r in request.session.get("inv", []) if r["id"] not in drop]
        uid = request.session.get("inv_uid", 0) + 1
        inv.append({"id": uid, "name": out.name, "image": out.image,
                    "price": out.price, "rarity": out.rarity, "color": out.color,
                    "wear": out.wear, "case_name": out.case.name if out.case else ""})
        request.session["inv"] = inv
        request.session["inv_uid"] = uid

    request.session["contract_result"] = {
        "inputs": inputs, "output": item_payload(out),
        "in_value": total, "out_value": out_value,
        "profit": out_value - total, "won": out_value >= total,
        "n": len(picked),
    }
    request.session.modified = True
    return redirect("kontraktlar")


# ---------------------------------------------------------------- simple pages


def dostlar(request):
    return render(request, "simple.html", {"ACTIVE": "dostlar"})


def promocode(request):
    return render(request, "simple.html", {"ACTIVE": "promocode"})


# ---------------------------------------------------------------- profile
def _level_for(xp):
    """Cs-shot-style progression: each level costs 15% more XP than the last.

    Returns the level plus the current/needed XP into that level and a percent
    for the progress bar."""
    lvl, need, acc = 1, 800, 0
    while xp >= acc + need:
        acc += need
        lvl += 1
        need = int(need * 1.15)
    cur = xp - acc
    pct = round(cur / need * 100) if need else 0
    return {"level": lvl, "cur": cur, "need": need, "pct": pct, "xp": xp,
            "remaining": need - cur}


def _hist_row(name, image, price, rarity, color, wear, case_name, when=None, sold=False):
    parts = name.split(" | ")
    return {"weapon": parts[0], "finish": parts[1] if len(parts) > 1 else name,
            "name": name, "img": image, "price": price, "color": color or "#b0c3d9",
            "wear": wear, "case_name": case_name, "when": when, "sold": sold}


def profile(request):
    player = current_player(request)
    owned = _owned_rows(request)                     # unsold inventory
    inv_value = sum(r["value"] for r in owned)
    items_owned = len(owned)

    if player:
        all_opens = list(player.opens.all().order_by("-created_at"))
        cases_opened = len(all_opens)
        best = max(all_opens, key=lambda r: r.skin_price, default=None)
        best_drop = _hist_row(best.skin_name, best.skin_image, best.skin_price,
                              best.rarity, best.color, best.wear, best.case_name,
                              best.created_at, best.sold) if best else None
        history = [_hist_row(r.skin_name, r.skin_image, r.skin_price, r.rarity,
                             r.color, r.wear, r.case_name, r.created_at, r.sold)
                   for r in all_opens[:12]]
        prof = {
            "auth": True, "name": player.display_name, "photo": player.photo_url,
            "handle": player.username or (f"tg{player.telegram_id}" if player.telegram_id else ""),
            "since": player.created_at, "id": player.id,
            "balance": player.balance, "total_won": player.total_won,
            "streak": player.streak, "invited": player.invited_count,
        }
    else:
        st = get_state(request)
        cases_opened = items_owned
        best = max(owned, key=lambda r: r["value"], default=None)
        best_drop = _hist_row(best["name"], best["image"], best["value"], best["rarity"],
                              best["color"], best["wear"], best.get("case_name", "")) if best else None
        history = [_hist_row(r["name"], r["image"], r["value"], r["rarity"],
                             r["color"], r["wear"], r.get("case_name", "")) for r in owned[:12]]
        prof = {
            "auth": False, "name": "Mehmon", "photo": "", "handle": "guest",
            "since": None, "id": None,
            "balance": st["balance"], "total_won": st["total_won"],
            "streak": st["streak"], "invited": st["invited"],
        }

    xp = (prof["total_won"] + cases_opened * 25 + prof["invited"] * 100
          + prof["streak"] * 15)
    level = _level_for(xp)

    return render(request, "profile.html", {
        "ACTIVE": "profil", "P": prof, "level": level,
        "cases_opened": cases_opened, "items_owned": items_owned,
        "inv_value": inv_value, "best_drop": best_drop,
        "history": history,
        "inv_preview": [_hist_row(r["name"], r["image"], r["value"], r["rarity"],
                                  r["color"], r["wear"], r.get("case_name", ""))
                        for r in owned[:6]],
    })


_SHOP_CATS = ["knife", "gloves", "rifle", "pistol", "smg", "heavy", "agent", "other"]
_RARITY_RANK = {"#b0c3d9": 0, "#5e98d9": 1, "#4b69ff": 2, "#8847ff": 3, "#d32ce6": 4, "#eb4b4b": 5}
_SHOP_WEARS = ["Factory New", "Minimal Wear", "Field-Tested", "Well-Worn", "Battle-Scarred"]
_SHOP_PER_PAGE = 60
_SHOP_GROUP_N = 12


def _shop_qs(request):
    from urllib.parse import urlencode
    keep = {}
    for k in ("cat", "rarity", "wear", "q", "st", "min", "max", "sort"):
        v = request.GET.get(k)
        if v:
            keep[k] = v
    return urlencode(keep)


def dokon(request):
    lang = i18n.get_lang(request)
    catalog = game.get_catalog()

    cat = request.GET.get("cat") or ""
    rarity = request.GET.get("rarity") or ""
    wear = request.GET.get("wear") or ""
    q = (request.GET.get("q") or "").strip().lower()
    st = request.GET.get("st") == "1"
    mn, mx = _int(request.GET.get("min")), _int(request.GET.get("max"))
    sort = request.GET.get("sort") or "price_desc"

    def price_of(e):
        return e["wears"][wear][0] if wear and wear in e["wears"] else e["min_price"]

    def item_of(e):
        return e["wears"][wear][1] if wear and wear in e["wears"] else e["item_id"]

    def keep(e):
        if e["stattrak"] != st:
            return False
        if rarity and e["rarity"] != rarity:
            return False
        if wear and wear not in e["wears"]:
            return False
        if q and q not in e["name"].lower():
            return False
        p = price_of(e)
        if mn is not None and p < mn:
            return False
        if mx is not None and p > mx:
            return False
        return True

    def card(e):
        return {
            "name": e["name"], "weapon": e["weapon"], "finish": e["finish"] or e["name"],
            "rarity": e["rarity"], "color": e["color"], "img": e["image"],
            "price": price_of(e), "min_price": e["min_price"], "max_price": e["max_price"],
            "single": len(e["wears"]) == 1 or bool(wear), "item_id": item_of(e),
        }

    rar_color = {}
    for e in catalog:
        if e["rarity"] and e["rarity"] not in rar_color:
            rar_color[e["rarity"]] = e["color"]
    rarities = sorted(rar_color, key=lambda r: (_RARITY_RANK.get(rar_color[r], 9), r))

    filtered = bool(rarity or wear or q or mn is not None or mx is not None)
    base = [e for e in catalog if keep(e)]

    ctx = {
        "ACTIVE": "dokon", "wears": _SHOP_WEARS, "rarities": rarities,
        "cat_options": [{"v": c, "label": i18n.t(lang, "shop_cat_" + c)} for c in _SHOP_CATS],
        "sort_options": [{"v": s, "label": i18n.t(lang, "sort_" + s)}
                         for s in ("price_desc", "price_asc", "name")],
        "cat": cat, "rarity": rarity, "wear": wear, "q": request.GET.get("q") or "",
        "st": st, "min": request.GET.get("min") or "", "max": request.GET.get("max") or "",
        "sort": sort,
    }

    if cat or filtered:
        rows = [e for e in base if e["category"] == cat] if cat else base
        cards = [card(e) for e in rows]
        if sort == "name":
            cards.sort(key=lambda c: c["name"])
        else:
            cards.sort(key=lambda c: c["price"], reverse=(sort != "price_asc"))
        total = len(cards)
        pages = max(1, (total + _SHOP_PER_PAGE - 1) // _SHOP_PER_PAGE)
        page = min(max(1, _int(request.GET.get("page")) or 1), pages)
        s = (page - 1) * _SHOP_PER_PAGE
        ctx.update({
            "mode": "flat", "cards": cards[s:s + _SHOP_PER_PAGE], "total": total,
            "page": page, "pages": pages, "has_prev": page > 1, "has_next": page < pages,
            "qs": _shop_qs(request),
        })
    else:
        groups = []
        for c in _SHOP_CATS:
            rows = [e for e in base if e["category"] == c]
            if not rows:
                continue
            rows.sort(key=lambda e: e["min_price"], reverse=True)
            groups.append({"cat": c, "label": i18n.t(lang, "shop_cat_" + c),
                           "count": len(rows), "cards": [card(e) for e in rows[:_SHOP_GROUP_N]]})
        ctx.update({"mode": "groups", "groups": groups})

    return render(request, "dokon.html", ctx)


@require_POST
def skin_buy(request):
    from urllib.parse import urlencode
    item = CaseItem.objects.filter(pk=_int(request.POST.get("item"))).first()
    if not item:
        return redirect("home")
    player = current_player(request)
    ok, _ = _charge(request, player, item.price)
    if not ok:
        messages.error(request, i18n.t(i18n.get_lang(request), "not_enough"))
        return redirect(reverse("skin") + "?" + urlencode({"name": item.name}))
    if player:
        OpenRecord.objects.create(
            player=player, case=item.case, case_name=item.case.name if item.case else "",
            skin_name=item.name, skin_image=item.image, skin_price=item.price,
            rarity=item.rarity, color=item.color, wear=item.wear, sold=False)
    else:
        inv = request.session.get("inv", [])
        uid = request.session.get("inv_uid", 0) + 1
        inv.append({"id": uid, "name": item.name, "image": item.image, "price": item.price,
                    "rarity": item.rarity, "color": item.color, "wear": item.wear,
                    "case_name": item.case.name if item.case else ""})
        request.session["inv"] = inv
        request.session["inv_uid"] = uid
        request.session.modified = True
    messages.success(request, i18n.t(i18n.get_lang(request), "shop_bought").format(name=item.name))
    return redirect("inventory")


# ---------------------------------------------------------------- auth
def login_page(request):
    if request.method == "POST":
        ident = (request.POST.get("login") or "").strip()
        password = request.POST.get("password") or ""
        if not (ident and password):
            messages.error(request, "Login va parolni kiriting")
            return redirect("login")
        user = User.objects.filter(username__iexact=ident).first()
        if user is None:
            pl = Player.objects.filter(phone=_norm_phone(ident)).first()
            user = pl.user if pl else None
        if user is None or not user.check_password(password):
            messages.error(request, "Login yoki parol noto'g'ri")
            return redirect("login")
        try:
            player = user.player
        except Player.DoesNotExist:
            player = Player.objects.create(user=user, username=user.username,
                                           first_name=user.username)
        user.backend = "django.contrib.auth.backends.ModelBackend"
        auth_login(request, user)
        messages.success(request, i18n.t(i18n.get_lang(request), "toast_welcome")
                         .format(name=player.display_name))
        return redirect("home")
    return render(request, "login.html", {"ACTIVE": ""})


def register_page(request):
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        username = (request.POST.get("username") or "").strip()
        phone = _norm_phone(request.POST.get("phone"))
        password = request.POST.get("password") or ""

        err = None
        if not (email and username and phone and password):
            err = "Barcha maydonlarni to'ldiring"
        elif not EMAIL_RE.match(email):
            err = "Email noto'g'ri"
        elif not USERNAME_RE.match(username):
            err = "Username 3-32 ta harf/raqam bo'lishi kerak"
        elif len(phone) < 7:
            err = "Telefon raqam noto'g'ri"
        elif len(password) < 6:
            err = "Parol kamida 6 ta belgi bo'lishi kerak"
        elif User.objects.filter(username__iexact=username).exists():
            err = "Bu username band"
        elif User.objects.filter(email__iexact=email).exists():
            err = "Bu email allaqachon ro'yxatdan o'tgan"
        elif Player.objects.filter(phone=phone).exists():
            err = "Bu telefon raqam band"
        if err:
            messages.error(request, err)
            return redirect("register")

        with transaction.atomic():
            user = User.objects.create_user(username=username, email=email, password=password)
            player = Player.objects.create(user=user, username=username,
                                           first_name=username, phone=phone)
        user.backend = "django.contrib.auth.backends.ModelBackend"
        auth_login(request, user)
        messages.success(request, i18n.t(i18n.get_lang(request), "toast_welcome")
                         .format(name=player.display_name))
        return redirect("home")
    return render(request, "register.html", {"ACTIVE": ""})


@require_POST
def logout_page(request):
    auth_logout(request)
    messages.info(request, i18n.t(i18n.get_lang(request), "toast_logout"))
    return redirect("home")


@csrf_exempt
@require_POST
def webapp_login(request):
    """Auto-login for the Telegram Mini App.

    The front-end (base.html) posts ``initData`` that Telegram injected into the
    WebApp. We verify its HMAC signature with the bot token (the signature *is*
    the authentication), then create/refresh the Player and open a session.
    """
    user_data = verify_webapp(request.POST.get("initData") or "")
    if not user_data:
        return JsonResponse({"ok": False, "error": "invalid"}, status=400)

    tg_id = int(user_data["id"])
    player, _ = Player.objects.get_or_create(telegram_id=tg_id)
    player.username = user_data.get("username", "") or player.username
    player.first_name = user_data.get("first_name", "") or player.first_name
    if user_data.get("photo_url"):
        player.photo_url = user_data["photo_url"]
    if player.user is None:
        user, _ = User.objects.get_or_create(username=f"tg_{tg_id}")
        player.user = user
    player.save()

    user = player.user
    user.backend = "django.contrib.auth.backends.ModelBackend"
    auth_login(request, user)
    return JsonResponse({"ok": True})


def set_lang(request, code):
    if code in i18n.STRINGS:
        request.session["lang"] = code
        request.session.modified = True
    nxt = request.GET.get("next") or "home"
    if nxt.startswith("/"):
        return redirect(nxt)
    return redirect("home")
