"""Minimal Telegram bot webhook for SKINRUSH.

The Django site is a *web app*, not a chat bot, so on its own it never replies to
messages. This module adds a tiny webhook endpoint that Telegram calls for every
update. When a user sends ``/start`` we reply with a welcome message plus a big
**web_app** inline button that opens the Mini App (auto-login happens there).

Register the webhook with ``python manage.py set_webhook`` — not by hand. That
command owns the ``allowed_updates`` list, and it has to match what `webhook`
below handles: Telegram silently drops any update type missing from it, so a
stale list makes the inline buttons do nothing at all with no error anywhere.

Env vars used: ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_WEBHOOK_SECRET``.
"""
import json
import os
import urllib.request

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

APP_URL = os.environ.get("MINIAPP_URL", "https://95-169-201-44.sslip.io/")


def _api(method, payload):
    """Call the Telegram Bot API (stdlib only, no requests dependency)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        # never let a Telegram-side hiccup 500 the webhook (Telegram retries)
        pass


def _fmt(n):
    return f"{int(n):,}".replace(",", " ")


def _welcome(chat_id, first_name=""):
    name = (first_name or "").strip()
    hi = f"Salom, {name}! " if name else "Salom! "
    text = (
        f"🎯 <b>SKIN RUSH</b>\n\n"
        f"{hi}CS2 keyslarini oching, skinlar yutib oling, battle va "
        f"kontraktlarda sinab ko'ring!\n\n"
        f"Pastdagi tugmani bosib o'ynashni boshlang 👇"
    )
    _api("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "🎮 O'ynash", "web_app": {"url": APP_URL}}
            ]]
        },
    })


# ---------------------------------------------------------------- notifications
# Withdraw requests are fulfilled by hand in Steam, so the bot is how a player
# hears back about one. Keyed by WithdrawRequest status; a status missing here
# (or a player who never linked Telegram) simply sends nothing.
WITHDRAW_TEXTS = {
    "pending": (
        "✅ <b>So'rovingiz qabul qilindi</b>\n\n"
        "{skin}\n\n"
        "Adminlarimiz tez orada ko'rib chiqib, skiningizni Steam "
        "inventaringizga tushirib beradi."
    ),
    "approved": (
        "✅ <b>So'rovingiz tasdiqlandi</b>\n\n"
        "{skin}\n\n"
        "Skiningiz 2 soat ichida Steam inventaringizda bo'ladi."
    ),
    "sent": (
        "📤 <b>Trade offer yuborildi</b>\n\n"
        "{skin}\n\n"
        "Steam'ga kirib taklifni qabul qiling."
    ),
    "completed": (
        "🎉 <b>Skiningiz muvaffaqiyatli inventaringizga tushdi</b>\n\n"
        "{skin}\n\n"
        "O'yin uchun rahmat!"
    ),
    "rejected": (
        "❌ <b>So'rovingiz rad etildi</b>\n\n"
        "{skin}\n\n"
        "Sabab: {reason}\n\n"
        "Skin inventaringizga qaytarildi — qayta urinib ko'rishingiz mumkin."
    ),
}


def notify(chat_id, text):
    """Send a one-off message to a player. No-op without a linked Telegram id;
    never raises (``_api`` swallows transport errors)."""
    if not chat_id:
        return
    _api("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})


def notify_withdraw(chat_id, status, skin_name="", reason=""):
    """Tell a player their withdraw request reached `status`."""
    text = WITHDRAW_TEXTS.get(status)
    if not text:
        return
    notify(chat_id, text.format(skin=_esc(skin_name), reason=_esc(reason) or "—"))


def _esc(s):
    """Escape user/catalog text for parse_mode=HTML (skin names carry | and &)."""
    return (str(s or "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _open_app_button(text="🎮 Ochish"):
    return {"inline_keyboard": [[{"text": text, "web_app": {"url": APP_URL}}]]}


def notify_topup_admin_reply(chat_id):
    """Nudge a player on Telegram that the admin replied in the site chat, so
    they open the Mini App to see it even if it was closed."""
    if not chat_id:
        return
    _api("sendMessage", {
        "chat_id": chat_id,
        "text": "💬 <b>To'lov admini javob berdi.</b>\n\nOchib, suhbatni davom ettiring.",
        "parse_mode": "HTML",
        "reply_markup": _open_app_button(),
    })


def notify_topup_new_message(chat_id, user_name):
    """Nudge a payment admin (on Telegram) that a user wrote in the web chat."""
    if not chat_id:
        return
    _api("sendMessage", {
        "chat_id": chat_id,
        "text": f"💬 <b>{_esc(user_name)}</b> to'lov chatida yozdi. "
                f"Admin panelда javob bering.",
        "parse_mode": "HTML",
    })


# ---------------------------------------------------------------- top-ups
# A payment admin settles a top-up entirely inside Telegram: they are pinged,
# they take the request, and from then on everything they and the player send
# is relayed between the two chats. The canned replies below are buttons; they
# can also just type, and the player will usually answer with a photo of the
# receipt — which is why the relay copies whole messages rather than text.
def notify_topup_request(chat_id, req_id, name, username, amount_sum, coins, bonus):
    """Ping an admin that someone wants to buy coins. The conversation itself now
    happens in the web admin panel, so this is just a heads-up."""
    who = f"{_esc(name)}" + (f" (@{_esc(username)})" if username else "")
    text = (
        f"💰 <b>Yangi to'lov so'rovi</b>\n\n"
        f"👤 {who}\n"
        f"💵 <b>{_fmt(amount_sum)} so'm</b>\n"
        f"🪙 {_fmt(coins)} coin" + (f"  (+{bonus}% bonus)" if bonus else "") + "\n\n"
        f"Admin panel → «To'lov chat» bo'limida javob bering."
    )
    _api("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})


def _admin_keyboard(req):
    return {"inline_keyboard": [
        [{"text": "💳 Karta va summa", "callback_data": f"tu:card:{req.id}"}],
        [{"text": "⏳ 2 daqiqada tushadi", "callback_data": f"tu:soon:{req.id}"}],
        [{"text": "❌ Check noto'g'ri", "callback_data": f"tu:bad:{req.id}"}],
        [{"text": f"✅ Balansni to'ldirish ({_fmt(req.coins)})",
          "callback_data": f"tu:pay:{req.id}"}],
        [{"text": "🔚 Aloqani uzish", "callback_data": f"tu:end:{req.id}"}],
    ]}


def _tpl(req, kind):
    """The canned reply `kind`, worded for the player."""
    if kind == "card":
        a = req.admin
        return (
            f"💳 <b>To'lov uchun karta</b>\n\n"
            f"<code>{_esc(a.card_number)}</code>\n"
            f"<b>{_esc(a.card_holder)}</b>\n\n"
            f"Shunga <b>{_fmt(req.amount_sum)} so'm</b> o'tkazib, "
            f"check (skrinshot) yuboring."
        )
    if kind == "soon":
        return (f"⏳ 2 daqiqada balansingiz <b>{_fmt(req.coins)}</b> coinga to'ladi.")
    if kind == "bad":
        return ("❌ Check noto'g'ri yoki soxta. Iltimos, qayta to'lov qiling.")
    return ""


def _take(req, chat_id):
    """An admin picks up a waiting request."""
    from .models import TopUpRequest

    busy = (TopUpRequest.objects.filter(admin=req.admin,
                                        status=TopUpRequest.CONNECTED)
            .exclude(pk=req.pk).first())
    if busy:
        return (f"Avval @{busy.player.username or busy.player.display_name} bilan "
                f"aloqani uzing — bir vaqtda bitta suhbat.")
    if req.status != TopUpRequest.WAITING:
        return "Bu so'rov allaqachon yopilgan yoki boshqa admin oldi."

    req.status = TopUpRequest.CONNECTED
    req.save(update_fields=["status", "updated_at"])
    notify(req.player.telegram_id,
           "🤝 <b>Admin siz bilan bog'landi.</b>\n\nSavollaringizni shu yerda yozing.")
    _api("sendMessage", {
        "chat_id": chat_id,
        "text": (f"🤝 <b>{_esc(req.player.display_name)}</b> bilan ulandingiz.\n\n"
                 f"💵 {_fmt(req.amount_sum)} so'm → 🪙 {_fmt(req.coins)} coin\n\n"
                 f"Tugmalardan foydalaning yoki oddiy yozing — "
                 f"hammasi userga yetadi."),
        "parse_mode": "HTML",
        "reply_markup": _admin_keyboard(req),
    })
    return None


def _pay(req):
    """Credit the coins the request promised. Idempotent via the status."""
    from django.db import transaction

    from .models import CoinPurchase, Player, TopUpRequest

    with transaction.atomic():
        fresh = TopUpRequest.objects.select_for_update().get(pk=req.pk)
        if fresh.status == TopUpRequest.PAID:
            return "Bu so'rov allaqachon to'langan."
        p = Player.objects.select_for_update().get(pk=fresh.player_id)
        p.balance += fresh.coins
        p.coins_purchased += fresh.coins
        p.save(update_fields=["balance", "coins_purchased", "last_seen"])
        CoinPurchase.objects.create(
            player=p, amount=fresh.coins,
            note=f"To'lov · {_fmt(fresh.amount_sum)} so'm"
                 + (f" · +{fresh.bonus_percent}%" if fresh.bonus_percent else ""))
        fresh.status = TopUpRequest.PAID
        fresh.save(update_fields=["status", "updated_at"])
    notify(p.telegram_id,
           f"✅ <b>Balansingiz to'ldirildi!</b>\n\n"
           f"🪙 +{_fmt(fresh.coins)} coin\n"
           f"Yangi balans: <b>{_fmt(p.balance)}</b>\n\nO'yin uchun rahmat!")
    return None


def _end(req):
    from .models import TopUpRequest

    if req.status != TopUpRequest.PAID:
        req.release_promo()      # unpaid — the player keeps their code
        req.status = TopUpRequest.CLOSED
        req.save(update_fields=["status", "updated_at"])
    notify(req.player.telegram_id, "🔚 Aloqa uzildi admin bilan.")


def _live_request(chat_id):
    """The connected request this chat is part of, and which side it is.

    Returns (request, side) with side in {"admin", "player"}, or (None, None).
    """
    from .models import PaymentAdmin, Player, TopUpRequest

    admin = PaymentAdmin.objects.filter(tg_chat_id=chat_id, is_active=True).first()
    if admin:
        req = (TopUpRequest.objects.filter(admin=admin, status=TopUpRequest.CONNECTED)
               .select_related("player", "admin").first())
        return (req, "admin") if req else (None, None)

    player = Player.objects.filter(telegram_id=chat_id).first()
    if player:
        req = (TopUpRequest.objects.filter(player=player,
                                           status=TopUpRequest.CONNECTED)
               .select_related("player", "admin").first())
        return (req, "player") if req else (None, None)
    return None, None


def _relay(update_msg, req, side):
    """Copy a whole message across, so receipts/photos work, not just text."""
    if side == "admin":
        target = req.player.telegram_id
    else:
        target = req.admin.tg_chat_id if req.admin else None
    if not target:
        return
    _api("copyMessage", {
        "chat_id": target,
        "from_chat_id": update_msg["chat"]["id"],
        "message_id": update_msg["message_id"],
    })


def _handle_callback(cb):
    from .models import PaymentAdmin, TopUpRequest

    data = cb.get("data") or ""
    chat_id = ((cb.get("message") or {}).get("chat") or {}).get("id")
    cb_id = cb.get("id")

    def answer(text="", alert=False):
        _api("answerCallbackQuery", {"callback_query_id": cb_id, "text": text,
                                     "show_alert": alert})

    if not data.startswith("tu:"):
        return answer()
    try:
        _, action, raw_id = data.split(":", 2)
        req_id = int(raw_id)
    except (ValueError, TypeError):
        return answer()

    req = (TopUpRequest.objects.filter(pk=req_id)
           .select_related("player", "admin").first())
    if req is None:
        return answer("So'rov topilmadi", alert=True)
    # Only the admin the request was routed to may act on it.
    if not PaymentAdmin.objects.filter(tg_chat_id=chat_id, is_active=True,
                                       pk=req.admin_id).exists():
        return answer("Bu so'rov sizga tegishli emas", alert=True)

    if action == "take":
        err = _take(req, chat_id)
        return answer(err or "Ulandingiz", alert=bool(err))

    if req.status not in (TopUpRequest.CONNECTED, TopUpRequest.PAID):
        return answer("Aloqa uzilgan", alert=True)

    if action in ("card", "soon", "bad"):
        notify(req.player.telegram_id, _tpl(req, action))
        return answer("Yuborildi ✅")
    if action == "pay":
        err = _pay(req)
        return answer(err or "Balans to'ldirildi ✅", alert=bool(err))
    if action == "end":
        _end(req)
        _api("sendMessage", {"chat_id": chat_id, "text": "🔚 Aloqa uzildi."})
        return answer("Aloqa uzildi")
    return answer()


@csrf_exempt
@require_POST
def webhook(request, secret=""):
    """Receive updates from Telegram.

    Handles three things: ``/start`` (welcome + Mini App button), the payment
    admin's inline buttons, and relaying anything else between a connected
    admin/player pair.

    ``secret`` is the path component (obscurity); Telegram also echoes the
    configured secret in the ``X-Telegram-Bot-Api-Secret-Token`` header. Both are
    checked against ``TELEGRAM_WEBHOOK_SECRET`` when it is set.
    """
    want = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if want:
        header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if secret != want or header != want:
            return HttpResponse(status=403)
    try:
        update = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"ok": True})

    # Top-up conversations moved to the web admin panel, so the old inline
    # buttons no longer drive anything — answer any stale press politely.
    if update.get("callback_query"):
        cb = update["callback_query"]
        _api("answerCallbackQuery", {
            "callback_query_id": cb.get("id"),
            "text": "To'lovlar endi admin panelning «To'lov chat» bo'limida.",
            "show_alert": True,
        })
        return JsonResponse({"ok": True})

    msg = update.get("message") or update.get("edited_message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id:
        return JsonResponse({"ok": True})

    if text.startswith("/start"):
        _welcome(chat_id, (msg.get("from") or {}).get("first_name", ""))

    return JsonResponse({"ok": True})

    return JsonResponse({"ok": True})
