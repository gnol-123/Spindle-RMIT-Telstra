import test from "node:test";
import assert from "node:assert/strict";
// @ts-expect-error node needs the .ts extension; tsc does not allow it
import { groupByProject, markProjectRead, unreadElsewhere, upsert } from "./notifications.ts";
import type { AppNotification } from "./types";

let seq = 0;
const n = (o: Partial<AppNotification> = {}): AppNotification => ({
  id: `n${++seq}`, project_id: "p1", node_id: "x", message_id: "m", status: "complete",
  node_name: "Agent", project_name: "P1", nested: false, excerpt: null, read_at: null,
  created_at: "2026-01-01T00:00:00Z", ...o,
});

test("groupByProject orders groups by newest item", () => {
  const list = [
    n({ id: "a", project_id: "p1", created_at: "2026-01-01T00:00:00Z" }),
    n({ id: "b", project_id: "p2", project_name: "P2", created_at: "2026-01-03T00:00:00Z" }),
    n({ id: "c", project_id: "p1", created_at: "2026-01-02T00:00:00Z" }),
  ];
  const g = groupByProject(list);
  assert.deepEqual(g.map((x: { projectId: string }) => x.projectId), ["p2", "p1"]);
  assert.deepEqual(g[1].items.map((x: AppNotification) => x.id), ["c", "a"]);
  assert.equal(g[0].projectName, "P2");
});
test("unreadElsewhere ignores the open project", () => {
  assert.equal(unreadElsewhere([n({ project_id: "p1" })], "p1"), false);
  assert.equal(unreadElsewhere([n({ project_id: "p2" })], "p1"), true);
});
test("unreadElsewhere false when all read", () => {
  assert.equal(unreadElsewhere([n({ project_id: "p2", read_at: "2026-01-02T00:00:00Z" })], null), false);
});
test("upsert replaces by id (read_at update from another device)", () => {
  const a = n({ id: "a" }), b = n({ id: "b" });
  const out = upsert([a, b], { ...a, read_at: "2026-01-02T00:00:00Z" }, "UPDATE");
  assert.equal(out.length, 2);
  assert.equal(out[0].read_at, "2026-01-02T00:00:00Z");
});
test("upsert prepends new rows", () => {
  const a = n({ id: "a" }), b = n({ id: "b" });
  assert.deepEqual(upsert([a], b, "INSERT").map((x: AppNotification) => x.id), ["b", "a"]);
});
test("upsert ignores updates to rows not in the list", () => {
  const list = Array.from({ length: 100 }, () => n());
  const out = upsert(list, n({ id: "old", read_at: "2026-01-02T00:00:00Z" }), "UPDATE");
  assert.equal(out, list);
});
test("upsert caps at 100", () => {
  const list = Array.from({ length: 100 }, () => n());
  const out = upsert(list, n({ id: "new" }), "INSERT");
  assert.equal(out.length, 100);
  assert.equal(out[0].id, "new");
});

test("markProjectRead marks only that project; null marks nothing", () => {
  const list = [n({ project_id: "p1" }), n({ project_id: "p2" })];
  assert.deepEqual(markProjectRead(list, null), list);
  const out = markProjectRead(list, "p1");
  assert.notEqual(out[0].read_at, null);
  assert.equal(out[1].read_at, null);
});
