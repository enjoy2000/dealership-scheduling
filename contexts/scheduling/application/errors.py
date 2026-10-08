"""Application-level errors (not business rules)."""


class NotFoundError(Exception):
    """A referenced dealership, customer, vehicle, service type or appointment does not exist."""

    code = "not_found"

    def __init__(self, resource: str, identifier: object) -> None:
        super().__init__(f"Unknown {resource.replace('_', ' ')}: {identifier}.")
        self.resource = resource
        self.identifier = identifier
