"""Paths, limits and environment settings. Read as `config.NAME` at call time, so tests can
override them (via the api.py shim or directly)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]  # repository root
load_dotenv(BASE_DIR / ".env")

# SAFESOP_DATA_DIR moves the database and stored PDFs (e.g. a throwaway folder for demos).
DATA_DIR = Path(os.getenv("SAFESOP_DATA_DIR") or BASE_DIR / "data")
UPLOAD_DIR = DATA_DIR / "originals"
DB_PATH = DATA_DIR / "safesop.db"
BACKUP_DIR = DATA_DIR / "backups"
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
# Checked before the (billed) Gemini call. Text limits are enforced by FastAPI as 422s.
MAX_PDF_PAGES = 50
MAX_SOURCE_CHARS = 60_000
MAX_DESCRIPTION_CHARS = 2000
MAX_FEEDBACK_CHARS = 2000

# Authentication. JWT_SECRET must be set in production (any long random string); without it
# a random per-process secret is used and every login ends when the API restarts.
JWT_SECRET = os.getenv("JWT_SECRET", "")
TOKEN_MINUTES = int(os.getenv("TOKEN_MINUTES", "480"))  # one working day
BCRYPT_ROUNDS = 12
MIN_PASSWORD_LENGTH = 10
# Seeded once at startup if no user with this name exists.
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

DEFAULT_ALLOWED_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def allowed_origins():
    """Comma-separated ALLOWED_ORIGINS from the environment (or .env), else the Vite dev server."""
    value = os.getenv("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
    return [origin.strip() for origin in value.split(",") if origin.strip()]


for folder in (DATA_DIR, UPLOAD_DIR):
    folder.mkdir(parents=True, exist_ok=True)
