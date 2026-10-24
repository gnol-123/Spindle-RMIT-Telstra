"use client";

import { useEffect, useRef, useState } from "react";
import {
  listProjects,
  createProject,
  deleteProject,
  renameProject,
  logout,
  getMe,
  classifyPrompt,
  buildProject,
  ApiError,
} from "@/lib/api";
import { Project, User } from "@/lib/types";
import { Brand, BrandLockup } from "./Brand";
import SpindleAnim from "./SpindleAnim";
import MicButton from "./MicButton";

const SAMPLES = ["Finance tracker", "Build me a finance tracker", "Recipe box", "Make a habit app with streaks"];
const RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";
const CLASSIFY_DEBOUNCE_MS = 700;

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

function Pencil() {
  return (
    <svg viewBox="0 0 256 256" fill="none" stroke="currentColor" strokeWidth="20" strokeLinecap="round" strokeLinejoin="round" className="w-3 h-3" aria-hidden="true">
      <path d="M96 216H48a8 8 0 0 1-8-8v-44.7a8 8 0 0 1 2.3-5.6L160 40a8 8 0 0 1 11.3 0l44.7 44.7a8 8 0 0 1 0 11.3L96 216ZM136 64l56 56" />
    </svg>
  );
}

function Down() {
  return (
    <svg viewBox="0 0 256 256" fill="none" stroke="currentColor" strokeWidth="22" strokeLinecap="round" strokeLinejoin="round" className="w-3 h-3" aria-hidden="true">
      <path d="M128 40v176M56 144l72 72 72-72" />
    </svg>
  );
}

