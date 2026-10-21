"use client";

import { useEffect, useRef } from "react";

const STRANDS = 2;
const TURNS = 3;
const STEP = 4; // px between squares along x
const AMBER = "#F44E1A";

// Two threads of squares wound on a tapered helix, drifting left to right.
// turns/step/square tune the compact logo variant; defaults match the large hero.
export default function SpindleAnim({
  className,
  turns = TURNS,
  step = STEP,
  square = 1,
}: {
  className?: string;
  turns?: number;
  step?: number;
  square?: number;
}) {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const cv = ref.current;
    const ctx = cv?.getContext("2d");
    if (!cv || !ctx) return;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0;
    let h = 0;
    let raf = 0;
    let visible = true;

    function resize() {
      const r = cv!.getBoundingClientRect();
      const dpr = devicePixelRatio || 1;
      w = r.width;
      h = r.height;
      cv!.width = w * dpr;
      cv!.height = h * dpr;
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function draw(t: number) {
      ctx!.clearRect(0, 0, w, h);
      const cy = h / 2;
      const R = h * 0.38;
      const phase = (t / 1000) * 1.6;
      const n = Math.floor(w / step);
      if (n < 1) return;
      const back: [number, number, number][] = [];
      const front: [number, number, number][] = [];
      for (let i = 0; i <= n; i++) {
        const u = i / n;
        const r = R * Math.pow(Math.sin(Math.PI * u), 0.8); // fat middle, pointed ends
        for (let k = 0; k < STRANDS; k++) {
          const th = u * turns * Math.PI * 2 - phase + k * ((Math.PI * 2) / STRANDS);
          const z = Math.sin(th); // -1 back, 1 front
          (z < 0 ? back : front).push([i * step, cy + r * Math.cos(th), z]);
        }
      }
      ctx!.fillStyle = AMBER;
      // shaft
      ctx!.globalAlpha = 0.18;
      for (let i = 0; i <= n; i += 2) ctx!.fillRect(i * step - square, cy - square, 2 * square, 2 * square);
      for (const [x, y, z] of back.concat(front)) {
        const size = (2 + (z + 1) * 1.25) * square;
        ctx!.globalAlpha = 0.25 + (z + 1) * 0.375;
        ctx!.fillRect(x - size / 2, y - size / 2, size, size);
      }
      ctx!.globalAlpha = 1;
    }

    function loop(t: number) {
      draw(t);
      if (visible) raf = requestAnimationFrame(loop);
    }

    resize();
    const ro = new ResizeObserver(() => {
      resize();
      if (reduce) draw(0);
    });
    ro.observe(cv);
    let io: IntersectionObserver | null = null;
    if (reduce) draw(0);
    else {
      io = new IntersectionObserver(([e]) => {
        visible = e.isIntersecting;
        cancelAnimationFrame(raf);
        if (visible) raf = requestAnimationFrame(loop);
      });
      io.observe(cv);
    }
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      io?.disconnect();
    };
  }, [turns, step, square]);

  return <canvas ref={ref} aria-hidden="true" className={`block w-full h-full ${className ?? ""}`} />;
}
