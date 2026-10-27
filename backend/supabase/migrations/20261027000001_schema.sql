-- Schema: tables, indexes, triggers and their trigger functions.
--
-- A project is a canvas of nodes (boxes) joined by edges (arrows). Nodes are
-- agents, execution environments and tools. Agent nodes each hold a conversation.

-- Kept for older helpers; gen_random_uuid() itself is core since Postgres 13.
create extension if not exists pgcrypto;


-- ---------------------------------------------------------------------------
-- Shared trigger function
-- ---------------------------------------------------------------------------
create function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;


-- ---------------------------------------------------------------------------
-- agent_types: catalog of agent templates.
-- ---------------------------------------------------------------------------
create table public.agent_types (
  id              uuid primary key default gen_random_uuid(),
  slug            text not null unique,
  name            text not null,
  description     text,
  system_prompt   text not null,
  model           text not null default 'gemini-3-flash-preview',
  -- Order in the "add an agent" palette; ties broken by name.
  sort_order      integer not null default 100,
  is_active       boolean not null default true,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  -- Preset slugs wired on agent creation. Slugs, not ids, so an unbuilt
  -- preset is skipped at provision time rather than failing the seed.
  default_presets text[] not null default '{}',
  -- Model requests one turn may make. Null falls back to the backend setting.
  request_limit   integer check (request_limit is null or request_limit > 0),
  constraint agent_types_slug_format
    check (slug ~ '^[a-z][a-z0-9_]{1,48}[a-z0-9]$'),
  constraint agent_types_system_prompt_nonempty
    check (length(btrim(system_prompt)) > 0)
);

create trigger agent_types_set_updated_at
  before update on public.agent_types
  for each row execute function public.set_updated_at();


-- ---------------------------------------------------------------------------
-- tool_types: catalog of tool templates (Brave Search, MCP, skill, ...).
-- ---------------------------------------------------------------------------
create table public.tool_types (
  id            uuid primary key default gen_random_uuid(),
  slug          text not null unique,
  name          text not null,
  description   text,
  -- JSON Schema-ish description of the fields the user must fill in.
  config_schema jsonb not null default '{}'::jsonb,
  -- Which of those fields are secrets, so the API never echoes them back.
  secret_fields text[] not null default '{}',
  sort_order    integer not null default 100,
  is_active     boolean not null default true,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  -- 'token' renders a password field, 'oauth2' renders a Connect button.
  auth_kind     text not null default 'token',
  constraint tool_types_slug_format
    check (slug ~ '^[a-z][a-z0-9_]{1,48}[a-z0-9]$'),
  constraint tool_types_auth_kind_valid
    check (auth_kind in ('token', 'oauth2'))
);

create trigger tool_types_set_updated_at
  before update on public.tool_types
  for each row execute function public.set_updated_at();


-- ---------------------------------------------------------------------------
-- tool_presets: ready-to-instantiate tools and skills. config is copied into
-- nodes.config on create, so a preset edit never changes an existing node.
-- No secrets here: platform keys come from settings, user keys from the vault.
-- ---------------------------------------------------------------------------
create table public.tool_presets (
  id            uuid primary key default gen_random_uuid(),
  slug          text not null unique,
  tool_type_id  uuid not null references public.tool_types (id) on delete restrict,
  name          text not null,
  description   text,
  config        jsonb not null default '{}'::jsonb,
  is_active     boolean not null default true,
  sort_order    integer not null default 100,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint tool_presets_slug_format
    check (slug ~ '^[a-z][a-z0-9_]{1,48}[a-z0-9]$')
);

create trigger tool_presets_set_updated_at
  before update on public.tool_presets
  for each row execute function public.set_updated_at();


-- ---------------------------------------------------------------------------
-- projects: one user's list of canvases.
-- ---------------------------------------------------------------------------
create table public.projects (
  id                 uuid primary key default gen_random_uuid(),
  owner_id           uuid not null references auth.users (id) on delete cascade,
  name               text not null,
  description        text,
  archived_at        timestamptz,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  -- When the frontend last uploaded a canvas screenshot for the project card.
  canvas_snapshot_at timestamptz,
  constraint projects_name_nonempty check (length(btrim(name)) > 0),
  constraint projects_name_len      check (length(name) <= 200)
);

-- "List my projects", and the RLS predicate.
create index projects_owner_id_created_at_idx
  on public.projects (owner_id, created_at desc);

