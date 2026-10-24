import { useCallback, useEffect, useRef, useState } from "react";
import { authToken, listNotifications, markNotificationsRead } from "./api";
import { markProjectRead, unreadElsewhere, upsert } from "./notifications";
import { subscribeNotifications } from "./realtime";
import type { AppNotification } from "./types";

const markLocal = (list: AppNotification[], projectId: string | null): AppNotification[] => {
  const now = new Date().toISOString();
  return list.map((r) => (r.read_at === null && (projectId === null || r.project_id === projectId) ? { ...r, read_at: now } : r));
};

export function useNotifications(userId: string | null, activeProjectId: string | null) {
  const [items, setItems] = useState<AppNotification[]>([]);
  const activeRef = useRef(activeProjectId);
  activeRef.current = activeProjectId;

  useEffect(() => {
    if (!userId) {
      setItems([]);
      return;
    }
    let stopped = false;
    const load = () =>
      listNotifications(100)
        .then((rows) => {
          if (stopped) return;
          const active = activeRef.current;
          // arrived while offline: read on the server too
          if (active && rows.some((r) => r.read_at === null && r.project_id === active)) {
            markNotificationsRead(active).catch(() => {});
          }
          setItems(markProjectRead(rows, active));
        })
        .catch(() => {});
    void load();

    const onRow = (row: AppNotification, event: "INSERT" | "UPDATE") => {
      setItems((prev) => upsert(prev, row, event));
      // already looking at that project: read on arrival
      if (row.read_at === null && row.project_id === activeRef.current) {
        markNotificationsRead(row.project_id).catch(() => {});
        setItems((prev) => markLocal(prev, row.project_id));
      }
    };
    let wasLive = false;
    const onLive = (live: boolean) => {
      if (live && wasLive === false) void load();
      wasLive = live;
    };
    const stop = subscribeNotifications(userId, () => authToken().catch(() => null), onRow, onLive);
    return () => {
      stopped = true;
      stop();
    };
  }, [userId]);

  // opening a project reads its notifications
  useEffect(() => {
    if (!userId || !activeProjectId) return;
    markNotificationsRead(activeProjectId).catch(() => {});
    setItems((prev) => markLocal(prev, activeProjectId));
  }, [userId, activeProjectId]);

  const markAllRead = useCallback(() => {
    markNotificationsRead(null).catch(() => {});
    setItems((prev) => markLocal(prev, null));
  }, []);

  return { items, dot: unreadElsewhere(items, activeProjectId), markAllRead };
}
