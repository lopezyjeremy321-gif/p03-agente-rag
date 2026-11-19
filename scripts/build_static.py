"""Genera dist-static/: front estático con RESPUESTAS PREGRABADAS (las de la evaluación real). Sin claves, sin backend.
Uso: python scripts/build_static.py evals/results/eval-groq.csv"""
import csv
import json
import pathlib
import shutil
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "dist-static"
src = pathlib.Path(sys.argv[1])
if OUT.exists():
    shutil.rmtree(OUT)
shutil.copytree(ROOT / "web", OUT, ignore=shutil.ignore_patterns("reserva-demo.html"))
db = sqlite3.connect(ROOT / "data" / "p03.db")
chunks = {r[0]: (r[1], r[2], r[3]) for r in db.execute("select chunk_id,title,page,text from chunks where tenant_id='mirlo'")}
items = []
for row in csv.DictReader(open(src, encoding="utf-8")):
    cits = [{"id": c, "title": chunks[c][0], "page": chunks[c][1], "snippet": chunks[c][2][:240]} for c in row["citas"].split() if c in chunks]
    answerable = row["respuesta"].lower().startswith("no lo s") is False
    items.append({"q": row["pregunta"], "answer": row["respuesta"], "citations": cits, "answerable": answerable,
                  "handoff": not answerable, "booking": None})
items.append({"q": "Quiero reservar un corte de mujer", "answer": "Puedes reservar con el botón de abajo. En esta demostración el enlace es de ejemplo.",
              "citations": [], "answerable": True, "handoff": False,
              "booking": {"label": "Reservar corte (demostración)", "url": "https://example.com/", "demo": True}})
fallback = {"answer": "Esta demostración estática solo tiene respuestas pregrabadas para las preguntas sugeridas y las de la evaluación. Para preguntar libremente hay que ejecutar el servidor local.",
            "citations": [], "answerable": False, "handoff": False, "booking": None}
(OUT / "replay.json").write_text(json.dumps({"items": items, "fallback": fallback}, ensure_ascii=False), encoding="utf-8")
idx = (OUT / "index.html").read_text(encoding="utf-8")
idx = idx.replace('data-api="" defer', 'data-mode="replay" data-replay="replay.json" defer')
idx = idx.replace("Sitio de demostración: el negocio, los precios y los datos son ficticios.",
                  "Sitio de demostración con respuestas pregrabadas: el negocio, los precios y los datos son ficticios.")
(OUT / "index.html").write_text(idx, encoding="utf-8")
(OUT / "vercel.json").write_text(json.dumps({"headers": [{"source": "/(.*)", "headers": [
    {"key": "X-Content-Type-Options", "value": "nosniff"}, {"key": "Referrer-Policy", "value": "no-referrer"},
    {"key": "Content-Security-Policy", "value": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"}]}]}, indent=1), encoding="utf-8")
print("dist-static listo:", len(items), "respuestas")
