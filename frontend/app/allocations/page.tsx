import Link from "next/link";

import { AllocationRoster } from "../../components/allocation-roster";
import { DataPanel, PageIntro, StatusPill, SummaryStrip } from "../../components/page-shell";
import { fetchAllocationOverview, requireUser } from "../../lib/server-api";

type PageProps = {
  searchParams: Promise<{
    search?: string;
  }>;
};

export default async function AllocationsPage({ searchParams }: PageProps) {
  const user = await requireUser();

  if (!user.is_admin) {
    return (
      <div className="grid">
        <PageIntro
          eyebrow="Allocations"
          title="Allocation control is restricted to admins"
          actions={
            <>
              <Link className="button" href="/beds">
                Open beds
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
                <strong>Read-only daily operations</strong>
              </div>
            </div>
          }
        />
      </div>
    );
  }

  const params = await searchParams;
  const search = params.search ?? "";
  const overview = await fetchAllocationOverview(search);
  const transferableRows = overview.rows.filter((row) => row.transfer_targets.length).length;

  return (
    <div className="grid">
      <PageIntro
        title="Allocations"
        actions={
          <>
            <Link className="button ghost" href="/onboarding">
              Open onboarding
            </Link>
            <Link className="button ghost" href="/beds">
              Review beds
            </Link>
          </>
        }
        description="Transfer and move-out roster."
        aside={search ? <StatusPill tone="accent">Filtered</StatusPill> : <StatusPill>All stays</StatusPill>}
      />
      <SummaryStrip
        items={[
          { label: "Active stays", value: overview.active_allocations, tone: "accent" },
          { label: "Linked invoices", value: overview.linked_invoices, tone: "default" },
          { label: "Transfer-ready", value: transferableRows, tone: "success" },
        ]}
      />
      <DataPanel
        title="Active stays"
        toolbar={
          <form className="toolbar" method="get">
            <input name="search" defaultValue={search} placeholder="Search tenant, invoice, room" />
            <button className="button" type="submit">
              Search
            </button>
          </form>
        }
      >
        <AllocationRoster rows={overview.rows} />
      </DataPanel>
    </div>
  );
}
