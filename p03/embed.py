"""Embeddings: nomic-embed-text en el Ollama local. P03_EMBED=fake usa un hash de palabras (solo pruebas unitarias)."""
import array
import hashlib
import json
import math
import os
import re
import urllib.request

from . import config


def _norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _fake(text: str, dim=256):
    v = [0.0] * dim
    for w in re.findall(r"\w+", text.lower()):
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        v[h % dim] += 1.0
    return _norm(v)


def embed(texts: list[str], kind: str) -> list[list[float]]:
    """kind: 'document' o 'query' (nomic exige el prefijo). Caché persistente por texto (el Ollama es compartido y a veces lento)."""
    if os.environ.get("P03_EMBED") == "fake":
        return [_fake(t) for t in texts]
    from . import db
    con = db.connect()
    keys = [hashlib.sha256(f"{config.OLLAMA_EMBED_MODEL}|{kind}|{t}".encode()).hexdigest() for t in texts]
    got = {}
    for k in keys:
        r = con.execute("SELECT v FROM embed_cache WHERE k=?", (k,)).fetchone()
        if r:
            got[k] = list(from_blob(r["v"]))
    miss = [i for i, k in enumerate(keys) if k not in got]
    if miss:
        new = _ollama_embed([texts[i] for i in miss], kind)
        for i, v in zip(miss, new):
            got[keys[i]] = v
            con.execute("INSERT OR REPLACE INTO embed_cache(k,v) VALUES(?,?)", (keys[i], to_blob(v)))
        con.commit()
    con.close()
    return [got[k] for k in keys]


def _ollama_embed(texts, kind):
    prefix = "search_document: " if kind == "document" else "search_query: "
    body = json.dumps({"model": config.OLLAMA_EMBED_MODEL, "input": [prefix + t for t in texts], "keep_alive": "60m"}).encode()
    req = urllib.request.Request(config.OLLAMA_URL + "/api/embed", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        data = json.loads(r.read())
    return [_norm(e) for e in data["embeddings"]]


def to_blob(v) -> bytes:
    return array.array("f", v).tobytes()


def from_blob(b: bytes):
    a = array.array("f")
    a.frombytes(b)
    return a


def dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))
