<p align="center">
  <img src="docs/readme/hero.svg" alt="Spindle: turn a raw idea into a scoped, researched, built and judged prototype" width="100%">
</p>

<p align="center">
  <b>One sentence in. A scoped, researched, designed, built and honestly judged prototype out.</b><br>
  <sub>A team of AI agents on one canvas, for innovation teams deciding which ideas deserve a real budget.</sub>
</p>

<p align="center">
  <a href="#why-spindle">Why Spindle</a> ·
  <a href="#the-pipeline">The pipeline</a> ·
  <a href="#a-look-inside">A look inside</a> ·
  <a href="#what-you-walk-away-with">What you walk away with</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#under-the-hood">Under the hood</a> ·
  <a href="#running-it">Running it</a>
</p>

---

## Why Spindle

Most ideas die in a slide deck, or get built before anyone checks the market. Spindle runs the full path from idea to evidence: scope, market sizing, design, a working prototype, and a verdict. Every step stays visible, and you can edit any of it.

<table>
  <tr>
    <td width="33%" valign="top">
      <h3>🔎 Evidence, not vibes</h3>
      Market sizes are worked two ways, top-down and bottom-up. Every input carries a source and a grade. Anything the agents can't trace is marked <i>unverified</i>.
    </td>
    <td width="33%" valign="top">
      <h3>🛠️ Built for real</h3>
      The Coding agent writes and runs the app in a cloud sandbox. You get real files, a live preview, a terminal and a zip download, not a mockup.
    </td>
    <td width="33%" valign="top">
      <h3>⚖️ An honest verdict</h3>
      The Scrutinizer argues both sides with the same rigour: a pitch deck for the idea, a limitations deck against it, and a call of <b>Pursue</b>, <b>Pilot</b>, <b>Rethink</b> or <b>Park</b>.
    </td>
  </tr>
</table>

---

## The pipeline

<img src="docs/readme/pipeline.svg" alt="The Orchestrator runs Project Scoping, Market Research, UX/UI Design, Coding and Scrutinizer in order. Each hands its findings to the next." width="100%">

Give the **Orchestrator** your idea. It adds the agents it needs to the canvas, connects them and runs them one at a time. Each agent reads what the earlier ones found.

| Stage | Job | Hands over |
|---|---|---|
| **Project Scoping** | Goal, non-goals, milestones, feasibility, cost and time to an MVP | `scope.md` and a scope report |
| **Market Research** | TAM / SAM / SOM, competitors, a desirability, viability and feasibility (DVF) scorecard | `research.md` and a research report |
| **UX/UI Design** | User flows, screens and every state, built with the Telstra design system | A clickable `prototype.html` |
| **Coding** | Builds the prototype into a working app and tests it | Source code, a running app and a live preview |
| **Scrutinizer** | Judges the product against the research and the running app | A pitch deck, a limitations deck and a verdict |

Quality is checked along the way. After scoping, coding and scrutiny, an **Evaluator** checks the handoff against its brief. A failed check sends that stage back once with the fixes attached. When the research lands, scoping runs again to revise the brief against the findings.

---

## A look inside

### The canvas

<img src="docs/screenshots/canvas.png" alt="A full pipeline on the canvas: Orchestrator above five connected agents" width="100%">

Each project gets its own canvas. Every card is an agent with one job, and every arrow carries context from one agent to the next. Drag a ready-made agent from the library, or let the Orchestrator lay out the whole team for you. The canvas updates live while it works.

### The workspace

<img src="docs/screenshots/workspace-overview.png" alt="The workspace drawer showing a live deck preview and a card per agent" width="100%">

Pull up the workspace drawer for a view of every agent at once: what each one last wrote, how many files it made, and live previews of the pages they published.

### Chat with any agent

<img src="docs/screenshots/chat.png" alt="Chatting with the Market Research agent, with a competitor table in its reply" width="100%">

Double-click a card to talk to that agent directly. The chips along the top show everything it can see: the agents feeding it, its sandbox and its tools. Replies stream in, tool calls show as they happen, and you can pick the model per agent.

