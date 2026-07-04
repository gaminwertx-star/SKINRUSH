"""API routes for SKINRUSH."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("cases", views.CaseViewSet, basename="case")

urlpatterns = [
    path("", include(router.urls)),
    path("top-drops/", views.top_drops, name="top-drops"),
    path("stats/", views.stats, name="stats"),
    path("me/", views.me, name="me"),
    path("i18n/", views.i18n_strings, name="i18n"),
    path("lang/", views.set_lang, name="set-lang"),
    path("sell/", views.sell, name="sell"),
    path("daily/", views.daily, name="daily"),
    path("daily/claim/", views.daily_claim, name="daily-claim"),
    path("upgrade/inventory/", views.upgrade_inventory, name="upgrade-inventory"),
    path("upgrade/targets/", views.upgrade_targets, name="upgrade-targets"),
    path("upgrade/compute/", views.upgrade_compute, name="upgrade-compute"),
    path("upgrade/play/", views.upgrade_play, name="upgrade-play"),
]
