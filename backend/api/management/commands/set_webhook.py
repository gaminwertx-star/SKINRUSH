"""Register (or inspect) the Telegram webhook.

This lives in the repo rather than being a URL someone pastes once, because
``allowed_updates`` has to be kept in step with what ``api.telegram_bot``
actually handles. It was registered by hand as ``["message"]`` back when the bot
only answered /start; once the payment admin's inline buttons arrived, Telegram
went on filtering out every ``callback_query`` and the buttons silently did
nothing. Keeping the list next to the handler is what stops that happening again.

    python manage.py set_webhook              # register / re-register
    python manage.py set_webhook --show       # just print what Telegram has
    python manage.py set_webhook --delete     # unregister
"""
import json
import os
import urllib.request

from django.core.management.base import BaseCommand, CommandError

# Every update type api.telegram_bot.webhook knows how to act on.
ALLOWED_UPDATES = ["message", "edited_message", "callback_query"]


def _call(method, payload=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise CommandError("TELEGRAM_BOT_TOKEN is not set")
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


class Command(BaseCommand):
    help = "Point Telegram's webhook at this site with the right update types."

    def add_arguments(self, parser):
        parser.add_argument("--site", default=os.environ.get(
            "MINIAPP_URL", "https://95-169-201-44.sslip.io/"))
        parser.add_argument("--show", action="store_true")
        parser.add_argument("--delete", action="store_true")

    def handle(self, *a, **o):
        if o["show"]:
            return self._show()
        if o["delete"]:
            _call("deleteWebhook")
            self.stdout.write(self.style.SUCCESS("webhook deleted"))
            return

        secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
        if not secret:
            raise CommandError("TELEGRAM_WEBHOOK_SECRET is not set")
        url = f"{o['site'].rstrip('/')}/tg/webhook/{secret}/"
        res = _call("setWebhook", {
            "url": url,
            "secret_token": secret,
            "allowed_updates": ALLOWED_UPDATES,
            # Old presses queued while the webhook was misconfigured would fire
            # against requests that have since moved on.
            "drop_pending_updates": True,
        })
        if not res.get("ok"):
            raise CommandError(f"Telegram refused it: {res}")
        self.stdout.write(self.style.SUCCESS(
            f"webhook set · allowed_updates={ALLOWED_UPDATES}"))
        self._show()

    def _show(self):
        info = _call("getWebhookInfo")["result"]
        secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
        shown = info.get("url", "")
        if secret:
            shown = shown.replace(secret, "<secret>")
        self.stdout.write(f"  url             : {shown}")
        self.stdout.write(f"  pending updates : {info.get('pending_update_count')}")
        self.stdout.write(f"  last error      : {info.get('last_error_message', 'none')}")
        got = info.get("allowed_updates") or []
        self.stdout.write(f"  allowed_updates : {got or '(default)'}")
        missing = [u for u in ALLOWED_UPDATES if u not in got] if got else []
        if missing:
            self.stdout.write(self.style.ERROR(
                f"  MISSING         : {missing} — those updates never reach us"))
        else:
            self.stdout.write(self.style.SUCCESS("  every update type we handle is allowed"))
