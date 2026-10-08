from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection


@pytest.mark.django_db
def test_btree_gist_extension_is_installed():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'btree_gist'")
        assert cursor.fetchone() is not None


@pytest.mark.django_db
def test_exclusion_constraints_exist():
    with connection.cursor() as cursor:
        cursor.execute("SELECT conname FROM pg_constraint WHERE contype = 'x' ORDER BY conname")
        names = [row[0] for row in cursor.fetchall()]

    assert names == ["no_bay_overlap", "no_technician_overlap", "no_vehicle_overlap"]


@pytest.mark.django_db
def test_models_and_migrations_are_in_sync():
    call_command("makemigrations", "--check", "--dry-run", stdout=StringIO())
