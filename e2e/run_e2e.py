"""E2E en navegador real (Playwright/Chromium): las 30 preguntas por el widget + capturas + prueba de salida como texto.
Uso: python e2e/run_e2e.py --base http://127.0.0.1:3132 --mock http://127.0.0.1:3133
(base = servidor real con Groq; mock = servidor con LLM simulado hostil para probar el renderizado como texto)."""
import argparse
import csv
import json
import os
import pathlib
import sys
import unicodedata

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", r"D:\ClaudeBrain\cache\ms-playwright")
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "capturas"
SHOTS.mkdir(parents=True, exist_ok=True)


def norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def last_agent(page):
    return page.locator(".p03w-agent").last


def ask(page, text):
    n = page.locator(".p03w-agent").count()
    page.fill("#p03w-input", text)
    page.click("button[type=submit]")
    page.wait_for_function("(n) => document.querySelectorAll('.p03w-agent').length > n", arg=n, timeout=120000)
    page.wait_for_function("() => document.querySelector('.p03w-log').getAttribute('aria-busy') === 'false'", timeout=120000)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--mock", required=True)
    a = ap.parse_args()
    spec = json.loads((ROOT / "evals" / "questions.json").read_text(encoding="utf-8"))
    rows, console_errors = [], []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        page.goto(a.base)
        page.screenshot(path=str(SHOTS / "01-sitio-desktop.png"))
        page.click("#abrir-chat")
        page.wait_for_selector(".p03w-panel.is-open")
        assert page.evaluate("document.activeElement.id") == "p03w-input", "foco no va al input"
        page.screenshot(path=str(SHOTS / "02-widget-abierto-desktop.png"))
        # a11y básicas
        assert page.get_attribute(".p03w-log", "role") == "log"
        assert page.get_attribute(".p03w-log", "aria-live") == "polite"
        assert page.get_attribute(".p03w-launcher", "aria-expanded") == "true"
        for i, q in enumerate(spec["questions"]):
            ask(page, q["q"])
            m = last_agent(page)
            text = m.locator(".p03w-text").inner_text()
            ncit = m.locator(".p03w-cite").count()
            refuse = norm(text).startswith("no lo se")
            t = norm(text)
            if q["type"] == "answer":
                ok = (not refuse) and ncit > 0 and all(any(norm(x) in t for x in mm.split("|")) for mm in q.get("must", []))
            elif q["type"] == "refuse":
                ok = refuse and ncit == 0
            else:
                ok = True
            ok = ok and not any(norm(f) in t for f in q.get("forbid", []))
            handoff_btn = m.get_by_role("button", name="Hablar con una persona").count()
            rows.append({"id": q["id"], "pregunta": q["q"], "respuesta_en_pantalla": text.replace("\n", " "), "chips_de_fuente": ncit,
                         "boton_humano": handoff_btn, "ok_en_navegador": ok})
            if q["id"] == "R01":
                m.locator(".p03w-cite").first.click()
                page.screenshot(path=str(SHOTS / "03-respuesta-con-cita-desktop.png"))
            if q["id"] == "U01":
                page.screenshot(path=str(SHOTS / "04-no-lo-se-traspaso-desktop.png"))
        # reserva: botón con enlace
        ask(page, "Quiero reservar un corte de mujer")
        book = last_agent(page).locator("a.p03w-book")
        assert book.count() == 1 and "reserva-demo.html" in book.get_attribute("href"), "sin botón de reserva"
        book_label = book.inner_text()
        page.screenshot(path=str(SHOTS / "05-reserva-desktop.png"))
        # handoff real
        page.click("text=Pasar a humano")
        page.wait_for_function("() => document.querySelector('.p03w-log').innerText.includes('WhatsApp')", timeout=15000)
        # Esc cierra y devuelve foco
        page.keyboard.press("Escape")
        page.wait_for_function("() => document.querySelector('.p03w-panel').hidden === true", timeout=5000)
        assert page.evaluate("document.activeElement.className").startswith("p03w-launcher"), "Esc no devolvió el foco"
        # error de red con reintento (se corta la red)
        page.click(".p03w-launcher")
        ctx.set_offline(True)
        page.fill("#p03w-input", "¿Cuánto cuesta el corte de hombre?")
        page.click("button[type=submit]")
        page.wait_for_selector(".p03w-error")
        page.screenshot(path=str(SHOTS / "06-error-red-reintentar-desktop.png"))
        ctx.set_offline(False)
        page.click("text=Reintentar pregunta")
        page.wait_for_function("() => document.querySelector('.p03w-log').getAttribute('aria-busy') === 'false' && !document.querySelector('.p03w-error')", timeout=120000)
        # móvil 390
        mctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, has_touch=True, is_mobile=True)
        mp = mctx.new_page()
        mp.on("console", lambda m: console_errors.append("[móvil] " + m.text) if m.type == "error" else None)
        mp.goto(a.base)
        mp.screenshot(path=str(SHOTS / "07-sitio-movil.png"))
        mp.click(".p03w-launcher")
        mp.wait_for_selector(".p03w-panel.is-open")
        mp.screenshot(path=str(SHOTS / "08-widget-abierto-movil.png"))
        ask(mp, "¿Cuánto cuesta un corte de mujer?")
        mp.locator(".p03w-cite").first.click()
        mp.screenshot(path=str(SHOTS / "09-respuesta-con-cita-movil.png"))
        overflow = mp.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        # URL de 2000 caracteres y emoji (break-ui): se acepta o se rechaza con aviso, sin romper el layout
        mp.fill("#p03w-input", "https://ejemplo.invalid/" + "a" * 470 + " 😀")
        mp.keyboard.press("Enter")
        mp.wait_for_function("() => document.querySelector('.p03w-log').getAttribute('aria-busy') === 'false'", timeout=120000)
        overflow2 = mp.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        mp.screenshot(path=str(SHOTS / "10-url-larga-emoji-movil.png"))
        # tamaño de objetivos táctiles (≥44 px) y fuente del input (≥16 px)
        small = mp.evaluate("""() => [...document.querySelectorAll('.p03w button, .p03w a, .p03w textarea')].filter(e => e.offsetParent !== null).map(e => {const r = e.getBoundingClientRect(); return [e.className, Math.round(r.width), Math.round(r.height)]}).filter(x => x[2] < 44)""")
        fs = mp.evaluate("parseFloat(getComputedStyle(document.querySelector('#p03w-input')).fontSize)")
        # salida hostil como texto (servidor con LLM simulado)
        xp = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
        dialogs = []
        xp.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
        xp.goto(a.mock)
        xp.click("#abrir-chat")
        xp.wait_for_selector(".p03w-panel.is-open")
        ask(xp, "¿Qué precio tiene hoy el corte de cabello para mujer? (prueba hostil)")
        txt = last_agent(xp).locator(".p03w-text").inner_text()
        xss = {"img_en_dom": xp.locator(".p03w-log img").count(), "script_en_dom": xp.locator(".p03w-log script").count(),
               "enlaces_en_respuesta": xp.locator(".p03w-agent .p03w-text a").count(), "dialogos": len(dialogs),
               "texto_literal": ("<img" in txt and "javascript:alert(1)" in txt)}
        xp.screenshot(path=str(SHOTS / "11-salida-hostil-como-texto.png"))
        b.close()
    console_errors = [e for e in console_errors if "ERR_INTERNET_DISCONNECTED" not in e]  # provocado a propósito en la prueba de red
    ok = sum(1 for r in rows if r["ok_en_navegador"])
    out = ROOT / "e2e" / "results"
    out.mkdir(exist_ok=True)
    with open(out / "e2e-30-preguntas.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summary = {"preguntas_ok_en_navegador": f"{ok}/{len(rows)}", "errores_de_consola": console_errors, "boton_reserva": book_label,
               "scroll_horizontal_movil": [overflow, overflow2], "objetivos_menores_44px_movil": small, "fuente_input_px": fs, "xss": xss}
    (out / "e2e-resumen.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    bad = (xss["img_en_dom"] or xss["script_en_dom"] or xss["dialogos"] or not xss["texto_literal"] or console_errors)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
