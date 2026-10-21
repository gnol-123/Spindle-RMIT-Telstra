-- Agent-published previews, moved out of the sandbox's previews.json, plus the
-- private bucket for their thumbnails. Apply after design_skills.sql. Re-runnable.
begin;

create table if not exists public.previews (
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

create index if not exists previews_project_created_idx
  on public.previews (project_id, created_at desc);

-- Rows are written by the service client, so there is no owner column: access
-- follows the parent project's owner.
alter table public.previews enable row level security;
alter table public.previews force row level security;

drop policy if exists previews_select on public.previews;
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

drop policy if exists previews_insert on public.previews;
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

drop policy if exists previews_update on public.previews;
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

drop policy if exists previews_delete on public.previews;
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

insert into storage.buckets (id, name, public)
values ('project-previews', 'project-previews', false)
on conflict do nothing;

commit;
