from __future__ import annotations

from datetime import date, datetime, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models import Invoice, Payment, Receipt
from app.services.common import format_money, get_base_currency
from app.services.dashboard_metrics import get_dashboard_snapshot
from app.services.reservations import expired_hold_invoice_ids_query
from ...deps import get_current_user, get_db_session
from ...schemas import DashboardSummaryResponse

router = APIRouter()


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    _user: dict = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> DashboardSummaryResponse:
    now = datetime.now(timezone.utc)
    currency = get_base_currency()
    effective_end_date = end_date or now.date()
    effective_start_date = start_date or effective_end_date.replace(day=1)
    if effective_start_date > effective_end_date:
        effective_start_date, effective_end_date = effective_end_date, effective_start_date
    snapshot = get_dashboard_snapshot(
        session,
        as_of=now,
        currency=currency,
        start_date=effective_start_date,
        end_date=effective_end_date,
        include_occupancy_tables=False,
    )
    range_start = datetime.combine(effective_start_date, datetime.min.time(), tzinfo=timezone.utc)
    range_end = datetime.combine(effective_end_date, datetime.max.time(), tzinfo=timezone.utc)
    collected_period = session.execute(
        sa.select(sa.func.coalesce(sa.func.sum(Payment.amount), 0)).where(
            Payment.status != "voided",
            Payment.paid_at.is_not(None),
            Payment.currency == currency,
            Payment.paid_at >= range_start,
            Payment.paid_at <= range_end,
        )
    ).scalar_one()
    receipts_issued = session.execute(
        sa.select(sa.func.count(Receipt.id))
        .join(Payment, Payment.id == Receipt.payment_id)
        .where(
            Payment.status != "voided",
            Receipt.issued_at.is_not(None),
            Receipt.issued_at >= range_start,
            Receipt.issued_at <= range_end,
        )
    ).scalar_one()
    partially_paid_invoices = session.execute(
        sa.select(sa.func.count(Invoice.id)).where(Invoice.status == "partially_paid")
    ).scalar_one()
    hold_expired_invoices = session.execute(
        sa.select(sa.func.count()).select_from(expired_hold_invoice_ids_query().subquery())
    ).scalar_one()
    return DashboardSummaryResponse(
        start_date=effective_start_date.isoformat(),
        end_date=effective_end_date.isoformat(),
        available_beds=snapshot.occupancy.available_beds,
        occupied_beds=snapshot.occupancy.occupied_beds,
        reserved_beds=snapshot.occupancy.reserved_beds,
        occupancy_rate=round(snapshot.occupancy.occupancy_rate, 4),
        outstanding=format_money(snapshot.finance.outstanding, currency),
        collected_period=format_money(collected_period, currency),
        collected_mtd=format_money(snapshot.finance.collected_mtd, currency),
        receipts_issued=int(receipts_issued or 0),
        open_invoices=snapshot.finance.open_invoices,
        pending_approvals=snapshot.finance.pending_approvals,
        partially_paid_invoices=int(partially_paid_invoices or 0),
        hold_expired_invoices=int(hold_expired_invoices or 0),
        prospects=snapshot.onboarding.prospects,
        approved_unpaid=snapshot.onboarding.prospects_with_approved_unpaid,
        paid_unallocated=snapshot.onboarding.paid_unallocated_tenants,
    )
