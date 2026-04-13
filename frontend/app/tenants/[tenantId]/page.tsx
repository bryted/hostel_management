import Link from "next/link";
import { notFound } from "next/navigation";

import { DataPanel, PageIntro, SummaryStrip, StatusPill } from "../../../components/page-shell";
import { TenantActions } from "../../../components/tenant-actions";
import { WorkspaceActions } from "../../../components/workspace-actions";
import { fetchTenantWorkspace, requireUser } from "../../../lib/server-api";

type PageProps = {
  params: Promise<{
    tenantId: string;
  }>;
  searchParams: Promise<{
    invoice_page?: string;
    payment_page?: string;
    receipt_page?: string;
    timeline_page?: string;
  }>;
};

function tenantStatusLabel(status: string): string {
  if (status === "active") return "Checked in";
  if (status === "inactive") return "Archived";
  return "Prospect";
}

function nextActionLabel(nextAction: string): string {
  if (nextAction === "active_stay") return "Checked in";
  if (nextAction === "reservation_active") return "Reservation in progress";
  if (nextAction === "allocate_bed") return "Assign room";
  if (nextAction === "collect_payment") return "Collect payment";
  return "Review account";
}

function statusText(nextAction: string): string {
  if (nextAction === "active_stay") {
    return "The resident is checked in. Use this screen for transfer or move-out.";
  }
  if (nextAction === "reservation_active") {
    return "There is an active room hold. Extend it, cancel it, or continue collection.";
  }
  if (nextAction === "allocate_bed") {
    return "Payment is in place. The next step is assigning a room.";
  }
  if (nextAction === "collect_payment") {
    return "Payment is still outstanding before check-in can continue.";
  }
  return "Review billing and resident history before the next step.";
}

function totalPages(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize));
}

