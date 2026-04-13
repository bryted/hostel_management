from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcademicYear, Bed, Block, Floor, Invoice, Payment, PaymentAllocation, Receipt, Room, Tenant
from app.services.common import format_money
from app.services.invoicing import paid_totals_subquery
from app.services.reservations import expired_hold_invoice_ids_query


def _paginate_query(
    session: Session,
    query: sa.Select,
    *,
    page: int,
    page_size: int | None,
) -> tuple[int, list[Any]]:
    if page_size is None:
        rows = session.execute(query).all()
        return len(rows), rows
    total = int(
        session.execute(
            select(sa.func.count()).select_from(query.order_by(None).subquery())
        ).scalar_one()
        or 0
    )
    rows = session.execute(query.offset((page - 1) * page_size).limit(page_size)).all()
    return total, rows


def get_reporting_tables(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    currency: str,
    include_finance: bool = True,
    include_occupancy: bool = True,
    include_conversion: bool = True,
    academic_year_id: int | None = None,
    tenant_query: str = "",
    aging_page: int = 1,
    aging_page_size: int | None = 50,
    room_page: int = 1,
    room_page_size: int | None = 50,
    finance_page: int = 1,
    finance_page_size: int | None = 50,
) -> dict[str, Any]:
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
    paid_subq = paid_totals_subquery()
    payment_allocated_subq = (
        select(
            PaymentAllocation.payment_id.label("payment_id"),
            sa.func.coalesce(sa.func.sum(PaymentAllocation.allocated_amount), 0).label("allocated_total"),
        )
        .group_by(PaymentAllocation.payment_id)
        .subquery()
    )
    tenant_pattern = f"%{tenant_query.strip()}%" if tenant_query.strip() else None
    available_academic_years = [
        {
            "id": int(year.id),
            "label": year.label,
            "start_date": year.start_date.isoformat(),
            "end_date": year.end_date.isoformat(),
            "is_current": bool(year.is_current),
            "is_closed": bool(year.is_closed),
        }
        for year in session.execute(
            select(AcademicYear).order_by(AcademicYear.start_date.desc(), AcademicYear.id.desc())
        ).scalars().all()
    ]

    collections_by_method: list[dict[str, Any]] = []
    aging_rows: list[dict[str, Any]] = []
    aging_total = 0
    tenant_finance_rows: list[dict[str, Any]] = []
    tenant_finance_total = 0
    if include_finance:
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
            .where(Payment.academic_year_id == academic_year_id if academic_year_id is not None else sa.true())
            .group_by(Payment.method)
            .order_by(sa.func.coalesce(sa.func.sum(Payment.amount), 0).desc())
            ).all()
        ]

        today = datetime.now(timezone.utc).date()
        balance_expr = sa.func.coalesce(Invoice.total, 0) - sa.func.coalesce(paid_subq.c.paid_total, 0)
        aging_query = (
            select(Invoice, Tenant, sa.func.coalesce(paid_subq.c.paid_total, 0))
            .join(Tenant, Tenant.id == Invoice.tenant_id)
            .outerjoin(paid_subq, paid_subq.c.invoice_id == Invoice.id)
            .where(
                Invoice.currency == currency,
                Invoice.status.in_(["approved", "partially_paid"]),
                ~Invoice.id.in_(expired_hold_invoice_ids_query()),
                balance_expr > 0,
            )
            .where(Invoice.academic_year_id == academic_year_id if academic_year_id is not None else sa.true())
            .order_by(Invoice.due_at.asc())
        )
        if tenant_pattern:
            aging_query = aging_query.where(Tenant.name.ilike(tenant_pattern))
        aging_total, invoices = _paginate_query(
            session,
            aging_query,
            page=aging_page,
            page_size=aging_page_size,
        )
        for invoice, tenant, paid_total in invoices:
            balance = Decimal(str(invoice.total)) - Decimal(str(paid_total or 0))
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

        tenant_finance_query = (
            select(
                AcademicYear.label,
                Tenant.name,
                Invoice.invoice_no,
                Payment.payment_no,
                Receipt.receipt_no,
                sa.func.coalesce(Payment.paid_at, Payment.created_at),
                Payment.amount,
                PaymentAllocation.allocated_amount,
                sa.func.coalesce(Invoice.total, 0) - sa.func.coalesce(paid_subq.c.paid_total, 0),
                sa.func.coalesce(payment_allocated_subq.c.allocated_total, 0),
                Payment.id,
            )
            .join(Tenant, Tenant.id == Payment.tenant_id)
            .outerjoin(AcademicYear, AcademicYear.id == Payment.academic_year_id)
            .outerjoin(PaymentAllocation, PaymentAllocation.payment_id == Payment.id)
            .outerjoin(Invoice, Invoice.id == PaymentAllocation.invoice_id)
            .outerjoin(paid_subq, paid_subq.c.invoice_id == Invoice.id)
            .outerjoin(payment_allocated_subq, payment_allocated_subq.c.payment_id == Payment.id)
            .outerjoin(Receipt, Receipt.payment_id == Payment.id)
            .where(
                Payment.status != "voided",
                Payment.currency == currency,
                sa.func.coalesce(Payment.paid_at, Payment.created_at) >= start_dt,
                sa.func.coalesce(Payment.paid_at, Payment.created_at) <= end_dt,
            )
            .where(Payment.academic_year_id == academic_year_id if academic_year_id is not None else sa.true())
            .order_by(sa.func.coalesce(Payment.paid_at, Payment.created_at).desc(), Payment.id.desc())
        )
        if tenant_pattern:
            tenant_finance_query = tenant_finance_query.where(Tenant.name.ilike(tenant_pattern))
        tenant_finance_total, tenant_finance_rows_raw = _paginate_query(
            session,
            tenant_finance_query,
            page=finance_page,
            page_size=finance_page_size,
        )
        tenant_finance_rows = [
            {
                "Academic year": academic_year_label or "-",
                "Tenant": tenant_name,
                "Invoice": invoice_no or "-",
                "Payment": payment_no,
                "Receipt": receipt_no or "-",
                "Paid on": paid_at.isoformat() if paid_at is not None else "-",
                "Payment amount": format_money(amount, currency),
                "Allocated": format_money(allocated_amount or 0, currency),
                "Unallocated": format_money(Decimal(str(amount or 0)) - Decimal(str(allocated_total or 0)), currency),
                "Balance": format_money(balance, currency) if invoice_no else "-",
            }
            for academic_year_label, tenant_name, invoice_no, payment_no, receipt_no, paid_at, amount, allocated_amount, balance, allocated_total, payment_id in tenant_finance_rows_raw
        ]

    room_utilization: list[dict[str, Any]] = []
    room_utilization_total = 0
    if include_occupancy:
        room_utilization_query = (
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
        )
        room_utilization_total, room_utilization_rows = _paginate_query(
            session,
            room_utilization_query,
            page=room_page,
            page_size=room_page_size,
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
            for block_name, room_code, total, occupied, reserved, available, out_of_service in room_utilization_rows
        ]

    conversion_rows: list[dict[str, Any]] = []
    if include_conversion:
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

    return {
        "collections_by_method": collections_by_method,
        "aging_rows": aging_rows,
        "aging_total": aging_total,
        "aging_page": aging_page,
        "aging_page_size": aging_page_size or max(aging_total, 1),
        "room_utilization": room_utilization,
        "room_utilization_total": room_utilization_total,
        "room_page": room_page,
        "room_page_size": room_page_size or max(room_utilization_total, 1),
        "conversion_rows": conversion_rows,
        "tenant_finance_rows": tenant_finance_rows,
        "tenant_finance_total": tenant_finance_total,
        "finance_page": finance_page,
        "finance_page_size": finance_page_size or max(tenant_finance_total, 1),
        "available_academic_years": available_academic_years,
        "selected_academic_year_id": academic_year_id,
        "tenant_query": tenant_query.strip(),
    }
