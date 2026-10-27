-- Durable turns: checkpoints, nested turn linkage, resume cap. Apply after
-- scope_report.sql. Re-runnable.
begin;

-- The orchestrator turn a nested (canvas run_agent) turn runs under. Null = top level.
alter table public.messages add column if not exists parent_message_id uuid
  references public.messages (id) on delete set null;

-- Claims by the recovery loop. Failed at 3, so a crashing run cannot loop forever.
alter table public.messages add column if not exists resume_count integer not null default 0;

-- FK side of parent_message_id. The loop's own query uses messages_running_heartbeat_idx.
create index if not exists messages_parent_message_id_idx
  on public.messages (parent_message_id)
  where parent_message_id is not null;

-- A live turn's full model history, rewritten after each model step. Its own
-- table, not a messages column: messages is in the realtime publication and
-- every flush would broadcast it. Service client only: no client policies.
create table if not exists public.turn_checkpoints (
  message_id  uuid primary key references public.messages (id) on delete cascade,
  owner_id    uuid not null references auth.users (id) on delete cascade,
  history     jsonb not null,
  -- Bubble length (content chars, tool_calls entries) at the checkpoint.
  content_len integer not null default 0,
  events_len  integer not null default 0,
  updated_at  timestamptz not null default now()
);

create index if not exists turn_checkpoints_owner_id_idx on public.turn_checkpoints (owner_id);

alter table public.turn_checkpoints enable row level security;
alter table public.turn_checkpoints force row level security;

-- The approval decisions the run from this checkpoint resumed with, replayed by
-- recovery. Cleared once the run moves past the calls they answer.
alter table public.turn_checkpoints add column if not exists approvals jsonb;

-- A user stop for a running row no live driver here received. The driving or
-- resuming backend reads it on its next heartbeat or claim.
alter table public.messages add column if not exists cancel_requested boolean not null default false;

commit;
