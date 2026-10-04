from __future__ import annotations

import sqlite3

from apps.config import INVOICE_DIR, ensure_dirs
from apps.world.db import connect, init_schema
from apps.world.pdfs import write_garbage_pdf, write_invoice_pdf

INVOICES = [
    {
        "vendor": "Northwind",
        "invoice_id": "INV-1042",
        "amount": 4280.50,
        "due_date": "2026-10-15",
        "issued": "2026-10-01",
        "status": "open",
        "pdf": True,
    },
    {
        "vendor": "Northwind",
        "invoice_id": "INV-1030",
        "amount": 1200.00,
        "due_date": "2026-08-20",
        "issued": "2026-08-01",
        "status": "open",
        "pdf": True,
    },
    {
        "vendor": "Northwind",
        "invoice_id": "INV-1022",
        "amount": 890.00,
        "due_date": "2026-07-01",
        "issued": "2026-06-15",
        "status": "open",
        "pdf": True,
    },
    {
        "vendor": "Contoso",
        "invoice_id": "INV-C-91",
        "amount": 3100.00,
        "due_date": "2026-10-20",
        "issued": "2026-09-28",
        "status": "open",
        "pdf": True,
    },
    {
        "vendor": "Contoso",
        "invoice_id": "INV-C-88",
        "amount": 1500.00,
        "due_date": "2026-09-01",
        "issued": "2026-08-20",
        "status": "open",
        "pdf": True,
    },
    {
        "vendor": "Acme",
        "invoice_id": "INV-A-12",
        "amount": 500.00,
        "due_date": "2026-11-01",
        "issued": "2026-09-18",
        "status": "open",
        "pdf": True,
    },
    {
        "vendor": "Acme",
        "invoice_id": "INV-A-07",
        "amount": 2200.00,
        "due_date": "2026-09-15",
        "issued": "2026-08-30",
        "status": "open",
        "pdf": False,
    },
    {
        "vendor": "Globex",
        "invoice_id": "INV-G-1",
        "amount": 99.00,
        "due_date": "2026-12-01",
        "issued": "2026-09-01",
        "status": "open",
        "pdf": "garbage",
    },
]

EMAILS = [
    {
        "sender": "billing@northwind.test",
        "subject": "Invoice INV-1042 from Northwind",
        "received_at": "2026-10-01 09:14",
        "vendor": "Northwind",
        "invoice_id": "INV-1042",
        "attachment": "northwind-INV-1042.pdf",
        "body": "<p>Please find the latest Northwind invoice attached.</p>",
    },
    {
        "sender": "billing@northwind.test",
        "subject": "Invoice INV-1030 from Northwind",
        "received_at": "2026-08-01 11:02",
        "vendor": "Northwind",
        "invoice_id": "INV-1030",
        "attachment": "northwind-INV-1030.pdf",
        "body": "<p>August statement attached.</p>",
    },
    {
        "sender": "billing@northwind.test",
        "subject": "Invoice INV-1022 from Northwind",
        "received_at": "2026-06-15 16:40",
        "vendor": "Northwind",
        "invoice_id": "INV-1022",
        "attachment": "northwind-INV-1022.pdf",
        "body": "<p>Q2 invoice attached.</p>",
    },
    {
        "sender": "ap@contoso.test",
        "subject": "Contoso invoice INV-C-91",
        "received_at": "2026-09-28 08:22",
        "vendor": "Contoso",
        "invoice_id": "INV-C-91",
        "attachment": "contoso-INV-C-91.pdf",
        "body": "<p>New Contoso payable.</p>",
    },
    {
        "sender": "ap@contoso.test",
        "subject": "Contoso invoice INV-C-88",
        "received_at": "2026-08-20 13:10",
        "vendor": "Contoso",
        "invoice_id": "INV-C-88",
        "attachment": "contoso-INV-C-88.pdf",
        "body": "<p>Prior Contoso invoice.</p>",
    },
    {
        "sender": "invoices@acme.test",
        "subject": "Acme INV-A-12",
        "received_at": "2026-09-18 10:00",
        "vendor": "Acme",
        "invoice_id": "INV-A-12",
        "attachment": "acme-INV-A-12.pdf",
        "body": "<p>Small materials invoice.</p>",
    },
    {
        "sender": "invoices@acme.test",
        "subject": "Acme INV-A-07 — attachment failed",
        "received_at": "2026-08-30 17:45",
        "vendor": "Acme",
        "invoice_id": "INV-A-07",
        "attachment": None,
        "body": "<p>Our mail gateway dropped the PDF. Please pull INV-A-07 from the vendor portal.</p>",
    },
    {
        "sender": "noreply@globex.test",
        "subject": "Globex invoice (corrupt file)",
        "received_at": "2026-09-01 04:12",
        "vendor": "Globex",
        "invoice_id": "INV-G-1",
        "attachment": "globex-INV-G-1.pdf",
        "body": "<p>Automated send. File may be damaged.</p>",
    },
]


def _pdf_name(vendor: str, invoice_id: str) -> str:
    return f"{vendor.lower()}-{invoice_id}.pdf"


def seed(force: bool = False) -> Path:
    ensure_dirs()
    conn = connect()
    init_schema(conn)
    existing = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    if existing and not force:
        conn.close()
        return INVOICE_DIR

    conn.execute("DELETE FROM emails")
    conn.execute("DELETE FROM portal_invoices")
    conn.execute("DELETE FROM ledger")
    try:
        conn.execute("DELETE FROM sqlite_sequence")
    except sqlite3.OperationalError:
        pass

    pdf_paths: dict[str, str] = {}
    for inv in INVOICES:
        name = _pdf_name(inv["vendor"], inv["invoice_id"])
        path = INVOICE_DIR / name
        if inv["pdf"] is True:
            write_invoice_pdf(
                path,
                inv["vendor"],
                inv["invoice_id"],
                inv["amount"],
                inv["due_date"],
                inv["issued"],
            )
            pdf_paths[inv["invoice_id"]] = str(path)
            stored = str(path)
        elif inv["pdf"] == "garbage":
            write_garbage_pdf(path)
            pdf_paths[inv["invoice_id"]] = str(path)
            stored = str(path)
        else:
            stored = None
        conn.execute(
            """INSERT INTO portal_invoices
               (vendor, invoice_id, amount, due_date, issued, pdf_path, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                inv["vendor"],
                inv["invoice_id"],
                inv["amount"],
                inv["due_date"],
                inv["issued"],
                stored,
                inv["status"],
            ),
        )

    for mail in EMAILS:
        att_name = mail["attachment"]
        att_path = str(INVOICE_DIR / att_name) if att_name else None
        conn.execute(
            """INSERT INTO emails
               (sender, subject, received_at, body_html, vendor, invoice_id,
                attachment_name, attachment_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                mail["sender"],
                mail["subject"],
                mail["received_at"],
                mail["body"],
                mail["vendor"],
                mail["invoice_id"],
                att_name,
                att_path,
            ),
        )

    conn.execute(
        """INSERT INTO ledger (vendor, invoice_id, amount, due_date, source)
           VALUES ('Contoso', 'INV-C-88', 1500.00, '2026-09-01', 'seed')"""
    )
    conn.commit()
    conn.close()
    return INVOICE_DIR
