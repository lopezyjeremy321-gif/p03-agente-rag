"""Configuración. Todo sale de variables de entorno; ninguna clave se guarda en archivos."""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = pathlib.Path(os.environ.get("P03_DATA_DIR", ROOT / "data"))
DB_PATH = pathlib.Path(os.environ.get("P03_DB", DATA / "p03.db"))
LOG_PATH = pathlib.Path(os.environ.get("P03_LOG", DATA / "p03.log"))
WEB_DIR = ROOT / "web"
DOCS_DIR = ROOT / "data" / "docs"

HOST = os.environ.get("P03_HOST", "127.0.0.1")
PORT = int(os.environ.get("P03_PORT", "3130"))
PUBLIC_BASE = os.environ.get("P03_PUBLIC_BASE", f"http://127.0.0.1:{PORT}")
ALLOWED_ORIGINS = {o.strip() for o in os.environ.get(
    "P03_ALLOWED_ORIGINS", f"http://127.0.0.1:{PORT},http://localhost:{PORT}").split(",") if o.strip()}

# Proveedores LLM (cadena de respaldo). La clave de Groq SOLO se lee del entorno en tiempo de ejecución.
LLM_CHAIN = [p.strip() for p in os.environ.get("P03_LLM_CHAIN", "groq,ollama").split(",") if p.strip()]
if os.environ.get("P03_LLM_PROVIDER"):  # atajo para pruebas: mock / ollama / groq
    LLM_CHAIN = [os.environ["P03_LLM_PROVIDER"]]
GROQ_MODELS = [m.strip() for m in os.environ.get("GROQ_MODELS", "openai/gpt-oss-120b,openai/gpt-oss-20b").split(",") if m.strip()]
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_CHAT_MODEL = os.environ.get("OLLAMA_CHAT_MODEL", "llama3.2:3b")
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")

# Recuperación
TOP_K = int(os.environ.get("P03_TOP_K", "5"))
MIN_SCORE = float(os.environ.get("P03_MIN_SCORE", "0.60"))  # umbral coseno; calibrado en evals/dev_queries.json

# Límites (control de recursos)
MAX_QUESTION_CHARS = 500
MAX_BODY_BYTES = 8 * 1024
MAX_WEBHOOK_BYTES = 64 * 1024
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_PDF_PAGES = 10
MAX_TXT_BYTES = 200 * 1024
RATE_LIMIT_PER_MIN = int(os.environ.get("P03_RATE_LIMIT", "200"))
SESSION_MSG_CAP = int(os.environ.get("P03_SESSION_CAP", "60"))
LLM_MAX_TOKENS = 1200

# WhatsApp (modo prueba: sin credenciales de Meta). El secreto de prueba NO es una credencial real.
WA_APP_SECRET = os.environ.get("WHATSAPP_APP_SECRET", "") or "p03-demo-secret-not-for-production"
WA_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "") or "p03-demo-verify"
WA_TEST_MODE = not os.environ.get("WHATSAPP_APP_SECRET", "")

# Reserva por enlace (variable vacía = enlace de demo propio)
CAL_URL = os.environ.get("CAL_URL", "").strip()

# Turnstile (vacío = desactivado en local)
TURNSTILE_SECRET = os.environ.get("TURNSTILE_SECRET", "").strip()
