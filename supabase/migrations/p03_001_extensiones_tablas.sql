-- P03 (agente RAG). Idempotente. Orden: 001 -> 002 -> 003. Aplicar desde el SQL Editor (lo hace el orquestador).
create extension if not exists vector;

create table if not exists public.p03_tenants (
  id text primary key,
  name text not null,
  owner_user_id uuid not null,              -- auth.users.id del dueño (se asigna al crear el negocio)
  wa_phone_number_id text unique,
  handoff_text text not null default ''
);

create table if not exists public.p03_chunks (
  tenant_id text not null references public.p03_tenants(id) on delete cascade,
  chunk_id text not null,                   -- doc_id#n
  doc_id text not null,
  chunk_idx int not null,
  title text not null,
  page int not null,
  text text not null,
  embedding vector(768) not null,           -- nomic-embed-text
  primary key (tenant_id, chunk_id)
);
create index if not exists p03_chunks_tenant_ix on public.p03_chunks(tenant_id);

create table if not exists public.p03_sessions (
  id text primary key,
  tenant_id text not null references public.p03_tenants(id) on delete cascade,
  created timestamptz not null default now(),
  msg_count int not null default 0
);
create table if not exists public.p03_messages (
  id bigint generated always as identity primary key,
  session_id text not null references public.p03_sessions(id) on delete cascade,
  tenant_id text not null,
  role text not null check (role in ('user','assistant')),
  content text not null,
  ts timestamptz not null default now()
);
create table if not exists public.p03_processed_messages (   -- idempotencia webhook WhatsApp
  message_id text primary key,
  tenant_id text not null,
  ts timestamptz not null default now()
);
create table if not exists public.p03_handoffs (
  id bigint generated always as identity primary key,
  tenant_id text not null,
  session_id text not null,
  ts timestamptz not null default now()
);