-- One project name per user. Partial, so archiving a project frees its name.
create unique index projects_owner_id_name_uniq
  on public.projects (owner_id, name)
  where archived_at is null;

create trigger projects_set_updated_at
  before update on public.projects
  for each row execute function public.set_updated_at();


-- ---------------------------------------------------------------------------
-- nodes: the boxes on the canvas.
--
--   agent       -> from agent_types; owns a conversation
--   environment -> an E2B microVM
--   tool        -> an external capability, e.g. Brave Search
--
-- One table with a `kind` discriminator so edges can point at any box.
-- Many nodes can share one agent_type, which is what allows teams.
-- ---------------------------------------------------------------------------
create table public.nodes (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references public.projects (id) on delete cascade,
  owner_id      uuid not null references auth.users (id)      on delete cascade,
  kind          text not null,
  -- Exactly one is set, per `kind`. See nodes_type_matches_kind.
  agent_type_id uuid references public.agent_types (id) on delete restrict,
  tool_type_id  uuid references public.tool_types (id)  on delete restrict,
  -- Label on the box, e.g. "Market Research (EU)".
  name          text not null,

  -- Canvas position.
  position_x    double precision not null default 0,
  position_y    double precision not null default 0,

  -- Per-instance settings: prompt/model overrides, E2B sandbox id,
  -- or a tool's non-secret config.
  config        jsonb not null default '{}'::jsonb,

  -- 'ask' suspends the turn for approval, 'auto' just runs. Agent nodes only.
  tool_policy   text not null default 'ask',

  -- Lifecycle, so the canvas can show a box as live, broken, or still coming up.
  --   agent       : ready <-> running
  --   environment : pending -> provisioning -> ready / error / stopped
  --   tool        : pending -> ready (verified) / error
  status        text not null default 'pending',
  status_detail text,
  last_checked_at timestamptz,

  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),

  -- Per-node model override. Null inherits agent_types.model, so a catalog
  -- change still moves every node that never overrode it.
  model         text,

  constraint nodes_kind_valid
    check (kind in ('agent', 'environment', 'tool')),
  constraint nodes_status_valid
    check (status in ('pending', 'provisioning', 'ready', 'error', 'stopped', 'running')),
  constraint nodes_tool_policy_valid
    check (tool_policy in ('ask', 'auto')),
  constraint nodes_name_nonempty
    check (length(btrim(name)) > 0),
  -- Each kind points at its own catalog, and nothing else.
  constraint nodes_type_matches_kind check (
    (kind = 'agent'       and agent_type_id is not null and tool_type_id is null)
    or (kind = 'tool'     and tool_type_id  is not null and agent_type_id is null)
    or (kind = 'environment' and agent_type_id is null and tool_type_id is null)
  ),
  -- An environment carries its identity in config, so the shape is checked
  -- here rather than by a foreign key to a catalog table.
  constraint nodes_environment_config_valid check (
    kind <> 'environment' or (
      (config->>'runtime') in ('e2b', 'local')
      and (config->>'role') in ('scratch', 'user')
    )
  ),
  constraint nodes_model_shape check (
    model is null or (length(btrim(model)) > 0 and length(model) <= 200)
  ),
  -- A tool or environment box has no model.
  constraint nodes_model_agents_only check (
    model is null or kind = 'agent'
  )
);

-- Canvas load.
create index nodes_project_id_idx on public.nodes (project_id);
-- RLS predicate.
create index nodes_owner_id_idx on public.nodes (owner_id);
-- Keeps `on delete restrict` cheap.
create index nodes_agent_type_id_idx on public.nodes (agent_type_id);
create index nodes_tool_type_id_idx  on public.nodes (tool_type_id);

-- One scratch environment per project. A concurrent double create fails
-- loudly here rather than leaving two.
create unique index nodes_one_scratch_per_project
  on public.nodes (project_id)
  where kind = 'environment' and (config->>'role') = 'scratch';

create trigger nodes_set_updated_at
  before update on public.nodes
  for each row execute function public.set_updated_at();

-- nodes.owner_id always comes from the parent project, never the client.
-- Stops anyone attaching a node to someone else's project.
create function public.nodes_sync_owner()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  project_owner uuid;
begin
  select p.owner_id into project_owner
  from public.projects p
  where p.id = new.project_id;

  if project_owner is null then
    raise exception 'project % not found', new.project_id
      using errcode = 'foreign_key_violation';
  end if;

  new.owner_id := project_owner;
  return new;
end;
$$;

