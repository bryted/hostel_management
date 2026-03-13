from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.services.lifecycle import cancel_reservation_hold, extend_reservation_hold
from ...deps import get_db_session, require_admin
from ...schemas import ActionResponse, CancelReservationRequest, ExtendReservationRequest

router = APIRouter()


@router.post("/{reservation_id}/extend", response_model=ActionResponse)
def extend_reservation(
    reservation_id: int,
    payload: ExtendReservationRequest,
    session: Session = Depends(get_db_session),
    user: dict = Depends(require_admin),
) -> ActionResponse:
    try:
        reservation = extend_reservation_hold(
            session,
            reservation_id=reservation_id,
            extra_hours=payload.extra_hours,
            user_id=int(user["id"]),
            reason=payload.reason,
            now=datetime.now(timezone.utc),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ActionResponse(
        message="Reservation hold extended.",
        reservation_id=int(reservation.id),
        bed_id=int(reservation.bed_id),
    )


@router.post("/{reservation_id}/cancel", response_model=ActionResponse)
def cancel_reservation(
    reservation_id: int,
    payload: CancelReservationRequest,
    session: Session = Depends(get_db_session),
    user: dict = Depends(require_admin),
) -> ActionResponse:
    try:
        reservation = cancel_reservation_hold(
            session,
            reservation_id=reservation_id,
            user_id=int(user["id"]),
            reason=payload.reason,
            now=datetime.now(timezone.utc),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ActionResponse(
        message="Reservation cancelled.",
        reservation_id=int(reservation.id),
        bed_id=int(reservation.bed_id),
    )
