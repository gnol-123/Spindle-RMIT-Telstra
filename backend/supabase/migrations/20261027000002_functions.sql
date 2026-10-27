-- Callable RPCs: vault-backed node secrets and Web Push.


-- ---------------------------------------------------------------------------
-- Write a secret. The caller may set a key they can never read back.
-- ---------------------------------------------------------------------------
create function public.set_node_secret(
  p_node_id uuid,
  p_key     text,
  p_value   text
)
returns void
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  node_owner  uuid;
  existing_id uuid;
  secret_name text;
begin
  select n.owner_id into node_owner
  from public.nodes n
  where n.id = p_node_id;

  if node_owner is null then
    raise exception 'node % not found', p_node_id
      using errcode = 'foreign_key_violation';
  end if;

  if node_owner <> auth.uid() then
    raise exception 'not permitted' using errcode = 'insufficient_privilege';
  end if;

  select ns.vault_secret_id into existing_id
  from public.node_secrets ns
  where ns.node_id = p_node_id and ns.key = p_key;

  secret_name := 'node:' || p_node_id::text || ':' || p_key;

  if existing_id is null then
    insert into public.node_secrets (node_id, owner_id, key, vault_secret_id)
    values (
      p_node_id,
      node_owner,
      p_key,
      vault.create_secret(p_value, secret_name, 'tool node secret')
    );
  else
    perform vault.update_secret(existing_id, p_value, secret_name, 'tool node secret');
    -- No-op on the value itself, but this keeps updated_at current via the trigger.
    update public.node_secrets
       set vault_secret_id = existing_id
     where node_id = p_node_id and key = p_key;
  end if;
end;
$$;

revoke all on function public.set_node_secret(uuid, text, text) from public, anon;
grant execute on function public.set_node_secret(uuid, text, text) to authenticated;


-- ---------------------------------------------------------------------------
-- Read a secret. Granted to service_role only: the backend calls it after
-- ownership has been checked under RLS.
-- ---------------------------------------------------------------------------
create function public.get_node_secret(
  p_node_id uuid,
  p_key     text
)
returns text
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  secret_value text;
begin
  select ds.decrypted_secret into secret_value
  from public.node_secrets ns
  join vault.decrypted_secrets ds on ds.id = ns.vault_secret_id
  where ns.node_id = p_node_id and ns.key = p_key;

  return secret_value;
end;
$$;

revoke all on function public.get_node_secret(uuid, text) from public, anon, authenticated;
grant execute on function public.get_node_secret(uuid, text) to service_role;


-- ---------------------------------------------------------------------------
-- set_node_secret for the OAuth callback, which has no user JWT: ownership
-- rests on the signed state, so the owner is passed explicitly and checked
-- against the node. service_role only, after the backend verified the state.
-- ---------------------------------------------------------------------------
create function public.set_node_secret_as(
  p_node_id  uuid,
  p_owner_id uuid,
  p_key      text,
  p_value    text
)
returns void
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  node_owner  uuid;
  existing_id uuid;
  secret_name text;
begin
  select n.owner_id into node_owner
  from public.nodes n
  where n.id = p_node_id;

  if node_owner is null then
    raise exception 'node % not found', p_node_id
      using errcode = 'foreign_key_violation';
  end if;

  if node_owner <> p_owner_id then
    raise exception 'not permitted' using errcode = 'insufficient_privilege';
  end if;

  select ns.vault_secret_id into existing_id
  from public.node_secrets ns
  where ns.node_id = p_node_id and ns.key = p_key;

  secret_name := 'node:' || p_node_id::text || ':' || p_key;

  if existing_id is null then
    insert into public.node_secrets (node_id, owner_id, key, vault_secret_id)
    values (
      p_node_id,
      node_owner,
      p_key,
      vault.create_secret(p_value, secret_name, 'tool node secret')
    );
  else
    perform vault.update_secret(existing_id, p_value, secret_name, 'tool node secret');
    update public.node_secrets
       set vault_secret_id = existing_id
     where node_id = p_node_id and key = p_key;
  end if;
end;
$$;

revoke all on function public.set_node_secret_as(uuid, uuid, text, text) from public, anon, authenticated;
grant execute on function public.set_node_secret_as(uuid, uuid, text, text) to service_role;


-- ---------------------------------------------------------------------------
-- Register a device for the caller. An endpoint already on another account
-- moves to the caller, with a fresh created_at so its backlog never pushes.
-- Browser push services only (mirrors the API check). 10 devices per account.
-- ---------------------------------------------------------------------------
create function public.upsert_push_subscription(
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
