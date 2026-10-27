# Migrations

Plain SQL. Order matters: `rls.sql` policies reference tables that `init.sql`
creates, so run it second.

| File | What it does |
|---|---|
| `init.sql` | Tables, indexes, triggers, and the seeded catalogs. Run first. |
| `rls.sql` | Row Level Security policies. Run second. |
| `tools.sql` | Tool call audit, the approval pause, and vault-backed secrets. Run third. |
| `oauth.sql` | OAuth token storage for tool nodes that connect rather than take a key. Run fourth. |
| `environments.sql` | Environment edge validation, one scratch space per project, and backfills. Run fifth. |
| `defaults.sql` | Tool presets library, `agent_types.default_presets`, `web_fetch`, and the seeded skills. Run sixth. |
| `parity.sql` | Context7 type and preset, ten process skills, agent default lists. Run seventh. |
| `provider.sql` | Switches the default model provider to Ollama, adds the per-node `model` override. Run eighth. |
| `usage.sql` | Token usage columns on messages and the usage_totals rollup. Run ninth. |
| `orchestrator.sql` | Canvas tool type and preset, the orchestrator agent type and its prompt. Run tenth. |
| `turns.sql` | Progressive turn persistence: status constraints, `messages.sender_node_id`, and realtime publication for nodes. Run eleventh. |
| `pitch.sql` | Scrutinizer and evaluator agent types, pitch scrutiny skill preset. Run twelfth. |
| `runtime.sql` | `messages.heartbeat_at` for stale turn detection, per agent type `request_limit`. Run thirteenth. |
| `design_skills.sql` | Design Taste, Impeccable and Emil Design Engineering skill presets, wired onto UX/UI and Scrutinizer. Run fourteenth. |
| `previews.sql` | `previews` table with RLS (agent-published previews, thumbnail path) and the private `project-previews` bucket. Run fifteenth. |
| `canvas_snapshot.sql` | `projects.canvas_snapshot_at`, set when a canvas screenshot is uploaded. Run sixteenth. |
| `realtime_edges.sql` | Adds `edges` to the realtime publication. Run seventeenth. |
| `idea_assessment.sql` | Market Sizing, DVF Assessment and Visual Report skills; new Market Research prompt and defaults, backfilled. Run eighteenth. |
| `telstra_design.sql` | Telstra Design skill and prompt for the UX/UI agent, backfilled. Run nineteenth. |
| `scope_report.sql` | Scope Report skill, reworked Scoping Brief, new Project Scoping prompt and defaults, backfilled. Run twentieth. |
| `durability.sql` | `messages.parent_message_id`, `resume_count` and `cancel_requested`, and the service-only `turn_checkpoints` table (history plus replayed approvals) for resuming turns after a redeploy. Run twenty-first. |
| `notifications.sql` | `notifications` (bell, filled by a trigger on assistant status changes), `push_subscriptions` and the service-only `push_deliveries` outbox, the `upsert_push_subscription` and `claim_push_batch` RPCs, and realtime for `notifications`. Run twenty-second. |
| `realtime_trim.sql` | Unpublishes `messages` and `tool_calls` from realtime (nothing subscribes; turns stream over SSE). Run twenty-third. |
| `apply.py` | Runs them all, in order, in one transaction. |

## Applying

### Script

From `backend/`, with `DBOS_DATABASE_URL` set in `.env` (the Supabase session
pooler connection string; the name outlived DBOS) and `psycopg` installed from
`requirements-dev.txt`:

```
python migrations/apply.py --dry-run   # apply, report, then roll back
python migrations/apply.py             # apply for real
```

Every file runs in one transaction (the script strips each file's own
`begin`/`commit`), so a failure part-way rolls the whole thing back rather than
leaving the schema half-built. Use `--dry-run` first to see what you would get.

### By hand

Or paste them into the Supabase **SQL Editor** in the order above. Each file
wraps itself in `begin`/`commit`. Run each and confirm success before the next.

Either way, every file is safe to re-run: they use `if not exists`,
`create or replace`, `drop policy if exists`, and `on conflict do nothing`, so
applying twice is a no-op rather than an error.

Schema and policies are separate files on purpose. Policies get iterated on far
more often than the schema, and a typo in a policy should not roll back your
tables.

## After applying: verify tenant isolation

Nothing in CI exercises the policies against a real database, so check them
by hand at least once, and again after editing `rls.sql`.

Substitute two real ids from `select id from auth.users limit 2`:

```sql
-- Impersonate user A exactly as PostgREST does.
select set_config('request.jwt.claims', '{"sub":"<USER-A-UUID>","role":"authenticated"}', true);
select set_config('role', 'authenticated', true);

select count(*) from projects;   -- only A's rows
select count(*) from messages;   -- only A's rows

-- Now become user B. Both counts must exclude everything owned by A.
reset role;
select set_config('request.jwt.claims', '{"sub":"<USER-B-UUID>","role":"authenticated"}', true);
select set_config('role', 'authenticated', true);

select count(*) from projects;   -- zero of A's rows
```

