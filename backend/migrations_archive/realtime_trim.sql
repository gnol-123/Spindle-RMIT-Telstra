-- Unpublish messages and tool_calls from Supabase Realtime. Re-runnable.
-- No client subscribes to them (turns stream over SSE), yet Realtime decoded
-- every progress flush: ~46% of DB time.
begin;
set local lock_timeout = '5s';

do $$
begin
  if exists (select 1 from pg_publication_tables
             where pubname = 'supabase_realtime' and tablename = 'messages') then
    alter publication supabase_realtime drop table public.messages;
  end if;
  if exists (select 1 from pg_publication_tables
             where pubname = 'supabase_realtime' and tablename = 'tool_calls') then
    alter publication supabase_realtime drop table public.tool_calls;
  end if;
end
$$;

commit;
