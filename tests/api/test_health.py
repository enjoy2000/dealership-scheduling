import pytest
from django.db import connection
from django.test import Client


def test_healthz_reports_process_up(client: Client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_readyz_reports_database_up(client: Client):
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["database"] == "up"


@pytest.mark.django_db
def test_tests_run_on_real_postgresql():
    assert connection.vendor == "postgresql"
