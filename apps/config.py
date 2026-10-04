from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
INVOICE_DIR = DATA_DIR / "invoices"
DOWNLOAD_DIR = DATA_DIR / "downloads"
RUNS_DIR = DATA_DIR / "runs"
DB_PATH = DATA_DIR / "atrium.db"

WORKER_BASE_URL = os.getenv("WORKER_BASE_URL", "http://127.0.0.1:8000")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
PORTAL_USER = os.getenv("PORTAL_USER", "agent")
PORTAL_PASSWORD = os.getenv("PORTAL_PASSWORD", "sandbox")
SESSION_SECRET = os.getenv("SESSION_SECRET", "atrium-dev-secret-change-me")
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "20"))


def ensure_dirs() -> None:
    for path in (DATA_DIR, INVOICE_DIR, DOWNLOAD_DIR, RUNS_DIR):
        path.mkdir(parents=True, exist_ok=True)
