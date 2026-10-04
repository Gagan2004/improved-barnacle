from __future__ import annotations

import json
from typing import Any

import httpx

from apps.config import WORKER_BASE_URL


async def ledger_lookup(vendor: str | None = None, invoice_id: str | None = None) -> dict[str, Any]:
    params: dict[str, str] = {}
    if vendor:
        params["vendor"] = vendor
    if invoice_id:
        params["invoice_id"] = invoice_id
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(f"{WORKER_BASE_URL}/api/ledger", params=params)
        response.raise_for_status()
        return response.json()
