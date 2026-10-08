"""Test settings: real PostgreSQL (exclusion constraints need it), local-memory cache."""

import os

from .base import *  # noqa: F403

SECRET_KEY = os.environ.get("SECRET_KEY") or "test-insecure-key"
ALLOWED_HOSTS = ["testserver", "localhost"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