create trigger nodes_sync_owner_trg
  before insert or update of project_id, owner_id on public.nodes
  for each row execute function public.nodes_sync_owner();


-- ---------------------------------------------------------------------------
-- node_secrets: tool credential pointers, kept off the node row so a select
-- on nodes can never leak an API key. Ciphertext lives in vault.secrets;
-- read and write through set_node_secret / get_node_secret.
-- ---------------------------------------------------------------------------
create table public.node_secrets (
  id              uuid primary key default gen_random_uuid(),
  node_id         uuid not null references public.nodes (id)  on delete cascade,
  owner_id        uuid not null references auth.users (id)    on delete cascade,
  key             text not null,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  vault_secret_id uuid,
  constraint node_secrets_node_key_uniq unique (node_id, key),
  constraint node_secrets_key_nonempty check (length(btrim(key)) > 0)
);

create index node_secrets_owner_id_idx on public.node_secrets (owner_id);

create trigger node_secrets_set_updated_at
  before update on public.node_secrets
  for each row execute function public.set_updated_at();

-- vault.secrets has no foreign key back to node_secrets, so the cascade that
-- removes a pointer row cannot reach the ciphertext. This deletes it.
create function public.node_secrets_delete_vault_secret()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if old.vault_secret_id is not null then
    delete from vault.secrets where id = old.vault_secret_id;
  end if;
  return old;
end;
$$;

create trigger node_secrets_delete_vault_secret_trg
  after delete on public.node_secrets
  for each row execute function public.node_secrets_delete_vault_secret();

-- Rotating a secret replaces the pointer. Drop the old ciphertext.
create function public.node_secrets_replace_vault_secret()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if old.vault_secret_id is not null
     and old.vault_secret_id is distinct from new.vault_secret_id then
    delete from vault.secrets where id = old.vault_secret_id;
  end if;
  return new;
end;
$$;

create trigger node_secrets_replace_vault_secret_trg
  after update of vault_secret_id on public.node_secrets
  for each row execute function public.node_secrets_replace_vault_secret();


-- ---------------------------------------------------------------------------
-- edges: the arrows. They make context and capability available to the
-- target agent; no pipeline execution.
--
--   context     (agent -> agent)       : a summary + a retrieval tool
--   tool        (tool -> agent)        : a callable capability
--   environment (environment -> agent) : an execution target
--
-- Context edges go stale when the source conversation moves past
-- `summarised_through_seq`. The UI recolours the arrow; the user refreshes it.
-- Nothing regenerates on its own, so no surprise LLM bills.
-- ---------------------------------------------------------------------------
create table public.edges (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references public.projects (id) on delete cascade,
  owner_id       uuid not null references auth.users (id)      on delete cascade,
  source_node_id uuid not null references public.nodes (id)    on delete cascade,
  target_node_id uuid not null references public.nodes (id)    on delete cascade,
  kind           text not null,

  -- Context edges only.
  summary                text,
  summarised_through_seq bigint,
  summary_updated_at     timestamptz,
  -- Per edge: a feeder agent with a long history may warrant more room.
  summary_max_words      integer not null default 200,

  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),

  constraint edges_kind_valid
    check (kind in ('context', 'tool', 'environment')),
  -- One arrow per kind between two boxes.
  constraint edges_unique_link
    unique (source_node_id, target_node_id, kind),
  -- A box cannot feed itself.
  constraint edges_no_self_link
    check (source_node_id <> target_node_id),
  -- Summary is for context edges only.
  constraint edges_summary_only_on_context
    check (kind = 'context' or (summary is null and summarised_through_seq is null)),
  constraint edges_summary_max_words_sane
    check (summary_max_words between 20 and 2000)
);

-- Canvas load.
create index edges_project_id_idx on public.edges (project_id);
-- RLS predicate.
create index edges_owner_id_idx on public.edges (owner_id);
-- "What feeds this agent?": hot lookup when building a turn.
create index edges_target_node_id_kind_idx
  on public.edges (target_node_id, kind);
create index edges_source_node_id_idx on public.edges (source_node_id);

create trigger edges_set_updated_at
  before update on public.edges
  for each row execute function public.set_updated_at();

-- Edges inherit owner from their source node, both endpoints must sit on the
-- same canvas, and each edge kind connects its own pair of box kinds.
create function public.edges_validate()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  src_project uuid;
  src_owner   uuid;
  src_kind    text;
  tgt_project uuid;
  tgt_kind    text;
