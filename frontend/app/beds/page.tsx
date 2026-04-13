import Link from "next/link";

import { BedMaintenanceForm } from "../../components/bed-maintenance-form";
import { DataPanel, FilterChipBar, PageIntro, SummaryStrip, StatusPill } from "../../components/page-shell";
import { fetchBeds, requireUser } from "../../lib/server-api";

type PageProps = {
  searchParams: Promise<{
    search?: string;
    status?: string;
    page?: string;
  }>;
};

function badgeClass(status: string): string {
  if (status === "AVAILABLE") {
    return "badge available";
  }
  if (status === "RESERVED") {
    return "badge reserved";
  }
  if (status === "OCCUPIED") {
    return "badge occupied";
  }
  return "badge out";
}

export default async function BedsPage({ searchParams }: PageProps) {
  const user = await requireUser();
  const params = await searchParams;
  const search = params.search ?? "";
  const status = params.status ?? "";
  const page = Math.max(1, Number(params.page || "1") || 1);
  const beds = await fetchBeds(search, status, page);
  const totalPages = Math.max(1, Math.ceil(beds.total / beds.page_size));
  const activeFilterItems = [
    search ? { label: "Search", value: search, tone: "accent" as const } : null,
    status ? { label: "Status", value: status, tone: "warning" as const } : null,
  ].filter((item): item is NonNullable<typeof item> => Boolean(item));

  function buildBedsHref(overrides: {
    search?: string;
    status?: string;
    page?: string | null;
  }): string {
    const query = new URLSearchParams();
    const nextSearch = overrides.search ?? search;
    const nextStatus = overrides.status ?? status;
    const nextPage = overrides.page === undefined ? String(page) : overrides.page ?? "";
    if (nextSearch) {
      query.set("search", nextSearch);
    }
    if (nextStatus) {
      query.set("status", nextStatus);
    }
    if (nextPage && nextPage !== "1") {
      query.set("page", nextPage);
    }
    const suffix = query.toString();
    return suffix ? `/beds?${suffix}` : "/beds";
  }

  return (
    <div className="grid">
      <PageIntro
        title="Beds"
        description="Live availability and maintenance state."
        actions={
          user.is_admin ? (
            <Link className="button ghost" href="/inventory">
              Open inventory admin
            </Link>
          ) : null
        }
        aside={
          <>
            {status ? <StatusPill tone="accent">{status}</StatusPill> : <StatusPill>All statuses</StatusPill>}
            <StatusPill tone={user.is_admin ? "success" : "default"}>{user.is_admin ? "Maintenance enabled" : "Read only"}</StatusPill>
          </>
        }
      />
      <section className="panel filter-bar">
        <div className="filter-bar-main">
          <form className="filter-form" method="get">
            <label className="filter-field grow">
              <span>Search</span>
              <input name="search" type="search" defaultValue={search} placeholder="Search tenant, room, or invoice" />
            </label>
            <label className="filter-field">
              <span>Status</span>
              <select name="status" defaultValue={status}>
                <option value="">All statuses</option>
                <option value="AVAILABLE">Available</option>
                <option value="RESERVED">Reserved</option>
                <option value="OCCUPIED">Occupied</option>
                <option value="OUT_OF_SERVICE">Out of service</option>
              </select>
            </label>
            <div className="filter-actions">
              <button className="button" type="submit">
                Apply filters
              </button>
              <Link className="button ghost" href="/beds">
                Reset
              </Link>
            </div>
          </form>
          <p className="filter-copy">
            Use one register filter row for live bed status, then work row-level actions inside the table.
          </p>
        </div>
        <FilterChipBar items={activeFilterItems} clearHref="/beds" />
      </section>
      <SummaryStrip
        items={[
          { label: "Visible beds", value: beds.total, tone: "default" },
          { label: "Available", value: beds.available_total, tone: "success" },
          { label: "Reserved", value: beds.reserved_total, tone: "warning" },
          { label: "Occupied", value: beds.occupied_total, tone: "accent" },
          { label: "Out of service", value: beds.out_of_service_total, tone: "default" },
        ]}
      />
      <DataPanel title="Register" description="Live rooming register with maintenance controls and tenant context." tone="primary">
        {!beds.rows.length ? (
          <p className="empty-state">
            No beds match the current filters. Adjust the status filter or search
            for a different room, tenant, or invoice.
          </p>
        ) : null}
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Location</th>
                <th>Status</th>
                <th>Tenant</th>
                <th>Invoice</th>
                <th>Price</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {beds.rows.length ? (
                beds.rows.map((bed) => (
                  <tr key={bed.bed_id}>
                    <td>
                      {bed.block} / {bed.floor} / {bed.room} / {bed.bed}
                    </td>
                    <td>
                      <span className={badgeClass(bed.status)}>{bed.status}</span>
                    </td>
                    <td>{bed.tenant ?? "-"}</td>
                    <td>{bed.invoice ?? "-"}</td>
                    <td>{bed.price_per_bed}</td>
                    <td>
                      <div className="stack tight">
                        {bed.tenant_id ? (
                          <Link className="button small" href={`/tenants/${bed.tenant_id}`}>
                            Open workspace
                          </Link>
                        ) : null}
                        <BedMaintenanceForm bed={bed} canEdit={user.is_admin} />
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="small">
                    No bed rows match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="ledger-pagination">
          <span className="small">
            Page {Math.min(page, totalPages)} of {totalPages} | {beds.total} bed(s)
          </span>
          <div className="inline-actions">
            <Link
              className={page <= 1 ? "button small ghost disabled-link" : "button small ghost"}
              href={page <= 1 ? buildBedsHref({ page: "1" }) : buildBedsHref({ page: String(page - 1) })}
            >
              Previous
            </Link>
            <Link
              className={page >= totalPages ? "button small ghost disabled-link" : "button small ghost"}
              href={page >= totalPages ? buildBedsHref({ page: String(totalPages) }) : buildBedsHref({ page: String(page + 1) })}
            >
              Next
            </Link>
          </div>
        </div>
      </DataPanel>
    </div>
  );
}
