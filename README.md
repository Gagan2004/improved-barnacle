# Atrium Clerk

Prototype **autonomous AI task worker** for intern evaluation. A user states an accounts-payable goal in English. Clerk infers success criteria, drives a **local fake company** with Playwright (inbox, vendor portal, internal ledger), extracts invoice fields, writes the payable through the **ledger form**, then **verifies** the books. It retries injected failures, refuses to double-post, and **asks the user** when the vendor is ambiguous.

This is a narrow sandbox that actually does the work — not a slide-deck of mocked tools, and not live Gmail/QuickBooks.

## Setup

Python 3.11+ recommended.

```powershell
cd C:\Users\gagan\OneDrive\projects\center
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env
```

Set `GEMINI_API_KEY` in `.env`. Optional: `GEMINI_MODEL` (default `gemini-2.5-flash`).

## Run

From the repo root (so `apps` and `worker` import):

```powershell
python run.py
```

Open [http://127.0.0.1:8000/worker](http://127.0.0.1:8000/worker).

Sandbox tabs (same process):

- Inbox: [http://127.0.0.1:8000/inbox](http://127.0.0.1:8000/inbox)
- Vendor portal: [http://127.0.0.1:8000/portal](http://127.0.0.1:8000/portal) — `agent` / `sandbox`
- Ledger: [http://127.0.0.1:8000/ledger](http://127.0.0.1:8000/ledger)

CLI (starts the sandbox on `:8000` if it is not already up):

```powershell
python -m worker run "Find the latest invoice from Northwind, extract the amount and due date, enter it into our internal ledger, and tell me once it is done."
python -m worker eval --world
python -m worker eval --list
python -m worker eval --scenario hero
```

`--world` does not call Gemini. Scenario runs do.

## Demo script (about two minutes)

1. Show inbox / portal / ledger as ordinary internal apps.
2. On **Worker**, run the hero task (chip: *Northwind invoice*). Watch thought → click → extract → ledger form → verifier.
3. Refresh **Ledger** and show `Northwind INV-1042` / `4280.50` / `2026-10-15`.
4. Run *Company X*. Clerk should **ask** which vendor; reply `Northwind` if the row already exists it should **not** double-post.
5. Optional: `python -m worker eval --world` to show duplicate 409 + portal 500 retry plumbing.

## Architecture

```
User goal → FastAPI /worker
         → Gemini plans next JSON action
         → Playwright tools against localhost
         → scratchpad facts + screenshots
         → verifier (ledger_lookup + rules + Gemini)
         → summary + evidence pack
```

| Piece | Role |
| --- | --- |
| `apps/world` | Seeded SQLite company: mail, portal invoices, AP ledger, fail flags |
| `worker/loop.py` | Custom ReAct loop (no LangChain). Cap `MAX_AGENT_STEPS` (default 20) |
| `worker/tools` | Browser, files, PDF extract, read-only ledger lookup |
| `worker/verifier.py` | Programmatic field match, then a model rationale |
| `templates/worker.html` | Live SSE trace, ask-user pause, screenshot evidence |

The hero path **must** submit `/ledger/new` in the browser. `ledger_lookup` is read-only so verification is not the same write path.

## Design decisions

- **Closed sandbox over the live web.** The brief forbids real credentials. A company that always exists makes autonomy, retries, and demos repeatable.
- **Custom loop, not an agent framework.** Every thought, tool error, and retry is visible in the trace and easy to explain in a technical discussion.
- **Gemini Flash + JSON actions.** Cheap enough for a 20-step browser loop; schema-validated with Pydantic after parse.
- **Verification is a phase, not a vibe.** After `finish`, Clerk re-reads the ledger. Status is `succeeded` only if checks pass; otherwise `partial` / `failed` with evidence. Fake success is a product bug.
- **Generalization via tools, not a second bot.** The overdue-payables task uses the same tools and policy. New workflows should be new seeds + a prompt, not a new codebase.
- **Ask instead of guessing.** “Company X” and unreadable PDFs are supposed to block, not hallucinate amounts.

## Seeded world (assumptions)

Today for the demo seed is **2026-10-03**.

- Latest Northwind mail/PDF: **INV-1042**, **4280.50 USD**, due **2026-10-15**
- Already in the ledger: Contoso **INV-C-88**
- Acme **INV-A-07** has no inbox attachment (portal fallback)
- Globex PDF is corrupt on purpose
- Injected faults: `POST /admin/fail?target=portal|ledger&count=1`

## Models, APIs, frameworks

- Google Gemini (`google-genai`), default `gemini-2.5-flash`
- FastAPI, Uvicorn, Jinja2, SQLite
- Playwright (Chromium, localhost only)
- pypdf / fpdf2 for invoice files
- No LangChain, no cloud vendor APIs, no real customer data

## Known limitations

- Only the Atrium sandbox, not arbitrary websites or desktop apps.
- Headless Chromium; no OS-level computer-use.
- Extraction regex is tuned to these PDFs; messy scans fall back to Gemini and may still need `ask_user`.
- Step cap can stop a wandering browser loop.
- Gemini can still click the wrong control; the verifier is the backstop, not a proof of correctness.
- One worker process; no auth on `/admin/*` (local demo only).
- No durable memory across days.

## What I would build next

- HTML accessibility snapshots instead of raw CSS ids, so new apps need fewer hand-placed `#ids`
- Deterministic eval harness with recorded traces (pass/fail without a live model)
- Policy kernel: auto-approve below a dollar threshold, always confirm above it
- Multi-goal queue and human review inbox
- Structured invoice OCR for scans

## Evaluation mapping

| Criterion | Where it shows up |
| --- | --- |
| Autonomy | Goal → plan → tools; no hardcoded Northwind script |
| Execution | Real Playwright + SQLite writes |
| Reliability | Portal 500, duplicates, unreadable PDF, step limit |
| Verification | `ledger_lookup` + field compare after finish |
| Generalization | Hero vs overdue vs vague vendor, same loop |
| Product | Evidence pack, ask-user, fail-closed summaries |

## License / safety

Sandbox only. Do not point Clerk at production systems or third-party logins.
