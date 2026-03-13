"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import type { BedOption, InvoiceDetail, PaymentSummary } from "../lib/api";
import {
  buildConfirmationMessage,
  confirmAction,
  storeFlashMessage,
} from "../lib/action-feedback";
import { postAction } from "../lib/client-api";

type Props = {
  detail: InvoiceDetail;
};

function cleanMoney(value: string): string {
  const normalized = value.replace(/[^\d.-]/g, "");
  return normalized || "0";
}

export function InvoiceDetailActions({ detail }: Props) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reservedBedId, setReservedBedId] = useState(
    detail.reserved_bed_id ? String(detail.reserved_bed_id) : (detail.available_beds[0] ? String(detail.available_beds[0].bed_id) : ""),
  );
  const [tax, setTax] = useState(cleanMoney(detail.tax));
  const [discount, setDiscount] = useState(cleanMoney(detail.discount));
  const [holdHours, setHoldHours] = useState("24");
  const [dueAt, setDueAt] = useState(detail.invoice.due_at ? detail.invoice.due_at.slice(0, 10) : "");
  const [notes, setNotes] = useState(detail.notes ?? "");
  const [cancelReason, setCancelReason] = useState("");
  const [voidPaymentId, setVoidPaymentId] = useState("");
  const [voidReason, setVoidReason] = useState("");

  const editableBeds = useMemo(() => {
    const rows: BedOption[] = [...detail.available_beds];
    if (detail.reserved_bed_id && detail.reserved_bed_label && !rows.find((bed) => bed.bed_id === detail.reserved_bed_id)) {
      rows.unshift({
        bed_id: detail.reserved_bed_id,
        block: "",
        floor: "",
        room: "",
        bed: "",
        status: "RESERVED",
        label: detail.reserved_bed_label,
      });
    }
    return rows;
  }, [detail.available_beds, detail.reserved_bed_id, detail.reserved_bed_label]);

  const voidablePayments = detail.payments.filter((payment) => payment.status === "completed");

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
      setError(err instanceof Error ? err.message : "Invoice action failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="panel">
      <h3>Invoice actions</h3>
      <div className="stack">
        {detail.can_edit ? (
          <div className="action-card">
            <h4>Edit unpaid invoice</h4>
            <div className="stack tight">
              <label className="field">
                <span>Reserved bed</span>
                <select value={reservedBedId} onChange={(event) => setReservedBedId(event.target.value)}>
                  {editableBeds.map((bed) => (
                    <option key={bed.bed_id} value={bed.bed_id}>
                      {bed.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="inline-actions">
                <label className="field">
                  <span>Tax</span>
                  <input value={tax} onChange={(event) => setTax(event.target.value)} inputMode="decimal" />
                </label>
                <label className="field">
                  <span>Discount</span>
                  <input value={discount} onChange={(event) => setDiscount(event.target.value)} inputMode="decimal" />
                </label>
                <label className="field">
                  <span>Hold hours</span>
                  <input value={holdHours} onChange={(event) => setHoldHours(event.target.value)} inputMode="numeric" />
                </label>
              </div>
              <div className="inline-actions">
                <label className="field">
                  <span>Due date</span>
                  <input type="date" value={dueAt} onChange={(event) => setDueAt(event.target.value)} />
                </label>
                <label className="field">
                  <span>Notes</span>
                  <input value={notes} onChange={(event) => setNotes(event.target.value)} />
                </label>
              </div>
              <button
                className="button"
                disabled={pending || !reservedBedId}
                onClick={() =>
                  runAction(
                    `/invoices/${detail.invoice.id}/update`,
                    {
                      reserved_bed_id: Number(reservedBedId),
                      tax: Number(tax || "0"),
                      discount: Number(discount || "0"),
                      hold_hours: Number(holdHours || "24"),
                      due_at: dueAt || null,
                      notes,
                    },
                    buildConfirmationMessage("Save these invoice changes?", [
                      `Invoice: ${detail.invoice.invoice_no}`,
                      `Bed ID: ${reservedBedId}`,
                      `Due date: ${dueAt || "Not set"}`,
                      notes.trim() ? `Note: ${notes.trim()}` : null,
                    ]),
                  )
                }
                type="button"
              >
                Save invoice
              </button>
            </div>
          </div>
        ) : null}

        {detail.can_cancel ? (
          <div className="action-card">
            <h4>Cancel invoice</h4>
            <div className="stack tight">
              <label className="field">
                <span>Reason</span>
                <input value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} placeholder="Cancellation reason" />
              </label>
              <button
                className="button danger"
                disabled={pending}
                onClick={() =>
                  runAction(
                    `/invoices/${detail.invoice.id}/cancel`,
                    { reason: cancelReason },
                    buildConfirmationMessage("Cancel this invoice?", [
                      `Invoice: ${detail.invoice.invoice_no}`,
                      cancelReason.trim() ? `Reason: ${cancelReason.trim()}` : "No cancellation note entered.",
                    ]),
                  )
                }
                type="button"
              >
                Cancel invoice
              </button>
            </div>
          </div>
        ) : null}

        {voidablePayments.length ? (
          <div className="action-card">
            <h4>Void payment</h4>
            <div className="stack tight">
              <label className="field">
                <span>Payment</span>
                <select value={voidPaymentId} onChange={(event) => setVoidPaymentId(event.target.value)}>
                  <option value="">Select payment</option>
                  {voidablePayments.map((payment: PaymentSummary) => (
                    <option key={payment.id} value={payment.id}>
                      {payment.payment_no} | {payment.amount}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Reason</span>
                <input value={voidReason} onChange={(event) => setVoidReason(event.target.value)} placeholder="Void reason" />
              </label>
              <button
                className="button danger"
                disabled={pending || !voidPaymentId}
                onClick={() =>
                  runAction(
                    `/invoices/payments/${voidPaymentId}/void`,
                    { reason: voidReason },
                    buildConfirmationMessage("Void this payment?", [
                      `Invoice: ${detail.invoice.invoice_no}`,
                      `Payment ID: ${voidPaymentId}`,
                      voidReason.trim() ? `Reason: ${voidReason.trim()}` : "No void note entered.",
                    ]),
                  )
                }
                type="button"
              >
                Void payment
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
