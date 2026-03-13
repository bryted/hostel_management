"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  buildConfirmationMessage,
  confirmAction,
  storeFlashMessage,
} from "../lib/action-feedback";
import { postAction } from "../lib/client-api";

type Props = {
  receiptId: number;
  canSendSms: boolean;
  smsRecipient: string | null;
  canSendEmail: boolean;
  emailRecipient: string | null;
  canSendWhatsApp: boolean;
  whatsAppRecipient: string | null;
  verificationUrl: string;
};

export function ReceiptActions({
  receiptId,
  canSendSms,
  smsRecipient,
  canSendEmail,
  emailRecipient,
  canSendWhatsApp,
  whatsAppRecipient,
  verificationUrl,
}: Props) {
  const router = useRouter();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function runAction(path: string, confirmation: string) {
    if (!(await confirmAction(confirmation))) {
      return;
    }
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const result = await postAction(path, {});
      setMessage(result.message);
      storeFlashMessage({ tone: "success", message: result.message });
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Receipt action failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="stack tight">
      <div className="inline-actions">
        <a
          className="button ghost"
          href={`/api/proxy/receipts/${receiptId}/pdf`}
          target="_blank"
          rel="noreferrer"
        >
          Open PDF
        </a>
        <button
          className="button"
          disabled={pending}
          onClick={() =>
            runAction(
              `/receipts/${receiptId}/print`,
              buildConfirmationMessage("Mark this receipt as printed?", [`Receipt ID: ${receiptId}`]),
            )
          }
        >
          Mark printed
        </button>
        <a className="button ghost" href={verificationUrl} target="_blank" rel="noreferrer">
          Verify
        </a>
        <button
          className="button secondary"
          disabled={pending || !canSendSms}
          onClick={() =>
            runAction(
              `/receipts/${receiptId}/send-sms`,
              buildConfirmationMessage("Send this receipt by SMS?", [
                `Receipt ID: ${receiptId}`,
                smsRecipient ? `Recipient: ${smsRecipient}` : null,
              ]),
            )
          }
        >
          {canSendSms ? `Send SMS${smsRecipient ? ` to ${smsRecipient}` : ""}` : "SMS unavailable"}
        </button>
        <button
          className="button secondary"
          disabled={pending || !canSendEmail}
          onClick={() =>
            runAction(
              `/receipts/${receiptId}/send-email`,
              buildConfirmationMessage("Send this receipt by email?", [
                `Receipt ID: ${receiptId}`,
                emailRecipient ? `Recipient: ${emailRecipient}` : null,
              ]),
            )
          }
        >
          {canSendEmail ? `Send email${emailRecipient ? ` to ${emailRecipient}` : ""}` : "Email unavailable"}
        </button>
        <button
          className="button secondary"
          disabled={pending || !canSendWhatsApp}
          onClick={() =>
            runAction(
              `/receipts/${receiptId}/send-whatsapp`,
              buildConfirmationMessage("Send this receipt by WhatsApp?", [
                `Receipt ID: ${receiptId}`,
                whatsAppRecipient ? `Recipient: ${whatsAppRecipient}` : null,
              ]),
            )
          }
        >
          {canSendWhatsApp ? `Send WhatsApp${whatsAppRecipient ? ` to ${whatsAppRecipient}` : ""}` : "WhatsApp unavailable"}
        </button>
      </div>
      {message ? <p className="success-text">{message}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}
    </div>
  );
}
