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
    AUTO_DISPATCH=(bool, False),
    DISPATCH_MIN_INTERVAL_SEC=(int, 2),
    DISPATCH_HORIZON_MIN=(int, 120),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:5173"]),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-only-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# Render terminates TLS at its edge and forwards plain HTTP with this header.
# Without it Django believes every request is insecure, and secure cookies and
# any redirect it builds come out as http://.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# The dashboard lives on another origin (Vercel), so its origin has to be
# trusted for any form POST that carries a CSRF token -- the admin login above all.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # Render already redirects to HTTPS at its edge; this closes the gap for any
    # request that reaches Django on plain HTTP anyway. Safe only because
    # SECURE_PROXY_SSL_HEADER above tells Django what the edge already did --
    # without it this would be an infinite redirect loop.
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    # One year, but OFF by default. HSTS is remembered by the browser and cannot
    # be withdrawn early: turn it on once you are sure of the domain, not while
    # you are still moving the API around.
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = bool(SECURE_HSTS_SECONDS)
    SECURE_HSTS_PRELOAD = bool(SECURE_HSTS_SECONDS)

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

    # Order matters: an app must come after anything it imports.
    "apps.accounts",
    "apps.reports",
    "apps.resources",
    "apps.dispatch",
    "apps.alerts",
    "apps.ingest",
    "apps.realtime",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # Render has no nginx in front of you. Without this, DEBUG=False serves the
    # admin with no CSS at all and every static asset 404s.
    "whitenoise.middleware.WhiteNoiseMiddleware",
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

# Managed Postgres (Neon, Render, Supabase...) hands you ONE connection string.
# A laptop has five separate fields in .env. Support both: DATABASE_URL wins when
# it is set, which is exactly the production case and needs no other change.
if env("DATABASE_URL", default=""):
    DATABASES = {"default": env.db("DATABASE_URL")}
    # Neon terminates idle connections aggressively and every request paying for
    # a fresh TLS handshake is the difference between a snappy dashboard and a
    # sluggish one. Keep them, but not longer than the pooler will.
    DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)
    DATABASES["default"].setdefault("OPTIONS", {})["sslmode"] = env(
        "DB_SSLMODE", default="require")
else:
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
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
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
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 200,
    "EXCEPTION_HANDLER": "apps.common.exceptions.ps05_exception_handler",
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
# Does a new report dispatch units BY ITSELF?
#
# False -- the default -- means the solver keeps a live plan ready and the
# dashboard shows it, but nothing moves until an operator presses Dispatch. That
# is the behaviour an ops room actually wants, it is what makes the "human in
# the loop" answer true, and it is the only way a demo can show units going out
# one at a time instead of the whole district already being committed before
# anyone looks at the screen.
#
# True restores hands-off auto-dispatch: every report immediately commits the
# best plan. Useful for load-testing the solver, not for a control room.
AUTO_DISPATCH = env("AUTO_DISPATCH")

DISPATCH_MIN_INTERVAL_SEC = env("DISPATCH_MIN_INTERVAL_SEC")   # debounce floor
DISPATCH_HORIZON_MIN = env("DISPATCH_HORIZON_MIN")             # the 120 in cost = w*(eta-120)
USE_ROAD_GRAPH = env("USE_ROAD_GRAPH")                         # route on real roads
# The district `manage.py seed_roadgraph` downloads (min_lat, min_lon, max_lat, max_lon).
ROAD_GRAPH_BBOX = env.list("ROAD_GRAPH_BBOX", cast=float,
                           default=[19.60, 85.50, 20.10, 86.20])
USE_ALERT_FIXTURE = env("USE_ALERT_FIXTURE")                   # demo-safe CAP feed
USE_WEBSOCKETS = env("USE_WEBSOCKETS")                         # False -> broadcast() becomes a no-op
SMS_GATEWAY_SECRET = env("SMS_GATEWAY_SECRET", default="change-me")

# TextBee turns an Android phone into an SMS gateway. Polled by
# `manage.py poll_textbee` rather than taking their webhook, because their cloud
# cannot reach a laptop behind NAT -- see that command's docstring.
TEXTBEE_API_KEY = env("TEXTBEE_API_KEY", default="")
TEXTBEE_BASE_URL = env("TEXTBEE_BASE_URL", default="https://api.textbee.dev")
SACHET_FEED_URL = env("SACHET_FEED_URL", default="https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml")
CORROBORATION_WINDOW_MIN = 60      # distinct reporters in a cell within this window
