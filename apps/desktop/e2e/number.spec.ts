import { expect, test } from "@playwright/test";

test("required number and date fields accept a value (number incl. 0)", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder("Username").fill("admin");
  await page.getByPlaceholder("Password").fill("DocMaster!2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Engine ready")).toBeVisible();
  await page.locator(".tile", { hasText: "New document" }).click();
  await page.locator(".ant-card", { hasText: "Cover note" }).getByRole("button", { name: "Use this template" }).click();
  const years = page.getByLabel("Years of experience");
  await years.fill("7");
  await page.getByLabel("Full name", { exact: true }).fill("Asha");
  const sign = page.getByLabel("Sign date"); await sign.click(); await sign.fill("2026-03-12"); await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Review details" }).click();
  const errors = await page.locator(".ant-form-item-explain-error").allTextContents();
  console.log("ERRORS:", JSON.stringify(errors));
  expect(errors.filter((e) => /years|sign date/i.test(e))).toEqual([]);
  expect(errors).toContain("Email is required");                      // other required fields still flagged
  await years.fill("0");
  await page.getByRole("button", { name: "Review details" }).click();
  const errors0 = await page.locator(".ant-form-item-explain-error").allTextContents();
  console.log("ERRORS0:", JSON.stringify(errors0));
  expect(errors0.filter((e) => /years/i.test(e))).toEqual([]);
});
