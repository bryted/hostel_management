"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type {
  AllocationSummary,
  BedOption,
  InvoiceSummary,
  ReservationSummary,
  User,
} from "../lib/api";
import {
  buildConfirmationMessage,
  confirmAction,
  storeFlashMessage,
} from "../lib/action-feedback";
import { postAction } from "../lib/client-api";

type Props = {
  user: User;
  reservation: ReservationSummary | null;
  allocation: AllocationSummary | null;
  availableBeds: BedOption[];
  allocatableInvoices: InvoiceSummary[];
};

export function WorkspaceActions({
  user,
  reservation,
  allocation,
  availableBeds,
  allocatableInvoices,
}: Props) {
  const router = useRouter();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [reason, setReason] = useState("");
  const [extraHours, setExtraHours] = useState("24");
  const [transferBedId, setTransferBedId] = useState(
    availableBeds[0] ? String(availableBeds[0].bed_id) : "",
  );
  const [assignInvoiceId, setAssignInvoiceId] = useState(
    allocatableInvoices[0] ? String(allocatableInvoices[0].id) : "",
  );
  const [assignBedId, setAssignBedId] = useState(
    availableBeds[0] ? String(availableBeds[0].bed_id) : "",
  );

  if (!user.is_admin) {
    return null;
  }

  async function runAction(path: string, payload: object, confirmation: string) {
    if (!(await confirmAction(confirmation))) {
      return;
    }
    setPending(true);
    setError(null);
    setMessage(null);
    try {
      const result = await postAction(path, payload);
      setMessage(result.message);
      storeFlashMessage({ tone: "success", message: result.message });
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="panel">
      <h3>Workflow actions</h3>
      <div className="stack">
        {allocation ? (
          <div className="action-card">
            <h4>Active stay</h4>
            <p>
              {allocation.block} / {allocation.floor} / {allocation.room} / {allocation.bed}
            </p>
            <label className="field">
              <span>Reason</span>
              <input
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Transfer or move-out note"
              />
            </label>
            <div className="inline-actions">
              <button
                className="button danger"
                disabled={pending}
                onClick={() =>
                  runAction(
                    `/allocations/${allocation.id}/end`,
                    { reason },
                    buildConfirmationMessage("End this tenant stay?", [
                      `Current bed: ${allocation.block} / ${allocation.floor} / ${allocation.room} / ${allocation.bed}`,
                      reason.trim() ? `Reason: ${reason.trim()}` : "No move-out note entered.",
                    ]),
                  )
                }
              >
                End stay
              </button>
              {availableBeds.length ? (
                <>
                  <select
                    value={transferBedId}
                    onChange={(event) => setTransferBedId(event.target.value)}
                  >
                    {availableBeds.map((bed) => (
                      <option key={bed.bed_id} value={bed.bed_id}>
                        {bed.label}
                      </option>
                    ))}
                  </select>
                  <button
                    className="button secondary"
                    disabled={pending}
                    onClick={() =>
                      runAction(
                        `/allocations/${allocation.id}/transfer`,
                        {
                          new_bed_id: Number(transferBedId),
                          reason,
                        },
                        buildConfirmationMessage("Transfer this tenant to a new bed?", [
                          `Current bed: ${allocation.block} / ${allocation.floor} / ${allocation.room} / ${allocation.bed}`,
                          `New bed ID: ${transferBedId}`,
                          reason.trim() ? `Reason: ${reason.trim()}` : "No transfer note entered.",
                        ]),
                      )
                    }
                  >
                    Transfer bed
                  </button>
                </>
              ) : null}
            </div>
          </div>
        ) : null}

        {reservation ? (
          <div className="action-card">
            <h4>Reservation</h4>
            <p>
              {reservation.block} / {reservation.floor} / {reservation.room} /{" "}
              {reservation.bed}
            </p>
            <label className="field">
              <span>Extra hold hours</span>
              <input
                type="number"
                min="1"
                max="168"
                value={extraHours}
                onChange={(event) => setExtraHours(event.target.value)}
              />
            </label>
            <label className="field">
              <span>Note</span>
              <input
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Reservation follow-up"
              />
            </label>
            <div className="inline-actions">
              <button
                className="button"
                disabled={pending}
                onClick={() =>
                  runAction(
                    `/reservations/${reservation.id}/extend`,
                    {
                      extra_hours: Number(extraHours),
                      reason,
                    },
                    buildConfirmationMessage("Extend this reservation hold?", [
                      `Reserved bed: ${reservation.block} / ${reservation.floor} / ${reservation.room} / ${reservation.bed}`,
                      `Extra hours: ${extraHours}`,
                      reason.trim() ? `Note: ${reason.trim()}` : "No note entered.",
                    ]),
                  )
                }
              >
                Extend hold
              </button>
              <button
                className="button danger"
                disabled={pending}
                onClick={() =>
                  runAction(
                    `/reservations/${reservation.id}/cancel`,
                    { reason },
                    buildConfirmationMessage("Cancel this reservation hold?", [
                      `Reserved bed: ${reservation.block} / ${reservation.floor} / ${reservation.room} / ${reservation.bed}`,
                      reason.trim() ? `Reason: ${reason.trim()}` : "No cancellation note entered.",
                    ]),
                  )
                }
              >
                Cancel hold
              </button>
            </div>
          </div>
        ) : null}

        {!allocation && allocatableInvoices.length && availableBeds.length ? (
          <div className="action-card">
            <h4>Assign paid invoice</h4>
            <div className="inline-actions">
              <select
                value={assignInvoiceId}
                onChange={(event) => setAssignInvoiceId(event.target.value)}
              >
                {allocatableInvoices.map((invoice) => (
                  <option key={invoice.id} value={invoice.id}>
                    {invoice.invoice_no}
                  </option>
                ))}
              </select>
              <select
                value={assignBedId}
                onChange={(event) => setAssignBedId(event.target.value)}
              >
                {availableBeds.map((bed) => (
                  <option key={bed.bed_id} value={bed.bed_id}>
                    {bed.label}
                  </option>
                ))}
              </select>
              <button
              className="button success"
              disabled={pending}
              onClick={() =>
                runAction(
                  `/invoices/${assignInvoiceId}/allocate`,
                  {
                    bed_id: Number(assignBedId),
                  },
                  buildConfirmationMessage("Assign this paid invoice to a bed?", [
                    `Invoice ID: ${assignInvoiceId}`,
                    `Bed ID: ${assignBedId}`,
                    "This will confirm the tenant's stay on the selected bed.",
                  ]),
                )
              }
            >
              Assign bed
            </button>
            </div>
          </div>
        ) : null}

        {message ? <p className="success-text">{message}</p> : null}
        {error ? <p className="error-text">{error}</p> : null}
      </div>
    </section>
  );
}
