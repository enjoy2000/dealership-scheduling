"""Responses validate against the drf-spectacular schema (the stubbed client's contract)."""

from typing import Any, cast

import pytest
from drf_spectacular.generators import SchemaGenerator
from jsonschema import Draft202012Validator

from tests.api.conftest import booking, post_booking

pytestmark = pytest.mark.usefixtures("seeded")


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    generator = SchemaGenerator()  # type: ignore[no-untyped-call]
    return cast(dict[str, Any], generator.get_schema(request=None, public=True))  # type: ignore[no-untyped-call]


def validate(schema: dict[str, Any], component: str, instance: Any) -> None:
    document = {"$ref": f"#/components/schemas/{component}", "components": schema["components"]}
    Draft202012Validator(document).validate(instance)


def response_component(schema, path: str, method: str, status: str) -> str:
    content = schema["paths"][path][method]["responses"][status]["content"]
    media = content.get("application/json") or content["application/problem+json"]
    return str(media["schema"]["$ref"]).rsplit("/", 1)[-1]


def test_schema_and_docs_are_served(api):
    assert api.get("/api/v1/schema/").status_code == 200
    assert api.get("/api/v1/docs/").status_code == 200


def test_201_matches_schema(api, schema):
    response = post_booking(api, booking())

    validate(
        schema, response_component(schema, "/api/v1/appointments/", "post", "201"), response.json()
    )


@pytest.mark.parametrize(
    ("body", "status"),
    [
        (booking(customer=99), "404"),
        (booking(customer=2), "422"),
        ({"customer_id": "x"}, "400"),
    ],
)
def test_error_responses_match_schema(api, schema, body, status):
    response = post_booking(api, body)

    assert str(response.status_code) == status
    component = response_component(schema, "/api/v1/appointments/", "post", status)
    validate(schema, component, response.json())


def test_schema_documents_idempotency_key_and_location(schema):
    operation = schema["paths"]["/api/v1/appointments/"]["post"]

    header = next(p for p in operation["parameters"] if p["name"] == "Idempotency-Key")
    assert header["in"] == "header"
    assert header["required"] is True
    assert "Location" in operation["responses"]["201"]["headers"]
    assert "204" in schema["paths"]["/api/v1/appointments/{id}/"]["delete"]["responses"]
