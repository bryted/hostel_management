from __future__ import annotations

import os
from datetime import date, datetime, timezone

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcademicYear


def academic_year_start_month() -> int:
    raw = (os.getenv("ACADEMIC_YEAR_START_MONTH") or "").strip()
    if not raw:
        return 9
    try:
        month = int(raw)
    except ValueError:
        return 9
    return month if 1 <= month <= 12 else 9


def normalize_date(value: date | datetime | None) -> date:
    if value is None:
        return datetime.now(timezone.utc).date()
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).date()
        return value.date()
    return value


def academic_year_bounds_for_date(value: date | datetime | None) -> tuple[date, date, str]:
    target = normalize_date(value)
    start_month = academic_year_start_month()
    start_year = target.year if target.month >= start_month else target.year - 1
    return _academic_year_bounds(start_year, start_month)


def _academic_year_bounds(start_year: int, start_month: int) -> tuple[date, date, str]:
    start_date = date(start_year, start_month, 1)
    end_year = start_year + 1
    end_month = start_month - 1 or 12
    end_month_year = end_year if start_month > 1 else start_year
    if end_month == 2:
        is_leap = end_month_year % 4 == 0 and (end_month_year % 100 != 0 or end_month_year % 400 == 0)
        end_day = 29 if is_leap else 28
    elif end_month in {4, 6, 9, 11}:
        end_day = 30
    else:
        end_day = 31
    end_date = date(end_month_year, end_month, end_day)
    return start_date, end_date, f"{start_year}/{start_year + 1}"


def get_or_create_academic_year(
    session: Session,
    *,
    as_of: date | datetime | None = None,
) -> AcademicYear:
    target = normalize_date(as_of)
    existing = session.execute(
        select(AcademicYear)
        .where(AcademicYear.start_date <= target, AcademicYear.end_date >= target)
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        _sync_current_flag(session, current_id=int(existing.id), target=target)
        return existing

    start_date, end_date, label = academic_year_bounds_for_date(target)
    academic_year = AcademicYear(
        label=label,
        start_date=start_date,
        end_date=end_date,
        is_current=True,
        is_closed=False,
    )
    session.add(academic_year)
    session.flush()
    _sync_current_flag(session, current_id=int(academic_year.id), target=target)
    return academic_year


def resolve_academic_year(
    session: Session,
    *,
    academic_year_id: int | None = None,
    as_of: date | datetime | None = None,
) -> AcademicYear:
    if academic_year_id is not None:
        academic_year = session.get(AcademicYear, academic_year_id)
        if academic_year is None:
            raise ValueError("Academic year not found.")
        return academic_year
    return get_or_create_academic_year(session, as_of=as_of)


def list_academic_years(session: Session) -> list[AcademicYear]:
    return session.execute(
        select(AcademicYear).order_by(AcademicYear.start_date.desc(), AcademicYear.id.desc())
    ).scalars().all()


def _sync_current_flag(session: Session, *, current_id: int, target: date) -> None:
    session.execute(
        sa.update(AcademicYear)
        .values(is_current=False)
        .where(AcademicYear.id != current_id, AcademicYear.is_current.is_(True))
    )
    current = session.get(AcademicYear, current_id)
    if current is not None:
        current.is_current = current.start_date <= target <= current.end_date
