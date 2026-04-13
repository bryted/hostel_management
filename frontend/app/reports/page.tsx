import Link from "next/link";

import { InteractiveTable } from "../../components/interactive-table";
import { FilterChipBar, DataPanel, PageIntro, StatusPill, SummaryStrip } from "../../components/page-shell";
import { fetchReportsOverview, requireUser } from "../../lib/server-api";

type PageProps = {
  searchParams: Promise<{
    start_date?: string;
    end_date?: string;
    section?: string;
    academic_year_id?: string;
    tenant_query?: string;
    aging_page?: string;
    finance_page?: string;
    room_page?: string;
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
  const academicYearId = params.academic_year_id ?? "";
  const tenantQuery = params.tenant_query ?? "";
  const agingPage = Math.max(1, Number(params.aging_page || "1") || 1);
  const financePage = Math.max(1, Number(params.finance_page || "1") || 1);
  const roomPage = Math.max(1, Number(params.room_page || "1") || 1);
  const reports = await fetchReportsOverview(
    startDate,
    endDate,
    section,
    academicYearId,
    tenantQuery,
    agingPage,
    financePage,
    roomPage,
  );

  function buildReportsHref(
      nextSection: ReportSection,
      overrides?: {
      academicYearId?: string | null;
      tenantQuery?: string | null;
      agingPage?: string | null;
      financePage?: string | null;
      roomPage?: string | null;
    },
  ): string {
    const query = new URLSearchParams({
      start_date: reports.start_date,
      end_date: reports.end_date,
    });
    if (nextSection !== "finance") {
      query.set("section", nextSection);
    }
    const nextAcademicYearId =
      overrides?.academicYearId === undefined ? String(reports.selected_academic_year_id ?? "") : overrides.academicYearId ?? "";
    const nextTenantQuery =
      overrides?.tenantQuery === undefined ? reports.tenant_query : overrides.tenantQuery ?? "";
    if (nextAcademicYearId) {
      query.set("academic_year_id", nextAcademicYearId);
    }
    if (nextTenantQuery) {
      query.set("tenant_query", nextTenantQuery);
    }
    const nextAgingPage = overrides?.agingPage === undefined ? String(reports.aging_page) : overrides.agingPage ?? "";
    const nextFinancePage =
      overrides?.financePage === undefined ? String(reports.finance_page) : overrides.financePage ?? "";
    const nextRoomPage = overrides?.roomPage === undefined ? String(reports.room_page) : overrides.roomPage ?? "";
    if (nextAgingPage && nextAgingPage !== "1") {
      query.set("aging_page", nextAgingPage);
    }
    if (nextFinancePage && nextFinancePage !== "1") {
      query.set("finance_page", nextFinancePage);
    }
    if (nextRoomPage && nextRoomPage !== "1") {
      query.set("room_page", nextRoomPage);
    }
    return `/reports?${query.toString()}`;
  }

  const agingPages = Math.max(1, Math.ceil(reports.aging_total / reports.aging_page_size));
  const financePages = Math.max(1, Math.ceil(reports.tenant_finance_total / reports.finance_page_size));
  const roomPages = Math.max(1, Math.ceil(reports.room_utilization_total / reports.room_page_size));

  const exportParams = new URLSearchParams({
    start_date: reports.start_date,
    end_date: reports.end_date,
  });
  if (reports.selected_academic_year_id) {
    exportParams.set("academic_year_id", String(reports.selected_academic_year_id));
  }
  if (reports.tenant_query) {
    exportParams.set("tenant_query", reports.tenant_query);
  }
  const exportQuery = exportParams.toString();

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
    reports.selected_academic_year_id
      ? {
          label: "Academic year",
          value:
            reports.available_academic_years.find((year) => year.id === reports.selected_academic_year_id)?.label ??
            String(reports.selected_academic_year_id),
          tone: "warning" as const,
        }
      : null,
    reports.tenant_query ? { label: "Tenant", value: reports.tenant_query, tone: "default" as const } : null,
    section !== "finance" ? { label: "Section", value: section, tone: "default" as const } : null,
  ].filter((item): item is NonNullable<typeof item> => Boolean(item));

  return (
    <div className="grid">
      <PageIntro
        title="Reports"
        description="Finance, occupancy, and conversion reporting with export-ready tables for operational review."
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
            {section === "finance" ? (
              <>
                <label className="filter-field">
                  <span>Academic year</span>
                  <select name="academic_year_id" defaultValue={reports.selected_academic_year_id ? String(reports.selected_academic_year_id) : ""}>
                    <option value="">All years</option>
                    {reports.available_academic_years.map((year) => (
                      <option key={year.id} value={year.id}>
                        {year.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="filter-field grow">
                  <span>Tenant</span>
                  <input type="search" name="tenant_query" defaultValue={reports.tenant_query} placeholder="Filter by tenant name" />
                </label>
              </>
            ) : null}
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
            <Link className={section === "finance" ? "button small" : "button small ghost"} href={buildReportsHref("finance", { agingPage: null, financePage: null })}>
              Finance
            </Link>
            <Link className={section === "occupancy" ? "button small" : "button small ghost"} href={buildReportsHref("occupancy", { roomPage: null })}>
              Occupancy
            </Link>
            <Link className={section === "conversion" ? "button small" : "button small ghost"} href={buildReportsHref("conversion")}>
              Conversion
            </Link>
          </div>
          <p className="filter-copy">
            Keep the date range on the left and switch report families without losing the current reporting context.
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
          <DataPanel title="Collections by method" description="Quick view of how money came in during the selected reporting window." tone="supporting">
            <InteractiveTable rows={reports.collections_by_method} emptyText="No collections landed in the selected period." searchPlaceholder="Filter methods" />
          </DataPanel>

          <DataPanel title="Receivables" description="Outstanding approved invoices that still need attention, grouped for follow-up work." tone="primary">
            <InteractiveTable rows={reports.aging_rows} emptyText="No outstanding approved invoices remain." searchPlaceholder="Filter receivables" />
            <div className="ledger-pagination">
              <span className="small">
                Page {Math.min(reports.aging_page, agingPages)} of {agingPages} | {reports.aging_total} row(s)
              </span>
              <div className="inline-actions">
                <Link
                  className={reports.aging_page <= 1 ? "button small ghost disabled-link" : "button small ghost"}
                  href={
                    reports.aging_page <= 1
                      ? buildReportsHref("finance", { agingPage: "1" })
                      : buildReportsHref("finance", { agingPage: String(reports.aging_page - 1) })
                  }
                >
                  Previous
                </Link>
                <Link
                  className={reports.aging_page >= agingPages ? "button small ghost disabled-link" : "button small ghost"}
                  href={
                    reports.aging_page >= agingPages
                      ? buildReportsHref("finance", { agingPage: String(agingPages) })
                      : buildReportsHref("finance", { agingPage: String(reports.aging_page + 1) })
                  }
                >
                  Next
                </Link>
              </div>
            </div>
          </DataPanel>

          <DataPanel title="Tenant finance ledger" description="Export-ready payment ledger by resident and academic year for finance review and bank matching outside the app." tone="secondary">
            <InteractiveTable rows={reports.tenant_finance_rows} emptyText="No payments were recorded in the selected period." searchPlaceholder="Filter tenant finance" />
            <div className="ledger-pagination">
              <span className="small">
                Page {Math.min(reports.finance_page, financePages)} of {financePages} | {reports.tenant_finance_total} row(s)
              </span>
              <div className="inline-actions">
                <Link
                  className={reports.finance_page <= 1 ? "button small ghost disabled-link" : "button small ghost"}
                  href={
                    reports.finance_page <= 1
                      ? buildReportsHref("finance", { financePage: "1" })
                      : buildReportsHref("finance", { financePage: String(reports.finance_page - 1) })
                  }
                >
                  Previous
                </Link>
                <Link
                  className={reports.finance_page >= financePages ? "button small ghost disabled-link" : "button small ghost"}
                  href={
                    reports.finance_page >= financePages
                      ? buildReportsHref("finance", { financePage: String(financePages) })
                      : buildReportsHref("finance", { financePage: String(reports.finance_page + 1) })
                  }
                >
                  Next
                </Link>
              </div>
            </div>
          </DataPanel>
        </>
      ) : null}

      {section === "occupancy" ? (
        <div className="grid three">
          <DataPanel title="Occupancy by block" description="High-level room usage by block." tone="supporting">
            <InteractiveTable rows={reports.block_occupancy_rows} emptyText="No block data available." searchPlaceholder="Filter blocks" />
          </DataPanel>
          <DataPanel title="Occupancy by floor" description="Detailed room usage by floor." tone="supporting">
            <InteractiveTable rows={reports.floor_occupancy_rows} emptyText="No floor data available." searchPlaceholder="Filter floors" />
          </DataPanel>
          <DataPanel title="Room utilization" description="Room-by-room view of total, occupied, reserved, and unavailable beds." tone="primary">
            <InteractiveTable rows={reports.room_utilization} emptyText="No room data available." searchPlaceholder="Filter rooms" />
            <div className="ledger-pagination">
              <span className="small">
                Page {Math.min(reports.room_page, roomPages)} of {roomPages} | {reports.room_utilization_total} row(s)
              </span>
              <div className="inline-actions">
                <Link
                  className={reports.room_page <= 1 ? "button small ghost disabled-link" : "button small ghost"}
                  href={
                    reports.room_page <= 1
                      ? buildReportsHref("occupancy", { roomPage: "1" })
                      : buildReportsHref("occupancy", { roomPage: String(reports.room_page - 1) })
                  }
                >
                  Previous
                </Link>
                <Link
                  className={reports.room_page >= roomPages ? "button small ghost disabled-link" : "button small ghost"}
                  href={
                    reports.room_page >= roomPages
                      ? buildReportsHref("occupancy", { roomPage: String(roomPages) })
                      : buildReportsHref("occupancy", { roomPage: String(reports.room_page + 1) })
                  }
                >
                  Next
                </Link>
              </div>
            </div>
          </DataPanel>
        </div>
      ) : null}

      {section === "conversion" ? (
        <DataPanel title="Conversion" description="Simple funnel view from prospect to invoiced resident to active stay." tone="primary">
          <InteractiveTable rows={reports.conversion_rows} emptyText="No conversion data available." searchPlaceholder="Filter metrics" />
        </DataPanel>
      ) : null}
    </div>
  );
}
