import Link from "next/link";

import { OnboardingRowActions } from "../../components/onboarding-row-actions";
import { DataPanel, PageIntro, SummaryStrip, StatusPill } from "../../components/page-shell";
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

  return (
    <div className="grid">
      <PageIntro
        title="Onboarding"
        description="Payment-to-allocation handoff queue."
        aside={stage ? <StatusPill tone={toneForStage(stage)}>{stage}</StatusPill> : <StatusPill>All stages</StatusPill>}
      />
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
      <DataPanel
        title="Onboarding queue"
        toolbar={
          <form className="toolbar" method="get">
            <input name="search" defaultValue={search} placeholder="Search tenant or invoice" />
            <select name="stage" defaultValue={stage}>
              <option value="">All stages</option>
              <option value="Approved unpaid">Approved unpaid</option>
              <option value="Paid unallocated">Paid unallocated</option>
            </select>
            <button className="button" type="submit">
              Filter
            </button>
          </form>
        }
      >
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
