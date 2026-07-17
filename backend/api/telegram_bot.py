"""Minimal Telegram bot webhook for SKINRUSH.

The Django site is a *web app*, not a chat bot, so on its own it never replies to
messages. This module adds a tiny webhook endpoint that Telegram calls for every
update. When a user sends ``/start`` we reply with a welcome message plus a big
**web_app** inline button that opens the Mini App (auto-login happens there).

Set the webhook once (see ``set_webhook`` helper / management step):
    https://api.telegram.org/bot<TOKEN>/setWebhook?url=<SITE>/tg/webhook/<SECRET>/
        &secret_token=<SECRET>

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


@csrf_exempt
@require_POST
def webhook(request, secret=""):
    """Receive updates from Telegram and reply to /start.

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

    msg = update.get("message") or update.get("edited_message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()

    if chat_id and text.startswith("/start"):
        _welcome(chat_id, (msg.get("from") or {}).get("first_name", ""))

    return JsonResponse({"ok": True})
