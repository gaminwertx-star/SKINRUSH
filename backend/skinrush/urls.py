"""Root URL configuration for SKINRUSH.

The whole public site is server-rendered (Django templates, no client-side JS):
every screen is its own URL handled by `api.pages`. `/api/` is kept only for the
staff admin panel. Static assets (styles.css, ssr.css, images/…) are served from
the project root by the trailing static fallback.
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve as static_serve

from api import pages
from api import telegram_bot

FRONTEND_DIR = settings.FRONTEND_DIR


def admin_panel(request):
    # Custom staff admin single-page app. Auth is enforced by /api/admin/*.
    return static_serve(request, "admin/index.html", document_root=FRONTEND_DIR)


urlpatterns = [
    # ---- admin + legacy API (declared first so the public page URL names below
    #      win reverse() over the old DRF endpoints that share names) ----
    re_path(r"^adminpanel/?$", admin_panel, name="adminpanel"),
    path("django-admin/", admin.site.urls),
    path("api/", include("api.urls")),

    # ---- public server-rendered site ----
    path("", pages.home, name="home"),
    path("kunlik/olish/", pages.daily_claim, name="daily-claim"),

    path("keys/<slug:slug>/", pages.case_detail, name="case"),
    path("skin/", pages.skin_detail, name="skin"),
    path("skin/buy/", pages.skin_buy, name="skin-buy"),
    path("keys/<slug:slug>/ochish/", pages.case_open, name="case-open"),
    path("natija/", pages.result, name="result"),
    path("olish/", pages.claim, name="claim"),
    path("sotish/", pages.sell, name="sell"),

    path("inventar/", pages.inventory, name="inventory"),
    path("inventar/hammasini-sotish/", pages.sell_all, name="sell-all"),
    path("inventar/<int:pk>/", pages.inventory_item, name="inventory-item"),

    path("yechish/", pages.withdraw, name="withdraw"),
    path("yechish/trade-url/", pages.withdraw_trade_url, name="withdraw-trade-url"),
    path("yechish/tasdiqlash/", pages.withdraw_create, name="withdraw-create"),

    path("yaxshilash/", pages.upgrade, name="upgrade"),
    path("yaxshilash/play/", pages.upgrade_play, name="upgrade-play"),

    path("janglar/", pages.battles, name="battles"),
    path("janglar/create/", pages.battle_create, name="battle-create"),
    path("janglar/<int:pk>/", pages.battle_detail, name="battle"),
    path("janglar/<int:pk>/qatnashish/", pages.battle_join, name="battle-join"),
    path("janglar/<int:pk>/bekor/", pages.battle_cancel, name="battle-cancel"),

    path("dokon/", pages.dokon, name="dokon"),
    path("kontraktlar/", pages.kontraktlar, name="kontraktlar"),
    path("kontraktlar/create/", pages.kontrakt_play, name="kontrakt-play"),
    path("dostlar/", pages.dostlar, name="dostlar"),
    path("promokod/", pages.promocode, name="promocode"),
    path("profil/", pages.profile, name="profile"),

    # ---- auth ----
    path("tg/webapp-login/", pages.webapp_login, name="webapp-login"),
    path("tg/webhook/<str:secret>/", telegram_bot.webhook, name="tg-webhook"),
    path("kirish/", pages.login_page, name="login"),
    path("royxat/", pages.register_page, name="register"),
    path("chiqish/", pages.logout_page, name="logout"),
    path("til/<str:code>/", pages.set_lang, name="setlang"),

    # ---- static assets from the project root (styles.css, ssr.css, images/…) ----
    re_path(r"^(?P<path>.+)$", static_serve, {"document_root": FRONTEND_DIR}),
]
