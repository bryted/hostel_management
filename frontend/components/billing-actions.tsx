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

const PAYMENT_METHOD_OPTIONS = [
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
  { value: "bank_transfer", label: "Bank transfer" },
  { value: "mobile_money", label: "Mobile money" },
  { value: "check", label: "Check" },
];

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

  const [paymentTenantId, setPaymentTenantId] = useState(
    payableInvoices[0] ? String(payableInvoices[0].tenant_id) : (tenants[0] ? String(tenants[0].id) : ""),
  );
  const [allocations, setAllocations] = useState<Array<{ invoiceId: string; amount: string }>>(
    payableInvoices[0] ? [{ invoiceId: String(payableInvoices[0].id), amount: "" }] : [],
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
  const payableInvoiceCountByTenant = new Map<string, number>();
  for (const invoice of payableInvoices) {
    const key = String(invoice.tenant_id);
    payableInvoiceCountByTenant.set(key, (payableInvoiceCountByTenant.get(key) ?? 0) + 1);
  }
  const paymentTenantOptions = tenants.filter((tenant) =>
    payableInvoices.some((invoice) => String(invoice.tenant_id) === String(tenant.id)),
  );
  const selectedPaymentTenant = tenants.find((tenant) => String(tenant.id) === paymentTenantId) ?? null;
  const tenantPayableInvoices = payableInvoices.filter(
    (invoice) => String(invoice.tenant_id) === paymentTenantId,
  );
  const selectedAllocationInvoiceIds = new Set(
    allocations.map((allocation) => allocation.invoiceId).filter(Boolean),
  );
  const selectedApprovalInvoice =
    submittedInvoices.find((invoice) => String(invoice.id) === approvalInvoiceId) ?? null;
  const paymentAmount = Number(amount);
  const allocationTotal = allocations.reduce(
    (sum, allocation) => sum + (Number(allocation.amount || "0") || 0),
    0,
  );
  const remainingToAllocate = Number.isFinite(paymentAmount) ? paymentAmount - allocationTotal : 0;
  const paymentAmountInvalid = !amount.trim() || !Number.isFinite(paymentAmount) || paymentAmount <= 0;
  const referenceMissing = method !== "cash" && !reference.trim();
  const allocationInvalid =
    allocations.some((allocation) => {
      const invoice = tenantPayableInvoices.find((item) => String(item.id) === allocation.invoiceId);
      const allocationAmount = Number(allocation.amount || "0");
      return (
        !allocation.invoiceId
        || !invoice
        || !Number.isFinite(allocationAmount)
        || allocationAmount <= 0
        || allocationAmount > moneyValue(invoice.balance)
      );
    })
    || allocationTotal > paymentAmount
    || allocations.length === 0;

  useEffect(() => {
    if (!paymentTenantOptions.length) {
      if (paymentTenantId) {
        setPaymentTenantId("");
      }
      if (allocations.length) {
        setAllocations([]);
      }
      return;
    }
    if (!paymentTenantOptions.some((tenant) => String(tenant.id) === paymentTenantId)) {
      const nextTenantId = String(paymentTenantOptions[0].id);
      setPaymentTenantId(nextTenantId);
      const nextInvoices = payableInvoices.filter((invoice) => String(invoice.tenant_id) === nextTenantId);
      setAllocations(nextInvoices[0] ? [{ invoiceId: String(nextInvoices[0].id), amount: "" }] : []);
    }
  }, [allocations.length, payableInvoices, paymentTenantId, paymentTenantOptions]);

  useEffect(() => {
    for (const invoice of tenantPayableInvoices) {
      if (
        invoice.hold_expired
        || invoice.hold_hours_left === null
        || invoice.hold_hours_left > 6
        || peekFlashMessage() !== null
        || warnedHoldInvoicesRef.current.has(invoice.id)
      ) {
        continue;
      }
      warnedHoldInvoicesRef.current.add(invoice.id);
      storePassiveFlashMessage({
        tone: "warning",
        message: `Bed hold expires in ${invoice.hold_hours_left}h for ${invoice.invoice_no}. Collect or reassign promptly.`,
      });
    }
  }, [tenantPayableInvoices]);

  function invoiceOptionsForAllocation(index: number): BillingInvoiceItem[] {
    return tenantPayableInvoices.filter((invoice) => {
      const invoiceId = String(invoice.id);
      return (
        invoiceId === allocations[index]?.invoiceId ||
        !allocations.some((allocation, allocationIndex) => allocationIndex !== index && allocation.invoiceId === invoiceId)
      );
    });
  }

  function nextUnselectedInvoiceId(): string {
    const candidate = tenantPayableInvoices.find(
      (invoice) => !selectedAllocationInvoiceIds.has(String(invoice.id)),
    );
    return candidate ? String(candidate.id) : "";
  }

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
    <section className="panel workspace-panel secondary">
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
                    {tenant.name} | {tenant.status}
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
              <span>Tenant</span>
              <select
                value={paymentTenantId}
                disabled={pending || !paymentTenantOptions.length}
                onChange={(event) => {
                  const nextTenantId = event.target.value;
                  setPaymentTenantId(nextTenantId);
                  const nextInvoices = payableInvoices.filter(
                    (invoice) => String(invoice.tenant_id) === nextTenantId,
                  );
                  setAllocations(
                    nextInvoices[0] ? [{ invoiceId: String(nextInvoices[0].id), amount: "" }] : [],
                  );
                }}
              >
                {paymentTenantOptions.map((tenant) => (
                  <option key={tenant.id} value={tenant.id}>
                    {tenant.name} | {payableInvoiceCountByTenant.get(String(tenant.id)) ?? 0} open invoice(s)
                  </option>
                ))}
              </select>
            </label>
            <div className="inline-actions">
              <label className="field">
                <span>Total payment</span>
                <input value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal" placeholder="0.00" />
              </label>
              <label className="field">
                <span>Method</span>
                <select value={method} onChange={(event) => setMethod(event.target.value)}>
                  {PAYMENT_METHOD_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
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
            <div className="stack tight">
              <div className="meta-row">
                <span>Allocations</span>
                <div className="inline-actions">
                  <button
                    className="button ghost small"
                    disabled={pending || !tenantPayableInvoices.length || !nextUnselectedInvoiceId()}
                    onClick={() =>
                      setAllocations((current) => [
                        ...current,
                        { invoiceId: nextUnselectedInvoiceId(), amount: "" },
                      ])
                    }
                    type="button"
                  >
                    Add invoice
                  </button>
                  <button
                    className="button ghost small"
                    disabled={pending || !Number.isFinite(remainingToAllocate) || allocations.length === 0}
                    onClick={() =>
                      setAllocations((current) =>
                        current.map((allocation, index) =>
                          index === current.length - 1
                            ? {
                                ...allocation,
                                amount: remainingToAllocate > 0 ? remainingToAllocate.toFixed(2) : allocation.amount,
                              }
                            : allocation,
                        ),
                      )
                    }
                    type="button"
                  >
                    Use remaining
                  </button>
                </div>
              </div>
              {allocations.length ? (
                allocations.map((allocation, index) => {
                  const invoiceOptions = invoiceOptionsForAllocation(index);
                  const selectedInvoice = tenantPayableInvoices.find((invoice) => String(invoice.id) === allocation.invoiceId);
                  return (
                    <div key={`${allocation.invoiceId}-${index}`} className="inline-actions">
                      <label className="field grow">
                        <span>Invoice {index + 1}</span>
                        <select
                          value={allocation.invoiceId}
                          disabled={!invoiceOptions.length}
                          onChange={(event) =>
                            setAllocations((current) =>
                              current.map((item, itemIndex) =>
                                itemIndex === index ? { ...item, invoiceId: event.target.value } : item,
                              ),
                            )
                          }
                        >
                          {invoiceOptions.map((invoice) => (
                            <option key={invoice.id} value={invoice.id}>
                              {invoice.invoice_no} | {invoice.balance} | {invoice.academic_year ?? "-"}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="field">
                        <span>Allocated amount</span>
                        <input
                          value={allocation.amount}
                          onChange={(event) =>
                            setAllocations((current) =>
                              current.map((item, itemIndex) =>
                                itemIndex === index ? { ...item, amount: event.target.value } : item,
                              ),
                            )
                          }
                          inputMode="decimal"
                          placeholder="0.00"
                        />
                      </label>
                      <button
                        className="button ghost small"
                        disabled={pending || allocations.length <= 1}
                        onClick={() =>
                          setAllocations((current) => current.filter((_, itemIndex) => itemIndex !== index))
                        }
                        type="button"
                      >
                        Remove
                      </button>
                      <span className="small">
                        {selectedInvoice
                          ? `${selectedInvoice.balance} remaining | ${selectedInvoice.hold_expired ? "hold expired" : selectedInvoice.hold_hours_left !== null ? `${selectedInvoice.hold_hours_left}h left` : "hold active"}`
                          : "Select an invoice"}
                      </span>
                    </div>
                  );
                })
              ) : (
                <p className="section-note">
                  {paymentTenantOptions.length
                    ? "No payable invoices remain for the selected tenant."
                    : "No tenants currently have invoices ready for payment collection."}
                </p>
              )}
            </div>
            <p className="section-note">
              {blockDuplicatePaymentReference
                ? "Duplicate payment references are blocked in this environment."
                : "Duplicate payment references will warn but not block."}
            </p>
            <div className="meta-list">
              <div className="meta-row">
                <span>Tenant</span>
                <strong>{selectedPaymentTenant?.name ?? "-"}</strong>
              </div>
              <div className="meta-row">
                <span>Total payment</span>
                <strong>{amount || "0.00"}</strong>
              </div>
              <div className="meta-row">
                <span>Allocated</span>
                <strong>{allocationTotal.toFixed(2)}</strong>
              </div>
              <div className="meta-row">
                <span>Unallocated</span>
                <strong>{Number.isFinite(remainingToAllocate) ? remainingToAllocate.toFixed(2) : "-"}</strong>
              </div>
            </div>
            {allocationInvalid && tenantPayableInvoices.length ? (
              <p className="error-text">Each split must use a valid invoice and amount, and total allocations cannot exceed the payment amount.</p>
            ) : null}
            {referenceMissing ? (
              <p className="error-text">Reference is required for non-cash payments.</p>
            ) : null}
            <button
              className="button success"
              disabled={pending || !paymentTenantId || paymentAmountInvalid || referenceMissing || allocationInvalid}
              onClick={() =>
                runAction(
                  "/billing/payments",
                  {
                    tenant_id: Number(paymentTenantId),
                    amount: Number(amount),
                    method,
                    reference,
                    allocations: allocations.map((allocation) => ({
                      invoice_id: Number(allocation.invoiceId),
                      amount: Number(allocation.amount),
                    })),
                  },
                  buildConfirmationMessage("Record this payment?", [
                    selectedPaymentTenant ? `Tenant: ${selectedPaymentTenant.name}` : null,
                    `Amount: ${amount}`,
                    `Method: ${method}`,
                    `Allocated: ${allocationTotal.toFixed(2)}`,
                    `Unallocated: ${Number.isFinite(remainingToAllocate) ? remainingToAllocate.toFixed(2) : "-"}`,
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
