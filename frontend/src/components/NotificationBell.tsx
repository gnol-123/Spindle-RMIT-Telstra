"use client";

import { useRef, useState } from "react";
import { getPushKey } from "@/lib/api";
import { groupByProject } from "@/lib/notifications";
import { currentPushEndpoint, enablePush, isStandalone, pushSupported } from "@/lib/push";
import type { AppNotification } from "@/lib/types";

const STATUS: Record<AppNotification["status"], { word: string; cls: string }> = {
  complete: { word: "Finished", cls: "text-green" },
  failed: { word: "Failed", cls: "text-red-400" },
  awaiting_approval: { word: "Needs approval", cls: "text-amber" },
};

type Footer = "none" | "enable" | "home" | "blocked";

function ago(iso: string): string {
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

async function footerState(): Promise<Footer> {
  const key = await getPushKey().catch(() => null);
  if (key === null) return "none";
  if (!isStandalone()) return "home";
  if (!pushSupported() || (await currentPushEndpoint()) !== null) return "none";
  return Notification.permission === "denied" ? "blocked" : "enable";
}

export default function NotificationBell({
  items,
  dot,
  onOpenPanel,
  onOpenProject,
}: {
  items: AppNotification[];
  dot: boolean;
  onOpenPanel: () => void;
  onOpenProject: (projectId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  // unread at open time: markAllRead clears read_at but entries stay emphasized
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [footer, setFooter] = useState<Footer>("none");
  const [busy, setBusy] = useState(false);
  const opening = useRef(false);

  const toggle = () => {
    if (open) return setOpen(false);
    setFresh(new Set(items.filter((r) => r.read_at === null).map((r) => r.id)));
    setOpen(true);
    onOpenPanel();
    if (opening.current) return;
    opening.current = true;
    footerState()
      .then(setFooter)
      .catch(() => setFooter("none"))
      .finally(() => (opening.current = false));
  };

  const enable = async () => {
    setBusy(true);
    try {
      await enablePush();
    } catch {
      // stays offered; user can retry
    }
    setFooter(await footerState().catch(() => "none" as Footer));
    setBusy(false);
  };

  const groups = groupByProject(items);

  return (
    <div className="relative shrink-0">
      <button
        onClick={toggle}
        aria-label={dot ? "Notifications, unread" : "Notifications"}
        aria-expanded={open}
        className="relative grid place-items-center w-11 h-11 bg-transparent border border-white/[0.14] text-white/60 hover:text-text hover:border-white/30 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
          <path d="M10.3 21a1.9 1.9 0 0 0 3.4 0" />
        </svg>
        {dot && <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-red-500 anim-softpulse" />}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-2 z-50 w-[360px] max-w-[calc(100vw-24px)] max-h-[70vh] flex flex-col bg-panel border border-white/[0.13] rounded-lg shadow-[0_8px_24px_rgba(10,15,36,0.7)]">
            <div className="overflow-y-auto flex-1 min-h-0">
              {groups.length === 0 && <p className="px-4 py-6 text-center text-xs text-muted">No notifications yet.</p>}
              {groups.map((g) => (
                <section key={g.projectId}>
                  <h3 className="sticky top-0 bg-panel px-4 py-2 text-[10.5px] uppercase tracking-wider text-white/40 border-b border-white/[0.06] truncate">
                    {g.projectName}
                  </h3>
                  {g.items.map((r) => {
                    const st = STATUS[r.status];
                    const unread = fresh.has(r.id);
                    return (
                      <button
                        key={r.id}
                        onClick={() => {
                          setOpen(false);
                          onOpenProject(r.project_id);
                        }}
                        className="block w-full min-h-[44px] text-left px-4 py-2.5 border-b border-white/[0.04] hover:bg-white/[0.04] focus-visible:outline-none focus-visible:bg-white/[0.06]"
                      >
                        <div className="flex items-baseline gap-2 text-xs">
                          {unread && <span className="w-1.5 h-1.5 rounded-full bg-accent shrink-0 self-center"><span className="sr-only">unread</span></span>}
                          <span className={`truncate ${unread ? "font-semibold text-text" : "text-white/70"}`}>{r.node_name}</span>
                          <span className={`shrink-0 ${st.cls}`}>{st.word}</span>
                          <span className="ml-auto shrink-0 text-[10.5px] text-muted">{ago(r.created_at)}</span>
                        </div>
                        {r.nested && <div className="text-[10.5px] text-muted mt-0.5">via orchestrator</div>}
                        {r.excerpt && <div className="text-[11.5px] text-muted mt-0.5 truncate">{r.excerpt}</div>}
                      </button>
                    );
                  })}
                </section>
              ))}
            </div>
            {footer !== "none" && (
              <div className="border-t border-white/[0.09] px-4 py-2">
                {footer === "enable" && (
                  <button
                    onClick={enable}
                    disabled={busy}
                    className="w-full min-h-[44px] text-xs text-accent hover:text-text disabled:opacity-50"
                  >
                    Turn on iPad notifications
                  </button>
                )}
                {footer === "home" && <p className="py-2 text-[11.5px] text-muted">Add Spindle to your Home Screen to get push notifications.</p>}
                {footer === "blocked" && <p className="py-2 text-[11.5px] text-muted">Notifications are blocked. Turn them on in iPad Settings.</p>}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
