import test from "node:test";
import assert from "node:assert/strict";
// @ts-expect-error node needs the .ts extension; tsc does not allow it
import { toChange, changeMatters, coalesce, subscribeCanvas } from "./realtime.ts";

const P = "p1";
// payload stubs: only the fields toChange reads
const payload = (p: object) => p as Parameters<typeof toChange>[0];

test("toChange insert", () => assert.deepEqual(
  toChange(payload({ table: "nodes", eventType: "INSERT", new: { id: "n1", project_id: P }, old: {} })),
  { table: "nodes", event: "INSERT", id: "n1", projectId: P }));
test("toChange delete uses old, projectId null", () => assert.deepEqual(
  toChange(payload({ table: "edges", eventType: "DELETE", new: {}, old: { id: "e1" } })),
  { table: "edges", event: "DELETE", id: "e1", projectId: null }));
test("insert same project matters", () => assert.equal(changeMatters({ table: "nodes", event: "INSERT", id: "n9", projectId: P }, P, new Set()), true));
test("insert other project ignored", () => assert.equal(changeMatters({ table: "nodes", event: "INSERT", id: "n9", projectId: "p2" }, P, new Set()), false));
test("update same project matters", () => assert.equal(changeMatters({ table: "nodes", event: "UPDATE", id: "n1", projectId: P }, P, new Set(["n1"])), true));
test("delete known id matters", () => assert.equal(changeMatters({ table: "edges", event: "DELETE", id: "e1", projectId: null }, P, new Set(["e1"])), true));
test("delete unknown id ignored", () => assert.equal(changeMatters({ table: "nodes", event: "DELETE", id: "zz", projectId: null }, P, new Set(["n1"])), false));
test("coalesce: 5 calls in burst run once", async () => {
  let n = 0; const c = coalesce(() => n++, 50);
  for (let i = 0; i < 5; i++) c.call();
  await new Promise((r) => setTimeout(r, 120));
  assert.equal(n, 1);
});
test("coalesce: cancel drops pending", async () => {
  let n = 0; const c = coalesce(() => n++, 50);
  c.call(); c.cancel();
  await new Promise((r) => setTimeout(r, 120));
  assert.equal(n, 0);
});
test("subscribeCanvas without env: offline, no throw", () => {
  delete process.env.NEXT_PUBLIC_SUPABASE_URL;
  const live: boolean[] = [];
  const stop = subscribeCanvas(P, async () => null, () => {}, (l) => live.push(l));
  assert.deepEqual(live, [false]);
  stop();
});
test("subscribeCanvas: no onLive after cleanup", async () => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = "http://127.0.0.1:1";
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "k";
  const live: boolean[] = [];
  const stop = subscribeCanvas(P, async () => null, () => {}, (l) => live.push(l));
  stop();
  await new Promise((r) => setTimeout(r, 200));
  delete process.env.NEXT_PUBLIC_SUPABASE_URL;
  delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  assert.deepEqual(live, []);
});
