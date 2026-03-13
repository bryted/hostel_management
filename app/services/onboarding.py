from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.models import Allocation, Bed, BedReservation, Invoice, Payment, Room, Tenant, TenantEvent
from app.services.reservations import invoice_hold_expired
from app.services.types import ConversionResult, OnboardingPipelineSnapshot


def _paid_totals_subquery() -> sa.Subquery:
    return (
        select(
            Payment.invoice_id.label("invoice_id"),
            sa.func.coalesce(sa.func.sum(Payment.amount), 0).label("paid_total"),
        )
        .where(Payment.status != "voided")
        .group_by(Payment.invoice_id)
        .subquery()
    )


def _queue_base_query(
    block_id: int | None = None,
    floor_id: int | None = None,
) -> sa.Select:
    paid_subq = _paid_totals_subquery()
    paid_total_expr = sa.func.coalesce(paid_subq.c.paid_total, 0)

    has_confirmed_allocation = sa.exists(
        select(Allocation.id).where(
            Allocation.invoice_id == Invoice.id,
            Allocation.status == "CONFIRMED",
        )
    )
    approved_unpaid_condition = sa.and_(
        Invoice.status.in_(["approved", "partially_paid"]),
        paid_total_expr == 0,
    )
    paid_unallocated_condition = sa.and_(
        paid_total_expr > 0,
        Invoice.status != "rejected",
        ~has_confirmed_allocation,
    )

    active_reservation_bed_subq = (
        select(
            sa.func.min(Bed.id).label("reservation_bed_id"),
            BedReservation.invoice_id.label("invoice_id"),
        )
        .join(Bed, Bed.id == BedReservation.bed_id)
        .where(BedReservation.status == "ACTIVE", BedReservation.invoice_id.is_not(None))
        .group_by(BedReservation.invoice_id)
        .subquery()
    )

    invoice_bed = aliased(Bed)
    invoice_room = aliased(Room)
    reservation_bed = aliased(Bed)
    reservation_room = aliased(Room)

    effective_block_id = sa.func.coalesce(invoice_room.block_id, reservation_room.block_id)
    effective_floor_id = sa.func.coalesce(invoice_room.floor_id, reservation_room.floor_id)
    effective_reserved_bed_id = sa.func.coalesce(
        Invoice.reserved_bed_id,
        active_reservation_bed_subq.c.reservation_bed_id,
    )

    queue_query = (
        select(
            Tenant.id.label("tenant_id"),
            Tenant.name.label("tenant_name"),
            Invoice.id.label("invoice_id"),
            Invoice.invoice_no.label("invoice_no"),
            Invoice.status.label("invoice_status"),
            Invoice.total.label("invoice_total"),
            paid_total_expr.label("paid_total"),
            effective_reserved_bed_id.label("reserved_bed_id"),
            Invoice.created_at.label("created_at"),
            sa.case(
                (paid_total_expr > 0, "Paid unallocated"),
                else_="Approved unpaid",
            ).label("stage"),
        )
        .join(Invoice, Invoice.tenant_id == Tenant.id)
        .outerjoin(paid_subq, paid_subq.c.invoice_id == Invoice.id)
        .outerjoin(invoice_bed, invoice_bed.id == Invoice.reserved_bed_id)
        .outerjoin(invoice_room, invoice_room.id == invoice_bed.room_id)
        .outerjoin(active_reservation_bed_subq, active_reservation_bed_subq.c.invoice_id == Invoice.id)
        .outerjoin(reservation_bed, reservation_bed.id == active_reservation_bed_subq.c.reservation_bed_id)
        .outerjoin(reservation_room, reservation_room.id == reservation_bed.room_id)
        .where(sa.or_(approved_unpaid_condition, paid_unallocated_condition))
    )
    if block_id is not None:
        queue_query = queue_query.where(
            sa.or_(
                effective_block_id == block_id,
                effective_block_id.is_(None),
            )
        )
    if floor_id is not None:
        queue_query = queue_query.where(
            sa.or_(
                effective_floor_id == floor_id,
                effective_floor_id.is_(None),
            )
        )
    return queue_query


def get_onboarding_queue_counts(
    session: Session,
    *,
    block_id: int | None = None,
    floor_id: int | None = None,
) -> dict[str, int]:
    queue_subq = _queue_base_query(block_id=block_id, floor_id=floor_id).subquery()
    approved_unpaid_count, paid_unallocated_count = session.execute(
        select(
            sa.func.coalesce(
                sa.func.sum(sa.case((queue_subq.c.stage == "Approved unpaid", 1), else_=0)),
                0,
            ),
            sa.func.coalesce(
                sa.func.sum(sa.case((queue_subq.c.stage == "Paid unallocated", 1), else_=0)),
                0,
            ),
        )
    ).one()
    return {
        "Approved unpaid": int(approved_unpaid_count or 0),
        "Paid unallocated": int(paid_unallocated_count or 0),
    }


