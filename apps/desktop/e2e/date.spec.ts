import { expect, test, type Page } from "@playwright/test";

async function openForm(page: Page, errors: string[]) {
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !m.text().includes("Warning:")) errors.push("console: " + m.text()); });
  await page.goto("/");
  await page.getByPlaceholder("Username").fill("admin");
  await page.getByPlaceholder("Password").fill("DocMaster!2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Engine ready")).toBeVisible();
  await page.locator(".tile", { hasText: "New document" }).click();
  await page.locator(".ant-card", { hasText: "Resume (ATS-friendly)" }).getByRole("button", { name: "Use this template" }).click();
}

test("typing a date keeps the form alive", async ({ page }) => {
  const errors: string[] = []; await openForm(page, errors);
  const date = page.getByLabel("Available from");
  await date.click(); await date.fill("2026-03-12"); await page.keyboard.press("Enter");
  await expect(date).toHaveValue("2026-03-12");
  await page.getByLabel("Full name", { exact: true }).fill("Someone");
  await expect(page.locator("#root")).not.toBeEmpty();
  expect(errors).toEqual([]);
});

test("clicking a day in the calendar, then review, then back", async ({ page }) => {
  const errors: string[] = []; await openForm(page, errors);
  await page.getByRole("button", { name: "Pre-fill with example values" }).first().click();
  const date = page.getByLabel("Available from");
  await date.click();
  await page.locator(".ant-picker-dropdown:visible .ant-picker-cell-inner", { hasText: /^15$/ }).first().click();
  await expect(date).toHaveValue(/-15$/);
  await page.getByRole("button", { name: "Review details" }).click();
  await expect(page.getByText("Available from")).toBeVisible();
  await expect(page.getByText(/-15$/).first()).toBeVisible();
  await page.getByRole("button", { name: "Edit", exact: true }).first().click();
  await expect(date).toHaveValue(/-15$/);
  await page.getByRole("button", { name: "Review details" }).click();
  await page.getByRole("button", { name: "Generate document" }).click();
  await expect(page.getByText("Document generated")).toBeVisible({ timeout: 10_000 });
  await expect(page.locator("#root")).not.toBeEmpty();
  expect(errors).toEqual([]);
});

test("a non-ISO date default renders as empty instead of crashing", async ({ page }) => {
  const errors: string[] = []; await openForm(page, errors);
  const date = page.getByLabel("Available from");
  await expect(date).toHaveValue("");
  await expect(page.locator("#root")).not.toBeEmpty();
  expect(errors).toEqual([]);
});

test("text inputs have autocomplete switched off", async ({ page }) => {
  const errors: string[] = []; await openForm(page, errors);
  expect(await page.getByLabel("Full name", { exact: true }).getAttribute("autocomplete")).toBe("off");
  expect(await page.locator("form").first().getAttribute("autocomplete")).toBe("off");
});
