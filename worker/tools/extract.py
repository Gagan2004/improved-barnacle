from __future__ import annotations

import json
import re
from pathlib import Path

from pypdf import PdfReader

from worker.tools.files import _safe_path

AMOUNT_RE = re.compile(r"Amount due:\s*([0-9,]+\.\d{2})", re.I)
DUE_RE = re.compile(r"Due date:\s*(\d{4}-\d{2}-\d{2})", re.I)
INV_RE = re.compile(r"INVOICE\s+([A-Z0-9-]+)", re.I)
ISSUED_RE = re.compile(r"Issued:\s*(\d{4}-\d{2}-\d{2})", re.I)


def _pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _parse(text: str, vendor_hint: str | None = None) -> dict:
    amount_m = AMOUNT_RE.search(text)
    due_m = DUE_RE.search(text)
    inv_m = INV_RE.search(text)
    issued_m = ISSUED_RE.search(text)
    vendor = vendor_hint
    if not vendor:
        first = text.strip().splitlines()[0].strip() if text.strip() else None
        vendor = first.title() if first else None
    fields = {
        "vendor": vendor,
        "invoice_id": inv_m.group(1) if inv_m else None,
        "amount": float(amount_m.group(1).replace(",", "")) if amount_m else None,
        "due_date": due_m.group(1) if due_m else None,
        "issued": issued_m.group(1) if issued_m else None,
    }
    missing = [k for k, v in fields.items() if v is None and k != "issued"]
    confidence = "high" if not missing else ("low" if len(missing) > 1 else "medium")
    return {"fields": fields, "confidence": confidence, "missing": missing, "text": text[:4000]}


def extract_invoice(path: str, vendor_hint: str | None = None) -> dict:
    p = _safe_path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        try:
            text = _pdf_text(p)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"Could not read PDF: {exc}",
                "confidence": "low",
                "fields": {},
                "path": str(p),
            }
        if len(text.strip()) < 20:
            return {
                "ok": False,
                "error": "PDF text is empty or unreadable",
                "confidence": "low",
                "fields": {},
                "path": str(p),
            }
        parsed = _parse(text, vendor_hint)
        parsed["ok"] = parsed["confidence"] != "low"
        parsed["path"] = str(p)
        return parsed
    text = p.read_text(encoding="utf-8", errors="replace")
    parsed = _parse(text, vendor_hint)
    parsed["ok"] = parsed["confidence"] != "low"
    parsed["path"] = str(p)
    return parsed


def extract_via_gemini(text: str, client) -> dict:
    from apps.config import GEMINI_MODEL
    from worker.gemini import json_config

    prompt = (
        "Extract invoice fields as JSON with keys vendor, invoice_id, amount (number), "
        "due_date (YYYY-MM-DD). If unknown, use null. Text:\n"
        + text[:8000]
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=json_config(),
    )
    fields = json.loads(response.text)
    missing = [k for k in ("vendor", "invoice_id", "amount", "due_date") if not fields.get(k)]
    return {
        "ok": not missing,
        "fields": fields,
        "confidence": "medium" if not missing else "low",
        "missing": missing,
        "source": "gemini",
    }