### Tools and skills

<img src="docs/screenshots/tool-shelf.png" alt="The tool shelf: Brave Search, Web Fetch, Context7, Obsidian, Canvas, MCP Server, GitHub, Gmail and skills" width="100%">

<img src="docs/screenshots/inspector.png" alt="The agent inspector listing the Market Research agent's tools, sandbox and inherited context" width="100%">

Drop a tool onto a card to equip it: web search, page fetching, GitHub, Gmail, Obsidian, any MCP server, and 29 **skills** such as *Market Sizing*, *DVF Assessment* and *Source Grading*. Click a card to open the inspector and see its tools, its sandbox and where its context comes from. Set the tool policy to *ask first* if you want to approve each call yourself.

### Agents keep notes

<img src="docs/screenshots/agent-page.png" alt="An agent page with its NOTES.md memory and the shared sandbox file explorer" width="100%">

Each agent keeps a `NOTES.md` of facts that should outlive the conversation: decisions, open questions, bugs it found. The next agent, or the next session, picks up from there.

### Files, code and a real terminal

<img src="docs/screenshots/files-terminal.png" alt="The file explorer, server.js open in the code view, and a terminal in the sandbox" width="100%">

Every agent works in its own folder inside the sandbox. Browse the files as they're written, read the code, open a terminal, and download the whole project as a zip.

---

## What you walk away with

One idea, run end to end. These came out of a single run for a smart plant coaster.

<table>
  <tr>
    <td width="50%" valign="top">
      <img src="docs/screenshots/pitch-deck.png" alt="Pitch deck slide: one screen, one instruction, twelve states">
      <p align="center"><b>The pitch deck</b><br><sub>The strongest honest case for the idea. Each claim is tagged with its source.</sub></p>
    </td>
    <td width="50%" valign="top">
      <img src="docs/screenshots/limitations-deck.png" alt="Limitations deck slide: everything on the screen comes from one file that pretends to be firmware">
      <p align="center"><b>The limitations deck</b><br><sub>The same evidence read the other way, ending in a verdict.</sub></p>
    </td>
  </tr>
  <tr>
    <td colspan="2">
      <img src="docs/screenshots/built-app.png" alt="The working plant coaster status app built by the Coding agent">
      <p align="center"><b>The working app</b><br><sub>Built and running in the sandbox, on simulated data, with tests.</sub></p>
    </td>
  </tr>
</table>

---

## How it works

### Arrows share what an agent knows

<img src="docs/readme/context.svg" alt="How context moves along an arrow" width="100%">

An arrow keeps a short **summary** of the source agent's conversation. Before the agent at the other end replies, it reads that summary, so it answers as if it had been in the room.

When the source agent keeps talking, the summary falls behind and the arrow turns orange. It never refreshes on its own, because that would spend money on every message. You choose when to refresh.

### One turn, start to finish

<img src="docs/readme/turn.svg" alt="The path of one message" width="100%">

The agent reads its arrows, then starts answering. Partway through it may call a tool: a search, a page fetch, a file in its sandbox. The result goes back to the agent and it keeps writing, sometimes several times in one reply.

If the agent is set to *ask first*, it pauses at the tool and waits for your OK. That pause is saved in the database, so you can approve it minutes later, even after a server restart, and it picks up where it left off.

Runs survive a redeploy too. Each model step is checkpointed, and the next backend to come up picks up any run that stopped heartbeating and carries on. A pipeline continues with its next agent.

### Built in

- **Secret keys stay secret.** API keys live encrypted in Supabase Vault. Agents never see them and nobody can read them back.
- **Your projects are yours.** Postgres row-level security filters every query by owner. Someone else's project returns "not found", as if it doesn't exist.
- **A broken tool doesn't break the chat.** A misconfigured tool is reported as unavailable and the agent carries on without it.
- **Bad keys show up early.** Tools are checked when you save them, so a typo turns the card red before a conversation starts.
- **Spend is tracked.** Token usage is recorded per project, per user and per model.
- **You hear when a run finishes.** A bell lists finished, failed and waiting-for-approval turns, and the installed app sends a push notification (iPad Home Screen included).

