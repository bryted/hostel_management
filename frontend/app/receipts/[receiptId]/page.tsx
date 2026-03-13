import Link from "next/link";
import { notFound } from "next/navigation";

import { DataPanel, PageIntro, StatusPill } from "../../../components/page-shell";
import { ReceiptActions } from "../../../components/receipt-actions";
import { fetchReceiptDetail, requireUser } from "../../../lib/server-api";

type PageProps = {
  params: Promise<{ receiptId: string }>;
};

export default async function ReceiptDetailPage({ params }: PageProps) {
  await requireUser();
  const { receiptId } = await params;
  const parsedReceiptId = Number(receiptId);
  if (Number.isNaN(parsedReceiptId)) notFound();

  const detail = await fetchReceiptDetail(parsedReceiptId);

  return (
    <div className="grid">
      <PageIntro
        title={detail.receipt.receipt_no}
        description={detail.tenant.name}
        actions={
          <>
            <Link className="button ghost" href={`/tenants/${detail.tenant.id}`}>
              Tenant workspace
            </Link>
            <Link className="button" href={`/billing?receiptId=${detail.receipt.id}${detail.invoice ? `&invoiceId=${detail.invoice.id}` : ""}`}>
              Billing desk
            </Link>
          </>
        }
        aside={<StatusPill tone="accent">Verified receipt</StatusPill>}
      />

      <div className="grid two">
        <DataPanel title="Receipt detail">
          <div className="meta-list">
            <div className="meta-row">
              <span>Amount</span>
              <strong>{detail.receipt.amount}</strong>
            </div>
            <div className="meta-row">
              <span>Issued</span>
              <strong>{detail.receipt.issued_at ?? "-"}</strong>
            </div>
            <div className="meta-row">
              <span>Payment</span>
              <strong>{detail.payment?.payment_no ?? "-"}</strong>
            </div>
            <div className="meta-row">
              <span>Invoice</span>
              <strong>{detail.invoice?.invoice_no ?? "-"}</strong>
            </div>
            <div className="meta-row">
              <span>Printed count</span>
              <strong>{detail.receipt.printed_count}</strong>
            </div>
          </div>
        </DataPanel>
        <DataPanel title="Security">
          <div className="receipt-security">
            <div className="meta-list">
              <div className="meta-row">
                <span>Security code</span>
                <span className="security-code">{detail.verification_code}</span>
              </div>
              <div className="meta-row">
                <span>SMS delivery</span>
                <strong>{detail.sms_available ? detail.sms_recipient ?? "Ready" : "Not configured"}</strong>
              </div>
              <div className="meta-row">
                <span>Received by</span>
                <strong>{detail.received_by ?? "-"}</strong>
              </div>
              <div className="meta-row">
                <span>Balance after</span>
                <strong>{detail.balance_after ?? "-"}</strong>
              </div>
            </div>
          </div>
          <ReceiptActions
            receiptId={detail.receipt.id}
            canSendSms={detail.sms_available}
            smsRecipient={detail.sms_recipient}
            canSendEmail={detail.email_available}
            emailRecipient={detail.email_recipient}
            canSendWhatsApp={detail.whatsapp_available}
            whatsAppRecipient={detail.whatsapp_recipient}
            verificationUrl={detail.verification_url}
          />
        </DataPanel>
      </div>
    </div>
  );
}
