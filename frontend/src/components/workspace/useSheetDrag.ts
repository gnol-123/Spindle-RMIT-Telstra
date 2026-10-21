"use client";

import { RefObject, useEffect, useLayoutEffect, useRef } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { Snap, bodyClaim, pickSnap, rubberband, snapOffsets } from "@/lib/sheet";

type PE = ReactPointerEvent<HTMLElement>;
export type PointerHandlers = {
  onPointerDown: (e: PE) => void;
  onPointerMove: (e: PE) => void;
  onPointerUp: (e: PE) => void;
  onPointerCancel: (e: PE) => void;
};

const EASE = "transform 260ms cubic-bezier(0.23, 1, 0.32, 1)";
const SLOP = 8; // body px before deciding drag vs scroll
const TAP = 4; // handle px still counted as a tap
const VELOCITY_MS = 80;

type Gesture = {
  id: number;
  body: boolean;
  dragging: boolean;
  moved: boolean;
  startX: number;
  startY: number;
  scrollTop: number; // body scrollTop at down
  base: number;
  samples: { t: number; y: number }[];
};

// native touch decision for the body, once per gesture
type TouchClaim = { startX: number; startY: number; scrollTop: number; decided: boolean; claim: boolean };

// Writes transform straight to the DOM; no React state per move.
export function useSheetDrag(
  sheet: RefObject<HTMLElement | null>,
  snap: Snap,
  onSnap: (s: Snap) => void,
): { handleProps: PointerHandlers; bodyProps: PointerHandlers & { "data-sheet-body": "" } } {
  const height = useRef(0);
  const y = useRef(0);
  const snapRef = useRef(snap);
  const onSnapRef = useRef(onSnap);
  const g = useRef<Gesture | null>(null);
  const touch = useRef<TouchClaim | null>(null);

  useEffect(() => {
    onSnapRef.current = onSnap;
  });

  const write = (to: number, animate: boolean) => {
    const el = sheet.current;
    if (!el) return;
    y.current = to;
    el.style.transition =
      animate && !window.matchMedia("(prefers-reduced-motion: reduce)").matches ? EASE : "none";
    el.style.transform = `translate3d(0, ${to}px, 0)`;
  };
  const stop = () => {
    g.current = null;
    if (sheet.current) sheet.current.style.userSelect = "";
  };
  const settle = (s: Snap, animate = true) => write(snapOffsets(height.current)[s], animate);
  // visual offset, catches a sheet mid-settle
  const grab = () => {
    const el = sheet.current;
    const at = el ? new DOMMatrixReadOnly(getComputedStyle(el).transform).m42 : y.current;
    write(at, false);
    return at;
  };

  // re-snap to the same named point on resize / rotation
  useLayoutEffect(() => {
    const parent = sheet.current?.parentElement;
    if (!parent) return;
    const measure = () => {
      height.current = parent.clientHeight;
      if (!g.current?.dragging) settle(snapRef.current, false);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(parent);
    return () => ro.disconnect();
  }, [sheet]);

  useLayoutEffect(() => {
    if (snapRef.current === snap) return;
    snapRef.current = snap;
    stop();
    settle(snap);
  }, [snap]);

  // React touch listeners are passive and may run after the browser picks a pan;
  // decide here so a top pull-down is never handed to native scroll
  useEffect(() => {
    const el = sheet.current;
    if (!el) return;
    const start = (e: TouchEvent) => {
      const body = (e.target as Element).closest("[data-sheet-body]");
      touch.current =
        body && e.touches.length === 1
          ? { startX: e.touches[0].clientX, startY: e.touches[0].clientY, scrollTop: body.scrollTop, decided: false, claim: false }
          : null;
    };
    const move = (e: TouchEvent) => {
      const t = touch.current;
      if (!t) return;
      if (!t.decided) {
        const c = bodyClaim(t.scrollTop, e.touches[0].clientX - t.startX, e.touches[0].clientY - t.startY, SLOP);
        if (c === undefined) return;
        t.decided = true;
        t.claim = c;
      }
      if (t.claim && e.cancelable) e.preventDefault();
    };
    const end = (e: TouchEvent) => {
      if (e.touches.length === 0) touch.current = null;
    };
    el.addEventListener("touchstart", start, { passive: true });
    el.addEventListener("touchmove", move, { passive: false });
    el.addEventListener("touchend", end);
    el.addEventListener("touchcancel", end);
    return () => {
      el.removeEventListener("touchstart", start);
      el.removeEventListener("touchmove", move);
      el.removeEventListener("touchend", end);
      el.removeEventListener("touchcancel", end);
    };
  }, [sheet]);

  const down = (body: boolean) => (e: PE) => {
    if (g.current || (e.pointerType === "mouse" && e.button !== 0)) return;
    if (!body) {
      e.currentTarget.setPointerCapture(e.pointerId);
      if (sheet.current) sheet.current.style.userSelect = "none";
    }
    g.current = {
      id: e.pointerId,
      body,
      dragging: !body,
      moved: false,
      startX: e.clientX,
      startY: e.clientY,
      scrollTop: e.currentTarget.scrollTop,
      base: body ? y.current : grab(),
      samples: [{ t: e.timeStamp, y: e.clientY }],
    };
  };

  const move = (e: PE) => {
    const cur = g.current;
    if (!cur || cur.id !== e.pointerId) return;
    if (!cur.dragging) {
      // touch: native listener decides; mouse/pen: same rule, once, here
      let claim: boolean | undefined;
      if (e.pointerType === "touch") {
        if (touch.current?.decided) claim = touch.current.claim;
      } else {
        claim = bodyClaim(cur.scrollTop, e.clientX - cur.startX, e.clientY - cur.startY, SLOP);
      }
      if (claim === undefined) return;
      if (!claim) {
        g.current = null; // native scroll owns it
        return;
      }
      e.currentTarget.setPointerCapture(e.pointerId);
      if (sheet.current) sheet.current.style.userSelect = "none";
      cur.dragging = true;
      cur.startY = e.clientY;
      cur.base = grab();
      cur.samples = [];
    }
    if (Math.abs(e.clientY - cur.startY) >= TAP) cur.moved = true;
    const t = e.timeStamp;
    cur.samples.push({ t, y: e.clientY });
    while (cur.samples.length > 2 && t - cur.samples[0].t > VELOCITY_MS) cur.samples.shift();
    write(rubberband(cur.base + e.clientY - cur.startY, 0, snapOffsets(height.current).closed), false);
  };

  const end = (cancelled: boolean) => (e: PE) => {
    const cur = g.current;
    if (!cur || cur.id !== e.pointerId) return;
    stop();
    if (!cur.dragging) return;
    const tap = !cur.body && !cur.moved;
    if (cancelled || (tap && snapRef.current !== "closed")) {
      settle(snapRef.current);
      return;
    }
    let to: Snap;
    if (tap) {
      to = "half"; // tap on closed tab
    } else {
      const recent = cur.samples.filter((p) => e.timeStamp - p.t <= VELOCITY_MS);
      const a = recent[0];
      const b = recent[recent.length - 1];
      const v = recent.length > 1 ? (b.y - a.y) / Math.max(1, b.t - a.t) : 0;
      to = pickSnap(y.current, v, snapOffsets(height.current));
    }
    snapRef.current = to;
    settle(to);
    onSnapRef.current(to);
  };

  const handlers = (body: boolean): PointerHandlers => ({
    onPointerDown: down(body),
    onPointerMove: move,
    onPointerUp: end(false),
    onPointerCancel: end(true),
  });
  return { handleProps: handlers(false), bodyProps: { ...handlers(true), "data-sheet-body": "" } };
}
