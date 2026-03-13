"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { BedListItem } from "../lib/api";
import {
  buildConfirmationMessage,
  confirmAction,
  storeFlashMessage,
} from "../lib/action-feedback";
import { postAction } from "../lib/client-api";

type Props = {
  bed: BedListItem;
  canEdit: boolean;
};

export function BedMaintenanceForm({ bed, canEdit }: Props) {
  const router = useRouter();
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!canEdit) {
    return null;
  }

  const nextOutOfService = bed.status !== "OUT_OF_SERVICE";

  async function handleSubmit() {
    if (
      !(await confirmAction(
        buildConfirmationMessage(
          nextOutOfService ? "Block this bed for maintenance?" : "Return this bed to service?",
          [
            `Bed: ${bed.block} / ${bed.floor} / ${bed.room} / ${bed.bed}`,
            reason.trim() ? `Reason: ${reason.trim()}` : "No maintenance note entered.",
          ],
        ),
      ))
    ) {
      return;
    }
    setPending(true);
    setError(null);
    try {
      const result = await postAction(`/beds/${bed.bed_id}/maintenance`, {
        out_of_service: nextOutOfService,
        reason,
      });
      storeFlashMessage({ tone: "success", message: result.message });
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mini-action">
      <input
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        placeholder="Maintenance note"
      />
      <button className="button subtle small" onClick={handleSubmit} disabled={pending}>
        {nextOutOfService ? "Block bed" : "Return bed"}
      </button>
      {error ? <p className="error-text">{error}</p> : null}
    </div>
  );
}