Wrap the whole check in `begin; ... rollback;` if you seed test rows.

## The shape of it

A project is a **canvas**: `nodes` (boxes) joined by `edges` (arrows).

```
projects
   └── nodes ──< edges >── nodes
         │  kind: agent | environment | tool
         │
         ├── node_secrets ──> vault.secrets
         ├── previews (environment nodes)
         └── conversations (agent nodes only)
               ├──< messages ──o turn_checkpoints
               │      └──< notifications ──< push_deliveries >── push_subscriptions
               └──< tool_calls

projects ──< usage_totals (per owner, per model; rolled up from messages)
tool_types ──< tool_presets (copied into nodes.config on create)
```

`agent_types` and `tool_types` are **catalogs of templates**. A node is an
*instance* provisioned from one, so a project can hold two "Market Research"
boxes as separate nodes with separate conversations. That is what makes teams
of agents possible.

Edges do not execute a pipeline. They make context and capability available to
whichever agent the user is chatting with:

| Edge kind | Direction | Carries |
|---|---|---|
| `context` | agent → agent | A summary of the source conversation, plus a retrieval tool |
| `tool` | tool → agent | A callable capability and its credentials |
| `environment` | environment → agent | An execution target |

### Stale context

A `context` edge stores `summary` and `summarised_through_seq`. When the source
conversation grows past that seq the edge is **stale**, and the UI colours it
differently until the user refreshes it. Nothing regenerates automatically, so
there are no background LLM calls and the user can see when a downstream agent
is working from older information.

Staleness compares seq to seq, over `complete` rows only. Not
`conversations.message_count`: that counter includes `running`, `cancelled` and
`failed` rows, whose text was never summarised, so an edge would read stale
forever after one cancelled turn.

```sql
select e.id,
       e.summarised_through_seq < coalesce(
         (select max(m.seq) from messages m
          where m.conversation_id = c.id and m.status = 'complete'), 0
       ) as is_stale
from edges e
join nodes n         on n.id = e.source_node_id
join conversations c on c.node_id = n.id
where e.kind = 'context';
```

## Adding an agent type

An insert, not a deploy:

```sql
insert into public.agent_types
  (slug, name, description, system_prompt, model, sort_order, default_presets)
values ('legal_review', 'Legal Review', 'Flags contractual risk.',
        'You are a contracts analyst...', 'deepseek-v4.1-flash', 40,
        array['web_fetch', 'source_grading']);
```

The slug must match `^[a-z][a-z0-9_]{1,48}[a-z0-9]$`. `default_presets` lists
`tool_presets` slugs wired onto each new node; an unknown slug is skipped.
`request_limit` caps model requests per turn (null uses the backend setting).
A node can override `model` on its own row.

**Retiring one is `is_active = false`, never `DELETE`.** Nodes reference the
catalogs with `on delete restrict` precisely so that removing a template cannot
cascade away user transcripts.

## Adding a tool type

Same idea. `config_schema` drives the form the user sees when they click the
box; `secret_fields` names the values that go to Vault (via `node_secrets`) and
are never returned by the API. `auth_kind` is `token` (password field) or
`oauth2` (Connect button). Ready-made configurations of a type go in
`tool_presets`.

```sql
insert into public.tool_types (slug, name, description, config_schema, secret_fields)
values ('github', 'GitHub', 'Read and write repositories.',
        '{"fields": [{"key": "token", "label": "Access token", "type": "password",
                      "required": true}]}'::jsonb,
        array['token']);
```

## Notes

- Everything lives in `public`.
- **Tool credentials live in Supabase Vault.** `node_secrets` holds only the
  key name and a `vault_secret_id`; read and write through `set_node_secret` /
  `get_node_secret` (`tools.sql`). Values never sit on the `nodes` row.
- **Two clients, two trust levels.** User requests go through `SUPABASE_KEY`
  (publishable/anon) plus the user's JWT, so RLS applies. The service client
  (`SUPABASE_SERVICE_KEY`) is `BYPASSRLS` and is used for Vault, turn recovery,
  the push outbox and previews. The backend filters by owner on every query
  either way.
- **Service-only tables** (`turn_checkpoints`, `push_deliveries`) have RLS
  forced on with no client policies, so only the service client reaches them.
- **Realtime** publishes `nodes`, `edges` and `notifications`. Turns stream
  over SSE, so `messages` and `tool_calls` are not published.
- `owner_id` on every tenant table is set by trigger from the parent row,
  never by the client.
