import Link from "next/link";

import { DataPanel, PageIntro, SummaryStrip, StatusPill } from "../../components/page-shell";
import { fetchDashboardSummary, requireUser } from "../../lib/server-api";

type PageProps = {
  searchParams: Promise<{
    start_date?: string;
    end_date?: string;
  }>;
};

function formatRangeLabel(startDate: string, endDate: string): string {
  if (startDate === endDate) {
    return `Collected ${endDate}`;
  }
  return "Collected in range";
}

export default async function DashboardPage({ searchParams }: PageProps) {
  const user = await requireUser();
  const params = await searchParams;
  const summary = await fetchDashboardSummary(params.start_date ?? "", params.end_date ?? "");
  const queuePressure = summary.approved_unpaid + summary.paid_unallocated + summary.hold_expired_invoices;
  const adminCards = [
    {
      title: "Billing desk",
      body: "Work unpaid balances, partials, and expired holds.",
      href: "/billing",
      label: "Open billing",
    },
    {
      title: "Onboarding",
      body: "Move paid residents into beds.",
      href: "/onboarding",
      label: "Open queue",
    },
    {
      title: "Allocations",
      body: "Transfer or end active stays.",
      href: "/allocations",
      label: "Open allocations",
    },
    {
      title: "Inventory",
      body: "Manage blocks, floors, rooms, and pricing.",
      href: "/inventory",
      label: "Open inventory",
    },
  ];
  const cashierCards = [
    {
      title: "Collections",
      body: "Work open invoices and part-paid balances.",
      href: "/billing",
      label: "Open billing",
    },
    {
      title: "Residents",
      body: "Open tenant records and payment history.",
      href: "/tenants",
      label: "Open tenants",
    },
    {
      title: "Stay status",
      body: "Check reservation and allocation state.",
      href: "/beds",
      label: "Open beds",
    },
  ];

  return (
    <div className="grid">
      <PageIntro
        title="Dashboard"
        description={
          user.is_admin
            ? "Operations overview focused on collections, queue pressure, and occupancy."
            : "Cash position, collection pressure, and resident access."
        }
        aside={
          <>
            <StatusPill tone={queuePressure ? "warning" : "success"}>{queuePressure} items need action</StatusPill>
            <StatusPill tone="accent">
              {summary.start_date} to {summary.end_date}
            </StatusPill>
          </>
        }
      />
      <section className="panel filter-bar">
        <div className="filter-bar-main">
          <form className="filter-form" method="get">
            <label className="filter-field">
              <span>Start date</span>
              <input defaultValue={summary.start_date} name="start_date" type="date" />
            </label>
            <label className="filter-field">
              <span>End date</span>
              <input defaultValue={summary.end_date} name="end_date" type="date" />
            </label>
            <div className="filter-actions">
              <button className="button" type="submit">
                Apply range
              </button>
              <Link className="button ghost" href="/dashboard">
                Reset
              </Link>
            </div>
          </form>
          <p className="filter-copy">
            Change the collection window without leaving the operations summary. The cards and pipeline counts update together.
          </p>
        </div>
      </section>
      <SummaryStrip
        items={[
          { label: "Outstanding", value: summary.outstanding, tone: "warning" },
          { label: formatRangeLabel(summary.start_date, summary.end_date), value: summary.collected_period, tone: "success" },
          { label: "Open invoices", value: summary.open_invoices, tone: "default" },
          { label: "Partially paid", value: summary.partially_paid_invoices, tone: "accent" },
          { label: "Hold expired", value: summary.hold_expired_invoices, tone: "warning" },
          { label: "Occupancy", value: `${Math.round(summary.occupancy_rate * 100)}%`, tone: "accent" },
        ]}
      />
      <div className="grid two">
        <DataPanel title="Pipeline">
          <div className="detail-grid">
            <div className="detail-card">
              <h4>Prospects</h4>
              <strong>{summary.prospects}</strong>
            </div>
            <div className="detail-card">
              <h4>Approved unpaid</h4>
              <strong>{summary.approved_unpaid}</strong>
            </div>
            <div className="detail-card">
              <h4>Paid unallocated</h4>
              <strong>{summary.paid_unallocated}</strong>
            </div>
            <div className="detail-card">
              <h4>Pending approvals</h4>
              <strong>{summary.pending_approvals}</strong>
            </div>
            <div className="detail-card">
              <h4>Receipts in range</h4>
              <strong>{summary.receipts_issued}</strong>
            </div>
            <div className="detail-card">
              <h4>Reserved beds</h4>
              <strong>{summary.reserved_beds}</strong>
            </div>
          </div>
        </DataPanel>
        <DataPanel title="Quick actions">
          <div className="shortcut-grid">
            {(user.is_admin ? adminCards : cashierCards).map((card) => (
              <div key={card.href} className="shortcut-tile">
                <strong>{card.title}</strong>
                <span className="small">{card.body}</span>
                <Link className="button ghost" href={card.href}>
                  {card.label}
                </Link>
              </div>
            ))}
          </div>
        </DataPanel>
      </div>
    </div>
  );
}
