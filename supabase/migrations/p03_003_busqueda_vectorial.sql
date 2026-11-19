-- Búsqueda con tenant_id en la PROPIA consulta. security invoker: respeta RLS del llamante.
create or replace function public.p03_match_chunks(p_tenant text, p_query vector(768), p_k int default 4)
returns table (chunk_id text, doc_id text, title text, page int, text text, score float)
language sql stable security invoker set search_path = public as $$
  select c.chunk_id, c.doc_id, c.title, c.page, c.text, 1 - (c.embedding <=> p_query) as score
  from public.p03_chunks c
  where c.tenant_id = p_tenant
  order by c.embedding <=> p_query
  limit least(greatest(p_k, 1), 10);
$$;
revoke all on function public.p03_match_chunks(text, vector, int) from public, anon;
grant execute on function public.p03_match_chunks(text, vector, int) to authenticated;
