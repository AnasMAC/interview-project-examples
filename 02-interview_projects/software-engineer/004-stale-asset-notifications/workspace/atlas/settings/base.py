import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


SECRET_KEY = env("DJANGO_SECRET_KEY", "DEMO-django-secret-local-only")
DEBUG = False
ALLOWED_HOSTS = env("ATLAS_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "atlas.core",
    "atlas.jobs",
    "atlas.assets",
    "atlas.exposure",
    "atlas.notify",
    "atlas.dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "atlas.urls"
WSGI_APPLICATION = "atlas.wsgi.application"

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
        "HOST": env("ATLAS_DB_HOST", "localhost"),
        "PORT": env("ATLAS_DB_PORT", "5432"),
        "NAME": env("ATLAS_DB_NAME", "atlas"),
        "USER": env("ATLAS_DB_USER", "atlas"),
        "PASSWORD": env("ATLAS_DB_PASSWORD", "DEMO-atlas-db"),
        "CONN_MAX_AGE": 60,
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Everything is stored and computed in UTC. Org-local dates (expiry "today",
# "last 24h" windows) go through atlas.core.clock with the org's timezone.
TIME_ZONE = "UTC"
USE_TZ = True
LANGUAGE_CODE = "en-us"
USE_I18N = False

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "var" / "static"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# Throttle counters live in the default cache. LocMem means per process:
# good enough for the dev server, see docs/runbook.md for production.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["atlas.core.auth.ApiKeyAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "atlas.core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {"api_key": env("ATLAS_API_RATE", "600/min")},
    "UNAUTHENTICATED_USER": None,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "atlas.core.logging.JsonFormatter"},
        "text": {
            "()": "atlas.core.logging.RedactingFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": env("ATLAS_LOG_FORMAT", "text")},
    },
    "root": {"handlers": ["console"], "level": env("ATLAS_LOG_LEVEL", "INFO")},
    # No handlers here: replaces Django's own console handler, records reach root.
    "loggers": {"django": {"level": "INFO"}, "django.db.backends": {"level": "WARNING"}},
}

# --- Atlas -----------------------------------------------------------------
ATLAS_SERVICE = env("ATLAS_SERVICE", "web")
# Import job payloads carry a path relative to this directory.
ATLAS_IMPORT_ROOT = Path(env("ATLAS_IMPORT_ROOT", str(BASE_DIR / "fixtures" / "imports")))
ATLAS_JOB_MAX_ATTEMPTS = int(env("ATLAS_JOB_MAX_ATTEMPTS", "5"))
ATLAS_WORKER_POLL_SECONDS = float(env("ATLAS_WORKER_POLL_SECONDS", "1.0"))
ATLAS_WEBHOOK_TIMEOUT_SECONDS = float(env("ATLAS_WEBHOOK_TIMEOUT_SECONDS", "5"))
ATLAS_WEBHOOK_MAX_ATTEMPTS = int(env("ATLAS_WEBHOOK_MAX_ATTEMPTS", "8"))
# Webhook targets outside this list are refused (empty list = no restriction).
ATLAS_WEBHOOK_ALLOWED_HOSTS = [
    h for h in env("ATLAS_WEBHOOK_ALLOWED_HOSTS", "mockhook,localhost,*.example.test").split(",") if h
]
