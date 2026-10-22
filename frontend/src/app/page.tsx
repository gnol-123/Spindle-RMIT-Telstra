"use client";

import { useEffect, useRef, useState } from "react";
import { loadAuth, saveAuth } from "@/lib/auth";
import { completeOAuth, getMe } from "@/lib/api";
import { Project } from "@/lib/types";
import LoginScreen from "@/components/LoginScreen";
import ProjectsScreen from "@/components/ProjectsScreen";
import MeshCanvas from "@/components/MeshCanvas";

export default function Home() {
  const [checkedAuth, setCheckedAuth] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  // focusNodeId + initialPrompt: Build idea opens the orchestrator's chat and sends the idea.
  const [active, setActive] = useState<{ project: Project; focusNodeId?: string; initialPrompt?: string } | null>(null);
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
      .then(() => setLoggedIn(true))
      .catch(() => setLoggedIn(false))
      .finally(() => setCheckedAuth(true));
  }, []);

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
        <ProjectsScreen onOpen={(project, focusNodeId, initialPrompt) => setActive({ project, focusNodeId, initialPrompt })} onLoggedOut={() => setLoggedIn(false)} />
      </>
    );
  }

  return (
    <>
      {banner}
      <MeshCanvas project={active.project} focusNodeId={active.focusNodeId} initialPrompt={active.initialPrompt} onBack={() => setActive(null)} />
    </>
  );
}
