# Security fixes

From the full-codebase security review (22 Oct 2026). Branch `fix/security-review`, based on `main`.

## 1. Gmail connect can be hijacked (high)
Problem: the OAuth state proves which node is being connected, but not who is clicking. A consent link sent to a colleague puts their Gmail into the sender's node.

Fix:
- `/oauth/callback` stops saving the token. It redirects to the frontend with `code` and `state`.
- New route `POST /oauth/complete` (bearer auth). It checks the state's owner matches the caller, then exchanges the code and saves the token.
- The frontend page that already reads `?oauth=` posts the code and state to `/oauth/complete`, then clears them from the URL.
- Gmail always uses the catalog MCP URL, never a user-edited one, so a token can't be sent to someone else's server.
- No change to the redirect URI registered at Google.

## 2. Logout signs out the wrong person (medium)
Problem: login and refresh run on one shared Supabase client, which remembers the last session. Logout then revokes that session, which belongs to whoever logged in last.

Fix:
- Login and refresh use a fresh client per call, so nothing is remembered.
- Logout revokes the caller's own session with their token (`scope=local`).
- After merging `backend-perf`: logout also drops the token from its 60s token cache.

## 3. MCP tools can reach internal addresses (medium)
Problem: a user-supplied MCP URL is called from the backend with no address check.

Fix: reuse web_fetch's public-address check when a tool is verified and when it is built. Skipped when `ENVIRONMENT=development`, so local bridges (Obsidian) still work on a laptop.

## 4. Terminal token lands in logs (low)
Fix:
- A logging filter in the backend redacts `token=` from uvicorn's log lines.
- nginx logs the path without the query string.

## 5. CORS default is `*` (low)
Fix: the default becomes `http://localhost:3000`. **Before merging:** check `CORS_ORIGINS` is set on Railway, or production requests will be blocked.

## 6. Markdown fallback could render raw HTML (low)
Fix: the fallback escapes the code before display.

## Not changing
Prompt injection between tools: the default `ask` tool policy already covers it.

## Merging
- `backend-perf` worktree changes `backend/app/routers/auth.py` (token cache) and `projects.py`. Fix 2 touches the same file in different functions. Merge by hand after both land.
- `feature/canvas-realtime` touches only frontend canvas files and one migration. No overlap expected.

## Checks
- A test per fix (kept local, `backend/tests/` is gitignored).
- `ruff`, `pytest`, frontend `tsc`.
