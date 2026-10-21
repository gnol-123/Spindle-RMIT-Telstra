"use client";

import { useEffect, useRef, useState } from "react";
import {
  listProjects,
  createProject,
  deleteProject,
  logout,
  getMe,
  classifyPrompt,
  buildProject,
  ApiError,
} from "@/lib/api";
import { Project, User } from "@/lib/types";
import { Brand } from "./Brand";
import SpindleAnim from "./SpindleAnim";

const SAMPLES = ["Finance tracker", "Build me a finance tracker", "Recipe box", "Make a habit app with streaks"];
const RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

function firstName(user: User | null) {
  if (!user) return "";
  const local = user.email?.split("@")[0] ?? "";
  return user.name?.split(" ")[0] || local.charAt(0).toUpperCase() + local.slice(1);
}

function Arrow() {
  return (
    <svg viewBox="0 0 256 256" fill="none" stroke="currentColor" strokeWidth="22" strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5" aria-hidden="true">
      <path d="M40 128h176M144 56l72 72-72 72" />
    </svg>
  );
}

export default function ProjectsScreen({
  onOpen,
  onLoggedOut,
}: {
  onOpen: (project: Project, focusNodeId?: string, initialPrompt?: string) => void;
  onLoggedOut: () => void;
}) {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Composer
  const [text, setText] = useState("");
  const [phase, setPhase] = useState<"idle" | "reading" | "ready">("idle");
  const [kind, setKind] = useState<"name" | "build">("name");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);
  const ctrl = useRef<AbortController | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const taRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((e) => {
        setProjects([]);
        setListError(e.message);
      });
    getMe().then(setUser).catch(() => {});
  }, []);

  // Typed placeholder, set on the node so it doesn't re-render the screen.
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
      ta.placeholder = SAMPLES[1];
      return;
    }
    let i = 0;
    let j = 0;
    let del = false;
    let t = 0;
    const tick = () => {
      const w = SAMPLES[i];
      j += del ? -1 : 1;
      ta.placeholder = w.slice(0, j);
      let d = del ? 28 : 55;
      if (!del && j === w.length) {
        del = true;
        d = 1600;
      } else if (del && j === 0) {
        del = false;
        i = (i + 1) % SAMPLES.length;
        d = 350;
      }
      t = window.setTimeout(tick, d);
    };
    tick();
    return () => window.clearTimeout(t);
  }, []);

  // Drops any queued or in-flight classify so a stale answer never lands.
  function cancelClassify() {
    seq.current++;
    ctrl.current?.abort();
    ctrl.current = null;
    window.clearTimeout(timer.current);
  }

  useEffect(() => cancelClassify, []);

  async function classify(value: string) {
    const v = value.trim();
    if (!v) return;
    cancelClassify();
    const my = seq.current;
    const c = new AbortController();
    ctrl.current = c;
    setPhase("reading");
    let next: "name" | "build" = "name";
    try {
      next = (await classifyPrompt(v, c.signal)).kind;
    } catch {
      // network or auth trouble: fall back to the plain create path
    }
    if (my !== seq.current) return;
    setKind(next);
    setPhase("ready");
  }

  function handleChange(value: string) {
    setText(value);
    setError(null);
    cancelClassify();
    setPhase("idle");
    if (value.trim()) timer.current = window.setTimeout(() => classify(value), 3000);
  }

  async function handleAction() {
    const v = text.trim();
    if (!v || pending) return;
    setPending(true);
    setError(null);
    try {
      if (kind === "name") {
        const project = await createProject(v);
        setProjects((p) => [project, ...(p ?? [])]);
        setText("");
        setPhase("idle");
      } else {
        const { project, orchestrator_node_id } = await buildProject(v);
        // The orchestrator's chat sends the idea (streamed, errors shown there).
        onOpen(project, orchestrator_node_id, v);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
    } finally {
      setPending(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== "Enter" || e.shiftKey) return;
    e.preventDefault();
    if (phase === "ready") handleAction();
    else classify(text);
  }

  async function handleDelete(project: Project) {
    setDeletingId(project.id);
    setListError(null);
    try {
      await deleteProject(project.id);
      setProjects((p) => (p ?? []).filter((x) => x.id !== project.id));
    } catch (e) {
      setListError(e instanceof ApiError ? e.message : "Could not delete project");
    } finally {
      setDeletingId(null);
      setConfirmingId(null);
    }
  }

  const name = firstName(user);

  return (
    <div className="h-screen flex flex-col bg-bg text-text">
      <header className="flex-none flex items-center gap-4 px-5 h-[60px] border-b border-white/[0.09]">
        <Brand />
        <button
          onClick={async () => {
            await logout();
            onLoggedOut();
          }}
          className={`ml-auto shrink-0 whitespace-nowrap bg-transparent border border-white/[0.14] text-white/60 hover:text-text hover:border-white/30 rounded-lg px-3 py-2 text-xs ${RING}`}
        >
          Log out
        </button>
      </header>

      <div className="flex-1 min-h-0 overflow-auto lg:overflow-hidden grid lg:grid-cols-[minmax(0,1fr)_340px]">
        <main
          className="order-2 lg:order-1 lg:min-h-0 lg:overflow-auto px-5 sm:px-7 py-8"
          style={{
            backgroundImage: "radial-gradient(rgba(255,255,255,.06) 1px, transparent 1px)",
            backgroundSize: "26px 26px",
          }}
        >
          <h1 className="text-[17px] font-semibold tracking-[-0.01em]">Your projects</h1>
          <p className="text-xs text-muted mt-1 mb-[22px]">Each project is its own canvas of agents, tools and sandboxes.</p>

          {listError && <div className="text-xs text-red-400 mb-4">{listError}</div>}

          {projects === null ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4" aria-busy="true" aria-label="Loading projects">
              {[0, 1, 2].map((i) => (
                <div key={i} className="bg-white/[0.022] border border-white/[0.13] rounded-[13px] p-3">
                  <div className="h-3 w-1/2 mb-3 ml-0.5 rounded-[4px] bg-white/[0.07] animate-pulse motion-reduce:animate-none" />
                  <div className="aspect-[16/10] rounded-[9px] bg-white/[0.04] border border-white/[0.09] animate-pulse motion-reduce:animate-none" />
                </div>
              ))}
            </div>
          ) : projects.length === 0 ? (
            <p className="text-sm text-muted">No projects yet. Name one or describe an idea on the right.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
              {projects.map((p) => (
                <div key={p.id} className="proj-card relative bg-white/[0.022] border border-white/[0.13] rounded-[13px] p-3">
                  <button onClick={() => onOpen(p)} className={`proj-open block w-full text-left rounded-[9px] ${RING}`}>
                    <div className="text-[13px] font-medium mb-2.5 ml-0.5 pr-6 truncate">{p.name}</div>
                    <div className="relative aspect-[16/10] rounded-[9px] bg-bg border border-white/[0.09] overflow-hidden">
                      {p.preview_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={p.preview_url} alt="" loading="lazy" className="absolute inset-0 w-full h-full object-cover object-top" />
                      ) : (
                        <div className="absolute inset-0 grid place-items-center text-[10.5px] text-muted">No preview yet</div>
                      )}
                    </div>
                  </button>

                  {confirmingId === p.id ? (
                    <div className="flex items-center gap-2 mt-2.5 flex-wrap">
                      <span className="text-[10px] text-muted">Delete? Cascades to its whole canvas.</span>
                      <button
                        onClick={() => handleDelete(p)}
                        disabled={deletingId === p.id}
                        className={`text-[11px] text-red-400 border border-red-400/40 rounded-md px-2 py-1 disabled:opacity-50 ${RING}`}
                      >
                        {deletingId === p.id ? "Deleting..." : "Delete"}
                      </button>
                      <button onClick={() => setConfirmingId(null)} className={`text-[11px] text-muted hoverable:text-text px-1 rounded ${RING}`}>
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setConfirmingId(p.id)}
                      title="Delete project"
                      aria-label={`Delete ${p.name}`}
                      className={`proj-x absolute top-[9px] right-[11px] text-white/30 hoverable:text-red-400 text-sm px-1 rounded transition-opacity duration-150 ${RING}`}
                    >
                      ×
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </main>

        <aside className="order-1 lg:order-2 relative flex flex-col lg:overflow-hidden bg-panel border-b lg:border-b-0 lg:border-l border-white/[0.09] px-7 pt-7 lg:pt-11">
          <p className="text-[22px] font-semibold tracking-[-0.01em]">Hello{name && ` ${name}`}!</p>
          <p className="text-[22px] font-semibold tracking-[-0.01em] leading-tight text-[rgba(245,237,226,0.55)] mt-0.5 mb-[34px]">
            Shall we <span className="text-amber">Spindel</span> something?
          </p>
          <label htmlFor="composer" className="block text-xs text-[rgba(245,237,226,0.75)] mb-2">
            Give us your idea or name your project
          </label>
          <div className="composer relative flex bg-[rgba(10,15,36,0.55)] border border-white/[0.13] rounded-[12px] px-4 pt-3.5 pb-3">
            <textarea
              id="composer"
              ref={taRef}
              rows={2}
              value={text}
              readOnly={pending}
              autoComplete="off"
              onChange={(e) => handleChange(e.target.value)}
              onKeyDown={handleKeyDown}
              className="flex-1 min-w-0 h-[46px] resize-none bg-transparent border-0 outline-none p-0 text-[15px] leading-[1.5] text-text caret-amber placeholder:text-[rgba(245,237,226,0.32)]"
            />
          </div>

          <div className="mt-3 min-h-[40px] flex items-center gap-2.5 flex-wrap" aria-live="polite">
            {phase === "reading" && (
              <>
                <span className="reading-dots inline-flex gap-1" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                <span className="text-[11px] text-muted">Reading your prompt</span>
              </>
            )}
            {phase === "ready" && kind === "name" && (
              <button
                type="button"
                onClick={handleAction}
                disabled={pending}
                className={`btn-name press anim-rise inline-flex items-center gap-2 rounded-[4px] px-4 py-2.5 text-[13px] font-semibold bg-white/[0.05] text-text border border-white/[0.22] disabled:opacity-60 ${RING}`}
              >
                {pending ? "Creating..." : "Create project"} <Arrow />
              </button>
            )}
            {phase === "ready" && kind === "build" && (
              <>
                <button
                  type="button"
                  onClick={handleAction}
                  disabled={pending}
                  className={`btn-build press anim-rise inline-flex items-center gap-2 rounded-[4px] px-4 py-2.5 text-[13px] font-semibold bg-amber text-[#2b1a00] border border-amber disabled:opacity-60 ${RING}`}
                >
                  {pending ? "Starting..." : "Build idea"} <Arrow />
                </button>
                <span className="text-[11px] text-muted">New project, orchestrator runs it</span>
              </>
            )}
          </div>
          {error && <p className="text-xs text-red-400 mt-1">{error}</p>}

          <div className="mt-6 lg:mt-auto -mx-7 h-[120px] lg:h-[170px]">
            <SpindleAnim />
          </div>
        </aside>
      </div>
    </div>
  );
}
