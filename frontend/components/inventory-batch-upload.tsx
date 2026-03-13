"use client";

import { useRef, useState } from "react";

import {
  buildConfirmationMessage,
  confirmAction,
  storeFlashMessage,
} from "../lib/action-feedback";
import { postFormData } from "../lib/client-api";

export function InventoryBatchUpload() {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function uploadFile() {
    const file = inputRef.current?.files?.[0];
    if (!file) {
      setError("Select a CSV or Excel file first.");
      setMessage(null);
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    if (
      !(await confirmAction(
        buildConfirmationMessage("Upload this inventory file?", [
          `File: ${file.name}`,
          "Existing room, floor, and bed records may be updated.",
        ]),
      ))
    ) {
      return;
    }
    setPending(true);
    setError(null);
    setMessage(null);
    try {
      const result = await postFormData("/inventory/upload", formData);
      setMessage(result.message);
      storeFlashMessage({ tone: "success", message: result.message });
      window.location.assign("/inventory");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="panel">
      <h3>Batch upload</h3>
      <div className="stack">
        <div className="action-card">
          <h4>Inventory file</h4>
          <div className="stack tight">
            <input ref={inputRef} accept=".csv,.xlsx,.xls" type="file" />
            <span className="small">Accepted formats: .csv, .xlsx, .xls</span>
            <button
              className="button"
              disabled={pending}
              onClick={uploadFile}
              type="button"
            >
              Upload inventory
            </button>
          </div>
        </div>
        {message ? <p className="success-text">{message}</p> : null}
        {error ? <p className="error-text">{error}</p> : null}
      </div>
    </section>
  );
}
