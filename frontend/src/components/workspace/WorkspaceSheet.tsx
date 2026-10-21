"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Edge, ProjectNode, isAgentNode, isEnvironmentNode } from "@/lib/types";
import {
  ApiError,
  deleteEnvironmentPreview,
  listEnvironmentPreviews,
  listManyEnvironmentFiles,
  readEnvironmentFile,
} from "@/lib/api";
import { WORKSPACE_ROOT } from "@/lib/files";
import { Snap, mainReport, orderAgents, reportExcerpt, visiblePreviews } from "@/lib/sheet";
import { useSheetDrag } from "./useSheetDrag";
import SheetOverview, { AgentInfo, SheetPreview } from "./SheetOverview";
import AgentPage from "./AgentPage";
import { Workspace } from "./WorkspaceWindow";
import { AGENT_ICONS } from "../NodeCard";

export type SheetOpenRequest = { envId: string; path: string | null; n: number };

// agent: envId from the request (agents can link several envs), path = deeper folder to reveal
type Page =
  | { kind: "overview" }
  | { kind: "agent"; id: string; envId?: string; path?: string }
  | { kind: "files"; envId: string };

const previewKey = (envId: string, port: number) => `${envId}:${port}`;

// agent folder servers count as that agent's; coding agent's previews lead
function pickPreviews(list: SheetPreview[], nodes: ProjectNode[]): SheetPreview[] {
  const agents = nodes.filter(isAgentNode);
  return visiblePreviews(
    list,
    new Set(agents.map((a) => a.id)),
    new Set(agents.filter((a) => a.agent_slug === "coding").map((a) => a.id)),
  );
}

// agent -> linked env, else scratch
function agentEnvs(nodes: ProjectNode[], edges: Edge[]): Map<string, string | null> {
  const scratch = nodes.find((n) => isEnvironmentNode(n) && n.role === "scratch")?.id ?? null;
  const envOf = new Map<string, string>();
  for (const e of edges) if (e.kind === "environment") envOf.set(e.target_node_id, e.source_node_id);
  const m = new Map<string, string | null>();
  for (const n of nodes) if (isAgentNode(n)) m.set(n.id, envOf.get(n.id) ?? scratch);
  return m;
}

