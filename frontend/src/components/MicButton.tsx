"use client";

import { useEffect, useRef, useState } from "react";
import { transcribeAudio } from "@/lib/api";

// Click to record, click again to stop. The clip is transcribed and cleaned up
// server side (Gemini), then handed to onText.
export default function MicButton({
  onText,
  disabled,
  className = "",
}: {
  onText: (text: string) => void;
  disabled?: boolean;
  className?: string;
}) {
  const [phase, setPhase] = useState<"idle" | "rec" | "busy">("idle");
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<MediaRecorder | null>(null);
  // Latest callback, so text lands on the current draft, not the one at record start.
  const onTextRef = useRef(onText);
  useEffect(() => {
    onTextRef.current = onText;
  });

  // Unmounted mid-recording: release the mic, drop the clip.
  useEffect(
    () => () => {
      const r = rec.current;
      if (!r) return;
      r.onstop = null;
      if (r.state !== "inactive") r.stop();
      r.stream.getTracks().forEach((t) => t.stop());
    },
    []
  );

  async function start() {
    setError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("Microphone unavailable");
      return;
    }
    const r = new MediaRecorder(stream);
    const chunks: Blob[] = [];
    r.ondataavailable = (e) => chunks.push(e.data);
    r.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      rec.current = null;
      setPhase("busy");
      try {
        const text = await transcribeAudio(new Blob(chunks, { type: r.mimeType || "audio/webm" }));
        if (text) onTextRef.current(text);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Transcription failed");
      } finally {
        setPhase("idle");
      }
    };
    r.start();
    rec.current = r;
    setPhase("rec");
  }

  const label = phase === "rec" ? "Stop and transcribe" : phase === "busy" ? "Transcribing…" : "Speak your prompt";

  return (
    <span className={`relative inline-flex shrink-0 ${className}`}>
      <button
        type="button"
        onClick={() => (phase === "rec" ? rec.current?.stop() : start())}
        disabled={phase === "busy" || (disabled && phase === "idle")}
        title={error ?? label}
        aria-label={label}
        aria-pressed={phase === "rec"}
        className={`grid place-items-center w-8 h-8 rounded-lg border transition-colors disabled:opacity-50 ${
          phase === "rec"
            ? "border-red-500/50 bg-red-500/15 text-red-300 animate-pulse"
            : error
              ? "border-red-400/40 text-red-300"
              : "border-white/[0.12] text-white/60 hover:text-white/85"
        }`}
      >
        {phase === "busy" ? (
          <span className="w-3.5 h-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" />
        ) : (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="9" y="2" width="6" height="12" rx="3" />
            <path d="M5 10a7 7 0 0 0 14 0M12 17v5" />
          </svg>
        )}
      </button>
      {error && (
        <span role="alert" className="absolute bottom-full right-0 mb-1.5 whitespace-nowrap rounded-md bg-panel2 border border-red-400/30 px-2 py-1 text-[10.5px] text-red-300">
          {error}
        </span>
      )}
    </span>
  );
}
