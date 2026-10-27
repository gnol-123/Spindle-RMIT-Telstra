"""Task 5: end-to-end check of agent parity against a running backend.

Manual script, not run by pytest. Credentials come from backend/.env:
  E2E_EMAIL + E2E_PASSWORD, or E2E_TOKEN. Optional E2E_BASE.

    python tests/e2e_parity.py

Creates one throwaway project and deletes it at the end.
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

CODING = [
    "Web Fetch",
    "Context7",
    "Plan Before Code",
    "Coding Conventions",
    "Test Driven Development",
    "Systematic Debugging",
    "Code Review",
    "Security Basics",
    "Verify Before Done",
    "Working in a Repo",
    "Plain Writing",
    "Workspace Memory",
]
UX_UI = [
    "Brave Search",
    "Web Fetch",
    "Brainstorming",
    "Design Brief",
    "Prototype Design",
    "Accessibility Basics",
    "Plain Writing",
    "Workspace Memory",
]

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}"[:400], flush=True)


def token(http: httpx.Client) -> str:
    if _ENV.get("E2E_TOKEN"):
        return _ENV["E2E_TOKEN"]
    email, password = _ENV.get("E2E_EMAIL"), _ENV.get("E2E_PASSWORD")
    if not (email and password):
        sys.exit("set E2E_TOKEN, or E2E_EMAIL and E2E_PASSWORD, in backend/.env")
    r = http.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def tools_for(http, pid, agent_id):
    """Tool nodes wired into one agent, in creation order."""
    edges = http.get(f"{BASE}/projects/{pid}/edges").json()
    ids = [
        e["source_node_id"]
        for e in edges
        if e["kind"] == "tool" and e["target_node_id"] == agent_id
    ]
    nodes = {n["id"]: n for n in http.get(f"{BASE}/projects/{pid}/nodes").json()}
    return [nodes[i] for i in ids if i in nodes]


def main() -> int:
    with httpx.Client(timeout=180) as http:
        http.headers["Authorization"] = f"Bearer {token(http)}"

        presets = {p["slug"]: p for p in http.get(f"{BASE}/tool-presets").json()}
        check("22 presets in the library", len(presets) == 22, str(len(presets)))
        check(
            "context7 preset over its own type",
            presets.get("context7", {}).get("tool_slug") == "context7",
        )
        for slug in ("plain_writing", "tdd", "workspace_memory", "prototype_design"):
            check(
                f"{slug} preset carries text",
                bool(presets.get(slug, {}).get("config", {}).get("text")),
            )

        agents = {a["slug"]: a for a in http.get(f"{BASE}/agent-types").json()}
        check(
            "coding lists 12 presets",
            len(agents["coding"]["default_presets"]) == 12,
            str(agents["coding"]["default_presets"]),
        )
        check(
            "plain_writing on all four agents",
            all("plain_writing" in a["default_presets"] for a in agents.values()),
            str({s: "plain_writing" in a["default_presets"] for s, a in agents.items()}),
        )
        check(
            "coding has no brave_search", "brave_search" not in agents["coding"]["default_presets"]
        )

        pid = http.post(f"{BASE}/projects", json={"name": "e2e parity check"}).json()["id"]
        try:
            # Coding agent arrives fully equipped.
            coding = http.post(
                f"{BASE}/projects/{pid}/nodes",
                json={
                    "kind": "agent",
                    "agent_slug": "coding",
                    "position_x": 600,
                    "position_y": 100,
                },
            ).json()
            tools = tools_for(http, pid, coding["id"])
            check("coding wired to 12 tool nodes", len(tools) == 12, str(len(tools)))
            check(
                "coding box names match the plan",
                sorted(n["name"] for n in tools) == sorted(CODING),
                str(sorted(n["name"] for n in tools)),
            )
            bad = {
                n["name"]: (n["status"], n["status_detail"])
                for n in tools
                if n["status"] != "ready"
            }
            check("every coding box ready", not bad, str(bad))

            c7 = next((n for n in tools if n["name"] == "Context7"), None)
            if c7 is None:
                check("context7 node present", False)
            else:
                node = http.post(f"{BASE}/projects/{pid}/nodes/{c7['id']}/verify").json()
                discovered = node.get("config", {}).get("discovered_tools") or []
                check(
                    "context7 platform key in effect",
                    node.get("platform_provided") == ["auth_token"]
                    and node.get("secrets_set") == [],
                    str({k: node.get(k) for k in ("status", "platform_provided", "secrets_set")}),
                )
                check(
                    "context7 discovered its tools",
                    any("resolve" in t for t in discovered) and any("doc" in t for t in discovered),
                    str(discovered),
                )

            # One turn that loads several skills and does a real docs lookup.
            http.patch(f"{BASE}/projects/{pid}/nodes/{coding['id']}", json={"tool_policy": "auto"})
            reply = http.post(
                f"{BASE}/chat",
                json={
                    "node_id": coding["id"],
                    "prompt": (
                        "Do these in order. 1) Load your Plain Writing skill. "
                        "2) Load your TDD skill. "
                        "3) Load your Workspace Memory skill. 4) Use Context7 to look up how "
                        "pydantic-ai's FunctionToolset.add_function works. "
                        "Then summarise what you found "
                        "in two sentences."
                    ),
                },
            ).json()
            check(
                "coding turn produced a reply",
                bool(reply.get("output")),
                str(reply.get("output"))[:200],
            )

            calls = {}
            for n in tools:
                for c in http.get(f"{BASE}/projects/{pid}/nodes/{n['id']}/tool-calls").json():
                    calls.setdefault(n["name"], []).append((c["tool_name"], c["status"]))
            for name in ("Plain Writing", "Test Driven Development", "Workspace Memory"):
                check(
                    f"{name} skill loaded ok",
                    any(s == "ok" for _, s in calls.get(name, [])),
                    str(calls.get(name)),
                )
            check(
                "context7 docs lookup ok",
                any(s == "ok" for _, s in calls.get("Context7", [])),
                str(calls.get("Context7")),
            )

            # ux_ui arrives with the design set.
            ux = http.post(
                f"{BASE}/projects/{pid}/nodes", json={"kind": "agent", "agent_slug": "ux_ui"}
            ).json()
            ux_tools = tools_for(http, pid, ux["id"])
            check("ux_ui wired to 8 tool nodes", len(ux_tools) == 8, str(len(ux_tools)))
            check(
                "ux_ui box names match the plan",
                sorted(n["name"] for n in ux_tools) == sorted(UX_UI),
                str(sorted(n["name"] for n in ux_tools)),
            )
        finally:
            http.delete(f"{BASE}/projects/{pid}")

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
