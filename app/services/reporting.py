from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bed, Block, Floor, Invoice, Payment, Receipt, Room, Tenant
from app.services.common import format_money
from app.services.reservations import expired_hold_invoice_ids_query


def get_reporting_tables(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    currency: str,
) -> dict[str, list[dict[str, Any]]]:
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
    paid_subq = (
        select(
            Payment.invoice_id.label("invoice_id"),
            sa.func.coalesce(sa.func.sum(Payment.amount), 0).label("paid_total"),
        )
        .where(Payment.status != "voided")
        .group_by(Payment.invoice_id)
        .subquery()
    )

    collections_by_method = [
        {
            "Method": method or "unknown",
            "Transactions": int(count or 0),
            "Amount": format_money(amount, currency),
        }
        for method, count, amount in session.execute(
            select(
                Payment.method,
                sa.func.count(Payment.id),
                sa.func.coalesce(sa.func.sum(Payment.amount), 0),
            )
            .where(
                Payment.status != "voided",
                Payment.currency == currency,
                Payment.paid_at.is_not(None),
                Payment.paid_at >= start_dt,
                Payment.paid_at <= end_dt,
            )
            .group_by(Payment.method)
            .order_by(sa.func.coalesce(sa.func.sum(Payment.amount), 0).desc())
        ).all()
    ]

    aging_rows: list[dict[str, Any]] = []
    today = datetime.now(timezone.utc).date()
    invoices = session.execute(
        select(Invoice, Tenant, sa.func.coalesce(paid_subq.c.paid_total, 0))
        .join(Tenant, Tenant.id == Invoice.tenant_id)
        .outerjoin(paid_subq, paid_subq.c.invoice_id == Invoice.id)
        .where(
            Invoice.currency == currency,
            Invoice.status.in_(["approved", "partially_paid"]),
            ~Invoice.id.in_(expired_hold_invoice_ids_query()),
        )
        .order_by(Invoice.due_at.asc())
    ).all()
    for invoice, tenant, paid_total in invoices:
        balance = Decimal(str(invoice.total)) - Decimal(str(paid_total or 0))
        if balance <= 0:
            continue
        days_overdue = 0
        if invoice.due_at is not None:
            days_overdue = max((today - invoice.due_at.date()).days, 0)
        if days_overdue <= 0:
            bucket = "Current"
        elif days_overdue <= 30:
            bucket = "1-30"
        elif days_overdue <= 60:
            bucket = "31-60"
        else:
            bucket = "61+"
        aging_rows.append(
            {
                "Invoice": invoice.invoice_no,
                "Tenant": tenant.name,
                "Due": invoice.due_at.isoformat() if invoice.due_at else "",
                "Days overdue": days_overdue,
                "Bucket": bucket,
                "Balance": format_money(balance, currency),
            }
        )

    room_utilization = [
        {
            "Block": block_name,
            "Room": room_code,
            "Total beds": int(total or 0),
            "Occupied": int(occupied or 0),
            "Reserved": int(reserved or 0),
            "Available": int(available or 0),
            "Out of service": int(out_of_service or 0),
        }
        for block_name, room_code, total, occupied, reserved, available, out_of_service in session.execute(
            select(
                Block.name,
                Room.room_code,
                sa.func.count(Bed.id),
                sa.func.coalesce(sa.func.sum(sa.case((Bed.status == "OCCUPIED", 1), else_=0)), 0),
                sa.func.coalesce(sa.func.sum(sa.case((Bed.status == "RESERVED", 1), else_=0)), 0),
                sa.func.coalesce(sa.func.sum(sa.case((Bed.status == "AVAILABLE", 1), else_=0)), 0),
                sa.func.coalesce(sa.func.sum(sa.case((Bed.status == "OUT_OF_SERVICE", 1), else_=0)), 0),
            )
            .join(Block, Block.id == Room.block_id)
            .outerjoin(Bed, Bed.room_id == Room.id)
            .group_by(Block.name, Room.room_code)
            .order_by(Block.name.asc(), Room.room_code.asc())
        ).all()
    ]

    prospects = int(session.execute(select(sa.func.count(Tenant.id)).where(Tenant.status == "prospect")).scalar_one() or 0)
    active_tenants = int(session.execute(select(sa.func.count(Tenant.id)).where(Tenant.status == "active")).scalar_one() or 0)
    invoiced_tenants = int(
        session.execute(
            select(sa.func.count(sa.distinct(Invoice.tenant_id))).where(
                Invoice.created_at >= start_dt,
                Invoice.created_at <= end_dt,
            )
        ).scalar_one()
        or 0
    )
    conversion_rows = [
        {"Metric": "Prospects", "Value": prospects},
        {"Metric": "Tenants with invoices in period", "Value": invoiced_tenants},
        {"Metric": "Active tenants", "Value": active_tenants},
        {"Metric": "Prospect to invoiced", "Value": f"{(invoiced_tenants / prospects):.0%}" if prospects else "0%"},
    ]

    tenant_finance_rows = [
        {
            "Tenant": tenant_name,
            "Invoice": invoice_no or "-",
            "Payment": payment_no,
            "Receipt": receipt_no or "-",
            "Paid on": paid_at.isoformat() if paid_at is not None else "-",
            "Amount": format_money(amount, currency),
            "Balance": format_money(balance, currency),
        }
        for tenant_name, invoice_no, payment_no, receipt_no, paid_at, amount, balance in session.execute(
            select(
                Tenant.name,
                Invoice.invoice_no,
                Payment.payment_no,
                Receipt.receipt_no,
                sa.func.coalesce(Payment.paid_at, Payment.created_at),
                Payment.amount,
                sa.func.coalesce(Invoice.total, 0) - sa.func.coalesce(paid_subq.c.paid_total, 0),
            )
            .join(Tenant, Tenant.id == Payment.tenant_id)
            .outerjoin(Invoice, Invoice.id == Payment.invoice_id)
            .outerjoin(paid_subq, paid_subq.c.invoice_id == Invoice.id)
            .outerjoin(Receipt, Receipt.payment_id == Payment.id)
            .where(
                Payment.status != "voided",
                Payment.currency == currency,
                sa.func.coalesce(Payment.paid_at, Payment.created_at) >= start_dt,
                sa.func.coalesce(Payment.paid_at, Payment.created_at) <= end_dt,
            )
            .order_by(sa.func.coalesce(Payment.paid_at, Payment.created_at).desc(), Payment.id.desc())
        ).all()
    ]

    return {
        "collections_by_method": collections_by_method,
        "aging_rows": aging_rows,
        "room_utilization": room_utilization,
        "conversion_rows": conversion_rows,
        "tenant_finance_rows": tenant_finance_rows,
    }