def get_onboarding_pipeline(
    session: Session,
    as_of: datetime | None = None,
    block_id: int | None = None,
    floor_id: int | None = None,
) -> OnboardingPipelineSnapshot:
    now = as_of or datetime.now(timezone.utc)

    prospects = session.execute(
        select(sa.func.count(Tenant.id)).where(Tenant.status == "prospect")
    ).scalar_one()

    queue_counts = get_onboarding_queue_counts(
        session,
        block_id=block_id,
        floor_id=floor_id,
    )
    prospects_with_approved_unpaid = queue_counts["Approved unpaid"]
    paid_unallocated_tenants = queue_counts["Paid unallocated"]

    active_allocated_query = (
        select(sa.func.count(sa.distinct(Allocation.invoice_id)))
        .join(Tenant, Tenant.id == Allocation.tenant_id)
        .join(Bed, Bed.id == Allocation.bed_id)
        .join(Room, Room.id == Bed.room_id)
        .where(
            Allocation.status == "CONFIRMED",
            Tenant.status == "active",
            Allocation.invoice_id.is_not(None),
        )
    )
    if block_id is not None:
        active_allocated_query = active_allocated_query.where(Room.block_id == block_id)
    if floor_id is not None:
        active_allocated_query = active_allocated_query.where(Room.floor_id == floor_id)
    active_allocated_tenants = session.execute(active_allocated_query).scalar_one()

    activation_events = ["TENANT_ACTIVATED_PENDING_ALLOCATION", "TENANT_CONFIRMED"]
    newly_activated_last_7d = session.execute(
        select(sa.func.count(sa.distinct(TenantEvent.tenant_id))).where(
            TenantEvent.event_type.in_(activation_events),
            TenantEvent.event_at >= (now - timedelta(days=7)),
        )
    ).scalar_one()

    return OnboardingPipelineSnapshot(
        prospects=int(prospects or 0),
        prospects_with_approved_unpaid=int(prospects_with_approved_unpaid or 0),
        paid_unallocated_tenants=int(paid_unallocated_tenants or 0),
        active_allocated_tenants=int(active_allocated_tenants or 0),
        newly_activated_last_7d=int(newly_activated_last_7d or 0),
    )


def get_onboarding_queue(
    session: Session,
    limit: int = 50,
    block_id: int | None = None,
    floor_id: int | None = None,
) -> list[dict[str, object]]:
    queue_query = _queue_base_query(block_id=block_id, floor_id=floor_id)
    queue_rows = session.execute(
        queue_query.order_by(
            sa.column("created_at").asc(),
            sa.column("invoice_id").asc(),
        ).limit(limit)
    ).all()

    rows_by_invoice: dict[int, tuple[datetime, int, dict[str, object]]] = {}

    def _row_payload(
        stage: str,
        tenant_id: int,
        tenant_name: str,
        invoice_id: int,
        invoice_no: str,
        status: str,
        total: object,
        paid_total: object,
        reserved_bed_id: int | None,
    ) -> dict[str, object]:
        return {
            "Stage": stage,
            "Tenant ID": tenant_id,
            "Tenant": tenant_name,
            "Invoice ID": invoice_id,
            "Invoice": invoice_no,
            "Invoice status": status,
            "Total": str(total),
            "Paid": str(paid_total),
            "Reserved bed ID": reserved_bed_id,
            "Hold expired": invoice_hold_expired(session, invoice_id),
        }

    for tenant_id, tenant_name, invoice_id, invoice_no, status, total, paid_total, reserved_bed_id, created_at, stage in queue_rows:
        key = int(invoice_id)
        payload = _row_payload(
            str(stage),
            int(tenant_id),
            str(tenant_name),
            key,
            str(invoice_no),
            str(status),
            total,
            paid_total,
            reserved_bed_id,
        )
        existing = rows_by_invoice.get(key)
        if existing is None:
            rows_by_invoice[key] = (created_at, key, payload)
            continue
        # Defensive duplicate resolution: keep paid-unallocated precedence.
        if payload["Stage"] == "Paid unallocated" and existing[2].get("Stage") != "Paid unallocated":
            rows_by_invoice[key] = (created_at, key, payload)

    sorted_rows = sorted(rows_by_invoice.values(), key=lambda item: (item[0], item[1]))
    return [row for _, _, row in sorted_rows[:limit]]


def apply_first_payment_conversion(
    session: Session,
    tenant_id: int,
    invoice_id: int | None,
    user_id: int | None,
    now: datetime,
) -> ConversionResult:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        return ConversionResult(activated=False, details={"reason": "tenant_not_found"})

    successful_payment_count = session.execute(
        select(sa.func.count(Payment.id)).where(
            Payment.tenant_id == tenant_id,
            Payment.status != "voided",
            Payment.paid_at.is_not(None),
        )
    ).scalar_one()

    if int(successful_payment_count or 0) != 1:
        return ConversionResult(activated=False, details={"reason": "not_first_payment"})

    allocation_exists = session.execute(
        select(Allocation.id)
        .where(Allocation.tenant_id == tenant_id, Allocation.status == "CONFIRMED")
        .limit(1)
    ).scalar_one_or_none()

    event_type = "TENANT_CONFIRMED" if allocation_exists else "TENANT_ACTIVATED_PENDING_ALLOCATION"

    activated = False
    if tenant.status != "active":
        tenant.status = "active"
        activated = True

    session.add(
        TenantEvent(
            tenant_id=tenant.id,
            event_type=event_type,
            event_at=now,
            user_id=user_id,
            detail_json={
                "invoice_id": invoice_id,
                "first_payment": True,
                "has_allocation": bool(allocation_exists),
            },
        )
    )

    return ConversionResult(
        activated=activated,
        event_type=event_type,
        details={"invoice_id": invoice_id},
    )
