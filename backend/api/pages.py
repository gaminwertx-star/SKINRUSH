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
from django.db import IntegrityError, transaction
from django.db.models import F, Q
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
    TOPUP_MIN_SUM, TOPUP_PACK_COINS, TOPUP_PACK_SUM,
    Battle, Case, CaseItem, Drop, FreeCase, OpenRecord, PaymentAdmin, Player,
    PromoCode, PromoRedemption, TopUpMessage, TopUpRequest, WithdrawRequest,
    coins_for_sum,
)
from .telegram_bot import (
    notify_topup_new_message, notify_topup_request, notify_withdraw,
)
from .views import (
    DAILY_DAYS, DAILY_TASKS, UPGRADE_EDGE,
    _battle_card, _card_cases, _clamp, _credit, _daily_days, _int,
    _odds, _owned_rows, _owned_skin_payload, _player_daily, _resolve_battle,
    _seat_of, get_state, item_payload, save_state,
)


# ---------------------------------------------------------------- helpers
def _charge(request, player, amount):
    """Deduct `amount` from the real balance (player or guest). Returns (ok, balance).

    The debit is a single conditional UPDATE (``balance >= amount``), so it is
    atomic: two concurrent charges can never both pass the funds check and
    overdraw the account."""
    if player:
        charged = Player.objects.filter(pk=player.pk, balance__gte=amount).update(
            balance=F("balance") - amount)
        player.refresh_from_db(fields=["balance"])
        return bool(charged), player.balance
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
    """Clear the pending-win marker (reel + card) after an opening.

    The skin itself is banked into the inventory at open time now, so this only
    clears the marker. Sessions opened before that change may still hold an
    unbanked drop (no ``banked`` flag) — those are banked here so nothing is
    lost during the transition. Returns the popped payload, or None.
    """
    pw = request.session.pop("pending_win", None)
    request.session.pop("reel", None)
    request.session.modified = True
    if not pw:
        return None
    if not pw.get("banked"):
        # legacy: opened before skins were banked at open — bank it now
        player = current_player(request)
        if player:
            case = Case.objects.filter(pk=pw["case_id"]).first()
            OpenRecord.objects.create(
                player=player, case=case, case_name=pw["case_name"],
                skin_name=pw["name"], skin_image=pw["image"], skin_price=pw["price"],
                rarity=pw["rarity"], color=pw["color"], wear=pw["wear"], sold=False,
                source=OpenRecord.SRC_CASE)
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
def top_drops_feed(request):
    """JSON the strip polls to update itself without a page reload — both the
    LIVE feed and the TOP (most expensive) list."""
    from .context_processors import top_expensive, top_feed
    return JsonResponse({"drops": top_feed(), "top": top_expensive()})


def drop_detail(request, pk):
    """One drop from the TOP DROPS feed: the skin, and who won it."""
    drop = (Drop.objects.select_related("item", "case", "player")
            .filter(pk=pk).first())
    if drop is None:
        return redirect("home")
    it = drop.item
    parts = it.name.split(" | ")
    owner = drop.player
    return render(request, "drop.html", {
        "ACTIVE": "keyslar",
        "drop": drop,
        "skin": {
            "name": it.name, "weapon": parts[0],
            "finish": parts[1] if len(parts) > 1 else it.name,
            "img": it.image, "price": it.price,
            "rarity": it.rarity, "color": it.color or "#b0c3d9", "wear": it.wear,
            # No Steam price source feeds the catalog yet, so this stays "—".
            "usd": None,
        },
        "owner_name": owner.display_name if owner else "Anonim",
        "owner_photo": owner.photo_url if owner else "",
        "owner": owner,
    })


