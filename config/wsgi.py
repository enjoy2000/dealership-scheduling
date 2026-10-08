import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

# Tracing must hook in before the WSGI handler loads its middleware.
from contexts.scheduling.infrastructure.telemetry.tracing import configure_tracing

configure_tracing()

application = get_wsgi_application()
