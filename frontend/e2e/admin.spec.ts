import { expect, test } from "@playwright/test";

import {
  acceptCenteredDialog,
  expectRoughlyCentered,
  login,
  selectOptionByPartialText,
} from "./helpers";

const adminUsername = process.env.E2E_ADMIN_USERNAME;
const adminPassword = process.env.E2E_ADMIN_PASSWORD;

test.skip(!adminUsername || !adminPassword, "Admin credentials not configured.");

test("admin can access core admin surfaces", async ({ page }) => {
  await login(page, adminUsername!, adminPassword!);

  await page.goto("/inventory");
  await expect(page.getByRole("heading", { name: "Inventory", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Integrity", exact: true }).click();
  await expect(page).toHaveURL(/\/inventory\?section=integrity$/);
  await expect(page.getByRole("heading", { name: "Integrity", exact: true })).toBeVisible();

  await page.goto("/allocations");
  await expect(page).toHaveURL(/\/allocations$/);
  await expect(page.getByRole("heading", { name: "Active stays" })).toBeVisible();

  await page.goto("/reports");
  await expect(page).toHaveURL(/\/reports$/);
  await expect(page.getByRole("heading", { name: "Reports" })).toBeVisible();

  await page.goto("/settings");
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
});

test("admin can download reports and inventory exports", async ({ page }) => {
  await login(page, adminUsername!, adminPassword!);

  await page.goto("/reports");
  const financeDownloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Tenant finance CSV" }).click();
  const financeDownload = await financeDownloadPromise;
  expect(financeDownload.suggestedFilename()).toMatch(/^tenant-finance-.*\.csv$/);

  await page.getByRole("link", { name: "Occupancy" }).click();
  const occupancyDownloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Room utilization CSV" }).click();
  const occupancyDownload = await occupancyDownloadPromise;
  expect(occupancyDownload.suggestedFilename()).toMatch(/^room-utilization-.*\.csv$/);

  await page.goto("/inventory?section=structure");
  const roomsDownloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download all rooms" }).click();
  const roomsDownload = await roomsDownloadPromise;
  expect(roomsDownload.suggestedFilename()).toMatch(/^rooms-.*\.csv$/);

  const bedsDownloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download available beds" }).click();
  const bedsDownload = await bedsDownloadPromise;
  expect(bedsDownload.suggestedFilename()).toMatch(/^available-beds-.*\.csv$/);
});

test("admin can test providers and use global search", async ({ page }) => {
  await login(page, adminUsername!, adminPassword!);

  await page.goto("/settings");
  await page.getByRole("textbox", { name: "Test email recipient" }).fill("qa@example.test");
  await page.getByRole("button", { name: "Send email test" }).click();
  await acceptCenteredDialog(page);
  await expect(page.getByRole("status")).toContainText("EMAIL test sent.");

  await page.getByRole("searchbox", { name: "Global search" }).fill("E2E Resident");
  await page.getByRole("link", { name: "E2E Resident" }).first().click();
  await expect(page.getByRole("heading", { name: "E2E Resident" })).toBeVisible();

  await page.getByRole("link", { name: /^REC-/ }).first().click();
  await expect(page).toHaveURL(/\/receipts\//);
  await expect(page.getByText("Verified receipt")).toBeVisible();
});

test("admin feedback surfaces stay centered on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, adminUsername!, adminPassword!);

  await page.goto("/settings");
  await page.getByRole("textbox", { name: "Test email recipient" }).fill("qa@example.test");
  await page.getByRole("button", { name: "Send email test" }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expectRoughlyCentered(page, dialog);
  await acceptCenteredDialog(page);

  const toast = page.getByRole("status").filter({ hasText: "EMAIL test sent." });
  await expect(toast).toBeVisible();
  await expectRoughlyCentered(page, toast);
});

test("admin sees hold-expiry warning in billing", async ({ page }) => {
  await login(page, adminUsername!, adminPassword!);

  await page.goto("/billing");
  const invoiceSelect = page.getByLabel("Invoice").first();
  await selectOptionByPartialText(invoiceSelect, "E2E Hold Warning");

  const warningToast = page.getByRole("status").filter({ hasText: "Bed hold expires in" });
  await expect(warningToast).toBeVisible();
  await expect(warningToast).toContainText("Collect or reassign promptly");
});

test("admin can record a warn-only duplicate reference payment", async ({ page }) => {
  await login(page, adminUsername!, adminPassword!);

  await page.goto("/settings");
  await page.getByLabel("Payment reference policy").selectOption("warn");
  await page.getByRole("button", { name: "Save controls" }).click();
  await acceptCenteredDialog(page);
  await expect(page.getByRole("status")).toContainText("Settings updated.");

  await page.goto("/billing");
  const invoiceSelect = page.getByLabel("Invoice").first();
  await selectOptionByPartialText(invoiceSelect, "E2E Duplicate Target");
  await page.getByRole("button", { name: "Use remaining balance" }).click();
  await page.getByLabel("Method").selectOption("card");
  await page.getByLabel("Reference").fill("E2E-DUP-REF");
  await page.getByRole("button", { name: "Record payment" }).click();
  await acceptCenteredDialog(page);

  const warningToast = page.getByRole("status").filter({ hasText: "duplicate reference" });
  await expect(warningToast).toBeVisible();
  await expect(warningToast).toContainText("warn only");

  await page.goto("/settings");
  await page.getByLabel("Payment reference policy").selectOption("block");
  await page.getByRole("button", { name: "Save controls" }).click();
  await acceptCenteredDialog(page);
  await expect(page.getByRole("status")).toContainText("Settings updated.");
});

test("admin can create an invoice from billing", async ({ page }) => {
  await login(page, adminUsername!, adminPassword!);
  const tenantName = `E2E Billing ${Date.now()}`;

  await page.goto("/billing");
  await page.getByLabel("Name").fill(tenantName);
  await page.getByRole("button", { name: "Create tenant" }).click();
  await acceptCenteredDialog(page);
  await expect(page).toHaveURL(/\/tenants\/\d+$/);
  await expect(page.getByRole("heading", { name: tenantName })).toBeVisible();

  await page.goto("/billing");
  await page.locator("summary.action-summary").filter({ hasText: "Create invoice" }).click();
  await page.getByLabel("Tenant").first().selectOption({ label: tenantName });
  await selectOptionByPartialText(page.getByLabel("Bed").first(), "E2E-103 / B1");
  await page.getByLabel("Notes").fill("E2E browser invoice");
  await page.getByLabel("Submit now").selectOption({ label: "Save as draft" });
  await page.getByRole("button", { name: "Create invoice" }).click();
  await acceptCenteredDialog(page);

  await expect(page).toHaveURL(/invoiceId=/);
  await expect(page.getByRole("status")).toContainText("Invoice created.");
  await expect(page.getByRole("heading", { name: "Selected record" })).toBeVisible();
  await page.getByRole("link", { name: "Full invoice" }).click();
  await expect(page).toHaveURL(/\/invoices\//);
  await expect(page.getByRole("heading", { name: "Invoice", exact: true })).toBeVisible();
  await expect(page.getByText("E2E browser invoice")).toBeVisible();
  await page.getByLabel("Reason").fill("E2E cleanup");
  await page.getByRole("button", { name: "Cancel invoice" }).click();
  await acceptCenteredDialog(page);
  await expect(page.getByRole("status")).toContainText("Invoice cancelled.");
});

test("admin cannot overpay an invoice from billing", async ({ page }) => {
  await login(page, adminUsername!, adminPassword!);

  await page.goto("/billing");
  const invoiceSelect = page.getByLabel("Invoice").first();
  await expect(invoiceSelect).toBeVisible();
  await invoiceSelect.selectOption({ index: 0 });
  await page.getByLabel("Amount").fill("999999");

  await expect(page.getByText(/Amount exceeds the remaining balance/i)).toBeVisible();
  await expect(page.getByRole("button", { name: "Record payment" })).toBeDisabled();
});
