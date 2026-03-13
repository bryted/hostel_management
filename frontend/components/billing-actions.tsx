"use client";

import { useEffect, useRef, useState } from "react";

import type { BedOption, BillingInvoiceItem, TenantListItem, User } from "../lib/api";
import {
  buildConfirmationMessage,
  confirmAction,
  peekFlashMessage,
  storePassiveFlashMessage,
  storeFlashMessage,
} from "../lib/action-feedback";
import { postAction } from "../lib/client-api";

function moneyValue(value: string): number {
  const normalized = Number(value.replace(/[^\d.-]/g, ""));
  return Number.isFinite(normalized) ? normalized : 0;
}

type Props = {
  user: User;
  tenants: TenantListItem[];
  availableBeds: BedOption[];
  payableInvoices: BillingInvoiceItem[];
  submittedInvoices: BillingInvoiceItem[];
  defaultHoldHours: number;
  blockDuplicatePaymentReference: boolean;
  autoApproveInvoices: boolean;
};

export function BillingActions({
  user,
  tenants,
  availableBeds,
  payableInvoices,
  submittedInvoices,
  defaultHoldHours,
  blockDuplicatePaymentReference,
  autoApproveInvoices,
}: Props) {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const [tenantId, setTenantId] = useState(tenants[0] ? String(tenants[0].id) : "");
  const [bedId, setBedId] = useState(availableBeds[0] ? String(availableBeds[0].bed_id) : "");
  const [tax, setTax] = useState("0");
  const [discount, setDiscount] = useState("0");
  const [holdHours, setHoldHours] = useState(String(defaultHoldHours));
  const [dueAt, setDueAt] = useState(new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState("");
  const [submitNow, setSubmitNow] = useState(true);

  const [paymentInvoiceId, setPaymentInvoiceId] = useState(
    payableInvoices[0] ? String(payableInvoices[0].id) : "",
  );
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("cash");
  const [reference, setReference] = useState("");

  const [approvalInvoiceId, setApprovalInvoiceId] = useState(
    submittedInvoices[0] ? String(submittedInvoices[0].id) : "",
  );
  const [rejectionReason, setRejectionReason] = useState("");
  const warnedHoldInvoicesRef = useRef<Set<number>>(new Set());

  const selectedTenant = tenants.find((tenant) => String(tenant.id) === tenantId) ?? null;
  const selectedBed = availableBeds.find((bed) => String(bed.bed_id) === bedId) ?? null;
  const selectedPaymentInvoice =
    payableInvoices.find((invoice) => String(invoice.id) === paymentInvoiceId) ?? null;
  const selectedApprovalInvoice =
    submittedInvoices.find((invoice) => String(invoice.id) === approvalInvoiceId) ?? null;
  const selectedPaymentBalance = selectedPaymentInvoice ? moneyValue(selectedPaymentInvoice.balance) : 0;
  const paymentAmount = Number(amount);
  const paymentAmountInvalid =
    !amount.trim()
    || !Number.isFinite(paymentAmount)
    || paymentAmount <= 0
    || paymentAmount > selectedPaymentBalance;
  const referenceMissing = method !== "cash" && !reference.trim();

  useEffect(() => {
    if (
      !selectedPaymentInvoice
      || selectedPaymentInvoice.hold_expired
      || selectedPaymentInvoice.hold_hours_left === null
      || selectedPaymentInvoice.hold_hours_left > 6
      || peekFlashMessage() !== null
      || warnedHoldInvoicesRef.current.has(selectedPaymentInvoice.id)
    ) {
      return;
    }
    warnedHoldInvoicesRef.current.add(selectedPaymentInvoice.id);
    storePassiveFlashMessage({
      tone: "warning",
      message: `Bed hold expires in ${selectedPaymentInvoice.hold_hours_left}h for ${selectedPaymentInvoice.invoice_no}. Collect or reassign promptly.`,
    });
  }, [selectedPaymentInvoice]);

  async function runAction(path: string, payload: object, confirmation: string, redirectTo?: string) {
    if (!(await confirmAction(confirmation))) {
      return;
    }
    setPending(true);
    setError(null);
    setMessage(null);
    try {
      const result = await postAction(path, payload);
      setMessage(result.message);
      storeFlashMessage({
        tone: result.warning_message ? "warning" : "success",
        message: result.warning_message ?? result.message,
      });
      if (redirectTo) {
        window.location.assign(redirectTo);
      } else if (result.receipt_id) {
        window.location.assign(`/billing?receiptId=${result.receipt_id}&invoiceId=${result.invoice_id ?? ""}`);
      } else if (result.invoice_id) {
        window.location.assign(`/billing?invoiceId=${result.invoice_id}`);
      } else {
        window.location.reload();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="panel">
      <h3>Billing actions</h3>
      <div className="stack">
        <details className="action-disclosure">
          <summary className="action-summary">Create invoice</summary>
          <div className="action-card action-card-embedded">
            <div className="stack tight">
            <label className="field">
              <span>Tenant</span>
              <select value={tenantId} onChange={(event) => setTenantId(event.target.value)}>
                {tenants.map((tenant) => (
                  <option key={tenant.id} value={tenant.id}>
                    {tenant.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Bed</span>
              <select value={bedId} onChange={(event) => setBedId(event.target.value)}>
                {availableBeds.map((bed) => (
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
                <span>Submit now</span>
                <select value={submitNow ? "yes" : "no"} onChange={(event) => setSubmitNow(event.target.value === "yes")}>
                  <option value="yes">{autoApproveInvoices ? "Approve immediately" : "Send to approval queue"}</option>
                  <option value="no">Save as draft</option>
                </select>
              </label>
            </div>
            <label className="field">
              <span>Notes</span>
              <input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Optional billing note" />
            </label>
            <button
              className="button"
              disabled={pending || !tenantId || !bedId}
              onClick={() =>
                runAction(
                  "/invoices",
                  {
                    tenant_id: Number(tenantId),
                    reserved_bed_id: Number(bedId),
                    tax: Number(tax || "0"),
                    discount: Number(discount || "0"),
                    hold_hours: Number(holdHours || defaultHoldHours),
                    due_at: dueAt || null,
                    notes,
                    submit_now: submitNow,
                  },
                  buildConfirmationMessage("Create this invoice?", [
                    selectedTenant ? `Tenant: ${selectedTenant.name}` : null,
                    selectedBed ? `Bed: ${selectedBed.label}` : null,
                    `Due date: ${dueAt || "Not set"}`,
                    `Flow: ${submitNow ? (autoApproveInvoices ? "Approve immediately" : "Send to approval queue") : "Save as draft"}`,
                    notes.trim() ? `Note: ${notes.trim()}` : null,
                  ]),
                )
              }
            >
              Create invoice
            </button>
          </div>
          </div>
        </details>

        <div className="action-card">
          <h4>Receive payment</h4>
          <div className="stack tight">
            <label className="field">
              <span>Invoice</span>
              <select value={paymentInvoiceId} onChange={(event) => setPaymentInvoiceId(event.target.value)}>
                {payableInvoices.map((invoice) => (
                  <option key={invoice.id} value={invoice.id}>
                    {invoice.invoice_no} | {invoice.tenant_name} | {invoice.balance}
                  </option>
                ))}
              </select>
            </label>
            <div className="inline-actions">
              <label className="field">
                <span>Amount</span>
                <input value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal" placeholder="0.00" />
              </label>
              <label className="field">
                <span>Method</span>
                <select value={method} onChange={(event) => setMethod(event.target.value)}>
                  <option value="cash">cash</option>
                  <option value="card">card</option>
                  <option value="bank_transfer">bank_transfer</option>
                  <option value="mobile_money">mobile_money</option>
                  <option value="check">check</option>
                </select>
              </label>
            </div>
            <label className="field">
              <span>Reference</span>
              <input
                value={reference}
                onChange={(event) => setReference(event.target.value)}
                placeholder={method === "cash" ? "Optional for cash" : "Required for non-cash"}
              />
            </label>
            <p className="section-note">
              {blockDuplicatePaymentReference
                ? "Duplicate payment references are blocked in this environment."
                : "Duplicate payment references will warn but not block."}
            </p>
            {selectedPaymentInvoice ? (
              <p className="section-note">
                Selected invoice: {selectedPaymentInvoice.invoice_no} for {selectedPaymentInvoice.tenant_name} with balance {selectedPaymentInvoice.balance} and paid so far {selectedPaymentInvoice.paid_total}.
                {selectedPaymentInvoice.hold_expired
                  ? " Hold expired."
                  : selectedPaymentInvoice.hold_hours_left !== null && selectedPaymentInvoice.hold_expires_at
                    ? ` Hold has ${selectedPaymentInvoice.hold_hours_left}h left and expires ${selectedPaymentInvoice.hold_expires_at}.`
                    : ""}
              </p>
            ) : null}
            {selectedPaymentInvoice ? (
              <div className="inline-actions">
                <button
                  className="button ghost small"
                  disabled={pending}
                  onClick={() => setAmount(selectedPaymentBalance.toFixed(2))}
                  type="button"
                >
                  Use remaining balance
                </button>
                <span className="small">Remaining balance: {selectedPaymentInvoice.balance}</span>
              </div>
            ) : null}
            {paymentAmount > selectedPaymentBalance && selectedPaymentInvoice ? (
              <p className="error-text">
                Amount exceeds the remaining balance of {selectedPaymentInvoice.balance}. Overpayment is blocked.
              </p>
            ) : null}
            {referenceMissing ? (
              <p className="error-text">Reference is required for non-cash payments.</p>
            ) : null}
            {selectedPaymentInvoice?.hold_expired ? (
              <p className="section-note">
                The original bed hold expired. Select a new bed before recording payment or allocation.
              </p>
            ) : null}
            <button
              className="button success"
              disabled={
                pending
                || !paymentInvoiceId
                || paymentAmountInvalid
                || referenceMissing
                || Boolean(selectedPaymentInvoice?.hold_expired)
              }
              onClick={() =>
                runAction(
                  `/invoices/${paymentInvoiceId}/payments`,
                  {
                    amount: Number(amount),
                    method,
                    reference,
                  },
                  buildConfirmationMessage("Record this payment?", [
                    selectedPaymentInvoice ? `Invoice: ${selectedPaymentInvoice.invoice_no}` : null,
                    selectedPaymentInvoice ? `Tenant: ${selectedPaymentInvoice.tenant_name}` : null,
                    `Amount: ${amount}`,
                    `Method: ${method}`,
                    reference.trim() ? `Reference: ${reference.trim()}` : null,
                  ]),
                )
              }
            >
              Record payment
            </button>
          </div>
        </div>

        {user.is_admin && !autoApproveInvoices ? (
          <details className="action-disclosure" open={submittedInvoices.length > 0}>
            <summary className="action-summary">
              Approval queue
              {submittedInvoices.length ? ` (${submittedInvoices.length})` : ""}
            </summary>
            <div className="action-card action-card-embedded">
              {submittedInvoices.length ? (
                <div className="stack tight">
                <label className="field">
                  <span>Submitted invoice</span>
                  <select value={approvalInvoiceId} onChange={(event) => setApprovalInvoiceId(event.target.value)}>
                    {submittedInvoices.map((invoice) => (
                      <option key={invoice.id} value={invoice.id}>
                        {invoice.invoice_no} | {invoice.tenant_name}{invoice.hold_expired ? " | hold expired" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                {selectedApprovalInvoice?.hold_expired ? (
                  <p className="section-note">
                    This invoice no longer has an active bed hold. Open the invoice, choose a new bed, then approve it.
                  </p>
                ) : null}
                <label className="field">
                  <span>Rejection note</span>
                  <input
                    value={rejectionReason}
                    onChange={(event) => setRejectionReason(event.target.value)}
                    placeholder="Optional rejection reason"
                  />
                </label>
                <div className="inline-actions">
                  <button
                    className="button success"
                    disabled={pending || !approvalInvoiceId || Boolean(selectedApprovalInvoice?.hold_expired)}
                    onClick={() =>
                      runAction(
                        `/invoices/${approvalInvoiceId}/approve`,
                        {},
                        buildConfirmationMessage("Approve this invoice?", [
                          selectedApprovalInvoice ? `Invoice: ${selectedApprovalInvoice.invoice_no}` : null,
                          selectedApprovalInvoice ? `Tenant: ${selectedApprovalInvoice.tenant_name}` : null,
                        ]),
                      )
                    }
                  >
                    Approve invoice
                  </button>
                  <button
                    className="button danger"
                    disabled={pending || !approvalInvoiceId}
                    onClick={() =>
                      runAction(
                        `/invoices/${approvalInvoiceId}/reject`,
                        {
                          reason: rejectionReason,
                        },
                        buildConfirmationMessage("Reject this invoice?", [
                          selectedApprovalInvoice ? `Invoice: ${selectedApprovalInvoice.invoice_no}` : null,
                          selectedApprovalInvoice ? `Tenant: ${selectedApprovalInvoice.tenant_name}` : null,
                          rejectionReason.trim() ? `Reason: ${rejectionReason.trim()}` : "No rejection note entered.",
                        ]),
                      )
                    }
                  >
                    Reject invoice
                  </button>
                </div>
                </div>
              ) : (
                <p className="section-note">No submitted invoices are waiting for review.</p>
              )}
            </div>
          </details>
        ) : user.is_admin && autoApproveInvoices ? (
          <div className="action-card">
            <h4>Approval queue</h4>
            <p className="section-note">Invoices are auto-approved on submit. Switch the setting off to restore manual approval.</p>
          </div>
        ) : null}

        {message ? <p className="success-text">{message}</p> : null}
        {error ? <p className="error-text">{error}</p> : null}
      </div>
    </section>
  );
}
