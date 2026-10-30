"""Paths, limits and environment settings. Read as `config.NAME` at call time, so tests can
override them (via the api.py shim or directly)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]  # repository root
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "originals"
DB_PATH = DATA_DIR / "safesop.db"
BACKUP_DIR = DATA_DIR / "backups"
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
# Checked before the (billed) Gemini call. Text limits are enforced by FastAPI as 422s.
MAX_PDF_PAGES = 50
MAX_SOURCE_CHARS = 60_000
MAX_DESCRIPTION_CHARS = 2000
MAX_FEEDBACK_CHARS = 2000
MAX_REVIEWER_CHARS = 100

DEFAULT_ALLOWED_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def allowed_origins():
    """Comma-separated ALLOWED_ORIGINS from the environment (or .env), else the Vite dev server."""
    value = os.getenv("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
    return [origin.strip() for origin in value.split(",") if origin.strip()]


for folder in (DATA_DIR, UPLOAD_DIR):
    folder.mkdir(parents=True, exist_ok=True)
