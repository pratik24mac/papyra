import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page) {
  await page.goto("/");
  await page.getByPlaceholder("Username").fill("admin");
  await page.getByPlaceholder("Password").fill("DocMaster!2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Good", { exact: false })).toBeVisible();
}

test("rejects a wrong password and accepts the right one", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder("Username").fill("admin");
  await page.getByPlaceholder("Password").fill("nope");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Incorrect username or password.")).toBeVisible();
  await page.getByPlaceholder("Password").fill("DocMaster!2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Engine ready")).toBeVisible();
});

test("full wizard: template → form → review → generate → preview → email draft", async ({ page }) => {
  await signIn(page);
  await page.locator(".tile", { hasText: "New document" }).click();
  await page.getByRole("button", { name: "Use this template" }).click();
  // validation blocks an empty form
  await page.getByRole("button", { name: "Review details" }).click();
  await expect(page.getByText("Full name is required")).toBeVisible();
  await page.getByRole("button", { name: "Load example values" }).click();
  await expect(page.getByLabel("Full name")).toHaveValue("Asha Verma");
  await page.getByRole("button", { name: "Review details" }).click();
  await expect(page.getByText("Resume — Asha Verma")).toBeVisible();      // default expanded
  await page.getByRole("button", { name: "Generate document" }).click();
  await expect(page.getByText("Document generated")).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: "Preview PDF" }).click();
  await expect(page.locator("[data-testid=pdf-pages] canvas")).toHaveCount(2, { timeout: 15_000 });
  await page.getByRole("button", { name: "Continue to email" }).click();
  await expect(page.getByLabel("To", { exact: true })).toHaveValue("hiring@example.com");
  await page.getByRole("button", { name: "Create draft…" }).click();
  const dialog = page.getByRole("dialog").filter({ hasText: "Create the email draft?" });
  await expect(dialog).toBeVisible();
  await dialog.locator("button", { hasText: /^Create draft$/ }).click();
  await expect(page.getByText("Email file saved")).toBeVisible({ timeout: 10_000 });
});

test("stale PDF blocks preview actions until regenerated", async ({ page }) => {
  await signIn(page);
  await page.locator(".tile", { hasText: "New document" }).click();
  await page.getByRole("button", { name: "Use this template" }).click();
  await page.getByRole("button", { name: "Load example values" }).click();
  await page.getByRole("button", { name: "Review details" }).click();
  await page.getByRole("button", { name: "Generate document" }).click();
  await page.getByRole("button", { name: "Preview PDF" }).click({ timeout: 10_000 });
  await page.evaluate(() => { (window as unknown as { __mockStale: boolean }).__mockStale = true; window.dispatchEvent(new Event("focus")); });
  await expect(page.getByText("The Word document was changed after this PDF was created")).toBeVisible();
  await expect(page.locator("button", { hasText: /^Open PDF$/ })).toBeDisabled();
  await page.getByRole("button", { name: "Regenerate PDF" }).click();
  await expect(page.locator("[data-testid=pdf-pages] canvas")).toHaveCount(2, { timeout: 15_000 });
});

test("settings: mailbox connect, output folder, privacy toggles", async ({ page }) => {
  await signIn(page);
  await page.locator(".tile", { hasText: "Settings" }).click();
  await page.getByPlaceholder("you@yourdomain.com").fill("me@porkbun-domain.com");
  await page.getByLabel("Password").fill("wrong");
  await page.getByRole("button", { name: "Test connection" }).click();
  await expect(page.getByText("Mailbox sign-in failed", { exact: false })).toBeVisible();
  await page.getByLabel("Password").fill("secret-pw");
  await page.locator("button", { hasText: /^Connect$/ }).click();
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Choose folder…" }).click();
  await expect(page.getByText("/Users/you/Desktop/Generated documents").first()).toBeVisible();
  const offline = page.getByRole("switch").first();
  await expect(offline).toBeChecked();                                               // offline by default
  await expect(page.getByRole("button", { name: /Check mail server reachability/ })).toBeDisabled();
  await offline.click();                                                             // user opts in to network
  await page.getByRole("button", { name: /Check mail server reachability/ }).click();
  await expect(page.getByText("Mail server reachable", { exact: false })).toBeVisible({ timeout: 10_000 });
});

test("a broken user template is listed as needs fixing, not hidden", async ({ page }) => {
  await signIn(page);
  await page.locator(".tile", { hasText: "New document" }).click();
  const card = page.locator(".ant-card", { hasText: "Offer letter" });
  await expect(card.getByText("needs fixing")).toBeVisible();
  await expect(card.getByText("M001", { exact: false })).toBeVisible();
  await expect(card.getByRole("button", { name: "Open folder to fix" })).toBeVisible();
  await expect(card.getByRole("button", { name: "Use this template" })).toHaveCount(0);
  await page.getByRole("button", { name: "Rescan templates" }).click();
  await expect(page.locator(".ant-card", { hasText: "Resume (ATS-friendly)" }).getByRole("button", { name: "Use this template" })).toBeVisible();
});
