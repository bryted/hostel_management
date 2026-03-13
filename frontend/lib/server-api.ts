import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import type {
  AllocationOverview,
  BedListItem,
  BillingOverview,
  DashboardSummary,
  InventoryOverview,
  InvoiceDetail,
  OnboardingOverview,
  ReportsOverview,
  ReceiptDetail,
  SettingsOverview,
  TenantListItem,
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
): Promise<ReportsOverview> {
  const params = new URLSearchParams();
  if (startDate) {
    params.set("start_date", startDate);
  }
  if (endDate) {
    params.set("end_date", endDate);
  }
  return fetchServerJson<ReportsOverview>(`/reports/overview?${params.toString()}`);
}

export async function fetchSettingsOverview(): Promise<SettingsOverview> {
  return fetchServerJson<SettingsOverview>("/settings/overview");
}

export async function fetchTenants(search = ""): Promise<TenantListItem[]> {
  const params = new URLSearchParams();
  if (search) {
    params.set("search", search);
  }
  return fetchServerJson<TenantListItem[]>(`/tenants?${params.toString()}`);
}

export async function fetchBeds(search = "", status = ""): Promise<BedListItem[]> {
  const params = new URLSearchParams();
  if (search) {
    params.set("search", search);
  }
  if (status) {
    params.set("status", status);
  }
  return fetchServerJson<BedListItem[]>(`/beds?${params.toString()}`);
}

export async function fetchTenantWorkspace(tenantId: number): Promise<TenantWorkspace> {
  return fetchServerJson<TenantWorkspace>(`/tenants/${tenantId}/workspace`);
}
