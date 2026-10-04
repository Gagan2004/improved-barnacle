from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from apps.config import GEMINI_API_KEY, ROOT
from worker.runtime import MANAGER

templates = Jinja2Templates(directory=str(ROOT / "templates"))
router = APIRouter()

HERO = "Find the latest invoice from Northwind, extract the amount and due date, enter it into our internal ledger, and tell me once it is done."
OVERDUE = "Find overdue inbox invoices (due before 2026-10-03) and record only those that are not already in the ledger."


@router.get("/worker", response_class=HTMLResponse)
def worker_home(request: Request):
    return templates.TemplateResponse(
        request,
        "worker.html",
        {
            "title": "Atrium Clerk",
            "hero": HERO,
            "overdue": OVERDUE,
            "has_key": bool(GEMINI_API_KEY),
        },
    )


@router.post("/worker/runs")
async def start_run(goal: str = Form(...)):
    if not GEMINI_API_KEY:
        raise HTTPException(400, "Set GEMINI_API_KEY in .env")
    state = MANAGER.start(goal)
    return JSONResponse(state.public())


@router.get("/worker/runs/{run_id}")
def get_run(run_id: str):
    state = MANAGER.get(run_id)
    if not state:
        raise HTTPException(404, "Unknown run")
    return JSONResponse(state.public())


@router.post("/worker/runs/{run_id}/reply")
async def reply_run(run_id: str, text: str = Form(...)):
    state = MANAGER.get(run_id)
    if not state:
        raise HTTPException(404, "Unknown run")
    MANAGER.answer(run_id, text)
    return JSONResponse({"ok": True})


@router.get("/worker/runs/{run_id}/events")
async def run_events(run_id: str):
    state = MANAGER.get(run_id)
    if not state:
        raise HTTPException(404, "Unknown run")
    queue = MANAGER.queues[run_id]

    async def gen():
        yield f"data: {json.dumps({'kind': 'hello', 'payload': state.public()}, default=str)}\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
            except asyncio.TimeoutError:
                yield "data: {\"kind\":\"ping\"}\n\n"
                continue
            yield f"data: {json.dumps(event, default=str)}\n\n"
            if event.get("kind") == "end":
                break

    return StreamingResponse(gen(), media_type="text/event-stream")
