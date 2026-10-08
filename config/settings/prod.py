"""Production settings: everything required comes from the environment."""

import os

from .base import *  # noqa: F403

SECRET_KEY = os.environ["SECRET_KEY"]
