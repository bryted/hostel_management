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
};

function statusText(nextAction: string): string {
  if (nextAction === "active_stay") {
    return "Tenant is currently allocated. Use this screen for move-out or transfer.";
  }
  if (nextAction === "reservation_active") {
    return "Tenant has a live reservation. Extend or cancel it here.";
  }
  if (nextAction === "allocate_bed") {
    return "Tenant has a paid invoice ready for bed assignment.";
  }
  if (nextAction === "collect_payment") {
    return "Tenant still needs payment before allocation can continue.";
  }
  return "Review billing and resident history before the next step.";
}

export default async function TenantWorkspacePage({ params }: PageProps) {
  const user = await requireUser();
  const { tenantId } = await params;
  const parsedTenantId = Number(tenantId);
  if (Number.isNaN(parsedTenantId)) {
    notFound();
  }
  const workspace = await fetchTenantWorkspace(parsedTenantId);
  const invoiceCount = workspace.invoices.length;
  const paymentCount = workspace.payments.length;
  const receiptCount = workspace.receipts.length;
  const timelineCount = workspace.timeline.length;
  const nextActionTone: "success" | "warning" | "accent" =
    workspace.next_action === "active_stay"
      ? "success"
      : workspace.next_action === "reservation_active" || workspace.next_action === "collect_payment"
        ? "warning"
        : "accent";

  return (
    <div className="grid">
      <PageIntro
        title={workspace.tenant.name}
        description={`${workspace.tenant.status} | ${workspace.tenant.email ?? "No email"} | ${workspace.tenant.phone ?? "No phone"}`}
        aside={
          <>
            <StatusPill tone={nextActionTone}>{workspace.next_action.replace("_", " ")}</StatusPill>
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
        >
          <table className="table">
            <thead>
              <tr>
                <th>Invoice</th>
                <th>Status</th>
                <th>Total</th>
                <th>Paid</th>
                <th>Balance</th>
              </tr>
            </thead>
            <tbody>
              {workspace.invoices.map((invoice) => (
                <tr key={invoice.id}>
                  <td>
                    <Link href={`/invoices/${invoice.id}`}>{invoice.invoice_no}</Link>
                  </td>
                  <td>{invoice.status}</td>
                  <td>{invoice.total}</td>
                  <td>{invoice.paid_total}</td>
                  <td>{invoice.balance}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </DataPanel>
        <DataPanel
          title="Payments and receipts"
        >
          <div className="stack">
            <table className="table">
              <thead>
                <tr>
                  <th>Payment</th>
                  <th>Amount</th>
                  <th>Method</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {workspace.payments.map((payment) => (
                  <tr key={payment.id}>
                    <td>{payment.payment_no}</td>
                    <td>{payment.amount}</td>
                    <td>{payment.method ?? "-"}</td>
                    <td>{payment.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
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
                {workspace.receipts.map((receipt) => (
                  <tr key={receipt.id}>
                    <td>
                      <Link href={`/receipts/${receipt.id}`}>{receipt.receipt_no}</Link>
                    </td>
                    <td>{receipt.amount}</td>
                    <td>{receipt.issued_at ?? "-"}</td>
                    <td>{receipt.printed_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </DataPanel>
      </div>

      <DataPanel title="Timeline">
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
            {workspace.timeline.map((row, index) => (
              <tr key={`${row.When}-${row.Event}-${index}`}>
                <td>{row.When}</td>
                <td>{row.Source}</td>
                <td>{row.Event}</td>
                <td>{row.Detail || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataPanel>
    </div>
  );
}
