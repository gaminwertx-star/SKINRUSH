"""DRF serializers for SKINRUSH."""
from rest_framework import serializers

from .models import Case, CaseItem, Drop


def human_count(n):
    """14800000 -> '14.8M', 582800 -> '582.8k'."""
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def price_color(price):
    """Crate accent colour derived from the price tier."""
    if price >= 1_000_000:
        return "#e4ae39"
    if price >= 300_000:
        return "#eb4b4b"
    if price >= 75_000:
        return "#d32ce6"
    if price >= 25_000:
        return "#8847ff"
    if price >= 5_000:
        return "#4b69ff"
    if price >= 1_000:
        return "#5e98d9"
    return "#b0c3d9"


class CaseSerializer(serializers.ModelSerializer):
    color = serializers.SerializerMethodField()
    opened_display = serializers.SerializerMethodField()

    class Meta:
        model = Case
        fields = ["id", "slug", "name", "price", "image", "color",
                  "opened_display", "is_new"]

    def get_color(self, obj):
        return price_color(obj.price)

    def get_opened_display(self, obj):
        return human_count(obj.openings)


class CaseItemSerializer(serializers.ModelSerializer):
    tier_label = serializers.CharField(source="rarity", read_only=True)
    img = serializers.CharField(source="image", read_only=True)

    class Meta:
        model = CaseItem
        fields = ["id", "name", "weapon", "finish", "wear", "tier_label",
                  "color", "img", "price", "chance"]


class DropSerializer(serializers.ModelSerializer):
    skin = CaseItemSerializer(source="item", read_only=True)
    case_name = serializers.CharField(source="case.name", read_only=True)

    class Meta:
        model = Drop
        fields = ["id", "skin", "case_name", "created_at"]
