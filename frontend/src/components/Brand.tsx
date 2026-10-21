import SpindleAnim from "./SpindleAnim";

// Spinning spindle logo; box is 1.6x wide.
export function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <div role="img" aria-label="Spindel" className="flex-none" style={{ width: Math.round(size * 1.6), height: size }}>
      <SpindleAnim turns={1.5} step={2} square={0.7} />
    </div>
  );
}

// Loading indicator: mini spindle, width 1.6x height. Label makes it a status.
export function Spinner({ size = 14, label, className = "" }: { size?: number; label?: string; className?: string }) {
  const tiny = size < 16;
  const a11y = label ? { role: "status", "aria-label": label } : { "aria-hidden": true };
  return (
    <span {...a11y} className={`inline-block flex-none ${className}`} style={{ width: Math.round(size * 1.6), height: size }}>
      <SpindleAnim turns={tiny ? 1 : 1.5} step={tiny ? 1.5 : 2} square={tiny ? 0.5 : 0.7} />
    </span>
  );
}

// muru-D × RMIT lockup for headers.
export function BrandLockup({ className = "" }: { className?: string }) {
  /* eslint-disable @next/next/no-img-element */
  return (
    <div className={`flex items-center gap-2 flex-none ${className}`}>
      <img src="/murud-logo.svg" alt="muru-D" className="h-8 w-auto" />
      <span className="text-white/40 text-sm">×</span>
      <img src="/rmit-logo.svg" alt="RMIT University" className="h-5 w-auto" />
    </div>
  );
  /* eslint-enable @next/next/no-img-element */
}

export function Brand({ sub }: { sub?: string }) {
  return (
    <div className="flex items-center gap-3 min-w-0">
      <BrandMark />
      <div className="min-w-0">
        <div className="text-sm font-semibold tracking-[-0.01em]">Spindel</div>
        <div className="text-[10.5px] text-white/[0.38] truncate">{sub ?? "Telstra Muru-D Team 2"}</div>
      </div>
    </div>
  );
}
