"""Seed the database from the scraped real cs-shot.pro catalog.

Reads ``backend/shot_cases.json`` (78 cases, ~3400 items) and loads every case
with its real skins, real drop chances (%) and real prices.

    python manage.py seed
"""
import json
import random
import re

from django.conf import settings
from django.core.management.base import BaseCommand

from api.models import Case, CaseItem, Drop

# Rarities that count as a "top drop" for the live strip.
TOP_RARITIES = {"Covert", "Extraordinary", "Classified", "Exceptional",
                "Master", "Superior", "Distinguished", "Exotic", "Remarkable"}

WEAR_RE = re.compile(r"\s*\([^)]*\)\s*$")


def base_name(name):
    """'AK-47 | Redline (Field-Tested)' -> 'AK-47 | Redline'."""
    return WEAR_RE.sub("", name).strip()


def data_path():
    for p in (settings.BASE_DIR / "shot_cases.json",
              settings.FRONTEND_DIR / "shot_cases.json"):
        if p.exists():
            return p
    raise FileNotFoundError("shot_cases.json topilmadi (backend/ ichiga qo'ying).")


class Command(BaseCommand):
    help = "Load the real cs-shot.pro cases, skins, chances and prices."

    def handle(self, *args, **options):
        Drop.objects.all().delete()
        CaseItem.objects.all().delete()
        Case.objects.all().delete()

        cases = json.loads(data_path().read_text(encoding="utf-8"))

        top_items = []
        for c in cases:
            # Crate images are self-hosted (downloaded from the source) under
            # images/cases/ so they don't depend on the source's hotlink rules.
            src_img = (c.get("img") or "").split("?")[0]
            local_img = f"images/cases/{src_img.rsplit('/', 1)[-1]}" if src_img else ""
            case = Case.objects.create(
                ext_id=c.get("id", ""), name=c["name"], price=c["price"],
                image=local_img,
                openings=c.get("openings") or 0, is_new=bool(c.get("isNew")),
                xp=c.get("xp") or 0, sort_order=c.get("order") or 0,
            )
            rows = []
            for i, it in enumerate(c["items"]):
                # item = [name, wear, chance, priceCredits, color, imgHash, rarity]
                name, wear, chance, price, color, img, rarity = (
                    it[0], it[1], it[2], it[3], it[4], it[5], it[6] if len(it) > 6 else ""
                )
                bname = base_name(name)
                parts = bname.split(" | ", 1)
                weapon = parts[0].strip()
                finish = parts[1].strip() if len(parts) > 1 else ""
                rows.append(CaseItem(
                    case=case, name=bname, weapon=weapon, finish=finish, wear=wear,
                    chance=float(chance), price=int(round(price)), rarity=rarity,
                    color=color or "#b0c3d9", image=img, order=i,
                ))
            CaseItem.objects.bulk_create(rows, batch_size=500)
            top_items += [r for r in rows if r.rarity in TOP_RARITIES]

        self.stdout.write(self.style.SUCCESS(
            f"Keyslar: {Case.objects.count()} · Skinlar: {CaseItem.objects.count()}"))

        # Seed some TOP DROPS so the live strip isn't empty.
        pool = top_items or list(CaseItem.objects.all()[:200])
        if pool:
            picks = random.sample(pool, min(40, len(pool)))
            Drop.objects.bulk_create([Drop(case=p.case, item=p) for p in picks])
        self.stdout.write(self.style.SUCCESS(
            f"Boshlang'ich droplar: {Drop.objects.count()} · Seed tugadi."))
