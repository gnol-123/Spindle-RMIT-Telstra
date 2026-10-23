import test from "node:test";
import assert from "node:assert/strict";
// @ts-expect-error node needs the .ts extension; tsc does not allow it
import { snapOffsets, pickSnap, rubberband, shouldDragSheet, orderAgents, mainReport, visiblePreviews, reportExcerpt, bodyClaim } from "./sheet.ts";

const ag = (id: string) => ({ id, name: id });
const ctx = (s: string, t: string, kind = "context") => ({ source_node_id: s, target_node_id: t, kind });

test("snapOffsets", () => {
  assert.deepEqual(snapOffsets(800), { full: 0, half: 400, closed: 744 });
});

test("pickSnap", () => {
  const o = snapOffsets(800);
  assert.equal(pickSnap(380, 0, o), "half");
  assert.equal(pickSnap(380, 0.8, o), "closed");
  assert.equal(pickSnap(380, -0.8, o), "full");
  assert.equal(pickSnap(10, -2, o), "full");
});

test("rubberband", () => {
  assert.equal(rubberband(-100, 0, 744), -35);
  assert.equal(rubberband(300, 0, 744), 300);
});

test("orderAgents", () => {
  const ids = (l: { id: string }[]) => l.map((a) => a.id);
  assert.deepEqual(ids(orderAgents([ag("C"), ag("B"), ag("A")], [ctx("A", "B"), ctx("B", "C")])), ["A", "B", "C"]);
  assert.deepEqual(ids(orderAgents([ag("B"), ag("A")], [ctx("B", "A", "other")])), ["A", "B"]);
  assert.deepEqual(ids(orderAgents([ag("A"), ag("B"), ag("D")], [ctx("A", "B"), ctx("B", "A")])), ["D", "A", "B"]);
});

test("mainReport", () => {
  const e = [
    { name: "brief.md", type: "file", modified: "2026-01-01T00:00:00Z" },
    { name: "notes.MD", type: "file", modified: "2026-02-01T00:00:00Z" },
    { name: "x.md", type: "dir", modified: "2026-03-01T00:00:00Z" },
    { name: "y.txt", type: "file", modified: "2026-04-01T00:00:00Z" },
  ];
  assert.equal(mainReport(e)?.name, "notes.MD");
  assert.equal(mainReport([]), null);
});

test("visiblePreviews", () => {
  const p = (id: string, published: boolean, live: boolean, created_at: string | null, title: string | null = id, agent_node_id: string | null = null) =>
    ({ id, published, live, created_at, title, agent_node_id });
  const out = visiblePreviews([
    p("old", true, true, "2026-01-01"),
    p("unpub", false, true, "2026-05-01"),
    p("dead", true, false, "2026-05-01"),
    p("new", true, true, "2026-03-01"),
  ]);
  assert.deepEqual(out.map((x) => x.id), ["new", "old"]);

  // Ledger Lite: coding agent's folder server is unpublished, deck is published and newer
  const agents = new Set(["coder", "scrut"]);
  const coding = new Set(["coder"]);
  const ledger = visiblePreviews(
    [
      p("deck", true, true, "2026-10-21T04:32", "Ledger deck", "scrut"),
      p("app", false, true, null, "coder"),
      p("stray", false, true, null, null),
      p("deadFolder", false, false, null, "coder"),
    ],
    agents,
    coding
  );
  assert.deepEqual(ledger.map((x) => x.id), ["app", "deck"]);
  assert.equal(ledger[0].agent_node_id, "coder");
  // idempotent on its own output
  assert.deepEqual(visiblePreviews(ledger, agents, coding).map((x) => x.id), ["app", "deck"]);

  // leftover servers from re-runs: published wins, else one folder server per agent
  const dupes = visiblePreviews(
    [
      p("probe", true, true, "2026-10-20", "Probe page", "coder"),
      p("old1", false, true, null, "coder"),
      p("old2", false, true, null, "coder"),
      p("s1", false, true, null, "scrut"),
      p("s2", false, true, null, "scrut"),
    ],
    agents,
    coding
  );
  assert.deepEqual(dupes.map((x) => x.id), ["probe", "s1"]);
});

test("shouldDragSheet", () => {
  assert.equal(shouldDragSheet(0, 12), true);
  assert.equal(shouldDragSheet(40, 12), false);
  assert.equal(shouldDragSheet(0, -12), false);
});

test("reportExcerpt", () => {
  assert.equal(reportExcerpt("# Title\n\n## Sub\n  First line  \nSecond"), "First line");
  assert.equal(reportExcerpt("# only\n\n"), null);
  assert.equal(reportExcerpt("x".repeat(200))?.length, 140);
});

test("bodyClaim", () => {
  assert.equal(bodyClaim(0, 3, 5), undefined);
  assert.equal(bodyClaim(0, 2, 10), true);
  assert.equal(bodyClaim(0, 30, 9), false); // sideways swipe drifting down
  assert.equal(bodyClaim(50, 0, 10), false);
  assert.equal(bodyClaim(0, 0, -10), false);
});
