-- RLS en TODAS las tablas p03_. Sin política = denegado. El rol anon/publishable NO lee ni escribe nada.
alter table public.p03_tenants enable row level security;
alter table public.p03_chunks enable row level security;
alter table public.p03_sessions enable row level security;
alter table public.p03_messages enable row level security;
alter table public.p03_processed_messages enable row level security;
alter table public.p03_handoffs enable row level security;

-- El dueño autenticado solo ve/edita lo de su negocio.
drop policy if exists p03_tenants_owner on public.p03_tenants;
create policy p03_tenants_owner on public.p03_tenants for all to authenticated
  using ((select auth.uid()) = owner_user_id) with check ((select auth.uid()) = owner_user_id);

drop policy if exists p03_chunks_owner on public.p03_chunks;
create policy p03_chunks_owner on public.p03_chunks for all to authenticated
  using (exists (select 1 from public.p03_tenants t where t.id = tenant_id and t.owner_user_id = (select auth.uid())))
  with check (exists (select 1 from public.p03_tenants t where t.id = tenant_id and t.owner_user_id = (select auth.uid())));

drop policy if exists p03_handoffs_owner on public.p03_handoffs;
create policy p03_handoffs_owner on public.p03_handoffs for select to authenticated
  using (exists (select 1 from public.p03_tenants t where t.id = tenant_id and t.owner_user_id = (select auth.uid())));

-- sessions, messages y processed_messages: solo las toca el servidor del agente (sin políticas para anon/authenticated).
