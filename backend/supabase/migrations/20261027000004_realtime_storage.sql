-- Realtime publication and storage.

-- Postgres Changes enforces RLS per subscriber, so the select policies
-- (20261027000003_security.sql) must exist first. Not messages or tool_calls: turns
-- stream over SSE, and Realtime decoding every progress flush cost ~46% of DB time.
alter publication supabase_realtime add table public.nodes, public.edges, public.notifications;

-- Private bucket for preview thumbnails.
insert into storage.buckets (id, name, public)
values ('project-previews', 'project-previews', false);