begin
  select n.project_id, n.owner_id, n.kind into src_project, src_owner, src_kind
  from public.nodes n where n.id = new.source_node_id;

  select n.project_id, n.kind into tgt_project, tgt_kind
  from public.nodes n where n.id = new.target_node_id;

  if src_project is null or tgt_project is null then
    raise exception 'edge endpoints must exist'
      using errcode = 'foreign_key_violation';
  end if;

  if src_project <> tgt_project then
    raise exception 'edge endpoints must belong to the same project'
      using errcode = 'check_violation';
  end if;

  if new.kind = 'context' and (src_kind <> 'agent' or tgt_kind <> 'agent') then
    raise exception 'context edges run agent to agent, not % to %', src_kind, tgt_kind
      using errcode = 'check_violation';
  end if;

  if new.kind = 'tool' and (src_kind <> 'tool' or tgt_kind <> 'agent') then
    raise exception 'tool edges run tool to agent, not % to %', src_kind, tgt_kind
      using errcode = 'check_violation';
  end if;

  if new.kind = 'environment' and (src_kind <> 'environment' or tgt_kind <> 'agent') then
    raise exception 'environment edges run environment to agent, not % to %', src_kind, tgt_kind
      using errcode = 'check_violation';
  end if;

  new.project_id := src_project;
  new.owner_id   := src_owner;
  return new;
end;
$$;

create trigger edges_validate_trg
  before insert or update of source_node_id, target_node_id, project_id, owner_id
  on public.edges
  for each row execute function public.edges_validate();


-- ---------------------------------------------------------------------------
-- conversations: one per agent node. Keyed on the node, not
-- (project, agent_type), so two "Market Research" boxes get two conversations.
-- ---------------------------------------------------------------------------
create table public.conversations (
  id              uuid primary key default gen_random_uuid(),
  node_id         uuid not null references public.nodes (id)    on delete cascade,
  project_id      uuid not null references public.projects (id) on delete cascade,
  owner_id        uuid not null references auth.users (id)      on delete cascade,
  title           text,
  -- Kept current by a trigger on messages, to avoid counting rows.
  message_count   integer not null default 0,
  last_message_at timestamptz,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  -- The approval pause. messages stores plain text and cannot round-trip a
  -- model response carrying tool call parts, so the history is parked here.
  pending_run     jsonb,
  pending_run_at  timestamptz,
  -- One conversation per agent box.
  constraint conversations_node_uniq unique (node_id),
  constraint conversations_message_count_nonneg check (message_count >= 0)
);

create index conversations_project_id_idx
  on public.conversations (project_id);
create index conversations_owner_id_idx
  on public.conversations (owner_id);

create trigger conversations_set_updated_at
  before update on public.conversations
  for each row execute function public.set_updated_at();

-- Conversations inherit project/owner from their node, and only agent nodes
-- get one: there is nothing to talk to on a tool or a microVM.
create function public.conversations_sync_owner()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  node_project uuid;
  node_owner   uuid;
  node_kind    text;
begin
  select n.project_id, n.owner_id, n.kind
    into node_project, node_owner, node_kind
  from public.nodes n
  where n.id = new.node_id;

  if node_project is null then
    raise exception 'node % not found', new.node_id
      using errcode = 'foreign_key_violation';
  end if;

  if node_kind <> 'agent' then
    raise exception 'conversations may only attach to agent nodes, not %', node_kind
      using errcode = 'check_violation';
  end if;

  new.project_id := node_project;
  new.owner_id   := node_owner;
  return new;
end;
$$;

create trigger conversations_sync_owner_trg
  before insert or update of node_id, project_id, owner_id on public.conversations
  for each row execute function public.conversations_sync_owner();


