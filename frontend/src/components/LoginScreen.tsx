"use client";

import { useState } from "react";
import { login, signup, googleLoginUrl, ApiError } from "@/lib/api";
import { BrandLockup, BrandMark } from "./Brand";
import LoginAnim from "./LoginAnim";

export default function LoginScreen({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleGoogle() {
    setError(null);
    try {
      const { url } = await googleLoginUrl(window.location.origin);
      window.location.href = url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start Google sign-in");
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    setBusy(true);
    try {
      if (mode === "login") {
        await login(email, password);
        onLoggedIn();
      } else {
        await signup(email, password);
        setMessage("Check your email to confirm your account, then log in.");
        setMode("login");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  const input =
    "w-full bg-white/[0.03] border border-white/[0.13] rounded-[10px] px-3.5 py-3 text-sm outline-none focus:border-accent/50 placeholder:text-white/30";

  return (
    <div className="h-dvh flex bg-bg text-text overflow-hidden">
      <section className="flex-1 min-[900px]:flex-none min-[900px]:w-[clamp(420px,36vw,540px)] flex flex-col px-6 sm:px-11 py-8 overflow-y-auto">
        <div className="flex items-center gap-2.5">
          <BrandMark size={26} />
          <span className="text-[15px] font-semibold">Spindle</span>
        </div>

        <form onSubmit={handleSubmit} className="m-auto w-full max-w-[390px] py-10 anim-pop">
          <h1 className="text-[30px] font-semibold tracking-[-0.01em]">
            {mode === "login" ? "Welcome back" : "Create an account"}
          </h1>
          <p className="text-sm text-[rgba(245,237,226,0.55)] mt-1.5 mb-7">
            {mode === "login" ? "Log in to your workspace" : "Sign up to start spindling ideas"}
          </p>

          <button
            type="button"
            onClick={handleGoogle}
            className="w-full border border-white/[0.14] rounded-[10px] py-3 text-sm text-text/85 hover:border-accent/45"
          >
            Continue with Google
          </button>

          <div className="flex items-center gap-3 text-[11px] text-muted my-5">
            <div className="flex-1 h-px bg-border" />
            or
            <div className="flex-1 h-px bg-border" />
          </div>

          <label htmlFor="login-email" className="block text-xs text-[rgba(245,237,226,0.75)] mb-1.5">
            Email
          </label>
          <input
            id="login-email"
            type="email"
            required
            autoComplete="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={`${input} mb-4`}
          />
          <label htmlFor="login-password" className="block text-xs text-[rgba(245,237,226,0.75)] mb-1.5">
            Password
          </label>
          <input
            id="login-password"
            type="password"
            required
            minLength={8}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            placeholder="Min 8 characters"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={`${input} mb-4`}
          />

          {error && <div className="text-xs text-red-400 mb-3">{error}</div>}
          {message && <div className="text-xs text-green mb-3">{message}</div>}

          <button
            type="submit"
            disabled={busy}
            className="w-full bg-primary hover:bg-accent text-white font-semibold rounded-[10px] py-3 text-sm disabled:opacity-50"
          >
            {busy ? "Please wait…" : mode === "login" ? "Log in" : "Sign up"}
          </button>

          <p className="text-center text-xs text-muted mt-4">
            {mode === "login" ? "Need an account?" : "Already have one?"}{" "}
            <button
              type="button"
              onClick={() => setMode(mode === "login" ? "signup" : "login")}
              className="text-accent hover:text-[#8FB1FF]"
            >
              {mode === "login" ? "Sign up" : "Log in"}
            </button>
          </p>
        </form>

        <BrandLockup className="scale-[.8] origin-left" />
      </section>

      <div className="hidden min-[900px]:block flex-1 p-3 pl-0">
        <LoginAnim />
      </div>
    </div>
  );
}
