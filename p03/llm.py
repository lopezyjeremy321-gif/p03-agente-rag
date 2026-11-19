"""Proveedores de generación con respaldo: Groq -> Ollama local. La clave de Groq se lee del entorno al llamar."""
import json
import os
import time
import urllib.error
import urllib.request

from . import config
from .logs import get_logger

log = get_logger()


class LLMError(Exception):
    pass


def _post(url, body, headers, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _groq(system, user):
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        raise LLMError("sin_clave_groq")
    last = None
    for model in config.GROQ_MODELS:  # varios modelos de Groq: cada uno tiene su propia cuota diaria
        body = {"model": model, "temperature": 0, "max_completion_tokens": config.LLM_MAX_TOKENS,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if "gpt-oss" in model:
            body["reasoning_effort"] = "low"
        for attempt in range(4):
            try:
                d = _post("https://api.groq.com/openai/v1/chat/completions", body,
                          {"Content-Type": "application/json", "Authorization": "Bearer " + key,
                           "User-Agent": "p03-rag-demo/1.0"}, timeout=45)
                u = d.get("usage", {})
                return d["choices"][0]["message"]["content"] or "", {
                    "model": "groq:" + model, "tokens_in": u.get("prompt_tokens", 0),
                    "tokens_out": u.get("completion_tokens", 0)}
            except urllib.error.HTTPError as e:
                last = e.code
                detail = ""
                try:
                    detail = e.read()[:300].decode("utf-8", "ignore")
                except Exception:
                    pass
                log.warning("groq_http modelo=%s %s %s", model, e.code, detail[:160])
                if e.code == 429 and "per day" not in detail and attempt < 3:  # límite por minuto: esperar
                    time.sleep(min(float(e.headers.get("retry-after", "3") or 3), 20) + 1)
                    continue
                break  # cuota diaria u otro error: probar el siguiente modelo
            except Exception as e:  # red, timeout
                last = type(e).__name__
                time.sleep(1)
    raise LLMError(f"groq_fallo_{last}")


def _ollama(system, user):
    body = {"model": config.OLLAMA_CHAT_MODEL, "stream": False, "format": "json",
            "options": {"temperature": 0, "num_predict": 500},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    try:
        d = _post(config.OLLAMA_URL + "/api/chat", body, {"Content-Type": "application/json"}, timeout=120)
    except Exception as e:
        raise LLMError("ollama_fallo_" + type(e).__name__)
    return d["message"]["content"], {"model": "ollama:" + config.OLLAMA_CHAT_MODEL,
                                     "tokens_in": d.get("prompt_eval_count", 0), "tokens_out": d.get("eval_count", 0)}


def _mock(system, user):
    """Solo pruebas. Devuelve salida hostil con una cita válida para probar el renderizado como texto."""
    import re
    ids = re.findall(r'<fragmento id="([^"]+)"', user)
    out = {"answer": "<img src=//x.invalid/p.png onerror=alert(1)> **negrita** [clic](javascript:alert(1)) <script>1</script>",
           "citations": ids[:1], "answerable": bool(ids)}
    return json.dumps(out), {"model": "mock", "tokens_in": 0, "tokens_out": 0}


PROVIDERS = {"groq": _groq, "ollama": _ollama, "mock": _mock}


def generate(system: str, user: str):
    errors = []
    for name in config.LLM_CHAIN:
        try:
            text, meta = PROVIDERS[name](system, user)
            meta["fallbacks"] = errors
            return text, meta
        except LLMError as e:
            errors.append(str(e))
            log.warning("llm_fallo proveedor=%s causa=%s", name, e)
    raise LLMError(",".join(errors) or "sin_proveedores")
