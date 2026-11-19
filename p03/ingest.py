"""Ingesta de PDF/TXT. El contenido es NO CONFIABLE: se extrae solo texto (sin ejecutar nada) y con límites."""
import io
import re
import unicodedata

from . import config, db, embed


class IngestError(Exception):
    def __init__(self, code: str, status: int):
        super().__init__(code)
        self.code, self.status = code, status


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:40] or "doc"


def extract(data: bytes, filename: str) -> list[tuple[int, str]]:
    """Devuelve [(pagina, texto)]. Valida tamaño, tipo real (magic bytes) y número de páginas."""
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise IngestError("archivo_demasiado_grande", 413)
    if data[:5] == b"%PDF-":
        from pypdf import PdfReader
        try:
            rd = PdfReader(io.BytesIO(data))
            if rd.is_encrypted:
                raise IngestError("pdf_cifrado", 422)
            if len(rd.pages) > config.MAX_PDF_PAGES:
                raise IngestError("demasiadas_paginas", 413)
            pages = [(i + 1, (p.extract_text() or "")) for i, p in enumerate(rd.pages)]
        except IngestError:
            raise
        except Exception:
            raise IngestError("pdf_invalido", 422)
    elif filename.lower().endswith(".txt") and len(data) <= config.MAX_TXT_BYTES:
        try:
            pages = [(1, data.decode("utf-8"))]
        except UnicodeDecodeError:
            raise IngestError("codificacion_invalida", 422)
    else:
        raise IngestError("tipo_no_permitido", 415)
    return [(n, re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", t)) for n, t in pages]


_SENT = re.compile(r"(?<=[.!?\"»])\s+")


def chunk_page(text: str, max_chars=450) -> list[str]:
    """Empaqueta frases hasta ~max_chars con 1 frase de solape. Un hecho = una frase, así no se parten precios."""
    if "\nP:" in text or text.lstrip().startswith("P:"):  # FAQ: un par P/R por fragmento
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
        return [re.sub(r"\s*\n\s*", " ", b) for b in blocks]
    flat = re.sub(r"\s*\n\s*", " ", text).strip()
    sents = [s for s in _SENT.split(flat) if s]
    chunks, cur = [], []
    for s in sents:
        if cur and sum(len(x) + 1 for x in cur) + len(s) > max_chars:
            chunks.append(" ".join(cur))
            cur = cur[-1:]
        cur.append(s)
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def ingest_document(con, tenant_id: str, filename: str, data: bytes, title: str | None = None) -> dict:
    if not db.get_tenant(con, tenant_id):
        raise IngestError("tenant_desconocido", 404)
    pages = extract(data, filename)
    doc_id = slug(filename.rsplit(".", 1)[0])
    title = (title or filename.rsplit(".", 1)[0]).strip()[:120]
    pieces = []
    for page, text in pages:
        for c in chunk_page(text):
            pieces.append((page, c))
    if not pieces:
        raise IngestError("sin_texto", 422)
    vecs = embed.embed([f"{title}. {c}" for _, c in pieces], "document")
    con.execute("DELETE FROM chunks WHERE tenant_id=? AND doc_id=?", (tenant_id, doc_id))
    for i, ((page, c), v) in enumerate(zip(pieces, vecs)):
        con.execute("INSERT INTO chunks(tenant_id,doc_id,chunk_idx,chunk_id,title,page,text,embedding) VALUES(?,?,?,?,?,?,?,?)",
                    (tenant_id, doc_id, i, f"{doc_id}#{i}", title, page, c, embed.to_blob(v)))
    con.commit()
    return {"doc_id": doc_id, "chunks": len(pieces), "pages": len(pages)}
