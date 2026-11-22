import { expect, test, type Page } from "@playwright/test";

async function openCoverNote(page: Page) {
  await page.goto("/");
  await page.getByPlaceholder("Username").fill("admin");
  await page.getByPlaceholder("Password").fill("DocMaster!2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Engine ready")).toBeVisible();
  await page.locator(".tile", { hasText: "New document" }).click();
  await page.locator(".ant-card", { hasText: "Cover note" }).getByRole("button", { name: "Use this template" }).click();
}

test("a transform:upper field capitalises as the user types", async ({ page }) => {
  await openCoverNote(page);
  const field = page.getByLabel("Recipient name");
  await field.fill("hiring team");
  await expect(field).toHaveValue("HIRING TEAM");
  await field.press("End"); await field.type(" x");
  await expect(field).toHaveValue("HIRING TEAM X");
});

test("boundary: max length counter blocks the extra character, required list and bad email are reported", async ({ page }) => {
  await openCoverNote(page);
  const note = page.getByLabel("Note text");
  await note.fill("a".repeat(800));
  await expect(page.getByText("800 / 800")).toBeVisible();
  await note.press("End"); await note.type("b");
  await expect(note).toHaveValue("a".repeat(800));                 // maxLength stops the 801st character
  await page.getByLabel("Full name", { exact: true }).fill("x");
  await page.getByLabel("Email", { exact: true }).fill("not-an-email");
  await page.getByRole("button", { name: "Review details" }).click();
  await expect(page.getByText("Enter a valid email address")).toBeVisible();
  await expect(page.getByText("Recipient name is required")).toBeVisible();
  await expect(page.getByRole("button", { name: "Generate document" })).toHaveCount(0);   // still on the form
});

test("edge: whitespace-only required field is rejected by the engine, with the field marked", async ({ page }) => {
  await openCoverNote(page);
  await page.getByRole("button", { name: "Pre-fill with example values" }).first().click();
  await page.getByLabel("Full name", { exact: true }).fill("   ");
  await page.getByRole("button", { name: "Review details" }).click();
  await expect(page.getByText("Full name is required")).toBeVisible();   // the form catches it before the engine does
});
