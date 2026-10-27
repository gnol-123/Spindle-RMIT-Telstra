# Supabase migrations

Plain SQL in Supabase CLI format. `config.toml` sets the local project
(`spindle`). Files apply in filename order.

| File | What it does |
|---|---|
| `20261027000001_schema.sql` | Extensions, `set_updated_at`, all 16 tables, indexes, triggers and trigger functions. |
| `20261027000002_functions.sql` | Vault secret RPCs and Web Push RPCs, with grants. |
| `20261027000003_security.sql` | RLS enable/force and every policy. |
| `20261027000004_realtime_storage.sql` | Realtime publication (`nodes`, `edges`, `notifications`) and the private `project-previews` bucket. |
| `20261027000005_catalog.sql` | Generated `agent_types`, `tool_types` and `tool_presets` rows. |

## Applying

Run from `backend/`. Use the Supabase CLI or `npx supabase`. Local needs Docker.

Local:

```
npx supabase start       # starts the stack and applies the migrations
npx supabase db reset    # rebuild from scratch
```

Hosted:

```
npx supabase login
npx supabase link --project-ref <ref>
npx supabase db push
```

Values for the env files: locally, `npx supabase status` prints the API URL,
anon/publishable key and service_role/secret key. They map to `SUPABASE_URL`,
`SUPABASE_KEY` and `SUPABASE_SERVICE_KEY` (backend) and
`NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` (frontend).
Hosted values are under Project Settings > API.

Hosted prerequisites for Google sign-in (local has no Google provider, so
local is email/password only):

- Create a Google Cloud OAuth client; enter its id and secret in the Supabase Google provider.
- Add `https://<ref>.supabase.co/auth/v1/callback` as an authorized redirect URI in Google.
- Add the frontend URL under Authentication > URL Configuration, and set the backend's `OAUTH_REDIRECT_URL`.

The auth settings in `config.toml` do not push. Hosted requires email
confirmation by default, while `config.toml` has `enable_confirmations = false`.

History: the old 23-file chain and `apply.py` are in `backend/migrations_archive/`.

## Verify tenant isolation

Nothing in CI exercises the policies against a real database, so check them
by hand at least once, and again after editing `20261027000003_security.sql`.

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

Write a new migration with `npx supabase migration new <name>` and put the insert in it:

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

Same idea, in its own migration. `config_schema` drives the form the user sees when they click the
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
  `get_node_secret` (`20261027000002_functions.sql`). Values never sit on the `nodes` row.
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

## Known oddities

- `previews` has no `owner_id`; its RLS goes through the project.
- `previews.agent_node_id` has no foreign key.
