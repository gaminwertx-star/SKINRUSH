"""Custom admin panel API (replaces the built-in Django admin UI).

All endpoints are session-authenticated and restricted to staff users.
The admin front-end (admin/index.html) is a thin client that calls these.
"""
from django.contrib.auth import authenticate, login, logout
from django.db.models import Count, Sum
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from .authentication import CsrfExemptSession
from .models import Case, CaseItem, CoinPurchase, Drop, OpenRecord, Player


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
    return Response({
        "cases": Case.objects.count(),
        "skins": CaseItem.objects.values("name").distinct().count(),
        "items": CaseItem.objects.count(),
        "drops": Drop.objects.count(),
        "players": Player.objects.count(),
        "opens": OpenRecord.objects.count(),
    })


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
        "created_at": p.created_at.isoformat(),
        "last_seen": p.last_seen.isoformat(),
    }


@api_view(["GET"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_users(request):
    q = (request.query_params.get("q") or "").strip()
    qs = Player.objects.annotate(opens_count=Count("opens")).order_by("-created_at")
    if q:
        qs = qs.filter(first_name__icontains=q) | qs.filter(username__icontains=q)
    return Response([_player_row(p) for p in qs])


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
    won_total = p.opens.aggregate(s=Sum("skin_price"))["s"] or 0
    return Response({
        "player": _player_row(p),
        "opens": opens,
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
    return Response({"ok": True, "balance": p.balance,
                     "coins_purchased": p.coins_purchased})


@api_view(["GET"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_cases(request):
    q = (request.query_params.get("q") or "").strip()
    qs = Case.objects.annotate(n_items=Count("items")).order_by("sort_order", "price")
    if q:
        qs = qs.filter(name__icontains=q)
    return Response([_case_row(c) for c in qs])


@api_view(["GET"])
@authentication_classes([CsrfExemptSession])
@permission_classes([IsAdminUser])
def admin_case_detail(request, pk):
    case = Case.objects.filter(pk=pk).annotate(n_items=Count("items")).first()
    if case is None:
        return Response({"error": "Topilmadi"}, status=404)
    items = [
        {
            "id": it.id, "name": it.name, "weapon": it.weapon, "finish": it.finish,
            "wear": it.wear, "chance": it.chance, "price": it.price,
            "rarity": it.rarity, "color": it.color, "image": it.image,
        }
        for it in case.items.all().order_by("chance")
    ]
    return Response({"case": _case_row(case), "items": items})
