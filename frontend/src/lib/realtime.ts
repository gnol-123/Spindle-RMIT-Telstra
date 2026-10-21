import { RealtimeClient, type RealtimePostgresChangesPayload } from "@supabase/realtime-js";

export type CanvasChange = {
  table: "nodes" | "edges";
  event: "INSERT" | "UPDATE" | "DELETE";
  id: string;
  projectId: string | null;
};

export const CANVAS_DEBOUNCE_MS = 200;

type Row = { id: string; project_id?: string };

// DELETE carries only the pk in old, so no project id
export function toChange(p: RealtimePostgresChangesPayload<Row>): CanvasChange {
  const event = p.eventType as CanvasChange["event"];
  const table = p.table as CanvasChange["table"];
  if (event === "DELETE") return { table, event, id: (p.old as Row).id, projectId: null };
  const row = p.new as Row;
  return { table, event, id: row.id, projectId: row.project_id ?? null };
}

export function changeMatters(c: CanvasChange, projectId: string, knownIds: Set<string>): boolean {
  return c.event === "DELETE" ? knownIds.has(c.id) : c.projectId === projectId;
}

// trailing debounce
export function coalesce(fn: () => void, ms: number): { call(): void; cancel(): void } {
  let t: ReturnType<typeof setTimeout> | undefined;
  return {
    call() {
      clearTimeout(t);
      t = setTimeout(fn, ms);
    },
    cancel() {
      clearTimeout(t);
      t = undefined;
    },
  };
}

export function subscribeCanvas(
  projectId: string,
  getToken: () => Promise<string | null>,
  onChange: (c: CanvasChange) => void,
  onLive: (live: boolean) => void,
): () => void {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) {
    console.warn("realtime: missing Supabase env, canvas stays offline");
    onLive(false);
    return () => {};
  }

  const client = new RealtimeClient(url.replace(/^http/, "ws") + "/realtime/v1", {
    params: { apikey: key },
    accessToken: getToken,
  });
  const channel = client.channel(`canvas:${projectId}`, {
    config: { postgres_changes_options: { wait: true } },
  });

  // cleanup closes the channel, which still emits CLOSED; drop it
  let stopped = false;
  let warned = false;
  const handle = (p: RealtimePostgresChangesPayload<Row>) => {
    if (!stopped) onChange(toChange(p));
  };
  for (const table of ["nodes", "edges"]) {
    const filter = `project_id=eq.${projectId}`;
    channel.on("postgres_changes", { event: "INSERT", schema: "public", table, filter }, handle);
    channel.on("postgres_changes", { event: "UPDATE", schema: "public", table, filter }, handle);
    // DELETE can't be filtered by project
    channel.on("postgres_changes", { event: "DELETE", schema: "public", table }, handle);
  }

  channel.subscribe((status, err) => {
    if (stopped) return;
    if (status === "SUBSCRIBED") onLive(true);
    else if (status === "CHANNEL_ERROR" || status === "TIMED_OUT" || status === "CLOSED") {
      if (status === "CHANNEL_ERROR" && !warned) {
        warned = true;
        console.warn("realtime:", err);
      }
      onLive(false);
    }
  });

  return () => {
    stopped = true;
    client.removeAllChannels().catch(() => {});
    client.disconnect();
  };
}
