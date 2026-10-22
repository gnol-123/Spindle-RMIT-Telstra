import test from "node:test";
import assert from "node:assert/strict";
// @ts-expect-error node needs the .ts extension; tsc does not allow it
import { agentProvisioned } from "./provision.ts";

const tool = (id: string, status: string) => ({ id, kind: "tool", status });
const edge = (s: string, t = "a", kind = "tool") => ({ kind, source_node_id: s, target_node_id: t });

test("no presets unlocks at once", () => assert.equal(agentProvisioned("a", [], [], 0), true));
test("waits for expected count", () =>
  assert.equal(agentProvisioned("a", [tool("t1", "ready")], [edge("t1")], 2), false));
test("pending tool keeps lock", () =>
  assert.equal(agentProvisioned("a", [tool("t1", "ready"), tool("t2", "pending")], [edge("t1"), edge("t2")], 2), false));
test("ready and error unlock", () =>
  assert.equal(agentProvisioned("a", [tool("t1", "ready"), tool("t2", "error")], [edge("t1"), edge("t2")], 2), true));
test("ignores other agents and non-tool edges", () =>
  assert.equal(agentProvisioned("a", [tool("t1", "ready")], [edge("t1", "b"), edge("t1", "a", "context")], 1), false));
