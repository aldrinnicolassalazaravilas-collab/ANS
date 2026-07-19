from flask import Flask
from pathlib import Path
import os


def load_dotenv(path):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "ans-ai-secret-key-change-in-production-2024")
IS_PROD = "VERCEL_URL" in os.environ or "RENDER_EXTERNAL_URL" in os.environ or os.environ.get("GOOGLE_REDIRECT_URI", "").startswith("https://")
app.config.update(
    SESSION_COOKIE_SECURE=IS_PROD,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="None" if IS_PROD else "Lax",
    SESSION_COOKIE_NAME="ans_session",
)
_data_dir = Path("/tmp/ans_data") if IS_PROD else BASE_DIR
_data_dir.mkdir(parents=True, exist_ok=True)
MEMORY_FILE = _data_dir / "ans_memory.json"
USER_FILE = _data_dir / "ans_users.json"
HISTORY_DIR = _data_dir / "ans_history"
CHATS_FILE = _data_dir / "ans_chats.json"
MESSAGES_FILE = _data_dir / "ans_messages.json"

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:5000/auth/google/callback")

OWNER_EMAIL = "aldrinnicolassalazaravilas@gmail.com"

KV_REST_API_URL = os.environ.get("KV_REST_API_URL", "")
KV_REST_API_TOKEN = os.environ.get("KV_REST_API_TOKEN", "")