---

## Under the hood

<table>
  <tr>
    <td><b>Frontend</b></td>
    <td>Next.js 16, React 19, Tailwind</td>
  </tr>
  <tr>
    <td><b>Backend</b></td>
    <td>FastAPI on Python 3.12, Pydantic AI for the agents, Postgres checkpoints for durable runs</td>
  </tr>
  <tr>
    <td><b>Data and auth</b></td>
    <td>Supabase: Postgres with row-level security, Realtime, Vault and Google sign-in</td>
  </tr>
  <tr>
    <td><b>Sandboxes</b></td>
    <td>E2B cloud sandboxes for files, terminals and live previews</td>
  </tr>
  <tr>
    <td><b>Hosting</b></td>
    <td>Railway</td>
  </tr>
</table>

For every diagram in detail, open [docs/SYSTEM_GUIDE.html](docs/SYSTEM_GUIDE.html) in a browser. The HTTP API is documented in [docs/API.md](docs/API.md). The database ERD is in [docs/erd](docs/erd) (PNG, SVG and Mermaid source).

---

## Running it

### You need

- Python 3.12 and Node 22.18 or newer
- Docker, for a local Supabase (`npx supabase start`). Not needed for hosted only.
- A Supabase project
- A model key: `OLLAMA_API_KEY` (default provider) or `GEMINI_API_KEY` with `LLM_PROVIDER=gemini`
- An [E2B](https://e2b.dev) key for sandboxes. Without it, agents run but can't write files, run code or show previews.

Everything else (Brave, Context7, Google OAuth, Web Push, Jev) is optional. Each is described in [backend/.env.example](backend/.env.example).

### 1. Database

Install the [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started), or use `npx supabase`. Run these from `backend/`.

```
npx supabase start                        # local: starts Postgres and applies the migrations
npx supabase login                        # hosted: sign in to the CLI,
npx supabase link --project-ref <ref>     # link the project,
npx supabase db push                      # then apply the migrations
```

See [backend/supabase/README.md](backend/supabase/README.md) for the schema and a tenant isolation check.

Google sign-in, hosted only (local is email/password: `config.toml` has no Google provider):

- Create a Google Cloud OAuth client and enter its id and secret in the Supabase Google provider.
- Add `https://<ref>.supabase.co/auth/v1/callback` as an authorized redirect URI in Google.
- Add the frontend URL under **Authentication > URL Configuration**, and set the backend's `OAUTH_REDIRECT_URL`.

### 2. Backend

From the repo root:

```
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then fill it in
uvicorn app.main:app --reload --port 8000
```

`http://localhost:8000/health` should answer.

### 3. Frontend

```
cd frontend
npm install
cp .env.example .env.local      # then fill it in
npm run dev
```

Open `http://localhost:3000`. More in [frontend/README.md](frontend/README.md).

To run both from the repo root instead: `npm install`, then `npm run dev` with the backend's virtualenv active.

### Deploying

The backend and an nginx proxy each deploy to Railway from their own `Dockerfile` and `railway.json` (`backend/`, `nginx/`), with health checks on `/health`. nginx sits in front of the backend with per-IP rate limits, a small response cache and the terminal WebSocket upgrade. Set its `BACKEND_HOST` to the backend's private address (`<service>.railway.internal:<port>`). `docker compose up --build` runs the same pair locally from `backend/.env`.

The frontend is a standard Next.js app: `npm run build`, then `npm start`, with the same `NEXT_PUBLIC_*` variables set at build time.

---

<p align="center">
  <img src="frontend/public/murud-logo.svg" alt="muru-D" height="40">
</p>

<p align="center">
  <sub>Built by Team 2 for the Telstra muru-D program with RMIT University.</sub>
</p>
