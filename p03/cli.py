"""CLI: python -m p03.cli seed | search <tenant> <pregunta> | ask <tenant> <pregunta>"""
import json
import sys

from . import agent, config, db, ingest, retrieve

TENANTS = {
    "mirlo": ("Peluquería Mirlo (demostración)", "100000000001",
              "Escríbenos por WhatsApp al 300 000 0000 (número ficticio de demostración) y una persona te atiende en horario de atención."),
    "aurelio": ("Barbería Don Aurelio (demostración)", "100000000002", "Una persona de la barbería te escribirá pronto."),
}


def seed():
    con = db.connect()
    tokens = {}
    for tid, (name, wa, hand) in TENANTS.items():
        tok = db.upsert_tenant(con, tid, name, wa, hand)
        if tok:
            tokens[tid] = tok
        for f in sorted((config.DOCS_DIR / tid).glob("*")):
            if f.suffix.lower() in (".pdf", ".txt"):
                info = ingest.ingest_document(con, tid, f.name, f.read_bytes(), f.stem.replace("-", " ").title())
                print(tid, f.name, info)
    if tokens:  # solo se muestran/guardan al crear el tenant; el archivo está en .gitignore
        p = config.DATA / "owner-tokens.local.json"
        old = json.loads(p.read_text()) if p.exists() else {}
        old.update(tokens)
        p.write_text(json.dumps(old, indent=2))
        print("tokens de dueño de prueba guardados en", p.name)
    con.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "seed":
        seed()
    elif cmd == "search":
        con = db.connect()
        for c in retrieve.search(con, sys.argv[2], " ".join(sys.argv[3:]), 6):
            print(round(c["score"], 3), c["chunk_id"], c["text"][:90])
    elif cmd == "ask":
        con = db.connect()
        r = agent.answer(con, sys.argv[2], " ".join(sys.argv[3:]), use_cache=False)
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(__doc__)
