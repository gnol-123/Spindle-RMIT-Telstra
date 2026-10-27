"""Check the PATCH-by-kind behaviour: the directing 404 and the env route.

Manual script, not run by pytest. E2E_EMAIL and E2E_PASSWORD are read
from backend/.env and go straight into the login request; never printed.

    python tests/e2e_patch_kinds.py
"""

import os
import pathlib
import sys
from urllib.parse import urlparse

import httpx
from dotenv import dotenv_values

_ENV = {**dotenv_values(pathlib.Path(__file__).parent.parent / ".env"), **os.environ}
BASE = _ENV.get("E2E_BASE", "http://127.0.0.1:8000")


if urlparse(BASE).hostname not in ("127.0.0.1", "localhost", "::1") and not _ENV.get(
    "E2E_ALLOW_REMOTE"
):
    sys.exit(f"refusing non-local E2E_BASE {BASE}; set E2E_ALLOW_REMOTE=1 to allow")

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}"[:300], flush=True)


def token(http: httpx.Client) -> str:
    email = _ENV.get("E2E_EMAIL") or ""
    password = _ENV.get("E2E_PASSWORD") or ""
    if not (email and password):
        sys.exit("E2E_EMAIL and E2E_PASSWORD must be set in backend/.env")
    r = http.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def main() -> int:
    with httpx.Client(timeout=120) as http:
        http.headers["Authorization"] = f"Bearer {token(http)}"
        pid = http.post(f"{BASE}/projects", json={"name": "e2e patch kinds"}).json()["id"]
        try:
            agent = http.post(
                f"{BASE}/projects/{pid}/nodes",
                json={"kind": "agent", "agent_slug": "market_research"},
            ).json()
            nodes = http.get(f"{BASE}/projects/{pid}/nodes").json()
            env = next((n for n in nodes if n["kind"] == "environment"), None)
            tool = next((n for n in nodes if n["kind"] == "tool"), None)
            check("scratch environment exists", env is not None)
            check("a tool node exists", tool is not None)

            # The agent route still works for an agent.
            ok = http.patch(f"{BASE}/projects/{pid}/nodes/{agent['id']}", json={"position_x": 42})
            check("agent patch still 200", ok.status_code == 200, str(ok.status_code))

            # An environment id on the agent route: 404 that names the right route.
            if env is not None:
                miss = http.patch(
                    f"{BASE}/projects/{pid}/nodes/{env['id']}", json={"position_x": 7}
                )
                check("env on agent route is 404", miss.status_code == 404, str(miss.status_code))
                detail = miss.json().get("detail", "")
                check("404 says it is an environment", "environment" in detail, detail)
                check("404 names the environments route", "/environments/" in detail, detail)
                check("404 no longer says 'Agent not found'", detail != "Agent not found", detail)

                # And the route it points at works.
                fixed = http.patch(
                    f"{BASE}/projects/{pid}/environments/{env['id']}", json={"position_x": 7}
                )
                check("the named route works", fixed.status_code == 200, str(fixed.status_code))

            # A tool id on the agent route: 404 that says so, with no invented URL.
            if tool is not None:
                miss = http.patch(
                    f"{BASE}/projects/{pid}/nodes/{tool['id']}", json={"position_x": 7}
                )
                check("tool on agent route is 404", miss.status_code == 404, str(miss.status_code))
                detail = miss.json().get("detail", "")
                check("404 says it is a tool", "tool" in detail, detail)
                check(
                    "404 points at verify, not a fake config route",
                    "/verify" in detail and "/config" not in detail,
                    detail,
                )

            # A genuinely absent node still reads as not found.
            gone = http.patch(
                f"{BASE}/projects/{pid}/nodes/11111111-2222-3333-4444-555555555555",
                json={"position_x": 7},
            )
            check("absent node is 404", gone.status_code == 404, str(gone.status_code))
            check(
                "absent node says 'Node not found'",
                gone.json().get("detail") == "Node not found",
                str(gone.json().get("detail")),
            )
        finally:
            http.delete(f"{BASE}/projects/{pid}")

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
