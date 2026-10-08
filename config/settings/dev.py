"""Local development settings."""

import os

from .base import *  # noqa: F403

DEBUG = True
SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-insecure-key-not-for-production"
ALLOWED_HOSTS = ALLOWED_HOSTS or ["localhost", "127.0.0.1"]  # noqa: F405

# WhiteNoise serves collected static files in the container only.
MIDDLEWARE = [m for m in MIDDLEWARE if not m.startswith("whitenoise.")]  # noqa: F405
