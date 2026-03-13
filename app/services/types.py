from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(slots=True)
class OccupancySnapshot:
    total_beds: int = 0
    available_beds: int = 0
    reserved_beds: int = 0
    occupied_beds: int = 0
    out_of_service_beds: int = 0

    @property
    def operational_beds(self) -> int:
        return max(self.total_beds - self.out_of_service_beds, 0)

    @property
    def occupancy_rate(self) -> float:
        if self.operational_beds == 0:
            return 0.0
        return self.occupied_beds / self.operational_beds


@dataclass(slots=True)
class FinanceSnapshot:
    currency: str = "GHS"
    open_invoices: int = 0
    pending_approvals: int = 0
    receipts_issued_today: int = 0
    collected_today: Decimal = Decimal("0")
    collected_mtd: Decimal = Decimal("0")
    collected_ytd: Decimal = Decimal("0")
    outstanding: Decimal = Decimal("0")


@dataclass(slots=True)
class OnboardingPipelineSnapshot:
    prospects: int = 0
    prospects_with_approved_unpaid: int = 0
    paid_unallocated_tenants: int = 0
    active_allocated_tenants: int = 0
    newly_activated_last_7d: int = 0


@dataclass(slots=True)
class AlertSnapshot:
    expiring_reservations_count: int = 0
    approved_unpaid_count: int = 0
    paid_unallocated_count: int = 0
    expiring_reservations_rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class FloorOccupancyRow:
    block: str
    floor: str
    total: int
    occupied: int
    reserved: int
    available: int
    out_of_service: int
    occupancy_percent: str


@dataclass(slots=True)
class DashboardSnapshot:
    as_of: datetime
    currency: str
    occupancy: OccupancySnapshot
    finance: FinanceSnapshot
    onboarding: OnboardingPipelineSnapshot
    alerts: AlertSnapshot
    room_availability_rows: list[dict[str, Any]] = field(default_factory=list)
    bed_availability_rows: list[dict[str, Any]] = field(default_factory=list)
    block_occupancy_rows: list[dict[str, Any]] = field(default_factory=list)
    floor_occupancy_rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ConversionResult:
    activated: bool
    event_type: str | None = None
    details: dict[str, Any] | None = None


@dataclass(slots=True)
class InventoryRow:
    block: str
    floor: str
    room_code: str
    room_type: str
    beds_count: int
    unit_price_per_bed: Decimal
    is_active: bool = True


@dataclass(slots=True)
class RepriceResult:
    invoices_updated: int = 0


@dataclass(slots=True)
class RoomUpdateResult:
    room_id: int
    repriced_invoices: int = 0
    room_code_changed: bool = False
    room_type_changed: bool = False
    bed_count_changed: bool = False


@dataclass(slots=True)
class UploadResult:
    created_rooms: int = 0
    updated_rooms: int = 0


@dataclass(slots=True)
class AllocationResult:
    allocation_id: int
    invoice_id: int
    bed_id: int
    tenant_id: int
    bed_status: str
    created: bool
