"""API routes for SKINRUSH."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import admin_api, auth_account, auth_telegram, views

router = DefaultRouter()
router.register("cases", views.CaseViewSet, basename="case")

urlpatterns = [
    path("", include(router.urls)),
    # Custom admin panel API (staff-only).
    path("admin/me/", admin_api.admin_me, name="admin-me"),
    path("admin/login/", admin_api.admin_login, name="admin-login"),
    path("admin/logout/", admin_api.admin_logout, name="admin-logout"),
    path("admin/stats/", admin_api.admin_stats, name="admin-stats"),
    path("admin/cases/", admin_api.admin_cases, name="admin-cases"),
    path("admin/cases/<int:pk>/", admin_api.admin_case_detail, name="admin-case-detail"),
    path("admin/users/", admin_api.admin_users, name="admin-users"),
    path("admin/users/<int:pk>/", admin_api.admin_user_detail, name="admin-user-detail"),
    path("admin/users/<int:pk>/coins/", admin_api.admin_give_coins, name="admin-give-coins"),
    path("admin/payment-admins/", admin_api.admin_payment_admins,
         name="admin-payment-admins"),
    path("admin/payment-admins/<int:pk>/", admin_api.admin_payment_admin_detail,
         name="admin-payment-admin-detail"),
    path("admin/promos/", admin_api.admin_promos, name="admin-promos"),
    path("admin/promos/<int:pk>/", admin_api.admin_promo_detail, name="admin-promo-detail"),
    path("admin/topups/", admin_api.admin_topups, name="admin-topups"),
    path("admin/withdraws/", admin_api.admin_withdraws, name="admin-withdraws"),
    path("admin/withdraws/<int:pk>/approve/", admin_api.admin_withdraw_approve,
         name="admin-withdraw-approve"),
    path("admin/withdraws/<int:pk>/reject/", admin_api.admin_withdraw_reject,
         name="admin-withdraw-reject"),
    path("admin/withdraws/<int:pk>/mark-sent/", admin_api.admin_withdraw_mark_sent,
         name="admin-withdraw-mark-sent"),
    path("admin/withdraws/<int:pk>/complete/", admin_api.admin_withdraw_complete,
         name="admin-withdraw-complete"),
    # Player auth (Telegram)
    path("auth/config/", auth_telegram.auth_config, name="auth-config"),
    path("auth/me/", auth_telegram.auth_me, name="auth-me"),
    path("auth/telegram/", auth_telegram.telegram_login, name="auth-telegram"),
    path("auth/register/", auth_account.register, name="auth-register"),
    path("auth/login/", auth_account.account_login, name="auth-login"),
    path("auth/logout/", auth_telegram.auth_logout, name="auth-logout"),
    path("top-drops/", views.top_drops, name="top-drops"),
    path("stats/", views.stats, name="stats"),
    path("me/", views.me, name="me"),
    path("i18n/", views.i18n_strings, name="i18n"),
    path("lang/", views.set_lang, name="set-lang"),
    path("sell/", views.sell, name="sell"),
    path("claim/", views.claim, name="claim"),
    path("inventory/", views.inventory, name="inventory"),
    path("daily/", views.daily, name="daily"),
    path("daily/claim/", views.daily_claim, name="daily-claim"),
    path("upgrade/inventory/", views.upgrade_inventory, name="upgrade-inventory"),
    path("upgrade/targets/", views.upgrade_targets, name="upgrade-targets"),
    path("upgrade/compute/", views.upgrade_compute, name="upgrade-compute"),
    path("upgrade/play/", views.upgrade_play, name="upgrade-play"),
]