export default function ProjectsScreen({
  onOpen,
  onLoggedOut,
  bell,
}: {
  onOpen: (project: Project, focusNodeId?: string, initialPrompt?: string) => void;
  onLoggedOut: () => void;
  bell?: React.ReactNode;
}) {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [renameError, setRenameError] = useState<{ id: string; message: string } | null>(null);
  // Enter, blur and Escape can all fire for one edit: only the first counts.
  const editDone = useRef(false);

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
  const gridRef = useRef<HTMLElement | null>(null);
  const [gridInView, setGridInView] = useState(false);

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
    if (value.trim()) timer.current = window.setTimeout(() => classify(value), CLASSIFY_DEBOUNCE_MS);
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

  function startRename(p: Project) {
    editDone.current = false;
    setRenameError(null);
    setEditingId(p.id);
  }

  async function finishRename(p: Project, raw: string, save: boolean) {
    if (editDone.current) return;
    editDone.current = true;
    setEditingId(null);
    const next = raw.trim();
    if (!save || !next || next === p.name) return;
    const setName = (name: string) => setProjects((l) => (l ?? []).map((x) => (x.id === p.id ? { ...x, name } : x)));
    setName(next);
    try {
      await renameProject(p.id, next);
    } catch (e) {
      setName(p.name);
      setRenameError({ id: p.id, message: e instanceof ApiError ? e.message : "Could not rename project" });
    }
  }

  // Pill shows only while the projects section is off screen.
  useEffect(() => {
    const el = gridRef.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setGridInView(e.isIntersecting), { threshold: 0, rootMargin: "0px 0px -64px 0px" }); // in view once ~64px of the grid shows
    io.observe(el);
    return () => io.disconnect();
  }, []);

  function jumpToProjects() {
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    gridRef.current?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
  }

  const preview = (p: Project) => (
    <div className="relative aspect-[16/10] rounded-[9px] bg-bg border border-white/[0.09] overflow-hidden">
      {p.preview_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={p.preview_url} alt="" loading="lazy" className="absolute inset-0 w-full h-full object-cover object-top" />
      ) : (
        <div className="absolute inset-0 grid place-items-center text-[10.5px] text-muted">No preview yet</div>
      )}
    </div>
  );

  const name = firstName(user);
  const showJump = !gridInView && projects !== null && projects.length > 0;

  return (
    <div className="min-h-screen bg-bg text-text">
      <header className="flex items-center gap-4 px-5 h-[60px] border-b border-white/[0.09]">
        <Brand />
        <BrandLockup className="ml-auto hidden sm:flex" />
        <div className="ml-auto sm:ml-0">{bell}</div>
        <button
          onClick={async () => {
            await logout();
            onLoggedOut();
          }}
          className={`shrink-0 whitespace-nowrap bg-transparent border border-white/[0.14] text-white/60 hover:text-text hover:border-white/30 rounded-lg px-3 py-2 text-xs ${RING}`}
        >
          Log out
        </button>
      </header>

      <section className="relative isolate overflow-hidden min-h-[calc(100dvh-60px)] flex items-center justify-center px-5 py-12">
        <div className="w-full max-w-[680px]">
          <p className="text-center text-[22px] sm:text-[26px] font-semibold tracking-[-0.01em]">Hello{name && ` ${name}`}!</p>
          <p className="text-center text-[22px] sm:text-[26px] font-semibold tracking-[-0.01em] leading-tight text-[rgba(245,237,226,0.55)] mt-0.5 mb-[34px]">
            <span className="text-accent">Shall we</span> <span className="text-amber">Spindle</span>{" "}
            <span className="text-accent">something?</span>
          </p>
          <label htmlFor="composer" className="block text-xs text-[rgba(245,237,226,0.75)] mb-2">
            Give us your idea or name your project
          </label>
          <div className="relative">
            {/* Spindle behind the composer, full hero width */}
            <div
              aria-hidden="true"
              className="pointer-events-none absolute -z-10 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-screen h-[180px] sm:h-[260px] opacity-40"
            >
              <SpindleAnim />
            </div>
            <div className="composer relative flex bg-[rgba(10,15,36,0.55)] border border-white/[0.13] rounded-[12px] px-4 pt-3.5 pb-3">
              <textarea
                id="composer"
                ref={taRef}
                rows={3}
                value={text}
                readOnly={pending}
                autoComplete="off"
                onChange={(e) => handleChange(e.target.value)}
                onKeyDown={handleKeyDown}
                className="flex-1 min-w-0 h-[68px] resize-none bg-transparent border-0 outline-none p-0 text-[15px] leading-[1.5] text-text caret-amber placeholder:text-[rgba(245,237,226,0.32)]"
              />
              <MicButton
                className="self-end ml-2"
                disabled={pending}
                onText={(t) => {
                  handleChange(text.trim() ? `${text.trimEnd()} ${t}` : t);
                  taRef.current?.focus();
                }}
              />
            </div>
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
        </div>
      </section>

      <main
        ref={gridRef}
        className="px-5 sm:px-7 py-8 border-t border-white/[0.09]"
        style={{
          backgroundImage: "radial-gradient(rgba(255,255,255,.06) 1px, transparent 1px)",
          backgroundSize: "26px 26px",
        }}
      >
        <div className="max-w-6xl mx-auto">
          <h1 className="text-[17px] font-semibold tracking-[-0.01em]">Your projects</h1>
          <p className="text-xs text-muted mt-1 mb-[22px]">Each project is its own canvas of agents, tools and sandboxes.</p>

          {listError && <div className="text-xs text-red-400 mb-4">{listError}</div>}

          {projects === null ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" aria-busy="true" aria-label="Loading projects">
              {[0, 1, 2].map((i) => (
                <div key={i} className="bg-white/[0.022] border border-white/[0.13] rounded-[13px] p-3">
                  <div className="h-3 w-1/2 mb-3 ml-0.5 rounded-[4px] bg-white/[0.07] animate-pulse motion-reduce:animate-none" />
                  <div className="aspect-[16/10] rounded-[9px] bg-white/[0.04] border border-white/[0.09] animate-pulse motion-reduce:animate-none" />
                </div>
              ))}
            </div>
          ) : projects.length === 0 ? (
            <p className="text-sm text-muted">No projects yet. Name one or describe an idea above.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {projects.map((p) => (
                <div key={p.id} className="proj-card relative bg-white/[0.022] border border-white/[0.13] rounded-[13px] p-3">
                  {editingId === p.id ? (
                    <div className="block w-full rounded-[9px]">
                      <input
                        autoFocus
                        defaultValue={p.name}
                        maxLength={200}
                        aria-label={`New name for ${p.name}`}
                        onFocus={(e) => e.currentTarget.select()}
                        onBlur={(e) => finishRename(p, e.currentTarget.value, true)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") finishRename(p, e.currentTarget.value, true);
                          else if (e.key === "Escape") finishRename(p, e.currentTarget.value, false);
                        }}
                        className="block w-[calc(100%-3rem)] text-[13px] font-medium mb-2.5 ml-0.5 px-1.5 py-0.5 -my-0.5 rounded-[4px] bg-white/[0.06] shadow-[inset_0_1px_2px_rgba(0,0,0,0.35)] border-0 outline-none caret-amber text-text"
                      />
                      {preview(p)}
                    </div>
                  ) : (
                    <>
                      <button onClick={() => onOpen(p)} className={`proj-open block w-full text-left rounded-[9px] ${RING}`}>
                        <div className="text-[13px] font-medium mb-2.5 ml-0.5 pr-12 truncate">{p.name}</div>
                        {renameError?.id === p.id && <p className="text-[11px] text-red-400 -mt-1.5 mb-2 ml-0.5">{renameError.message}</p>}
                        {preview(p)}
                      </button>
                      <button
                        onClick={() => startRename(p)}
                        title="Rename project"
                        aria-label={`Rename ${p.name}`}
                        className={`proj-x absolute top-[9px] right-[30px] p-1 text-white/30 hoverable:text-text rounded transition-opacity duration-150 ${RING}`}
                      >
                        <Pencil />
                      </button>
                    </>
                  )}

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
        </div>
      </main>

      {/* Wrapper fades and slides; the button keeps .press scale to itself */}
      <div
        className={`pointer-events-none fixed inset-x-0 bottom-6 z-20 flex justify-center transition-[opacity,transform] duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] ${
          showJump ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2 motion-reduce:translate-y-0"
        } motion-reduce:transition-opacity`}
      >
        <button
          type="button"
          onClick={jumpToProjects}
          aria-label="Jump to your projects"
          aria-hidden={!showJump}
          tabIndex={showJump ? 0 : -1}
          className={`press inline-flex items-center gap-2 rounded-[4px] px-3.5 py-2 text-[12.5px] text-text bg-panel border border-white/[0.13] shadow-[0_8px_24px_rgba(10,15,36,0.7)] hoverable:border-white/30 ${
            showJump ? "pointer-events-auto" : "pointer-events-none"
          } ${RING}`}
        >
          Your projects <Down />
        </button>
      </div>
    </div>
  );
}
