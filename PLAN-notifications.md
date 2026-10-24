# Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Notify the account owner when any agent turn ends as complete, failed or awaiting approval: iPad Web Push when outside the app, a bell with a red dot inside it.

**Architecture:** A Postgres trigger on `messages` writes `notifications` rows in the same transaction as the status change. The bell reads them over Supabase Realtime. A backend outbox claims (notification, device) pairs through a `security definer` RPC and sends Web Push with `pywebpush`, deferring devices that report themselves visible.

**Tech Stack:** Supabase Postgres (plpgsql, RLS, Realtime), FastAPI + supabase-py, `pywebpush`, Next.js 16 App Router, `@supabase/realtime-js`, a plain service worker.

**Spec:** `docs/superpowers/specs/2026-10-24-notifications-design.md`

## In plain English

1. **Database (Task 1).** A new migration adds three tables and a trigger. Whenever an agent's reply row changes to finished, failed or waiting for approval, the trigger writes a notification. Leaving "waiting for approval" marks the old approval notification read. A database function hands out pushes to send, one per notification per device, so two backends never double-send.
2. **Backend routes (Task 2).** The app can list notifications, mark them read, register an iPad for push, report "I'm on screen", and unregister.
3. **Push sender (Task 3).** Right after a turn ends, and every 10 seconds as a safety net, the backend asks the database for pushes to send and delivers them. Dead devices get removed.
4. **Frontend data (Task 4).** Types, API calls, grouping by project, and a live Realtime feed.
5. **Installable app (Task 5).** Manifest, service worker, the enable-push flow, and the "I'm on screen" ping.
6. **Bell (Task 6).** Top-right bell on the projects screen and the canvas, red dot, a panel grouped by project, and the read rules.
7. **Review and iPad check (Task 7).**

## Global Constraints

- Never open, read or edit any `.env` file. VAPID keys are added by the user. Name the variables only: `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_SUBJECT`.
- The `.env` DB is prod. Never apply a migration, run `apply.py` (dry run included), or run anything live against it without the user's explicit OK in that moment.
- No git writes of any kind. The user commits. There are no commit steps in this plan.
- `backend/tests/` is gitignored. Write tests there to verify locally; they ship nowhere.
- Notifying statuses: `complete`, `failed`, `awaiting_approval`. `cancelled` never notifies.
- Push window: notifications older than 1 hour are never pushed.
- Presence: ping every 30 s, `visible_until = now() + 60 s`.
- Outbox loop interval: 10 s.
- Next.js here has breaking changes. Read `frontend/node_modules/next/dist/docs/01-app/02-guides/progressive-web-apps.md` and `.../03-file-conventions/01-metadata/manifest.md` before Task 5.
- Comments: short, describe not explain, matching the surrounding code. No em dashes anywhere.
- Push sender needs `SUPABASE_SERVICE_KEY` and all three VAPID settings. Missing any: push is off, bell still works, one warning logged.

## Review Focus

1. **A trigger error must never fail the turn's status write.** If the notification insert raises (bad join, constraint), the `messages` update must still commit. Test in Task 1 (exception block).
2. **Same device, different account.** User A logs out, user B logs in on the same iPad: the endpoint must move to B, and A must stop getting B's pushes. Tests in Task 1 (RPC) and Task 5 (unsubscribe on logout).
3. **Turning push on doesn't flood old notifications.** A device subscribed now must not receive pushes for notifications created before it subscribed. Test in Task 1 (claim filter).
4. **Notification for the project that's open.** Arrives read, no dot, no push, even on the fast path. Tests in Task 4 (`unreadElsewhere`) and Task 6 (mark on receipt).
5. **Push service rejects with 404/410.** Subscription deleted, no exception escapes the loop, other deliveries in the batch still go out. Test in Task 3.

---

### Task 1: Migration `notifications.sql`

Model: opus.

**Files:**
- Create: `backend/migrations/notifications.sql`
- Modify: `backend/migrations/apply.py` (append `"notifications.sql"` after `"durability.sql"` in `MIGRATIONS`)
- Modify: `backend/migrations/README.md` (table row, "Run twenty-second.")
- Test: `backend/tests/sql_notifications_check.py` (rollback-only, run only with user OK)

