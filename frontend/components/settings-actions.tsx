"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import type { SettingsOverview, UserListItem } from "../lib/api";
import {
  buildConfirmationMessage,
  confirmAction,
  storeFlashMessage,
} from "../lib/action-feedback";
import { postAction } from "../lib/client-api";
import { StatusPill } from "./page-shell";

type Props = {
  overview: SettingsOverview;
};

function UserRowActions({
  user,
  onAction,
  pending,
}: {
  user: UserListItem;
  onAction: (
    path: string,
    payload: object,
    shouldRefresh?: boolean,
    confirmation?: string,
  ) => Promise<void>;
  pending: boolean;
}) {
  return (
    <div className="inline-actions">
      <button
        className="button ghost small"
        disabled={pending}
        onClick={() =>
          onAction(
            `/settings/users/${user.id}`,
            { is_active: !user.is_active },
            true,
            buildConfirmationMessage(
              user.is_active ? "Disable this account?" : "Enable this account?",
              [`User: ${user.full_name}`, `Email: ${user.email}`],
            ),
          )
        }
        type="button"
      >
        {user.is_active ? "Disable" : "Enable"}
      </button>
      <button
        className="button ghost small"
        disabled={pending}
        onClick={() =>
          onAction(
            `/settings/users/${user.id}`,
            { is_admin: !user.is_admin },
            true,
            buildConfirmationMessage(
              user.is_admin ? "Make this user a cashier?" : "Promote this user to admin?",
              [`User: ${user.full_name}`, `Email: ${user.email}`],
            ),
          )
        }
        type="button"
      >
        {user.is_admin ? "Make cashier" : "Make admin"}
      </button>
    </div>
  );
}

