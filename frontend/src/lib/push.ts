// Web Push for the installed app (iPadOS 16.4+ Home Screen).
// api.ts is imported lazily: keeps this file loadable by node --test and
// avoids a static cycle with logout().
const api = () => import("./api");

const PRESENCE_MS = 30_000;

export function isStandalone(): boolean {
  if (typeof matchMedia === "function" && matchMedia("(display-mode: standalone)").matches) return true;
  return typeof navigator !== "undefined" && (navigator as { standalone?: boolean }).standalone === true;
}

export function pushSupported(): boolean {
  return typeof navigator !== "undefined" && "serviceWorker" in navigator
    && typeof PushManager !== "undefined" && typeof Notification !== "undefined";
}

// VAPID key: base64url, unpadded
export function urlBase64ToUint8Array(s: string): Uint8Array<ArrayBuffer> {
  const b64 = (s + "=".repeat((4 - (s.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!pushSupported()) return null;
  try {
    return await navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" });
  } catch {
    return null;
  }
}

async function currentSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null;
  try {
    const reg = await navigator.serviceWorker.getRegistration("/");
    return (await reg?.pushManager.getSubscription()) ?? null;
  } catch {
    return null;
  }
}

export async function currentPushEndpoint(): Promise<string | null> {
  return (await currentSubscription())?.endpoint ?? null;
}

// Call from a tap handler. requestPermission runs before any await so iOS
// still sees the user gesture.
export async function enablePush(): Promise<"enabled" | "denied" | "unavailable"> {
  if (!pushSupported()) return "unavailable";
  const key = api().then((m) => m.getPushKey()).catch(() => null);
  const reg = registerServiceWorker();
  const permission = await Notification.requestPermission();
  const publicKey = await key;
  if (!publicKey || !(await reg)) return "unavailable";
  if (permission !== "granted") return "denied";
  const ready = await navigator.serviceWorker.ready;
  const sub = await ready.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(publicKey),
  });
  await (await api()).savePushSubscription(sub.toJSON());
  return "enabled";
}

// Server row first, while the token is valid; local unsubscribe always runs
// so this device stops getting pushes even if the server call fails.
export async function disablePush(): Promise<void> {
  const sub = await currentSubscription();
  if (!sub) return;
  try {
    await (await api()).deletePushSubscription(sub.endpoint);
  } finally {
    await sub.unsubscribe().catch(() => {});
  }
}

// Tells the server this device is looking at the app, so it skips the push.
export function startPresence(): () => void {
  if (typeof document === "undefined") return () => {};
  let endpoint: string | null = null;

  const ping = async () => {
    if (document.visibilityState !== "visible") return;
    endpoint = await currentPushEndpoint();
    if (endpoint) await (await api()).setPushVisible(endpoint, true).catch(() => {});
  };
  const onVisibility = () => {
    if (document.visibilityState === "visible") return void ping();
    // cached endpoint: page may freeze before an async lookup finishes
    const ep = endpoint;
    if (ep) void api().then((m) => m.setPushVisible(ep, false, { keepalive: true })).catch(() => {});
  };

  void ping();
  const timer = setInterval(ping, PRESENCE_MS);
  document.addEventListener("visibilitychange", onVisibility);
  return () => {
    clearInterval(timer);
    document.removeEventListener("visibilitychange", onVisibility);
  };
}