**Interfaces:**
- Produces tables:
  - `notifications(id uuid pk, owner_id, project_id, node_id, message_id, status text, node_name text, project_name text, nested boolean, excerpt text null, read_at timestamptz null, created_at timestamptz default now())`. FKs cascade on delete. Indexes `(owner_id, created_at desc)`, `(message_id)`, and `(created_at) where read_at is null`.
  - `push_subscriptions(id uuid pk, owner_id, endpoint text unique, p256dh text, auth text, user_agent text null, visible_until timestamptz null, created_at, updated_at)`.
  - `push_deliveries(notification_id, subscription_id, sent_at timestamptz default now(), primary key (notification_id, subscription_id))`, both FKs cascade.
- Produces RPCs:
  - `upsert_push_subscription(p_endpoint text, p_p256dh text, p_auth text, p_user_agent text) returns uuid`: `security definer`, insert or on conflict (endpoint) set owner to `auth.uid()` and refresh keys. Granted to `authenticated`. Raises if `auth.uid()` is null.
  - `claim_push_batch(p_limit int default 50) returns table(notification_id uuid, subscription_id uuid, endpoint text, p256dh text, auth text, status text, node_name text, project_name text, project_id uuid, nested boolean, excerpt text)`: `security definer`. Execute revoked from `public`, `anon`, `authenticated`; granted to `service_role`.

- [ ] **Step 1: Write the check script** `backend/tests/sql_notifications_check.py`

psycopg, one transaction, `ROLLBACK` at the end no matter what. Reads the DSN the same way `apply.py` does. Executes `notifications.sql` without its own `begin;`/`commit;` (strip them like `apply.py` does), seeds an auth user, project, agent node, conversation and assistant message (status `running`), then asserts:

```python
# running -> complete: one notification, status complete, excerpt from content
# complete -> complete (re-write): still one
# second message: running -> awaiting_approval -> running -> awaiting_approval -> running -> complete
#   => 3 rows for it; both approval rows have read_at set; complete row read_at null
# running -> cancelled: no row
# user row (role 'user') updated: no row
# nested: message with parent_message_id set -> nested is true
# trigger failure is swallowed: temporarily make the insert fail
#   (e.g. `alter table notifications add constraint t_fail check (false) not valid`
#    inside a savepoint), update status, assert the messages row still updated
# claim_push_batch as service_role:
#   subscription created AFTER notification -> not claimed (Review Focus 3)
#   subscription created before, visible_until = now()+60s -> not claimed
#   same, visible_until null -> claimed once; second call -> nothing
#   notification read_at set -> not claimed
#   notification created_at = now() - 61 min -> not claimed
# upsert_push_subscription as user A then as user B (set request.jwt.claims + role authenticated):
#   one row, owner_id == B (Review Focus 2)
# RLS as authenticated user B: select sees only B's notifications; update of
#   any column other than read_at is rejected
```

- [ ] **Step 2: Write `notifications.sql`**

`begin; ... commit;`, re-runnable (`if not exists`, `create or replace`, `drop trigger if exists`, `do $$ ... $$` guards like `realtime_edges.sql`). Header comment: "Apply after durability.sql. Re-runnable."

Trigger `messages_notify_trg`: `after update of status on public.messages for each row execute function public.messages_notify()`. Function is `security definer`, `set search_path = public, pg_temp`. Body:

```sql
if new.role <> 'assistant' or new.status is not distinct from old.status then return new; end if;
if old.status = 'awaiting_approval' then
  update notifications set read_at = now()
   where message_id = new.id and status = 'awaiting_approval' and read_at is null;
end if;
if new.status in ('complete', 'failed', 'awaiting_approval') then
  begin
    insert into notifications (...) select ... from conversations c
      join nodes n on n.id = c.node_id join projects p on p.id = c.project_id
     where c.id = new.conversation_id;
  exception when others then
    raise warning 'notification insert failed for message %: %', new.id, sqlerrm;
  end;
end if;
return new;
```

`excerpt`: complete → `left(regexp_replace(new.content, '\s+', ' ', 'g'), 140)`; failed → `left(new.error, 140)`; approval → null. `nested` = `new.parent_message_id is not null`.

