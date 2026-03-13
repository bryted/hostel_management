import Link from "next/link";

import { BillingActions } from "../../components/billing-actions";
import { DataPanel, PageIntro, SummaryStrip, StatusPill } from "../../components/page-shell";
import { ReceiptActions } from "../../components/receipt-actions";
import { TenantActions } from "../../components/tenant-actions";
import {
  fetchBillingOverview,
  fetchInvoiceDetail,
  fetchReceiptDetail,
  requireUser,
} from "../../lib/server-api";

type PageProps = {
  searchParams: Promise<{
    search?: string;
    invoiceId?: string;
    receiptId?: string;
    queue?: string;
    ledger?: string;
    page?: string;
    invoice_status?: string;
  }>;
};

type QueueFilter = "all" | "collect" | "review" | "expired" | "partial";
type LedgerFilter = "invoices" | "payments" | "receipts";
type InvoiceStatusFilter = "open" | "partial" | "paid" | "all";

const INVOICE_PAGE_SIZE = 40;
const PAYMENT_PAGE_SIZE = 20;
const RECEIPT_PAGE_SIZE = 20;

function toneForInvoiceStatus(status: string): "success" | "warning" | "accent" | "default" {
  if (status === "paid") {
    return "success";
  }
  if (status === "approved" || status === "partially_paid") {
    return "warning";
  }
  if (status === "submitted") {
    return "accent";
  }
  return "default";
}

function holdText(invoice: {
  hold_expired: boolean;
  hold_hours_left: number | null;
  hold_expires_at: string | null;
}): string {
  if (invoice.hold_expired) {
    return "Hold expired";
  }
  if (invoice.hold_hours_left !== null && invoice.hold_expires_at) {
    return `${invoice.hold_hours_left}h left, expires ${invoice.hold_expires_at}`;
  }
  if (invoice.hold_hours_left !== null) {
    return `${invoice.hold_hours_left}h left`;
  }
  if (invoice.hold_expires_at) {
    return `Expires ${invoice.hold_expires_at}`;
  }
  return "No active hold";
}

function isQueueFilter(value: string | undefined): value is QueueFilter {
  return value === "all" || value === "collect" || value === "review" || value === "expired" || value === "partial";
}

function isLedgerFilter(value: string | undefined): value is LedgerFilter {
  return value === "invoices" || value === "payments" || value === "receipts";
}

function isInvoiceStatusFilter(value: string | undefined): value is InvoiceStatusFilter {
  return value === "open" || value === "partial" || value === "paid" || value === "all";
}

function queuePrimaryAction(
  invoice: {
    id: number;
    tenant_id: number;
    status: string;
    hold_expired: boolean;
  },
  buildBillingHref: (overrides: {
    search?: string;
    invoiceId?: string | null;
    receiptId?: string | null;
    queue?: QueueFilter;
    ledger?: LedgerFilter;
    page?: string | null;
    invoiceStatus?: InvoiceStatusFilter;
  }) => string,
): { href: string; label: string; className: string } {
  if (invoice.hold_expired) {
    return {
      href: `/invoices/${invoice.id}`,
      label: "Reassign bed",
      className: "button small warning",
    };
  }
  if (invoice.status === "partially_paid") {
    return {
      href: buildBillingHref({ invoiceId: String(invoice.id), receiptId: null, ledger: "invoices" }),
      label: "Collect balance",
      className: "button success small",
    };
  }
  if (invoice.status === "approved") {
    return {
      href: buildBillingHref({ invoiceId: String(invoice.id), receiptId: null, ledger: "invoices" }),
      label: "Collect",
      className: "button success small",
    };
  }
  if (invoice.status === "draft" || invoice.status === "submitted") {
    return {
      href: `/invoices/${invoice.id}`,
      label: "Review",
      className: "button small",
    };
  }
  return {
    href: `/invoices/${invoice.id}`,
    label: "Open invoice",
    className: "button small",
  };
}

function totalPages(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize));
}

