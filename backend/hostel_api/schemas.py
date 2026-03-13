from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    is_admin: bool
    tenant_id: int | None


class DashboardSummaryResponse(BaseModel):
    start_date: str
    end_date: str
    available_beds: int
    occupied_beds: int
    reserved_beds: int
    occupancy_rate: float
    outstanding: str
    collected_period: str
    collected_mtd: str
    receipts_issued: int
    open_invoices: int
    pending_approvals: int
    partially_paid_invoices: int
    hold_expired_invoices: int
    prospects: int
    approved_unpaid: int
    paid_unallocated: int


class TenantListItem(BaseModel):
    id: int
    name: str
    email: str | None
    phone: str | None
    status: str
    room: str | None = None


class InvoiceSummary(BaseModel):
    id: int
    invoice_no: str
    status: str
    total: str
    paid_total: str
    balance: str
    issued_at: str | None
    due_at: str | None
    can_allocate: bool


class PaymentSummary(BaseModel):
    id: int
    payment_no: str
    amount: str
    method: str | None
    reference: str | None
    status: str
    paid_at: str | None


class ReceiptSummary(BaseModel):
    id: int
    receipt_no: str
    amount: str
    issued_at: str | None
    printed_count: int


class BedOption(BaseModel):
    bed_id: int
    block: str
    floor: str
    room: str
    bed: str
    status: str
    label: str


class ReservationSummary(BaseModel):
    id: int
    bed_id: int
    invoice_id: int | None
    invoice_no: str | None
    block: str
    floor: str
    room: str
    bed: str
    expires_at: str | None
    extension_count: int


class AllocationSummary(BaseModel):
    id: int
    bed_id: int
    invoice_id: int | None
    invoice_no: str | None
    block: str
    floor: str
    room: str
    bed: str
    start_date: str | None


class TimelineRow(BaseModel):
    When: str
    Source: str
    Event: str
    Detail: str


class TenantWorkspaceResponse(BaseModel):
    tenant: TenantListItem
    invoices: list[InvoiceSummary]
    payments: list[PaymentSummary]
    receipts: list[ReceiptSummary]
    active_reservation: ReservationSummary | None
    active_allocation: AllocationSummary | None
    timeline: list[TimelineRow]
    available_beds: list[BedOption]
    allocatable_invoices: list[InvoiceSummary]
    next_action: str
    model_config = ConfigDict(protected_namespaces=())


class BedListItem(BaseModel):
    bed_id: int
    block: str
    floor: str
    room: str
    bed: str
    status: str
    tenant: str | None
    tenant_id: int | None
    invoice: str | None
    invoice_id: int | None
    reservation_id: int | None
    allocation_id: int | None
    price_per_bed: str
    reservation_expires: str | None
    allocation_start: str | None


class BillingInvoiceItem(BaseModel):
    id: int
    invoice_no: str
    tenant_id: int
    tenant_name: str
    status: str
    total: str
    paid_total: str
    balance: str
    issued_at: str | None
    due_at: str | None
    hold_expired: bool = False
    hold_expires_at: str | None = None
    hold_hours_left: int | None = None


class BillingPaymentItem(BaseModel):
    id: int
    payment_no: str
    tenant_id: int
    tenant_name: str
    invoice_id: int | None
    invoice_no: str | None
    amount: str
    method: str | None
    reference: str | None
    status: str
    paid_at: str | None
    can_void: bool = False


class BillingReceiptItem(BaseModel):
    id: int
    receipt_no: str
    tenant_id: int
    tenant_name: str
    payment_id: int | None
    payment_no: str | None
    invoice_id: int | None
    invoice_no: str | None
    amount: str
    issued_at: str | None
    printed_count: int


class BillingOverviewResponse(BaseModel):
    outstanding_total: str
    collected_mtd: str
    action_invoice_rows: list[BillingInvoiceItem]
    invoice_rows: list[BillingInvoiceItem]
    invoice_total: int
    payment_rows: list[BillingPaymentItem]
    payment_total: int
    receipt_rows: list[BillingReceiptItem]
    receipt_total: int
    tenants: list[TenantListItem]
    available_beds: list[BedOption]
    payable_invoices: list[BillingInvoiceItem]
    submitted_invoices: list[BillingInvoiceItem]
    default_hold_hours: int
    block_duplicate_payment_reference: bool
    auto_approve_invoices: bool


class OnboardingQueueItem(BaseModel):
    stage: str
    tenant_id: int
    tenant_name: str
    invoice_id: int
    invoice_no: str
    invoice_status: str
    total: str
    paid: str
    balance: str
    reserved_bed_id: int | None
    reserved_bed_label: str | None = None
    hold_expired: bool = False


