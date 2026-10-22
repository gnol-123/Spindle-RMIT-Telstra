// Temp id prefix for an agent card shown before its POST returns.
export const TEMP_PREFIX = "pending:";
// Unlock regardless after this long, so a failed preset can't lock a card forever.
export const PROVISION_TIMEOUT_MS = 20_000;
// Canvas sync cadence while an agent provisions.
export const PROVISION_POLL_MS = 600;

interface N {
  id: string;
  kind: string;
  status?: string;
}
interface E {
  kind: string;
  source_node_id: string;
  target_node_id: string;
}

// Agent has its default tools attached and none still pending.
export function agentProvisioned(agentId: string, nodes: N[], edges: E[], expected: number): boolean {
  if (expected === 0) return true;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  let count = 0;
  for (const e of edges) {
    if (e.kind !== "tool" || e.target_node_id !== agentId) continue;
    const t = byId.get(e.source_node_id);
    if (!t || t.kind !== "tool") continue;
    if (t.status === "pending") return false;
    count++;
  }
  return count >= expected;
}
