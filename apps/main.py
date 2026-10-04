from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from apps.config import RUNS_DIR, SESSION_SECRET, ensure_dirs
from apps.world.routes import router as world_router
from apps.world.seed import seed
from worker.api import router as worker_router

ensure_dirs()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_dirs()
    seed()
    yield


app = FastAPI(title="Atrium Autonomous Worker", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.include_router(world_router)
app.include_router(worker_router)

static_dir = Path(__file__).resolve().parent.parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
app.mount("/evidence", StaticFiles(directory=str(RUNS_DIR)), name="evidence")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/worker")
