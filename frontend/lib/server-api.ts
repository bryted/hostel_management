import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import type {
  AllocationOverview,
  BedListResponse,
  BillingOverview,
  DashboardSummary,
  InventoryOverview,
  InvoiceDetail,
  OnboardingOverview,
  ReportsOverview,
  ReceiptDetail,
  SettingsOverview,
  TenantListResponse,
  TenantWorkspace,
  User,
} from "./api";
import { getServerApiBaseUrl } from "./api";

async function fetchServerJson<T>(path: string, init?: RequestInit): Promise<T> {
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("hostel_session");
  const response = await fetch(`${getServerApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      Cookie: sessionCookie
        ? `hostel_session=${decodeURIComponent(sessionCookie.value)}`
        : "",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

function normalizeBedsResponse(payload: unknown, requestedPage: number): BedListResponse {
  if (Array.isArray(payload)) {
    const rows = payload;
    const availableTotal = rows.filter((row) => row?.status === "AVAILABLE").length;
    const reservedTotal = rows.filter((row) => row?.status === "RESERVED").length;
    const occupiedTotal = rows.filter((row) => row?.status === "OCCUPIED").length;
    const outOfServiceTotal = rows.filter((row) => row?.status === "OUT_OF_SERVICE").length;
    return {
      rows: rows as BedListResponse["rows"],
      total: rows.length,
      page: requestedPage,
      page_size: rows.length || 100,
      available_total: availableTotal,
      reserved_total: reservedTotal,
      occupied_total: occupiedTotal,
      out_of_service_total: outOfServiceTotal,
    };
  }
  const objectPayload = payload as Partial<BedListResponse> | null;
  return {
    rows: objectPayload?.rows ?? [],
    total: objectPayload?.total ?? 0,
    page: objectPayload?.page ?? requestedPage,
    page_size: objectPayload?.page_size ?? Math.max((objectPayload?.rows ?? []).length, 1),
    available_total: objectPayload?.available_total ?? 0,
    reserved_total: objectPayload?.reserved_total ?? 0,
    occupied_total: objectPayload?.occupied_total ?? 0,
    out_of_service_total: objectPayload?.out_of_service_total ?? 0,
  };
}

export async function getCurrentUser(): Promise<User | null> {
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("hostel_session");
  if (!sessionCookie) {
    return null;
  }
  const response = await fetch(`${getServerApiBaseUrl()}/auth/me`, {
    headers: {
      Accept: "application/json",
      Cookie: `hostel_session=${decodeURIComponent(sessionCookie.value)}`,
    },
    cache: "no-store",
  });
  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as User;
}

export async function requireUser(): Promise<User> {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/login");
  }
  return user;
}

export async function fetchDashboardSummary(
  startDate = "",
  endDate = "",
): Promise<DashboardSummary> {
  const params = new URLSearchParams();
  if (startDate) {
    params.set("start_date", startDate);
  }
  if (endDate) {
    params.set("end_date", endDate);
  }
  return fetchServerJson<DashboardSummary>(`/dashboard/summary?${params.toString()}`);
}

export async function fetchBillingOverview(
  search = "",
  page = 1,
  invoiceStatus = "open",
): Promise<BillingOverview> {
  const params = new URLSearchParams();
  if (search) {
    params.set("search", search);
  }
  if (page > 1) {
    params.set("page", String(page));
  }
  if (invoiceStatus && invoiceStatus !== "open") {
    params.set("invoice_status", invoiceStatus);
  }
  return fetchServerJson<BillingOverview>(`/billing/overview?${params.toString()}`);
}

export async function fetchOnboardingOverview(
  search = "",
  stage = "",
): Promise<OnboardingOverview> {
  const params = new URLSearchParams();
  if (search) {
    params.set("search", search);
  }
  if (stage) {
    params.set("stage", stage);
  }
  return fetchServerJson<OnboardingOverview>(`/onboarding/queue?${params.toString()}`);
}

export async function fetchInvoiceDetail(invoiceId: number): Promise<InvoiceDetail> {
  return fetchServerJson<InvoiceDetail>(`/invoices/${invoiceId}`);
}

export async function fetchReceiptDetail(receiptId: number): Promise<ReceiptDetail> {
  return fetchServerJson<ReceiptDetail>(`/receipts/${receiptId}`);
}

export async function fetchInventoryOverview(): Promise<InventoryOverview> {
  return fetchServerJson<InventoryOverview>("/inventory/overview");
}

export async function fetchAllocationOverview(search = ""): Promise<AllocationOverview> {
  const params = new URLSearchParams();
  if (search) {
    params.set("search", search);
  }
  return fetchServerJson<AllocationOverview>(`/allocations/overview?${params.toString()}`);
}

export async function fetchReportsOverview(
  startDate = "",
  endDate = "",
  section = "finance",
  academicYearId = "",
  tenantQuery = "",
  agingPage = 1,
  financePage = 1,
  roomPage = 1,
): Promise<ReportsOverview> {
  const params = new URLSearchParams();
  if (startDate) {
    params.set("start_date", startDate);
  }
  if (endDate) {
    params.set("end_date", endDate);
  }
  if (section && section !== "finance") {
    params.set("section", section);
  }
  if (academicYearId) {
    params.set("academic_year_id", academicYearId);
  }
  if (tenantQuery) {
    params.set("tenant_query", tenantQuery);
  }
  if (agingPage > 1) {
    params.set("aging_page", String(agingPage));
  }
  if (financePage > 1) {
    params.set("finance_page", String(financePage));
  }
  if (roomPage > 1) {
    params.set("room_page", String(roomPage));
  }
  return fetchServerJson<ReportsOverview>(`/reports/overview?${params.toString()}`);
}

export async function fetchSettingsOverview(): Promise<SettingsOverview> {
  return fetchServerJson<SettingsOverview>("/settings/overview");
}

export async function fetchTenants(search = "", page = 1): Promise<TenantListResponse> {
  const params = new URLSearchParams();
  if (search) {
    params.set("search", search);
  }
  if (page > 1) {
    params.set("page", String(page));
  }
  return fetchServerJson<TenantListResponse>(`/tenants?${params.toString()}`);
}

export async function fetchBeds(search = "", status = "", page = 1): Promise<BedListResponse> {
  const params = new URLSearchParams();
  if (search) {
    params.set("search", search);
  }
  if (status) {
    params.set("status", status);
  }
  if (page > 1) {
    params.set("page", String(page));
  }
  const payload = await fetchServerJson<unknown>(`/beds?${params.toString()}`);
  return normalizeBedsResponse(payload, page);
}

export async function fetchTenantWorkspace(
  tenantId: number,
  invoicePage = 1,
  paymentPage = 1,
  receiptPage = 1,
  timelinePage = 1,
): Promise<TenantWorkspace> {
  const params = new URLSearchParams();
  if (invoicePage > 1) {
    params.set("invoice_page", String(invoicePage));
  }
  if (paymentPage > 1) {
    params.set("payment_page", String(paymentPage));
  }
  if (receiptPage > 1) {
    params.set("receipt_page", String(receiptPage));
  }
  if (timelinePage > 1) {
    params.set("timeline_page", String(timelinePage));
  }
  const suffix = params.toString();
  return fetchServerJson<TenantWorkspace>(
    `/tenants/${tenantId}/workspace${suffix ? `?${suffix}` : ""}`,
  );
}
