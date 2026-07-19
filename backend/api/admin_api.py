"""Custom admin panel API (replaces the built-in Django admin UI).

All endpoints are session-authenticated and restricted to staff users.
The admin front-end (admin/index.html) is a thin client that calls these.
"""
from datetime import timedelta

from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from .authentication import CsrfExemptSession
from .models import (
    AdminAction, Case, CaseItem, CoinPurchase, Drop, FreeCase, OpenRecord,
    PaymentAdmin, Player, PromoCode, TopUpMessage, TopUpRequest, WithdrawRequest,
)
from .telegram_bot import (
    _pay as _credit_topup, notify, notify_topup_admin_reply, notify_withdraw,
)


def _log(request, action, detail="", target=None):
    """Write one audit-log row for a mutating admin action."""
    actor = getattr(getattr(request, "user", None), "username", "") or "admin"
    AdminAction.objects.create(actor=actor, action=action,
                               detail=detail[:300], target_player=target)


def _case_row(c):
    return {
        "id": c.id,
        "name": c.name,
        "price": c.price,
        "image": c.image,
        "openings": c.openings,
        "items_count": getattr(c, "n_items", None),
        "is_new": c.is_new,
    }


# ---------- auth ----------
@api_view(["GET"])
@authentication_classes([CsrfExemptSession])
@permission_classes([AllowAny])
def admin_me(request):
    u = request.user
    if u.is_authenticated and u.is_staff:
        return Response({"authenticated": True, "username": u.username})
    return Response({"authenticated": False})


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([AllowAny])
def admin_login(request):
    user = authenticate(
        request,
        username=(request.data.get("username") or "").strip(),
        password=request.data.get("password") or "",
    )
    if user is None or not user.is_staff:
        return Response({"error": "Login yoki parol noto'g'ri"}, status=400)
    login(request._request, user)
    return Response({"authenticated": True, "username": user.username})


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([AllowAny])
def admin_logout(request):
    logout(request._request)
    return Response({"authenticated": False})