class OnboardingOverviewResponse(BaseModel):
    prospects: int
    approved_unpaid: int
    paid_unallocated: int
    active_allocated: int
    newly_activated_last_7d: int
    queue_rows: list[OnboardingQueueItem]
    available_beds: list[BedOption]


class CreateInvoiceRequest(BaseModel):
    tenant_id: int
    reserved_bed_id: int
    tax: Decimal = Decimal("0")
    discount: Decimal = Decimal("0")
    notes: str = ""
    due_at: date | None = None
    hold_hours: int = Field(default=24, ge=1, le=720)
    submit_now: bool = True


class CreateTenantRequest(BaseModel):
    name: str
    email: str = ""
    phone: str = ""
    status: str = "prospect"
    room: str = ""


class UpdateTenantRequest(BaseModel):
    name: str
    email: str = ""
    phone: str = ""
    status: str = "prospect"
    room: str = ""


class RecordPaymentRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    method: str
    reference: str = ""


class RejectInvoiceRequest(BaseModel):
    reason: str = ""


class UpdateInvoiceRequest(BaseModel):
    reserved_bed_id: int
    tax: Decimal = Decimal("0")
    discount: Decimal = Decimal("0")
    notes: str = ""
    due_at: date | None = None
    hold_hours: int = Field(default=24, ge=1, le=720)


class VoidPaymentRequest(BaseModel):
    reason: str = ""


class InvoiceDetailResponse(BaseModel):
    invoice: BillingInvoiceItem
    tenant: TenantListItem
    payments: list[PaymentSummary]
    receipts: list[ReceiptSummary]
    available_beds: list[BedOption]
    reserved_bed_label: str | None
    reserved_bed_id: int | None
    hold_expired: bool = False
    subtotal: str
    tax: str
    discount: str
    notes: str | None
    can_edit: bool = False
    can_cancel: bool = False


class ReceiptDetailResponse(BaseModel):
    receipt: BillingReceiptItem
    tenant: TenantListItem
    payment: PaymentSummary | None
    invoice: BillingInvoiceItem | None
    paid_before: str | None
    balance_after: str | None
    received_by: str | None
    verification_code: str
    verification_url: str
    sms_available: bool
    sms_recipient: str | None
    email_available: bool = False
    email_recipient: str | None = None
    whatsapp_available: bool = False
    whatsapp_recipient: str | None = None


class ReceiptVerificationResponse(BaseModel):
    valid: bool
    receipt_no: str | None = None
    amount: str | None = None
    issued_at: str | None = None
    tenant_name: str | None = None
    payment_no: str | None = None
    invoice_no: str | None = None


class BlockOption(BaseModel):
    id: int
    name: str
    is_active: bool = True


class FloorOption(BaseModel):
    id: int
    block_id: int
    block_name: str
    floor_label: str
    is_active: bool = True


class InventoryRoomItem(BaseModel):
    room_id: int
    block_id: int
    block_name: str
    floor_id: int | None
    floor_label: str | None
    room_code: str
    room_type: str | None
    beds_count: int
    available_beds: int
    reserved_beds: int
    occupied_beds: int
    out_of_service_beds: int
    unit_price_per_bed: str
    is_active: bool


class InventoryOverviewResponse(BaseModel):
    total_blocks: int
    total_floors: int
    total_rooms: int
    total_beds: int
    blocks: list[BlockOption]
    floors: list[FloorOption]
    rooms: list[InventoryRoomItem]
    integrity_rows: list[TableRow] = Field(default_factory=list)


class CreateBlockRequest(BaseModel):
    name: str


class CreateFloorRequest(BaseModel):
    block_id: int
    floor_label: str


class UpdateBlockRequest(BaseModel):
    name: str
    is_active: bool = True


class UpdateFloorRequest(BaseModel):
    floor_label: str
    is_active: bool = True


class RoomPayload(BaseModel):
    block_id: int
    floor_id: int
    room_code: str
    room_type: str
    unit_price_per_bed: Decimal
    is_active: bool = True


class AllocationRosterItem(BaseModel):
    allocation_id: int
    tenant_id: int
    tenant_name: str
    invoice_id: int | None
    invoice_no: str | None
    block: str
    floor: str
    room: str
    bed: str
    start_date: str | None
    transfer_targets: list[BedOption]


class AllocationOverviewResponse(BaseModel):
    active_allocations: int
    linked_invoices: int
    rows: list[AllocationRosterItem]


TableCellValue: TypeAlias = str | int | float | None
TableRow: TypeAlias = dict[str, TableCellValue]


