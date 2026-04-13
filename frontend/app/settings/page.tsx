import Link from "next/link";

import { InteractiveTable } from "../../components/interactive-table";
import { DataPanel, PageIntro, StatusPill, SummaryStrip } from "../../components/page-shell";
import { SettingsActions } from "../../components/settings-actions";
import { fetchSettingsOverview, requireUser } from "../../lib/server-api";

export default async function SettingsPage() {
  const user = await requireUser();

  if (!user.is_admin) {
    return (
      <div className="grid">
        <PageIntro
          title="Settings are restricted to admins"
          actions={
            <>
              <Link className="button" href="/billing">
                Open billing
              </Link>
              <Link className="button ghost" href="/dashboard">
                Return to dashboard
              </Link>
            </>
          }
          aside={
            <div className="meta-list">
              <div className="meta-row">
                <span>Role</span>
                <StatusPill tone="warning">Cashier</StatusPill>
              </div>
              <div className="meta-row">
                <span>Scope</span>
                <strong>No admin policy access</strong>
              </div>
            </div>
          }
        />
      </div>
    );
  }

  const overview = await fetchSettingsOverview();
  const adminCount = overview.users.filter((account) => account.is_admin).length;
  const currentAcademicYear =
    overview.academic_years.find((year) => year.is_current)?.label ?? "Not set";

  return (
    <div className="grid">
      <PageIntro
        title="Settings"
        description="Operational controls, delivery providers, user access, and audit visibility."
        aside={
          <>
            <StatusPill tone={overview.settings.auto_approve_invoices ? "success" : "warning"}>
              {overview.settings.auto_approve_invoices ? "Auto approval on" : "Admin approval required"}
            </StatusPill>
            <StatusPill tone={overview.settings.mock_mode ? "warning" : "default"}>
              {overview.settings.mock_mode ? "Mock notifications" : "Live notifications"}
            </StatusPill>
          </>
        }
      />
      <SummaryStrip
        items={[
          { label: "Users", value: overview.users.length, tone: "default" },
          { label: "Admins", value: adminCount, tone: "accent" },
          { label: "Academic year", value: currentAcademicYear, tone: "accent" },
          { label: "SMS", value: overview.settings.sms_configured ? "Ready" : "Offline", tone: overview.settings.sms_configured ? "success" : "warning" },
          { label: "Email", value: overview.settings.email_configured ? "Ready" : "Offline", tone: overview.settings.email_configured ? "success" : "default" },
          { label: "WhatsApp", value: overview.settings.whatsapp_configured ? "Ready" : "Offline", tone: overview.settings.whatsapp_configured ? "success" : "default" },
          { label: "Bed hold", value: `${overview.settings.reservation_default_hold_hours}h`, tone: "warning" },
        ]}
      />

      <SettingsActions overview={overview} />

      <div className="grid two">
        <DataPanel title="Cashier visibility" description="What cashier accounts can see and act on in daily operations." tone="supporting">
          <ul className="role-scope-list">
            {overview.cashier_scope.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </DataPanel>
        <DataPanel title="Admin visibility" description="What admin accounts can control across finance, inventory, and policy." tone="supporting">
          <ul className="role-scope-list">
            {overview.admin_scope.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </DataPanel>
      </div>

      <div className="grid two">
        <DataPanel title="Academic years" description="Current and historical academic periods used across billing, receipts, and room assignments." tone="secondary">
          <div className="stack tight">
            {overview.academic_years.length ? (
              overview.academic_years.map((year) => (
                <div key={year.id} className="meta-row">
                  <span>
                    {year.label} | {year.start_date} to {year.end_date}
                  </span>
                  <div className="inline-actions">
                    {year.is_current ? <StatusPill tone="accent">Current</StatusPill> : null}
                    {year.is_closed ? <StatusPill tone="default">Closed</StatusPill> : null}
                  </div>
                </div>
              ))
            ) : (
              <p className="small">Academic years will appear here after migration and first use.</p>
            )}
          </div>
        </DataPanel>
        <DataPanel title="Notification queue" description="Current state of outbound messaging activity across all configured channels." tone="supporting">
          <div className="queue-grid">
            {overview.queue_statuses.length ? (
              overview.queue_statuses.map((row) => (
                <div key={row.status} className="queue-tile">
                  <span>{row.status}</span>
                  <strong>{row.count}</strong>
                </div>
              ))
            ) : (
              <p className="small">No queued notification activity yet.</p>
            )}
          </div>
        </DataPanel>
        <DataPanel title="Reservation expiry worker" description="Background process responsible for releasing unpaid room holds." tone="supporting">
          <div className="stack tight">
            <p className="section-note">{overview.worker_status.reservation_expiry_job}</p>
            <div className="meta-list">
              <div className="meta-row">
                <span>Interval</span>
                <strong>Every {overview.worker_status.interval_minutes} minutes</strong>
              </div>
              <div className="meta-row">
                <span>Purpose</span>
                <strong>Release unpaid bed holds automatically</strong>
              </div>
            </div>
          </div>
        </DataPanel>
      </div>

      <DataPanel title="Recent audit trail" description="Recent administrative and financial actions captured for accountability." tone="secondary">
        <InteractiveTable
          rows={overview.audit_rows.map((row) => ({
            When: row.when,
            Source: row.source,
            Event: row.event,
            Detail: row.detail,
          }))}
          emptyText="No recent activity yet."
          searchPlaceholder="Filter audit trail"
        />
      </DataPanel>

      <DataPanel title="Notification activity" description="Delivery attempts and recent outcomes for SMS, email, and WhatsApp." tone="supporting">
        <InteractiveTable
          rows={overview.notification_rows.map((row) => ({
            Channel: row.channel,
            Recipient: row.recipient,
            Tenant: row.tenant_name ?? "-",
            Status: row.status,
            Attempts: row.attempt_count,
            Scheduled: row.scheduled_at ?? "-",
            Sent: row.sent_at ?? "-",
            Error: row.error ?? "-",
          }))}
          emptyText="No notification activity yet."
          searchPlaceholder="Filter notifications"
        />
      </DataPanel>
    </div>
  );
}