export default async function BillingPage({ searchParams }: PageProps) {
  const user = await requireUser();
  const params = await searchParams;
  const search = params.search ?? "";
  const invoiceId = params.invoiceId ? Number(params.invoiceId) : Number.NaN;
  const receiptId = params.receiptId ? Number(params.receiptId) : Number.NaN;
  const queueFilter: QueueFilter = isQueueFilter(params.queue) ? params.queue : "all";
  const ledgerFilter: LedgerFilter = isLedgerFilter(params.ledger) ? params.ledger : "invoices";
  const invoiceStatusFilter: InvoiceStatusFilter = isInvoiceStatusFilter(params.invoice_status)
    ? params.invoice_status
    : "open";
  const page = Math.max(1, Number(params.page || "1") || 1);
  const billing = await fetchBillingOverview(search, page, invoiceStatusFilter);
  const [invoiceDetail, receiptDetail] = await Promise.all([
    Number.isNaN(invoiceId) ? Promise.resolve(null) : fetchInvoiceDetail(invoiceId),
    Number.isNaN(receiptId) ? Promise.resolve(null) : fetchReceiptDetail(receiptId),
  ]);

  const actionInvoices = [...billing.action_invoice_rows]
    .filter((invoice) => !["paid", "cancelled", "rejected"].includes(invoice.status))
    .sort((left, right) => {
      const rank = (invoice: { hold_expired: boolean; status: string }) => {
        if (invoice.hold_expired) return 0;
        if (invoice.status === "partially_paid") return 1;
        if (invoice.status === "approved") return 2;
        if (invoice.status === "submitted") return 3;
        if (invoice.status === "draft") return 4;
        return 5;
      };
      return rank(left) - rank(right);
    });
  const readyToCollect = actionInvoices.filter(
    (invoice) =>
      (invoice.status === "approved" || invoice.status === "partially_paid") && !invoice.hold_expired,
  );
  const needsReview = actionInvoices.filter(
    (invoice) => invoice.status === "draft" || invoice.status === "submitted",
  );
  const partiallyPaid = actionInvoices.filter((invoice) => invoice.status === "partially_paid");
  const expiredQueue = actionInvoices.filter((invoice) => invoice.hold_expired);
  const actionQueue =
    queueFilter === "collect"
      ? readyToCollect
      : queueFilter === "review"
        ? needsReview
        : queueFilter === "partial"
          ? partiallyPaid
          : queueFilter === "expired"
            ? expiredQueue
            : actionInvoices;

  function buildBillingHref(overrides: {
    search?: string;
    invoiceId?: string | null;
    receiptId?: string | null;
    queue?: QueueFilter;
    ledger?: LedgerFilter;
    page?: string | null;
    invoiceStatus?: InvoiceStatusFilter;
  }): string {
    const query = new URLSearchParams();
    const nextSearch = overrides.search ?? search;
    const nextQueue = overrides.queue ?? queueFilter;
    const nextLedger = overrides.ledger ?? ledgerFilter;
    const nextInvoiceStatus = overrides.invoiceStatus ?? invoiceStatusFilter;
    const nextPage = overrides.page === undefined ? String(page) : overrides.page ?? "";
    const nextInvoiceId =
      overrides.invoiceId === undefined ? (Number.isNaN(invoiceId) ? "" : String(invoiceId)) : overrides.invoiceId ?? "";
    const nextReceiptId =
      overrides.receiptId === undefined ? (Number.isNaN(receiptId) ? "" : String(receiptId)) : overrides.receiptId ?? "";

    if (nextSearch) {
      query.set("search", nextSearch);
    }
    if (nextQueue !== "all") {
      query.set("queue", nextQueue);
    }
    if (nextLedger !== "invoices") {
      query.set("ledger", nextLedger);
    }
    if (nextInvoiceStatus !== "open") {
      query.set("invoice_status", nextInvoiceStatus);
    }
    if (nextPage && nextPage !== "1") {
      query.set("page", nextPage);
    }
    if (nextInvoiceId) {
      query.set("invoiceId", nextInvoiceId);
    }
    if (nextReceiptId) {
      query.set("receiptId", nextReceiptId);
    }

    const suffix = query.toString();
    return suffix ? `/billing?${suffix}` : "/billing";
  }

  const ledgerTotal =
    ledgerFilter === "invoices"
      ? billing.invoice_total
      : ledgerFilter === "payments"
        ? billing.payment_total
        : billing.receipt_total;
  const ledgerPageSize =
    ledgerFilter === "invoices"
      ? INVOICE_PAGE_SIZE
      : ledgerFilter === "payments"
        ? PAYMENT_PAGE_SIZE
        : RECEIPT_PAGE_SIZE;
  const ledgerPages = totalPages(ledgerTotal, ledgerPageSize);

  return (
    <div className="grid">
      <PageIntro
        title="Billing"
        description={`The billing desk is organized around active balances first. Bed holds stay active for ${billing.default_hold_hours}h after approval and release automatically if unpaid.`}
        actions={
          <form className="toolbar" method="get">
            <input name="search" defaultValue={search} placeholder="Search tenant, invoice, reference" />
            {queueFilter !== "all" ? <input type="hidden" name="queue" value={queueFilter} /> : null}
            {ledgerFilter !== "invoices" ? <input type="hidden" name="ledger" value={ledgerFilter} /> : null}
            {invoiceStatusFilter !== "open" ? <input type="hidden" name="invoice_status" value={invoiceStatusFilter} /> : null}
            <button className="button" type="submit">
              Search
            </button>
          </form>
        }
        aside={
          <>
            {search ? <StatusPill tone="accent">Filtered</StatusPill> : <StatusPill>Focus mode</StatusPill>}
            <StatusPill tone={billing.block_duplicate_payment_reference ? "warning" : "default"}>
              {billing.block_duplicate_payment_reference ? "Duplicate refs blocked" : "Duplicate refs warn only"}
            </StatusPill>
            <StatusPill tone={billing.auto_approve_invoices ? "success" : "warning"}>
              {billing.auto_approve_invoices ? "Auto approval on" : "Admin approval"}
            </StatusPill>
          </>
        }
      />
      <SummaryStrip
        items={[
          { label: "Outstanding balances", value: billing.outstanding_total, tone: "warning" },
          { label: "Ready to collect", value: readyToCollect.length, tone: "accent" },
          { label: "Partially paid", value: partiallyPaid.length, tone: "accent" },
          { label: "Hold expired", value: expiredQueue.length, tone: "warning" },
          { label: "Needs review", value: needsReview.length, tone: "default" },
        ]}
      />

      <div className="grid two workspace-grid">
        <DataPanel
          title="Action queue"
          description="Work this list first. It covers collection, partial balances, review, and expired-hold recovery."
          toolbar={
            <div className="inline-actions">
              <Link className={queueFilter === "all" ? "button small" : "button small ghost"} href={buildBillingHref({ queue: "all", page: null })}>
                All
              </Link>
              <Link className={queueFilter === "collect" ? "button success small" : "button small ghost"} href={buildBillingHref({ queue: "collect", page: null })}>
                Ready
              </Link>
              <Link className={queueFilter === "partial" ? "button success small" : "button small ghost"} href={buildBillingHref({ queue: "partial", page: null })}>
                Partials
              </Link>
              <Link className={queueFilter === "review" ? "button small" : "button small ghost"} href={buildBillingHref({ queue: "review", page: null })}>
                Review
              </Link>
              <Link className={queueFilter === "expired" ? "button warning small" : "button small ghost"} href={buildBillingHref({ queue: "expired", page: null })}>
                Expired holds
              </Link>
            </div>
          }
        >
          <div className="segmented-list">
            {actionQueue.length ? (
              actionQueue.slice(0, 10).map((invoice) => {
                const primaryAction = queuePrimaryAction(invoice, buildBillingHref);
                return (
                  <div key={invoice.id} className="segmented-row">
                    <div className="meta-row">
                      <strong>{invoice.invoice_no}</strong>
                      <div className="inline-actions">
                        <StatusPill tone={toneForInvoiceStatus(invoice.status)}>{invoice.status}</StatusPill>
                        {invoice.hold_expired ? <StatusPill tone="warning">Hold expired</StatusPill> : null}
                      </div>
                    </div>
                    <span>
                      {invoice.tenant_name} | Balance {invoice.balance} | Paid {invoice.paid_total} | Due {invoice.due_at ?? "-"} | {holdText(invoice)}
                    </span>
                    <div className="inline-actions">
                      <Link className={primaryAction.className} href={primaryAction.href}>
                        {primaryAction.label}
                      </Link>
                      <Link className="button small ghost" href={buildBillingHref({ invoiceId: String(invoice.id), receiptId: null, page: null })}>
                        Preview
                      </Link>
                      <Link className="button small ghost" href={`/tenants/${invoice.tenant_id}`}>
                        Tenant
                      </Link>
                    </div>
                  </div>
                );
              })
            ) : (
              <p className="section-note">No queue items match the current billing focus.</p>
            )}
          </div>
        </DataPanel>

        <BillingActions
          user={user}
          tenants={billing.tenants}
          availableBeds={billing.available_beds}
          payableInvoices={billing.payable_invoices}
          submittedInvoices={billing.submitted_invoices}
          defaultHoldHours={billing.default_hold_hours}
          blockDuplicatePaymentReference={billing.block_duplicate_payment_reference}
          autoApproveInvoices={billing.auto_approve_invoices}
        />
      </div>

      <DataPanel
        title="History"
        description="Keep the ledger focused on the current desk task. Paid invoices are hidden by default and remain available through filters, payments, and receipts."
        toolbar={
          <div className="inline-actions">
            <Link className={ledgerFilter === "invoices" ? "button small" : "button small ghost"} href={buildBillingHref({ ledger: "invoices", page: null })}>
              Invoices
            </Link>
            <Link className={ledgerFilter === "payments" ? "button small" : "button small ghost"} href={buildBillingHref({ ledger: "payments", page: null })}>
              Payments
            </Link>
            <Link className={ledgerFilter === "receipts" ? "button small" : "button small ghost"} href={buildBillingHref({ ledger: "receipts", page: null })}>
              Receipts
            </Link>
          </div>
        }
      >
        {ledgerFilter === "invoices" ? (
          <div className="stack tight">
            <div className="inline-actions">
              <Link className={invoiceStatusFilter === "open" ? "button small" : "button small ghost"} href={buildBillingHref({ invoiceStatus: "open", page: null })}>
                Open only
              </Link>
              <Link className={invoiceStatusFilter === "partial" ? "button success small" : "button small ghost"} href={buildBillingHref({ invoiceStatus: "partial", page: null })}>
                Partially paid
              </Link>
              <Link className={invoiceStatusFilter === "paid" ? "button small" : "button small ghost"} href={buildBillingHref({ invoiceStatus: "paid", page: null })}>
                Paid
              </Link>
              <Link className={invoiceStatusFilter === "all" ? "button small" : "button small ghost"} href={buildBillingHref({ invoiceStatus: "all", page: null })}>
                All
              </Link>
            </div>
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Invoice</th>
                    <th>Tenant</th>
                    <th>Status</th>
                    <th>Total</th>
                    <th>Paid</th>
                    <th>Balance</th>
                    <th>Hold</th>
                    <th>Due</th>
                    <th>Open</th>
                  </tr>
                </thead>
                <tbody>
                  {billing.invoice_rows.length ? (
                    billing.invoice_rows.map((invoice) => (
                      <tr key={invoice.id}>
                        <td>
                          <Link href={buildBillingHref({ invoiceId: String(invoice.id), receiptId: null })}>{invoice.invoice_no}</Link>
                        </td>
                        <td>{invoice.tenant_name}</td>
                        <td>
                          <div className="inline-actions">
                            <StatusPill tone={toneForInvoiceStatus(invoice.status)}>{invoice.status}</StatusPill>
                            {invoice.hold_expired ? <StatusPill tone="warning">Hold expired</StatusPill> : null}
                          </div>
                        </td>
                        <td>{invoice.total}</td>
                        <td>{invoice.paid_total}</td>
                        <td>{invoice.balance}</td>
                        <td>{holdText(invoice)}</td>
                        <td>{invoice.due_at ?? "-"}</td>
                        <td>
                          <Link className="button small" href={`/invoices/${invoice.id}`}>
                            View
                          </Link>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={9} className="small">
                        No invoices match the current billing filter.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {ledgerFilter === "payments" ? (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Payment</th>
                  <th>Tenant</th>
                  <th>Invoice</th>
                  <th>Amount</th>
                  <th>Method</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {billing.payment_rows.length ? (
                  billing.payment_rows.map((payment) => (
                    <tr key={payment.id}>
                      <td>{payment.payment_no}</td>
                      <td>{payment.tenant_name}</td>
                      <td>{payment.invoice_no ?? "-"}</td>
                      <td>{payment.amount}</td>
                      <td>{payment.method ?? "-"}</td>
                      <td>
                        <StatusPill tone={payment.status === "completed" ? "success" : "warning"}>
                          {payment.status}
                        </StatusPill>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} className="small">
                      No recent payments match the current filter.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        ) : null}

        {ledgerFilter === "receipts" ? (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Receipt</th>
                  <th>Tenant</th>
                  <th>Payment</th>
                  <th>Invoice</th>
                  <th>Amount</th>
                  <th>Printed</th>
                </tr>
              </thead>
              <tbody>
                {billing.receipt_rows.length ? (
                  billing.receipt_rows.map((receipt) => (
                    <tr key={receipt.id}>
                      <td>
                        <Link
                          href={buildBillingHref({
                            receiptId: String(receipt.id),
                            invoiceId: receipt.invoice_id ? String(receipt.invoice_id) : null,
                          })}
                        >
                          {receipt.receipt_no}
                        </Link>
                      </td>
                      <td>{receipt.tenant_name}</td>
                      <td>{receipt.payment_no ?? "-"}</td>
                      <td>{receipt.invoice_no ?? "-"}</td>
                      <td>{receipt.amount}</td>
                      <td>{receipt.printed_count}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} className="small">
                      No receipts have been issued for the current filter.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        ) : null}

        <div className="ledger-pagination">
          <span className="small">
            Page {Math.min(page, ledgerPages)} of {ledgerPages} | {ledgerTotal} record(s)
          </span>
          <div className="inline-actions">
            <Link
              className={page <= 1 ? "button small ghost disabled-link" : "button small ghost"}
              href={page <= 1 ? buildBillingHref({ page: "1" }) : buildBillingHref({ page: String(page - 1) })}
            >
              Previous
            </Link>
            <Link
              className={page >= ledgerPages ? "button small ghost disabled-link" : "button small ghost"}
              href={page >= ledgerPages ? buildBillingHref({ page: String(ledgerPages) }) : buildBillingHref({ page: String(page + 1) })}
            >
              Next
            </Link>
          </div>
        </div>
      </DataPanel>

      <div className="grid two workspace-grid">
        <DataPanel title="Selected record">
          {invoiceDetail ? (
            <div className="stack tight">
              <div className="meta-list">
                <div className="meta-row">
                  <span>Invoice</span>
                  <strong>{invoiceDetail.invoice.invoice_no}</strong>
                </div>
                <div className="meta-row">
                  <span>Tenant</span>
                  <strong>{invoiceDetail.tenant.name}</strong>
                </div>
                <div className="meta-row">
                  <span>Status</span>
                  <StatusPill tone={toneForInvoiceStatus(invoiceDetail.invoice.status)}>
                    {invoiceDetail.invoice.status}
                  </StatusPill>
                </div>
                <div className="meta-row">
                  <span>Balance</span>
                  <strong>{invoiceDetail.invoice.balance}</strong>
                </div>
                <div className="meta-row">
                  <span>Paid so far</span>
                  <strong>{invoiceDetail.invoice.paid_total}</strong>
                </div>
                <div className="meta-row">
                  <span>Bed hold</span>
                  <strong>{holdText(invoiceDetail.invoice)}</strong>
                </div>
                <div className="meta-row">
                  <span>Reserved bed</span>
                  <strong>{invoiceDetail.reserved_bed_label ?? "No reserved bed"}</strong>
                </div>
              </div>
              <div className="inline-actions">
                <Link className="button ghost small" href={`/invoices/${invoiceDetail.invoice.id}`}>
                  Full invoice
                </Link>
                <Link className="button small" href={`/tenants/${invoiceDetail.tenant.id}`}>
                  Open tenant workspace
                </Link>
              </div>
            </div>
          ) : receiptDetail ? (
            <div className="stack tight">
              <div className="meta-list">
                <div className="meta-row">
                  <span>Receipt</span>
                  <strong>{receiptDetail.receipt.receipt_no}</strong>
                </div>
                <div className="meta-row">
                  <span>Tenant</span>
                  <strong>{receiptDetail.tenant.name}</strong>
                </div>
                <div className="meta-row">
                  <span>Amount</span>
                  <strong>{receiptDetail.receipt.amount}</strong>
                </div>
                <div className="meta-row">
                  <span>Payment</span>
                  <strong>{receiptDetail.payment?.payment_no ?? "-"}</strong>
                </div>
                <div className="meta-row">
                  <span>Balance after</span>
                  <strong>{receiptDetail.balance_after ?? "-"}</strong>
                </div>
                <div className="meta-row">
                  <span>Security code</span>
                  <span className="security-code">{receiptDetail.verification_code}</span>
                </div>
              </div>
              <ReceiptActions
                receiptId={receiptDetail.receipt.id}
                canSendSms={receiptDetail.sms_available}
                smsRecipient={receiptDetail.sms_recipient}
                canSendEmail={receiptDetail.email_available}
                emailRecipient={receiptDetail.email_recipient}
                canSendWhatsApp={receiptDetail.whatsapp_available}
                whatsAppRecipient={receiptDetail.whatsapp_recipient}
                verificationUrl={receiptDetail.verification_url}
              />
              <div className="inline-actions">
                <Link className="button ghost small" href={`/receipts/${receiptDetail.receipt.id}`}>
                  Full receipt
                </Link>
              </div>
            </div>
          ) : (
            <p className="section-note">Select an invoice or receipt from the queue or history views to review it here.</p>
          )}
        </DataPanel>

        <TenantActions title="Walk-in tenant" defaultStatus="prospect" compact />
      </div>
    </div>
  );
}
