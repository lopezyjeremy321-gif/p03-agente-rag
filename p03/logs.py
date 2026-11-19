"""Logging sin PII: redacta teléfonos, correos y tokens; el código nunca registra el texto del cliente."""
import logging
import re

from . import config

_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [token]"),
    (re.compile(r"(?i)(sha256=)[0-9a-f]{16,}"), r"\1[hmac]"),
    (re.compile(r"\+?\d[\d\s().-]{6,}\d"), "[tel]"),
]


def redact(text: str) -> str:
    for rx, rep in _PATTERNS:
        text = rx.sub(rep, text)
    return text


class _RedactFilter(logging.Filter):
    def filter(self, record):
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def get_logger() -> logging.Logger:
    lg = logging.getLogger("p03")
    if not lg.handlers:
        lg.setLevel(logging.INFO)
        config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        h = logging.FileHandler(config.LOG_PATH, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        h.addFilter(_RedactFilter())
        lg.addHandler(h)
        lg.propagate = False
    return lg
