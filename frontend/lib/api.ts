export type User = {
  id: number;
  email: string;
  full_name: string;
  is_admin: boolean;
  tenant_id: number | null;
};

export type DashboardSummary = {
  start_date: string;
  end_date: string;
  available_beds: number;
  occupied_beds: number;
  reserved_beds: number;
  occupancy_rate: number;
  outstanding: string;
  collected_period: string;
  collected_mtd: string;
  receipts_issued: number;
  open_invoices: number;
  pending_approvals: number;
  partially_paid_invoices: number;
  hold_expired_invoices: number;
  prospects: number;
  approved_unpaid: number;
  paid_unallocated: number;
};

export type BillingInvoiceItem = {
  id: number;
  invoice_no: string;
  tenant_id: number;
  tenant_name: string;
  status: string;
  total: string;
  paid_total: string;
  balance: string;
  issued_at: string | null;
  due_at: string | null;
  hold_expired: boolean;
  hold_expires_at: string | null;
  hold_hours_left: number | null;
};

export type BillingPaymentItem = {
  id: number;
  payment_no: string;
  tenant_id: number;
  tenant_name: string;
  invoice_id: number | null;
  invoice_no: string | null;
  amount: string;
  method: string | null;
  reference: string | null;
  status: string;
  paid_at: string | null;
  can_void: boolean;
};

export type BillingReceiptItem = {
  id: number;
  receipt_no: string;
  tenant_id: number;
  tenant_name: string;
  payment_id: number | null;
  payment_no: string | null;
  invoice_id: number | null;
  invoice_no: string | null;
  amount: string;
  issued_at: string | null;
  printed_count: number;
};

export type BillingOverview = {
  outstanding_total: string;
  collected_mtd: string;
  action_invoice_rows: BillingInvoiceItem[];
  invoice_rows: BillingInvoiceItem[];
  invoice_total: number;
  payment_rows: BillingPaymentItem[];
  payment_total: number;
  receipt_rows: BillingReceiptItem[];
  receipt_total: number;
  tenants: TenantListItem[];
  available_beds: BedOption[];
  payable_invoices: BillingInvoiceItem[];
  submitted_invoices: BillingInvoiceItem[];
  default_hold_hours: number;
  block_duplicate_payment_reference: boolean;
  auto_approve_invoices: boolean;
};

export type TenantListItem = {
  id: number;
  name: string;
  email: string | null;
  phone: string | null;
  status: string;
  room: string | null;
};

export type InvoiceSummary = {
  id: number;
  invoice_no: string;
  status: string;
  total: string;
  paid_total: string;
  balance: string;
  issued_at: string | null;
  due_at: string | null;
  can_allocate: boolean;
};

export type PaymentSummary = {
  id: number;
  payment_no: string;
  amount: string;
  method: string | null;
  reference: string | null;
  status: string;
  paid_at: string | null;
};

export type ReceiptSummary = {
  id: number;
  receipt_no: string;
  amount: string;
  issued_at: string | null;
  printed_count: number;
};

export type BedOption = {
  bed_id: number;
  block: string;
  floor: string;
  room: string;
  bed: string;
  status: string;
  label: string;
};

export type ReservationSummary = {
  id: number;
  bed_id: number;
  invoice_id: number | null;
  invoice_no: string | null;
  block: string;
  floor: string;
  room: string;
  bed: string;
  expires_at: string | null;
  extension_count: number;
};

export type AllocationSummary = {
  id: number;
  bed_id: number;
  invoice_id: number | null;
  invoice_no: string | null;
  block: string;
  floor: string;
  room: string;
  bed: string;
  start_date: string | null;
};

export type TimelineRow = {
  When: string;
  Source: string;
  Event: string;
  Detail: string;
};

export type TenantWorkspace = {
  tenant: TenantListItem;
  invoices: InvoiceSummary[];
  payments: PaymentSummary[];
  receipts: ReceiptSummary[];
  active_reservation: ReservationSummary | null;
  active_allocation: AllocationSummary | null;
  timeline: TimelineRow[];
  available_beds: BedOption[];
  allocatable_invoices: InvoiceSummary[];
  next_action: string;
};

export type BedListItem = {
  bed_id: number;
  block: string;
  floor: string;
  room: string;
  bed: string;
  status: string;
  tenant: string | null;
  tenant_id: number | null;
  invoice: string | null;
  invoice_id: number | null;
  reservation_id: number | null;
  allocation_id: number | null;
  price_per_bed: string;
  reservation_expires: string | null;
  allocation_start: string | null;
};

export type OnboardingQueueItem = {
  stage: string;
  tenant_id: number;
  tenant_name: string;
  invoice_id: number;
  invoice_no: string;
  invoice_status: string;
  total: string;
  paid: string;
  balance: string;
  reserved_bed_id: number | null;
  reserved_bed_label: string | null;
  hold_expired: boolean;
};

export type OnboardingOverview = {
  prospects: number;
  approved_unpaid: number;
  paid_unallocated: number;
  active_allocated: number;
  newly_activated_last_7d: number;
  queue_rows: OnboardingQueueItem[];
  available_beds: BedOption[];
};

export type InvoiceDetail = {
  invoice: BillingInvoiceItem;
  tenant: TenantListItem;
  payments: PaymentSummary[];
  receipts: ReceiptSummary[];
  available_beds: BedOption[];
  reserved_bed_label: string | null;
  reserved_bed_id: number | null;
  hold_expired: boolean;
  subtotal: string;
  tax: string;
  discount: string;
  notes: string | null;
  can_edit: boolean;
  can_cancel: boolean;
};

