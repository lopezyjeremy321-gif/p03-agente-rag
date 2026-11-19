"""Servidor HTTP (stdlib). Rutas: widget estático, /api/chat, /api/handoff, /api/ingest, /webhook/whatsapp."""
import hashlib
import hmac
import json
import mimetypes
import secrets
import threading
import time
import urllib.request
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import agent, config, db, ingest
from .logs import get_logger

log = get_logger()

SEC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                                "font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; "
                                "frame-ancestors 'none'"),
}


class RateLimiter:
    def __init__(self, limit, window=60.0):
        self.limit, self.window, self.hits, self.lock = limit, window, defaultdict(deque), threading.Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False, max(1, int(self.window - (now - q[0])))
            q.append(now)
            return True, 0


LIMITER = RateLimiter(config.RATE_LIMIT_PER_MIN)


def verify_turnstile(token: str, ip: str) -> bool:
    if not config.TURNSTILE_SECRET:
        return True  # desactivado en local (pendiente de Luis: cuenta de Cloudflare)
    try:
        data = ("secret=%s&response=%s&remoteip=%s" % (config.TURNSTILE_SECRET, token, ip)).encode()
        req = urllib.request.Request("https://challenges.cloudflare.com/turnstile/v0/siteverify", data=data)
        with urllib.request.urlopen(req, timeout=8) as r:
            return bool(json.loads(r.read()).get("success"))
    except Exception:
        return False


def wa_signature(body: bytes, secret: str | None = None) -> str:
    return "sha256=" + hmac.new((secret or config.WA_APP_SECRET).encode(), body, hashlib.sha256).hexdigest()