export default function WorkspaceSheet({
  projectId,
  nodes,
  edges,
  workingIds,
  openRequest,
  onNodeUpdated,
}: {
  projectId: string;
  nodes: ProjectNode[];
  edges: Edge[];
  workingIds: string[];
  openRequest: SheetOpenRequest | null;
  onNodeUpdated: (n: ProjectNode) => void;
}) {
  const [snap, setSnap] = useState<Snap>("closed");
  const [page, setPage] = useState<Page>({ kind: "overview" });
  const [terminal, setTerminal] = useState(false);
  const [filesEnvId, setFilesEnvId] = useState<string | null>(null); // last env picked on Files
  const sheetRef = useRef<HTMLDivElement | null>(null);
  const { handleProps, bodyProps } = useSheetDrag(sheetRef, snap, setSnap);

  const [previews, setPreviews] = useState<SheetPreview[]>([]);
  const [agentInfo, setAgentInfo] = useState<Record<string, AgentInfo>>({});
  const [removeErr, setRemoveErr] = useState<string | null>(null);
  const agents = useMemo(() => orderAgents(nodes.filter(isAgentNode), edges), [nodes, edges]);
  const envs = useMemo(() => nodes.filter(isEnvironmentNode), [nodes]);
  const envOfAgent = useMemo(() => agentEnvs(nodes, edges), [nodes, edges]);

  const live = useRef({ projectId, nodes, edges });
  live.current = { projectId, nodes, edges };
  const req = useRef(0);
  const hidden = useRef(new Set<string>()); // removes in flight
  const excerpts = useRef(new Map<string, { key: string; excerpt: string | null }>());

  async function load() {
    const n = ++req.current;
    const { projectId, nodes, edges } = live.current;
    const envs = nodes.filter(isEnvironmentNode);
    const ready = envs.filter((e) => e.status === "ready").map((e) => e.id);
    const readySet = new Set(ready);
    const envOf = agentEnvs(nodes, edges);

    const info: Record<string, AgentInfo> = {};
    const folders = new Map<string, string[]>(); // env -> agent ids
    for (const a of nodes) {
      if (!isAgentNode(a)) continue;
      const envId = envOf.get(a.id) ?? null;
      info[a.id] = { envId, files: 0, report: null, excerpt: null };
      if (!envId || !readySet.has(envId)) continue;
      const l = folders.get(envId);
      if (l) l.push(a.id);
      else folders.set(envId, [a.id]);
    }
    const byEnv = [...folders];

    // null = request failed, keep what we had
    const [previewLists, listings] = await Promise.all([
      Promise.all(
        ready.map((id) =>
          listEnvironmentPreviews(projectId, id).then(
            (r) => r.previews.map((p) => ({ ...p, envId: id })),
            () => null,
          ),
        ),
      ),
      Promise.all(
        byEnv.map(([id, ids]) =>
          listManyEnvironmentFiles(projectId, id, ids.map((a) => `${WORKSPACE_ROOT}/${a}`)).then(
            (r) => r.listings,
            () => null,
          ),
        ),
      ),
    ]);
    if (n !== req.current) return;

    const failed = new Set<string>();
    listings.forEach((ls, i) => {
      if (!ls) {
        for (const a of byEnv[i][1]) failed.add(a);
        return;
      }
      // listings follow request order
      ls.forEach((l, j) => {
        const a = info[byEnv[i][1][j]];
        if (!a || !l.entries) return; // missing folder: 0 files
        a.files = l.entries.filter((e) => e.type === "file").length;
        a.report = mainReport(l.entries);
      });
    });

    // re-read only when the report changed
    await Promise.all(
      Object.entries(info).map(async ([id, a]) => {
        if (!a.report || !a.envId) return;
        const key = `${a.envId}:${a.report.path}:${a.report.modified ?? ""}:${a.report.size}`;
        const hit = excerpts.current.get(id);
        if (hit?.key === key) {
          a.excerpt = hit.excerpt;
          return;
        }
        try {
          a.excerpt = reportExcerpt((await readEnvironmentFile(projectId, a.envId, a.report.path)).content);
          excerpts.current.set(id, { key, excerpt: a.excerpt });
        } catch {
          a.excerpt = hit?.excerpt ?? null;
        }
      }),
    );
    if (n !== req.current) return;

    setAgentInfo((prev) => {
      for (const id of failed) if (prev[id]) info[id] = prev[id];
      return info;
    });
    setPreviews((prev) => {
      const all = previewLists.flatMap((l, i) => l ?? prev.filter((p) => p.envId === ready[i]));
      return pickPreviews(all, nodes).filter((p) => !hidden.current.has(previewKey(p.envId, p.port)));
    });
  }

  async function removePreview(envId: string, port: number) {
    const k = previewKey(envId, port);
    const gone = previews.find((p) => previewKey(p.envId, p.port) === k);
    if (!gone) return;
    hidden.current.add(k);
    setRemoveErr(null);
    setPreviews((ps) => ps.filter((p) => previewKey(p.envId, p.port) !== k));
    try {
      await deleteEnvironmentPreview(projectId, envId, port);
      hidden.current.delete(k);
      load(); // supersedes loads started before the delete
    } catch (e) {
      hidden.current.delete(k);
      setPreviews((ps) => (ps.some((p) => previewKey(p.envId, p.port) === k) ? ps : pickPreviews([...ps, gone], live.current.nodes)));
      setRemoveErr(e instanceof ApiError ? e.message : "Could not remove this preview");
    }
  }

  function go(p: Page) {
    setPage(p);
    setTerminal(false);
  }

  function openAgent(id: string) {
    go({ kind: "agent", id });
    setSnap("full");
  }

  // mount, and when a sandbox comes up (nodes arrive after mount)
  const readyKey = nodes
    .filter((n) => isEnvironmentNode(n) && n.status === "ready")
    .map((n) => n.id)
    .join(",");
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readyKey]);

  const opened = useRef(false);
  useEffect(() => {
    if (snap === "closed" || opened.current) return;
    opened.current = true;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snap]);

  // an agent finished
  const prevWorking = useRef(workingIds);
  const workingKey = workingIds.join(",");
  useEffect(() => {
    const now = new Set(workingIds);
    if (prevWorking.current.some((id) => !now.has(id))) load();
    prevWorking.current = workingIds;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workingKey]);

  useEffect(() => {
    if (!openRequest) return;
    setSnap("full");
    const { envId, path } = openRequest;
    if (!envs.some((e) => e.id === envId)) return go({ kind: "overview" }); // stale
    const id = path?.startsWith(`${WORKSPACE_ROOT}/`) ? path.slice(WORKSPACE_ROOT.length + 1).split("/")[0] : null;
    if (id && agents.some((a) => a.id === id)) {
      const root = `${WORKSPACE_ROOT}/${id}`;
      go({ kind: "agent", id, envId, path: path !== root ? path! : undefined });
    } else {
      go({ kind: "files", envId });
      setFilesEnvId(envId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openRequest?.n]);

  // Esc closes, unless typing or in the terminal
  useEffect(() => {
    if (snap === "closed") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const el = document.activeElement as HTMLElement | null;
      if (el?.closest(".terminal-host") || el?.tagName === "TEXTAREA" || el?.tagName === "INPUT") return;
      setSnap("closed");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [snap]);

  const half = snap !== "full";
  const previewCount = previews.length;
  const defaultEnv = envs.find((e) => e.role !== "scratch") ?? envs[0] ?? null;
  const agent = page.kind === "agent" ? agents.find((a) => a.id === page.id) ?? null : null;
  const agentEnv =
    (page.kind === "agent" && envs.find((e) => e.id === page.envId)) ||
    envs.find((e) => e.id === (agent ? envOfAgent.get(agent.id) : null)) ||
    null;
  const filesEnv = page.kind === "files" ? envs.find((e) => e.id === page.envId) ?? defaultEnv : null;
  // gone agent falls back to the overview
  const shown = half ? "overview" : page.kind === "agent" && !agent ? "overview" : page.kind;
  const termEnv = shown === "agent" ? agentEnv : shown === "files" ? filesEnv : null;
  const termOk = termEnv?.status === "ready";
  useEffect(() => {
    if (!termOk) setTerminal(false);
  }, [termOk]);
  const working = new Set(workingIds);

  const navItem = (on: boolean) =>
    `w-full min-h-11 flex items-center gap-2.5 px-3 rounded-lg text-left text-[12.5px] ${
      on ? "bg-panel2 text-text" : "text-white/60 [@media(hover:hover)_and_(pointer:fine)]:hover:text-text"
    }`;

  const errBanner = removeErr && (
    <button
      onClick={() => setRemoveErr(null)}
      className="flex-none min-h-11 text-left px-3 rounded-lg text-[11.5px] text-red-300 bg-red-500/[0.07] border border-red-400/20"
    >
      {removeErr}
    </button>
  );

  return (
    // full covers the Inspector too; height stays, so snap offsets hold
    <div className={`absolute inset-y-0 left-0 ${half ? "right-[var(--inspector-w)]" : "right-0"} z-[30] overflow-hidden pointer-events-none`}>
      <div
        ref={sheetRef}
        className="absolute inset-x-0 top-0 h-full flex flex-col pointer-events-auto bg-panel rounded-t-[16px] border-t border-white/[0.09] shadow-[0_-12px_32px_rgba(0,0,0,.45)] will-change-transform"
      >
        <div className="flex-none relative">
          <button
            {...handleProps}
            // keyboard only; pointer taps go through the hook
            onClick={(e) => e.detail === 0 && setSnap(snap === "closed" ? "half" : "closed")}
            aria-label={snap === "closed" ? "Open workspace" : "Close workspace"}
            aria-expanded={snap !== "closed"}
            className="h-14 w-full flex flex-col items-center justify-center gap-1.5 touch-none cursor-grab active:cursor-grabbing"
          >
            <span className="w-9 h-1 rounded-full bg-white/25" />
            <span className="flex items-center gap-2 text-[12.5px] font-semibold">
              Workspace
              <span className="text-[11px] font-normal text-white/[0.45]">
                {previewCount} preview{previewCount === 1 ? "" : "s"}
              </span>
            </span>
          </button>
          {!half && (
            <div className="absolute right-3 inset-y-0 flex items-center gap-1">
              <button
                onClick={() => setTerminal((t) => !t)}
                disabled={!termOk}
                aria-pressed={terminal}
                className={`h-11 px-3 rounded-lg text-[12px] border disabled:opacity-40 ${
                  terminal ? "border-accent/45 text-accent bg-accent/10" : "border-white/[0.14] text-white/60"
                }`}
              >
                Terminal
              </button>
              <button
                onClick={() => setSnap("closed")}
                aria-label="Close workspace"
                className="w-11 h-11 grid place-items-center rounded-lg text-white/55 text-[15px] [@media(hover:hover)_and_(pointer:fine)]:hover:text-text"
              >
                ×
              </button>
            </div>
          )}
        </div>

        {/* half: only the sheet's top half is on screen */}
        <div
          inert={snap === "closed"}
          style={half ? { maxHeight: "calc(50% - 56px)" } : undefined}
          className={`flex-1 min-h-0 flex ${half ? "" : "border-t border-white/[0.09]"}`}
        >
          {!half && (
            <nav aria-label="Workspace pages" className="flex-none w-[232px] overflow-y-auto overscroll-contain border-r border-white/[0.09] p-2 flex flex-col gap-0.5">
              <button onClick={() => go({ kind: "overview" })} className={navItem(shown === "overview")}>
                Overview
              </button>
              {agents.map((a) => (
                <button key={a.id} onClick={() => go({ kind: "agent", id: a.id })} className={navItem(shown === "agent" && agent?.id === a.id)}>
                  <span className="flex-none text-accent text-[13px]">{AGENT_ICONS[a.agent_slug] ?? "◆"}</span>
                  <span className="truncate">{a.name}</span>
                  {working.has(a.id) && <span aria-label="Working" className="ml-auto flex-none w-2 h-2 rounded-full bg-accent anim-softpulse" />}
                </button>
              ))}
              <div className="my-1.5 border-t border-white/[0.09]" />
              <button
                onClick={() => defaultEnv && go({ kind: "files", envId: filesEnvId ?? defaultEnv.id })}
                disabled={!defaultEnv}
                className={`${navItem(shown === "files")} disabled:opacity-40`}
              >
                Files
              </button>
            </nav>
          )}
          {shown === "files" ? (
            <div className="flex-1 min-w-0 min-h-0 flex flex-col">
              {filesEnv ? (
                <Workspace
                  embedded
                  key={filesEnv.id}
                  projectId={projectId}
                  env={filesEnv}
                  envs={envs}
                  initialPath={null}
                  nodes={nodes}
                  terminal={terminal}
                  onSwitchEnv={(id) => {
                    setPage({ kind: "files", envId: id });
                    setFilesEnvId(id);
                  }}
                  onNodeUpdated={onNodeUpdated}
                />
              ) : (
                <div className="m-auto text-[12px] text-white/40">No sandbox yet</div>
              )}
            </div>
          ) : (
            <div {...bodyProps} className="flex-1 min-w-0 min-h-0 overflow-y-auto overscroll-contain touch-pan-x touch-pan-y px-5 py-4">
              {shown === "agent" && agent ? (
                <div className="flex flex-col gap-3">
                  {errBanner}
                  <AgentPage
                    key={agent.id}
                    projectId={projectId}
                    agent={agent}
                    env={agentEnv}
                    // agentInfo covers the default env only
                    report={agentEnv && agentInfo[agent.id]?.envId === agentEnv.id ? agentInfo[agent.id].report : undefined}
                    previews={previews}
                    nodes={nodes}
                    working={working.has(agent.id)}
                    terminal={terminal}
                    initialPath={page.kind === "agent" ? page.path : null}
                    onNodeUpdated={onNodeUpdated}
                    onRemovePreview={removePreview}
                  />
                </div>
              ) : (
                <div className={`flex flex-col gap-3 ${half ? "h-full" : ""}`}>
                  {errBanner}
                  <div className={half ? "flex-1 min-h-0" : ""}>
                    <SheetOverview
                      layout={half ? "row" : "grid"}
                      previews={previews}
                      agents={agents}
                      agentInfo={agentInfo}
                      workingIds={workingIds}
                      onOpenAgent={openAgent}
                      onRemovePreview={removePreview}
                    />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
