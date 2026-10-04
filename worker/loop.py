from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from apps.config import MAX_AGENT_STEPS, RUNS_DIR, WORKER_BASE_URL, ensure_dirs
from worker.gemini import generate_json
from worker.policies import POLICY
from worker.tools.browser import BrowserSession
from worker.tools.extract import extract_invoice, extract_via_gemini
from worker.tools.files import download_save, read_file
from worker.tools.ledger import ledger_lookup
from worker.verifier import verify_run

TOOL_SPECS = [
    {
        "name": "browser_goto",
        "args": {"url": "http://127.0.0.1:8000/inbox or a path like /ledger"},
        "use": "Open a localhost page",
    },
    {
        "name": "browser_click",
        "args": {"selector": "CSS selector, prefer #id"},
        "use": "Click a link or button",
    },
    {
        "name": "browser_type",
        "args": {"selector": "CSS selector", "text": "value", "submit": "optional bool"},
        "use": "Fill an input",
    },
    {
        "name": "browser_read",
        "args": {},
        "use": "Re-read the current page",
    },
    {
        "name": "download_save",
        "args": {"url": "localhost file URL"},
        "use": "Save an invoice PDF from /files/invoices/...",
    },
    {
        "name": "read_file",
        "args": {"path": "sandbox path"},
        "use": "Read a non-PDF sandbox file",
    },
    {
        "name": "extract_invoice",
        "args": {"path": "saved PDF path", "vendor_hint": "optional"},
        "use": "Parse amount, due date, vendor, invoice id",
    },
    {
        "name": "ledger_lookup",
        "args": {"vendor": "optional", "invoice_id": "optional"},
        "use": "Read-only check of ledger rows",
    },
    {
        "name": "remember",
        "args": {"key": "vendor|invoice_id|amount|due_date|ledger_id|notes", "value": "string or number"},
        "use": "Store a confirmed fact in working memory",
    },
]


def _trim(obj: Any, limit: int = 7000) -> Any:
    text = json.dumps(obj, default=str)
    if len(text) <= limit:
        return obj
    return {"truncated": True, "preview": text[:limit]}


@dataclass
class RunState:
    id: str
    goal: str
    success_criteria: list[str] = field(default_factory=list)
    restated_goal: str = ""
    scratchpad: dict[str, Any] = field(default_factory=dict)
    trace: list[dict[str, Any]] = field(default_factory=list)
    status: str = "queued"
    question: str | None = None
    summary: str | None = None
    verification: dict[str, Any] | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "restated_goal": self.restated_goal,
            "success_criteria": self.success_criteria,
            "scratchpad": self.scratchpad,
            "trace": self.trace[-40:],
            "status": self.status,
            "question": self.question,
            "summary": self.summary,
            "verification": self.verification,
            "evidence": self.evidence,
            "error": self.error,
            "created_at": self.created_at,
        }


