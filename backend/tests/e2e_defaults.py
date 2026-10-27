"""Task 9: end-to-end check of default wiring against a running backend.

Manual script, not run by pytest. Needs one of:
  E2E_TOKEN                      an access token from POST /auth/login
  E2E_EMAIL + E2E_PASSWORD       an existing account; the script logs in
Optional: E2E_BASE (default http://127.0.0.1:8000).

    python tests/e2e_defaults.py

Creates one throwaway project and deletes it at the end.
"""

import os
import pathlib
import sys
from urllib.parse import urlparse

import httpx
from dotenv import dotenv_values

# Env wins; backend/.env fills gaps so credentials need not be exported.
_ENV = {**dotenv_values(pathlib.Path(__file__).parent.parent / ".env"), **os.environ}

BASE = _ENV.get("E2E_BASE", "http://127.0.0.1:8000")


if urlparse(BASE).hostname not in ("127.0.0.1", "localhost", "::1") and not _ENV.get(
    "E2E_ALLOW_REMOTE"
):
    sys.exit(f"refusing non-local E2E_BASE {BASE}; set E2E_ALLOW_REMOTE=1 to allow")
EXPECTED = {
    "market_research": ["Brave Search", "Web Fetch", "Research Method", "Source Grading"],
    "coding": ["Web Fetch", "Coding Conventions", "Verify Before Done"],
}

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


def token(http: httpx.Client) -> str:
    if _ENV.get("E2E_TOKEN"):
        return _ENV["E2E_TOKEN"]
    email, password = _ENV.get("E2E_EMAIL"), _ENV.get("E2E_PASSWORD")
    if not (email and password):
        sys.exit("set E2E_TOKEN, or E2E_EMAIL and E2E_PASSWORD")
    r = http.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def main() -> int:
    with httpx.Client(timeout=120) as http:
        http.headers["Authorization"] = f"Bearer {token(http)}"

        # Library is visible.
        presets = http.get(f"{BASE}/tool-presets").json()
        slugs = {p["slug"] for p in presets}
        check("GET /tool-presets lists 10 presets", len(presets) == 10, str(sorted(slugs)))
        check(
            "skill preset carries text",
            any(p["slug"] == "research_method" and p["config"].get("text") for p in presets),
        )
        agent_types = {a["slug"]: a for a in http.get(f"{BASE}/agent-types").json()}
        check("ux_ui agent type exists", "ux_ui" in agent_types)
        check(
            "market_research default_presets",
            agent_types["market_research"]["default_presets"]
            == ["brave_search", "web_fetch", "research_method", "source_grading"],
            str(agent_types["market_research"]["default_presets"]),
        )

        project = http.post(f"{BASE}/projects", json={"name": "e2e defaults check"}).json()
        pid = project["id"]
        try:
            # Step 2: market_research arrives wired.
            agent = http.post(
                f"{BASE}/projects/{pid}/nodes",
                json={
                    "kind": "agent",
                    "agent_slug": "market_research",
                    "position_x": 400,
                    "position_y": 200,
                },
            ).json()
            nodes = http.get(f"{BASE}/projects/{pid}/nodes").json()
            edges = http.get(f"{BASE}/projects/{pid}/edges").json()
            tools = [n for n in nodes if n["kind"] == "tool"]
            tool_edges = [
                e for e in edges if e["kind"] == "tool" and e["target_node_id"] == agent["id"]
            ]
            env_edges = [e for e in edges if e["kind"] == "environment"]
            check("6 nodes (agent, scratch, 4 tools)", len(nodes) == 6, str(len(nodes)))
            check(
                "4 tool nodes named from presets",
                sorted(n["name"] for n in tools) == sorted(EXPECTED["market_research"]),
                str([n["name"] for n in tools]),
            )
            check("4 tool edges into the agent", len(tool_edges) == 4, str(len(tool_edges)))
            check("1 environment edge", len(env_edges) == 1, str(len(env_edges)))
            check(
                "every tool node ready",
                all(n["status"] == "ready" for n in tools),
                str({n["name"]: (n["status"], n["status_detail"]) for n in tools}),
            )
            check(
                "tools placed left of the agent",
                all(n["position_x"] == 400 - 260 for n in tools),
                str({n["name"]: n["position_x"] for n in tools}),
            )

            # Step 3: platform key in effect.
            brave = next(n for n in tools if n["name"] == "Brave Search")
            verified = http.post(f"{BASE}/projects/{pid}/nodes/{brave['id']}/verify").json()
            check(
                "brave_search platform_provided=['api_key'], secrets_set=[]",
                verified.get("platform_provided") == ["api_key"]
                and verified.get("secrets_set") == [],
                str(
                    {
                        k: verified.get(k)
                        for k in ("status", "status_detail", "platform_provided", "secrets_set")
                    }
                ),
            )

            # Step 4: chat, tool_policy auto so nothing pauses for approval.
            http.patch(f"{BASE}/projects/{pid}/nodes/{agent['id']}", json={"tool_policy": "auto"})
            reply = http.post(
                f"{BASE}/chat",
                json={
                    "node_id": agent["id"],
                    "prompt": (
                        "First load your research method skill. Then fetch https://example.com "
                        "and tell me its title. Then do one Brave search for 'example domain'."
                    ),
                },
            ).json()
            check(
                "chat returned an assistant message",
                bool(reply.get("assistant_message") or reply.get("output")),
                str(reply)[:300],
            )
            calls = {}
            for n in tools:
                for c in http.get(f"{BASE}/projects/{pid}/nodes/{n['id']}/tool-calls").json():
                    calls.setdefault(n["name"], []).append((c["tool_name"], c["status"]))
            check(
                "research_method skill was loaded ok",
                any(s == "ok" for _, s in calls.get("Research Method", [])),
                str(calls.get("Research Method")),
            )
            check(
                "web_fetch call ok",
                any(s == "ok" for _, s in calls.get("Web Fetch", [])),
                str(calls.get("Web Fetch")),
            )
            check(
                "brave_search call ok",
                any(s == "ok" for _, s in calls.get("Brave Search", [])),
                str(calls.get("Brave Search")),
            )

            # Step 7: standalone preset node.
            standalone = http.post(
                f"{BASE}/projects/{pid}/nodes", json={"kind": "tool", "preset_slug": "design_brief"}
            ).json()
            check(
                "standalone preset node ready with text",
                standalone.get("tool_slug") == "skill"
                and standalone.get("status") == "ready"
                and bool(standalone.get("config", {}).get("text")),
                str({k: standalone.get(k) for k in ("tool_slug", "status", "status_detail")}),
            )

            # Step 8: coding gets fetch + two skills, no search.
            coding = http.post(
                f"{BASE}/projects/{pid}/nodes", json={"kind": "agent", "agent_slug": "coding"}
            ).json()
            edges = http.get(f"{BASE}/projects/{pid}/edges").json()
            coding_tool_ids = {
                e["source_node_id"]
                for e in edges
                if e["kind"] == "tool" and e["target_node_id"] == coding["id"]
            }
            nodes = http.get(f"{BASE}/projects/{pid}/nodes").json()
            coding_tools = sorted(n["name"] for n in nodes if n["id"] in coding_tool_ids)
            check(
                "coding wired to fetch + 2 skills, no search",
                coding_tools == sorted(EXPECTED["coding"]),
                str(coding_tools),
            )
        finally:
            http.delete(f"{BASE}/projects/{pid}")

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
