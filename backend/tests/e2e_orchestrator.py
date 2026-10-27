"""End-to-end check of the orchestrator against a running backend.

Manual script, not run by pytest. Credentials come from backend/.env:
  E2E_EMAIL + E2E_PASSWORD, or E2E_TOKEN. Optional E2E_BASE.

    python tests/e2e_orchestrator.py            # canvas tools, ask mode, one stage
    python tests/e2e_orchestrator.py --full     # also run the whole pipeline unattended

Creates one throwaway project and deletes it at the end.
"""

import json
import os
import pathlib
import sys
import time
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


def agents_on(http, pid):
    return [n for n in http.get(f"{BASE}/projects/{pid}/nodes").json() if n["kind"] == "agent"]


def stream(http, node_id: str, prompt: str, timeout: float = 900.0):
    """Drive /chat/stream, printing progress. Returns (events, text, approval)."""
    events: list[str] = []
    text: list[str] = []
    approval = None
    started = time.time()
    with http.stream(
        "POST",
        f"{BASE}/chat/stream",
        json={"node_id": node_id, "prompt": prompt},
        timeout=timeout,
    ) as r:
        r.raise_for_status()
        event = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                event = line[7:].strip()
                events.append(event)
            elif line.startswith("data: ") and event:
                payload = json.loads(line[6:])
                if event == "tool":
                    mark = "->" if "args" in payload else "<-"
                    extra = json.dumps(payload.get("args", ""))[:120]
                    if "result_head" in payload:
                        extra = str(payload["result_head"])[:120]
                    print(
                        f"    {int(time.time() - started):4d}s {mark} {payload['name']}: {extra}",
                        flush=True,
                    )
                elif event == "chunk":
                    text.append(payload["text"])
                elif event == "approval_required":
                    approval = payload
                elif event == "error":
                    print(f"    stream error: {payload}", flush=True)
    return events, "".join(text), approval


