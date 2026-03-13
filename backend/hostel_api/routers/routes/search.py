from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Allocation, Bed, Block, Floor, Invoice, Payment, Receipt, Room, Tenant, User
from ...deps import get_current_user, get_db_session
from ...schemas import SearchResponse, SearchResultItem

router = APIRouter()


def _pattern(query: str) -> str:
    return f"%{query.strip()}%"


@router.get("", response_model=SearchResponse)
def global_search(
    q: str = Query(min_length=1),
    limit: int = Query(default=12, ge=1, le=50),
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> SearchResponse:
    pattern = _pattern(q)
    results: list[SearchResultItem] = []

    tenants = session.execute(
        select(Tenant)
        .where(
            sa.or_(
                Tenant.name.ilike(pattern),
                Tenant.email.ilike(pattern),
                Tenant.phone.ilike(pattern),
            )
        )
        .order_by(Tenant.name.asc())
        .limit(limit)
    ).scalars().all()
    for tenant in tenants:
        results.append(
            SearchResultItem(
                type="tenant",
                id=int(tenant.id),
                title=tenant.name,
                subtitle=f"{tenant.status} | {tenant.email or tenant.phone or 'No contact'}",
                href=f"/tenants/{int(tenant.id)}",
            )
        )

    invoices = session.execute(
        select(Invoice, Tenant)
        .join(Tenant, Tenant.id == Invoice.tenant_id)
        .where(
            sa.or_(
                Invoice.invoice_no.ilike(pattern),
                Tenant.name.ilike(pattern),
                Invoice.status.ilike(pattern),
            )
        )
        .order_by(sa.func.coalesce(Invoice.issued_at, Invoice.created_at).desc())
        .limit(limit)
    ).all()
    for invoice, tenant in invoices:
        results.append(
            SearchResultItem(
                type="invoice",
                id=int(invoice.id),
                title=invoice.invoice_no,
                subtitle=f"{tenant.name} | {invoice.status}",
                href=f"/invoices/{int(invoice.id)}",
            )
        )

    receipts = session.execute(
        select(Receipt, Tenant)
        .join(Tenant, Tenant.id == Receipt.tenant_id)
        .where(
            sa.or_(
                Receipt.receipt_no.ilike(pattern),
                Tenant.name.ilike(pattern),
            )
        )
        .order_by(sa.func.coalesce(Receipt.issued_at, Receipt.created_at).desc())
        .limit(limit)
    ).all()
    for receipt, tenant in receipts:
        results.append(
            SearchResultItem(
                type="receipt",
                id=int(receipt.id),
                title=receipt.receipt_no,
                subtitle=f"{tenant.name}",
                href=f"/receipts/{int(receipt.id)}",
            )
        )

    payments = session.execute(
        select(Payment, Tenant, Invoice)
        .join(Tenant, Tenant.id == Payment.tenant_id)
        .outerjoin(Invoice, Invoice.id == Payment.invoice_id)
        .where(
            sa.or_(
                Payment.payment_no.ilike(pattern),
                Payment.reference.ilike(pattern),
                Tenant.name.ilike(pattern),
                Invoice.invoice_no.ilike(pattern),
            )
        )
        .order_by(sa.func.coalesce(Payment.paid_at, Payment.created_at).desc())
        .limit(limit)
    ).all()
    for payment, tenant, invoice in payments:
        results.append(
            SearchResultItem(
                type="payment",
                id=int(payment.id),
                title=payment.payment_no,
                subtitle=f"{tenant.name} | {payment.reference or payment.method or 'payment'}",
                href=f"/billing?invoiceId={int(invoice.id)}" if invoice is not None else "/billing",
            )
        )

    beds = session.execute(
        select(Bed, Room, Floor, Block)
        .join(Room, Room.id == Bed.room_id)
        .join(Block, Block.id == Room.block_id)
        .outerjoin(Floor, Floor.id == Room.floor_id)
        .where(
            sa.or_(
                Block.name.ilike(pattern),
                Room.room_code.ilike(pattern),
                Bed.bed_label.ilike(pattern),
                sa.cast(Bed.status, sa.String).ilike(pattern),
            )
        )
        .order_by(Block.name.asc(), Room.room_code.asc(), Bed.bed_number.asc())
        .limit(limit)
    ).all()
    for bed, room, floor, block in beds:
        floor_label = floor.floor_label if floor is not None else "Unassigned"
        results.append(
            SearchResultItem(
                type="bed",
                id=int(bed.id),
                title=f"{block.name} / {floor_label} / {room.room_code} / {bed.bed_label}",
                subtitle=bed.status,
                href=f"/beds?search={bed.bed_label}",
            )
        )

    rooms = session.execute(
        select(Room, Floor, Block)
        .join(Block, Block.id == Room.block_id)
        .outerjoin(Floor, Floor.id == Room.floor_id)
        .where(
            sa.or_(
                Block.name.ilike(pattern),
                Room.room_code.ilike(pattern),
                Room.room_type.ilike(pattern),
            )
        )
        .order_by(Block.name.asc(), Room.room_code.asc())
        .limit(limit)
    ).all()
    for room, floor, block in rooms:
        floor_label = floor.floor_label if floor is not None else "Unassigned"
        results.append(
            SearchResultItem(
                type="room",
                id=int(room.id),
                title=f"{block.name} / {floor_label} / {room.room_code}",
                subtitle=room.room_type or "Room",
                href=f"/inventory",
            )
        )

    allocations = session.execute(
        select(Allocation, Tenant, Bed, Room, Floor, Block)
        .join(Tenant, Tenant.id == Allocation.tenant_id)
        .join(Bed, Bed.id == Allocation.bed_id)
        .join(Room, Room.id == Bed.room_id)
        .join(Block, Block.id == Room.block_id)
        .outerjoin(Floor, Floor.id == Room.floor_id)
        .where(
            Allocation.status == "CONFIRMED",
            sa.or_(
                Tenant.name.ilike(pattern),
                Room.room_code.ilike(pattern),
                Bed.bed_label.ilike(pattern),
                Block.name.ilike(pattern),
            ),
        )
        .order_by(Allocation.created_at.desc())
        .limit(limit)
    ).all()
    for allocation, tenant, bed, room, floor, block in allocations:
        floor_label = floor.floor_label if floor is not None else "Unassigned"
        results.append(
            SearchResultItem(
                type="allocation",
                id=int(allocation.id),
                title=tenant.name,
                subtitle=f"{block.name} / {floor_label} / {room.room_code} / {bed.bed_label}",
                href=f"/allocations?search={tenant.name}",
            )
        )

    if bool(user.get("is_admin")):
        users = session.execute(
            select(User)
            .where(
                sa.or_(
                    User.full_name.ilike(pattern),
                    User.email.ilike(pattern),
                )
            )
            .order_by(User.full_name.asc())
            .limit(limit)
        ).scalars().all()
        for account in users:
            results.append(
                SearchResultItem(
                    type="user",
                    id=int(account.id),
                    title=account.full_name,
                    subtitle=account.email,
                    href="/settings",
                )
            )
        results.append(
            SearchResultItem(
                type="workflow",
                id=0,
                title="Onboarding queue",
                subtitle="Admin queue and approvals",
                href=f"/onboarding?search={q.strip()}",
            )
        )

    ordered = results[: limit]
    return SearchResponse(results=ordered)
