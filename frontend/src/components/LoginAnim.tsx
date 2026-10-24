"use client";

import { useEffect, useRef } from "react";
import SpindleAnim from "./SpindleAnim";
import { Spinner } from "./Brand";
import { AGENT_ICONS, AGENT_ROLES } from "./NodeCard";

// Pipeline order on the login loop.
const PIPE = [
  { slug: "project_scoping", name: "Scoping", done: "Scoped", out: () => `${rnd(5, 9)} features` },
  { slug: "market_research", name: "Market research", done: "Researched", out: () => `${rnd(8, 24)} rivals found` },
  { slug: "ux_ui", name: "UX / UI", done: "Designed", out: () => `${rnd(4, 9)} screens` },
  { slug: "coding", name: "Coding", done: "Built", out: () => `${rnd(24, 80)} tests ✓` },
];

const IDEAS = [
  "A recipe app that plans a week of meals from what is in my fridge",
  "A booking page for a local community garden",
  "A study planner for first-year uni students",
  "A volunteer roster tool for a weekend sports club",
  "A reusable coffee cup rental service for campus cafes",
];

const W = 660; // stage size, scaled to fit the panel
const H = 560;
const CX = W / 2;
const AGENT_X = PIPE.map((_, i) => 87 + i * 162);
const NS = "http://www.w3.org/2000/svg";

function rnd(a: number, b: number) {
  return a + Math.floor(Math.random() * (b - a + 1));
}

function Status() {
  return (
    <div className="la-st">
      <span className="la-spin">
        <Spinner size={12} />
      </span>
      <span className="la-dot" />
      <span data-t>ready</span>
    </div>
  );
}

