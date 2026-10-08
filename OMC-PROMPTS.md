# Using SPEC.md with oh-my-claudecode (OMC)

## Install (from the project's README)
```
/plugin marketplace add https://github.com/Yeachan-Heo/oh-my-claudecode
/plugin install oh-my-claudecode
/setup
```
(npm alternative: `npm i -g oh-my-claude-sisyphus@latest`.) Run the plugin's help/command list in your session to see the exact skills available in your version, since names change between releases.

## Suggested flow
1. `git init`, copy `SPEC.md` into the repo root.
2. **Clarify first.** (The spec targets Django 5 + DRF + PostgreSQL.) OMC ships a deep-interview skill; use it with: *"Read SPEC.md. Interview me on anything ambiguous or risky before building. Do not change the assumptions table without asking."*
3. **Build milestone by milestone** (don't hand over the whole spec at once, so you can verify each step):
   > "Implement milestone 1 and 2 of SPEC.md section 12. Write tests first where §8 applies. Stop and summarize when done."
4. **Verify yourself after each milestone:** run the tests, run `docker compose up`, hit the endpoints with curl, read the diff. Note anything wrong in §13 of the spec.
5. **Use a review/critic pass** (an OMC reviewer/verifier-style agent if available, or plain Claude Code):
   > "Review the booking transaction for race conditions and for any logic that duplicates what the DB exclusion constraints already guarantee."
6. If you try OMC's parallel/team modes, give each agent a disjoint area (e.g., booking app vs. observability vs. docs) to avoid merge conflicts.

## Prompt snippets worth reusing
- "Show me the failing concurrency test before implementing the fix."
- "List every assumption you made that is not in SPEC.md."
- "What would break at 100x load? Only answer; don't change code."

## Django-specific checks to run after each milestone
- `python manage.py makemigrations --check` shows no drift; migration 1 enables `BtreeGistExtension`.
- `pytest` passes with a real Postgres (no SQLite, since exclusion constraints need Postgres).
- Grep for `IntegrityError` handling and confirm it checks SQLSTATE `23P01` before retrying.
- Confirm no naive datetimes (`USE_TZ=True`) and no N+1 queries in serializers.

## Load-test prompt (after milestone 8)
> "Write Locust scenarios in tests/load for SPEC.md section 2.1: sustained (10 booking TPS, 100 availability TPS) and burst (50/500 TPS for 60 s) plus a hot-slot scenario. Run them against docker compose, report p95/p99 and error rate, and tell me what the bottleneck is before changing any config."

## DDD-specific prompts and checks
- Milestone 2: *"Implement only the domain layer from SPEC.md section 4.3 under contexts/scheduling/domain. No Django, DRF or database imports. Write the unit tests first. Run `lint-imports` and pytest tests/unit/domain."*
- Milestone 3: *"Implement the application layer using in-memory fakes for the ports. Do not touch Django."*
- Milestone 4: *"Implement infrastructure only. Domain objects must not import ORM models; use mappers."*
- After every milestone run `lint-imports`. If the agent edits `.importlinter` to make it pass, reject the change.
- Ask: *"Where does any business rule live outside the domain layer?"* and move it if found.

## Kickoff prompt (copy-paste to your agent)
> Read CLAUDE.md and SPEC.md completely. Do not write code yet. First reply with: (1) a 10-line summary of what you will build, (2) any ambiguities or risks you see in the spec, and (3) your plan for milestone 1. Wait for my approval, then implement milestone 1 only, run the checks in SPEC.md section 0, and report.

Repeat for each milestone: *"Proceed to milestone N. Same rules."*

## Setup checklist
1. `git init`; copy `SPEC.md`, `CLAUDE.md` (Claude Code reads CLAUDE.md automatically) and `OMC-PROMPTS.md` into the repo root.
2. Install the OMC plugin (see top of this file) and open Claude Code in the repo.
3. Paste the kickoff prompt above.
