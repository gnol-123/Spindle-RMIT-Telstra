-- Row Level Security and table grants.
--
-- The backend filters by owner as well; these policies are the backstop.
-- Use `(select auth.uid())`, not bare `auth.uid()`: the subquery is
-- evaluated once per query instead of once per row.

alter table public.agent_types        enable row level security;
alter table public.tool_types         enable row level security;
alter table public.tool_presets       enable row level security;
alter table public.projects           enable row level security;
alter table public.nodes              enable row level security;
alter table public.node_secrets       enable row level security;
alter table public.edges              enable row level security;
alter table public.conversations      enable row level security;
alter table public.messages           enable row level security;
alter table public.tool_calls         enable row level security;
alter table public.usage_totals       enable row level security;
alter table public.previews           enable row level security;
alter table public.turn_checkpoints   enable row level security;
alter table public.notifications      enable row level security;
alter table public.push_subscriptions enable row level security;
alter table public.push_deliveries    enable row level security;

-- Force RLS for table owners too. Does not cover service_role, which is
-- BYPASSRLS: anything using the service key relies on backend filtering.
alter table public.tool_presets       force row level security;
alter table public.projects           force row level security;
alter table public.nodes              force row level security;
alter table public.node_secrets       force row level security;
alter table public.edges              force row level security;
alter table public.conversations      force row level security;
alter table public.messages           force row level security;
alter table public.tool_calls         force row level security;
alter table public.previews           force row level security;
alter table public.turn_checkpoints   force row level security;
alter table public.notifications      force row level security;
alter table public.push_subscriptions force row level security;
alter table public.push_deliveries    force row level security;

-- Service client only, no client policies: turn_checkpoints, push_deliveries.


-- ---------------------------------------------------------------------------
-- Catalogs: read-only. No write policies, so writes are refused.
-- ---------------------------------------------------------------------------
create policy agent_types_select
  on public.agent_types
  for select
  to authenticated
  using (is_active);

create policy tool_types_select
  on public.tool_types
  for select
  to authenticated
  using (is_active);

create policy tool_presets_select
  on public.tool_presets
  for select
  to authenticated
  using (is_active);


-- ---------------------------------------------------------------------------
-- projects
-- ---------------------------------------------------------------------------
create policy projects_select
  on public.projects
  for select
  to authenticated
  using (owner_id = (select auth.uid()));

create policy projects_insert
  on public.projects
  for insert
  to authenticated
  with check (owner_id = (select auth.uid()));

create policy projects_update
  on public.projects
  for update
  to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy projects_delete
  on public.projects
  for delete
  to authenticated
  using (owner_id = (select auth.uid()));


-- ---------------------------------------------------------------------------
-- nodes. INSERT checks the parent project, since owner_id is trigger-assigned
-- and not yet trustworthy at check time.
-- ---------------------------------------------------------------------------
create policy nodes_select
  on public.nodes
  for select
  to authenticated
  using (owner_id = (select auth.uid()));

create policy nodes_insert
  on public.nodes
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.projects p
      where p.id = nodes.project_id
        and p.owner_id = (select auth.uid())
    )
  );

create policy nodes_update
  on public.nodes
  for update
  to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy nodes_delete
  on public.nodes
  for delete
  to authenticated
  using (owner_id = (select auth.uid()));


-- ---------------------------------------------------------------------------
-- node_secrets
-- ---------------------------------------------------------------------------
create policy node_secrets_select
  on public.node_secrets
  for select
  to authenticated
  using (owner_id = (select auth.uid()));

create policy node_secrets_insert
  on public.node_secrets
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.nodes n
      where n.id = node_secrets.node_id
        and n.owner_id = (select auth.uid())
    )
  );

create policy node_secrets_update
  on public.node_secrets
  for update
  to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy node_secrets_delete
  on public.node_secrets
  for delete
  to authenticated
  using (owner_id = (select auth.uid()));


-- ---------------------------------------------------------------------------
-- edges. INSERT checks the source node; edges_validate also refuses edges
-- spanning two projects. UPDATE is for refreshing a stale summary.
-- ---------------------------------------------------------------------------
create policy edges_select
  on public.edges
  for select
  to authenticated
  using (owner_id = (select auth.uid()));

create policy edges_insert
  on public.edges
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.nodes n
      where n.id = edges.source_node_id
        and n.owner_id = (select auth.uid())
    )
  );

