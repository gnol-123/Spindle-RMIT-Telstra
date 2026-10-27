# Spindle (frontend)

Next.js app for the canvas. Log in, pick or create a project, wire agents,
tools and context edges, chat with each agent, browse its sandbox.

## Local development

1. `npm install`
2. `cp .env.example .env.local` and set:
   - `NEXT_PUBLIC_API_URL`: `http://localhost:8000` (default when unset) or the
     deployed Railway URL.
   - `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`: live canvas
     and notification updates over Supabase Realtime. Without them the app
     works but stays offline (refresh to see changes).
3. `npm run dev`
4. Open http://localhost:3000

Supabase only redirects Google sign-in back to allowlisted origins, so keep the
frontend on port 3000 during local dev.

## Tests

```
node --test src/lib/*.test.ts
```

Node's built-in runner, no framework. Needs a Node version that strips TS types
(22.18+).

## Structure

- `src/app/page.tsx`: auth gate, then projects, then canvas. Registers the
  service worker and Web Push.
- `src/app/manifest.ts`, `public/sw.js`: installable app and push handler.
- `src/components/LoginScreen.tsx`, `LoginAnim.tsx`: email/password and Google
  sign-in, with the looping pipeline animation.
- `src/components/ProjectsScreen.tsx`: project list and the "describe an idea"
  composer.
- `src/components/MeshCanvas.tsx`: one project's canvas. Holds chat state per
  node, the palette, the inspector and canvas snapshots.
- `src/components/NodeCard.tsx`, `EdgeLayer.tsx`: draggable cards and the
  arrows between them (amber when a context summary is stale).
- `src/components/Palette.tsx`, `ToolConfigModal.tsx`: agent and tool library;
  dropping a tool on a card creates the node and its `tool` edge.
- `src/components/Inspector.tsx`, `ChatWindow.tsx`: node settings and the
  streaming chat, with tool approvals and cancel.
- `src/components/RunProgress.tsx`: progress strip while agents are running.
- `src/components/NotificationBell.tsx`: in-app bell and push opt-in.
- `src/components/workspace/`: sandbox drawer and agent pages: file tree, code
  view, previews, terminal (xterm.js).
- `src/lib/api.ts`: every backend call, one function per `docs/API.md` endpoint,
  plus token refresh.
- `src/lib/realtime.ts`: Supabase Realtime subscriptions for nodes, edges and
  notifications.
- `src/lib/push.ts`, `notifications.ts`, `useNotifications.ts`: Web Push and
  the bell's state.
- `src/lib/layout.ts`: the canvas "Tidy" layout.
- `src/lib/types.ts`, `auth.ts`: shared types and token storage.
