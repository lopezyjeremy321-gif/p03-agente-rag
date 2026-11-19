# Migraciones Supabase de P03 (prefijo `p03_`, esquema `public`, RLS siempre)

Aplicar en el SQL Editor, en este orden (todas idempotentes):
1. `migrations/p03_001_extensiones_tablas.sql` (pgvector + tablas)
2. `migrations/p03_002_rls.sql` (RLS: anon/publishable no ve nada; el dueño autenticado solo lo suyo)
3. `migrations/p03_003_busqueda_vectorial.sql` (`p03_match_chunks`, con `tenant_id` en la consulta)

Estado honesto: la app corre y se probó contra SQLite local. NO se probó contra Supabase.
El agente necesita escribir sesiones/mensajes/idempotencia/chunks desde el servidor; con solo la clave
publishable y RLS estricta eso no es posible sin un usuario autenticado (dueño) o una clave de servidor
(que no se usa ni se pide). Mapeo: SQLite `tenants/chunks/sessions/...` = `p03_tenants/p03_chunks/...`.
Un adaptador `db_supabase.py` (JWT del dueño por sesión + RPC `p03_match_chunks`) queda como pendiente.
