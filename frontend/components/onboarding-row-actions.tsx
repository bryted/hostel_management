"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { BedOption, OnboardingQueueItem, User } from "../lib/api";
import {
  buildConfirmationMessage,
  confirmAction,
  storeFlashMessage,
} from "../lib/action-feedback";
import { postAction } from "../lib/client-api";

function moneyValue(value: string): number {
  const normalized = Number(value.replace(/[^\d.-]/g, ""));
  return Number.isFinite(normalized) ? normalized : 0;
}

type Props = {
  row: OnboardingQueueItem;
  user: User;
  availableBeds: BedOption[];
};

export function OnboardingRowActions({ row, user, availableBeds }: Props) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("cash");
  const [reference, setReference] = useState("");
  const [bedId, setBedId] = useState(availableBeds[0] ? String(availableBeds[0].bed_id) : "");
  const remainingBalance = moneyValue(row.balance);
  const paymentAmount = Number(amount);
  const paymentAmountInvalid =
    !amount.trim()
    || !Number.isFinite(paymentAmount)
    || paymentAmount <= 0
    || paymentAmount > remainingBalance;
  const referenceMissing = method !== "cash" && !reference.trim();

  async function runAction(path: string, payload: object, confirmation: string) {
    if (!(await confirmAction(confirmation))) {
      return;
    }
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const result = await postAction(path, payload);
      setMessage(result.message);
      storeFlashMessage({ tone: "success", message: result.message });
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Queue action failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="stack tight">
      <Link className="button small ghost" href={`/tenants/${row.tenant_id}`}>
        Workspace
      </Link>
      {row.stage === "Approved unpaid" ? (
        <div className="mini-action">
          <input
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            inputMode="decimal"
            placeholder={`Balance ${row.balance}`}
          />
          <select value={method} onChange={(event) => setMethod(event.target.value)}>
            <option value="cash">cash</option>
            <option value="card">card</option>
            <option value="bank_transfer">bank_transfer</option>
            <option value="mobile_money">mobile_money</option>
            <option value="check">check</option>
          </select>
          <input
            value={reference}
            onChange={(event) => setReference(event.target.value)}
            placeholder={method === "cash" ? "Optional reference" : "Reference required"}
          />
          <button
            className="button ghost small"
            disabled={pending}
            onClick={() => setAmount(remainingBalance.toFixed(2))}
            type="button"
          >
            Use balance
          </button>
          <button
            className="button success small"
            disabled={pending || paymentAmountInvalid || referenceMissing}
            onClick={() =>
              runAction(
                `/invoices/${row.invoice_id}/payments`,
                {
                  amount: Number(amount),
                  method,
                  reference,
                },
                buildConfirmationMessage("Collect this payment?", [
                  `Tenant: ${row.tenant_name}`,
                  `Invoice: ${row.invoice_no}`,
                  `Amount: ${amount}`,
                  `Method: ${method}`,
                  reference.trim() ? `Reference: ${reference.trim()}` : null,
                ]),
              )
            }
          >
            Collect payment
          </button>
        </div>
      ) : null}
      {row.stage === "Approved unpaid" && paymentAmount > remainingBalance ? (
        <p className="error-text">Amount exceeds the remaining balance of {row.balance}.</p>
      ) : null}
      {row.stage === "Approved unpaid" && referenceMissing ? (
        <p className="error-text">Reference is required for non-cash payments.</p>
      ) : null}
      {row.stage === "Paid unallocated" && user.is_admin ? (
        <div className="mini-action">
          <select value={bedId} onChange={(event) => setBedId(event.target.value)}>
            {availableBeds.map((bed) => (
              <option key={bed.bed_id} value={bed.bed_id}>
                {bed.label}
              </option>
            ))}
          </select>
          <button
            className="button success small"
            disabled={pending || !bedId}
            onClick={() =>
              runAction(
                `/invoices/${row.invoice_id}/allocate`,
                {
                  bed_id: Number(bedId),
                },
                buildConfirmationMessage("Assign this paid tenant to a bed?", [
                  `Tenant: ${row.tenant_name}`,
                  `Invoice: ${row.invoice_no}`,
                  `Bed ID: ${bedId}`,
                ]),
              )
            }
          >
            Assign bed
          </button>
        </div>
      ) : null}
      {message ? <p className="success-text">{message}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}
    </div>
  );
}
