"use client";

import { useEffect, useRef, useState } from "react";
import { AgentNode, EnvironmentFileEntry, EnvironmentNode, ProjectNode } from "@/lib/types";
import { listEnvironmentFiles, readEnvironmentFile } from "@/lib/api";
import { mainReport } from "@/lib/sheet";
import { WORKSPACE_ROOT } from "@/lib/files";
import MarkdownMessage from "../MarkdownMessage";
import { AGENT_ICONS } from "../NodeCard";
import PreviewCard from "./PreviewCard";
import { SheetPreview } from "./SheetOverview";
import { Workspace } from "./WorkspaceWindow";

export default function AgentPage({
  projectId,
  agent,
  env,
  report,
  previews,
  nodes,
  working,
  terminal,
  initialPath,
  onNodeUpdated,
  onRemovePreview,
}: {
  projectId: string;
  agent: AgentNode;
  env: EnvironmentNode | null;
  // undefined: not known for this env, look it up
  report: EnvironmentFileEntry | null | undefined;
  previews: SheetPreview[];
  nodes: ProjectNode[];
  working: boolean;
  terminal: boolean;
  initialPath?: string | null;
  onNodeUpdated: (n: ProjectNode) => void;
  onRemovePreview: (envId: string, port: number) => void;
}) {
  const [content, setContent] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const envId = env?.id ?? null;

  // ponytail: looked up once per open, no live refresh; feed from the sheet's load() if it matters
  const [found, setFound] = useState<EnvironmentFileEntry | null | undefined>(undefined);
  const lookup = report === undefined && env?.status === "ready";
  useEffect(() => {
    if (!lookup || !envId) return;
    let cancelled = false;
    listEnvironmentFiles(projectId, envId, `${WORKSPACE_ROOT}/${agent.id}`).then(
      (r) => !cancelled && setFound(mainReport(r.entries)),
      () => !cancelled && setFound(null), // no folder yet
    );
    return () => {
      cancelled = true;
    };
  }, [lookup, projectId, envId, agent.id]);
  const rep = report !== undefined ? report : lookup ? found : null;

  // new report: drop the old one
  useEffect(() => {
    setContent(null);
    setFailed(false);
  }, [envId, rep?.path]);

  // re-read when the report moves
  useEffect(() => {
    if (!envId || !rep) return;
    let cancelled = false;
    readEnvironmentFile(projectId, envId, rep.path).then(
      (f) => {
        if (cancelled) return;
        setContent(f.content);
        setFailed(false);
      },
      () => !cancelled && setFailed(true),
    );
    return () => {
      cancelled = true;
    };
  }, [projectId, envId, rep?.path, rep?.modified, rep?.size]);

  // tree/editor scroll on their own; keep sheet drag out of them
  const isolate = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = isolate.current;
    if (!el) return;
    const stop = (e: TouchEvent) => e.stopPropagation();
    el.addEventListener("touchstart", stop, { passive: true });
    return () => el.removeEventListener("touchstart", stop);
  }, [envId]);

  const mine = previews.filter((p) => p.agent_node_id === agent.id);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-2.5 min-w-0">
        <span className="flex-none text-accent text-[16px]">{AGENT_ICONS[agent.agent_slug] ?? "◆"}</span>
        <h2 className="truncate text-[15px] font-semibold">{agent.name}</h2>
        <span className="flex-none flex items-center gap-1.5 text-[11px] text-white/45">
          <span className={`w-2 h-2 rounded-full ${working ? "bg-accent anim-softpulse" : "bg-white/30"}`} />
          {working ? "Working" : "Idle"}
        </span>
      </div>

      <section className="rounded-xl border border-white/[0.09] bg-panel2 px-4 py-3.5 text-[13px] text-white/80">
        {rep && content !== null ? (
          <>
            <div className="mb-2 text-[10.5px] text-white/35 font-mono truncate">{rep.name}</div>
            <MarkdownMessage content={content} />
          </>
        ) : (
          <span className="text-white/40">
            {rep === undefined ? "Loading report…" : !rep ? "Nothing written yet" : failed ? "Could not load the report" : "Loading report…"}
          </span>
        )}
      </section>

      {mine.map((p) => (
        <div key={`${p.envId}:${p.port}`} className="h-[min(56vh,520px)]">
          <PreviewCard
            // folder id titles read as the agent's name
            preview={p.title === agent.id ? { ...p, title: agent.name } : p}
            agentName={agent.name}
            size="lg"
            onRemove={p.published ? () => onRemovePreview(p.envId, p.port) : undefined}
          />
        </div>
      ))}

      {env ? (
        <div
          ref={isolate}
          onPointerDown={(e) => e.stopPropagation()}
          className="h-[520px] flex flex-col rounded-xl overflow-hidden border border-white/[0.09] bg-bg"
        >
          <Workspace
            embedded
            key={env.id}
            projectId={projectId}
            env={env}
            envs={[env]}
            initialPath={initialPath ?? `${WORKSPACE_ROOT}/${agent.id}`}
            nodes={nodes}
            terminal={terminal}
            onSwitchEnv={() => {}}
            onNodeUpdated={onNodeUpdated}
          />
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-white/[0.14] px-4 py-6 text-center text-[12px] text-white/40">
          No sandbox linked
        </div>
      )}
    </div>
  );
}
