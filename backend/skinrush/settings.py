"""Django settings for the SKINRUSH backend (dev-oriented)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
# Project root that holds the front-end files (index.html, skins-data.js, ...)
FRONTEND_DIR = BASE_DIR.parent

# In production set these via environment variables (Render does this for you).
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-not-secret-change-me")
DEBUG = os.environ.get("DEBUG", "True") == "True"

ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "*").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o]
# Render exposes the public hostname here — trust it automatically.
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
    CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")

if not DEBUG:
    # Render terminates TLS at its proxy; trust the forwarded protocol.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "api",
]

MIDDLEWARE = [
    "api.middleware.SimpleCorsMiddleware",  # allow the static front-end to fetch us
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serve Django static in production
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "skinrush.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "skinrush.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
# On a server, set the DATABASE_URL env var to a PostgreSQL connection string.
# Then the data lives in an EXTERNAL database (outside the code) and survives
# every deploy/redeploy. Locally, with no DATABASE_URL, SQLite is used as before.
_db_url = os.environ.get("DATABASE_URL")
if _db_url:
    import dj_database_url

    DATABASES["default"] = dj_database_url.parse(
        _db_url, conn_max_age=600, ssl_require=True
    )

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    # State is anonymous and per-session; no auth (and thus no CSRF check on the
    # POST endpoints, which are called by the same-origin front-end via fetch).
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
}
