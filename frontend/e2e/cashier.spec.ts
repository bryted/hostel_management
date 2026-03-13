import { expect, test } from "@playwright/test";

import { login } from "./helpers";

const cashierUsername = process.env.E2E_CASHIER_USERNAME ?? "user@example.com";
const cashierPassword = process.env.E2E_CASHIER_PASSWORD ?? "UserPass1!";

test("cashier can access billing, tenants, and beds", async ({ page }) => {
  await login(page, cashierUsername, cashierPassword);

  await expect(page.getByRole("heading", { name: "Billing", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Inventory" })).toHaveCount(0);

  await page.goto("/tenants");
  await expect(page.getByRole("heading", { name: "Residents" })).toBeVisible();

  await page.goto("/beds");
  await expect(page.getByRole("heading", { name: "Beds" })).toBeVisible();
});

test("cashier can open resident billing records", async ({ page }) => {
  await login(page, cashierUsername, cashierPassword);

  await page.goto("/tenants?search=E2E%20Resident");
  await page.getByRole("link", { name: "Workspace" }).first().click();
  await expect(page.getByRole("heading", { name: "E2E Resident" })).toBeVisible();

  await page.getByRole("link", { name: /^REC-/ }).first().click();
  await expect(page).toHaveURL(/\/receipts\//);
  await expect(page.getByText("Verified receipt")).toBeVisible();
});