create policy edges_update
  on public.edges
  for update
  to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy edges_delete
  on public.edges
  for delete
  to authenticated
  using (owner_id = (select auth.uid()));


-- ---------------------------------------------------------------------------
-- conversations
-- ---------------------------------------------------------------------------
create policy conversations_select
  on public.conversations
  for select
  to authenticated
  using (owner_id = (select auth.uid()));

create policy conversations_insert
  on public.conversations
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.nodes n
      where n.id = conversations.node_id
        and n.owner_id = (select auth.uid())
    )
  );

create policy conversations_update
  on public.conversations
  for update
  to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy conversations_delete
  on public.conversations
  for delete
  to authenticated
  using (owner_id = (select auth.uid()));


-- ---------------------------------------------------------------------------
-- messages. UPDATE is only so a suspended turn can be completed in place;
-- the transcript is otherwise append-only.
-- ---------------------------------------------------------------------------
create policy messages_select
  on public.messages
  for select
  to authenticated
  using (owner_id = (select auth.uid()));

create policy messages_insert
  on public.messages
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.conversations c
      where c.id = messages.conversation_id
        and c.owner_id = (select auth.uid())
    )
  );

create policy messages_update
  on public.messages
  for update
  to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy messages_delete
  on public.messages
  for delete
  to authenticated
  using (owner_id = (select auth.uid()));


-- ---------------------------------------------------------------------------
-- tool_calls
-- ---------------------------------------------------------------------------
create policy tool_calls_select_own on public.tool_calls
  for select to authenticated
  using (owner_id = (select auth.uid()));

create policy tool_calls_insert_own on public.tool_calls
  for insert to authenticated
  with check (
    exists (
      select 1 from public.projects p
      where p.id = project_id and p.owner_id = (select auth.uid())
    )
  );

create policy tool_calls_update_own on public.tool_calls
  for update to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy tool_calls_delete_own on public.tool_calls
  for delete to authenticated
  using (owner_id = (select auth.uid()));


-- ---------------------------------------------------------------------------
-- usage_totals: read-only to the owner. Writes come from the security
-- definer rollup trigger.
-- ---------------------------------------------------------------------------
create policy usage_totals_select
  on public.usage_totals
  for select
  to authenticated
  using (owner_id = (select auth.uid()));


-- ---------------------------------------------------------------------------
-- previews: access follows the parent project's owner.
-- ---------------------------------------------------------------------------
create policy previews_select
  on public.previews
  for select
  to authenticated
  using (
    exists (
      select 1 from public.projects p
      where p.id = previews.project_id
        and p.owner_id = (select auth.uid())
    )
  );

create policy previews_insert
  on public.previews
  for insert
  to authenticated
  with check (
    exists (
      select 1 from public.projects p
      where p.id = previews.project_id
        and p.owner_id = (select auth.uid())
    )
  );

create policy previews_update
  on public.previews
  for update
  to authenticated
  using (
    exists (
      select 1 from public.projects p
      where p.id = previews.project_id
        and p.owner_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.projects p
      where p.id = previews.project_id
        and p.owner_id = (select auth.uid())
    )
  );

create policy previews_delete
  on public.previews
  for delete
  to authenticated
  using (
    exists (
      select 1 from public.projects p
      where p.id = previews.project_id
        and p.owner_id = (select auth.uid())
    )
  );


-- ---------------------------------------------------------------------------
-- notifications: read own, mark own read. No client insert or delete.
-- ---------------------------------------------------------------------------
create policy notifications_select
  on public.notifications
  for select
  to authenticated
  using (owner_id = (select auth.uid()));

create policy notifications_update
  on public.notifications
  for update
  to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

revoke update on public.notifications from authenticated;
grant update (read_at) on public.notifications to authenticated;


-- ---------------------------------------------------------------------------
-- push_subscriptions: insert through upsert_push_subscription only.
-- ---------------------------------------------------------------------------
create policy push_subscriptions_select
  on public.push_subscriptions
  for select
  to authenticated
  using (owner_id = (select auth.uid()));

create policy push_subscriptions_update
  on public.push_subscriptions
  for update
  to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy push_subscriptions_delete
  on public.push_subscriptions
  for delete
  to authenticated
  using (owner_id = (select auth.uid()));

revoke update on public.push_subscriptions from authenticated;
grant update (visible_until, updated_at) on public.push_subscriptions to authenticated;
