-- Agent turn notifications: in-app bell and Web Push outbox.
-- Apply after durability.sql. Re-runnable.
begin;
-- Fail fast on the messages trigger lock instead of queueing turn writes.
set local lock_timeout = '5s';

-- One row per assistant turn reaching complete, failed or awaiting_approval.
-- Names copied at insert so a push needs no joins.
create table if not exists public.notifications (
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
create index if not exists notifications_owner_id_created_at_idx
  on public.notifications (owner_id, created_at desc);
-- Approval clear.
create index if not exists notifications_message_id_idx
  on public.notifications (message_id);
-- Push outbox scan.
create index if not exists notifications_unread_created_at_idx
  on public.notifications (created_at)
  where read_at is null;
-- Keeps the cascades cheap.
create index if not exists notifications_project_id_idx on public.notifications (project_id);
create index if not exists notifications_node_id_idx on public.notifications (node_id);

-- A device's Web Push endpoint. Written through upsert_push_subscription only.
create table if not exists public.push_subscriptions (
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

create index if not exists push_subscriptions_owner_id_idx on public.push_subscriptions (owner_id);

-- Sent (or claimed) pushes. Service only: no client policies.
-- ponytail: never pruned, delete rows older than the 1 hour push window if it grows.
create table if not exists public.push_deliveries (
  notification_id uuid not null references public.notifications (id)      on delete cascade,
  subscription_id uuid not null references public.push_subscriptions (id) on delete cascade,
  sent_at         timestamptz not null default now(),
  primary key (notification_id, subscription_id)
);

-- Cascade on a 404/410 subscription delete.
create index if not exists push_deliveries_subscription_id_idx
  on public.push_deliveries (subscription_id);


-- ---------------------------------------------------------------------------
-- Notify on an assistant status change. Never fails the status write.
-- ---------------------------------------------------------------------------
create or replace function public.messages_notify()
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

drop trigger if exists messages_notify_trg on public.messages;
create trigger messages_notify_trg
  after update of status on public.messages
  for each row execute function public.messages_notify();


-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table public.notifications      enable row level security;
alter table public.notifications      force row level security;
alter table public.push_subscriptions enable row level security;
alter table public.push_subscriptions force row level security;
alter table public.push_deliveries    enable row level security;
alter table public.push_deliveries    force row level security;

-- notifications: read own, mark own read. No client insert or delete.
drop policy if exists notifications_select on public.notifications;
create policy notifications_select
  on public.notifications
  for select
  to authenticated
  using (owner_id = (select auth.uid()));

drop policy if exists notifications_update on public.notifications;
create policy notifications_update
  on public.notifications
  for update
  to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

revoke update on public.notifications from authenticated;
grant update (read_at) on public.notifications to authenticated;

-- push_subscriptions: insert through the RPC only.
drop policy if exists push_subscriptions_select on public.push_subscriptions;
create policy push_subscriptions_select
  on public.push_subscriptions
  for select
  to authenticated
  using (owner_id = (select auth.uid()));

drop policy if exists push_subscriptions_update on public.push_subscriptions;
create policy push_subscriptions_update
  on public.push_subscriptions
  for update
  to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

drop policy if exists push_subscriptions_delete on public.push_subscriptions;
create policy push_subscriptions_delete
  on public.push_subscriptions
  for delete
  to authenticated
  using (owner_id = (select auth.uid()));

revoke update on public.push_subscriptions from authenticated;
grant update (visible_until, updated_at) on public.push_subscriptions to authenticated;


-- ---------------------------------------------------------------------------
-- Register a device for the caller. An endpoint already on another account
-- moves to the caller, with a fresh created_at so its backlog never pushes.
-- Browser push services only (mirrors the API check). 10 devices per account.
-- ---------------------------------------------------------------------------
create or replace function public.upsert_push_subscription(
  p_endpoint   text,
  p_p256dh     text,
  p_auth       text,
  p_user_agent text
)
returns uuid
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  caller uuid := auth.uid();
  sub_id uuid;
begin
  if caller is null then
    raise exception 'not authenticated' using errcode = 'insufficient_privilege';
  end if;

  -- Host must end right before the path: no userinfo, no other port, no lookalikes.
  if p_endpoint is null or p_endpoint !~*
     '^https://(web\.push\.apple\.com|fcm\.googleapis\.com|[a-z0-9.-]+\.push\.services\.mozilla\.com|[a-z0-9.-]+\.notify\.windows\.com)(:443)?/'
  then
    raise exception 'invalid push endpoint' using errcode = '22023';
  end if;

  insert into public.push_subscriptions as s (owner_id, endpoint, p256dh, auth, user_agent)
  values (caller, p_endpoint, p_p256dh, p_auth, p_user_agent)
  on conflict (endpoint) do update
    set owner_id   = excluded.owner_id,
        p256dh     = excluded.p256dh,
        auth       = excluded.auth,
        user_agent = excluded.user_agent,
        created_at = case when s.owner_id = excluded.owner_id then s.created_at else now() end,
        updated_at = now()
  returning s.id into sub_id;

  -- Keep this device and the 9 most recently updated others.
  delete from public.push_subscriptions
   where id in (select id from public.push_subscriptions
                 where owner_id = caller and id <> sub_id
                 order by updated_at desc, created_at desc
                 offset 9);

  return sub_id;
end;
$$;

revoke all on function public.upsert_push_subscription(text, text, text, text) from public, anon;
grant execute on function public.upsert_push_subscription(text, text, text, text) to authenticated;


-- ---------------------------------------------------------------------------
-- Push outbox claim. The insert is the claim, so two backends never double send.
-- ---------------------------------------------------------------------------
-- Return columns changed: replace cannot alter them.
drop function if exists public.claim_push_batch(int);
create function public.claim_push_batch(p_limit int default 50)
returns table (
  notification_id uuid,
  subscription_id uuid,
  endpoint        text,
  p256dh          text,
  auth            text,
  status          text,
  node_name       text,
  project_name    text,
  project_id      uuid,
  nested          boolean,
  excerpt         text,
  message_id      uuid
)
language sql
security definer
set search_path = public, pg_temp
as $$
  with pairs as (
    select n.id as nid, s.id as sid
      from public.notifications n
      join public.push_subscriptions s on s.owner_id = n.owner_id
     where n.read_at is null
       and n.created_at > now() - interval '1 hour'
       and n.created_at >= s.created_at
       and (s.visible_until is null or s.visible_until < now())
       and not exists (select 1 from public.push_deliveries d
                        where d.notification_id = n.id and d.subscription_id = s.id)
     order by n.created_at
     limit p_limit
  ),
  claimed as (
    insert into public.push_deliveries (notification_id, subscription_id)
    select nid, sid from pairs
    on conflict do nothing
    returning push_deliveries.notification_id as nid, push_deliveries.subscription_id as sid
  )
  select n.id, s.id, s.endpoint, s.p256dh, s.auth, n.status, n.node_name, n.project_name,
         n.project_id, n.nested, n.excerpt, n.message_id
    from claimed c
    join public.notifications n      on n.id = c.nid
    join public.push_subscriptions s on s.id = c.sid;
$$;

revoke all on function public.claim_push_batch(int) from public, anon, authenticated;
grant execute on function public.claim_push_batch(int) to service_role;


-- ---------------------------------------------------------------------------
-- Realtime. Postgres Changes enforces RLS per subscriber; the select policy is above.
-- ---------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_publication_tables
                 where pubname = 'supabase_realtime' and schemaname = 'public'
                   and tablename = 'notifications') then
    alter publication supabase_realtime add table public.notifications;
  end if;
end
$$;

commit;
