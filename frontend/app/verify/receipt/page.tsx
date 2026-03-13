import Link from "next/link";

import type { ReceiptVerification } from "../../../lib/api";
import { getServerApiBaseUrl } from "../../../lib/api";

type PageProps = {
  searchParams: Promise<{
    receipt?: string;
    code?: string;
  }>;
};

async function fetchVerification(receipt: string, code: string): Promise<ReceiptVerification | null> {
  const params = new URLSearchParams({ receipt_no: receipt, code });
  const response = await fetch(`${getServerApiBaseUrl()}/receipts/verify?${params.toString()}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    return null;
  }
  return (await response.json()) as ReceiptVerification;
}

export default async function ReceiptVerificationPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const receipt = params.receipt?.trim() ?? "";
  const code = params.code?.trim() ?? "";
  const verification = receipt && code ? await fetchVerification(receipt, code) : null;

  return (
    <div className="login-shell">
      <section className="panel narrow auth-card">
        <div className="auth-copy">
          <h1>Receipt verification</h1>
          <p>{verification?.valid ? "Receipt verified." : "Verification could not be confirmed."}</p>
        </div>
        {verification?.valid ? (
          <div className="stack tight">
            <div className="metric compact">
              <span>Receipt</span>
              <strong>{verification.receipt_no}</strong>
            </div>
            <div className="meta-list">
              <div className="meta-row">
                <span>Tenant</span>
                <strong>{verification.tenant_name}</strong>
              </div>
              <div className="meta-row">
                <span>Amount</span>
                <strong>{verification.amount}</strong>
              </div>
              <div className="meta-row">
                <span>Issued</span>
                <strong>{verification.issued_at}</strong>
              </div>
              <div className="meta-row">
                <span>Payment</span>
                <strong>{verification.payment_no ?? "-"}</strong>
              </div>
              <div className="meta-row">
                <span>Invoice</span>
                <strong>{verification.invoice_no ?? "-"}</strong>
              </div>
            </div>
          </div>
        ) : (
          <p className="section-note">
            Check the receipt number and security code, or request a fresh copy from the hostel desk.
          </p>
        )}
        <div className="inline-actions">
          <Link className="button ghost" href="/login">
            Open portal
          </Link>
        </div>
      </section>
    </div>
  );
}
