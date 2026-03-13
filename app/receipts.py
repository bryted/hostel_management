from __future__ import annotations

from io import BytesIO
import textwrap

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.models import HostelProfile, Invoice, Payment, Receipt, Tenant


def build_receipt_pdf(
    receipt: Receipt,
    payment: Payment,
    invoice: Invoice,
    tenant: Tenant,
    received_by: str | None,
    profile: HostelProfile | None = None,
    paid_before: str | None = None,
    balance_after: str | None = None,
    verification_code: str | None = None,
    verification_url: str | None = None,
) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=LETTER)
    width, height = LETTER

    def clamp(text: str | None, max_len: int) -> str:
        if not text:
            return ""
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    def wrap_text(text: str | None, width_chars: int) -> list[str]:
        if not text:
            return []
        return textwrap.wrap(text, width=width_chars)

    def draw_label_value(x: float, y: float, label: str, value: str, bold: bool = False) -> None:
        pdf.setFont("Helvetica", 8)
        pdf.setFillColor(MUTED)
        pdf.drawString(x, y, label)
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
        pdf.setFillColor(TEXT)
        pdf.drawString(x, y - 12, value)

    ACCENT = colors.HexColor("#2563EB")
    ACCENT_ALT = colors.HexColor("#0F172A")
    ACCENT_SOFT = colors.HexColor("#DBEAFE")
    TEXT = colors.HexColor("#0F172A")
    MUTED = colors.HexColor("#64748B")
    LINE = colors.HexColor("#E2E8F0")
    PANEL = colors.HexColor("#F8FAFC")
    WATERMARK = colors.HexColor("#DBEAFE")

    margin = 40
    header_height = 85
    header_top = height - margin
    header_bottom = header_top - header_height

    pdf.setFillColor(ACCENT_SOFT)
    pdf.rect(margin, header_bottom, width - (2 * margin), header_height, fill=1, stroke=0)

    pdf.saveState()
    pdf.translate(width / 2, height / 2)
    pdf.rotate(32)
    pdf.setFillColor(WATERMARK)
    pdf.setFont("Helvetica-Bold", 34)
    pdf.drawCentredString(0, 0, "VERIFIED RECEIPT")
    pdf.restoreState()

    if profile and profile.logo:
        try:
            image = ImageReader(BytesIO(profile.logo))
            logo_w = 90
            logo_h = 50
            logo_x = width - margin - logo_w - 8
            logo_y = header_top - logo_h - 12
            pdf.drawImage(
                image,
                logo_x,
                logo_y,
                width=logo_w,
                height=logo_h,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    hostel_name = profile.name if profile and profile.name else "Hostel"
    pdf.setFillColor(TEXT)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(margin + 10, header_top - 26, clamp(hostel_name, 40))
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(margin + 10, header_top - 50, "Payment receipt")

    issued_at_value = receipt.issued_at or receipt.created_at
    issued_at = issued_at_value.isoformat() if issued_at_value else ""
    right_x = width - margin - 190
    draw_label_value(right_x, header_top - 24, "Receipt No", receipt.receipt_no, bold=True)
    draw_label_value(right_x, header_top - 52, "Issued At", issued_at)

    contact_line = ""
    if profile:
        contact_parts = []
        if profile.address:
            contact_parts.append(profile.address.replace("\n", " "))
        if profile.phone:
            contact_parts.append(f"Phone: {profile.phone}")
        if profile.email:
            contact_parts.append(f"Email: {profile.email}")
        contact_line = " | ".join([part for part in contact_parts if part])

    if contact_line:
        pdf.setFont("Helvetica", 8)
        pdf.setFillColor(MUTED)
        pdf.drawString(margin + 10, header_bottom - 18, clamp(contact_line, 110))

    content_top = header_bottom - 36
    gutter = 18
    col_width = (width - (2 * margin) - gutter) / 2
    box_height = 110

    pdf.setStrokeColor(LINE)
    pdf.setLineWidth(1)
    pdf.rect(margin, content_top - box_height, col_width, box_height, stroke=1, fill=0)
    pdf.rect(margin + col_width + gutter, content_top - box_height, col_width, box_height, stroke=1, fill=0)

    pdf.setFont("Helvetica-Bold", 9)
    pdf.setFillColor(MUTED)
    pdf.drawString(margin + 12, content_top - 18, "BILL TO")
    pdf.drawString(margin + col_width + gutter + 12, content_top - 18, "PAYMENT DETAILS")

    pdf.setFillColor(TEXT)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(margin + 12, content_top - 35, clamp(tenant.name, 36))
    pdf.setFont("Helvetica", 9)
    tenant_lines = [
        f"Email: {tenant.email or ''}",
        f"Phone: {tenant.phone or ''}",
        f"Room: {tenant.room or ''}",
    ]
    ty = content_top - 52
    for line in tenant_lines:
        pdf.drawString(margin + 12, ty, line)
        ty -= 13

    pdf.setFont("Helvetica", 9)
    pdx = margin + col_width + gutter + 12
    pdy = content_top - 35
    pdf.drawString(pdx, pdy, f"Received by: {received_by or ''}")
    pdf.drawString(pdx, pdy - 13, f"Method: {payment.method or ''}")
    ref_line = clamp(payment.reference or "", 48)
    pdf.drawString(pdx, pdy - 26, f"Reference: {ref_line}")

    line_y = content_top - box_height - 18
    pdf.setStrokeColor(LINE)
    pdf.line(margin, line_y, width - margin, line_y)

    info_y = line_y - 20
    draw_label_value(margin, info_y, "Invoice No", invoice.invoice_no, bold=True)
    draw_label_value(margin + 200, info_y, "Payment No", payment.payment_no)

    summary_width = 220
    summary_height = 124
    summary_x = width - margin - summary_width
    summary_top = info_y - 8
    pdf.setFillColor(PANEL)
    pdf.setStrokeColor(LINE)
    pdf.rect(summary_x, summary_top - summary_height, summary_width, summary_height, fill=1, stroke=1)

    pdf.setFillColor(TEXT)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(summary_x + 12, summary_top - 20, "Summary")
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(MUTED)
    pdf.drawString(summary_x + 12, summary_top - 36, "Invoice Total")
    pdf.drawString(summary_x + 12, summary_top - 52, "Amount Paid")
    if paid_before is not None:
        pdf.drawString(summary_x + 12, summary_top - 68, "Paid Before")
    if balance_after is not None:
        pdf.drawString(summary_x + 12, summary_top - 84, "Balance After")
    if verification_code:
        pdf.drawString(summary_x + 12, summary_top - 100, "Security Code")

    pdf.setFillColor(TEXT)
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(
        summary_x + summary_width - 12,
        summary_top - 36,
        f"{invoice.currency} {invoice.total}",
    )
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawRightString(
        summary_x + summary_width - 12,
        summary_top - 52,
        f"{receipt.currency} {receipt.amount}",
    )
    pdf.setFont("Helvetica", 9)
    if paid_before is not None:
        pdf.drawRightString(
            summary_x + summary_width - 12,
            summary_top - 68,
            f"{receipt.currency} {paid_before}",
        )
    if balance_after is not None:
        pdf.drawRightString(
            summary_x + summary_width - 12,
            summary_top - 84,
            f"{receipt.currency} {balance_after}",
        )
    if verification_code:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawRightString(
            summary_x + summary_width - 12,
            summary_top - 100,
            verification_code,
        )

    notes_y = summary_top - summary_height - 18
    if invoice.notes:
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(margin, notes_y, "Notes")
        pdf.setFillColor(TEXT)
        pdf.setFont("Helvetica", 9)
        for idx, line in enumerate(wrap_text(invoice.notes.replace("\n", " "), 90)[:3]):
            pdf.drawString(margin, notes_y - 14 - (idx * 12), line)
        notes_y -= 60

    footer_text = profile.footer_text if profile and profile.footer_text else "Keep this receipt for reconciliation and room handoff."
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(MUTED)
    pdf.line(margin, 70, width - margin, 70)
    pdf.drawString(margin, 55, clamp(footer_text.replace("\n", " "), 110))
    if verification_url:
        pdf.setFillColor(ACCENT_ALT)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(margin, 40, "Verify receipt")
        pdf.setFont("Helvetica", 8)
        pdf.setFillColor(MUTED)
        pdf.drawString(margin + 64, 40, clamp(verification_url, 84))
    if verification_code:
        pdf.setFillColor(ACCENT_ALT)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawRightString(width - margin, 40, f"Code {verification_code}")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