export type ReceiptDetail = {
  receipt: BillingReceiptItem;
  tenant: TenantListItem;
  payment: PaymentSummary | null;
  invoice: BillingInvoiceItem | null;
  paid_before: string | null;
  balance_after: string | null;
  received_by: string | null;
  verification_code: string;
  verification_url: string;
  sms_available: boolean;
  sms_recipient: string | null;
  email_available: boolean;
  email_recipient: string | null;
  whatsapp_available: boolean;
  whatsapp_recipient: string | null;
};

export type ReceiptVerification = {
  valid: boolean;
  receipt_no: string | null;
  amount: string | null;
  issued_at: string | null;
  tenant_name: string | null;
  payment_no: string | null;
  invoice_no: string | null;
};

export type BlockOption = {
  id: number;
  name: string;
  is_active: boolean;
};

export type FloorOption = {
  id: number;
  block_id: number;
  block_name: string;
  floor_label: string;
  is_active: boolean;
};

export type InventoryRoomItem = {
  room_id: number;
  block_id: number;
  block_name: string;
  floor_id: number | null;
  floor_label: string | null;
  room_code: string;
  room_type: string | null;
  beds_count: number;
  available_beds: number;
  reserved_beds: number;
  occupied_beds: number;
  out_of_service_beds: number;
  unit_price_per_bed: string;
  is_active: boolean;
};

export type InventoryOverview = {
  total_blocks: number;
  total_floors: number;
  total_rooms: number;
  total_beds: number;
  blocks: BlockOption[];
  floors: FloorOption[];
  rooms: InventoryRoomItem[];
  integrity_rows: TableRow[];
};

export type AllocationRosterItem = {
  allocation_id: number;
  tenant_id: number;
  tenant_name: string;
  invoice_id: number | null;
  invoice_no: string | null;
  block: string;
  floor: string;
  room: string;
  bed: string;
  start_date: string | null;
  transfer_targets: BedOption[];
};

export type AllocationOverview = {
  active_allocations: number;
  linked_invoices: number;
  rows: AllocationRosterItem[];
};

export type TableRowValue = string | number | null;
export type TableRow = Record<string, TableRowValue>;

export type ReportsOverview = {
  start_date: string;
  end_date: string;
  collected_today: string;
  collected_mtd: string;
  collected_ytd: string;
  outstanding: string;
  receipts_issued_today: number;
  open_invoices: number;
  pending_approvals: number;
  block_occupancy_rows: TableRow[];
  floor_occupancy_rows: TableRow[];
  collections_by_method: TableRow[];
  aging_rows: TableRow[];
  room_utilization: TableRow[];
  conversion_rows: TableRow[];
  tenant_finance_rows: TableRow[];
};

export type NotificationSettings = {
  block_duplicate_payment_reference: boolean;
  notification_max_attempts: number;
  notification_retry_delay_seconds: number;
  reservation_default_hold_hours: number;
  auto_approve_invoices: boolean;
  mock_mode: boolean;
  sms_configured: boolean;
  email_configured: boolean;
  whatsapp_configured: boolean;
  sms_api_url: string;
  sms_sender_id: string;
  sms_api_key_set: boolean;
  smtp_host: string;
  smtp_port: number | null;
  smtp_user: string;
  smtp_from: string;
  smtp_password_set: boolean;
  whatsapp_phone_number_id: string;
  whatsapp_api_version: string;
  whatsapp_access_token_set: boolean;
};

export type UserListItem = {
  id: number;
  email: string;
  full_name: string;
  is_admin: boolean;
  is_active: boolean;
};

export type NotificationQueueStatus = {
  status: string;
  count: number;
};

export type AuditTrailItem = {
  when: string;
  source: string;
  event: string;
  detail: string;
};

export type WorkerStatus = {
  reservation_expiry_job: string;
  interval_minutes: number;
};

export type NotificationOutboxItem = {
  id: number;
  channel: string;
  recipient: string;
  subject: string | null;
  status: string;
  attempt_count: number;
  scheduled_at: string | null;
  sent_at: string | null;
  error: string | null;
  tenant_name: string | null;
};

export type SettingsOverview = {
  settings: NotificationSettings;
  users: UserListItem[];
  queue_statuses: NotificationQueueStatus[];
  audit_rows: AuditTrailItem[];
  notification_rows: NotificationOutboxItem[];
  worker_status: WorkerStatus;
  cashier_scope: string[];
  admin_scope: string[];
};

export type ActionResponse = {
  ok: boolean;
  message: string;
  warning_message?: string | null;
  tenant_id?: number | null;
  invoice_id?: number | null;
  payment_id?: number | null;
  receipt_id?: number | null;
  reservation_id?: number | null;
  allocation_id?: number | null;
  bed_id?: number | null;
  user_id?: number | null;
};

export type SearchResultItem = {
  type: string;
  id: number;
  title: string;
  subtitle: string | null;
  href: string;
};

export type SearchResponse = {
  results: SearchResultItem[];
};

export type PasswordResetRequestResponse = {
  ok: boolean;
  message: string;
  reset_token: string | null;
};

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000/api/v1";

export function getServerApiBaseUrl(): string {
  return process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL;
}

export function getPublicApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL;
}
