import Link from "next/link";

import { InteractiveTable } from "../../components/interactive-table";
import { FilterChipBar, DataPanel, PageIntro, StatusPill, SummaryStrip } from "../../components/page-shell";
import { fetchReportsOverview, requireUser } from "../../lib/server-api";

type PageProps = {
  searchParams: Promise<{
    start_date?: string;
    end_date?: string;
    section?: string;
  }>;
};

type ReportSection = "finance" | "occupancy" | "conversion";

function isReportSection(value: string | undefined): value is ReportSection {
  return value === "finance" || value === "occupancy" || value === "conversion";
}

export default async function ReportsPage({ searchParams }: PageProps) {
  const user = await requireUser();

  if (!user.is_admin) {
    return (
      <div className="grid">
        <PageIntro
          title="Reporting is restricted to admins"
          actions={
            <>
              <Link className="button" href="/dashboard">
                Open dashboard
              </Link>
              <Link className="button ghost" href="/billing">
                Return to billing
              </Link>
            </>
          }
          aside={
            <div className="meta-list">
              <div className="meta-row">
                <span>Role</span>
                <StatusPill tone="warning">Cashier</StatusPill>
              </div>
              <div className="meta-row">
                <span>Scope</span>
                <strong>No financial reporting access</strong>
              </div>
            </div>
          }
        />
      </div>
    );
  }

  const params = await searchParams;
  const today = new Date().toISOString().slice(0, 10);
  const startDate = params.start_date ?? today;
  const rawEndDate = params.end_date ?? today;
  const endDate = rawEndDate < startDate ? startDate : rawEndDate;
  const section: ReportSection = isReportSection(params.section) ? params.section : "finance";
  const reports = await fetchReportsOverview(startDate, endDate);

  function buildReportsHref(nextSection: ReportSection): string {
    const query = new URLSearchParams({
      start_date: reports.start_date,
      end_date: reports.end_date,
    });
    if (nextSection !== "finance") {
      query.set("section", nextSection);
    }
    return `/reports?${query.toString()}`;
  }

  const exportQuery = `start_date=${reports.start_date}&end_date=${reports.end_date}`;

  const exportLinks =
    section === "finance"
      ? [
          { href: `/api/proxy/reports/finance-export.csv?${exportQuery}`, label: "Tenant finance CSV" },
          { href: `/api/proxy/reports/collections-export.csv?${exportQuery}`, label: "Collections CSV" },
          { href: `/api/proxy/reports/receivables-export.csv?${exportQuery}`, label: "Receivables CSV" },
        ]
      : section === "occupancy"
        ? [
            { href: `/api/proxy/reports/block-occupancy-export.csv?${exportQuery}`, label: "Block occupancy CSV" },
            { href: `/api/proxy/reports/floor-occupancy-export.csv?${exportQuery}`, label: "Floor occupancy CSV" },
            { href: `/api/proxy/reports/room-utilization-export.csv?${exportQuery}`, label: "Room utilization CSV" },
          ]
        : [
            { href: `/api/proxy/reports/conversion-export.csv?${exportQuery}`, label: "Conversion CSV" },
          ];
  const reportFilterItems = [
    { label: "Start", value: reports.start_date, tone: "accent" as const },
    { label: "End", value: reports.end_date, tone: "accent" as const },
    section !== "finance" ? { label: "Section", value: section, tone: "default" as const } : null,
  ].filter((item): item is NonNullable<typeof item> => Boolean(item));

  return (
    <div className="grid">
      <PageIntro
        title="Reports"
        aside={
          <>
            <StatusPill tone="accent">{reports.start_date} to {reports.end_date}</StatusPill>
            <StatusPill>{section}</StatusPill>
          </>
        }
      />
      <section className="panel filter-bar sticky">
        <div className="filter-bar-main">
          <form className="filter-form" method="get">
            <label className="filter-field">
              <span>Start date</span>
              <input type="date" name="start_date" defaultValue={reports.start_date} />
            </label>
            <label className="filter-field">
              <span>End date</span>
              <input type="date" name="end_date" defaultValue={reports.end_date} />
            </label>
            {section !== "finance" ? <input type="hidden" name="section" value={section} /> : null}
            <div className="filter-actions">
              <button className="button" type="submit">
                Apply range
              </button>
            </div>
          </form>
          <div className="filter-actions">
            {exportLinks.map((item) => (
              <a
                key={item.href}
                className="button ghost small"
                download
                href={item.href}
              >
                {item.label}
              </a>
            ))}
          </div>
        </div>
        <div className="filter-bar-meta">
          <div className="inline-actions">
            <Link className={section === "finance" ? "button small" : "button small ghost"} href={buildReportsHref("finance")}>
              Finance
            </Link>
            <Link className={section === "occupancy" ? "button small" : "button small ghost"} href={buildReportsHref("occupancy")}>
              Occupancy
            </Link>
            <Link className={section === "conversion" ? "button small" : "button small ghost"} href={buildReportsHref("conversion")}>
              Conversion
            </Link>
          </div>
          <p className="filter-copy">
            Keep the date range on the left and use the section tabs to switch report families without losing context.
          </p>
        </div>
        <FilterChipBar items={reportFilterItems} clearHref="/reports" />
      </section>
      <SummaryStrip
        items={[
          { label: "Collected MTD", value: reports.collected_mtd, tone: "success" },
          { label: "Collected YTD", value: reports.collected_ytd, tone: "default" },
          { label: "Outstanding", value: reports.outstanding, tone: "warning" },
          { label: "Open invoices", value: reports.open_invoices, tone: "accent" },
          { label: "Pending approvals", value: reports.pending_approvals, tone: "warning" },
        ]}
      />

      {section === "finance" ? (
        <>
          <DataPanel title="Collections by method">
            <InteractiveTable rows={reports.collections_by_method} emptyText="No collections landed in the selected period." searchPlaceholder="Filter methods" />
          </DataPanel>

          <DataPanel title="Receivables">
            <InteractiveTable rows={reports.aging_rows} emptyText="No outstanding approved invoices remain." searchPlaceholder="Filter receivables" />
          </DataPanel>

          <DataPanel title="Tenant finance ledger">
            <InteractiveTable rows={reports.tenant_finance_rows} emptyText="No payments were recorded in the selected period." searchPlaceholder="Filter tenant finance" />
          </DataPanel>
        </>
      ) : null}

      {section === "occupancy" ? (
        <div className="grid three">
          <DataPanel title="Occupancy by block">
            <InteractiveTable rows={reports.block_occupancy_rows} emptyText="No block data available." searchPlaceholder="Filter blocks" />
          </DataPanel>
          <DataPanel title="Occupancy by floor">
            <InteractiveTable rows={reports.floor_occupancy_rows} emptyText="No floor data available." searchPlaceholder="Filter floors" />
          </DataPanel>
          <DataPanel title="Room utilization">
            <InteractiveTable rows={reports.room_utilization} emptyText="No room data available." searchPlaceholder="Filter rooms" />
          </DataPanel>
        </div>
      ) : null}

      {section === "conversion" ? (
        <DataPanel title="Conversion">
          <InteractiveTable rows={reports.conversion_rows} emptyText="No conversion data available." searchPlaceholder="Filter metrics" />
        </DataPanel>
      ) : null}
    </div>
  );
}
