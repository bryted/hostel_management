import Link from "next/link";

import { DataPanel, FilterChipBar, PageIntro, SummaryStrip, StatusPill } from "../../components/page-shell";
import { TenantActions } from "../../components/tenant-actions";
import { fetchTenants, requireUser } from "../../lib/server-api";

type PageProps = {
  searchParams: Promise<{
    search?: string;
  }>;
};

export default async function TenantsPage({ searchParams }: PageProps) {
  await requireUser();
  const params = await searchParams;
  const search = params.search ?? "";
  const tenants = await fetchTenants(search);
  const activeCount = tenants.filter((tenant) => tenant.status === "active").length;
  const prospectCount = tenants.filter((tenant) => tenant.status === "prospect").length;
  const activeFilterItems = search ? [{ label: "Search", value: search, tone: "accent" as const }] : [];

  return (
    <div className="grid">
      <PageIntro
        title="Residents"
        description="Resident and prospect directory."
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
          { label: "Visible tenants", value: tenants.length, tone: "default" },
          { label: "Active", value: activeCount, tone: "success" },
          { label: "Prospects", value: prospectCount, tone: "warning" },
        ]}
      />
      <div className="grid two workspace-grid">
        <DataPanel title="Directory">
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
              {tenants.map((tenant) => (
                <tr key={tenant.id}>
                  <td>{tenant.name}</td>
                  <td>{tenant.email ?? "-"}</td>
                  <td>{tenant.phone ?? "-"}</td>
                  <td>
                    <StatusPill tone={tenant.status === "active" ? "success" : "warning"}>
                      {tenant.status}
                    </StatusPill>
                  </td>
                  <td>
                    <Link className="button small" href={`/tenants/${tenant.id}`}>
                      Workspace
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </DataPanel>
        <TenantActions title="Create tenant" />
      </div>
    </div>
  );
}
