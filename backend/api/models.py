"""Data models for SKINRUSH.

Cases and their contents mirror the real cs-shot.pro catalog: every case holds
its own real skins with the source's real drop chance (%) and price. This is
what decides whether a player ends up + or - , so it is stored verbatim.
"""
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import slugify

WELCOME_BALANCE = 1000  # coins granted to a new account


class Case(models.Model):
    """A case in the catalog (real cs-shot.pro lineup)."""

    ext_id = models.CharField(max_length=64, blank=True, db_index=True)
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    price = models.PositiveBigIntegerField(help_text="Price in virtual coins/credits")
    image = models.CharField(max_length=400, help_text="Crate image URL")
    openings = models.PositiveBigIntegerField(default=0, help_text="Times opened on source")
    is_new = models.BooleanField(default=False)
    xp = models.IntegerField(default=0)
    sort_order = models.IntegerField(default=0, db_index=True)
    opens = models.PositiveBigIntegerField(default=0, help_text="Local opens")

    class Meta:
        ordering = ["sort_order", "price", "name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class CaseItem(models.Model):
    """A single real skin inside a case, with its real drop chance and price."""

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=180, db_index=True)   # base name, no wear
    weapon = models.CharField(max_length=100, blank=True)
    finish = models.CharField(max_length=140, blank=True)
    wear = models.CharField(max_length=40, blank=True)
    chance = models.FloatField(help_text="Drop chance in percent")
    price = models.PositiveBigIntegerField(help_text="Value in virtual coins")
    rarity = models.CharField(max_length=40, blank=True)
    color = models.CharField(max_length=9, blank=True)
    image = models.CharField(max_length=400)                 # steam image hash
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order"]
        indexes = [models.Index(fields=["price"])]

    def __str__(self):
        return f"{self.name} ({self.wear}) — {self.chance}%"


class Drop(models.Model):
    """A record of a skin won from a case — powers the TOP DROPS feed."""

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="drops")
    item = models.ForeignKey(CaseItem, on_delete=models.CASCADE, related_name="drops")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.item.name} ({self.case.name})"
