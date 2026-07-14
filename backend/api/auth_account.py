"""SKINRUSH native accounts — register & login with a password.

Registration asks for email (gmail), username, phone and password. Login accepts
either the username OR the phone number, both with the password. The Django
``User`` holds username/email/password; the linked ``Player`` holds the phone.
Telegram/Google are separate providers added elsewhere.
"""
import re

from django.contrib.auth import login
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .authentication import CsrfExemptSession
from .auth_telegram import player_payload
from .models import Player

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _norm_phone(raw):
    """Digits only, so '+998 90 111 99 99' and '998901119999' match the same key."""
    return re.sub(r"[^\d]", "", raw or "")


def _err(msg, status=400):
    return Response({"error": msg}, status=status)


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([AllowAny])
def register(request):
    d = request.data
    email = (d.get("email") or "").strip().lower()
    username = (d.get("username") or "").strip()
    phone = _norm_phone(d.get("phone"))
    password = d.get("password") or ""

    # --- validation ---
    if not (email and username and phone and password):
        return _err("Barcha maydonlarni to'ldiring")
    if not EMAIL_RE.match(email):
        return _err("Email noto'g'ri")
    if not USERNAME_RE.match(username):
        return _err("Username 3-32 ta harf/raqam bo'lishi kerak")
    if len(phone) < 7:
        return _err("Telefon raqam noto'g'ri")
    if len(password) < 6:
        return _err("Parol kamida 6 ta belgi bo'lishi kerak")

    # --- uniqueness ---
    if User.objects.filter(username__iexact=username).exists():
        return _err("Bu username band")
    if User.objects.filter(email__iexact=email).exists():
        return _err("Bu email allaqachon ro'yxatdan o'tgan")
    if Player.objects.filter(phone=phone).exists():
        return _err("Bu telefon raqam band")

    with transaction.atomic():
        user = User.objects.create_user(username=username, email=email, password=password)
        player = Player.objects.create(
            user=user, username=username, first_name=username, phone=phone
        )

    user.backend = "django.contrib.auth.backends.ModelBackend"
    login(request._request, user)
    return Response(player_payload(player))


@api_view(["POST"])
@authentication_classes([CsrfExemptSession])
@permission_classes([AllowAny])
def account_login(request):
    d = request.data
    ident = (d.get("login") or "").strip()
    password = d.get("password") or ""
    if not (ident and password):
        return _err("Login va parolni kiriting")

    # Resolve the account by username first, then by phone number.
    user = User.objects.filter(username__iexact=ident).first()
    if user is None:
        player = Player.objects.filter(phone=_norm_phone(ident)).first()
        user = player.user if player else None

    if user is None or not user.check_password(password):
        return _err("Login yoki parol noto'g'ri", status=401)

    try:
        player = user.player
    except Player.DoesNotExist:
        player = Player.objects.create(user=user, username=user.username, first_name=user.username)

    user.backend = "django.contrib.auth.backends.ModelBackend"
    login(request._request, user)
    return Response(player_payload(player))
