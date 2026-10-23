"use client";

import { useEffect, useRef, useState } from "react";
import { EnvironmentPreviewEntry } from "@/lib/types";

// Width previews render at, scaled down to fit the card.
const VIEW_W = 1280;

const frameSrc = (p: EnvironmentPreviewEntry) =>
  `${p.url.replace(/\/$/, "")}${p.path.startsWith("/") ? p.path : `/${p.path}`}`;

export default function PreviewCard({
  preview,
  agentName,
  size,
  onRemove,
}: {
  preview: EnvironmentPreviewEntry | null;
  agentName: string | null;
  size: "lg" | "sm";
  // unset: nothing to remove (unpublished folder server)
  onRemove?: () => void;
}) {
  const box = useRef<HTMLDivElement | null>(null);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setScale(Math.min(1, e.contentRect.width / VIEW_W)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [preview?.url]);

  if (!preview) {
    return (
      <div className="h-full min-h-[160px] grid place-items-center rounded-xl border border-dashed border-white/[0.14] bg-white/[0.02] text-[12px] text-white/40">
        Not running
      </div>
    );
  }
  const src = frameSrc(preview);
  const title = preview.title || "Preview";
  return (
    <div className="h-full min-h-[160px] flex flex-col rounded-xl overflow-hidden border border-white/[0.09] bg-panel2">
      <div className="flex-none flex items-center gap-2 pl-3 pr-1 h-11">
        <span className="w-[6px] h-[6px] flex-none rounded-full bg-green anim-softpulse" />
        <div className="min-w-0 flex-1 leading-tight">
          <div className={`truncate font-semibold ${size === "lg" ? "text-[13px]" : "text-[12px]"}`}>{title}</div>
          {agentName && <div className="truncate text-[10.5px] text-white/45">{agentName}</div>}
        </div>
        <a
          href={src}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Open ${title} in a new tab`}
          className="flex-none w-11 h-11 grid place-items-center rounded-lg text-white/55 [@media(hover:hover)_and_(pointer:fine)]:hover:text-text [@media(hover:hover)_and_(pointer:fine)]:hover:bg-white/[0.06]"
        >
          ↗
        </a>
        {onRemove && (
          <button
            onClick={onRemove}
            aria-label={`Remove ${title}`}
            className="flex-none w-11 h-11 grid place-items-center rounded-lg text-white/55 text-[15px] [@media(hover:hover)_and_(pointer:fine)]:hover:text-text [@media(hover:hover)_and_(pointer:fine)]:hover:bg-white/[0.06]"
          >
            ×
          </button>
        )}
      </div>
      <div ref={box} className="relative flex-1 min-h-0 overflow-hidden bg-white">
        <iframe
          src={src}
          title={title}
          loading="lazy"
          // popups: report citations open their source in a new tab
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"
          style={{ width: `${100 / scale}%`, height: `${100 / scale}%`, transform: `scale(${scale})`, transformOrigin: "0 0" }}
          className={`absolute left-0 top-0 border-0 ${size === "sm" ? "pointer-events-none" : ""}`}
        />
      </div>
    </div>
  );
}
