# Decisions

Decisions taken during implementation that are not spelled out in SPEC.md. Architectural decisions D1–D5 live in SPEC.md §4.6 and the SDD.

| # | Date | Decision | Rationale |
|---|------|----------|-----------|
| I1 | 2026-10-08 | All backing services (PostgreSQL, Redis, OTel collector, Prometheus) run only via `docker compose`; nothing is installed on the host. Host-side `pytest` uses the compose `db` service published on `localhost:5432` (`make deps` / `make test` start it). CI uses the same compose services. | Single source of truth for dependency versions; reproducible from a clean clone. |
| I2 | 2026-10-08 | `.importlinter` contract `catalog-only-via-gateway` sets `unmatched_ignore_imports_alerting = none` because `catalog_gateway.py` does not exist until milestone 4. To be tightened back to the default once the gateway exists. | import-linter otherwise errors on an ignore rule that matches nothing. The contract itself is not weakened. |
| I3 | 2026-10-08 | The Docker image installs the dev dependency group so tests and lint can run in-container; the runtime command is `gunicorn`. | Simplicity for the assessment; a slim prod stage is a later optimisation. |
| I4 | 2026-10-08 | Interface and infrastructure are modelled in import-linter as independent sibling layers under `contexts.scheduling`, with `container` as an optional top layer. | Encodes "interface must not import infrastructure except through container.py" (§8). |
