import test from "node:test";
import assert from "node:assert/strict";
// @ts-expect-error node needs the .ts extension; tsc does not allow it
import { urlBase64ToUint8Array, isStandalone } from "./push.ts";

const g = globalThis as Record<string, unknown>;
const stub = (name: string, value: unknown) =>
  Object.defineProperty(globalThis, name, { value, configurable: true, writable: true });

test("urlBase64ToUint8Array known vector", () =>
  assert.deepEqual([...urlBase64ToUint8Array("-_8")], [0xfb, 0xff]));
test("urlBase64ToUint8Array no padding needed", () =>
  assert.deepEqual([...urlBase64ToUint8Array("AQID")], [1, 2, 3]));
test("urlBase64ToUint8Array one pad", () =>
  assert.deepEqual([...urlBase64ToUint8Array("AQI")], [1, 2]));
test("urlBase64ToUint8Array two pads", () =>
  assert.deepEqual([...urlBase64ToUint8Array("AQ")], [1]));
test("urlBase64ToUint8Array 65-byte VAPID key", () => {
  const raw = Uint8Array.from({ length: 65 }, (_, i) => (i * 37) & 0xff);
  const key = Buffer.from(raw).toString("base64url");
  assert.deepEqual(urlBase64ToUint8Array(key), raw);
});

test("isStandalone false with no browser globals", () => {
  const nav = g.navigator;
  stub("navigator", undefined);
  assert.equal(isStandalone(), false);
  stub("navigator", nav);
});
test("isStandalone via display-mode media query", () => {
  stub("matchMedia", (q: string) => ({ matches: q === "(display-mode: standalone)" }));
  assert.equal(isStandalone(), true);
  delete g.matchMedia;
});
test("isStandalone false when media query does not match", () => {
  stub("matchMedia", () => ({ matches: false }));
  assert.equal(isStandalone(), false);
  delete g.matchMedia;
});
test("isStandalone via navigator.standalone (iOS)", () => {
  const nav = g.navigator;
  stub("navigator", { standalone: true });
  assert.equal(isStandalone(), true);
  stub("navigator", nav);
});
