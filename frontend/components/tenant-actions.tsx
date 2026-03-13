"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { TenantListItem } from "../lib/api";
import {
  buildConfirmationMessage,
  confirmAction,
  storeFlashMessage,
} from "../lib/action-feedback";
import { postAction } from "../lib/client-api";

type Props = {
  tenant?: TenantListItem | null;
  defaultStatus?: string;
  title?: string;
  compact?: boolean;
};

export function TenantActions({
  tenant = null,
  defaultStatus = "prospect",
  title,
  compact = false,
}: Props) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState(tenant?.name ?? "");
  const [email, setEmail] = useState(tenant?.email ?? "");
  const [phone, setPhone] = useState(tenant?.phone ?? "");
  const [status, setStatus] = useState(tenant?.status ?? defaultStatus);
  const [room, setRoom] = useState(tenant?.room ?? "");

  async function submit() {
    const confirmation = buildConfirmationMessage(
      tenant ? "Save tenant profile changes?" : "Create this tenant record?",
      [
        `Name: ${name.trim()}`,
        `Status: ${status}`,
        room.trim() ? `Room note: ${room.trim()}` : null,
      ],
    );
    if (!(await confirmAction(confirmation))) {
      return;
    }
    setPending(true);
    setError(null);
    setMessage(null);
    try {
      const result = await postAction(
        tenant ? `/tenants/${tenant.id}` : "/tenants",
        {
          name,
          email,
          phone,
          status,
          room,
        },
      );
      setMessage(result.message);
      storeFlashMessage({ tone: "success", message: result.message });
      if (!tenant && result.tenant_id) {
        window.location.assign(`/tenants/${result.tenant_id}`);
        return;
      }
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tenant action failed.");
    } finally {
      setPending(false);
    }
  }

  async function archiveTenant() {
    if (!tenant) return;
    if (
      !(await confirmAction(
        buildConfirmationMessage("Archive this tenant?", [
          `Tenant: ${tenant.name}`,
          "The tenant record stays in history but will be marked archived.",
        ]),
      ))
    ) {
      return;
    }
    setPending(true);
    setError(null);
    setMessage(null);
    try {
      const result = await postAction(`/tenants/${tenant.id}/archive`, {});
      setMessage(result.message);
      storeFlashMessage({ tone: "success", message: result.message });
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Archive failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="panel">
      <h3>{title ?? (tenant ? "Tenant profile" : "Create tenant")}</h3>
      <div className="stack">
        <div className="action-card">
          <div className="stack tight">
            <label className="field">
              <span>Name</span>
              <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Resident name" />
            </label>
            <div className={compact ? "stack tight" : "inline-actions"}>
              <label className="field">
                <span>Email</span>
                <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@example.com" />
              </label>
              <label className="field">
                <span>Phone</span>
                <input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="233XXXXXXXXX" />
              </label>
            </div>
            <div className={compact ? "stack tight" : "inline-actions"}>
              <label className="field">
                <span>Status</span>
                <select value={status} onChange={(event) => setStatus(event.target.value)}>
                  <option value="prospect">Prospect</option>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
              </label>
              <label className="field">
                <span>Room / note</span>
                <input value={room} onChange={(event) => setRoom(event.target.value)} placeholder="Optional room note" />
              </label>
            </div>
            <div className="inline-actions">
              <button className="button" disabled={pending || !name.trim()} onClick={submit} type="button">
                {tenant ? "Save tenant" : "Create tenant"}
              </button>
              {tenant ? (
                <button className="button danger" disabled={pending} onClick={archiveTenant} type="button">
                  Archive tenant
                </button>
              ) : null}
            </div>
          </div>
        </div>
        {message ? <p className="success-text">{message}</p> : null}
        {error ? <p className="error-text">{error}</p> : null}
      </div>
    </section>
  );
}
