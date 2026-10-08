# CLAUDE.md

Project: Unified Service Scheduler (Keyloop assessment, Scenario A), Django backend.

**The full specification is in `SPEC.md`. Read it completely before writing any code.** It is authoritative. Section 0 is your working agreement; section 14 has concrete details (IDs, error codes, examples, seed data, env vars, commands).

## Non-negotiables
- Implement milestones in SPEC.md section 12, in order, one at a time. Stop after each and report.
- Architecture is Domain-Driven Design with layers: domain -> application -> infrastructure/interface. The domain layer must not import Django or DRF.
- Resource exclusivity is enforced by PostgreSQL exclusion constraints (bay, technician, vehicle). Tests must run on real PostgreSQL, never SQLite.
- Tests first for domain and application code.
- Before finishing a milestone run: `ruff check`, `mypy`, `pytest`, `lint-imports`. Never weaken tests or edit `.importlinter` to make checks pass.
- Do not change assumptions, stack, layering or constraints without asking. Record any new decision in `docs/DECISIONS.md`.
- Log each milestone in `docs/AI_LOG.md`.
- No secrets in git; configuration via environment variables.

## Commands (create a Makefile)
`make up`, `make migrate`, `make seed`, `make test`, `make lint`, `make arch`, `make schema`, `make load`