-- ---------------------------------------------------------------------------
-- messages: the transcript.
-- owner_id is denormalised so RLS here is a column compare, not a join.
-- ---------------------------------------------------------------------------
create table public.messages (
  id              uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations (id) on delete cascade,
  owner_id        uuid not null references auth.users (id)           on delete cascade,
  role            text not null,
  content         text not null,
  -- Which model actually answered, and what it cost. Models change.
  model           text,
  input_tokens    integer,
  -- output_tokens INCLUDES reasoning; reasoning_tokens is that subset, for
  -- attribution only. Never sum the two.
  output_tokens   integer,
  reasoning_tokens integer,
  -- 'running' is a turn in flight, 'awaiting_approval' one suspended on a
  -- tool call, 'failed' once the agent gives up retrying, 'cancelled' a user stop.
  status          text not null default 'complete',
  error           text,
  -- What was called, with what args, and whether it was approved.
  tool_calls      jsonb default '[]'::jsonb,
  -- Idempotency key. A resend or a retried step converges on one row.
  client_token    text,
  -- Ordering. Assigned by trigger: created_at is not safe, two inserts can
  -- share a timestamp.
  seq             bigint not null,
  created_at      timestamptz not null default now(),
  -- Cached input is priced differently from fresh input, so cost needs these.
  cache_read_tokens  integer,
  cache_write_tokens integer,
  -- Model requests under this row: a turn that pauses or loops through tool
  -- calls issues several.
  requests           integer,
  -- The agent node that wrote a user row (canvas run_agent). Null = the user.
  sender_node_id     uuid references public.nodes (id) on delete set null,
  -- Bumped by the live driver every 20s. The startup sweep only fails rows
  -- whose heartbeat (or created_at, before the first beat) is stale.
  heartbeat_at       timestamptz,
  -- The orchestrator turn a nested (canvas run_agent) turn runs under. Null = top level.
  parent_message_id  uuid references public.messages (id) on delete set null,
  -- Claims by the recovery loop. Failed at 3, so a crashing run cannot loop forever.
  resume_count       integer not null default 0,
  -- A user stop for a running row no live driver here received. The driving or
  -- resuming backend reads it on its next heartbeat or claim.
  cancel_requested   boolean not null default false,
  constraint messages_role_valid
    check (role in ('user', 'assistant', 'system')),
  constraint messages_status_valid
    check (status in ('complete', 'failed', 'awaiting_approval', 'running', 'cancelled')),
  -- Empty content only allowed on a failed or waiting turn.
  constraint messages_content_nonempty
    check (status <> 'complete' or length(content) > 0),
  -- Error text only on failed rows.
  constraint messages_error_iff_failed
    check ((status = 'failed') or (error is null)),
  constraint messages_tokens_nonneg
    check (coalesce(input_tokens, 0) >= 0 and coalesce(output_tokens, 0) >= 0
           and coalesce(reasoning_tokens, 0) >= 0),
  constraint messages_usage_nonneg
    check (coalesce(cache_read_tokens, 0) >= 0
       and coalesce(cache_write_tokens, 0) >= 0
       and coalesce(requests, 0) >= 0)
);

-- Replaying a conversation. Unique, so a bypassed trigger errors instead
-- of quietly corrupting the order.
create unique index messages_conversation_id_seq_idx
  on public.messages (conversation_id, seq);
-- RLS predicate.
create index messages_owner_id_idx
  on public.messages (owner_id);
-- Partial, so the usual NULL client_token costs nothing.
create unique index messages_conversation_client_token_uniq
  on public.messages (conversation_id, client_token)
  where client_token is not null;
-- Startup sweep and recovery loop.
create index messages_running_heartbeat_idx
  on public.messages (heartbeat_at)
  where status = 'running';
-- FK side of parent_message_id.
create index messages_parent_message_id_idx
  on public.messages (parent_message_id)
  where parent_message_id is not null;

-- Assign seq, inherit owner_id from the conversation. The FOR UPDATE lock
-- serialises inserts into one conversation so seq is gap-free. Contention is
-- per-conversation, so per-user.
create function public.messages_before_insert()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  conv_owner uuid;
begin
  -- Lock the parent so the max(seq) below cannot race.
  select c.owner_id into conv_owner
  from public.conversations c
  where c.id = new.conversation_id
  for update;

  if conv_owner is null then
    raise exception 'conversation % not found', new.conversation_id
      using errcode = 'foreign_key_violation';
  end if;

  -- Read max(seq) rather than conversations.message_count: a multi-row
  -- insert fires this once per row before the AFTER trigger bumps the
  -- counter, so both rows would land on the same seq.
  select coalesce(max(m.seq), 0) + 1 into new.seq
  from public.messages m
  where m.conversation_id = new.conversation_id;

  new.owner_id := conv_owner;
  return new;
end;
$$;

create trigger messages_before_insert_trg
  before insert on public.messages
  for each row execute function public.messages_before_insert();

create function public.messages_after_insert()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  update public.conversations
     set message_count   = message_count + 1,
         last_message_at = new.created_at,
         updated_at      = now()
   where id = new.conversation_id;
  return null;
end;
$$;

create trigger messages_after_insert_trg
  after insert on public.messages
  for each row execute function public.messages_after_insert();


