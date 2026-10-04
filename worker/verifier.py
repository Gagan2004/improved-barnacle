from __future__ import annotations

import asyncio
import json
from typing import Any

from worker.gemini import generate_json
from worker.tools.ledger import ledger_lookup


async def verify_run(goal: str, criteria: list[str], scratchpad: dict[str, Any], summary: str | None) -> dict[str, Any]:
    vendor = scratchpad.get("vendor")
    invoice_id = scratchpad.get("invoice_id")
    lookup = await ledger_lookup(
        vendor=str(vendor) if vendor else None,
        invoice_id=str(invoice_id) if invoice_id else None,
    )
    facts = {
        "scratchpad": scratchpad,
        "ledger": lookup,
        "agent_summary": summary,
        "goal": goal,
        "success_criteria": criteria,
    }
    amount = scratchpad.get("amount")
    due = scratchpad.get("due_date")
    programmatic: dict[str, Any] | None = None
    if vendor and invoice_id:
        matches = lookup.get("payables") or []
        if not matches:
            programmatic = {
                "passed": False,
                "reason": f"No ledger row for {vendor} {invoice_id}",
                "unmatched": ["ledger_row"],
            }
        else:
            row = matches[0]
            unmatched = []
            if amount is not None and abs(float(row["amount"]) - float(amount)) > 0.009:
                unmatched.append("amount")
            if due and str(row["due_date"]) != str(due):
                unmatched.append("due_date")
            programmatic = {
                "passed": not unmatched,
                "reason": "Ledger row matches extracted fields" if not unmatched else "Ledger row differs from extracted fields",
                "unmatched": unmatched,
                "row": row,
            }

    prompt = (
        "You verify whether an AP worker finished the user's goal.\n"
        "Return JSON: passed (bool), reason (string), unmatched (array of strings).\n"
        "Pass only if the ledger (or other observed state) actually satisfies the criteria.\n"
        "If the goal was to skip duplicates, passing means the existing row was recognized and not double-posted.\n"
        f"DATA:\n{json.dumps(facts, default=str)[:12000]}"
    )
    try:
        llm = await asyncio.to_thread(generate_json, prompt, "verify")
    except Exception as exc:
        llm = {"passed": False, "reason": f"Verifier model error: {exc}", "unmatched": ["verifier"]}

    if programmatic and not programmatic["passed"]:
        return {**programmatic, "llm": llm, "lookup": lookup}
    if programmatic and programmatic["passed"]:
        return {**programmatic, "llm": llm, "lookup": lookup}
    return {**llm, "lookup": lookup}