RLS: enable + force on all three tables. `notifications`: select policy `owner_id = auth.uid()`; update policy same `using`/`with check`; `revoke update on notifications from authenticated; grant update (read_at) on notifications to authenticated;`. `push_subscriptions`: select, update and delete policies `owner_id = auth.uid()`, no insert policy (RPC only), and column grant `update (visible_until, updated_at)`. `push_deliveries`: no policies.

Realtime: add `notifications` to `supabase_realtime` with the guard pattern from `realtime_edges.sql`.

`claim_push_batch` body: one `with pairs as (select ... where n.read_at is null and n.created_at > now() - interval '1 hour' and n.created_at >= s.created_at and (s.visible_until is null or s.visible_until < now()) and not exists (select 1 from push_deliveries d where ...) order by n.created_at limit p_limit), claimed as (insert into push_deliveries select ... from pairs on conflict do nothing returning *) select ... from claimed join notifications ... join push_subscriptions ...`.

- [ ] **Step 3: Ask the user for OK, then run the check**

Say: "The check runs `notifications.sql` inside a transaction against the prod DB and rolls it back. OK to run?" Only on yes:
Run: `cd backend && python tests/sql_notifications_check.py`
Expected: every assertion prints `ok`, last line `rolled back`.

- [ ] **Step 4: Update `apply.py` and `README.md`**

---

### Task 2: Notification repository and routes

Model: sonnet.

**Files:**
- Create: `backend/app/repositories/notification_repo.py`
- Create: `backend/app/routers/notifications.py`
- Modify: `backend/app/routers/deps.py` (add `NotificationRepo`)
- Modify: `backend/app/main.py` (include router)
- Modify: `backend/app/config.py` (`vapid_private_key: str = ""`, `vapid_public_key: str = ""`, `vapid_subject: str = ""`, comment: empty disables push)
- Test: `backend/tests/test_notifications_api.py`

**Interfaces:**
- Consumes: Task 1 tables and `upsert_push_subscription`.
- Produces:
  - `NotificationRow` frozen dataclass: `id, project_id, node_id, message_id, status, node_name, project_name, nested, excerpt, read_at, created_at`.
  - `NotificationRepository(client, uid)`: `list_recent(limit: int) -> list[NotificationRow]` (newest first); `mark_read(project_id: str | None) -> int` (sets `read_at` where null); `upsert_subscription(endpoint, p256dh, auth, user_agent) -> str` (calls the RPC); `set_visible(endpoint: str, visible: bool) -> None` (`visible_until = now + 60 s` or null); `delete_subscription(endpoint: str) -> None`.
  - Routes (all `auth` required except `/push/key`):
    - `GET /notifications?limit=` (1..200, default 100) → `list[NotificationResponse]`
    - `POST /notifications/read` body `{project_id: UUID | None}` → `{updated: int}`
    - `GET /push/key` → `{public_key: str | None}` (None when push is off)
    - `POST /push/subscriptions` body `{endpoint: HttpUrl, keys: {p256dh: str, auth: str}}` (browser `PushSubscription.toJSON()` shape) → 204
    - `PATCH /push/subscriptions` body `{endpoint, visible: bool}` → 204
    - `DELETE /push/subscriptions` body `{endpoint}` → 204
  - `push_enabled() -> bool` in `app/config.py` or the router: service key and all three VAPID values set. Task 3 imports it.

- [ ] **Step 1: Write failing tests** with a fake PostgREST client (pattern: `tests/test_preview_repo.py`) and `app.dependency_overrides` for auth and repo:

```python
def test_list_newest_first_and_limit_bounds(): ...       # limit=0 and 201 -> 422
def test_mark_read_scoped_to_project(): ...              # only that project's unread rows
def test_mark_read_all(): ...
def test_push_key_none_when_disabled(): ...
def test_subscribe_calls_rpc_with_keys(): ...            # rpc name and params exact
def test_presence_sets_visible_until_60s(): ...          # within 2 s of now+60
def test_presence_false_clears(): ...
def test_routes_require_auth(): ...                      # 401 without bearer, except /push/key
```

