"use client";

import { AgentNode, EnvironmentFileEntry, EnvironmentPreviewEntry } from "@/lib/types";
import { AGENT_ICONS } from "../NodeCard";
import PreviewCard from "./PreviewCard";

export type SheetPreview = EnvironmentPreviewEntry & { envId: string };
export type AgentInfo = { envId: string | null; files: number; report: EnvironmentFileEntry | null; excerpt: string | null };

export default function SheetOverview({
  layout,
  previews,
  agents,
  agentInfo,
  workingIds,
  onOpenAgent,
  onRemovePreview,
}: {
  layout: "row" | "grid";
  previews: SheetPreview[];
  agents: AgentNode[];
  agentInfo: Record<string, AgentInfo>;
  workingIds: string[];
  onOpenAgent: (id: string) => void;
  onRemovePreview: (envId: string, port: number) => void;
}) {
  const names: Record<string, string> = {};
  for (const a of agents) names[a.id] = a.name;
  const working = new Set(workingIds);
  const previewCards = previews.length
    ? previews.map((p) => (
        <PreviewCard
          key={`${p.envId}:${p.port}`}
          // agent folder ids as titles read as agent names
          preview={p.title && names[p.title] ? { ...p, title: names[p.title] } : p}
          agentName={p.agent_node_id ? names[p.agent_node_id] ?? null : null}
          size="lg"
          onRemove={p.published ? () => onRemovePreview(p.envId, p.port) : undefined}
        />
      ))
    : [<PreviewCard key="none" preview={null} agentName={null} size="lg" />];
  const cards = agents.map((a) => (
    <AgentCard
      key={a.id}
      agent={a}
      info={agentInfo[a.id]}
      working={working.has(a.id)}
      onOpen={() => onOpenAgent(a.id)}
      // row: grow to fill, scroll once below 220px each
      className={layout === "row" ? "flex-[1_0_220px] snap-start" : ""}
    />
  ));

  if (layout === "row") {
    return (
      <div className="h-full min-h-[200px] flex gap-3 overflow-x-auto overscroll-x-contain snap-x snap-mandatory pb-1">
        {previewCards.map((c) => (
          <div key={c.key} className="flex-none w-[46%] min-w-[340px] max-w-[640px] snap-start">
            {c}
          </div>
        ))}
        {cards.length ? cards : <Empty />}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-5">
      <div className={`grid gap-4 ${previewCards.length > 1 ? "lg:grid-cols-2" : ""}`}>
        {previewCards.map((c) => (
          <div key={c.key} className="h-[min(56vh,520px)]">
            {c}
          </div>
        ))}
      </div>
      {cards.length ? <div className="grid grid-cols-2 xl:grid-cols-3 gap-3">{cards}</div> : <Empty />}
    </div>
  );
}

function Empty() {
  return <div className="self-center text-[12px] text-white/40">No agents yet</div>;
}

function AgentCard({
  agent,
  info,
  working,
  onOpen,
  className,
}: {
  agent: AgentNode;
  info: AgentInfo | undefined;
  working: boolean;
  onOpen: () => void;
  className: string;
}) {
  const files = info?.files ?? 0;
  return (
    <button
      onClick={onOpen}
      className={`min-h-[132px] flex flex-col gap-2 p-3.5 rounded-xl border border-white/[0.09] bg-panel2 text-left [@media(hover:hover)_and_(pointer:fine)]:hover:border-white/20 ${className}`}
    >
      <div className="flex items-center gap-2 min-w-0">
        <span className="flex-none text-accent text-[14px]">{AGENT_ICONS[agent.agent_slug] ?? "◆"}</span>
        <span className="truncate text-[13px] font-semibold">{agent.name}</span>
        <span
          aria-label={working ? "Working" : "Idle"}
          className={`ml-auto flex-none w-2 h-2 rounded-full ${working ? "bg-accent anim-softpulse" : "bg-white/30"}`}
        />
      </div>
      <p className={`flex-1 text-[11.5px] leading-snug line-clamp-3 ${info?.excerpt ? "text-white/70" : "text-white/35"}`}>
        {info?.excerpt ?? "Nothing written yet"}
      </p>
      <span className="text-[10.5px] text-white/40">
        {files} file{files === 1 ? "" : "s"}
      </span>
    </button>
  );
}
