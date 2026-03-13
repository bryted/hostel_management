import { expect, type Locator, type Page } from "@playwright/test";

export async function login(page: Page, username: string, password: string) {
  await page.goto("/login");
  await page.getByRole("textbox", { name: "Username or email" }).fill(username);
  await page.getByRole("textbox", { name: "Password" }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/(dashboard|billing)(\?|$)/, { timeout: 20000 });
}

export async function acceptCenteredDialog(page: Page) {
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.locator("[data-feedback-confirm]").click();
}

export async function selectOptionByPartialText(locator: Locator, text: string) {
  const value = await locator.evaluate((element, partialText) => {
    const select = element as HTMLSelectElement;
    const match = Array.from(select.options).find((option) =>
      option.text.includes(String(partialText)),
    );
    return match?.value ?? null;
  }, text);
  expect(value).toBeTruthy();
  await locator.selectOption(String(value));
}

export async function expectRoughlyCentered(page: Page, locator: Locator) {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  const viewport = page.viewportSize();
  expect(viewport).not.toBeNull();
  if (!box || !viewport) {
    return;
  }
  const centerX = box.x + box.width / 2;
  const centerY = box.y + box.height / 2;
  expect(Math.abs(centerX - viewport.width / 2)).toBeLessThanOrEqual(viewport.width * 0.18);
  expect(Math.abs(centerY - viewport.height / 2)).toBeLessThanOrEqual(viewport.height * 0.22);
}
