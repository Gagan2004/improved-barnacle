from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from apps.config import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY,
    sender TEXT NOT NULL,
    subject TEXT NOT NULL,
    received_at TEXT NOT NULL,
    body_html TEXT NOT NULL,
    vendor TEXT,
    invoice_id TEXT,
    attachment_name TEXT,
    attachment_path TEXT
);

CREATE TABLE IF NOT EXISTS portal_invoices (
    id INTEGER PRIMARY KEY,
    vendor TEXT NOT NULL,
    invoice_id TEXT NOT NULL UNIQUE,
    amount REAL NOT NULL,
    due_date TEXT NOT NULL,
    issued TEXT NOT NULL,
    pdf_path TEXT,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY,
    vendor TEXT NOT NULL,
    invoice_id TEXT NOT NULL,
    amount REAL NOT NULL,
    due_date TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(vendor, invoice_id)
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    ensure_dirs()
    db_path = path or DB_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
