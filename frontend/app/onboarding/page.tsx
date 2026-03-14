import Link from "next/link";

import { OnboardingRowActions } from "../../components/onboarding-row-actions";
import { DataPanel, FilterChipBar, PageIntro, SummaryStrip, StatusPill } from "../../components/page-shell";
import { TenantActions } from "../../components/tenant-actions";
import { fetchOnboardingOverview, requireUser } from "../../lib/server-api";

type PageProps = {
  searchParams: Promise<{
    search?: string;
    stage?: string;
  }>;
};

function toneForStage(stage: string): "warning" | "accent" | "default" {
  if (stage === "Approved unpaid") {
    return "warning";
  }
  if (stage === "Paid unallocated") {
    return "accent";
  }
  return "default";
}

export default async function OnboardingPage({ searchParams }: PageProps) {
  const user = await requireUser();
  if (!user.is_admin) {
    return (
      <div className="grid">
        <PageIntro
          title="Onboarding is restricted to admins"
          actions={
            <>
              <Link className="button" href="/billing">
                Open billing
              </Link>
              <Link className="button ghost" href="/dashboard">
                Return to dashboard
              </Link>
            </>
          }
          aside={<StatusPill tone="warning">Cashier scope</StatusPill>}
        />
      </div>
    );
  }
  const params = await searchParams;
  const search = params.search ?? "";
  const stage = params.stage ?? "";
  const onboarding = await fetchOnboardingOverview(search, stage);
  const activeFilterItems = [
    search ? { label: "Search", value: search, tone: "accent" as const } : null,
    stage ? { label: "Stage", value: stage, tone: "warning" as const } : null,
  ].filter((item): item is NonNullable<typeof item> => Boolean(item));

  return (
    <div className="grid">
      <PageIntro
        title="Onboarding"
        description="Payment-to-allocation handoff queue."
        aside={stage ? <StatusPill tone={toneForStage(stage)}>{stage}</StatusPill> : <StatusPill>All stages</StatusPill>}
      />
      <section className="panel filter-bar">
        <div className="filter-bar-main">
          <form className="filter-form" method="get">
            <label className="filter-field grow">
              <span>Queue search</span>
              <input name="search" type="search" defaultValue={search} placeholder="Search tenant or invoice" />
            </label>
            <label className="filter-field">
              <span>Stage</span>
              <select name="stage" defaultValue={stage}>
                <option value="">All stages</option>
                <option value="Approved unpaid">Approved unpaid</option>
                <option value="Paid unallocated">Paid unallocated</option>
              </select>
            </label>
            <div className="filter-actions">
              <button className="button" type="submit">
                Apply filters
              </button>
              <Link className="button ghost" href="/onboarding">
                Reset
              </Link>
            </div>
          </form>
          <p className="filter-copy">
            Search and stage selection control the handoff queue before you allocate or recover expired holds.
          </p>
        </div>
        <FilterChipBar items={activeFilterItems} clearHref="/onboarding" />
      </section>
      <SummaryStrip
        items={[
          { label: "Prospects", value: onboarding.prospects, tone: "default" },
          { label: "Approved unpaid", value: onboarding.approved_unpaid, tone: "warning" },
          { label: "Paid unallocated", value: onboarding.paid_unallocated, tone: "accent" },
          { label: "Active allocated", value: onboarding.active_allocated, tone: "success" },
          { label: "Activated last 7d", value: onboarding.newly_activated_last_7d, tone: "success" },
        ]}
      />
      <TenantActions title="Capture prospect" defaultStatus="prospect" compact />
      <DataPanel title="Onboarding queue">
        <table className="table">
          <thead>
            <tr>
              <th>Stage</th>
              <th>Tenant</th>
              <th>Invoice</th>
              <th>Status</th>
              <th>Total</th>
              <th>Paid</th>
              <th>Balance</th>
              <th>Reserved bed</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {onboarding.queue_rows.length ? (
              onboarding.queue_rows.map((row) => (
                <tr key={row.invoice_id}>
                  <td>
                    <StatusPill tone={toneForStage(row.stage)}>{row.stage}</StatusPill>
                  </td>
                  <td>{row.tenant_name}</td>
                  <td>{row.invoice_no}</td>
                  <td>{row.invoice_status}</td>
                  <td>{row.total}</td>
                  <td>{row.paid}</td>
                  <td>{row.balance}</td>
                  <td>
                    {row.hold_expired ? (
                      <StatusPill tone="warning">Hold expired</StatusPill>
                    ) : (
                      row.reserved_bed_label ?? "-"
                    )}
                  </td>
                  <td>
                    <OnboardingRowActions
                      row={row}
                      user={user}
                      availableBeds={onboarding.available_beds}
                    />
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={9} className="small">
                  No onboarding records match the current queue filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </DataPanel>
    </div>
  );
}