// Idea → orchestrator → agent pipeline → "ready for review", on loop.
export default function LoginAnim() {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const root = ref.current!;
    const q = <T extends Element = HTMLElement>(s: string) => root.querySelector(s) as T;
    const stage = q("[data-stage]");
    const svg = q<SVGSVGElement>("[data-svg]");
    const cap = q("[data-cap]");
    const idea = q("[data-idea]");
    const typed = q("[data-typed]");
    const orch = q("[data-orch]");
    const agents = [...root.querySelectorAll<HTMLElement>("[data-agent]")];
    const result = q("[data-result]");
    const checks = [...result.querySelectorAll<HTMLElement>(".la-chk")];

    let alive = true;
    const timers = new Set<ReturnType<typeof setTimeout>>();
    // Cleared on unmount, so a pending sleep never resolves and the loop just stops.
    const sleep = (ms: number) =>
      new Promise<void>((r) => {
        const t = setTimeout(() => (timers.delete(t), r()), ms);
        timers.add(t);
      });
    const frame = () => sleep(34);

    const ro = new ResizeObserver(() => {
      const p = stage.parentElement!;
      stage.style.transform = `scale(${Math.min(p.clientWidth / (W + 40), p.clientHeight / (H + 60), 1.35)})`;
    });
    ro.observe(stage.parentElement!);

    const place = (el: HTMLElement, s: Partial<CSSStyleDeclaration>) => Object.assign(el.style, s);
    const show = (el: HTMLElement) => el.classList.remove("la-hidden");
    const say = (t: string) => (cap.textContent = t);
    const status = (el: HTMLElement, cls: "think" | "run" | "done" | null, t: string) => {
      el.classList.remove("la-think", "la-run", "la-done");
      if (cls) el.classList.add(`la-${cls}`);
      el.querySelector<HTMLElement>("[data-t]")!.textContent = t;
    };

    function edge(d: string, chain = false) {
      const p = document.createElementNS(NS, "path");
      p.setAttribute("d", d);
      p.setAttribute("class", chain ? "la-edge la-chain" : "la-edge");
      svg.appendChild(p);
      if (chain) return p;
      const L = p.getTotalLength();
      p.style.strokeDasharray = `${L}`;
      p.style.strokeDashoffset = `${L}`;
      p.getBoundingClientRect();
      p.style.transition = "stroke-dashoffset .55s ease, opacity .4s";
      p.style.strokeDashoffset = "0";
      return p;
    }

    function packet(path: SVGPathElement, ms: number, blue = false) {
      return new Promise<void>((res) => {
        const c = document.createElementNS(NS, "circle");
        c.setAttribute("r", "3.5");
        c.setAttribute("class", blue ? "la-pkt la-blue" : "la-pkt");
        svg.appendChild(c);
        const L = path.getTotalLength();
        const t0 = performance.now();
        const step = (t: number) => {
          if (!alive) return;
          const k = Math.min((t - t0) / ms, 1);
          const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
          const pt = path.getPointAtLength(e * L);
          c.setAttribute("cx", `${pt.x}`);
          c.setAttribute("cy", `${pt.y}`);
          if (k < 1) requestAnimationFrame(step);
          else (c.remove(), res());
        };
        requestAnimationFrame(step);
      });
    }

    async function type(el: HTMLElement, text: string, base: number) {
      el.textContent = "";
      for (const ch of text) {
        el.textContent += ch;
        await sleep(base + Math.random() * base);
      }
    }

    // Snap everything back to its start pose without animating.
    function reset() {
      root.classList.add("la-snap");
      svg.replaceChildren();
      idea.className = "la-card la-idea la-hidden";
      place(idea, { left: "90px", top: "215px", width: "480px", transform: "scale(.92)", opacity: "" });
      typed.textContent = "";
      orch.className = "la-card la-orch la-hidden";
      place(orch, { left: `${CX - 132}px`, top: "232px", transform: "scale(.4)", opacity: "" });
      status(orch, null, "ready");
      for (const a of agents) {
        a.className = "la-card la-agent la-hidden";
        place(a, { left: `${CX - 70}px`, top: "110px", transform: "scale(.3)", opacity: "" });
        status(a, null, "ready");
        a.querySelector("[data-out]")!.textContent = "";
      }
      result.className = "la-card la-result la-hidden";
      place(result, { transform: "scale(.6)", opacity: "" });
      checks.forEach((c) => c.classList.remove("la-on"));
      root.getBoundingClientRect();
      root.classList.remove("la-snap");
    }

    async function play(text: string) {
      reset();
      await frame();

      // idea typed big, then shrinks in place at top centre
      say("Idea received");
      show(idea);
      idea.style.transform = "none";
      await sleep(400);
      await type(typed, text, 26);
      await sleep(500);
      idea.classList.add("la-mini");
      place(idea, { left: `${CX - 150}px`, top: "10px", width: "300px" });
      await sleep(750);

      // orchestrator spins up big, then shrinks under the idea
      show(orch);
      orch.style.transform = "scale(1.5)";
      await sleep(500);
      const e0 = edge(`M${CX} 66 C${CX} 130 ${CX} 150 ${CX} 208`);
      await packet(e0, 700, true);
      status(orch, "think", "planning…");
      say("Orchestrator is planning the work");
      await sleep(1500);
      e0.style.opacity = "0";
      status(orch, "think", `provisioning ${PIPE.length} agents`);
      say(`Provisioning ${PIPE.length} agents`);
      place(orch, { top: "110px", transform: "none" });
      await sleep(500);
      const e1 = edge(`M${CX} 66 L${CX} 110`);

      // agents fly out of the orchestrator into a row
      const fan: SVGPathElement[] = [];
      for (let i = 0; i < agents.length; i++) {
        const x = AGENT_X[i];
        show(agents[i]);
        place(agents[i], { left: `${x - 70}px`, top: "300px", transform: "none" });
        await sleep(380);
        fan.push(edge(`M${CX} 206 C${CX} 260 ${x} 250 ${x} 300`));
        await sleep(160);
      }
      const chain = AGENT_X.slice(1).map((x, i) =>
        edge(`M${AGENT_X[i]} 404 C${AGENT_X[i]} 460 ${x} 460 ${x} 404`, true),
      );
      status(orch, "run", "running pipeline");
      await sleep(400);

      // run in sequence, handing off along the chain
      for (let i = 0; i < agents.length; i++) {
        const a = agents[i];
        say(`${PIPE[i].name} agent working`);
        await packet(fan[i], 550, true);
        status(a, "run", "running");
        packet(fan[i], 700, true);
        await type(a.querySelector<HTMLElement>("[data-out]")!, `→ ${PIPE[i].out()}`, 22);
        await sleep(350);
        status(a, "done", "done");
        if (chain[i]) await packet(chain[i], 600);
      }
      status(orch, "done", "done");
      await sleep(500);

      // everything collapses into the result
      say("Combining results");
      [e1, ...fan, ...chain].forEach((p) => (p.style.opacity = "0"));
      for (const c of [...agents, orch, idea])
        place(c, { left: `${CX - c.offsetWidth / 2}px`, top: "220px", transform: "scale(.2)", opacity: "0" });
      await sleep(750);
      q("[data-quote]").textContent = `“${text}”`;
      show(result);
      result.style.transform = "none";
      say("Researched, scoped, designed and built");
      await sleep(450);
      for (const c of checks) {
        c.classList.add("la-on");
        await sleep(220);
      }
      await sleep(2600);
      place(result, { opacity: "0", transform: "scale(.96)" });
      say("");
      await sleep(600);
    }

    if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
      reset();
      q("[data-quote]").textContent = `“${IDEAS[0]}”`;
      show(result);
      result.style.transform = "none";
      checks.forEach((c) => c.classList.add("la-on"));
    } else {
      (async () => {
        while (alive) {
          const order = IDEAS.map((t) => [Math.random(), t] as const).sort((a, b) => a[0] - b[0]);
          for (const [, t] of order) {
            // panel is display:none on small screens; idle until it shows
            while (alive && !root.offsetParent) await sleep(1000);
            await play(t);
          }
        }
      })();
    }

    return () => {
      alive = false;
      timers.forEach(clearTimeout);
      ro.disconnect();
    };
  }, []);

  return (
    <div ref={ref} aria-hidden="true" className="la-panel">
      <div className="la-dots" />
      <div className="la-spiral">
        <SpindleAnim />
      </div>
      <div className="la-wrap">
        <div data-stage className="la-stage">
          <svg data-svg viewBox={`0 0 ${W} ${H}`} />
          <div data-idea className="la-card la-idea la-hidden">
            <div className="la-lbl">Give us your idea or name your project</div>
            <div className="la-txt">
              <span data-typed />
              <span className="la-caret" />
            </div>
          </div>
          <div data-orch className="la-card la-orch la-hidden">
            <div className="la-hd">
              <span className="la-ic">{AGENT_ICONS.orchestrator}</span>Orchestrator
            </div>
            <div className="la-role">{AGENT_ROLES.orchestrator}</div>
            <Status />
          </div>
          {PIPE.map((a, i) => (
            <div key={a.slug} data-agent className="la-card la-agent la-hidden">
              <div className="la-bob" style={{ animationDelay: `${-i * 0.8}s` }}>
                <div className="la-hd">
                  <span className="la-ic">{AGENT_ICONS[a.slug]}</span>
                  {a.name}
                </div>
                <Status />
                <div data-out className="la-out" />
              </div>
            </div>
          ))}
          <div data-result className="la-card la-result la-hidden">
            <div className="la-tag">● READY FOR YOUR REVIEW</div>
            <div className="la-title">Your idea, built</div>
            <div data-quote className="la-quote" />
            {PIPE.map((a) => (
              <div key={a.slug} className="la-chk">
                <i>✓</i>
                {a.done}
                <span>{a.name}</span>
              </div>
            ))}
            <div className="la-review">Review project →</div>
          </div>
        </div>
      </div>
      <div data-cap className="la-cap" />
    </div>
  );
}
