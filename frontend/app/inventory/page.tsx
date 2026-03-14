import Link from "next/link";

import { InventoryActions } from "../../components/inventory-actions";
import { InventoryBatchUpload } from "../../components/inventory-batch-upload";
import { DataPanel, PageIntro, StatusPill, SummaryStrip } from "../../components/page-shell";
import { fetchInventoryOverview, requireUser } from "../../lib/server-api";

type PageProps = {
  searchParams: Promise<{
    section?: string;
  }>;
};

type InventorySection = "overview" | "structure" | "integrity";

function isInventorySection(value: string | undefined): value is InventorySection {
  return value === "overview" || value === "structure" || value === "integrity";
}

export default async function InventoryPage({ searchParams }: PageProps) {
  const user = await requireUser();

  if (!user.is_admin) {
    return (
      <div className="grid">
        <PageIntro
          eyebrow="Inventory"
          title="Inventory administration is restricted to admins"
          actions={
            <>
              <Link className="button" href="/beds">
                Open bed register
              </Link>
              <Link className="button ghost" href="/billing">
                Return to billing desk
              </Link>
            </>
          }
          aside={
            <div className="meta-list">
              <div className="meta-row">
                <span>Signed in as</span>
                <strong>{user.full_name}</strong>
              </div>
              <div className="meta-row">
                <span>Role</span>
                <StatusPill tone="warning">Cashier</StatusPill>
              </div>
              <div className="meta-row">
                <span>Scope</span>
                <strong>Read-only operations</strong>
              </div>
            </div>
          }
        />
      </div>
    );
  }

  const params = await searchParams;
  const section: InventorySection = isInventorySection(params.section) ? params.section : "overview";
  const inventory = await fetchInventoryOverview();
  const activeRooms = inventory.rooms.filter((room) => room.is_active).length;
  const inactiveRooms = inventory.rooms.length - activeRooms;
  const availableBeds = inventory.rooms.reduce((sum, room) => sum + room.available_beds, 0);
  const occupiedBeds = inventory.rooms.reduce((sum, room) => sum + room.occupied_beds, 0);
  const reservedBeds = inventory.rooms.reduce((sum, room) => sum + room.reserved_beds, 0);
  const outOfServiceBeds = inventory.rooms.reduce((sum, room) => sum + room.out_of_service_beds, 0);
  const integrityIssues = inventory.integrity_rows.filter((row) => row.Status === "CHECK").length;
  const blockSummaries = inventory.blocks.map((block) => {
    const blockRooms = inventory.rooms.filter((room) => room.block_id === block.id);
    return {
      id: block.id,
      name: block.name,
      floors: inventory.floors.filter((floor) => floor.block_id === block.id).length,
      rooms: blockRooms.length,
      available: blockRooms.reduce((sum, room) => sum + room.available_beds, 0),
      occupied: blockRooms.reduce((sum, room) => sum + room.occupied_beds, 0),
      outOfService: blockRooms.reduce((sum, room) => sum + room.out_of_service_beds, 0),
    };
  });
  const floorSummaries = inventory.floors.map((floor) => {
    const floorRooms = inventory.rooms.filter((room) => room.floor_id === floor.id);
    return {
      id: floor.id,
      label: floor.floor_label,
      blockName: floor.block_name,
      rooms: floorRooms.length,
      available: floorRooms.reduce((sum, room) => sum + room.available_beds, 0),
      occupied: floorRooms.reduce((sum, room) => sum + room.occupied_beds, 0),
      reserved: floorRooms.reduce((sum, room) => sum + room.reserved_beds, 0),
    };
  });

  function buildInventoryHref(nextSection: InventorySection): string {
    return nextSection === "overview" ? "/inventory" : `/inventory?section=${nextSection}`;
  }

  const exportLinks =
    section === "structure"
      ? [
          { href: "/api/proxy/inventory/rooms.csv", label: "Download all rooms" },
          { href: "/api/proxy/inventory/available-rooms.csv", label: "Download available rooms" },
          { href: "/api/proxy/inventory/available-beds.csv", label: "Download available beds" },
          { href: "/api/proxy/inventory/upload-template.csv", label: "Download upload template" },
        ]
      : [
          { href: "/api/proxy/inventory/available-rooms.csv", label: "Download available rooms" },
          { href: "/api/proxy/inventory/available-beds.csv", label: "Download available beds" },
          { href: "/api/proxy/inventory/upload-template.csv", label: "Download upload template" },
        ];

  return (
    <div className="grid">
      <PageIntro
        title="Inventory"
        actions={
          <>
            <Link className={section === "overview" ? "button small" : "button small ghost"} href={buildInventoryHref("overview")}>
              Overview
            </Link>
            <Link className={section === "structure" ? "button small" : "button small ghost"} href={buildInventoryHref("structure")}>
              Structure
            </Link>
            <Link className={section === "integrity" ? "button small" : "button small ghost"} href={buildInventoryHref("integrity")}>
              Integrity
            </Link>
            <Link className="button ghost small" href="/beds">
              Review live bed register
            </Link>
            <Link className="button ghost small" href="/onboarding">
              Open onboarding queue
            </Link>
            {exportLinks.map((item) => (
              <a key={item.href} className="button ghost small" download href={item.href}>
                {item.label}
              </a>
            ))}
          </>
        }
        aside={<StatusPill tone={integrityIssues ? "warning" : "success"}>{integrityIssues ? `${integrityIssues} integrity checks` : "Integrity clean"}</StatusPill>}
      />
      <SummaryStrip
        items={[
          { label: "Blocks", value: inventory.total_blocks, tone: "default" },
          { label: "Floors", value: inventory.total_floors, tone: "default" },
          { label: "Rooms", value: inventory.total_rooms, tone: "accent" },
          { label: "Beds", value: inventory.total_beds, tone: "default" },
          { label: "Available beds", value: availableBeds, tone: "success" },
          { label: "Integrity checks", value: integrityIssues, tone: integrityIssues ? "warning" : "success" },
        ]}
      />

      {section === "overview" ? (
        <div className="grid two">
          <DataPanel title="Blocks" description="High-level capacity by block. Open Structure for floor and room detail.">
            <table className="table">
              <thead>
                <tr>
                  <th>Block</th>
                  <th>Floors</th>
                  <th>Rooms</th>
                  <th>Available</th>
                  <th>Occupied</th>
                  <th>Out of service</th>
                </tr>
              </thead>
              <tbody>
                {blockSummaries.map((block) => (
                  <tr key={block.id}>
                    <td>{block.name}</td>
                    <td>{block.floors}</td>
                    <td>{block.rooms}</td>
                    <td>{block.available}</td>
                    <td>{block.occupied}</td>
                    <td>{block.outOfService}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </DataPanel>
          <DataPanel title="Capacity snapshot">
            <div className="detail-grid">
              <div className="detail-card">
                <h4>Active rooms</h4>
                <strong>{activeRooms}</strong>
              </div>
              <div className="detail-card">
                <h4>Inactive rooms</h4>
                <strong>{inactiveRooms}</strong>
              </div>
              <div className="detail-card">
                <h4>Reserved beds</h4>
                <strong>{reservedBeds}</strong>
              </div>
              <div className="detail-card">
                <h4>Occupied beds</h4>
                <strong>{occupiedBeds}</strong>
              </div>
              <div className="detail-card">
                <h4>Out of service</h4>
                <strong>{outOfServiceBeds}</strong>
              </div>
            </div>
          </DataPanel>
        </div>
      ) : null}

      <div className="grid two workspace-grid">
        <InventoryActions
          blocks={inventory.blocks}
          floors={inventory.floors}
          rooms={inventory.rooms}
        />
        <InventoryBatchUpload />
      </div>

      {section === "integrity" ? (
        <DataPanel title="Integrity" description="Use this view to reconcile configured room structure against live beds.">
          <table className="table">
            <thead>
              <tr>
                <th>Room</th>
                <th>Configured</th>
                <th>Actual</th>
                <th>Status</th>
                <th>Issues</th>
              </tr>
            </thead>
            <tbody>
              {inventory.integrity_rows.length ? (
                inventory.integrity_rows.map((row, index) => (
                  <tr key={`${row.Room}-${index}`}>
                    <td>
                      {row.Block} / {row.Floor || "Unassigned"} / {row.Room}
                    </td>
                    <td>{row["Configured beds"]}</td>
                    <td>{row["Actual beds"]}</td>
                    <td>
                      <StatusPill tone={row.Status === "CHECK" ? "warning" : "success"}>
                        {String(row.Status ?? "OK")}
                      </StatusPill>
                    </td>
                    <td>{row.Issues || "-"}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="small">
                    No integrity rows are available.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </DataPanel>
      ) : null}

      {section === "structure" ? (
        <>
          <DataPanel title="Floors">
            <table className="table">
              <thead>
                <tr>
                  <th>Block</th>
                  <th>Floor</th>
                  <th>Rooms</th>
                  <th>Available</th>
                  <th>Reserved</th>
                  <th>Occupied</th>
                </tr>
              </thead>
              <tbody>
                {floorSummaries.length ? (
                  floorSummaries.map((floor) => (
                    <tr key={floor.id}>
                      <td>{floor.blockName}</td>
                      <td>{floor.label}</td>
                      <td>{floor.rooms}</td>
                      <td>{floor.available}</td>
                      <td>{floor.reserved}</td>
                      <td>{floor.occupied}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} className="small">
                      No floors are configured yet. Add a floor after creating a block.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </DataPanel>
          <DataPanel title="Rooms">
            <table className="table">
              <thead>
                <tr>
                  <th>Location</th>
                  <th>Type</th>
                  <th>Price/bed</th>
                  <th>Available</th>
                  <th>Reserved</th>
                  <th>Occupied</th>
                  <th>Out of service</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {inventory.rooms.length ? (
                  inventory.rooms.map((room) => (
                    <tr key={room.room_id}>
                      <td>
                        {room.block_name} / {room.floor_label ?? "Unassigned"} / {room.room_code}
                      </td>
                      <td>{room.room_type ?? "-"}</td>
                      <td>{room.unit_price_per_bed}</td>
                      <td>{room.available_beds}</td>
                      <td>{room.reserved_beds}</td>
                      <td>{room.occupied_beds}</td>
                      <td>{room.out_of_service_beds}</td>
                      <td>
                        <StatusPill tone={room.is_active ? "success" : "warning"}>
                          {room.is_active ? "Active" : "Inactive"}
                        </StatusPill>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={8} className="small">
                      No rooms are configured yet. Create the first block, floor, and room from the admin actions panel.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </DataPanel>
        </>
      ) : null}
    </div>
  );
}
