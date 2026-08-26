"""
PS-05 · Django settings.

Everything environment-specific comes from backend/.env (see .env.example).
Fill DB_NAME / DB_USER / DB_PASSWORD there before running migrate.
"""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, True),
    USE_ROAD_GRAPH=(bool, False),
    USE_ALERT_FIXTURE=(bool, True),
    USE_WEBSOCKETS=(bool, True),
    DISPATCH_MIN_INTERVAL_SEC=(int, 2),
    DISPATCH_HORIZON_MIN=(int, 120),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:5173"]),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-only-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "daphne",                       # must precede staticfiles so runserver goes ASGI
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "channels",

    # Order matters: dependencies first (blueprint 01 import map).
    "accounts",
    "reports",
    "resources",
    "dispatch",
    "alerts",
    "ingest",
    "realtime",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", default="ps05"),
        "USER": env("DB_USER", default="postgres"),
        "PASSWORD": env("DB_PASSWORD", default=""),
        "HOST": env("DB_HOST", default="localhost"),
        "PORT": env("DB_PORT", default="5432"),
    }
}

# Redis does two unrelated jobs on separate databases: the Channels group layer
# (here) and, later, a Celery broker for CAP polling and bulk SMS.
#
# Set REDIS_URL="" in .env to fall back to the in-memory layer. That works for a
# single daphne process -- which is every laptop -- and means nobody is blocked
# on `brew services start redis` to see the dashboard. It does NOT work across
# multiple workers: groups live in one process's memory, so a broadcast from
# worker A never reaches a socket held by worker B. Use Redis for anything real.
REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/0")

if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# DRF + JWT
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "common.pagination.DefaultPagination",
    "PAGE_SIZE": 200,
    "EXCEPTION_HANDLER": "common.exceptions.ps05_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("ACCESS_TOKEN_MINUTES", default=60)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# PS-05 tunables. Every number here is defended in the build plan; expose them
# so you can change one without touching engine.py.
# ---------------------------------------------------------------------------
DISPATCH_MIN_INTERVAL_SEC = env("DISPATCH_MIN_INTERVAL_SEC")   # debounce floor
DISPATCH_HORIZON_MIN = env("DISPATCH_HORIZON_MIN")             # the 120 in cost = w*(eta-120)
USE_ROAD_GRAPH = env("USE_ROAD_GRAPH")                         # True only once everything else works
USE_ALERT_FIXTURE = env("USE_ALERT_FIXTURE")                   # demo-safe CAP feed
USE_WEBSOCKETS = env("USE_WEBSOCKETS")                         # False -> broadcast() becomes a no-op
SMS_GATEWAY_SECRET = env("SMS_GATEWAY_SECRET", default="change-me")
SACHET_FEED_URL = env("SACHET_FEED_URL", default="https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml")
CORROBORATION_WINDOW_MIN = 60      # distinct reporters in a cell within this window
