from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from apps.config import DOWNLOAD_DIR, INVOICE_DIR, ROOT, WORKER_BASE_URL
from worker.tools.browser import assert_local_url

ALLOWED_PREFIXES = (
    DOWNLOAD_DIR.resolve(),
    INVOICE_DIR.resolve(),
    (ROOT / "data").resolve(),
)


def _safe_path(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if not any(p == prefix or prefix in p.parents for prefix in ALLOWED_PREFIXES):
        raise ValueError("Path is outside the sandbox data directory")
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(str(p))
    return p


def read_file(path: str, max_chars: int = 8000) -> dict:
    p = _safe_path(path)
    if p.suffix.lower() == ".pdf":
        return {"path": str(p), "kind": "pdf", "note": "Use extract_invoice for PDFs", "size": p.stat().st_size}
    text = p.read_text(encoding="utf-8", errors="replace")
    return {"path": str(p), "kind": "text", "text": text[:max_chars]}


def local_url_to_path(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.path.startswith("/files/invoices/"):
        name = parsed.path.rsplit("/", 1)[-1]
        candidate = INVOICE_DIR / name
        if candidate.exists():
            return str(candidate)
    return None


async def download_save(url: str) -> dict:
    if url.startswith("/"):
        url = WORKER_BASE_URL.rstrip("/") + url
    mapped = local_url_to_path(url)
    if mapped:
        return {"saved": mapped, "url": url, "via": "sandbox-disk"}
    target = assert_local_url(url)
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(target, follow_redirects=True)
        response.raise_for_status()
    name = Path(urlparse(target).path).name or f"download-{uuid4().hex[:8]}"
    dest = DOWNLOAD_DIR / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(response.content)
    return {"saved": str(dest), "url": target, "via": "http", "bytes": dest.stat().st_size}
