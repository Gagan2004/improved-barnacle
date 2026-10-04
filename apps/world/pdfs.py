from __future__ import annotations

from pathlib import Path

from fpdf import FPDF


def write_invoice_pdf(
    path: Path,
    vendor: str,
    invoice_id: str,
    amount: float,
    due_date: str,
    issued: str,
) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, vendor.upper(), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 8, f"INVOICE {invoice_id}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Issued: {issued}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Due date: {due_date}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Amount due: {amount:.2f} USD", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Bill to: Atrium Operations, Accounts Payable", new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))


def write_garbage_pdf(path: Path) -> None:
    path.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<>\n%%EOF\n" + bytes(range(256)))