class AgentLoop:
    def __init__(self, state: RunState, emit: Callable[[dict[str, Any]], Awaitable[None]], wait_user: Callable[[str], Awaitable[str]]):
        self.state = state
        self.emit = emit
        self.wait_user = wait_user
        self.browser = BrowserSession(RUNS_DIR / state.id)
        self.run_dir = RUNS_DIR / state.id

    def _persist(self) -> None:
        ensure_dirs()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "state.json").write_text(
            json.dumps(self.state.public(), indent=2, default=str),
            encoding="utf-8",
        )

    async def _observe(self, kind: str, payload: Any) -> None:
        event = {"kind": kind, "payload": payload}
        self.state.trace.append(event)
        self._persist()
        await self.emit(event)

    async def _call_tool(self, name: str, args: dict[str, Any]) -> Any:
        if name == "browser_goto":
            return await self.browser.goto(str(args["url"]))
        if name == "browser_click":
            return await self.browser.click(str(args["selector"]))
        if name == "browser_type":
            return await self.browser.type_text(
                str(args["selector"]),
                str(args.get("text", "")),
                bool(args.get("submit", False)),
            )
        if name == "browser_read":
            return await self.browser.read()
        if name == "download_save":
            return await download_save(str(args["url"]))
        if name == "read_file":
            return read_file(str(args["path"]))
        if name == "extract_invoice":
            result = extract_invoice(str(args["path"]), args.get("vendor_hint"))
            if not result.get("ok") and result.get("text"):
                try:
                    from worker.gemini import client as gemini_client

                    result = {**result, **extract_via_gemini(result["text"], gemini_client())}
                except Exception as exc:
                    result["gemini_fallback"] = str(exc)
            fields = result.get("fields") or {}
            for key in ("vendor", "invoice_id", "amount", "due_date"):
                if fields.get(key) is not None:
                    self.state.scratchpad[key] = fields[key]
            if result.get("path"):
                self.state.evidence["invoice_path"] = result["path"]
            return result
        if name == "ledger_lookup":
            return await ledger_lookup(args.get("vendor"), args.get("invoice_id"))
        if name == "remember":
            key = str(args["key"])
            self.state.scratchpad[key] = args.get("value")
            return {"ok": True, "scratchpad": self.state.scratchpad}
        raise ValueError(f"Unknown tool: {name}")

    def _decision_prompt(self) -> str:
        recent = self.state.trace[-12:]
        return (
            POLICY
            + "\n\nGoal: "
            + self.state.goal
            + "\nRestated: "
            + (self.state.restated_goal or "")
            + "\nSuccess criteria: "
            + json.dumps(self.state.success_criteria)
            + "\nWorking memory: "
            + json.dumps(self.state.scratchpad, default=str)
            + "\nWorld: inbox=/inbox portal=/portal ledger=/ledger lookup=/api/ledger"
            + f"\nBase URL: {WORKER_BASE_URL}"
            + "\nTools: "
            + json.dumps(TOOL_SPECS)
            + "\nRecent trace: "
            + json.dumps(recent, default=str)[:14000]
            + "\nReturn JSON with keys: think, action (tool|ask_user|finish), tool_name, tool_args_json (JSON object string), question, summary."
        )

    async def run(self) -> RunState:
        self.state.status = "planning"
        await self._observe("status", {"status": self.state.status})
        try:
            spec = await asyncio.to_thread(
                generate_json,
                "Turn this user request into JSON with restated_goal (string), "
                "success_criteria (array of concrete checks), notes (array).\n"
                f"User: {self.state.goal}",
                "goal",
            )
            self.state.restated_goal = spec["restated_goal"]
            self.state.success_criteria = spec["success_criteria"]
            await self._observe("plan", spec)
        except Exception as exc:
            self.state.restated_goal = self.state.goal
            self.state.success_criteria = ["The requested outcome is visible in the ledger or explained as blocked."]
            await self._observe("plan_error", {"error": str(exc)})

        await self.browser.start()
        try:
            self.state.status = "running"
            await self._observe("status", {"status": "running"})
            for step in range(MAX_AGENT_STEPS):
                decision = await asyncio.to_thread(generate_json, self._decision_prompt(), "decision")
                await self._observe("thought", {"step": step + 1, **decision})
                action = decision.get("action")
                if action == "ask_user":
                    question = decision.get("question") or "Need a decision to continue."
                    self.state.status = "waiting_user"
                    self.state.question = question
                    await self._observe("ask_user", {"question": question})
                    reply = await self.wait_user(question)
                    self.state.question = None
                    self.state.status = "running"
                    await self._observe("user_reply", {"reply": reply})
                    self.state.scratchpad["user_reply"] = reply
                    continue
                if action == "finish":
                    self.state.summary = decision.get("summary") or "Finished."
                    break
                if action == "tool":
                    name = decision.get("tool_name") or ""
                    try:
                        args = json.loads(decision.get("tool_args_json") or "{}")
                        if not isinstance(args, dict):
                            args = {}
                    except json.JSONDecodeError:
                        args = {}
                    await self._observe("tool", {"name": name, "args": args, "step": step + 1})
                    try:
                        result = await self._call_tool(name, args)
                        await self._observe("observation", _trim(result))
                    except Exception as exc:
                        await self._observe("observation", {"error": str(exc), "tool": name})
                    continue
                await self._observe("observation", {"error": f"Unknown action {action}"})

            else:
                self.state.summary = self.state.summary or "Stopped at step limit."
                await self._observe("limit", {"max_steps": MAX_AGENT_STEPS})

            self.state.status = "verifying"
            await self._observe("status", {"status": "verifying"})
            self.state.verification = await verify_run(
                self.state.goal,
                self.state.success_criteria,
                self.state.scratchpad,
                self.state.summary,
            )
            await self._observe("verify", self.state.verification)

            if self.state.verification.get("passed"):
                self.state.status = "succeeded"
            elif self.state.scratchpad.get("invoice_id") or self.state.summary:
                self.state.status = "partial"
            else:
                self.state.status = "failed"

            shots = sorted(self.run_dir.glob("shot_*.png"))
            self.state.evidence.update(
                {
                    "screenshots": [f"/evidence/{self.state.id}/{p.name}" for p in shots],
                    "state": f"/evidence/{self.state.id}/state.json",
                    "run_dir": str(self.run_dir),
                }
            )
            await self._observe("done", {"status": self.state.status, "summary": self.state.summary, "evidence": self.state.evidence})
            self._persist()
            return self.state
        finally:
            await self.browser.close()
