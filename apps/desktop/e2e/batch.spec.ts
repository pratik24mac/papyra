import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page) {
  await page.goto("/");
  await page.getByPlaceholder("Username").fill("admin");
  await page.getByPlaceholder("Password").fill("DocMaster!2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Engine ready")).toBeVisible();
  await page.locator(".tile", { hasText: "New document" }).click();
}

test("two templates: shared fields asked once, unique ones per template, one batch", async ({ page }) => {
  await signIn(page);
  await page.getByLabel("Select Resume (ATS-friendly)").check();
  await page.getByLabel("Select Cover note").check();
  await expect(page.getByText("2 selected", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Generate 2 documents together" }).click();
  // merged form
  await expect(page.locator(".ant-card-head-title", { hasText: "Common details" })).toBeVisible();
  await expect(page.getByLabel("Full name", { exact: true })).toHaveCount(1);          // shared, asked once
  await expect(page.locator(".ant-card-head-title", { hasText: "Note · Cover note" })).toBeVisible();
  await expect(page.getByLabel("Recipient name")).toBeVisible();                        // unique to the cover note
  await expect(page.getByLabel("Headline (Resume (ATS-friendly))")).toBeVisible();      // same id, different type → kept apart
  await expect(page.getByLabel("Tone (Cover note)")).toBeVisible();
  await page.getByRole("button", { name: "Pre-fill with example values" }).first().click();
  await expect(page.getByLabel("Full name", { exact: true })).toHaveValue("Asha Verma");
  await page.getByLabel("Recipient name").fill("Hiring team");
  await page.getByLabel("Note text").fill("Please see the attached.");
  await page.locator(".ant-select", { has: page.locator("input#headline__cover-note") }).click();
  await page.locator(".ant-select-item-option", { hasText: "Formal" }).click();
  await page.getByRole("button", { name: "Review details" }).click();
  await expect(page.getByText("Common details")).toBeVisible();
  await page.getByRole("button", { name: "Generate document" }).click();
  await expect(page.getByText("All documents generated")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("2 of 2 ready")).toBeVisible();
  await expect(page.locator(".ant-table-row", { hasText: "Cover note" }).getByText("ready", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Preview PDFs" }).click();
  await expect(page.locator("[data-testid=pdf-pages] canvas")).toHaveCount(2, { timeout: 15_000 });
});

test("a failed document in a batch is reported, the others stay usable", async ({ page }) => {
  await signIn(page);
  await page.getByLabel("Select Resume (ATS-friendly)").check();
  await page.getByLabel("Select Cover note").check();
  await page.getByRole("button", { name: "Generate 2 documents together" }).click();
  await page.getByRole("button", { name: "Pre-fill with example values" }).first().click();
  await page.getByLabel("Full name", { exact: true }).fill("FAIL PDF");
  await page.getByLabel("Recipient name").fill("x"); await page.getByLabel("Note text").fill("y");
  await page.locator(".ant-select", { has: page.locator("input#headline__cover-note") }).click();
  await page.locator(".ant-select-item-option", { hasText: "Formal" }).click();
  await page.getByRole("button", { name: "Review details" }).click();
  await page.getByRole("button", { name: "Generate document" }).click();
  await expect(page.getByText("Some documents failed")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("1 of 2 ready")).toBeVisible();
  await expect(page.locator(".ant-table-row", { hasText: "Resume (ATS-friendly)" }).getByText("failed", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Preview PDFs" })).toBeVisible();
});