class Handler(BaseHTTPRequestHandler):
    server_version = "p03"
    sys_version = ""

    # ---------- utilidades ----------
    def log_message(self, fmt, *args):
        log.info("http %s %s", self.command, urlsplit(self.path).path)  # sin query ni cuerpo

    def _cors(self):
        origin = self.headers.get("Origin")
        if origin and origin in config.ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def _send(self, status, payload, ctype="application/json; charset=utf-8", extra=None):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if ctype.startswith("application/json") else "public, max-age=300")
        for k, v in SEC_HEADERS.items():
            self.send_header(k, v)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _err(self, status, code, extra=None):
        self._send(status, {"error": code}, extra=extra)  # errores genéricos, sin stack

    def _body(self, limit):
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if n < 0 or n > limit:
            left = min(max(n, 0), 8 * 1024 * 1024)  # se vacía (hasta un tope) para poder responder 413 sin cortar la conexión
            while left > 0:
                chunk = self.rfile.read(min(65536, left))
                if not chunk:
                    break
                left -= len(chunk)
            self.close_connection = True
            return None
        return self.rfile.read(n)

    def _client(self):
        return self.client_address[0]

    def _origin_ok(self):
        o = self.headers.get("Origin")
        return o is None or o in config.ALLOWED_ORIGINS

    # ---------- métodos ----------
    def do_OPTIONS(self):
        if not self._origin_ok():
            return self._err(403, "origen_no_permitido")
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        u = urlsplit(self.path)
        if u.path == "/api/health":
            return self._send(200, {"ok": True, "wa_test_mode": config.WA_TEST_MODE})
        if u.path == "/webhook/whatsapp":
            q = parse_qs(u.query)
            if q.get("hub.mode") == ["subscribe"] and q.get("hub.verify_token") and \
                    hmac.compare_digest(q["hub.verify_token"][0], config.WA_VERIFY_TOKEN):
                return self._send(200, (q.get("hub.challenge", [""])[0][:64]).encode(), "text/plain; charset=utf-8")
            return self._err(403, "verificacion_fallida")
        return self._static(u.path)

    def _static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        rel = path.lstrip("/")
        f = (config.WEB_DIR / rel).resolve()
        if config.WEB_DIR.resolve() not in f.parents or not f.is_file():
            return self._err(404, "no_encontrado")
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, f.read_bytes(), ctype)

    def do_POST(self):
        path = urlsplit(self.path).path
        ok, retry = LIMITER.allow(self._client())  # primero el límite: nada cuesta antes de pasarlo
        if not ok:
            return self._err(429, "demasiadas_solicitudes", {"Retry-After": str(retry)})
        try:
            if path == "/api/chat":
                return self._chat()
            if path == "/api/handoff":
                return self._handoff()
            if path == "/api/ingest":
                return self._ingest()
            if path == "/webhook/whatsapp":
                return self._whatsapp()
        except Exception as e:  # nunca devolver stack al cliente
            log.error("error_interno ruta=%s tipo=%s", path, type(e).__name__)
            return self._err(500, "error_interno")
        return self._err(404, "no_encontrado")

    # ---------- /api/chat ----------
    def _json_body(self, allowed):
        if not self._origin_ok():
            self._err(403, "origen_no_permitido")
            return None
        raw = self._body(config.MAX_BODY_BYTES)
        if raw is None:
            self._err(413, "cuerpo_demasiado_grande")
            return None
        try:
            d = json.loads(raw)
        except Exception:
            self._err(400, "solicitud_no_valida")
            return None
        if not isinstance(d, dict) or set(d) - allowed:  # esquema estricto: sin campos extra (p. ej. 'role' o 'history')
            self._err(400, "solicitud_no_valida")
            return None
        return d

    def _chat(self):
        d = self._json_body({"tenant", "session_id", "message", "turnstile_token"})
        if d is None:
            return
        msg, tenant_id, sid = d.get("message"), d.get("tenant"), d.get("session_id")
        if not isinstance(msg, str) or not isinstance(tenant_id, str) or not msg.strip() or \
                (sid is not None and not isinstance(sid, str)):
            return self._err(400, "solicitud_no_valida")
        if len(msg) > config.MAX_QUESTION_CHARS:
            return self._err(413, "mensaje_demasiado_largo")
        if not verify_turnstile(str(d.get("turnstile_token", "")), self._client()):
            return self._err(403, "verificacion_humana_fallida")
        con = db.connect()
        try:
            if not db.get_tenant(con, tenant_id):
                return self._err(404, "negocio_desconocido")
            if sid:
                row = con.execute("SELECT tenant_id, msg_count FROM sessions WHERE id=?", (sid,)).fetchone()
                if not row or row["tenant_id"] != tenant_id:
                    return self._err(403, "sesion_no_valida")
            else:
                sid = secrets.token_urlsafe(24)
                con.execute("INSERT INTO sessions(id,tenant_id,created) VALUES(?,?,?)", (sid, tenant_id, time.time()))
                con.commit()
                row = {"msg_count": 0}
            if row["msg_count"] >= config.SESSION_MSG_CAP:
                return self._err(429, "limite_de_sesion", {"Retry-After": "3600"})
            res = agent.answer(con, tenant_id, msg.strip(), session_id=sid)
        finally:
            con.close()
        out = {k: res[k] for k in ("answer", "citations", "answerable", "handoff", "booking")}
        out["session_id"] = sid
        self._send(200, out)

    def _handoff(self):
        d = self._json_body({"tenant", "session_id"})
        if d is None:
            return
        con = db.connect()
        try:
            row = con.execute("SELECT tenant_id FROM sessions WHERE id=?", (str(d.get("session_id", "")),)).fetchone()
            if not row or row["tenant_id"] != d.get("tenant"):
                return self._err(403, "sesion_no_valida")
            con.execute("INSERT INTO handoffs(tenant_id,session_id,ts) VALUES(?,?,?)",
                        (row["tenant_id"], d["session_id"], time.time()))
            con.commit()
            t = db.get_tenant(con, row["tenant_id"])
            log.info("handoff tenant=%s", row["tenant_id"])
            self._send(200, {"ok": True, "message": t["handoff_text"] or "Una persona del equipo te escribirá pronto."})
        finally:
            con.close()

    # ---------- /api/ingest (solo el dueño autenticado) ----------
    def _ingest(self):
        auth = self.headers.get("Authorization", "")
        tenant_id = self.headers.get("X-Tenant", "")
        tok = auth[7:] if auth.startswith("Bearer ") else ""
        con = db.connect()
        try:
            t = db.get_tenant(con, tenant_id) if tenant_id else None
            if not tok or not t or not hmac.compare_digest(db.hash_token(tok), t["owner_token_hash"]):
                return self._err(401, "no_autorizado")  # token de otro tenant también cae aquí
            raw = self._body(config.MAX_UPLOAD_BYTES)
            if raw is None:
                return self._err(413, "archivo_demasiado_grande")
            fname = (self.headers.get("X-Filename") or "doc.pdf")[:80]
            try:
                info = ingest.ingest_document(con, tenant_id, fname, raw, self.headers.get("X-Title"))
            except ingest.IngestError as e:
                return self._err(e.status, e.code)
            self._send(200, info)
        finally:
            con.close()

    # ---------- /webhook/whatsapp ----------
    def _whatsapp(self):
        raw = self._body(config.MAX_WEBHOOK_BYTES)
        if raw is None:
            return self._err(413, "cuerpo_demasiado_grande")
        sig = self.headers.get("X-Hub-Signature-256", "")
        if not sig or not hmac.compare_digest(sig, wa_signature(raw)):
            log.warning("webhook_firma_invalida")
            return self._err(401, "firma_invalida")
        try:
            payload = json.loads(raw)
            changes = [c for e in payload.get("entry", []) for c in e.get("changes", [])]
        except Exception:
            return self._err(400, "solicitud_no_valida")
        processed, dups, replies = 0, 0, []
        con = db.connect()
        try:
            for ch in changes:
                val = ch.get("value", {})
                pnid = (val.get("metadata") or {}).get("phone_number_id")
                t = con.execute("SELECT id FROM tenants WHERE wa_phone_number_id=?", (pnid,)).fetchone() if pnid else None
                if not t:
                    continue
                for m in val.get("messages", []):
                    mid, sender = m.get("id"), str(m.get("from", ""))
                    text = (m.get("text") or {}).get("body") if m.get("type") == "text" else None
                    if not isinstance(mid, str) or not text or not sender:
                        continue
                    cur = con.execute("INSERT OR IGNORE INTO processed_messages(message_id,tenant_id,ts) VALUES(?,?,?)",
                                      (mid, t["id"], time.time()))
                    con.commit()
                    if cur.rowcount == 0:  # idempotencia: mismo message.id -> 1 sola respuesta
                        dups += 1
                        continue
                    sid = "wa-" + hmac.new(config.WA_APP_SECRET.encode(), (t["id"] + sender).encode(),
                                           hashlib.sha256).hexdigest()[:24]  # el teléfono nunca se guarda ni se loguea
                    if not con.execute("SELECT 1 FROM sessions WHERE id=?", (sid,)).fetchone():
                        con.execute("INSERT INTO sessions(id,tenant_id,created) VALUES(?,?,?)", (sid, t["id"], time.time()))
                        con.commit()
                    res = agent.answer(con, t["id"], text[:config.MAX_QUESTION_CHARS], session_id=sid)
                    reply = res["answer"] + (f"\nReserva aquí: {res['booking']['url']}" if res.get("booking") else "")
                    processed += 1
                    # MODO PRUEBA: no se envía nada a Meta; la respuesta queda en la respuesta HTTP.
                    replies.append({"to": sid, "text": reply, "message_id": mid})
        finally:
            con.close()
        self._send(200, {"processed": processed, "duplicates": dups, "replies": replies, "test_mode": config.WA_TEST_MODE})


def make_server(host=None, port=None):
    return ThreadingHTTPServer((host or config.HOST, port if port is not None else config.PORT), Handler)


def main():
    con = db.connect()
    db.purge_old(con)
    con.close()
    srv = make_server()
    log.info("servidor_iniciado puerto=%s", config.PORT)
    print(f"P03 escuchando en http://{config.HOST}:{config.PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
