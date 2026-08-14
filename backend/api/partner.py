"""Partner program: a player creates their own 20%-bonus top-up promo code
and earns a 10% commission (real so'm, not coins) every time someone tops up
using it. There is no automated payout — once a partner's balance reaches
the threshold they're told to contact the admin, who pays by hand and marks
the request PAID from the admin panel.
"""
import re

from django.db import transaction
from django.db.models import F

from .models import Partner, PartnerEarning, PartnerWithdrawRequest, PromoCode

BONUS_PERCENT = 20        # the bonus a buyer gets for using a partner's code
COMMISSION_PERCENT = 10   # the partner's cut of what that buyer pays
PAYOUT_MIN = 100_000       # so'm — minimum balance before a payout can be requested
CONTACT_USERNAME = "wiiixr"

_CODE_RE = re.compile(r"^\d{6}$")


def _fmt(n):
    return f"{int(n):,}".replace(",", " ")


def _notify(player, text):
    try:
        from .telegram_bot import notify
        if player and player.telegram_id:
            notify(player.telegram_id, text)
    except Exception:
        pass


def create(player, code):
    """Turn `player` into a partner with their own 20%-bonus promo `code`
    (must be exactly 6 digits, globally unique). Returns (partner, error)."""
    if hasattr(player, "partner"):
        return None, "Sizda allaqachon hamkor promokodi bor"
    code = (code or "").strip()
    if not _CODE_RE.match(code):
        return None, "Kod aynan 6 ta raqamdan iborat bo'lsin"
    if PromoCode.objects.filter(code=code).exists():
        return None, "Bu kod band, boshqa kod tanlang"
    with transaction.atomic():
        promo = PromoCode.objects.create(
            code=code, kind=PromoCode.KIND_BONUS, bonus_percent=BONUS_PERCENT,
            max_uses=0, is_active=True)
        partner = Partner.objects.create(player=player, promo=promo)
    return partner, None


def credit_topup(topup):
    """Called once a top-up is marked PAID: if it used a partner's promo,
    credit that partner COMMISSION_PERCENT of what the buyer paid.
    Idempotent — PartnerEarning.topup is a OneToOne, so a second call for
    the same top-up is a no-op."""
    if not topup.promo_id:
        return
    partner = Partner.objects.filter(promo_id=topup.promo_id).select_related("player").first()
    if not partner or partner.player_id == topup.player_id:
        return  # no code, or the "referred" buyer is the partner themself
    if PartnerEarning.objects.filter(topup_id=topup.pk).exists():
        return
    commission = topup.amount_sum * COMMISSION_PERCENT // 100
    if commission <= 0:
        return
    with transaction.atomic():
        p = Partner.objects.select_for_update().get(pk=partner.pk)
        if PartnerEarning.objects.filter(topup_id=topup.pk).exists():
            return
        p.balance = F("balance") + commission
        p.total_earned = F("total_earned") + commission
        p.save(update_fields=["balance", "total_earned"])
        PartnerEarning.objects.create(
            partner=p, referred_id=topup.player_id, topup=topup,
            amount_sum=topup.amount_sum, commission=commission)
    p.refresh_from_db()
    _notify(p.player, f"💸 +{_fmt(commission)} so'm! Promokodingiz orqali to'lov qilindi.\n"
                       f"Hamkor balansingiz: {_fmt(p.balance)} so'm")


def stats(partner):
    earnings_qs = partner.earnings.select_related("referred").order_by("-created_at")
    earnings = list(earnings_qs[:50])
    referred_count = earnings_qs.values("referred_id").distinct().count()
    pending_withdraw = partner.withdraw_requests.filter(
        status=PartnerWithdrawRequest.WAITING).first()
    return {
        "code": partner.promo.code,
        "is_active": partner.promo.is_active,
        "bonus_percent": BONUS_PERCENT,
        "commission_percent": COMMISSION_PERCENT,
        "balance": partner.balance,
        "total_earned": partner.total_earned,
        "referred_count": referred_count,
        "purchases_count": earnings_qs.count(),
        "payout_min": PAYOUT_MIN,
        "progress_pct": min(100, partner.balance * 100 // PAYOUT_MIN) if PAYOUT_MIN else 100,
        "can_request": partner.balance >= PAYOUT_MIN and not pending_withdraw,
        "pending_withdraw": pending_withdraw,
        "contact_username": CONTACT_USERNAME,
        "earnings": [{"referred": e.referred.display_name, "amount_sum": e.amount_sum,
                     "commission": e.commission, "at": e.created_at} for e in earnings],
    }


def request_withdraw(partner):
    """A partner asking to be paid out. Returns (request, error)."""
    if partner.balance < PAYOUT_MIN:
        return None, f"Chiqarish uchun kamida {_fmt(PAYOUT_MIN)} so'm balans kerak"
    if partner.withdraw_requests.filter(status=PartnerWithdrawRequest.WAITING).exists():
        return None, "Sizda allaqachon kutilayotgan so'rov bor"
    req = PartnerWithdrawRequest.objects.create(partner=partner, amount=partner.balance)
    return req, None
