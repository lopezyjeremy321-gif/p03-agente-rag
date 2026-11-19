"""SQLite como almacén vectorial local. Toda consulta de datos lleva tenant_id."""
import hashlib
import secrets
import sqlite3
import time

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, owner_token_hash TEXT NOT NULL,
  wa_phone_number_id TEXT UNIQUE, handoff_text TEXT NOT NULL DEFAULT '', domain_note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS chunks(
  tenant_id TEXT NOT NULL, doc_id TEXT NOT NULL, chunk_idx INTEGER NOT NULL,
  chunk_id TEXT NOT NULL, title TEXT NOT NULL, page INTEGER NOT NULL,
  text TEXT NOT NULL, embedding BLOB NOT NULL,
  PRIMARY KEY(tenant_id, chunk_id));
CREATE INDEX IF NOT EXISTS ix_chunks_tenant ON chunks(tenant_id);
CREATE TABLE IF NOT EXISTS sessions(
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, created REAL NOT NULL, msg_count INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_messages_session ON messages(session_id, id);
CREATE TABLE IF NOT EXISTS processed_messages(
  message_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS handoffs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, session_id TEXT NOT NULL, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS embed_cache(k TEXT PRIMARY KEY, v BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS answer_cache(
  tenant_id TEXT NOT NULL, qhash TEXT NOT NULL, corpus TEXT NOT NULL, payload TEXT NOT NULL, ts REAL NOT NULL,
  PRIMARY KEY(tenant_id, qhash, corpus));
"""


def connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def hash_token(tok: str) -> str:
    return hashlib.sha256(tok.encode()).hexdigest()


def upsert_tenant(con, tenant_id, name, wa_phone_number_id=None, handoff_text="") -> str | None:
    """Crea el tenant si no existe y devuelve su token de dueño (solo la primera vez)."""
    row = con.execute("SELECT id FROM tenants WHERE id=?", (tenant_id,)).fetchone()
    if row:
        con.execute("UPDATE tenants SET name=?, wa_phone_number_id=?, handoff_text=? WHERE id=?",
                    (name, wa_phone_number_id, handoff_text, tenant_id))
        con.commit()
        return None
    tok = secrets.token_urlsafe(32)
    con.execute("INSERT INTO tenants(id,name,owner_token_hash,wa_phone_number_id,handoff_text) VALUES(?,?,?,?,?)",
                (tenant_id, name, hash_token(tok), wa_phone_number_id, handoff_text))
    con.commit()
    return tok


def get_tenant(con, tenant_id):
    return con.execute("SELECT * FROM tenants WHERE id=?", (tenant_id,)).fetchone()


def corpus_version(con, tenant_id) -> str:
    """Huella del corpus de un tenant (invalida la caché de respuestas al reingestar)."""
    h = hashlib.sha256()
    for r in con.execute("SELECT chunk_id, text FROM chunks WHERE tenant_id=? ORDER BY chunk_id", (tenant_id,)):
        h.update(r["chunk_id"].encode())
        h.update(r["text"].encode())
    return h.hexdigest()[:16]


def purge_old(con, max_age_s=24 * 3600):
    cutoff = time.time() - max_age_s
    con.execute("DELETE FROM messages WHERE ts<?", (cutoff,))
    con.execute("DELETE FROM sessions WHERE created<?", (cutoff,))
    con.commit()
