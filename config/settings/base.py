"""Base Django settings shared by every environment. All configuration comes from env vars."""

import os
from pathlib import Path
from typing import Any

import dj_database_url
import django_stubs_ext

from contexts.scheduling.infrastructure.telemetry.logging import configure_structlog, logging_config

# Lets admin classes use generics like ModelAdmin[Model] at runtime (typed with django-stubs).
django_stubs_ext.monkeypatch()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "")
DEBUG = False
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "django_prometheus",
    "contexts.catalog",
    "contexts.scheduling.infrastructure.persistence",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "contexts.scheduling.infrastructure.telemetry.middleware.CorrelationIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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

DB_STATEMENT_TIMEOUT_MS = int(os.environ.get("DB_STATEMENT_TIMEOUT_MS", "2000"))

DATABASES = {
    "default": dj_database_url.parse(
        os.environ.get("DATABASE_URL", "postgres://scheduler:scheduler@localhost:5432/scheduler"),
        conn_max_age=60,
        conn_health_checks=True,
    )
}
DATABASES["default"]["OPTIONS"] = {"options": f"-c statement_timeout={DB_STATEMENT_TIMEOUT_MS}"}
# Same PostgreSQL backend, wrapped to export query/connection metrics.
DATABASES["default"]["ENGINE"] = "django_prometheus.db.backends.postgresql"

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

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

REST_FRAMEWORK: dict[str, Any] = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "contexts.scheduling.interface.api.problem_details.exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%SZ",
    "DEFAULT_THROTTLE_RATES": {
        "booking": os.environ.get("THROTTLE_BOOKING_RATE", "60/min"),
        "availability": os.environ.get("THROTTLE_AVAILABILITY_RATE", "120/min"),
    },
    "NUM_PROXIES": int(os.environ.get("NUM_PROXIES", "0")),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Unified Service Scheduler API",
    "DESCRIPTION": (
        "Books a service bay and a qualified technician for a dealership appointment. "
        "Errors use application/problem+json (RFC 7807)."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# Scheduling tunables (SPEC §14.6).
BOOKING_MAX_RETRIES = int(os.environ.get("BOOKING_MAX_RETRIES", "3"))
AVAILABILITY_CACHE_TTL_SECONDS = int(os.environ.get("AVAILABILITY_CACHE_TTL_SECONDS", "5"))
IDEMPOTENCY_TTL_HOURS = int(os.environ.get("IDEMPOTENCY_TTL_HOURS", "24"))
OTEL_EXPORTER_OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")

# Observability (SPEC §9): JSON logs to stdout with correlation ids.
configure_structlog()
LOGGING = logging_config(
    level=os.environ.get("LOG_LEVEL", "INFO"), fmt=os.environ.get("LOG_FORMAT", "json")
)
