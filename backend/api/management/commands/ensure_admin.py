"""Create the admin superuser from env vars, idempotently.

Runs on every deploy. It creates the superuser once (from ADMIN_USERNAME /
ADMIN_PASSWORD); on later runs it only makes sure the account still has admin
rights and does NOT overwrite the password — so a password you change inside
the admin panel survives future deploys.

    python manage.py ensure_admin
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create/ensure the admin superuser from ADMIN_USERNAME/ADMIN_PASSWORD."

    def handle(self, *args, **options):
        username = os.environ.get("ADMIN_USERNAME")
        password = os.environ.get("ADMIN_PASSWORD")
        email = os.environ.get("ADMIN_EMAIL", "")

        if not username or not password:
            self.stdout.write("ADMIN_USERNAME/ADMIN_PASSWORD not set — skipping.")
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Admin '{username}' yaratildi."))
        else:
            changed = False
            if not user.is_staff:
                user.is_staff = True
                changed = True
            if not user.is_superuser:
                user.is_superuser = True
                changed = True
            if changed:
                user.save()
            self.stdout.write(f"Admin '{username}' allaqachon mavjud (parol saqlandi).")