-- ---------------------------------------------------------------------------
-- tool_calls: one row per tool invocation. Audit log, per-call status, and
-- the parking space for a pending approval.
-- ---------------------------------------------------------------------------
create table public.tool_calls (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid not null references public.projects (id)      on delete cascade,
  owner_id        uuid not null references auth.users (id)           on delete cascade,
  conversation_id uuid not null references public.conversations (id) on delete cascade,
  agent_node_id   uuid not null references public.nodes (id)         on delete cascade,
  tool_node_id    uuid not null references public.nodes (id)         on delete cascade,
  -- The model's own id for the call. Resume keys on it.
  tool_call_id    text not null,
  tool_name       text not null,
  arguments       jsonb not null default '{}'::jsonb,
  status          text not null,
  result          text,
  error           text,
  duration_ms     integer,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),

  constraint tool_calls_status_valid
    check (status in ('pending_approval', 'running', 'ok', 'error', 'denied', 'cancelled')),
  -- A resumed run must not record the same call twice.
  constraint tool_calls_unique_call
    unique (conversation_id, tool_call_id),
  constraint tool_calls_duration_sane
    check (duration_ms is null or duration_ms >= 0)
);

create index tool_calls_tool_node_id_idx
  on public.tool_calls (tool_node_id, created_at desc);
create index tool_calls_conversation_status_idx
  on public.tool_calls (conversation_id, status);
create index tool_calls_owner_id_idx on public.tool_calls (owner_id);

create trigger tool_calls_set_updated_at
  before update on public.tool_calls
  for each row execute function public.set_updated_at();

-- owner_id always comes from the parent project, never the client. Also
-- confirms conversation, agent node and tool node sit on the same project,
-- so a row cannot be repointed at another tenant's records.
create function public.tool_calls_sync_owner()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  project_owner   uuid;
  conv_project    uuid;
  agent_project   uuid;
  tool_project    uuid;
begin
  select p.owner_id into project_owner
  from public.projects p
  where p.id = new.project_id;

  if project_owner is null then
    raise exception 'project % not found', new.project_id
      using errcode = 'foreign_key_violation';
  end if;

  select c.project_id into conv_project
  from public.conversations c
  where c.id = new.conversation_id;

  select n.project_id into agent_project
  from public.nodes n
  where n.id = new.agent_node_id;

  select n.project_id into tool_project
  from public.nodes n
  where n.id = new.tool_node_id;

  if conv_project is null or agent_project is null or tool_project is null then
    raise exception 'tool call references must exist'
      using errcode = 'foreign_key_violation';
  end if;

  if conv_project <> new.project_id
     or agent_project <> new.project_id
     or tool_project <> new.project_id then
    raise exception 'tool call references must belong to the same project'
      using errcode = 'foreign_key_violation';
  end if;

  new.owner_id := project_owner;
  return new;
end;
$$;

create trigger tool_calls_sync_owner_trg
  before insert or update of
    project_id, owner_id, conversation_id, agent_node_id, tool_node_id
  on public.tool_calls
  for each row execute function public.tool_calls_sync_owner();


-- ---------------------------------------------------------------------------
-- usage_totals: token rollup per (project, owner, model), kept by a trigger
-- rather than summing messages on every read.
--
-- Grouped by model: nodes.model is a per-node override, and token counts are
-- neither comparable nor equally priced across models.
-- Keyed on owner too: projects are single-owner today, but a per-project key
-- would merge users once sharing lands and lose the per-user split for caps.
-- Failed turns count: they consumed tokens.
--
-- CAVEAT for sharing: messages_before_insert sets owner_id to the
-- CONVERSATION's owner, not the sender, so every row would bill the project
-- owner. Fix that trigger (carry the sender), not this table.
-- ---------------------------------------------------------------------------
create table public.usage_totals (
  project_id         uuid not null references public.projects (id) on delete cascade,
  owner_id           uuid not null references auth.users (id)      on delete cascade,
  model              text not null,
  input_tokens       bigint not null default 0,
  output_tokens      bigint not null default 0,
  reasoning_tokens   bigint not null default 0,
  cache_read_tokens  bigint not null default 0,
  cache_write_tokens bigint not null default 0,
  requests           bigint not null default 0,
  message_count      bigint not null default 0,
  updated_at         timestamptz not null default now(),
  primary key (project_id, owner_id, model)
);

