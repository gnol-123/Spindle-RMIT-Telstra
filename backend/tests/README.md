# Backend tests

Unit tests for the FastAPI backend. Everything is faked: no Supabase, E2B, push service or model calls.

## Run

From `backend/`, in CI or any checkout with no `.env`:

    ENVIRONMENT=test ANTHROPIC_API_KEY="" pytest -q

Never run it from a folder that holds a real `.env`. Settings load `.env` from the current directory, so a developer machine with production credentials would feed them to the suite. CI has no `.env`, and the suite must pass that way. To run locally, point at the config from a clean folder:

    cd <empty folder>
    ENVIRONMENT=test ANTHROPIC_API_KEY="" python -m pytest -q -c <repo>/backend/pyproject.toml --rootdir <repo>/backend <repo>/backend/tests

## CI

`.github/workflows/ci.yml`, from `backend/`:

- `ruff check .` and `ruff format --check .`
- `pytest -q` with `ENVIRONMENT=test` and an empty `ANTHROPIC_API_KEY`
- bandit on `app`, pip-audit, gitleaks, Trivy

## conftest.py

- `client`: a `TestClient` on the real app.
- Autouse resets of process-wide state, so tests do not leak into each other:
  - the catalog cache
  - the signed preview URL cache
  - the auth token cache
  - held sandbox connections (`workspace._HELD`)
- Autouse push stub: `push_enabled` is False, so no test reaches a push service.

## fakes_e2b.py

Helper, not a test. A fake E2B `AsyncSandbox` (files, commands, calls log) shared by the `test_environments_*` modules.

## e2e_*.py

Manual scripts, not collected by pytest. They hit a running backend over HTTP, log in, create a throwaway project and delete it at the end. Some call a real model, so they cost tokens.

| Script | Checks |
|---|---|
| `e2e_defaults.py` | default tools and skills wired on new agents |
| `e2e_orchestrator.py` | orchestrator canvas tools (`--full` runs the whole pipeline) |
| `e2e_parity.py` | tool and skill parity across agent types |
| `e2e_patch_kinds.py` | PATCH by node kind, and the 404 hints |
| `e2e_provider.py` | model list and the per-node model override |

Run when you change the matching API, seed data or provider settings, against a local backend:

    python tests/e2e_defaults.py

Credentials: `E2E_TOKEN`, or `E2E_EMAIL` and `E2E_PASSWORD`. All five read `backend/.env` as a fallback (via `dotenv_values`) and environment variables win. `e2e_provider.py` reads `.env` for credentials only; `E2E_BASE` there comes from the environment. `E2E_BASE` sets the target, default `http://127.0.0.1:8000`. A non-local target is refused unless `E2E_ALLOW_REMOTE=1` (set in the environment or `.env`; `e2e_provider.py`: environment only).

## Known gaps

- `app/services/recovery.py` (the recovery loop) is covered by `test_durability.py`, but there is no test against a real database, so the compare-and-set claim is only checked against an in-memory fake.
- The e2e scripts depend on seeded catalog names (skill and tool titles) and are not run in CI.
