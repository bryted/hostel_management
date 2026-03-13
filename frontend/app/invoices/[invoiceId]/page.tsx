import Link from "next/link";
import { notFound } from "next/navigation";

import { InvoiceDetailActions } from "../../../components/invoice-detail-actions";
import { DataPanel, PageIntro, StatusPill } from "../../../components/page-shell";
import { fetchInvoiceDetail, requireUser } from "../../../lib/server-api";

type PageProps = {
  params: Promise<{ invoiceId: string }>;
};

function toneForInvoiceStatus(status: string): "success" | "warning" | "accent" | "default" {
  if (status === "paid") return "success";
  if (status === "approved" || status === "partially_paid") return "warning";
  if (status === "submitted") return "accent";
  return "default";
}

function holdText(detail: {
  hold_expired: boolean;
  invoice: {
    hold_hours_left: number | null;
    hold_expires_at: string | null;
  };
}): string {
  if (detail.hold_expired) return "Hold expired";
  if (detail.invoice.hold_hours_left !== null && detail.invoice.hold_expires_at) {
    return `${detail.invoice.hold_hours_left}h left, expires ${detail.invoice.hold_expires_at}`;
  }
  if (detail.invoice.hold_hours_left !== null) return `${detail.invoice.hold_hours_left}h left`;
  if (detail.invoice.hold_expires_at) return `Expires ${detail.invoice.hold_expires_at}`;
  return "No active hold";
}

export default async function InvoiceDetailPage({ params }: PageProps) {
  const user = await requireUser();
  const { invoiceId } = await params;
  const parsedInvoiceId = Number(invoiceId);
  if (Number.isNaN(parsedInvoiceId)) notFound();

  const detail = await fetchInvoiceDetail(parsedInvoiceId);

  return (
    <div className="grid">
      <PageIntro
        title={detail.invoice.invoice_no}
        description={detail.tenant.name}
        actions={
          <>
            <Link className="button ghost" href={`/tenants/${detail.tenant.id}`}>
              Tenant workspace
            </Link>
            <Link className="button" href={`/billing?invoiceId=${detail.invoice.id}`}>
              Billing desk
            </Link>
          </>
        }
        aside={
          <>
            <StatusPill tone={toneForInvoiceStatus(detail.invoice.status)}>{detail.invoice.status}</StatusPill>
            {detail.hold_expired ? <StatusPill tone="warning">Hold expired</StatusPill> : null}
          </>
        }
      />

      <div className="grid two">
        {user.is_admin ? <InvoiceDetailActions detail={detail} /> : null}
        <DataPanel title="Invoice">
          <div className="meta-list">
            <div className="meta-row">
              <span>Total</span>
              <strong>{detail.invoice.total}</strong>
            </div>
            <div className="meta-row">
              <span>Paid</span>
              <strong>{detail.invoice.paid_total}</strong>
            </div>
            <div className="meta-row">
              <span>Balance</span>
              <strong>{detail.invoice.balance}</strong>
            </div>
            <div className="meta-row">
              <span>Reserved bed</span>
              <strong>{detail.reserved_bed_label ?? "-"}</strong>
            </div>
            <div className="meta-row">
              <span>Bed hold</span>
              <strong>{holdText(detail)}</strong>
            </div>
            <div className="meta-row">
              <span>Due</span>
              <strong>{detail.invoice.due_at ?? "-"}</strong>
            </div>
          </div>
          {detail.hold_expired ? (
            <p className="section-note">
              The original bed hold expired and the bed was released. Select a new bed before approving, recording payment, or assigning this invoice.
            </p>
          ) : null}
          {detail.notes ? <p className="section-note">{detail.notes}</p> : null}
        </DataPanel>

        <DataPanel title="Tenant">
          <div className="meta-list">
            <div className="meta-row">
              <span>Name</span>
              <strong>{detail.tenant.name}</strong>
            </div>
            <div className="meta-row">
              <span>Email</span>
              <strong>{detail.tenant.email ?? "-"}</strong>
            </div>
            <div className="meta-row">
              <span>Phone</span>
              <strong>{detail.tenant.phone ?? "-"}</strong>
            </div>
            <div className="meta-row">
              <span>Status</span>
              <strong>{detail.tenant.status}</strong>
            </div>
          </div>
        </DataPanel>
      </div>

      <div className="grid two">
        <DataPanel title="Payments">
          <table className="table">
            <thead>
              <tr>
                <th>Payment</th>
                <th>Amount</th>
                <th>Method</th>
                <th>Reference</th>
                <th>Paid on</th>
              </tr>
            </thead>
            <tbody>
              {detail.payments.length ? (
                detail.payments.map((payment) => (
                  <tr key={payment.id}>
                    <td>{payment.payment_no}</td>
                    <td>{payment.amount}</td>
                    <td>{payment.method ?? "-"}</td>
                    <td>{payment.reference ?? "-"}</td>
                    <td>{payment.paid_at ?? "-"}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="small" colSpan={5}>
                    No payments have been recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </DataPanel>
        <DataPanel title="Receipts">
          <table className="table">
            <thead>
              <tr>
                <th>Receipt</th>
                <th>Amount</th>
                <th>Issued</th>
                <th>Printed</th>
              </tr>
            </thead>
            <tbody>
              {detail.receipts.length ? (
                detail.receipts.map((receipt) => (
                  <tr key={receipt.id}>
                    <td>
                      <Link href={`/receipts/${receipt.id}`}>{receipt.receipt_no}</Link>
                    </td>
                    <td>{receipt.amount}</td>
                    <td>{receipt.issued_at ?? "-"}</td>
                    <td>{receipt.printed_count}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="small" colSpan={4}>
                    No receipts have been issued yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </DataPanel>
      </div>
    </div>
  );
}
