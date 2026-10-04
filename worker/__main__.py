from __future__ import annotations

import argparse
import asyncio
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.config import GEMINI_API_KEY, WORKER_BASE_URL  # noqa: E402
from worker.loop import AgentLoop, RunState  # noqa: E402


def _server_up() -> bool:
    try:
        r = httpx.get(f"{WORKER_BASE_URL}/health", timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False


def ensure_server() -> None:
    if _server_up():
        return
    thread = threading.Thread(
        target=lambda: uvicorn.run("apps.main:app", host="127.0.0.1", port=8000, log_level="warning"),
        daemon=True,
    )
    thread.start()
    for _ in range(50):
        if _server_up():
            return
        time.sleep(0.2)
    raise RuntimeError("Could not start local sandbox on :8000")


async def run_goal(goal: str) -> RunState:
    ensure_server()
    if not GEMINI_API_KEY:
        raise SystemExit("Set GEMINI_API_KEY in .env")

    async def emit(event: dict) -> None:
        kind = event.get("kind")
        payload = event.get("payload")
        print(f"[{kind}] {str(payload)[:500]}")

    async def wait_user(question: str) -> str:
        print(f"\nClerk needs you: {question}")
        return await asyncio.to_thread(input, "> ")

    state = RunState(id="cli-" + str(int(time.time())), goal=goal)
    agent = AgentLoop(state, emit, wait_user)
    return await agent.run()


def load_scenarios() -> dict:
    path = ROOT / "eval" / "scenarios.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def eval_world() -> None:
    ensure_server()
    from apps.world.seed import seed
    from worker.tools.extract import extract_invoice
    from apps.config import INVOICE_DIR

    seed(force=True)
    with httpx.Client(base_url=WORKER_BASE_URL, timeout=10, follow_redirects=True) as c:
        inbox = c.get("/inbox")
        assert inbox.status_code == 200 and "INV-1042" in inbox.text
        pdf = INVOICE_DIR / "northwind-INV-1042.pdf"
        parsed = extract_invoice(str(pdf))
        assert parsed["fields"]["invoice_id"] == "INV-1042"
        assert abs(parsed["fields"]["amount"] - 4280.50) < 0.001
        form = {
            "vendor": "Northwind",
            "invoice_id": "INV-1042",
            "amount": "4280.50",
            "due_date": "2026-10-15",
            "source": "test",
        }
        created = c.post("/ledger/new", data=form)
        assert created.status_code == 200
        dup = c.post("/ledger/new", data=form)
        assert dup.status_code == 409
        lookup = c.get("/api/ledger", params={"vendor": "Northwind", "invoice_id": "INV-1042"})
        assert lookup.json()["count"] == 1
        c.post("/portal/login", data={"username": "agent", "password": "sandbox"})
        c.post("/admin/fail", params={"target": "portal", "count": 1})
        fail = c.get("/portal/invoices")
        assert fail.status_code == 500
        ok = c.get("/portal/invoices")
        assert ok.status_code == 200
        c.post("/admin/reseed")
    print("world checks passed")
    asyncio.run(_eval_browser())
    print("browser smoke passed")


async def _eval_browser() -> None:
    from apps.config import RUNS_DIR
    from worker.tools.browser import BrowserSession

    session = BrowserSession(RUNS_DIR / "smoke")
    await session.start()
    try:
        snap = await session.goto("/inbox")
        if "INV-1042" not in snap["text"]:
            raise AssertionError("inbox missing Northwind invoice")
        await session.click("#email-link-1")
        detail = await session.read()
        if "INV-1042" not in detail["text"]:
            raise AssertionError("email detail did not open")
        await session.goto("/portal")
        await session.type_text("#username", "agent")
        await session.type_text("#password", "sandbox")
        await session.click("#login-submit")
        portal = await session.read()
        if "INV-1042" not in portal["text"]:
            raise AssertionError("portal login failed")
        await session.goto("/ledger/new")
        form = await session.read()
        if "Record payable" not in form["text"]:
            raise AssertionError("ledger form missing")
    finally:
        await session.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="worker")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run")
    run_p.add_argument("goal", nargs="+")
    ev = sub.add_parser("eval")
    ev.add_argument("--world", action="store_true")
    ev.add_argument("--scenario", default=None)
    ev.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.cmd == "run":
        goal = " ".join(args.goal)
        state = asyncio.run(run_goal(goal))
        print("\nSTATUS", state.status)
        print("SUMMARY", state.summary)
        print("VERIFY", state.verification)
        sys.exit(0 if state.status == "succeeded" else 1)

    scenarios = load_scenarios()
    if args.list:
        for name, spec in scenarios["scenarios"].items():
            print(f"{name}: {spec['goal']}")
        return
    if args.world:
        eval_world()
        return
    if args.scenario:
        spec = scenarios["scenarios"][args.scenario]
        ensure_server()
        httpx.post(f"{WORKER_BASE_URL}/admin/reseed", timeout=10)
        if spec.get("fail"):
            httpx.post(
                f"{WORKER_BASE_URL}/admin/fail",
                params={"target": spec["fail"]["target"], "count": spec["fail"].get("count", 1)},
                timeout=10,
            )
        print("Prompt:", spec["goal"])
        print("Expect:", spec["expect"])
        state = asyncio.run(run_goal(spec["goal"]))
        print("STATUS", state.status)
        print("SUMMARY", state.summary)
        sys.exit(0 if state.status in spec.get("ok_status", ["succeeded"]) else 1)
    parser.print_help()


if __name__ == "__main__":
    main()
