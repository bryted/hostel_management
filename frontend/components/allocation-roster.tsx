"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import type { AllocationRosterItem } from "../lib/api";
import {
  buildConfirmationMessage,
  confirmAction,
  storeFlashMessage,
} from "../lib/action-feedback";
import { postAction } from "../lib/client-api";

type Props = {
  rows: AllocationRosterItem[];
};

export function AllocationRoster({ rows }: Props) {
  const router = useRouter();
  const initialTargets = useMemo(
    () =>
      Object.fromEntries(
        rows
          .filter((row) => row.transfer_targets.length)
          .map((row) => [row.allocation_id, String(row.transfer_targets[0].bed_id)]),
      ),
    [rows],
  );
  const [targets, setTargets] = useState<Record<number, string>>(initialTargets);
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function runAction(
    allocationId: number,
    action: "end" | "transfer",
  ) {
    const row = rows.find((item) => item.allocation_id === allocationId);
    if (!row) {
      return;
    }
    if (
      !(await confirmAction(
        buildConfirmationMessage(
          action === "transfer" ? "Transfer this allocation?" : "End this tenant stay?",
          [
            `Tenant: ${row.tenant_name}`,
            `Current bed: ${row.block} / ${row.floor} / ${row.room} / ${row.bed}`,
            action === "transfer" ? `New bed ID: ${targets[allocationId]}` : null,
            reasons[allocationId]?.trim() ? `Reason: ${reasons[allocationId].trim()}` : "No note entered.",
          ],
        ),
      ))
    ) {
      return;
    }
    setPendingKey(`${allocationId}:${action}`);
    setMessage(null);
    setError(null);
    try {
      const payload =
        action === "transfer"
          ? {
              new_bed_id: Number(targets[allocationId]),
              reason: reasons[allocationId] ?? "",
            }
          : { reason: reasons[allocationId] ?? "" };
      const result = await postAction(
        `/allocations/${allocationId}/${action}`,
        payload,
      );
      setMessage(result.message);
      storeFlashMessage({ tone: "success", message: result.message });
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Allocation action failed.");
    } finally {
      setPendingKey(null);
    }
  }

  return (
    <div className="stack">
      {message ? <p className="success-text">{message}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}
      <table className="table">
        <thead>
          <tr>
            <th>Tenant</th>
            <th>Invoice</th>
            <th>Location</th>
            <th>Start</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((row) => (
              <tr key={row.allocation_id}>
                <td>
                  <div className="stack tight">
                    <strong>{row.tenant_name}</strong>
                    <span className="small">#{row.allocation_id}</span>
                  </div>
                </td>
                <td>{row.invoice_no ?? "-"}</td>
                <td>
                  {row.block} / {row.floor} / {row.room} / {row.bed}
                </td>
                <td>{row.start_date ?? "-"}</td>
                <td>
                  <div className="stack tight">
                    <div className="inline-actions">
                      <Link className="button small ghost" href={`/tenants/${row.tenant_id}`}>
                        Workspace
                      </Link>
                      <button
                        className="button small"
                        disabled={pendingKey === `${row.allocation_id}:end`}
                        onClick={() => runAction(row.allocation_id, "end")}
                        type="button"
                      >
                        End stay
                      </button>
                    </div>
                    <input
                      value={reasons[row.allocation_id] ?? ""}
                      onChange={(event) =>
                        setReasons((current) => ({
                          ...current,
                          [row.allocation_id]: event.target.value,
                        }))
                      }
                      placeholder="Reason"
                    />
                    {row.transfer_targets.length ? (
                      <div className="inline-actions">
                        <select
                          value={targets[row.allocation_id] ?? ""}
                          onChange={(event) =>
                            setTargets((current) => ({
                              ...current,
                              [row.allocation_id]: event.target.value,
                            }))
                          }
                        >
                          {row.transfer_targets.map((target) => (
                            <option key={target.bed_id} value={target.bed_id}>
                              {target.label}
                            </option>
                          ))}
                        </select>
                        <button
                          className="button small secondary"
                          disabled={
                            pendingKey === `${row.allocation_id}:transfer` ||
                            !targets[row.allocation_id]
                          }
                          onClick={() => runAction(row.allocation_id, "transfer")}
                          type="button"
                        >
                          Transfer
                        </button>
                      </div>
                    ) : (
                      <span className="small">No eligible transfer beds.</span>
                    )}
                  </div>
                </td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={5} className="small">
                No active allocations match the current filter.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
