"""Referral system: personal codes, linking, join reward, 5% top-up share,
invite milestones, stats and leaderboard.

A friend who opens t.me/<bot>?start=<CODE> is linked to the referrer at /start
time (bot webhook). The referrer is paid only once the friend actually plays
(opens a case) or tops up — that plus one-referral-per-account and no
self-referral is the whole anti-fraud story.
"""
import random

from django.db import transaction
from django.db.models import F

from .models import Player, ReferralEarning

JOIN_REWARD = 500                                    # to the referrer when a friend qualifies
SHARE_PCT = 5                                        # % of a friend's top-ups, for life
MILESTONES = [(5, 2000), (10, 5000), (25, 15000)]    # (invited friends, bonus)

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"       # no ambiguous chars


def code_for(player):
    """The player's referral code, generated once on first use."""
    if player.ref_code:
        return player.ref_code
    for _ in range(30):
        code = "".join(random.choice(_ALPHABET) for _ in range(6))
        if not Player.objects.filter(ref_code=code).exists():
            player.ref_code = code
            player.save(update_fields=["ref_code"])
            return code
    player.ref_code = "U" + str(player.id)
    player.save(update_fields=["ref_code"])
    return player.ref_code


def _notify(player, text):
    try:
        from .telegram_bot import notify
        if player and player.telegram_id:
            notify(player.telegram_id, text)
    except Exception:
        pass


def link_player(friend, referrer):
    """Attach `friend` to `referrer` if eligible: not self, not already linked,
    and the friend is brand new (no case opens yet)."""
    if not friend or not referrer or friend.pk == referrer.pk:
        return False
    if friend.referred_by_id or friend.opens.exists():
        return False
    friend.referred_by = referrer
    friend.save(update_fields=["referred_by"])
    _notify(referrer, f"👥 Yangi do'st qo'shildi: {friend.display_name}!\n"
                      f"U o'ynay boshlasa, mukofot olasiz.")
    return True


def link_by_code(friend, code):
    """From a /start CODE deep link: find the referrer and link the friend."""
    code = (code or "").strip().upper()
    if not code:
        return False
    referrer = Player.objects.filter(ref_code=code).first()
    return link_player(friend, referrer) if referrer else False


def qualify(player):
    """A referred player's first qualifying action (case open / top-up) pays the
    referrer the join reward. Idempotent via ref_qualified."""
    if not player or player.ref_qualified or not player.referred_by_id:
        return
    referrer = None
    with transaction.atomic():
        p = Player.objects.select_for_update().get(pk=player.pk)
        if p.ref_qualified or not p.referred_by_id:
            return
        p.ref_qualified = True
        p.save(update_fields=["ref_qualified"])
        referrer = Player.objects.select_for_update().get(pk=p.referred_by_id)
        referrer.balance = F("balance") + JOIN_REWARD
        referrer.ref_earned = F("ref_earned") + JOIN_REWARD
        referrer.invited_count = F("invited_count") + 1
        referrer.save(update_fields=["balance", "ref_earned", "invited_count", "last_seen"])
        ReferralEarning.objects.create(referrer=referrer, referred=p,
                                       kind=ReferralEarning.JOIN, amount=JOIN_REWARD,
                                       note=p.display_name)
    referrer.refresh_from_db()
    _notify(referrer, f"🪙 +{JOIN_REWARD} coin! Do'stingiz {player.display_name} o'ynay boshladi.")
    check_milestones(referrer)


def check_milestones(referrer):
    """Pay any newly reached invite milestone bonus."""
    referrer.refresh_from_db()
    for count, bonus in MILESTONES:
        if referrer.invited_count >= count > referrer.ref_milestone:
            with transaction.atomic():
                r = Player.objects.select_for_update().get(pk=referrer.pk)
                if count <= r.ref_milestone:
                    continue
                r.ref_milestone = count
                r.balance = F("balance") + bonus
                r.ref_earned = F("ref_earned") + bonus
                r.save(update_fields=["ref_milestone", "balance", "ref_earned", "last_seen"])
                ReferralEarning.objects.create(referrer=r, kind=ReferralEarning.MILESTONE,
                                               amount=bonus, note=f"{count} do'st")
            _notify(referrer, f"🎁 {count} ta do'st bosqichi! +{bonus} coin sizga.")


def topup_share(player, coins_added):
    """5% of a referred player's top-up goes to their referrer, for life."""
    if not player or not player.referred_by_id or coins_added <= 0:
        return
    share = coins_added * SHARE_PCT // 100
    if share <= 0:
        return
    referrer = None
    with transaction.atomic():
        referrer = Player.objects.select_for_update().get(pk=player.referred_by_id)
        referrer.balance = F("balance") + share
        referrer.ref_earned = F("ref_earned") + share
        referrer.save(update_fields=["balance", "ref_earned", "last_seen"])
        ReferralEarning.objects.create(referrer=referrer, referred=player,
                                       kind=ReferralEarning.TOPUP, amount=share,
                                       note=player.display_name)
    referrer.refresh_from_db()
    _notify(referrer, f"🪙 +{share} coin — do'stingiz {player.display_name} balans to'ldirdi ({SHARE_PCT}%).")


def stats(player):
    refs = list(player.referrals.all())
    active = sum(1 for r in refs if r.ref_qualified)
    next_ms = next((c for c, _ in MILESTONES if player.invited_count < c), None)
    return {
        "code": code_for(player),
        "invited": player.invited_count,
        "total": len(refs),
        "active": active,
        "earned": player.ref_earned,
        "next_milestone": next_ms,
        "milestones": MILESTONES,
        "share_pct": SHARE_PCT,
        "join_reward": JOIN_REWARD,
        "friends": [{"name": r.display_name, "photo": r.photo,
                     "qualified": r.ref_qualified, "at": r.created_at}
                    for r in sorted(refs, key=lambda x: x.created_at, reverse=True)[:50]],
    }


def leaderboard(limit=20):
    rows = (Player.objects.filter(invited_count__gt=0)
            .order_by("-invited_count", "-ref_earned")[:limit])
    return [{"name": p.display_name, "photo": p.photo,
             "invited": p.invited_count, "earned": p.ref_earned} for p in rows]