-- Per-user rollup sums across projects and cannot use the pkey's leading column.
create index usage_totals_owner_id_idx
  on public.usage_totals (owner_id);

-- Insert AND update: an assistant row is inserted when a turn pauses for
-- approval and updated when it resumes.
create function public.messages_usage_rollup()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  d_input     bigint;
  d_output    bigint;
  d_reasoning bigint;
  d_cache_r   bigint;
  d_cache_w   bigint;
  d_requests  bigint;
  d_messages  bigint;
  target_project uuid;
begin
  -- Only assistant rows carry usage; user rows never do.
  if new.role <> 'assistant' then
    return null;
  end if;

  if tg_op = 'UPDATE' then
    d_input     := coalesce(new.input_tokens, 0)       - coalesce(old.input_tokens, 0);
    d_output    := coalesce(new.output_tokens, 0)      - coalesce(old.output_tokens, 0);
    d_reasoning := coalesce(new.reasoning_tokens, 0)   - coalesce(old.reasoning_tokens, 0);
    d_cache_r   := coalesce(new.cache_read_tokens, 0)  - coalesce(old.cache_read_tokens, 0);
    d_cache_w   := coalesce(new.cache_write_tokens, 0) - coalesce(old.cache_write_tokens, 0);
    d_requests  := coalesce(new.requests, 0)           - coalesce(old.requests, 0);
    d_messages  := 0;
  else
    d_input     := coalesce(new.input_tokens, 0);
    d_output    := coalesce(new.output_tokens, 0);
    d_reasoning := coalesce(new.reasoning_tokens, 0);
    d_cache_r   := coalesce(new.cache_read_tokens, 0);
    d_cache_w   := coalesce(new.cache_write_tokens, 0);
    d_requests  := coalesce(new.requests, 0);
    d_messages  := 1;
  end if;

  -- A row with no usage at all and no new message changes nothing.
  if d_input = 0 and d_output = 0 and d_reasoning = 0 and d_cache_r = 0
     and d_cache_w = 0 and d_requests = 0 and d_messages = 0 then
    return null;
  end if;

  select c.project_id into target_project
    from public.conversations c
   where c.id = new.conversation_id;

  if target_project is null then
    return null;
  end if;

  insert into public.usage_totals as t (
    project_id, owner_id, model,
    input_tokens, output_tokens, reasoning_tokens,
    cache_read_tokens, cache_write_tokens, requests, message_count
  )
  values (
    target_project, new.owner_id, coalesce(new.model, 'unknown'),
    d_input, d_output, d_reasoning, d_cache_r, d_cache_w, d_requests, d_messages
  )
  on conflict (project_id, owner_id, model) do update
     set input_tokens       = t.input_tokens       + excluded.input_tokens,
         output_tokens      = t.output_tokens      + excluded.output_tokens,
         reasoning_tokens   = t.reasoning_tokens   + excluded.reasoning_tokens,
         cache_read_tokens  = t.cache_read_tokens  + excluded.cache_read_tokens,
         cache_write_tokens = t.cache_write_tokens + excluded.cache_write_tokens,
         requests           = t.requests           + excluded.requests,
         message_count      = t.message_count      + excluded.message_count,
         updated_at         = now();
  return null;
end;
$$;

create trigger messages_usage_rollup_trg
  after insert or update of input_tokens, output_tokens, reasoning_tokens,
                            cache_read_tokens, cache_write_tokens, requests
  on public.messages
  for each row execute function public.messages_usage_rollup();


-- ---------------------------------------------------------------------------
-- previews: agent-published previews. Written by the service client, so no
-- owner column: access follows the parent project's owner.
-- ---------------------------------------------------------------------------
create table public.previews (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references public.projects (id) on delete cascade,
  env_node_id    uuid not null references public.nodes (id) on delete cascade,
  port           integer not null,
  path           text not null default '/',
  title          text not null,
  agent_node_id  uuid,
  thumbnail_path text,
  created_at     timestamptz not null default now(),
  unique (env_node_id, port)
);

create index previews_project_created_idx
  on public.previews (project_id, created_at desc);


-- ---------------------------------------------------------------------------
-- turn_checkpoints: a live turn's full model history, rewritten after each
-- model step. Own table, not a messages column, so a flush is not a large
-- messages update. Service client only: no client policies.
-- ---------------------------------------------------------------------------
create table public.turn_checkpoints (
  message_id  uuid primary key references public.messages (id) on delete cascade,
  owner_id    uuid not null references auth.users (id) on delete cascade,
  history     jsonb not null,
  -- Bubble length (content chars, tool_calls entries) at the checkpoint.
  content_len integer not null default 0,
  events_len  integer not null default 0,
  updated_at  timestamptz not null default now(),
  -- Approval decisions the run from this checkpoint resumed with, replayed by
  -- recovery. Cleared once the run moves past the calls they answer.
  approvals   jsonb
);