export function SettingsActions({ overview }: Props) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [blockDuplicate, setBlockDuplicate] = useState(
    overview.settings.block_duplicate_payment_reference,
  );
  const [maxAttempts, setMaxAttempts] = useState(
    String(overview.settings.notification_max_attempts),
  );
  const [retryDelay, setRetryDelay] = useState(
    String(overview.settings.notification_retry_delay_seconds),
  );
  const [holdHours, setHoldHours] = useState(
    String(overview.settings.reservation_default_hold_hours),
  );
  const [autoApproveInvoices, setAutoApproveInvoices] = useState(
    overview.settings.auto_approve_invoices,
  );

  const [mockMode, setMockMode] = useState(overview.settings.mock_mode);
  const [smsApiUrl, setSmsApiUrl] = useState(overview.settings.sms_api_url);
  const [smsApiKey, setSmsApiKey] = useState("");
  const [smsSenderId, setSmsSenderId] = useState(overview.settings.sms_sender_id);
  const [smtpHost, setSmtpHost] = useState(overview.settings.smtp_host);
  const [smtpPort, setSmtpPort] = useState(
    overview.settings.smtp_port ? String(overview.settings.smtp_port) : "",
  );
  const [smtpUser, setSmtpUser] = useState(overview.settings.smtp_user);
  const [smtpPassword, setSmtpPassword] = useState("");
  const [smtpFrom, setSmtpFrom] = useState(overview.settings.smtp_from);
  const [whatsAppToken, setWhatsAppToken] = useState("");
  const [whatsAppPhoneId, setWhatsAppPhoneId] = useState(
    overview.settings.whatsapp_phone_number_id,
  );
  const [whatsAppVersion, setWhatsAppVersion] = useState(
    overview.settings.whatsapp_api_version || "v18.0",
  );
  const [smsTestRecipient, setSmsTestRecipient] = useState("");
  const [emailTestRecipient, setEmailTestRecipient] = useState("");
  const [whatsAppTestRecipient, setWhatsAppTestRecipient] = useState("");

  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("cashier");

  const resetCandidates = useMemo(
    () => overview.users.filter((account) => account.is_active),
    [overview.users],
  );
  const [resetUserId, setResetUserId] = useState(
    resetCandidates[0] ? String(resetCandidates[0].id) : "",
  );
  const selectedResetUser = useMemo(
    () => resetCandidates.find((account) => String(account.id) === resetUserId) ?? null,
    [resetCandidates, resetUserId],
  );
  const [resetPassword, setResetPassword] = useState("");
  const [notificationId, setNotificationId] = useState(
    overview.notification_rows[0] ? String(overview.notification_rows[0].id) : "",
  );

  async function runAction(
    path: string,
    payload: object,
    shouldRefresh = true,
    confirmation?: string,
  ) {
    if (confirmation && !(await confirmAction(confirmation))) {
      return;
    }
    setPending(true);
    setError(null);
    setMessage(null);
    try {
      const result = await postAction(path, payload);
      setMessage(result.message);
      storeFlashMessage({ tone: "success", message: result.message });
      if (shouldRefresh) {
        router.refresh();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Settings action failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="grid two">
      <section className="panel">
        <h3>Controls</h3>
        <div className="stack">
          <div className="action-card">
            <h4>Guardrails</h4>
            <div className="stack tight">
              <label className="field">
                <span>Payment reference policy</span>
                <select
                  value={blockDuplicate ? "block" : "warn"}
                  onChange={(event) => setBlockDuplicate(event.target.value === "block")}
                >
                  <option value="block">Block duplicates</option>
                  <option value="warn">Warn only</option>
                </select>
              </label>
              <label className="field">
                <span>Invoice approval</span>
                <select
                  value={autoApproveInvoices ? "auto" : "admin"}
                  onChange={(event) => setAutoApproveInvoices(event.target.value === "auto")}
                >
                  <option value="auto">Auto approve on submit</option>
                  <option value="admin">Require admin approval</option>
                </select>
              </label>
              <div className="inline-actions">
                <label className="field">
                  <span>Max attempts</span>
                  <input
                    autoComplete="off"
                    min="1"
                    name="notification_max_attempts"
                    max="20"
                    type="number"
                    value={maxAttempts}
                    onChange={(event) => setMaxAttempts(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Retry delay (seconds)</span>
                  <input
                    autoComplete="off"
                    min="30"
                    name="notification_retry_delay_seconds"
                    max="86400"
                    type="number"
                    value={retryDelay}
                    onChange={(event) => setRetryDelay(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Reservation hold (hours)</span>
                  <input
                    autoComplete="off"
                    min="1"
                    name="reservation_default_hold_hours"
                    max="720"
                    type="number"
                    value={holdHours}
                    onChange={(event) => setHoldHours(event.target.value)}
                  />
                </label>
              </div>
              <button
                className="button"
                disabled={pending}
                onClick={() =>
                  runAction(
                    "/settings/guardrails",
                    {
                      block_duplicate_payment_reference: blockDuplicate,
                      notification_max_attempts: Number(maxAttempts),
                      notification_retry_delay_seconds: Number(retryDelay),
                      reservation_default_hold_hours: Number(holdHours),
                      auto_approve_invoices: autoApproveInvoices,
                    },
                    true,
                    buildConfirmationMessage("Save guardrail settings?", [
                      `Duplicate references: ${blockDuplicate ? "Block" : "Warn only"}`,
                      `Invoice approval: ${autoApproveInvoices ? "Auto approve" : "Admin review"}`,
                      `Reservation hold: ${holdHours} hours`,
                    ]),
                  )
                }
                type="button"
              >
                Save controls
              </button>
            </div>
          </div>

          <div className="action-card">
            <h4>Providers</h4>
            <div className="stack tight">
              <form className="stack tight" onSubmit={(event) => event.preventDefault()}>
              <input
                autoComplete="username"
                name="providers_username_hint"
                readOnly
                tabIndex={-1}
                type="text"
                value="settings-providers"
                hidden
              />
              <label className="field">
                <span>Delivery mode</span>
                <select value={mockMode ? "mock" : "live"} onChange={(event) => setMockMode(event.target.value === "mock")}>
                  <option value="live">Live providers</option>
                  <option value="mock">Mock delivery</option>
                </select>
              </label>
              <div className="inline-actions">
                <label className="field">
                  <span>SMS API URL</span>
                  <input
                    autoComplete="url"
                    name="sms_api_url"
                    value={smsApiUrl}
                    onChange={(event) => setSmsApiUrl(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>SMS sender ID</span>
                  <input
                    autoComplete="off"
                    name="sms_sender_id"
                    value={smsSenderId}
                    onChange={(event) => setSmsSenderId(event.target.value)}
                  />
                </label>
              </div>
              <label className="field">
                <span>SMS API key {overview.settings.sms_api_key_set ? "(stored)" : ""}</span>
                <input
                  autoComplete="new-password"
                  name="sms_api_key"
                  type="password"
                  value={smsApiKey}
                  onChange={(event) => setSmsApiKey(event.target.value)}
                  placeholder={overview.settings.sms_api_key_set ? "Leave blank to keep current key" : ""}
                />
              </label>
              <div className="inline-actions">
                <label className="field">
                  <span>SMTP host</span>
                  <input
                    autoComplete="off"
                    name="smtp_host"
                    value={smtpHost}
                    onChange={(event) => setSmtpHost(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>SMTP port</span>
                  <input
                    autoComplete="off"
                    inputMode="numeric"
                    name="smtp_port"
                    value={smtpPort}
                    onChange={(event) => setSmtpPort(event.target.value)}
                  />
                </label>
              </div>
              <div className="inline-actions">
                <label className="field">
                  <span>SMTP user</span>
                  <input
                    autoComplete="username"
                    name="smtp_user"
                    value={smtpUser}
                    onChange={(event) => setSmtpUser(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>SMTP from</span>
                  <input
                    autoComplete="email"
                    name="smtp_from"
                    type="email"
                    value={smtpFrom}
                    onChange={(event) => setSmtpFrom(event.target.value)}
                  />
                </label>
              </div>
              <label className="field">
                <span>SMTP password {overview.settings.smtp_password_set ? "(stored)" : ""}</span>
                <input
                  autoComplete="new-password"
                  name="smtp_password"
                  type="password"
                  value={smtpPassword}
                  onChange={(event) => setSmtpPassword(event.target.value)}
                  placeholder={overview.settings.smtp_password_set ? "Leave blank to keep current password" : ""}
                />
              </label>
              <div className="inline-actions">
                <label className="field">
                  <span>WhatsApp phone ID</span>
                  <input
                    autoComplete="tel"
                    name="whatsapp_phone_number_id"
                    value={whatsAppPhoneId}
                    onChange={(event) => setWhatsAppPhoneId(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>API version</span>
                  <input
                    autoComplete="off"
                    name="whatsapp_api_version"
                    value={whatsAppVersion}
                    onChange={(event) => setWhatsAppVersion(event.target.value)}
                  />
                </label>
              </div>
              <label className="field">
                <span>WhatsApp access token {overview.settings.whatsapp_access_token_set ? "(stored)" : ""}</span>
                <input
                  autoComplete="new-password"
                  name="whatsapp_access_token"
                  type="password"
                  value={whatsAppToken}
                  onChange={(event) => setWhatsAppToken(event.target.value)}
                  placeholder={overview.settings.whatsapp_access_token_set ? "Leave blank to keep current token" : ""}
                />
              </label>
              <button
                className="button secondary"
                disabled={pending}
                onClick={() =>
                  runAction(
                    "/settings/providers",
                    {
                      mock_mode: mockMode,
                      sms_api_url: smsApiUrl,
                      sms_api_key: smsApiKey,
                      sms_sender_id: smsSenderId,
                      smtp_host: smtpHost,
                      smtp_port: smtpPort ? Number(smtpPort) : null,
                      smtp_user: smtpUser,
                      smtp_password: smtpPassword,
                      smtp_from: smtpFrom,
                      whatsapp_access_token: whatsAppToken,
                      whatsapp_phone_number_id: whatsAppPhoneId,
                      whatsapp_api_version: whatsAppVersion,
                    },
                    true,
                    buildConfirmationMessage("Save provider settings?", [
                      `Delivery mode: ${mockMode ? "Mock" : "Live"}`,
                      smsSenderId ? `SMS sender: ${smsSenderId}` : null,
                      smtpFrom ? `SMTP from: ${smtpFrom}` : null,
                    ]),
                  )
                }
                type="button"
              >
                Save providers
              </button>
              </form>
              <div className="stack tight">
                <form className="inline-actions" onSubmit={(event) => event.preventDefault()}>
                  <label className="field">
                    <span>Test SMS recipient</span>
                    <input
                      autoComplete="tel"
                      name="sms_test_recipient"
                      value={smsTestRecipient}
                      onChange={(event) => setSmsTestRecipient(event.target.value)}
                      placeholder="233XXXXXXXXX"
                    />
                  </label>
                  <button
                    className="button ghost"
                    disabled={pending || !smsTestRecipient.trim()}
                    onClick={() =>
                      runAction(
                        "/settings/providers/test",
                        { channel: "sms", recipient: smsTestRecipient },
                        false,
                        buildConfirmationMessage("Send SMS test?", [`Recipient: ${smsTestRecipient.trim()}`]),
                      )
                    }
                    type="button"
                  >
                    Send SMS test
                  </button>
                </form>
                <form className="inline-actions" onSubmit={(event) => event.preventDefault()}>
                  <label className="field">
                    <span>Test email recipient</span>
                    <input
                      autoComplete="email"
                      name="email_test_recipient"
                      type="email"
                      value={emailTestRecipient}
                      onChange={(event) => setEmailTestRecipient(event.target.value)}
                      placeholder="staff@example.com"
                    />
                  </label>
                  <button
                    className="button ghost"
                    disabled={pending || !emailTestRecipient.trim()}
                    onClick={() =>
                      runAction(
                        "/settings/providers/test",
                        { channel: "email", recipient: emailTestRecipient },
                        false,
                        buildConfirmationMessage("Send email test?", [`Recipient: ${emailTestRecipient.trim()}`]),
                      )
                    }
                    type="button"
                  >
                    Send email test
                  </button>
                </form>
                <form className="inline-actions" onSubmit={(event) => event.preventDefault()}>
                  <label className="field">
                    <span>Test WhatsApp recipient</span>
                    <input
                      autoComplete="tel"
                      name="whatsapp_test_recipient"
                      value={whatsAppTestRecipient}
                      onChange={(event) => setWhatsAppTestRecipient(event.target.value)}
                      placeholder="233XXXXXXXXX"
                    />
                  </label>
                  <button
                    className="button ghost"
                    disabled={pending || !whatsAppTestRecipient.trim()}
                    onClick={() =>
                      runAction(
                        "/settings/providers/test",
                        { channel: "whatsapp", recipient: whatsAppTestRecipient },
                        false,
                        buildConfirmationMessage("Send WhatsApp test?", [`Recipient: ${whatsAppTestRecipient.trim()}`]),
                      )
                    }
                    type="button"
                  >
                    Send WhatsApp test
                  </button>
                </form>
              </div>
            </div>
          </div>

          <div className="action-card">
            <h4>Operations</h4>
            <div className="stack tight">
              <button
                className="button ghost"
                disabled={pending}
                onClick={() =>
                  runAction(
                    "/settings/workers/reservations/run",
                    {},
                    true,
                    buildConfirmationMessage("Run reservation expiry now?", [
                      "This will process overdue reservation holds immediately.",
                    ]),
                  )
                }
                type="button"
              >
                Run reservation expiry now
              </button>
              {overview.notification_rows.length ? (
                <>
                  <label className="field">
                    <span>Notification item</span>
                    <select value={notificationId} onChange={(event) => setNotificationId(event.target.value)}>
                      {overview.notification_rows.map((row) => (
                        <option key={row.id} value={row.id}>
                          {row.channel} | {row.recipient} | {row.status}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="button secondary"
                    disabled={pending || !notificationId}
                    onClick={() =>
                      runAction(
                        `/settings/notifications/${notificationId}/retry`,
                        {},
                        true,
                        buildConfirmationMessage("Re-queue this notification?", [
                          `Notification ID: ${notificationId}`,
                        ]),
                      )
                    }
                    type="button"
                  >
                    Re-queue notification
                  </button>
                </>
              ) : (
                <p className="section-note">No notification items are available for retry.</p>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="panel">
        <h3>Users</h3>
        <div className="stack">
          <div className="action-card">
            <h4>Create user</h4>
            <form className="stack tight" onSubmit={(event) => event.preventDefault()}>
              <div className="inline-actions">
                <label className="field">
                  <span>Full name</span>
                  <input
                    autoComplete="name"
                    name="full_name"
                    value={fullName}
                    onChange={(event) => setFullName(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Email</span>
                  <input
                    autoComplete="email"
                    name="email"
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                  />
                </label>
              </div>
              <div className="inline-actions">
                <label className="field">
                  <span>Password</span>
                  <input
                    name="password"
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    autoComplete="new-password"
                  />
                </label>
                <label className="field">
                  <span>Role</span>
                  <select value={role} onChange={(event) => setRole(event.target.value)}>
                    <option value="cashier">Cashier</option>
                    <option value="admin">Admin</option>
                  </select>
                </label>
              </div>
              <button
                className="button"
                disabled={pending || !email.trim() || !fullName.trim() || !password}
                onClick={() =>
                  runAction(
                    "/settings/users",
                    {
                      email,
                      full_name: fullName,
                      password,
                      is_admin: role === "admin",
                    },
                    true,
                    buildConfirmationMessage("Create this user account?", [
                      `Name: ${fullName.trim()}`,
                      `Email: ${email.trim()}`,
                      `Role: ${role === "admin" ? "Admin" : "Cashier"}`,
                    ]),
                  )
                }
                type="button"
              >
                Create account
              </button>
            </form>
          </div>

          <div className="action-card">
            <h4>Reset password</h4>
            <form className="stack tight" onSubmit={(event) => event.preventDefault()}>
              <input
                autoComplete="username"
                name="reset_username_hint"
                readOnly
                tabIndex={-1}
                type="text"
                value={selectedResetUser?.email ?? ""}
                hidden
              />
              <label className="field">
                <span>User</span>
                <select value={resetUserId} onChange={(event) => setResetUserId(event.target.value)}>
                  {resetCandidates.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.full_name} | {account.email}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>New password</span>
                <input
                  name="reset_password"
                  type="password"
                  value={resetPassword}
                  onChange={(event) => setResetPassword(event.target.value)}
                  autoComplete="new-password"
                />
              </label>
              <button
                className="button secondary"
                disabled={pending || !resetUserId || !resetPassword}
                onClick={() =>
                  runAction(
                    `/settings/users/${resetUserId}/reset-password`,
                    {
                      password: resetPassword,
                    },
                    true,
                    buildConfirmationMessage("Reset this user's password?", [
                      `User ID: ${resetUserId}`,
                      "The old password will stop working immediately.",
                    ]),
                  )
                }
                type="button"
              >
                Reset password
              </button>
            </form>
          </div>

          <div className="action-card">
            <h4>Access roster</h4>
            <div className="stack tight">
              {overview.users.map((account) => (
                <div key={account.id} className="segmented-row">
                  <div className="meta-row">
                    <strong>{account.full_name}</strong>
                    <div className="inline-actions">
                      <StatusPill tone={account.is_admin ? "accent" : "default"}>
                        {account.is_admin ? "Admin" : "Cashier"}
                      </StatusPill>
                      <StatusPill tone={account.is_active ? "success" : "warning"}>
                        {account.is_active ? "Active" : "Inactive"}
                      </StatusPill>
                    </div>
                  </div>
                  <span>{account.email}</span>
                  <UserRowActions user={account} onAction={runAction} pending={pending} />
                </div>
              ))}
            </div>
          </div>

          {message ? <p className="success-text">{message}</p> : null}
          {error ? <p className="error-text">{error}</p> : null}
        </div>
      </section>
    </div>
  );
}
