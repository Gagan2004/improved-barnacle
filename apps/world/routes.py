from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from apps.config import PORTAL_PASSWORD, PORTAL_USER, ROOT
from apps.world.db import get_db
from apps.world.failflags import FLAGS

templates = Jinja2Templates(directory=str(ROOT / "templates"))
router = APIRouter()


def _logged_in(request: Request) -> bool:
    return bool(request.session.get("portal_user"))


@router.get("/health")
def health():
    return {"ok": True, "fail": FLAGS.snapshot()}


@router.post("/admin/reseed")
def reseed():
    from apps.world.seed import seed

    seed(force=True)
    return {"ok": True, "message": "Database reseeded"}


@router.post("/admin/fail")
def arm_fail(target: str = Query(...), count: int = Query(1)):
    try:
        msg = FLAGS.arm(target, count)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "message": msg, "fail": FLAGS.snapshot()}


@router.get("/inbox", response_class=HTMLResponse)
def inbox_list(request: Request):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM emails ORDER BY received_at DESC"
        ).fetchall()
    return templates.TemplateResponse(
        request,
        "inbox_list.html",
        {"emails": rows, "title": "Inbox"},
    )


@router.get("/inbox/{email_id}", response_class=HTMLResponse)
def inbox_detail(request: Request, email_id: int):
    with get_db() as db:
        row = db.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Email not found")
    return templates.TemplateResponse(
        request,
        "inbox_detail.html",
        {"email": row, "title": row["subject"]},
    )


@router.get("/files/invoices/{name}")
def download_invoice(name: str):
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "Invalid name")
    with get_db() as db:
        row = db.execute(
            "SELECT attachment_path FROM emails WHERE attachment_name = ?",
            (name,),
        ).fetchone()
        if not row:
            row = db.execute(
                "SELECT pdf_path AS attachment_path FROM portal_invoices WHERE pdf_path LIKE ?",
                (f"%{name}",),
            ).fetchone()
    if not row or not row["attachment_path"]:
        raise HTTPException(404, "File not found")
    path = Path(row["attachment_path"])
    if not path.exists():
        raise HTTPException(404, "File missing on disk")
    return FileResponse(path, filename=name, content_disposition_type="attachment")


@router.get("/portal", response_class=HTMLResponse)
def portal_home(request: Request):
    if _logged_in(request):
        return RedirectResponse("/portal/invoices", status_code=302)
    return templates.TemplateResponse(request, "portal_login.html", {"title": "Vendor portal", "error": None})


@router.post("/portal/login")
def portal_login(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    if username == PORTAL_USER and password == PORTAL_PASSWORD:
        request.session["portal_user"] = username
        return RedirectResponse("/portal/invoices", status_code=303)
    return templates.TemplateResponse(
        request,
        "portal_login.html",
        {"title": "Vendor portal", "error": "Invalid sandbox credentials"},
        status_code=401,
    )


@router.get("/portal/logout")
def portal_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/portal", status_code=302)


@router.get("/portal/invoices", response_class=HTMLResponse)
def portal_invoices(request: Request, fail: str | None = None):
    if not _logged_in(request):
        return RedirectResponse("/portal", status_code=302)
    if fail == "once":
        FLAGS.arm("portal", 1)
    if FLAGS.hit_portal():
        return HTMLResponse(
            "<html><body><h1 id='portal-error'>Portal temporarily unavailable</h1><p>Retry in a moment.</p></body></html>",
            status_code=500,
        )
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM portal_invoices ORDER BY issued DESC"
        ).fetchall()
    return templates.TemplateResponse(
        request,
        "portal_list.html",
        {"invoices": rows, "title": "Vendor invoices", "user": request.session.get("portal_user")},
    )


@router.get("/portal/invoices/{invoice_pk}", response_class=HTMLResponse)
def portal_invoice_detail(request: Request, invoice_pk: int):
    if not _logged_in(request):
        return RedirectResponse("/portal", status_code=302)
    with get_db() as db:
        row = db.execute("SELECT * FROM portal_invoices WHERE id = ?", (invoice_pk,)).fetchone()
    if not row:
        raise HTTPException(404, "Invoice not found")
    filename = Path(row["pdf_path"]).name if row["pdf_path"] else None
    return templates.TemplateResponse(
        request,
        "portal_detail.html",
        {"inv": row, "filename": filename, "title": row["invoice_id"]},
    )


@router.get("/ledger", response_class=HTMLResponse)
def ledger_list(request: Request, notice: str | None = None):
    with get_db() as db:
        rows = db.execute("SELECT * FROM ledger ORDER BY id DESC").fetchall()
    return templates.TemplateResponse(
        request,
        "ledger_list.html",
        {"rows": rows, "title": "Internal ledger", "notice": notice},
    )


@router.get("/ledger/new", response_class=HTMLResponse)
def ledger_new(request: Request, error: str | None = None):
    return templates.TemplateResponse(
        request,
        "ledger_form.html",
        {"title": "Record payable", "error": error},
    )


@router.post("/ledger/new")
async def ledger_create(
    request: Request,
    vendor: Annotated[str, Form()],
    invoice_id: Annotated[str, Form()],
    amount: Annotated[str, Form()],
    due_date: Annotated[str, Form()],
    source: Annotated[str, Form()] = "inbox",
    fail: str | None = Query(None),
):
    if fail == "once":
        FLAGS.arm("ledger", 1)
    if FLAGS.hit_ledger():
        return templates.TemplateResponse(
            request,
            "ledger_form.html",
            {"title": "Record payable", "error": "Ledger service error (injected). Retry."},
            status_code=500,
        )
    vendor = vendor.strip()
    invoice_id = invoice_id.strip()
    try:
        amount_f = float(amount)
    except ValueError:
        return templates.TemplateResponse(
            request,
            "ledger_form.html",
            {"title": "Record payable", "error": "Amount must be a number"},
            status_code=400,
        )
    with get_db() as db:
        existing = db.execute(
            "SELECT id FROM ledger WHERE vendor = ? AND invoice_id = ?",
            (vendor, invoice_id),
        ).fetchone()
        if existing:
            return templates.TemplateResponse(
                request,
                "ledger_form.html",
                {
                    "title": "Record payable",
                    "error": f"Duplicate payable: {vendor} {invoice_id} already exists as ledger #{existing['id']}",
                },
                status_code=409,
            )
        cur = db.execute(
            """INSERT INTO ledger (vendor, invoice_id, amount, due_date, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                vendor,
                invoice_id,
                amount_f,
                due_date.strip(),
                source.strip() or "inbox",
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
            ),
        )
        new_id = cur.lastrowid
    return RedirectResponse(f"/ledger?notice=created-{new_id}", status_code=303)


@router.get("/api/ledger")
def ledger_lookup(vendor: str | None = None, invoice_id: str | None = None):
    sql = "SELECT * FROM ledger WHERE 1=1"
    params: list[str] = []
    if vendor:
        sql += " AND vendor = ?"
        params.append(vendor)
    if invoice_id:
        sql += " AND invoice_id = ?"
        params.append(invoice_id)
    sql += " ORDER BY id DESC"
    with get_db() as db:
        rows = [dict(r) for r in db.execute(sql, params).fetchall()]
    return JSONResponse({"payables": rows, "count": len(rows)})