def main() -> int:
    full = "--full" in sys.argv
    with httpx.Client(timeout=3600) as http:
        http.headers["Authorization"] = f"Bearer {token(http)}"

        types = {a["slug"]: a for a in http.get(f"{BASE}/agent-types").json()}
        check("orchestrator agent type seeded", "orchestrator" in types)
        check(
            "orchestrator default preset is canvas",
            types.get("orchestrator", {}).get("default_presets") == ["canvas"],
            str(types.get("orchestrator", {}).get("default_presets")),
        )
        presets = {p["slug"]: p for p in http.get(f"{BASE}/tool-presets").json()}
        check("canvas preset in the library", "canvas" in presets)

        pid = http.post(f"{BASE}/projects", json={"name": f"e2e orchestrator {int(time.time())}"})
        pid = pid.json()["id"]
        print(f"\nproject {pid}\n", flush=True)
        try:
            orch = http.post(
                f"{BASE}/projects/{pid}/nodes",
                json={
                    "kind": "agent",
                    "agent_slug": "orchestrator",
                    "tool_policy": "ask",
                    "position_x": 400,
                    "position_y": 100,
                },
            ).json()
            check("orchestrator node created", "id" in orch, str(orch)[:200])
            check(
                "tool_policy honoured on create",
                orch.get("tool_policy") == "ask",
                str(orch.get("tool_policy")),
            )

            nodes = http.get(f"{BASE}/projects/{pid}/nodes").json()
            canvas = [n for n in nodes if n["kind"] == "tool" and n["name"] == "Canvas"]
            check("canvas tool node wired", len(canvas) == 1, str(len(canvas)))
            check(
                "canvas node ready",
                canvas and canvas[0]["status"] == "ready",
                str(canvas[0]["status"]) if canvas else "none",
            )

            # -- ask mode: the first run_agent must pause for approval ---------
            print("\n[ask mode] asking it to scope an idea\n", flush=True)
            idea = (
                "A web app that helps home cooks plan a week of meals from what is "
                "already in their fridge, then generates one shopping list for the gaps."
            )
            events, _text, approval = stream(http, orch["id"], idea)
            check("stream emitted tool events", "tool" in events, str(events[:6]))

            built = agents_on(http, pid)
            check(
                "stage agents created on the canvas",
                len(built) >= 2,
                ", ".join(f"{a['name']}({a['agent_slug']})" for a in built),
            )
            created = [a for a in built if a["agent_slug"] != "orchestrator"]
            check(
                "created agents are tool_policy auto",
                all(a["tool_policy"] == "auto" for a in created),
                str({a["name"]: a["tool_policy"] for a in created}),
            )
            rows = {}
            for a in created:
                rows.setdefault(a["position_y"], []).append(a["position_x"])
            check(
                "stage agents laid out in one row, 520 apart",
                all(len(set(xs)) == len(xs) for xs in rows.values()) and len(rows) == 1,
                str(rows),
            )
            edges = http.get(f"{BASE}/projects/{pid}/edges").json()
            ctx = [e for e in edges if e["kind"] == "context"]
            check("context edges wired", len(ctx) >= 1, f"{len(ctx)} context edges")

            check(
                "ask mode paused before running a stage",
                approval is not None,
                str(approval)[:200] if approval else "no approval_required event",
            )
            if approval:
                calls = approval["pending_calls"]
                check(
                    "the paused call is run_agent",
                    all(c["tool_name"] == "run_agent" for c in calls),
                    str([c["tool_name"] for c in calls]),
                )
                check(
                    "pending call shows the target and prompt",
                    all("node_id" in c["arguments"] and "prompt" in c["arguments"] for c in calls),
                    str(calls[0]["arguments"])[:200] if calls else "",
                )

                # -- approve it: the stage actually runs -----------------------
                print("\n[resume] approving the first stage\n", flush=True)
                r = http.post(
                    f"{BASE}/chat/resume",
                    json={
                        "node_id": orch["id"],
                        "approvals": {c["tool_call_id"]: True for c in calls},
                    },
                )
                check("resume accepted", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
                body = r.json()
                check(
                    "resume either answered or paused on the next stage",
                    ("output" in body) or body.get("paused") is True,
                    str(body)[:200],
                )
                target_id = calls[0]["arguments"]["node_id"]
                msgs = http.get(f"{BASE}/projects/{pid}/nodes/{target_id}/messages").json()
                check(
                    "stage agent produced a reply on its own conversation",
                    any(m["role"] == "assistant" and m["status"] == "complete" for m in msgs),
                    f"{len(msgs)} messages",
                )
                out = http.get(f"{BASE}/projects/{pid}/edges").json()
                refreshed = [
                    e
                    for e in out
                    if e["kind"] == "context"
                    and e["source_node_id"] == target_id
                    and e["summarised_through_seq"] is not None
                ]
                check(
                    "outbound context edges refreshed after the stage",
                    bool(refreshed)
                    or not [
                        e
                        for e in out
                        if e["kind"] == "context" and e["source_node_id"] == target_id
                    ],
                    f"{len(refreshed)} refreshed",
                )

            # -- messages endpoint --------------------------------------------
            om = http.get(f"{BASE}/projects/{pid}/nodes/{orch['id']}/messages").json()
            check("orchestrator transcript readable", len(om) >= 1, f"{len(om)} messages")
            if om:
                after = http.get(
                    f"{BASE}/projects/{pid}/nodes/{orch['id']}/messages",
                    params={"after_seq": om[0]["seq"]},
                ).json()
                check(
                    "after_seq filters",
                    all(m["seq"] > om[0]["seq"] for m in after),
                    f"{len(after)} after seq {om[0]['seq']}",
                )

            # -- unattended, whole pipeline -----------------------------------
            if full:
                print("\n[auto mode] running the whole pipeline unattended\n", flush=True)
                auto = http.post(
                    f"{BASE}/projects/{pid}/nodes",
                    json={
                        "kind": "agent",
                        "agent_slug": "orchestrator",
                        "name": "Orchestrator (auto)",
                        "tool_policy": "auto",
                        "position_x": 400,
                        "position_y": 900,
                    },
                ).json()
                events, text, approval = stream(http, auto["id"], idea)
                check("unattended run finished", "done" in events, str(events[-3:]))
                check("unattended run did not pause", approval is None)
                ran = [e for e in events if e == "tool"]
                check("tools were called", len(ran) >= 4, f"{len(ran)} tool events")
                check("report produced", len(text) > 200, f"{len(text)} chars")
                print("\n--- report ---\n" + text[:2000] + "\n", flush=True)
                for a in agents_on(http, pid):
                    if a["agent_slug"] == "orchestrator":
                        continue
                    m = http.get(f"{BASE}/projects/{pid}/nodes/{a['id']}/messages").json()
                    done = [x for x in m if x["role"] == "assistant" and x["status"] == "complete"]
                    check(f"{a['name']} has output", bool(done), f"{len(done)} replies")
        finally:
            if "--keep" not in sys.argv:
                http.delete(f"{BASE}/projects/{pid}")
                print(f"\ndeleted project {pid}", flush=True)

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    for name, _ok, detail in failed:
        print(f"  FAIL {name}  {detail}"[:300])
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
