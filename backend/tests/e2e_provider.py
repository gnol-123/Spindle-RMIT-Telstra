"""End-to-end check of the Ollama switch and the per-node model override.

Manual script, not run by pytest. E2E_EMAIL and E2E_PASSWORD are read
from backend/.env by the login helper and go straight into the login request;
they are never printed.

    python tests/e2e_provider.py

Creates one throwaway project and deletes it at the end.
"""

import os
import pathlib
import sys
from urllib.parse import urlparse

import httpx

BASE = os.environ.get("E2E_BASE", "http://127.0.0.1:8000")


if urlparse(BASE).hostname not in ("127.0.0.1", "localhost", "::1") and not os.environ.get(
    "E2E_ALLOW_REMOTE"
):
    sys.exit(f"refusing non-local E2E_BASE {BASE}; set E2E_ALLOW_REMOTE=1 to allow")
DEFAULT_MODEL = "deepseek-v4.1-flash"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}"[:400], flush=True)


def token(http: httpx.Client) -> str:
    """Log in with the e2e credentials.

    Settings has extra="ignore", so undeclared .env vars are not exposed on it.
    dotenv_values reads the file here; the values go straight into the login
    request and are never printed.
    """
    from dotenv import dotenv_values

    env = dotenv_values(pathlib.Path(__file__).parent.parent / ".env")
    email = os.environ.get("E2E_EMAIL") or env.get("E2E_EMAIL") or ""
    password = os.environ.get("E2E_PASSWORD") or env.get("E2E_PASSWORD") or ""
    if not (email and password):
        sys.exit("E2E_EMAIL and E2E_PASSWORD must be set in backend/.env")
    r = http.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def main() -> int:
    with httpx.Client(timeout=300) as http:
        http.headers["Authorization"] = f"Bearer {token(http)}"

        # The provider's catalogue is reachable, and it is Ollama's, not Google's.
        models = http.get(f"{BASE}/models")
        check("GET /models returns 200", models.status_code == 200, str(models.status_code))
        names = models.json() if models.status_code == 200 else []
        check(f"catalogue contains {DEFAULT_MODEL}", DEFAULT_MODEL in names, f"{len(names)} models")
        check(
            "catalogue has no gemini models",
            not any("gemini" in n for n in names),
            str([n for n in names if "gemini" in n]),
        )

        # Every agent type now defaults to the new model.
        types = http.get(f"{BASE}/agent-types").json()
        check("all agent types exist", len(types) == 4, str([t["slug"] for t in types]))

        pid = http.post(f"{BASE}/projects", json={"name": "e2e provider check"}).json()["id"]
        try:
            agent = http.post(
                f"{BASE}/projects/{pid}/nodes",
                json={"kind": "agent", "agent_slug": "market_research"},
            ).json()
            check(
                "new node inherits the type's model",
                agent.get("model") == DEFAULT_MODEL,
                str(agent.get("model")),
            )

            # A bogus model is refused before it can break a turn.
            bad = http.patch(
                f"{BASE}/projects/{pid}/nodes/{agent['id']}", json={"model": "deepseek-4.1-flash"}
            )
            check("bogus model is 422", bad.status_code == 422, str(bad.status_code))
            check("422 names the real options", "Unknown model" in bad.text, bad.text[:120])

            # A real override sticks.
            other = next((n for n in names if n != DEFAULT_MODEL), None)
            if other is None:
                check("a second model exists to override with", False)
            else:
                ok = http.patch(f"{BASE}/projects/{pid}/nodes/{agent['id']}", json={"model": other})
                check("override accepted", ok.status_code == 200, str(ok.status_code))
                check(
                    "override reported back",
                    ok.json().get("model") == other,
                    str(ok.json().get("model")),
                )
                listed = http.get(f"{BASE}/projects/{pid}/nodes").json()
                node = next(n for n in listed if n["id"] == agent["id"])
                check(
                    "override survives a re-read",
                    node.get("model") == other,
                    str(node.get("model")),
                )

                # Clearing it restores inheritance.
                cleared = http.patch(
                    f"{BASE}/projects/{pid}/nodes/{agent['id']}", json={"model": ""}
                )
                check(
                    "cleared override inherits again",
                    cleared.json().get("model") == DEFAULT_MODEL,
                    str(cleared.json().get("model")),
                )

            # A real turn, with tools, on the new provider.
            http.patch(f"{BASE}/projects/{pid}/nodes/{agent['id']}", json={"tool_policy": "auto"})
            reply = http.post(
                f"{BASE}/chat",
                json={
                    "node_id": agent["id"],
                    "prompt": "Load your research method skill, then say READY in one word.",
                },
            ).json()
            out = reply.get("output") or ""
            check("turn completed on the new provider", bool(out), str(reply)[:200])

            msgs = http.get(f"{BASE}/projects/{pid}/nodes/{agent['id']}/messages")
            if msgs.status_code == 200:
                used = {m.get("model") for m in msgs.json() if m.get("model")}
                check(
                    "assistant row records the new model",
                    used and all("deepseek" in m for m in used),
                    str(used),
                )

            edges = http.get(f"{BASE}/projects/{pid}/edges").json()
            tool_ids = [
                e["source_node_id"]
                for e in edges
                if e["kind"] == "tool" and e["target_node_id"] == agent["id"]
            ]
            ok_calls = []
            for tid in tool_ids:
                ok_calls += [
                    c["tool_name"]
                    for c in http.get(f"{BASE}/projects/{pid}/nodes/{tid}/tool-calls").json()
                    if c["status"] == "ok"
                ]
            check("a tool call succeeded on the new provider", bool(ok_calls), str(ok_calls))
        finally:
            http.delete(f"{BASE}/projects/{pid}")

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
