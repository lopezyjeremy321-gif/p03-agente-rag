"""Búsqueda híbrida (vectorial + léxica, fusión RRF). El filtro tenant_id va DENTRO de la consulta SQL."""
import math
import re
import unicodedata

from . import config, embed

STOP = set("""cual cuales cuanto cuanta cuantos cuantas cuesta cuestan vale tiene tienen hacen hace puedo pueden como donde cuando
para sobre entre desde hasta esta estan este esos esas otro otra muy mas menos tambien hay son ser mis tus sus con sin por que
los las una uno unos unas del the voy llegar quiero quieres necesito algo tipo hacer hago favor""".split())


def _norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def _stems(text):
    return {w[:5] for w in re.findall(r"[a-z0-9]+", _norm(text)) if len(w) >= 4 and w not in STOP}


def search(con, tenant_id: str, query: str, k: int | None = None) -> list[dict]:
    k = k or config.TOP_K
    qv = embed.embed([query], "query")[0]
    rows = con.execute(
        "SELECT chunk_id, doc_id, title, page, text, embedding FROM chunks WHERE tenant_id = ?",
        (tenant_id,)).fetchall()
    items = [{"chunk_id": r["chunk_id"], "doc_id": r["doc_id"], "title": r["title"], "page": r["page"],
              "text": r["text"], "score": embed.dot(qv, embed.from_blob(r["embedding"]))} for r in rows]
    # léxico: tokens de la pregunta (prefijo de 5 letras) ponderados por IDF dentro del tenant
    qs = _stems(query)
    cs = [_stems(it["title"] + " " + it["text"]) for it in items]
    n = len(items) or 1
    for it, c in zip(items, cs):
        it["lex"] = sum(math.log(1 + n / (1 + sum(1 for x in cs if s in x))) for s in qs if s in c)
    by_vec = sorted(items, key=lambda x: -x["score"])
    by_lex = sorted(items, key=lambda x: -x["lex"])
    rv = {id(x): i for i, x in enumerate(by_vec)}
    rl = {id(x): i for i, x in enumerate(by_lex)}
    for it in items:
        it["rrf"] = 1 / (10 + rv[id(it)]) + (1 / (10 + rl[id(it)]) if it["lex"] > 0 else 0)
    items.sort(key=lambda x: -x["rrf"])
    return items[:k]
