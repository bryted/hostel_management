import Link from "next/link";

import { BedMaintenanceForm } from "../../components/bed-maintenance-form";
import { DataPanel, FilterChipBar, PageIntro, SummaryStrip, StatusPill } from "../../components/page-shell";
import { fetchBeds, requireUser } from "../../lib/server-api";

type PageProps = {
  searchParams: Promise<{
    search?: string;
    status?: string;
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
  const beds = await fetchBeds(search, status);
  const availableCount = beds.filter((bed) => bed.status === "AVAILABLE").length;
  const reservedCount = beds.filter((bed) => bed.status === "RESERVED").length;
  const occupiedCount = beds.filter((bed) => bed.status === "OCCUPIED").length;
  const outCount = beds.filter((bed) => bed.status === "OUT_OF_SERVICE").length;
  const activeFilterItems = [
    search ? { label: "Search", value: search, tone: "accent" as const } : null,
    status ? { label: "Status", value: status, tone: "warning" as const } : null,
  ].filter((item): item is NonNullable<typeof item> => Boolean(item));

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
          { label: "Visible beds", value: beds.length, tone: "default" },
          { label: "Available", value: availableCount, tone: "success" },
          { label: "Reserved", value: reservedCount, tone: "warning" },
          { label: "Occupied", value: occupiedCount, tone: "accent" },
          { label: "Out of service", value: outCount, tone: "default" },
        ]}
      />
      <DataPanel title="Register">
        {!beds.length ? (
          <p className="section-note">
            No beds match the current filters. Adjust the status filter or search
            for a different room, tenant, or invoice.
          </p>
        ) : null}
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
            {beds.length ? (
              beds.map((bed) => (
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
      </DataPanel>
    </div>
  );
}
