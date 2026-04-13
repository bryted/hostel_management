import Link from "next/link";

import { DataPanel, FilterChipBar, PageIntro, SummaryStrip, StatusPill } from "../../components/page-shell";
import { TenantActions } from "../../components/tenant-actions";
import { fetchTenants, requireUser } from "../../lib/server-api";

type PageProps = {
  searchParams: Promise<{
    search?: string;
    page?: string;
  }>;
};

export default async function TenantsPage({ searchParams }: PageProps) {
  await requireUser();
  const params = await searchParams;
  const search = params.search ?? "";
  const page = Math.max(1, Number(params.page || "1") || 1);
  const tenants = await fetchTenants(search, page);
  const totalPages = Math.max(1, Math.ceil(tenants.total / tenants.page_size));
  const activeFilterItems = search ? [{ label: "Search", value: search, tone: "accent" as const }] : [];

  function buildTenantHref(nextPage: number): string {
    const query = new URLSearchParams();
    if (search) {
      query.set("search", search);
    }
    if (nextPage > 1) {
      query.set("page", String(nextPage));
    }
    const suffix = query.toString();
    return suffix ? `/tenants?${suffix}` : "/tenants";
  }

  return (
    <div className="grid">
      <PageIntro
        title="Residents"
        description="Resident directory with quick access to each person’s operational workspace."
        aside={search ? <StatusPill tone="accent">Filtered</StatusPill> : <StatusPill>All records</StatusPill>}
      />
      <section className="panel filter-bar">
        <div className="filter-bar-main">
          <form className="filter-form" method="get">
            <label className="filter-field grow">
              <span>Resident search</span>
              <input name="search" type="search" defaultValue={search} placeholder="Search name, email, or phone" />
            </label>
            <div className="filter-actions">
              <button className="button" type="submit">
                Apply search
              </button>
              <Link className="button ghost" href="/tenants">
                Reset
              </Link>
            </div>
          </form>
          <p className="filter-copy">
            Keep the directory search above the summary so the counts and the table always reflect the same resident slice.
          </p>
        </div>
        <FilterChipBar items={activeFilterItems} clearHref="/tenants" />
      </section>
      <SummaryStrip
        items={[
          { label: "Visible tenants", value: tenants.total, tone: "default" },
          { label: "Active", value: tenants.active_total, tone: "success" },
          { label: "Prospects", value: tenants.prospect_total, tone: "warning" },
        ]}
      />
      <div className="grid two workspace-grid">
        <DataPanel
          title="Directory"
          description="Open a workspace to handle room status, billing, receipts, and the resident timeline in one place."
          tone="primary"
        >
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Phone</th>
                  <th>Status</th>
                  <th>Open</th>
                </tr>
              </thead>
              <tbody>
                {tenants.rows.length ? (
                  tenants.rows.map((tenant) => (
                    <tr key={tenant.id}>
                      <td>{tenant.name}</td>
                      <td>{tenant.email ?? "-"}</td>
                      <td>{tenant.phone ?? "-"}</td>
                      <td>
                        <StatusPill tone={tenant.status === "active" ? "success" : "warning"}>
                          {tenant.status === "active" ? "Checked in" : tenant.status === "inactive" ? "Archived" : "Prospect"}
                        </StatusPill>
                      </td>
                      <td>
                        <Link className="button small" href={`/tenants/${tenant.id}`}>
                          Workspace
                        </Link>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td className="small" colSpan={5}>
                      No residents match the current directory search.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="ledger-pagination">
            <span className="small">
              Page {Math.min(page, totalPages)} of {totalPages} | {tenants.total} resident(s)
            </span>
            <div className="inline-actions">
              <Link
                className={page <= 1 ? "button small ghost disabled-link" : "button small ghost"}
                href={buildTenantHref(Math.max(page - 1, 1))}
              >
                Previous
              </Link>
              <Link
                className={page >= totalPages ? "button small ghost disabled-link" : "button small ghost"}
                href={buildTenantHref(Math.min(page + 1, totalPages))}
              >
                Next
              </Link>
            </div>
          </div>
        </DataPanel>
        <TenantActions title="Create tenant" />
      </div>
    </div>
  );
}
