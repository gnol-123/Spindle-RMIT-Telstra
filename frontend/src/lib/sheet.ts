export type Snap = "closed" | "half" | "full";

export function snapOffsets(height: number, tab = 56): Record<Snap, number> {
  return { full: 0, half: Math.round(height / 2), closed: height - tab };
}

const ORDER: Snap[] = ["full", "half", "closed"];

// velocity in px/ms, positive = downward
export function pickSnap(y: number, velocity: number, offsets: Record<Snap, number>): Snap {
  let i = 0;
  for (let k = 1; k < ORDER.length; k++) {
    if (Math.abs(offsets[ORDER[k]] - y) < Math.abs(offsets[ORDER[i]] - y)) i = k;
  }
  if (Math.abs(velocity) > 0.5) i += velocity > 0 ? 1 : -1;
  return ORDER[Math.min(ORDER.length - 1, Math.max(0, i))];
}

export function rubberband(y: number, min: number, max: number): number {
  if (y < min) return min + (y - min) * 0.35;
  if (y > max) return max + (y - max) * 0.35;
  return y;
}

// body drag: pull down from the top only
export function shouldDragSheet(scrollTop: number, dy: number): boolean {
  return scrollTop <= 0 && dy > 0;
}

// once past slop: vertical pull-down claims, sideways never does; undefined = undecided
export function bodyClaim(scrollTop: number, dx: number, dy: number, slop = 8): boolean | undefined {
  if (Math.max(Math.abs(dx), Math.abs(dy)) < slop) return undefined;
  return Math.abs(dy) > Math.abs(dx) && shouldDragSheet(scrollTop, dy);
}

// Kahn's over context edges, ties by name, cycle members appended by name.
// ponytail: ready list re-sorted per push batch; fine for small n, use a heap if n grows.
export function orderAgents<T extends { id: string; name: string }>(
  agents: T[],
  edges: { source_node_id: string; target_node_id: string; kind: string }[],
): T[] {
  const byName = (a: T, b: T) => a.name.localeCompare(b.name);
  const sorted = [...agents].sort(byName);
  const byId = new Map(sorted.map((a) => [a.id, a]));
  const indeg = new Map(sorted.map((a) => [a.id, 0]));
  const out = new Map<string, string[]>();
  for (const e of edges) {
    if (e.kind !== "context" || !byId.has(e.source_node_id) || !byId.has(e.target_node_id)) continue;
    indeg.set(e.target_node_id, indeg.get(e.target_node_id)! + 1);
    const l = out.get(e.source_node_id);
    if (l) l.push(e.target_node_id);
    else out.set(e.source_node_id, [e.target_node_id]);
  }
  const ready = sorted.filter((a) => indeg.get(a.id) === 0);
  const done = new Set<string>();
  const res: T[] = [];
  while (ready.length) {
    const a = ready.shift()!;
    res.push(a);
    done.add(a.id);
    let added = false;
    for (const t of out.get(a.id) ?? []) {
      const d = indeg.get(t)! - 1;
      indeg.set(t, d);
      if (d === 0) {
        ready.push(byId.get(t)!);
        added = true;
      }
    }
    if (added) ready.sort(byName);
  }
  for (const a of sorted) if (!done.has(a.id)) res.push(a);
  return res;
}

export function mainReport<E extends { name: string; type: string; modified?: string | null }>(entries: E[]): E | null {
  let best: E | null = null;
  for (const e of entries) {
    if (e.type !== "file" || !e.name.toLowerCase().endsWith(".md")) continue;
    if (!best || (e.modified ?? "") > (best.modified ?? "")) best = e;
  }
  return best;
}

type PreviewLike = {
  published: boolean;
  live: boolean;
  created_at: string | null;
  title: string | null;
  agent_node_id: string | null;
};

// Live published previews, plus live folder servers titled with an agent id
// (attributed to that agent). `first` agents lead, then newest.
export function visiblePreviews<P extends PreviewLike>(
  list: P[],
  agentIds: ReadonlySet<string> = new Set(),
  first: ReadonlySet<string> = new Set()
): P[] {
  const rank = (p: P) => (p.agent_node_id && first.has(p.agent_node_id) ? 0 : 1);
  return list
    .filter((p) => p.live && (p.published || (p.title !== null && agentIds.has(p.title))))
    .map((p) => (p.agent_node_id || p.title === null || !agentIds.has(p.title) ? p : { ...p, agent_node_id: p.title }))
    .sort((a, b) => rank(a) - rank(b) || (b.created_at ?? "").localeCompare(a.created_at ?? ""));
}

// first non-heading, non-empty line, cut to max chars
export function reportExcerpt(md: string, max = 140): string | null {
  for (const raw of md.split("\n")) {
    const l = raw.trim();
    if (l && !l.startsWith("#")) return l.length > max ? l.slice(0, max - 1) + "…" : l;
  }
  return null;
}
