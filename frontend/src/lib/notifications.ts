import type { AppNotification } from "./types";

export const NOTIFICATION_CAP = 100;

export type NotificationGroup = { projectId: string; projectName: string; items: AppNotification[] };

// newest first within a group; groups ordered by their newest item
export function groupByProject(list: AppNotification[]): NotificationGroup[] {
  const sorted = [...list].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  const groups = new Map<string, NotificationGroup>();
  for (const row of sorted) {
    const g = groups.get(row.project_id);
    if (g) g.items.push(row);
    else groups.set(row.project_id, { projectId: row.project_id, projectName: row.project_name, items: [row] });
  }
  return [...groups.values()];
}

export function unreadElsewhere(list: AppNotification[], activeProjectId: string | null): boolean {
  return list.some((r) => r.read_at === null && r.project_id !== activeProjectId);
}

// replace by id (read_at from another device); only inserts prepend
export function upsert(list: AppNotification[], row: AppNotification, event: "INSERT" | "UPDATE"): AppNotification[] {
  const i = list.findIndex((r) => r.id === row.id);
  if (i >= 0) return list.map((r, j) => (j === i ? row : r));
  // an update to an older row we never loaded
  if (event === "UPDATE") return list;
  return [row, ...list].slice(0, NOTIFICATION_CAP);
}

// fetched snapshot wins; live rows that landed mid-fetch (newer than it) survive
export function mergeSnapshot(prev: AppNotification[], snap: AppNotification[]): AppNotification[] {
  const ids = new Set(snap.map((r) => r.id));
  const newest = Math.max(-Infinity, ...snap.map((r) => Date.parse(r.created_at)));
  const newer = prev.filter((r) => !ids.has(r.id) && Date.parse(r.created_at) > newest);
  return [...newer, ...snap].slice(0, NOTIFICATION_CAP);
}

// local read mark for one project; null (no project open) marks nothing
export function markProjectRead(list: AppNotification[], projectId: string | null): AppNotification[] {
  if (projectId === null) return list;
  const now = new Date().toISOString();
  return list.map((r) => (r.read_at === null && r.project_id === projectId ? { ...r, read_at: now } : r));
}