def case_detail(request, slug):
    case = get_object_or_404(Case, slug=slug)
    items = sorted(case.items.all(), key=lambda it: (it.chance, -it.price))
    contents = [item_payload(it) for it in items]
    player = current_player(request)
    # A free opening beats the balance check entirely — it costs nothing, so a
    # broke player must still see the open button, not a top-up prompt.
    free_n = (player.free_cases.filter(case=case, used=False).count()
              if player else 0)
    return render(request, "case.html", {
        "ACTIVE": "keyslar", "case": case, "contents": contents,
        "free_n": free_n,
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
    # A promo-granted free opening is spent instead of the balance. Claim it
    # under a row lock: two taps must not both find the same grant unused.
    free = None
    if player:
        with transaction.atomic():
            free = (player.free_cases.select_for_update()
                    .filter(case=case, used=False).first())
            if free:
                free.used = True
                free.used_at = timezone.now()
                free.save(update_fields=["used", "used_at"])
    if not free:
        ok, _ = _charge(request, player, case.price)
        if not ok:
            messages.error(request, i18n.t(i18n.get_lang(request), "not_enough"))
            return redirect("case", slug=slug)

    # An unclaimed previous drop must not be lost when the session
    # pending_win is overwritten below — bank it into the inventory.
    _bank_pending(request)

    winner = game.draw_item(items)
    Drop.objects.create(case=case, item=winner, player=player)
    Case.objects.filter(pk=case.pk).update(opens=case.opens + 1)

    pending = {
        "skin_id": winner.id, "case_id": case.id, "case_name": case.name,
        "case_slug": case.slug, "name": winner.name, "image": winner.image,
        "price": winner.price, "rarity": winner.rarity, "color": winner.color,
        "wear": winner.wear, "float": game.wear_float(winner.wear),
        "weapon": winner.weapon, "finish": winner.finish, "banked": True,
    }
    # Bank the skin into the inventory NOW, at open time — leaving the result
    # page before pressing Olish must never lose a skin the player paid for.
    # Olish/Sotish then just keep or sell what is already theirs.
    if player:
        rec = OpenRecord.objects.create(
            player=player, case=case, case_name=case.name,
            skin_name=winner.name, skin_image=winner.image, skin_price=winner.price,
            rarity=winner.rarity, color=winner.color, wear=winner.wear, sold=False,
            source=OpenRecord.SRC_CASE)
        pending["record_id"] = rec.id
    else:
        inv = request.session.get("inv", [])
        uid = request.session.get("inv_uid", 0) + 1
        inv.append({"id": uid, "name": winner.name, "image": winner.image,
                    "price": winner.price, "rarity": winner.rarity,
                    "color": winner.color, "wear": winner.wear, "case_name": case.name})
        request.session["inv"] = inv
        request.session["inv_uid"] = uid
        pending["guest_uid"] = uid
    request.session["pending_win"] = pending
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
        rec = player.opens.filter(pk=rec_id).first()
        # Atomic claim: only the request that actually flips sold=False→True (and
        # the skin isn't is_locked, i.e. promised to a withdraw) credits, so two
        # concurrent sells of one skin can't both pay out.
        claimed = player.opens.filter(pk=rec_id, sold=False, is_locked=False).update(
            sold=True, disposition=OpenRecord.DISP_SOLD)
        if rec and claimed:
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

    # Selling the freshly-opened drop — which is already banked in the inventory,
    # so sell that record rather than just crediting a phantom skin.
    pw = request.session.get("pending_win")
    if not pw:
        return redirect("home")
    request.session.pop("pending_win", None)
    request.session.pop("reel", None)
    request.session.modified = True
    if player and pw.get("record_id"):
        # atomic claim: only credit if this request flips it sold
        claimed = player.opens.filter(pk=pw["record_id"], sold=False, is_locked=False).update(
            sold=True, disposition=OpenRecord.DISP_SOLD)
        if claimed:
            _credit(request, player, pw["price"])
    elif not player and pw.get("guest_uid"):
        inv = request.session.get("inv", [])
        if any(r["id"] == pw["guest_uid"] for r in inv):
            request.session["inv"] = [r for r in inv if r["id"] != pw["guest_uid"]]
            request.session.modified = True
            _credit(request, None, pw["price"])
    else:
        # legacy pending win that never entered the inventory
        _credit(request, player, pw["price"])
    messages.success(request, f"Sotildi: {pw['name']} · +{pw['price']}")
    return redirect("case", slug=pw.get("case_slug") or "") if pw.get("case_slug") else redirect("home")


# ---------------------------------------------------------------- inventory
# The tabs across the top of the inventory. `key` is the ?tab= value.
INV_TABS = [
    ("all", "Barchasi"), ("owned", "Mavjud"),
    ("sold", "Sotilgan"), ("withdrawn", "Chiqarilgan"),
]
INV_EMPTY = {
    "all": "Sizning inventaringiz bo'sh",
    "owned": "Sizning inventaringiz bo'sh",
    "sold": "Siz hali skin sotmagansiz",
    "withdrawn": "Siz hali skin chiqarmagansiz",
}


def _inv_row(rec, withdraw=None):
    """One inventory card. `withdraw` is the record's latest WithdrawRequest, if
    any — it decides the Chiqarilgan-tab status text."""
    parts = rec.skin_name.split(" | ")
    if withdraw and withdraw.status != WithdrawRequest.REJECTED:
        # An in-flight request outranks the record's own state: the player cares
        # where their skin is, not that it is technically still theirs. The label
        # is inventory-worded ("Chiqarilgan"), not the admin-side status name
        # ("Yakunlandi"), which means nothing next to a skin.
        if withdraw.status == WithdrawRequest.COMPLETED:
            state, label = "withdrawn", "Chiqarilgan"
        else:
            state, label = "withdrawing", "Chiqarilmoqda"
    elif rec.sold:
        state = rec.disposition or "gone"
        label = dict(OpenRecord.DISPOSITIONS).get(rec.disposition, "Inventarda emas")
    else:
        state, label = "owned", "Mavjud"
    return {
        "id": rec.id, "name": rec.skin_name, "weapon": parts[0],
        "finish": parts[1] if len(parts) > 1 else rec.skin_name,
        "img": rec.skin_image, "price": rec.skin_price,
        "tier_label": rec.rarity, "color": rec.color or "#b0c3d9",
        "wear": rec.wear, "case_name": rec.case_name,
        "usd": rec.steam_price_usd, "state": state, "state_label": label,
        "locked": rec.is_locked, "sellable": not rec.sold and not rec.is_locked,
    }


def _guest_inv_row(r):
    parts = r["name"].split(" | ")
    return {"id": r["id"], "name": r["name"], "weapon": parts[0],
            "finish": parts[1] if len(parts) > 1 else r["name"],
            "img": r["image"], "price": r["price"], "tier_label": r["rarity"],
            "color": r["color"] or "#b0c3d9", "wear": r["wear"],
            "case_name": r["case_name"], "usd": None,
            "state": "owned", "state_label": "Mavjud",
            "locked": False, "sellable": True}


def _inv_rows(request):
    """Every skin the player has ever held, newest first — sold and withdrawn
    ones included, since the tabs are built from them. Guests only ever have
    what is sitting in their session."""
    player = current_player(request)
    if not player:
        return [_guest_inv_row(r) for r in reversed(request.session.get("inv", []))]

    recs = list(player.opens.all().order_by("-created_at"))
    latest = {}
    for w in (WithdrawRequest.objects.filter(record__in=recs)
              .order_by("record_id", "-created_at")):
        latest.setdefault(w.record_id, w)
    return [_inv_row(r, latest.get(r.id)) for r in recs]


def _inv_filter(rows, tab):
    if tab == "owned":
        return [r for r in rows if r["state"] == "owned"]
    if tab == "sold":
        return [r for r in rows if r["state"] == OpenRecord.DISP_SOLD]
    if tab == "withdrawn":
        return [r for r in rows if r["state"] in ("withdrawn", "withdrawing")]
    return rows


def inventory(request):
    tab = request.GET.get("tab")
    if tab not in dict(INV_TABS):
        tab = "all"
    rows = _inv_rows(request)
    shown = _inv_filter(rows, tab)
    sellable = [r for r in rows if r["sellable"]]

    return render(request, "inventory.html", {
        "ACTIVE": "inventar",
        "items": shown,
        "tabs": [{"key": k, "label": lbl, "n": len(_inv_filter(rows, k)),
                  "active": k == tab} for k, lbl in INV_TABS],
        "tab": tab,
        "empty_text": INV_EMPTY[tab],
        # "Hammasini sotish" always acts on the whole sellable inventory, not on
        # whatever the current tab happens to show.
        "sell_all_count": len(sellable),
        "sell_all_total": sum(r["price"] for r in sellable),
        "balance": _balance_of(request),
        # Guests have no withdraw flow at all — the button needs an account.
        "can_withdraw": current_player(request) is not None,
    })


def _balance_of(request):
    player = current_player(request)
    return player.balance if player else get_state(request)["balance"]


def inventory_item(request, pk):
    """One skin out of the player's own inventory: what it is, where it came
    from, and what can still be done with it."""
    player = current_player(request)
    if not player:
        messages.error(request, "Bu sahifa uchun hisobingizga kiring")
        return redirect("login")
    rec = player.opens.filter(pk=pk).first()
    if not rec:
        messages.error(request, "Skin topilmadi")
        return redirect("inventory")

    # Two different questions, so two lookups: the skin's *state* ignores a
    # rejected request (the skin came back, it is plain owned again), but the
    # page still has to explain the rejection, so the note needs the last
    # request whatever its status.
    last = rec.withdraws.order_by("-created_at").first()
    live = (rec.withdraws.exclude(status=WithdrawRequest.REJECTED)
            .order_by("-created_at").first())
    row = _inv_row(rec, live)
    # "Manba" links back to the case only when the skin really came from one and
    # that case still exists in the catalog.
    src_link = (reverse("case", args=[rec.case.slug])
                if rec.source == OpenRecord.SRC_CASE and rec.case else None)
    return render(request, "inventory_item.html", {
        "ACTIVE": "inventar", "it": row, "rec": rec, "owner": player,
        "source_label": dict(OpenRecord.SOURCES).get(rec.source) or "—",
        "source_link": src_link,
        "withdraw": last,
        "can_upgrade": row["sellable"],
    })


@require_POST
def sell_all(request):
    """Sell every skin the player can currently sell, in one go.

    Skips anything held by a withdraw request — those are promised to Steam."""
    player = current_player(request)
    if player:
        # Lock the rows for the duration so a concurrent sell can't also claim
        # one of them; then the total we credit matches exactly what we flipped.
        with transaction.atomic():
            recs = list(player.opens.select_for_update()
                        .filter(sold=False, is_locked=False))
            if not recs:
                messages.error(request, "Sotish uchun buyumlar yo'q")
                return redirect("inventory")
            total = sum(r.skin_price for r in recs)
            player.opens.filter(pk__in=[r.pk for r in recs]).update(
                sold=True, disposition=OpenRecord.DISP_SOLD)
        _credit(request, player, total)
        messages.success(request, f"{len(recs)} ta skin sotildi · +{total:,}".replace(",", " "))
        return redirect("inventory")

    inv = request.session.get("inv", [])
    if not inv:
        messages.error(request, "Sotish uchun buyumlar yo'q")
        return redirect("inventory")
    total = sum(r["price"] for r in inv)
    request.session["inv"] = []
    request.session.modified = True
    _credit(request, None, total)
    messages.success(request, f"{len(inv)} ta skin sotildi · +{total:,}".replace(",", " "))
    return redirect("inventory")


# ---------------------------------------------------------------- promo codes
def _promo_for(code, kind=None):
    """The live promo matching `code`, or None. Codes are case-insensitive."""
    code = (code or "").strip().upper()
    if not code:
        return None
    qs = PromoCode.objects.filter(code=code, is_active=True)
    if kind:
        qs = qs.filter(kind=kind)
    return qs.select_related("case").first()


def _promo_error(promo, player):
    """Why `player` may not use `promo` right now — or None if they may.

    One place, because the top-up form and the redeem page have to agree; a code
    that looks good on one and is refused by the other is worse than no code.
    """
    if promo is None:
        return "Bunday promokod yo'q"
    if promo.is_spent:
        return "Bu promokod limiti tugagan"
    if player and PromoRedemption.objects.filter(promo=promo, player=player).exists():
        return "Siz bu promokodni allaqachon ishlatgansiz"
    return None


def _redeem(promo, player):
    """Book `player`'s use of `promo`. Returns an error string, or None.

    The unique constraint is the real guard: two taps racing each other both
    pass the checks above, and only one survives the insert.
    """
    with transaction.atomic():
        fresh = PromoCode.objects.select_for_update().get(pk=promo.pk)
        err = _promo_error(fresh, player)
        if err:
            return err
        try:
            PromoRedemption.objects.create(promo=fresh, player=player)
        except IntegrityError:
            return "Siz bu promokodni allaqachon ishlatgansiz"
        PromoCode.objects.filter(pk=fresh.pk).update(uses=F("uses") + 1)
        if fresh.kind == PromoCode.KIND_CASE and fresh.case_id:
            FreeCase.objects.create(player=player, case=fresh.case, promo=fresh)
    return None


def promocode(request):
    """Redeem a code. Bonus codes belong on the top-up page, so this page is
    where the free-case ones land."""
    player = current_player(request)
    granted = [f for f in (player.free_cases.filter(used=False)
                           .select_related("case") if player else [])]
    return render(request, "promocode.html", {
        "ACTIVE": "promocode",
        "player": player,
        "free_cases": granted,
    })


@require_POST
def promocode_redeem(request):
    player = current_player(request)
    if not player:
        messages.error(request, "Promokod ishlatish uchun hisobingizga kiring")
        return redirect("login")

    code = (request.POST.get("code") or "").strip().upper()
    promo = _promo_for(code)
    err = _promo_error(promo, player)
    if err:
        messages.error(request, err)
        return redirect("promocode")

    if promo.kind == PromoCode.KIND_BONUS:
        messages.info(
            request,
            f"«{promo.code}» — bu to'ldirish bonusi (+{promo.bonus_percent}%). "
            f"Uni balansni to'ldirishda kiriting.")
        return redirect("toldirish")

    if not promo.case_id:
        messages.error(request, "Bu promokodning keysi o'chirilgan")
        return redirect("promocode")

    err = _redeem(promo, player)
    if err:
        messages.error(request, err)
        return redirect("promocode")

    messages.success(request, f"🎁 Bepul keys yutdingiz: {promo.case.name}!")
    return redirect("case", slug=promo.case.slug)


# ---------------------------------------------------------------- top-up


def toldirish(request):
    """Buy coins. The player names an amount, optionally applies a promo, picks
    an admin, and the admin then settles it by hand over the bot."""
    player = current_player(request)
    if not player:
        messages.error(request, "Balansni to'ldirish uchun hisobingizga kiring")
        return redirect("login")

    admins = list(PaymentAdmin.objects.filter(is_active=True))
    code = (request.GET.get("promo") or "").strip().upper()
    promo = _promo_for(code, kind=PromoCode.KIND_BONUS)
    if promo and _promo_error(promo, player):
        promo = None
    return render(request, "toldirish.html", {
        "ACTIVE": "dokon",
        "pack_sum": TOPUP_PACK_SUM, "pack_coins": TOPUP_PACK_COINS,
        "min_sum": TOPUP_MIN_SUM,
        "quick": [TOPUP_MIN_SUM, 10_000, TOPUP_PACK_SUM, 50_000, 100_000],
        "admins": admins,
        "promo_code": code,
        "promo": promo,
        "promo_bad": bool(code) and promo is None,
        "active": _active_topup(player),
        # The whole point is that an admin messages them on Telegram, so an
        # account with no Telegram linked cannot be served here.
        "no_telegram": not player.telegram_id,
    })


def _active_topup(player):
    return (player.topups.filter(status__in=TopUpRequest.OPEN_STATUSES)
            .select_related("admin").first())


# ---------------------------------------------------------------- top-up chat
def _is_image_upload(f):
    """A light check that an upload is an image — we store it, we don't decode it."""
    ok_ext = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic")
    ct = (getattr(f, "content_type", "") or "").lower()
    name = (getattr(f, "name", "") or "").lower()
    return ct.startswith("image/") or name.endswith(ok_ext)


def _msg_json(m):
    return {
        "id": m.id, "sender": m.sender, "text": m.text,
        "image": m.image.url if m.image else None,
        "at": m.created_at.strftime("%H:%M"),
    }


def toldirish_chat(request):
    """Poll: the player's active/last top-up conversation as JSON."""
    player = current_player(request)
    req = (player.topups.select_related("admin").order_by("-created_at").first()
           if player else None)
    if not req:
        return JsonResponse({"status": None, "messages": []})
    # anything the admin sent is now seen by the player
    req.messages.filter(sender=TopUpMessage.ADMIN, read_by_user=False).update(
        read_by_user=True)
    return JsonResponse({
        "status": req.status,
        "status_label": dict(TopUpRequest.STATUSES).get(req.status, req.status),
        "amount_sum": req.amount_sum, "coins": req.coins,
        "admin": req.admin.name if req.admin else None,
        "messages": [_msg_json(m) for m in req.messages.all()],
    })


@require_POST
def toldirish_send(request):
    """Player sends a chat message (text and/or a receipt photo)."""
    player = current_player(request)
    if not player:
        return JsonResponse({"error": "auth"}, status=403)
    req = _active_topup(player)
    if not req:
        return JsonResponse({"error": "Faol so'rov yo'q"}, status=400)
    text = (request.POST.get("text") or "").strip()[:2000]
    img = request.FILES.get("image")
    if img:
        if not _is_image_upload(img):
            return JsonResponse({"error": "Faqat rasm yuborish mumkin"}, status=400)
        if img.size > 12 * 1024 * 1024:
            return JsonResponse({"error": "Rasm juda katta (12MB dan kam)"}, status=400)
    if not text and not img:
        return JsonResponse({"ok": True, "message": None})
    msg = TopUpMessage.objects.create(
        request=req, sender=TopUpMessage.USER, text=text, image=img,
        read_by_user=True)
    if req.admin:
        notify_topup_new_message(req.admin.tg_chat_id, player.display_name)
    return JsonResponse({"ok": True, "message": _msg_json(msg)})


def toldirish_promo(request):
    """Live promo lookup for the amount box (the form re-checks on submit).

    Only bonus codes work here; a free-case code entered by mistake gets told
    where it does belong rather than a flat "no such code".
    """
    code = (request.GET.get("code") or "").strip().upper()
    promo = _promo_for(code, kind=PromoCode.KIND_BONUS)
    if promo is None:
        other = _promo_for(code, kind=PromoCode.KIND_CASE)
        if other:
            return JsonResponse({"ok": False,
                                 "error": "Bu bepul keys kodi — «Promokod» "
                                          "sahifasida faollashtiring"})
        return JsonResponse({"ok": False})

    err = _promo_error(promo, current_player(request))
    if err:
        return JsonResponse({"ok": False, "error": err})
    return JsonResponse({"ok": True, "code": promo.code,
                         "bonus_percent": promo.bonus_percent})


@require_POST
def toldirish_create(request):
    player = current_player(request)
    if not player:
        return redirect("login")
    if not player.telegram_id:
        messages.error(request, "To'ldirish uchun Telegram orqali kiring — "
                                "admin siz bilan Telegramda bog'lanadi.")
        return redirect("toldirish")

    amount = _int(request.POST.get("amount_sum")) or 0
    if amount < TOPUP_MIN_SUM:
        messages.error(request, f"Eng kam to'ldirish {TOPUP_MIN_SUM:,} so'm".replace(",", " "))
        return redirect("toldirish")

    admin = PaymentAdmin.objects.filter(
        pk=_int(request.POST.get("admin_id")), is_active=True).first()
    if admin is None:
        admin = PaymentAdmin.objects.filter(is_active=True).first()
    if admin is None:
        messages.error(request, "Hozircha to'lov adminlari mavjud emas, "
                                "keyinroq urinib ko'ring")
        return redirect("toldirish")

    # Re-check the promo server-side; the page only ever displayed it. An
    # unusable code is dropped rather than blocking the top-up — the player
    # still wants their coins.
    promo = _promo_for(request.POST.get("promo"), kind=PromoCode.KIND_BONUS)
    if promo and _promo_error(promo, player):
        messages.error(request, _promo_error(promo, player))
        return redirect("toldirish")
    bonus = promo.bonus_percent if promo else 0
    coins = coins_for_sum(amount, bonus)

    with transaction.atomic():
        if player.topups.filter(status__in=TopUpRequest.OPEN_STATUSES).exists():
            messages.error(request, "Sizda hozircha faol so'rov bor, iltimos kuting")
            return redirect("toldirish")
        if promo:
            err = _redeem(promo, player)
            if err:
                messages.error(request, err)
                return redirect("toldirish")
        req = TopUpRequest.objects.create(
            player=player, admin=admin, amount_sum=amount, coins=coins,
            promo=promo, bonus_percent=bonus)

    notify_topup_request(admin.tg_chat_id, req.id, player.display_name,
                         player.username, amount, coins, bonus)
    messages.success(request, "So'rovingiz yuborildi ✅. Adminimiz 5 daqiqa "
                              "ichida Telegramda siz bilan bog'lanadi.")
    return redirect("toldirish")


@require_POST
def toldirish_cancel(request):
    """Let a player drop a request the admin has not picked up."""
    player = current_player(request)
    if not player:
        return redirect("login")
    for req in player.topups.filter(status=TopUpRequest.WAITING):
        req.release_promo()          # they never got the bonus — give the code back
        req.status = TopUpRequest.CLOSED
        req.save(update_fields=["status", "updated_at"])
    messages.success(request, "So'rov bekor qilindi")
    return redirect("toldirish")


# ---------------------------------------------------------------- withdraw
# Steam's own trade-offer URL shape. Anything else cannot receive an offer, so
# it is rejected at the form rather than wasting an admin's time.
TRADE_URL_RE = re.compile(
    r"^https://steamcommunity\.com/tradeoffer/new/\?partner=\d+&token=\w+$")


def _withdrawable(player, rec_id):
    """The player's skin `rec_id`, if it is theirs to withdraw. None otherwise."""
    return player.opens.filter(pk=rec_id, sold=False, is_locked=False).first()


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
        "skin": _inv_row(rec),
        "trade_url": player.trade_url,
        # No "one active request" gate — a player may withdraw several skins.
        "active": None,
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
        # No one-at-a-time limit: each request locks its own skin, so a player
        # may have several in flight — one per skin.
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
        player.opens.filter(pk=from_uid).update(
            sold=True, disposition=OpenRecord.DISP_UPGRADED)
        if won:
            OpenRecord.objects.create(
                player=player, case=to.case, case_name=to.case.name if to.case else "",
                skin_name=to.name, skin_image=to.image, skin_price=to.price,
                rarity=to.rarity, color=to.color, wear=to.wear, sold=False,
                source=OpenRecord.SRC_UPGRADE)
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

    if won and to.case_id:
        Drop.objects.create(case=to.case, item=to, player=player)

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
        player.opens.filter(pk__in=picked).update(
            sold=True, disposition=OpenRecord.DISP_CONTRACT)
        OpenRecord.objects.create(
            player=player, case=out.case,
            case_name=out.case.name if out.case else "",
            skin_name=out.name, skin_image=out.image, skin_price=out.price,
            rarity=out.rarity, color=out.color, wear=out.wear, sold=False,
            source=OpenRecord.SRC_CONTRACT)
    else:
        drop = set(picked)
        inv = [r for r in request.session.get("inv", []) if r["id"] not in drop]
        uid = request.session.get("inv_uid", 0) + 1
        inv.append({"id": uid, "name": out.name, "image": out.image,
                    "price": out.price, "rarity": out.rarity, "color": out.color,
                    "wear": out.wear, "case_name": out.case.name if out.case else ""})
        request.session["inv"] = inv
        request.session["inv_uid"] = uid

    if out.case_id:
        Drop.objects.create(case=out.case, item=out, player=player)

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
            rarity=item.rarity, color=item.color, wear=item.wear, sold=False,
            source=OpenRecord.SRC_SHOP)
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