export default async function TenantWorkspacePage({ params, searchParams }: PageProps) {
  const user = await requireUser();
  const { tenantId } = await params;
  const query = await searchParams;
  const parsedTenantId = Number(tenantId);
  if (Number.isNaN(parsedTenantId)) {
    notFound();
  }
  const invoicePage = Math.max(1, Number(query.invoice_page || "1") || 1);
  const paymentPage = Math.max(1, Number(query.payment_page || "1") || 1);
  const receiptPage = Math.max(1, Number(query.receipt_page || "1") || 1);
  const timelinePage = Math.max(1, Number(query.timeline_page || "1") || 1);
  const workspace = await fetchTenantWorkspace(
    parsedTenantId,
    invoicePage,
    paymentPage,
    receiptPage,
    timelinePage,
  );
  const invoiceCount = workspace.invoice_total;
  const paymentCount = workspace.payment_total;
  const receiptCount = workspace.receipt_total;
  const timelineCount = workspace.timeline_total;
  const invoicePages = totalPages(workspace.invoice_total, workspace.invoice_page_size);
  const paymentPages = totalPages(workspace.payment_total, workspace.payment_page_size);
  const receiptPages = totalPages(workspace.receipt_total, workspace.receipt_page_size);
  const timelinePages = totalPages(workspace.timeline_total, workspace.timeline_page_size);
  const nextActionTone: "success" | "warning" | "accent" =
    workspace.next_action === "active_stay"
      ? "success"
      : workspace.next_action === "reservation_active" || workspace.next_action === "collect_payment"
        ? "warning"
        : "accent";

  function buildWorkspaceHref(overrides: {
    invoicePage?: string | null;
    paymentPage?: string | null;
    receiptPage?: string | null;
    timelinePage?: string | null;
  }): string {
    const nextInvoicePage =
      overrides.invoicePage === undefined ? String(workspace.invoice_page) : overrides.invoicePage ?? "";
    const nextPaymentPage =
      overrides.paymentPage === undefined ? String(workspace.payment_page) : overrides.paymentPage ?? "";
    const nextReceiptPage =
      overrides.receiptPage === undefined ? String(workspace.receipt_page) : overrides.receiptPage ?? "";
    const nextTimelinePage =
      overrides.timelinePage === undefined ? String(workspace.timeline_page) : overrides.timelinePage ?? "";
    const params = new URLSearchParams();
    if (nextInvoicePage && nextInvoicePage !== "1") {
      params.set("invoice_page", nextInvoicePage);
    }
    if (nextPaymentPage && nextPaymentPage !== "1") {
      params.set("payment_page", nextPaymentPage);
    }
    if (nextReceiptPage && nextReceiptPage !== "1") {
      params.set("receipt_page", nextReceiptPage);
    }
    if (nextTimelinePage && nextTimelinePage !== "1") {
      params.set("timeline_page", nextTimelinePage);
    }
    const suffix = params.toString();
    return suffix ? `/tenants/${parsedTenantId}?${suffix}` : `/tenants/${parsedTenantId}`;
  }

  return (
    <div className="grid">
      <PageIntro
        title={workspace.tenant.name}
        description={`${tenantStatusLabel(workspace.tenant.status)} | ${workspace.tenant.email ?? "No email"} | ${workspace.tenant.phone ?? "No phone"}`}
        aside={
          <>
            <StatusPill tone={nextActionTone}>{nextActionLabel(workspace.next_action)}</StatusPill>
            <span className="small">{statusText(workspace.next_action)}</span>
          </>
        }
      />
      <SummaryStrip
        items={[
          { label: "Invoices", value: invoiceCount, tone: "default" },
          { label: "Payments", value: paymentCount, tone: "success" },
          { label: "Receipts", value: receiptCount, tone: "accent" },
          { label: "Timeline rows", value: timelineCount, tone: "default" },
        ]}
      />

      <div className="grid two workspace-grid">
        <WorkspaceActions
          user={user}
          reservation={workspace.active_reservation}
          allocation={workspace.active_allocation}
          availableBeds={workspace.available_beds}
          allocatableInvoices={workspace.allocatable_invoices}
        />
        <div className="stack">
          <TenantActions tenant={workspace.tenant} title="Tenant profile" />
          <DataPanel
            title="Current stay context"
            tone="supporting"
          >
            {workspace.active_allocation ? (
              <div className="stack">
                <div className="metric compact">
                  <span>Allocated bed</span>
                  <strong>
                    {workspace.active_allocation.block} / {workspace.active_allocation.floor} /{" "}
                    {workspace.active_allocation.room} / {workspace.active_allocation.bed}
                  </strong>
                </div>
                <p>Started {workspace.active_allocation.start_date ?? "-"}</p>
                <p>Academic year {workspace.active_allocation.academic_year ?? "-"}</p>
              </div>
            ) : workspace.active_reservation ? (
              <div className="stack">
                <div className="metric compact">
                  <span>Reserved bed</span>
                  <strong>
                    {workspace.active_reservation.block} / {workspace.active_reservation.floor} /{" "}
                    {workspace.active_reservation.room} / {workspace.active_reservation.bed}
                  </strong>
                </div>
                <p>Expires {workspace.active_reservation.expires_at ?? "-"}</p>
                <p>Academic year {workspace.active_reservation.academic_year ?? "-"}</p>
              </div>
            ) : (
              <p>No active reservation or confirmed stay.</p>
            )}
          </DataPanel>
        </div>
      </div>

      <div className="grid two">
        <DataPanel
          title="Invoices"
          description="Billing history for this resident. Use it to confirm what is still outstanding and what has already been settled."
          tone="secondary"
        >
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Status</th>
                  <th>Total</th>
                  <th>Paid</th>
                  <th>Balance</th>
                  <th>Year</th>
                </tr>
              </thead>
              <tbody>
                {workspace.invoices.length ? (
                  workspace.invoices.map((invoice) => (
                    <tr key={invoice.id}>
                      <td>
                        <Link href={`/invoices/${invoice.id}`}>{invoice.invoice_no}</Link>
                      </td>
                      <td>{invoice.status.replace("_", " ")}</td>
                      <td>{invoice.total}</td>
                      <td>{invoice.paid_total}</td>
                      <td>{invoice.balance}</td>
                      <td>{invoice.academic_year ?? "-"}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td className="small" colSpan={6}>
                      No invoice history is available for this resident yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="ledger-pagination">
            <span className="small">
              Page {Math.min(workspace.invoice_page, invoicePages)} of {invoicePages} | {workspace.invoice_total} invoice(s)
            </span>
            <div className="inline-actions">
              <Link
                className={workspace.invoice_page <= 1 ? "button small ghost disabled-link" : "button small ghost"}
                href={
                  workspace.invoice_page <= 1
                    ? buildWorkspaceHref({ invoicePage: "1" })
                    : buildWorkspaceHref({ invoicePage: String(workspace.invoice_page - 1) })
                }
              >
                Previous
              </Link>
              <Link
                className={workspace.invoice_page >= invoicePages ? "button small ghost disabled-link" : "button small ghost"}
                href={
                  workspace.invoice_page >= invoicePages
                    ? buildWorkspaceHref({ invoicePage: String(invoicePages) })
                    : buildWorkspaceHref({ invoicePage: String(workspace.invoice_page + 1) })
                }
              >
                Next
              </Link>
            </div>
          </div>
        </DataPanel>
        <DataPanel
          title="Payments and receipts"
          description="Money received and receipt history for this resident, kept together for quick finance checks."
          tone="secondary"
        >
          <div className="stack">
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Payment</th>
                    <th>Amount</th>
                    <th>Invoices</th>
                    <th>Method</th>
                    <th>Status</th>
                    <th>Year</th>
                  </tr>
                </thead>
                <tbody>
                  {workspace.payments.length ? (
                    workspace.payments.map((payment) => (
                      <tr key={payment.id}>
                        <td>{payment.payment_no}</td>
                        <td>{payment.amount}</td>
                        <td>{payment.invoice_summary ?? "-"}</td>
                        <td>{payment.method ?? "-"}</td>
                        <td>{payment.status.replace("_", " ")}</td>
                        <td>{payment.academic_year ?? "-"}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="small" colSpan={6}>
                        No payments have been recorded for this resident yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="ledger-pagination">
              <span className="small">
                Page {Math.min(workspace.payment_page, paymentPages)} of {paymentPages} | {workspace.payment_total} payment(s)
              </span>
              <div className="inline-actions">
                <Link
                  className={workspace.payment_page <= 1 ? "button small ghost disabled-link" : "button small ghost"}
                  href={
                    workspace.payment_page <= 1
                      ? buildWorkspaceHref({ paymentPage: "1" })
                      : buildWorkspaceHref({ paymentPage: String(workspace.payment_page - 1) })
                  }
                >
                  Previous
                </Link>
                <Link
                  className={workspace.payment_page >= paymentPages ? "button small ghost disabled-link" : "button small ghost"}
                  href={
                    workspace.payment_page >= paymentPages
                      ? buildWorkspaceHref({ paymentPage: String(paymentPages) })
                      : buildWorkspaceHref({ paymentPage: String(workspace.payment_page + 1) })
                  }
                >
                  Next
                </Link>
              </div>
            </div>
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Receipt</th>
                    <th>Amount</th>
                    <th>Invoices</th>
                    <th>Issued</th>
                    <th>Printed</th>
                    <th>Year</th>
                  </tr>
                </thead>
                <tbody>
                  {workspace.receipts.length ? (
                    workspace.receipts.map((receipt) => (
                      <tr key={receipt.id}>
                        <td>
                          <Link href={`/receipts/${receipt.id}`}>{receipt.receipt_no}</Link>
                        </td>
                        <td>{receipt.amount}</td>
                        <td>{receipt.invoice_summary ?? "-"}</td>
                        <td>{receipt.issued_at ?? "-"}</td>
                        <td>{receipt.printed_count}</td>
                        <td>{receipt.academic_year ?? "-"}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="small" colSpan={6}>
                        No receipts have been issued for this resident yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="ledger-pagination">
              <span className="small">
                Page {Math.min(workspace.receipt_page, receiptPages)} of {receiptPages} | {workspace.receipt_total} receipt(s)
              </span>
              <div className="inline-actions">
                <Link
                  className={workspace.receipt_page <= 1 ? "button small ghost disabled-link" : "button small ghost"}
                  href={
                    workspace.receipt_page <= 1
                      ? buildWorkspaceHref({ receiptPage: "1" })
                      : buildWorkspaceHref({ receiptPage: String(workspace.receipt_page - 1) })
                  }
                >
                  Previous
                </Link>
                <Link
                  className={workspace.receipt_page >= receiptPages ? "button small ghost disabled-link" : "button small ghost"}
                  href={
                    workspace.receipt_page >= receiptPages
                      ? buildWorkspaceHref({ receiptPage: String(receiptPages) })
                      : buildWorkspaceHref({ receiptPage: String(workspace.receipt_page + 1) })
                  }
                >
                  Next
                </Link>
              </div>
            </div>
          </div>
        </DataPanel>
      </div>

      <DataPanel title="Timeline" description="Chronological activity across billing, room movement, and administrative actions." tone="supporting">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Source</th>
                <th>Event</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {workspace.timeline.length ? (
                workspace.timeline.map((row, index) => (
                  <tr key={`${row.When}-${row.Event}-${index}`}>
                    <td>{row.When}</td>
                    <td>{row.Source}</td>
                    <td>{row.Event}</td>
                    <td>{row.Detail || "-"}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="small" colSpan={4}>
                    No timeline activity has been recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="ledger-pagination">
          <span className="small">
            Page {Math.min(workspace.timeline_page, timelinePages)} of {timelinePages} | {workspace.timeline_total} timeline row(s)
          </span>
          <div className="inline-actions">
            <Link
              className={workspace.timeline_page <= 1 ? "button small ghost disabled-link" : "button small ghost"}
              href={
                workspace.timeline_page <= 1
                  ? buildWorkspaceHref({ timelinePage: "1" })
                  : buildWorkspaceHref({ timelinePage: String(workspace.timeline_page - 1) })
              }
            >
              Previous
            </Link>
            <Link
              className={workspace.timeline_page >= timelinePages ? "button small ghost disabled-link" : "button small ghost"}
              href={
                workspace.timeline_page >= timelinePages
                  ? buildWorkspaceHref({ timelinePage: String(timelinePages) })
                  : buildWorkspaceHref({ timelinePage: String(workspace.timeline_page + 1) })
              }
            >
              Next
            </Link>
          </div>
        </div>
      </DataPanel>
    </div>
  );
}