- [ ] **Step 2: Run** `cd backend && pytest tests/test_notifications_api.py -v`. Expected: FAIL (import errors).
- [ ] **Step 3: Implement** repo, routes, deps, config, router include. Follow `preview_repo.py` and `routers/projects.py` style. Repository calls run via `anyio.to_thread.run_sync`, as in other routers.
- [ ] **Step 4: Run** the same command plus `ruff check app`. Expected: PASS, no lint errors.

---

### Task 3: Push sender

Model: opus.

**Files:**
- Create: `backend/app/services/push.py`
- Modify: `backend/requirements.txt` (`pywebpush==<latest 2.x, exact pin>`. Check the version with `pip index versions pywebpush`, then run `pip-audit -r requirements.txt`.)
- Modify: `backend/app/workflows.py:594-665` (`_finalise`: kick after the status write)
- Modify: `backend/app/main.py` (start `push_loop` on startup beside `_start_recovery`, cancel it in `_join_detached_turns`)
- Test: `backend/tests/test_push_sender.py`

**Interfaces:**
- Consumes: `claim_push_batch` (Task 1), `push_enabled()` (Task 2), `get_service_client()`, `runs.track_finaliser`.
- Produces:
  - `payload_for(row: dict) -> dict`: `{"title": node_name, "body": f"{project_name} · {verb}", "url": f"/?project={project_id}", "tag": notification_id}` where verb is `finished` / `failed` / `needs your approval`. Nested appends ` (orchestrator)` to the title. Excerpt, if any, goes on a second body line.
  - `send_batch(client) -> int`: one `claim_push_batch` RPC, then one `webpush(...)` per row in `to_thread`. Returns rows sent. On `WebPushException` with status 404/410, delete that subscription by id. Any other exception: log, continue.
  - `kick() -> None`: no-op unless `push_enabled()`. Else schedules `send_batch(get_service_client())` as a task tracked with `runs.track_finaliser`. Never raises.
  - `push_loop() -> None`: forever, `send_batch` then `asyncio.sleep(10)`, logging exceptions, like `recovery_loop`.

- [ ] **Step 1: Write failing tests** (monkeypatch `pywebpush.webpush` and the client):

```python
def test_payload_complete(): assert payload_for(row(status="complete"))["body"].startswith("Proj · finished")
def test_payload_approval_and_nested(): ...   # "needs your approval", title ends " (orchestrator)"
def test_payload_url_and_tag(): ...           # "/?project=<id>", tag == notification_id
def test_send_batch_410_deletes_subscription_and_continues(): ...   # Review Focus 5: 3 rows, 2nd raises 410 -> 2 sent, 1 delete
def test_send_batch_other_error_keeps_going(): ...
def test_kick_noop_when_disabled(): ...
def test_finalise_kicks_once(): ...           # patch push.kick, run _finalise with a fake repo, assert called once
```