# ---------- data ----------
@api_view(["GET"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_stats(request):
    day_ago = timezone.now() - timedelta(hours=24)
    return Response({
        "cases": Case.objects.count(),
        "skins": CaseItem.objects.values("name").distinct().count(),
        "items": CaseItem.objects.count(),
        "drops": Drop.objects.count(),
        "players": Player.objects.count(),
        "opens": OpenRecord.objects.count(),
        # Withdraws waiting on an admin — the queue that needs working today.
        "withdraws_pending": WithdrawRequest.objects.filter(
            status=WithdrawRequest.PENDING).count(),
        "withdraws_pending_24h": WithdrawRequest.objects.filter(
            status=WithdrawRequest.PENDING, created_at__gte=day_ago).count(),
        # Top-ups nobody has picked up yet — a player is sitting there waiting.
        "topups_waiting": TopUpRequest.objects.filter(
            status=TopUpRequest.WAITING).count(),
        "topups_waiting_24h": TopUpRequest.objects.filter(
            status=TopUpRequest.WAITING, created_at__gte=day_ago).count(),
        "payment_admins": PaymentAdmin.objects.filter(is_active=True).count(),
    })


# ---------- withdraw requests ----------
def _withdraw_row(w):
    p, r = w.player, w.record
    return {
        "id": w.id,
        "player": {
            "id": p.id, "name": p.display_name, "username": p.username,
            "telegram_id": p.telegram_id, "photo_url": p.photo_url,
        },
        "skin": {
            "name": r.skin_name, "image": r.skin_image, "price": r.skin_price,
            "rarity": r.rarity, "color": r.color, "wear": r.wear,
        },
        "case_name": w.case_name,
        "trade_url": w.trade_url,
        "status": w.status,
        "reject_reason": w.reject_reason,
        "created_at": w.created_at.isoformat(),
        "updated_at": w.updated_at.isoformat(),
    }


@api_view(["GET"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_withdraws(request):
    """List withdraw requests, newest first, optionally filtered by status.
    `counts` feeds the filter tabs so they show a badge even while filtered."""
    status = (request.query_params.get("status") or "").strip()
    qs = WithdrawRequest.objects.select_related("player", "record")
    if status and status != "all":
        qs = qs.filter(status=status)
    counts = dict(WithdrawRequest.objects.values_list("status")
                  .annotate(n=Count("id")).values_list("status", "n"))
    return Response({
        "rows": [_withdraw_row(w) for w in qs[:300]],
        "counts": counts,
        "total": WithdrawRequest.objects.count(),
    })


def _advance(pk, allowed_from, new_status, reason=""):
    """Move a request `allowed_from` -> `new_status`, settle the skin, notify.

    The `allowed_from` guard is what keeps the flow one-way: a double-clicked
    button or a stale page cannot re-fire a step or skip one.
    """
    with transaction.atomic():
        w = (WithdrawRequest.objects.select_for_update()
             .select_related("player", "record").filter(pk=pk).first())
        if w is None:
            return Response({"error": "Topilmadi"}, status=404)
        if w.status != allowed_from:
            label = dict(WithdrawRequest.STATUSES).get(w.status, w.status)
            return Response(
                {"error": f"So'rov allaqachon «{label}» holatida — amalni "
                          f"qo'llab bo'lmaydi. Sahifani yangilang."},
                status=409)

        w.status = new_status
        w.reject_reason = reason
        w.save(update_fields=["status", "reject_reason", "updated_at"])

        if new_status == WithdrawRequest.REJECTED:
            # Hand the skin back — the player can withdraw it again.
            OpenRecord.objects.filter(pk=w.record_id).update(is_locked=False)
        elif new_status == WithdrawRequest.COMPLETED:
            # It lives in real Steam now, so it leaves the virtual inventory for
            # good. is_locked stays on so it can never be re-withdrawn.
            OpenRecord.objects.filter(pk=w.record_id).update(
                sold=True, disposition=OpenRecord.DISP_WITHDRAWN)

    # Outside the transaction: a slow or failing Telegram call must not roll
    # back a status the admin already committed.
    notify_withdraw(w.player.telegram_id, new_status, w.record.skin_name, reason)
    return Response({"ok": True, "row": _withdraw_row(w)})


# ---------- payment admins ----------
def _padmin_row(a):
    return {
        "id": a.id, "tg_chat_id": a.tg_chat_id, "name": a.name,
        "card_number": a.card_number, "card_holder": a.card_holder,
        "is_active": a.is_active,
        "topups": getattr(a, "n_topups", None),
        "created_at": a.created_at.isoformat(),
    }


@api_view(["GET", "POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_payment_admins(request):
    """List, or add, the people who take real payments over the bot."""
    if request.method == "GET":
        qs = PaymentAdmin.objects.annotate(n_topups=Count("topups"))
        return Response([_padmin_row(a) for a in qs])

    try:
        chat_id = int(str(request.data.get("tg_chat_id")).strip())
    except (TypeError, ValueError):
        return Response({"error": "Telegram chat ID raqam bo'lishi kerak"}, status=400)
    name = (request.data.get("name") or "").strip()
    card = (request.data.get("card_number") or "").strip()
    holder = (request.data.get("card_holder") or "").strip()
    if not (name and card and holder):
        return Response({"error": "Ism, karta raqami va karta egasini to'ldiring"},
                        status=400)
    if PaymentAdmin.objects.filter(tg_chat_id=chat_id).exists():
        return Response({"error": "Bu chat ID allaqachon qo'shilgan"}, status=400)

    a = PaymentAdmin.objects.create(tg_chat_id=chat_id, name=name,
                                    card_number=card, card_holder=holder)
    return Response({"ok": True, "row": _padmin_row(a)})


@api_view(["POST", "DELETE"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_payment_admin_detail(request, pk):
    """DELETE removes an admin; POST toggles them on/off."""
    a = PaymentAdmin.objects.filter(pk=pk).first()
    if a is None:
        return Response({"error": "Topilmadi"}, status=404)
    if request.method == "DELETE":
        # A live conversation would be orphaned — close it first, handing back
        # any promo the player never actually got the benefit of.
        for req in TopUpRequest.objects.filter(
                admin=a, status__in=TopUpRequest.OPEN_STATUSES):
            req.release_promo()
            req.status = TopUpRequest.CLOSED
            req.save(update_fields=["status", "updated_at"])
        a.delete()
        return Response({"ok": True})
    a.is_active = not a.is_active
    a.save(update_fields=["is_active"])
    return Response({"ok": True, "row": _padmin_row(a)})


# ---------- promo codes ----------
def _promo_row(p):
    return {
        "id": p.id, "code": p.code, "kind": p.kind,
        "bonus_percent": p.bonus_percent,
        "case": {"id": p.case_id, "name": p.case.name} if p.case else None,
        "reward": p.reward,
        "max_uses": p.max_uses, "uses": p.uses, "is_spent": p.is_spent,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat(),
    }


@api_view(["GET", "POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_promos(request):
    if request.method == "GET":
        return Response([_promo_row(p) for p in
                         PromoCode.objects.select_related("case")])

    code = (request.data.get("code") or "").strip().upper()
    if not code:
        return Response({"error": "Promokodni yozing"}, status=400)
    if PromoCode.objects.filter(code=code).exists():
        return Response({"error": "Bunday promokod bor"}, status=400)

    kind = request.data.get("kind") or PromoCode.KIND_BONUS
    if kind not in dict(PromoCode.KINDS):
        return Response({"error": "Promokod turini tanlang"}, status=400)

    try:
        max_uses = int(request.data.get("max_uses") or 0)
    except (TypeError, ValueError):
        return Response({"error": "Aktivatsiya sonini raqam bilan yozing"}, status=400)
    if max_uses < 0:
        return Response({"error": "Aktivatsiya soni manfiy bo'lmasin"}, status=400)

    fields = {"code": code, "kind": kind, "max_uses": max_uses}
    if kind == PromoCode.KIND_BONUS:
        try:
            bonus = int(request.data.get("bonus_percent"))
        except (TypeError, ValueError):
            return Response({"error": "Bonus foizini raqam bilan yozing"}, status=400)
        if not 0 < bonus <= 500:
            return Response({"error": "Bonus 1% dan 500% gacha bo'lsin"}, status=400)
        fields["bonus_percent"] = bonus
    else:
        case = Case.objects.filter(pk=request.data.get("case_id")).first()
        if case is None:
            return Response({"error": "Keysni tanlang"}, status=400)
        fields["case"] = case

    p = PromoCode.objects.create(**fields)
    return Response({"ok": True, "row": _promo_row(p)})


@api_view(["POST", "DELETE"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_promo_detail(request, pk):
    p = PromoCode.objects.filter(pk=pk).first()
    if p is None:
        return Response({"error": "Topilmadi"}, status=404)
    if request.method == "DELETE":
        p.delete()
        return Response({"ok": True})
    p.is_active = not p.is_active
    p.save(update_fields=["is_active"])
    return Response({"ok": True, "row": _promo_row(p)})


# ---------- top-up requests ----------
@api_view(["GET"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_topups(request):
    status = (request.query_params.get("status") or "").strip()
    qs = TopUpRequest.objects.select_related("player", "admin", "promo")
    if status and status != "all":
        qs = qs.filter(status=status)
    counts = dict(TopUpRequest.objects.values_list("status")
                  .annotate(n=Count("id")).values_list("status", "n"))
    rows = [{
        "id": t.id,
        "player": {"id": t.player_id, "name": t.player.display_name,
                   "username": t.player.username,
                   "telegram_id": t.player.telegram_id},
        "admin": t.admin.name if t.admin else None,
        "amount_sum": t.amount_sum, "coins": t.coins,
        "promo": t.promo.code if t.promo else None,
        "bonus_percent": t.bonus_percent,
        "status": t.status,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
    } for t in qs[:300]]
    return Response({"rows": rows, "counts": counts,
                     "total": TopUpRequest.objects.count()})


# ---------- top-up chat (web inbox: many conversations at once) ----------
def _msg_json(m):
    read = m.read_by_admin if m.sender == TopUpMessage.USER else m.read_by_user
    return {"id": m.id, "sender": m.sender, "text": m.text,
            "image": m.image.url if m.image else None,
            "at": m.created_at.strftime("%H:%M"), "read": read}


def _canned(req, kind):
    """The three quick replies, worded for the player."""
    if kind == "card":
        a = req.admin
        if not a:
            return "Karta hali biriktirilmagan."
        amt = f"{req.amount_sum:,}".replace(",", " ")
        return (f"💳 To'lov uchun karta:\n{a.card_number}\n{a.card_holder}\n\n"
                f"Shunga {amt} so'm o'tkazib, check (skrinshot) yuboring.")
    if kind == "soon":
        coins = f"{req.coins:,}".replace(",", " ")
        return f"⏳ 2 daqiqada balansingiz {coins} coinga to'ladi."
    if kind == "bad":
        return "❌ Check noto'g'ri yoki soxta. Iltimos, qayta to'lov qiling."
    return ""


def _chat_row(t, unread):
    return {
        "id": t.id,
        "player": {"name": t.player.display_name, "username": t.player.username,
                   "telegram_id": t.player.telegram_id, "photo": t.player.photo_url},
        "admin": t.admin.name if t.admin else None,
        "amount_sum": t.amount_sum, "coins": t.coins, "bonus_percent": t.bonus_percent,
        "promo": t.promo.code if t.promo else None,
        "status": t.status,
        "unread": unread.get(t.id, 0),
        "updated_at": t.updated_at.isoformat(),
    }


@api_view(["GET"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_topup_chats(request):
    """Inbox: every top-up conversation, active first, with unread counts."""
    show = (request.query_params.get("filter") or "active").strip()
    qs = TopUpRequest.objects.select_related("player", "admin", "promo")
    if show == "active":
        qs = qs.filter(status__in=TopUpRequest.OPEN_STATUSES)
    qs = qs.order_by("-updated_at")[:200]
    reqs = list(qs)
    unread = dict(
        TopUpMessage.objects.filter(request__in=reqs, sender=TopUpMessage.USER,
                                    read_by_admin=False)
        .values_list("request").annotate(n=Count("id")).values_list("request", "n"))
    waiting = TopUpRequest.objects.filter(status__in=TopUpRequest.OPEN_STATUSES).count()
    total_unread = sum(unread.values())
    return Response({"rows": [_chat_row(t, unread) for t in reqs],
                     "active": waiting, "unread": total_unread})


@api_view(["GET"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_topup_chat(request, pk):
    """One conversation's full message history; marks the user's as read."""
    t = (TopUpRequest.objects.select_related("player", "admin", "promo")
         .filter(pk=pk).first())
    if t is None:
        return Response({"error": "Topilmadi"}, status=404)
    t.messages.filter(sender=TopUpMessage.USER, read_by_admin=False).update(
        read_by_admin=True)
    a = t.admin
    return Response({
        "id": t.id, "status": t.status,
        "player": {"name": t.player.display_name, "username": t.player.username,
                   "telegram_id": t.player.telegram_id, "photo": t.player.photo_url,
                   "balance": t.player.balance},
        "amount_sum": t.amount_sum, "coins": t.coins, "bonus_percent": t.bonus_percent,
        "promo": t.promo.code if t.promo else None,
        "card": {"number": a.card_number, "holder": a.card_holder, "name": a.name} if a else None,
        "messages": [_msg_json(m) for m in t.messages.all()],
    })


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_topup_send(request, pk):
    """Admin sends a message — free text, or a canned reply via ``kind``."""
    t = TopUpRequest.objects.select_related("player", "admin").filter(pk=pk).first()
    if t is None:
        return Response({"error": "Topilmadi"}, status=404)
    if t.status not in TopUpRequest.OPEN_STATUSES:
        return Response({"error": "Bu suhbat yopilgan"}, status=400)
    kind = request.data.get("kind")
    text = _canned(t, kind) if kind else (request.data.get("text") or "").strip()[:2000]
    if not text:
        return Response({"error": "Xabar bo'sh"}, status=400)
    msg = TopUpMessage.objects.create(
        request=t, sender=TopUpMessage.ADMIN, text=text, read_by_admin=True)
    if t.status == TopUpRequest.WAITING:
        t.status = TopUpRequest.CONNECTED
        t.save(update_fields=["status", "updated_at"])
    else:
        t.save(update_fields=["updated_at"])
    notify_topup_admin_reply(t.player.telegram_id)   # nudge on Telegram
    return Response({"ok": True, "message": _msg_json(msg), "status": t.status})


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_topup_pay(request, pk):
    """Credit the promised coins (idempotent; notifies the player)."""
    t = TopUpRequest.objects.filter(pk=pk).first()
    if t is None:
        return Response({"error": "Topilmadi"}, status=404)
    err = _credit_topup(t)      # bot's crediting logic: atomic + CoinPurchase + notify
    if err:
        return Response({"error": err}, status=400)
    TopUpMessage.objects.create(
        request=t, sender=TopUpMessage.ADMIN, read_by_admin=True,
        text=f"✅ Balansingiz {t.coins:,} coinga to'ldirildi. Rahmat!".replace(",", " "))
    t.refresh_from_db()
    return Response({"ok": True, "status": t.status})


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_topup_close(request, pk):
    t = TopUpRequest.objects.filter(pk=pk).first()
    if t is None:
        return Response({"error": "Topilmadi"}, status=404)
    if t.status != TopUpRequest.PAID:
        t.release_promo()
        t.status = TopUpRequest.CLOSED
        t.save(update_fields=["status", "updated_at"])
        from .telegram_bot import notify
        notify(t.player.telegram_id, "🔚 To'lov suhbati yopildi.")
    return Response({"ok": True, "status": t.status})


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_withdraw_approve(request, pk):
    return _advance(pk, WithdrawRequest.PENDING, WithdrawRequest.APPROVED)


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_withdraw_reject(request, pk):
    reason = (request.data.get("reason") or "").strip()
    if not reason:
        return Response({"error": "Rad etish sababini yozing"}, status=400)
    return _advance(pk, WithdrawRequest.PENDING, WithdrawRequest.REJECTED, reason)


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_withdraw_mark_sent(request, pk):
    """Admin has sent the trade offer by hand in Steam."""
    return _advance(pk, WithdrawRequest.APPROVED, WithdrawRequest.SENT)


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_withdraw_complete(request, pk):
    """Player accepted the offer — the skin is really theirs now."""
    return _advance(pk, WithdrawRequest.SENT, WithdrawRequest.COMPLETED)


# ---------- users / players ----------
def _player_row(p):
    return {
        "id": p.id,
        "name": p.display_name,
        "username": p.username,
        "telegram_id": p.telegram_id,
        "photo_url": p.photo_url,
        "balance": p.balance,
        "coins_purchased": p.coins_purchased,
        "opens_count": getattr(p, "opens_count", None),
        "is_banned": p.is_banned,
        "ban_reason": p.ban_reason,
        "created_at": p.created_at.isoformat(),
        "last_seen": p.last_seen.isoformat(),
    }


@api_view(["GET"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_users(request):
    q = (request.query_params.get("q") or "").strip()
    filt = (request.query_params.get("filter") or "all").strip()
    sort = (request.query_params.get("sort") or "new").strip()
    qs = Player.objects.annotate(opens_count=Count("opens"))
    if q:
        qs = (qs.filter(first_name__icontains=q) | qs.filter(username__icontains=q)
              | qs.filter(telegram_id__icontains=q))
    if filt == "banned":
        qs = qs.filter(is_banned=True)
    elif filt == "active":
        qs = qs.filter(is_banned=False)
    order = {
        "new": "-created_at", "old": "created_at",
        "rich": "-balance", "poor": "balance",
        "active_seen": "-last_seen", "opens": "-opens_count",
    }.get(sort, "-created_at")
    return Response([_player_row(p) for p in qs.order_by(order)[:400]])


@api_view(["GET"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_user_detail(request, pk):
    p = Player.objects.filter(pk=pk).annotate(opens_count=Count("opens")).first()
    if p is None:
        return Response({"error": "Topilmadi"}, status=404)
    opens = [
        {
            "case": o.case_name, "skin": o.skin_name, "image": o.skin_image,
            "price": o.skin_price, "rarity": o.rarity, "color": o.color,
            "wear": o.wear, "sold": o.sold, "created_at": o.created_at.isoformat(),
        }
        for o in p.opens.all()[:300]
    ]
    purchases = [
        {"amount": c.amount, "note": c.note, "created_at": c.created_at.isoformat()}
        for c in p.purchases.all()[:100]
    ]
    inventory = [
        {"id": o.id, "name": o.skin_name, "image": o.skin_image, "price": o.skin_price,
         "rarity": o.rarity, "color": o.color, "wear": o.wear}
        for o in p.opens.filter(sold=False, is_locked=False).order_by("-created_at")[:200]
    ]
    won_total = p.opens.aggregate(s=Sum("skin_price"))["s"] or 0
    return Response({
        "player": _player_row(p),
        "opens": opens,
        "inventory": inventory,
        "free_cases": p.free_cases.filter(used=False).count(),
        "purchases": purchases,
        "totals": {"opens": len(opens), "won_value": won_total,
                   "purchased": p.coins_purchased},
    })


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_give_coins(request, pk):
    """Give (or deduct) coins to a player — e.g. crediting someone who donated.
    Records a CoinPurchase row so it shows in the player's coin history."""
    p = Player.objects.filter(pk=pk).first()
    if p is None:
        return Response({"error": "Topilmadi"}, status=404)
    try:
        amount = int(request.data.get("amount"))
    except (TypeError, ValueError):
        amount = 0
    if amount == 0:
        return Response({"error": "Miqdorni kiriting"}, status=400)
    note = (request.data.get("note") or "").strip() or "Admin tomonidan berildi"

    p.balance += amount
    if amount > 0:
        p.coins_purchased += amount
    p.balance = max(0, p.balance)   # never go negative
    p.save(update_fields=["balance", "coins_purchased", "last_seen"])
    CoinPurchase.objects.create(player=p, amount=amount, note=note)
    _log(request, "coins", f"{'+' if amount > 0 else ''}{amount} coin → {p.display_name}", p)
    return Response({"ok": True, "balance": p.balance,
                     "coins_purchased": p.coins_purchased})


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_user_ban(request, pk):
    """Toggle a player's ban. Banned players can't open cases, withdraw or top up."""
    p = Player.objects.filter(pk=pk).first()
    if p is None:
        return Response({"error": "Topilmadi"}, status=404)
    p.is_banned = not p.is_banned
    p.ban_reason = (request.data.get("reason") or "").strip()[:200] if p.is_banned else ""
    p.save(update_fields=["is_banned", "ban_reason"])
    _log(request, "ban" if p.is_banned else "unban",
         f"{p.display_name}" + (f" — {p.ban_reason}" if p.ban_reason else ""), p)
    if p.is_banned and p.telegram_id:
        notify(p.telegram_id, "⛔️ Hisobingiz bloklandi." +
               (f"\nSabab: {p.ban_reason}" if p.ban_reason else ""))
    return Response({"ok": True, "is_banned": p.is_banned, "ban_reason": p.ban_reason})


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_give_skin(request, pk):
    """Drop a catalog skin (a CaseItem) straight into a player's inventory."""
    p = Player.objects.filter(pk=pk).first()
    if p is None:
        return Response({"error": "Topilmadi"}, status=404)
    it = CaseItem.objects.select_related("case").filter(pk=request.data.get("item_id")).first()
    if it is None:
        return Response({"error": "Skinni tanlang"}, status=400)
    rec = OpenRecord.objects.create(
        player=p, case=it.case, case_name=it.case.name if it.case else "Admin",
        skin_name=it.name, skin_image=it.image, skin_price=it.price,
        rarity=it.rarity, color=it.color, wear=it.wear, source=OpenRecord.SRC_SHOP)
    _log(request, "give_skin", f"«{it.name}» ({it.price}) → {p.display_name}", p)
    return Response({"ok": True, "record_id": rec.id})


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_take_skin(request, pk):
    """Remove a skin (an OpenRecord) from a player's inventory."""
    p = Player.objects.filter(pk=pk).first()
    if p is None:
        return Response({"error": "Topilmadi"}, status=404)
    rec = p.opens.filter(pk=request.data.get("record_id")).first()
    if rec is None:
        return Response({"error": "Skin topilmadi"}, status=404)
    name = rec.skin_name
    rec.delete()
    _log(request, "take_skin", f"«{name}» ← {p.display_name}", p)
    return Response({"ok": True})


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_give_free_case(request, pk):
    """Grant a player a free opening of a case (like the daily reward)."""
    p = Player.objects.filter(pk=pk).first()
    if p is None:
        return Response({"error": "Topilmadi"}, status=404)
    case = Case.objects.filter(pk=request.data.get("case_id")).first()
    if case is None:
        return Response({"error": "Keysni tanlang"}, status=400)
    try:
        n = max(1, min(20, int(request.data.get("count") or 1)))
    except (TypeError, ValueError):
        n = 1
    FreeCase.objects.bulk_create([FreeCase(player=p, case=case) for _ in range(n)])
    _log(request, "free_case", f"{n}× «{case.name}» → {p.display_name}", p)
    if p.telegram_id:
        notify(p.telegram_id, f"🎁 Sizga {n} ta bepul «{case.name}» keysi berildi!")
    return Response({"ok": True})


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_message_user(request, pk):
    """Send a one-off Telegram message to a player."""
    p = Player.objects.filter(pk=pk).first()
    if p is None:
        return Response({"error": "Topilmadi"}, status=404)
    text = (request.data.get("text") or "").strip()[:1500]
    if not text:
        return Response({"error": "Xabar bo'sh"}, status=400)
    if not p.telegram_id:
        return Response({"error": "Bu foydalanuvchida Telegram yo'q"}, status=400)
    notify(p.telegram_id, f"✉️ <b>Admin:</b>\n{text}")
    _log(request, "message", f"→ {p.display_name}: {text[:60]}", p)
    return Response({"ok": True})


@api_view(["GET"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_audit(request):
    """The audit log — every mutating admin action, newest first."""
    rows = AdminAction.objects.all()[:300]
    return Response([{
        "actor": a.actor, "action": a.action, "detail": a.detail,
        "player_id": a.target_player_id,
        "at": a.created_at.strftime("%d.%m %H:%M"),
    } for a in rows])


@api_view(["GET"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_skin_search(request):
    """Catalog skin picker for 'give skin' — search CaseItems by name."""
    q = (request.query_params.get("q") or "").strip()
    qs = CaseItem.objects.all()
    if q:
        qs = qs.filter(name__icontains=q)
    return Response([
        {"id": it.id, "name": it.name, "price": it.price, "image": it.image,
         "rarity": it.rarity, "color": it.color, "wear": it.wear}
        for it in qs.order_by("-price")[:40]
    ])


def _num(v, default=0, cast=int):
    try:
        return cast(v)
    except (TypeError, ValueError):
        return default


@api_view(["GET", "POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_cases(request):
    if request.method == "GET":
        q = (request.query_params.get("q") or "").strip()
        qs = Case.objects.annotate(n_items=Count("items")).order_by("sort_order", "price")
        if q:
            qs = qs.filter(name__icontains=q)
        return Response([_case_row(c) for c in qs])

    # ---- create a case ----
    name = (request.data.get("name") or "").strip()
    if not name:
        return Response({"error": "Keys nomini yozing"}, status=400)
    if Case.objects.filter(name=name).exists():
        return Response({"error": "Bunday nomli keys bor"}, status=400)
    price = _num(request.data.get("price"), 0)
    if price <= 0:
        return Response({"error": "Narxni to'g'ri kiriting"}, status=400)
    c = Case.objects.create(
        name=name, price=price,
        image=(request.data.get("image") or "").strip(),
        is_new=bool(request.data.get("is_new")),
        sort_order=_num(request.data.get("sort_order"), 0))
    c.n_items = 0
    _log(request, "case_add", f"«{name}» ({price})")
    return Response({"ok": True, "row": _case_row(c)})


@api_view(["GET", "POST", "DELETE"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_case_detail(request, pk):
    case = Case.objects.filter(pk=pk).first()
    if case is None:
        return Response({"error": "Topilmadi"}, status=404)

    if request.method == "DELETE":
        name = case.name
        case.delete()
        _log(request, "case_del", f"«{name}»")
        return Response({"ok": True})

    if request.method == "POST":
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"error": "Keys nomini yozing"}, status=400)
        if Case.objects.filter(name=name).exclude(pk=pk).exists():
            return Response({"error": "Bunday nomli keys bor"}, status=400)
        case.name = name
        case.price = _num(request.data.get("price"), case.price)
        if "image" in request.data:
            case.image = (request.data.get("image") or "").strip()
        if "sort_order" in request.data:
            case.sort_order = _num(request.data.get("sort_order"), case.sort_order)
        if "is_new" in request.data:
            case.is_new = bool(request.data.get("is_new"))
        case.save()
        _log(request, "case_edit", f"«{case.name}»")
        case.n_items = case.items.count()
        return Response({"ok": True, "row": _case_row(case)})

    case = Case.objects.filter(pk=pk).annotate(n_items=Count("items")).first()
    items = [_item_row(it) for it in case.items.all().order_by("chance")]
    return Response({"case": _case_row(case), "items": items})


def _item_row(it):
    return {
        "id": it.id, "name": it.name, "weapon": it.weapon, "finish": it.finish,
        "wear": it.wear, "chance": it.chance, "price": it.price,
        "rarity": it.rarity, "color": it.color, "image": it.image,
    }


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_case_items(request, pk):
    """Add a skin to a case."""
    case = Case.objects.filter(pk=pk).first()
    if case is None:
        return Response({"error": "Keys topilmadi"}, status=404)
    name = (request.data.get("name") or "").strip()
    if not name:
        return Response({"error": "Skin nomini yozing"}, status=400)
    chance = _num(request.data.get("chance"), -1, float)
    if chance <= 0:
        return Response({"error": "Ehtimol (%) 0 dan katta bo'lsin"}, status=400)
    it = CaseItem.objects.create(
        case=case, name=name,
        weapon=(request.data.get("weapon") or "").strip(),
        finish=(request.data.get("finish") or "").strip(),
        wear=(request.data.get("wear") or "").strip(),
        chance=chance, price=_num(request.data.get("price"), 0),
        rarity=(request.data.get("rarity") or "").strip(),
        color=(request.data.get("color") or "").strip(),
        image=(request.data.get("image") or "").strip())
    _log(request, "skin_add", f"«{name}» → {case.name}")
    return Response({"ok": True, "item": _item_row(it)})


@api_view(["POST", "DELETE"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_case_item_detail(request, pk):
    """Edit or delete one skin in a case."""
    it = CaseItem.objects.select_related("case").filter(pk=pk).first()
    if it is None:
        return Response({"error": "Topilmadi"}, status=404)
    if request.method == "DELETE":
        name = it.name
        it.delete()
        _log(request, "skin_del", f"«{name}»")
        return Response({"ok": True})
    for f in ("name", "weapon", "finish", "wear", "rarity", "color", "image"):
        if f in request.data:
            setattr(it, f, (request.data.get(f) or "").strip())
    if "chance" in request.data:
        ch = _num(request.data.get("chance"), it.chance, float)
        if ch <= 0:
            return Response({"error": "Ehtimol (%) 0 dan katta bo'lsin"}, status=400)
        it.chance = ch
    if "price" in request.data:
        it.price = _num(request.data.get("price"), it.price)
    it.save()
    _log(request, "skin_edit", f"«{it.name}»")
    return Response({"ok": True, "item": _item_row(it)})
