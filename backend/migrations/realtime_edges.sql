-- Publishes edges to Supabase Realtime. Apply after rls.sql. Re-runnable.
begin;

-- Postgres Changes enforces RLS per subscriber, so the select policy must exist first.
do $$
begin
  if not exists (select 1 from pg_policies where tablename = 'edges' and policyname = 'edges_select') then
    raise exception 'apply rls.sql before realtime_edges.sql';
  end if;

  if not exists (select 1 from pg_publication_tables
                 where pubname = 'supabase_realtime' and tablename = 'edges') then
    alter publication supabase_realtime add table public.edges;
  end if;
end
$$;

commit;
