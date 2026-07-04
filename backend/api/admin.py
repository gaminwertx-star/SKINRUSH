"""Django admin registrations."""
from django.contrib import admin

from .models import Case, CaseItem, Drop


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "openings", "opens", "sort_order")
    search_fields = ("name",)


@admin.register(CaseItem)
class CaseItemAdmin(admin.ModelAdmin):
    list_display = ("name", "wear", "chance", "price", "rarity", "case")
    list_filter = ("rarity", "case")
    search_fields = ("name", "weapon")


@admin.register(Drop)
class DropAdmin(admin.ModelAdmin):
    list_display = ("item", "case", "created_at")
    list_filter = ("case",)