- [ ] **Step 2: Run** `pytest tests/test_push_sender.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** `webpush(subscription_info={"endpoint", "keys": {"p256dh", "auth"}}, data=json.dumps(payload), vapid_private_key=settings.vapid_private_key, vapid_claims={"sub": settings.vapid_subject}, ttl=3600)`. In `_finalise`, call `push.kick()` once, just before `return message` (import inside the function, like the other lazy imports there).
- [ ] **Step 4: Run** the push tests plus the existing turn tests: `pytest tests/test_push_sender.py tests/test_turn_persistence.py tests/test_stream_detached.py -v`. Expected: PASS.
- [ ] **Step 5: Key-generation note.** Add a short "Push notifications" section to `backend/migrations/README.md` or `docs/API.md` with a one-off `python -c` that uses `py_vapid` (installed with pywebpush) to print a base64url private key and an uncompressed-point public key. Include the three variable names. Do not write any env file.

---

### Task 4: Frontend data layer

Model: sonnet.

**Files:**
- Modify: `frontend/src/lib/types.ts` (`AppNotification`)
- Modify: `frontend/src/lib/api.ts` (`listNotifications`, `markNotificationsRead`, `getPushKey`, `savePushSubscription`, `setPushVisible`, `deletePushSubscription`)
- Create: `frontend/src/lib/notifications.ts`
- Modify: `frontend/src/lib/realtime.ts` (extract the client and auth join from `subscribeCanvas` into `openRealtime(getToken)`; add `subscribeNotifications`)
- Test: `frontend/src/lib/notifications.test.ts` (node:test, same style as `realtime.test.ts`)

**Interfaces:**
- Produces:
  - `AppNotification = { id, project_id, node_id, message_id, status: "complete" | "failed" | "awaiting_approval", node_name, project_name, nested: boolean, excerpt: string | null, read_at: string | null, created_at: string }`
  - `groupByProject(list: AppNotification[]): { projectId: string; projectName: string; items: AppNotification[] }[]`: groups ordered by newest item, items newest first.
  - `unreadElsewhere(list, activeProjectId: string | null): boolean`
  - `upsert(list, row): AppNotification[]`: replace by id or prepend, capped at 100.
  - `subscribeNotifications(userId: string, getToken, onRow: (row: AppNotification) => void, onLive: (live: boolean) => void): () => void`: INSERT and UPDATE on `notifications` filtered `owner_id=eq.<userId>`.

- [ ] **Step 1: Write failing tests**

```ts
test("groupByProject orders groups by newest item", ...)
test("unreadElsewhere ignores the open project", ...)          // Review Focus 4
test("unreadElsewhere false when all read", ...)
test("upsert replaces by id (read_at update from another device)", ...)
test("upsert caps at 100", ...)
```

- [ ] **Step 2: Run** `cd frontend && node --test src/lib/notifications.test.ts`. Expected: FAIL.
- [ ] **Step 3: Implement.** Refactoring `subscribeCanvas` must not change its behavior.
- [ ] **Step 4: Run** `node --test src/lib/notifications.test.ts src/lib/realtime.test.ts` and `npx tsc --noEmit`. Expected: PASS, no type errors.

---

### Task 5: Installable app and push subscription

Model: opus.

**Files:**
- Create: `frontend/src/app/manifest.ts` (the App Router file convention auto-links it, so it replaces the spec's `public/manifest.webmanifest`)
- Create: `frontend/public/sw.js`
- Modify: `frontend/next.config.mjs` (`headers()` for `/sw.js`: `Cache-Control: no-cache, no-store, must-revalidate`, `Content-Type: application/javascript; charset=utf-8`, per the Next PWA guide)
- Create: `frontend/src/lib/push.ts`
- Modify: `frontend/src/lib/api.ts` `logout()` (call `disablePush()` first, best effort)
- Test: `frontend/src/lib/push.test.ts` (pure helpers only)

**Interfaces:**
- Consumes: Task 4 API functions.
- Produces:
  - `manifest()`: `name: "Spindle"`, `short_name: "Spindle"`, `start_url: "/"`, `display: "standalone"`, `background_color` and `theme_color` `"#0A0F24"`, icons `/icon.svg` (`sizes: "any"`) and `/apple-icon.png` (`180x180`).
  - `sw.js`: `push` → `event.waitUntil(self.registration.showNotification(title, { body, tag, data: { url } }))`, always shows. `notificationclick` → close; find a window client, `focus()` then `navigate(url)`, else `clients.openWindow(url)`.
  - `isStandalone(): boolean` (`matchMedia("(display-mode: standalone)")` or `navigator.standalone`)
  - `pushSupported(): boolean` (`serviceWorker`, `PushManager`, `Notification` all present)
  - `urlBase64ToUint8Array(s: string): Uint8Array`
  - `registerServiceWorker(): Promise<ServiceWorkerRegistration | null>` (scope `/`, `updateViaCache: "none"`)
  - `enablePush(): Promise<"enabled" | "denied" | "unavailable">`: must run inside a tap handler. Steps: get key (null → unavailable), `Notification.requestPermission()`, `pushManager.subscribe({ userVisibleOnly: true, applicationServerKey })`, then `savePushSubscription(sub.toJSON())`.
  - `currentPushEndpoint(): Promise<string | null>`
  - `startPresence(): () => void`: when an endpoint exists, ping `setPushVisible(endpoint, true)` now and every 30 s while visible; on `visibilitychange` to hidden send `visible: false` (`fetch` with `keepalive: true`); returns cleanup.
  - `disablePush(): Promise<void>`: `deletePushSubscription(endpoint)` then `sub.unsubscribe()`. Review Focus 2.

- [ ] **Step 1: Write failing tests** for `urlBase64ToUint8Array` (known vector, padding cases) and `isStandalone` with stubbed `matchMedia` / `navigator`.
- [ ] **Step 2: Run** `node --test src/lib/push.test.ts`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the tests, `npx tsc --noEmit` and `npm run build`. Expected: PASS. The build output lists `/manifest.webmanifest`.

---

### Task 6: Bell and read rules

Model: sonnet.

**Files:**
- Create: `frontend/src/components/NotificationBell.tsx`
- Create: `frontend/src/lib/useNotifications.ts`
- Modify: `frontend/src/app/page.tsx` (keep `userId` from `getMe()`; call `useNotifications`; pass `bell` to both screens; start presence when logged in)
- Modify: `frontend/src/components/ProjectsScreen.tsx` (`bell?: React.ReactNode` rendered in the header before Log out)
- Modify: `frontend/src/components/MeshCanvas.tsx:979-993` (`bell?: React.ReactNode` rendered first in the `ml-auto` group)

**Interfaces:**
- Consumes: Tasks 4 and 5.
- Produces:
  - `useNotifications(userId: string | null, activeProjectId: string | null): { items: AppNotification[]; dot: boolean; markAllRead(): void }`. Initial `listNotifications(100)`, then live via `subscribeNotifications`, merged with `upsert`. Re-fetches on Realtime rejoin. On a new row for `activeProjectId`, calls `markNotificationsRead(activeProjectId)` (Review Focus 4). When `activeProjectId` changes to non-null, marks that project read. `dot = unreadElsewhere(items, activeProjectId)`.
  - `<NotificationBell items dot onOpenPanel onOpenProject(projectId) />`. Bell button with a red dot (`anim-softpulse`, already in globals.css) when `dot`. The panel is a dropdown anchored top right, ~360 px wide, `max-height: 70vh`, scrolls. Groups come from `groupByProject`. Each entry shows the agent name, a status word (Finished / Failed / Needs approval), relative time, "via orchestrator" when nested, and the excerpt in one muted line. Unread entries are emphasized. Opening the panel calls `markAllRead`. Tapping an entry calls `onOpenProject` (page.tsx's `openProject` after looking the project up with `listProjects`) and closes the panel. Empty state: "No notifications yet."
  - Panel footer: if `pushSupported()` and permission isn't granted, show "Turn on iPad notifications" when `isStandalone()` (calls `enablePush` on tap), else "Add Spindle to your Home Screen to get push notifications." Hidden when `getPushKey()` is null.
  - Touch targets at least 44 px. The bell has `aria-label="Notifications"`, and when `dot` is set, `aria-label="Notifications, unread"`.

- [ ] **Step 1: Implement** the hook and components, matching existing header button styles (`border-white/[0.14]`, `rounded-lg`, `text-white/60`).
- [ ] **Step 2: Verify** `npx tsc --noEmit` and `npm run build`. Expected: PASS.
- [ ] **Step 3: Browser check** with the `run` skill or Playwright against `next dev`. Route-guard every non-GET API call except the notification and push routes, per the "browser tests block writes" memory. Check that the bell renders on both screens, the panel groups, the dot logic works, and the layout holds at iPad width (1024x768 and 768x1024). Screenshot both.

---

### Task 7: Whole-branch review and iPad checklist

- [ ] **Step 1:** Run the whole-branch review (superpowers:requesting-code-review) against the spec and the Review Focus list.
- [ ] **Step 2:** Hand the user this manual iPad checklist (needs the deployed HTTPS build, the migration applied, and VAPID keys set by the user):
  1. Safari → Share → Add to Home Screen → open Spindle from the icon → log in with email/password.
  2. Bell → "Turn on iPad notifications" → Allow.
  3. Run an agent on project A, switch to project B: the dot lights up and the entry lands under A.
  4. Run an agent, go to the iPad home screen: a banner appears. Tapping it opens project A.
  5. Run an agent and stay on its project: no dot, no banner.
  6. Trigger an approval pause: "needs your approval" arrives. Approve it: the entry goes read.