class ReportsOverviewResponse(BaseModel):
    start_date: str
    end_date: str
    collected_today: str
    collected_mtd: str
    collected_ytd: str
    outstanding: str
    receipts_issued_today: int
    open_invoices: int
    pending_approvals: int
    block_occupancy_rows: list[TableRow]
    floor_occupancy_rows: list[TableRow]
    collections_by_method: list[TableRow]
    aging_rows: list[TableRow]
    room_utilization: list[TableRow]
    conversion_rows: list[TableRow]
    tenant_finance_rows: list[TableRow]


class NotificationSettingsPayload(BaseModel):
    block_duplicate_payment_reference: bool
    notification_max_attempts: int = Field(ge=1, le=20)
    notification_retry_delay_seconds: int = Field(ge=30, le=86400)
    reservation_default_hold_hours: int = Field(ge=1, le=720)
    auto_approve_invoices: bool = False


class NotificationProviderSettingsPayload(BaseModel):
    mock_mode: bool = False
    sms_api_url: str = ""
    sms_api_key: str = ""
    sms_sender_id: str = ""
    smtp_host: str = ""
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_api_version: str = ""


class ProviderTestRequest(BaseModel):
    channel: str
    recipient: str


class NotificationSettingsResponse(BaseModel):
    block_duplicate_payment_reference: bool
    notification_max_attempts: int
    notification_retry_delay_seconds: int
    reservation_default_hold_hours: int
    auto_approve_invoices: bool = False
    mock_mode: bool = False
    sms_configured: bool = False
    email_configured: bool = False
    whatsapp_configured: bool = False
    sms_api_url: str = ""
    sms_sender_id: str = ""
    sms_api_key_set: bool = False
    smtp_host: str = ""
    smtp_port: int | None = None
    smtp_user: str = ""
    smtp_from: str = ""
    smtp_password_set: bool = False
    whatsapp_phone_number_id: str = ""
    whatsapp_api_version: str = ""
    whatsapp_access_token_set: bool = False


class UserListItem(BaseModel):
    id: int
    email: str
    full_name: str
    is_admin: bool
    is_active: bool


class UpdateUserRequest(BaseModel):
    is_admin: bool | None = None
    is_active: bool | None = None


class AdminResetPasswordRequest(BaseModel):
    password: str


class PasswordResetRequestPayload(BaseModel):
    username: str


class PasswordResetConfirmPayload(BaseModel):
    token: str
    password: str


class PasswordResetRequestResponse(BaseModel):
    ok: bool = True
    message: str
    reset_token: str | None = None


class NotificationQueueStatus(BaseModel):
    status: str
    count: int


class AuditTrailItem(BaseModel):
    when: str
    source: str
    event: str
    detail: str


class WorkerStatus(BaseModel):
    reservation_expiry_job: str
    interval_minutes: int


class NotificationOutboxItem(BaseModel):
    id: int
    channel: str
    recipient: str
    subject: str | None
    status: str
    attempt_count: int
    scheduled_at: str | None
    sent_at: str | None
    error: str | None
    tenant_name: str | None


class SettingsOverviewResponse(BaseModel):
    settings: NotificationSettingsResponse
    users: list[UserListItem]
    queue_statuses: list[NotificationQueueStatus]
    audit_rows: list[AuditTrailItem]
    notification_rows: list[NotificationOutboxItem]
    worker_status: WorkerStatus
    cashier_scope: list[str]
    admin_scope: list[str]


class CreateUserRequest(BaseModel):
    email: str
    full_name: str
    password: str
    is_admin: bool = False


class ExtendReservationRequest(BaseModel):
    extra_hours: int = Field(ge=1, le=168)
    reason: str = ""


class CancelReservationRequest(BaseModel):
    reason: str = ""


class EndAllocationRequest(BaseModel):
    reason: str = ""


class TransferAllocationRequest(BaseModel):
    new_bed_id: int
    reason: str = ""


class SetMaintenanceRequest(BaseModel):
    out_of_service: bool
    reason: str = ""


class AssignBedRequest(BaseModel):
    bed_id: int


class ActionResponse(BaseModel):
    ok: bool = True
    message: str
    warning_message: str | None = None
    tenant_id: int | None = None
    invoice_id: int | None = None
    payment_id: int | None = None
    receipt_id: int | None = None
    reservation_id: int | None = None
    allocation_id: int | None = None
    bed_id: int | None = None
    user_id: int | None = None


class SearchResultItem(BaseModel):
    type: str
    id: int
    title: str
    subtitle: str | None
    href: str


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
