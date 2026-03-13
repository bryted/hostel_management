from __future__ import annotations

from fastapi import APIRouter

from .routes import (
    allocations,
    auth,
    beds,
    billing,
    dashboard,
    health,
    inventory,
    invoices,
    onboarding,
    receipts,
    reports,
    reservations,
    search,
    settings,
    tenants,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(health.router, tags=["health"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(beds.router, prefix="/beds", tags=["beds"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])
api_router.include_router(invoices.router, prefix="/invoices", tags=["invoices"])
api_router.include_router(receipts.router, prefix="/receipts", tags=["receipts"])
api_router.include_router(reservations.router, prefix="/reservations", tags=["reservations"])
api_router.include_router(allocations.router, prefix="/allocations", tags=["allocations"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
