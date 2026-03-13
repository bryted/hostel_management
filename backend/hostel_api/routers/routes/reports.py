from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.services.common import format_money, get_base_currency
from app.services.dashboard_metrics import get_dashboard_snapshot
from app.services.reporting import get_reporting_tables
from ...deps import get_db_session, require_admin
from ...schemas import ReportsOverviewResponse

router = APIRouter()


@router.get("/overview", response_model=ReportsOverviewResponse)
def get_reports_overview(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    session: Session = Depends(get_db_session),
    _user: dict = Depends(require_admin),
) -> ReportsOverviewResponse:
    now = datetime.now(timezone.utc)
    report_start = start_date or now.date()
    report_end = end_date or now.date()
    if report_end < report_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date must be on or after start date.",
        )
    currency = get_base_currency()
    snapshot = get_dashboard_snapshot(
        session,
        as_of=now,
        currency=currency,
        start_date=report_start,
        end_date=report_end,
        include_occupancy_tables=True,
    )
    tables = get_reporting_tables(
        session,
        start_date=report_start,
        end_date=report_end,
        currency=currency,
    )
    return ReportsOverviewResponse(
        start_date=report_start.isoformat(),
        end_date=report_end.isoformat(),
        collected_today=format_money(snapshot.finance.collected_today, currency),
        collected_mtd=format_money(snapshot.finance.collected_mtd, currency),
        collected_ytd=format_money(snapshot.finance.collected_ytd, currency),
        outstanding=format_money(snapshot.finance.outstanding, currency),
        receipts_issued_today=int(snapshot.finance.receipts_issued_today),
        open_invoices=int(snapshot.finance.open_invoices),
        pending_approvals=int(snapshot.finance.pending_approvals),
        block_occupancy_rows=snapshot.block_occupancy_rows,
        floor_occupancy_rows=snapshot.floor_occupancy_rows,
        collections_by_method=tables["collections_by_method"],
        aging_rows=tables["aging_rows"],
        room_utilization=tables["room_utilization"],
        conversion_rows=tables["conversion_rows"],
        tenant_finance_rows=tables["tenant_finance_rows"],
    )


@router.get("/finance-export.csv")
def download_finance_export(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    session: Session = Depends(get_db_session),
    _user: dict = Depends(require_admin),
) -> Response:
    now = datetime.now(timezone.utc)
    report_start = start_date or now.date()
    report_end = end_date or now.date()
    if report_end < report_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date must be on or after start date.",
        )
    tables = get_reporting_tables(
        session,
        start_date=report_start,
        end_date=report_end,
        currency=get_base_currency(),
    )
    rows = tables["tenant_finance_rows"]
    columns = list(rows[0].keys()) if rows else ["Tenant", "Invoice", "Payment", "Receipt", "Paid on", "Amount", "Balance"]
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    filename = f"tenant-finance-{report_start.isoformat()}-{report_end.isoformat()}.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
