"use client";

import { useEffect, useRef, useState } from "react";
import { loadAuth, saveAuth } from "@/lib/auth";
import { ApiError, completeOAuth, getMe, listProjects, savePushSubscription } from "@/lib/api";
import { pushSupported, registerServiceWorker, startPresence } from "@/lib/push";
import { useNotifications } from "@/lib/useNotifications";
import { Project } from "@/lib/types";
import LoginScreen from "@/components/LoginScreen";
import ProjectsScreen from "@/components/ProjectsScreen";
import MeshCanvas from "@/components/MeshCanvas";
import NotificationBell from "@/components/NotificationBell";

// ?project=<id> keeps the open project across refresh and back/forward.
async function projectFromUrl(): Promise<Project | null> {
  const id = new URLSearchParams(window.location.search).get("project");
  if (!id) return null;
  const project = (await listProjects().catch(() => [] as Project[])).find((p) => p.id === id);
  if (!project) window.history.replaceState({}, "", window.location.pathname);
  return project ?? null;
}

export default function Home() {
  const [checkedAuth, setCheckedAuth] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  // focusNodeId + initialPrompt: Build idea opens the orchestrator's chat and sends the idea.
  const [active, setActive] = useState<{ project: Project; focusNodeId?: string; initialPrompt?: string } | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // strict mode runs effects twice; the code is single-use
  const oauthStarted = useRef(false);

  useEffect(() => {
    // Google login (POST /auth/login/google) returns the browser here with
    // the session in the URL fragment, since only JS can read that part.
    if (window.location.hash.includes("access_token")) {
      const params = new URLSearchParams(window.location.hash.slice(1));
      const access_token = params.get("access_token");
      const refresh_token = params.get("refresh_token");
      if (access_token && refresh_token) {
        saveAuth({ access_token, refresh_token });
      }
      window.history.replaceState({}, "", window.location.pathname);
    }

    // A tool node's OAuth connect flow (POST /nodes/{id}/authorize) lands
    // back here with ?oauth_code&oauth_state to complete as this user, or ?oauth=error.
    const search = new URLSearchParams(window.location.search);
    const oauth = search.get("oauth");
    const oauthCode = search.get("oauth_code");
    const oauthState = search.get("oauth_state");
    const connected = "Account connected. Re-open the tool node to confirm it verified.";
    const failed = "That account connection failed. Open the tool node and try again.";
    if (oauth === "error") setNotice(failed);
    if (oauth || oauthCode || oauthState) window.history.replaceState({}, "", window.location.pathname);
    if (oauthCode && oauthState && !oauthStarted.current) {
      oauthStarted.current = true;
      completeOAuth(oauthCode, oauthState)
        .then(() => setNotice(connected))
        .catch(() => setNotice(failed));
    }

    const stored = loadAuth();
    if (!stored) {
      setCheckedAuth(true);
      return;
    }
    // Confirm the stored token still works rather than trusting it blindly.
    getMe()
      .then(async (me) => {
        setUserId(me.id);
        const project = await projectFromUrl();
        if (project) setActive({ project });
        setLoggedIn(true);
      })
      .catch(() => setLoggedIn(false))
      .finally(() => setCheckedAuth(true));

    const onPop = () => projectFromUrl().then((project) => setActive(project ? { project } : null));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // logged in without a user id (login, or /auth/me failed): keep asking with
  // backoff; a 401 means the session is gone, so log out
  useEffect(() => {
    if (!loggedIn || userId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const attempt = (n: number) =>
      getMe()
        .then((me) => {
          if (!stopped) setUserId(me.id);
        })
        .catch((err) => {
          if (stopped) return;
          if (err instanceof ApiError && err.status === 401) return setLoggedIn(false);
          timer = setTimeout(() => attempt(n + 1), Math.min(30_000, 2_000 * 2 ** n));
        });
    attempt(0);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [loggedIn, userId]);

  const { items, dot, markAllRead } = useNotifications(loggedIn ? userId : null, active?.project.id ?? null);

  // presence ping; re-save an existing push subscription so it binds to this account
  useEffect(() => {
    if (!loggedIn) return;
    if (pushSupported()) {
      registerServiceWorker()
        .then(async (reg) => {
          const ready = reg && (await navigator.serviceWorker.ready);
          const sub = await ready?.pushManager.getSubscription();
          if (sub) await savePushSubscription(sub.toJSON());
        })
        .catch(() => {});
    }
    return startPresence();
  }, [loggedIn]);

  const openProject = (project: Project, focusNodeId?: string, initialPrompt?: string) => {
    window.history.pushState({}, "", `?project=${encodeURIComponent(project.id)}`);
    setActive({ project, focusNodeId, initialPrompt });
  };
  const closeProject = () => {
    window.history.pushState({}, "", window.location.pathname);
    setActive(null);
  };

  if (!checkedAuth) {
    return <div className="h-screen flex items-center justify-center text-muted text-sm bg-bg">Loading…</div>;
  }

  const banner = notice && (
    <div className="bg-accent/10 border-b border-accent/30 text-accent text-xs px-5 py-2 flex items-center gap-3">
      <span className="flex-1">{notice}</span>
      <button onClick={() => setNotice(null)} className="text-accent/70 hover:text-accent">
        dismiss
      </button>
    </div>
  );

  const bell = (
    <NotificationBell
      items={items}
      dot={dot}
      onOpenPanel={markAllRead}
      onOpenProject={async (id) => {
        if (active?.project.id === id) return;
        const project = (await listProjects().catch(() => [] as Project[])).find((p) => p.id === id);
        if (project) openProject(project);
      }}
    />
  );

  if (!loggedIn) {
    return (
      <>
        {banner}
        <LoginScreen onLoggedIn={() => setLoggedIn(true)} />
      </>
    );
  }

  if (!active) {
    return (
      <>
        {banner}
        <ProjectsScreen onOpen={openProject} onLoggedOut={() => {
          setUserId(null);
          setLoggedIn(false);
        }} bell={bell} />
      </>
    );
  }

  return (
    <>
      {banner}
      <MeshCanvas key={active.project.id} project={active.project} focusNodeId={active.focusNodeId} initialPrompt={active.initialPrompt} onBack={closeProject} bell={bell} />
    </>
  );
}
