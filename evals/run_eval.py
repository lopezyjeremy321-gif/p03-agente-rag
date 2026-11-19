"""Ejecuta las 30 preguntas. Modos: real (pipeline completo), oracle (respuestas doradas), null (siempre «No lo sé»).
Uso: python evals/run_eval.py --mode real --label groq   |   --mode oracle   |   --mode null
Salida: evals/results/eval-<label>.csv y .md (tabla real, sin retocar)."""
import argparse
import csv
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))
from p03 import agent, db  # noqa: E402
from grade import grade, wilson  # noqa: E402

RES = ROOT / "evals" / "results"
RES.mkdir(exist_ok=True)


def load_chunks(con, tenant):
    return {r["chunk_id"]: {"doc_id": r["doc_id"], "text": r["text"]}
            for r in con.execute("SELECT chunk_id, doc_id, text FROM chunks WHERE tenant_id=?", (tenant,))}


def respond(mode, con, tenant, q, chunks):
    if mode == "oracle":
        g = q.get("gold")
        if g:
            return {"answer": g["answer"], "citations": g["citations"], "answerable": True, "retrieved": list(chunks), "meta": {}}
    if mode in ("oracle", "null"):
        return {"answer": agent.REFUSAL.format(name="Peluquería Mirlo"), "citations": [], "answerable": False,
                "retrieved": list(chunks), "meta": {}}
    r = agent.answer(con, tenant, q["q"], use_cache=False)
    return {"answer": r["answer"], "citations": [c["id"] for c in r["citations"]], "answerable": r["answerable"],
            "retrieved": r["meta"]["retrieved"], "meta": r["meta"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="real", choices=["real", "oracle", "null"])
    ap.add_argument("--label", default=None)
    ap.add_argument("--pause", type=float, default=1.0)
    a = ap.parse_args()
    label = a.label or a.mode
    spec = json.loads((ROOT / "evals" / "questions.json").read_text(encoding="utf-8"))
    con = db.connect()
    chunks = load_chunks(con, spec["tenant"])
    rows = []
    for q in spec["questions"]:
        r = respond(a.mode, con, spec["tenant"], q, chunks)
        g = grade(q, r, chunks)
        m = r["meta"]
        rows.append({"id": q["id"], "categoria": q["cat"], "pregunta": q["q"], "esperado": q["expected"],
                     "respuesta": r["answer"], "citas": " ".join(r["citations"]),
                     "doc_correcto": g["doc_ok"], "cita_valida": g["cite_ok"], "fundamentada": g["grounded"],
                     "rechazo_correcto": g["refusal_ok"], "sin_prohibido": g["forbid_ok"],
                     "latencia_ms": m.get("latency_ms", ""), "tokens": (m.get("tokens_in", 0) or 0) + (m.get("tokens_out", 0) or 0)
                     if m else "", "modelo": m.get("model") or a.mode, "motivo": m.get("reason", ""),
                     "acierto": g["pass"]})
        if a.mode == "real":
            time.sleep(a.pause)
    csv_p = RES / f"eval-{label}.csv"
    with open(csv_p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    write_md(RES / f"eval-{label}.md", label, rows)
    n_ok = sum(1 for r in rows if r["acierto"])
    print(f"{label}: {n_ok}/{len(rows)}")


def write_md(path, label, rows):
    n = len(rows)
    ok = sum(1 for r in rows if r["acierto"])
    lo, hi = wilson(ok, n)
    cats = {}
    for r in rows:
        c = cats.setdefault(r["categoria"], [0, 0])
        c[1] += 1
        c[0] += 1 if r["acierto"] else 0
    L = [f"# Evaluación P03 ({label})", "",
         f"**Aciertos: {ok}/{n}** (IC 95% Wilson {lo*100:.0f}%-{hi*100:.0f}%). Con N=30 el margen es de ±18 puntos: "
         "diferencias menores entre corridas no son concluyentes.", "",
         "| categoría | aciertos |", "|---|---|"]
    L += [f"| {c} | {k}/{t} |" for c, (k, t) in cats.items()]
    L += ["", "| id | cat | pregunta | esperado | respuesta | citas | doc | cita válida | fundam. | rechazo | ms | tokens | modelo | acierto |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    f = lambda v: "-" if v in (None, "") else ("sí" if v is True else "no" if v is False else str(v))
    for r in rows:
        esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
        L.append("| " + " | ".join([r["id"], r["categoria"], esc(r["pregunta"]), esc(r["esperado"]), esc(r["respuesta"]),
                                    r["citas"] or "-", f(r["doc_correcto"]), f(r["cita_valida"]), f(r["fundamentada"]),
                                    f(r["rechazo_correcto"]), f(r["latencia_ms"]), f(r["tokens"]), esc(r["modelo"]),
                                    "**sí**" if r["acierto"] else "**NO**"]) + " |")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