create index turn_checkpoints_owner_id_idx on public.turn_checkpoints (owner_id);


-- ---------------------------------------------------------------------------
-- notifications: one row per assistant turn reaching complete, failed or
-- awaiting_approval. Names copied at insert so a push needs no joins.
-- ---------------------------------------------------------------------------
create table public.notifications (
  id           uuid primary key default gen_random_uuid(),
  owner_id     uuid not null references auth.users (id)      on delete cascade,
  project_id   uuid not null references public.projects (id) on delete cascade,
  node_id      uuid not null references public.nodes (id)    on delete cascade,
  message_id   uuid not null references public.messages (id) on delete cascade,
  status       text not null,
  node_name    text not null,
  project_name text not null,
  -- Run under an orchestrator turn.
  nested       boolean not null default false,
  excerpt      text,
  read_at      timestamptz,
  created_at   timestamptz not null default now(),
  constraint notifications_status_valid
    check (status in ('complete', 'failed', 'awaiting_approval'))
);

-- Bell list.
create index notifications_owner_id_created_at_idx
  on public.notifications (owner_id, created_at desc);
-- Approval clear.
create index notifications_message_id_idx
  on public.notifications (message_id);
-- Push outbox scan.
create index notifications_unread_created_at_idx
  on public.notifications (created_at)
  where read_at is null;
-- Keeps the cascades cheap.
create index notifications_project_id_idx on public.notifications (project_id);
create index notifications_node_id_idx on public.notifications (node_id);

-- Notify on an assistant status change. Never fails the status write.
create function public.messages_notify()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if new.role <> 'assistant' or new.status is not distinct from old.status then
    return new;
  end if;

  begin
    -- Leaving a pause clears its "needs approval" entries.
    if old.status = 'awaiting_approval' then
      update public.notifications set read_at = now()
       where message_id = new.id and status = 'awaiting_approval' and read_at is null;
    end if;

    if new.status in ('complete', 'failed', 'awaiting_approval') then
      insert into public.notifications
        (owner_id, project_id, node_id, message_id, status, node_name, project_name, nested, excerpt)
      select new.owner_id, c.project_id, c.node_id, new.id, new.status, n.name, p.name,
             new.parent_message_id is not null,
             case new.status
               when 'complete' then btrim(left(regexp_replace(new.content, '\s+', ' ', 'g'), 140))
               when 'failed'   then left(new.error, 140)
             end
        from public.conversations c
        join public.nodes n    on n.id = c.node_id
        join public.projects p on p.id = c.project_id
       where c.id = new.conversation_id;
    end if;
  exception when others then
    raise warning 'notification insert failed for message %: %', new.id, sqlerrm;
  end;

  return new;
end;
$$;

create trigger messages_notify_trg
  after update of status on public.messages
  for each row execute function public.messages_notify();


-- ---------------------------------------------------------------------------
-- push_subscriptions: a device's Web Push endpoint. Written through
-- upsert_push_subscription only.
-- ---------------------------------------------------------------------------
create table public.push_subscriptions (
  id            uuid primary key default gen_random_uuid(),
  owner_id      uuid not null references auth.users (id) on delete cascade,
  endpoint      text not null unique,
  p256dh        text not null,
  auth          text not null,
  user_agent    text,
  -- App in the foreground until then. Push deferred.
  visible_until timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create index push_subscriptions_owner_id_idx on public.push_subscriptions (owner_id);


-- ---------------------------------------------------------------------------
-- push_deliveries: sent (or claimed) pushes. Service only: no client policies.
-- ponytail: never pruned, delete rows older than the 1 hour push window if it grows.
-- ---------------------------------------------------------------------------
create table public.push_deliveries (
  notification_id uuid not null references public.notifications (id)      on delete cascade,
  subscription_id uuid not null references public.push_subscriptions (id) on delete cascade,
  sent_at         timestamptz not null default now(),
  primary key (notification_id, subscription_id)
);

-- Cascade on a 404/410 subscription delete.
create index push_deliveries_subscription_id_idx
  on public.push_deliveries (subscription_id);
