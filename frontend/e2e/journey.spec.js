// The whole user journey through the real UI, real API, real MongoDB and the real computer-vision pipeline:
// register → add project → add photo → photo analysis page (result, every CV step, how the answer was found, PDF)
// → confirm / adjust the stage → estimated completion on the project page.
import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const photo = (name) => path.resolve("../demo_photos", name);
const isPdf = async (download) => fs.readFileSync(await download.path()).subarray(0, 4).toString() === "%PDF";

test("add a project, add photos, see the computer-vision analysis, get the estimated completion", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

  // 1. sign-up (unauthenticated visitors land on the sign-in page)
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByRole("link", { name: "Create one" }).click();
  await page.getByLabel("Name").fill("E2E Student");
  await page.getByLabel("Email").fill(`e2e-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "No projects yet" })).toBeVisible();

  // 2. add a project (with client-side validation first)
  await page.getByRole("link", { name: "+ Add project" }).first().click();
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByText("Name needs at least 3 characters.")).toBeVisible();
  await page.getByLabel("Project name").fill("E2E Green Park Tower");
  await page.getByLabel("Location").fill("Ahmedabad, Gujarat");
  await page.getByLabel("Start date").fill("2025-01-01");
  await page.getByLabel("Planned finish date").fill("2026-12-31");
  await page.getByLabel("Project details (optional)").fill("14-storey residential tower");
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("heading", { name: "E2E Green Park Tower" })).toBeVisible();
  await expect(page.getByText("No estimate yet")).toBeVisible();

  // 3. first photo → its analysis page: CV result, all 19 pipeline steps, the derivation, the PDF
  await page.locator('input[type="file"]').setInputFiles(photo("building_2_excavation.jpg"));
  await page.getByLabel("Date the photo was taken").fill("2025-06-10");
  await page.getByRole("button", { name: "Analyse photo" }).click();
  await expect(page.getByRole("heading", { name: "Photo analysis · 10 Jun 2025" })).toBeVisible({ timeout: 60_000 });
  await expect(page.locator("#result")).toContainText("Computer vision suggests");
  await expect(page.locator("#stage")).toHaveValue("site_preparation");
  await expect(page.locator(".step")).toHaveCount(19);
  await expect(page.locator(".step").filter({ hasText: "Canny edge detector" })).toContainText("cv2.Canny");
  await expect(page.getByRole("heading", { name: "How we got the answer" })).toBeVisible();
  await expect(page.locator("table.path tr")).toHaveCount(19);
  await expect(page.getByRole("heading", { name: "8. Completion date" })).toBeVisible();
  const [analysisPdf] = await Promise.all([page.waitForEvent("download"),
    page.getByRole("link", { name: "Download analysis report (PDF)" }).first().click()]);
  expect(await isPdf(analysisPdf)).toBe(true);
  await page.getByRole("button", { name: "Confirm & save" }).click();
  await expect(page.locator("#result .badge.ok", { hasText: "Confirmed" })).toBeVisible();
  await page.getByRole("link", { name: "Back to project" }).click();
  await expect(page.getByText("Photos (1)")).toBeVisible();

  // 4. second photo: 20 steps (change detection against the first), adjust the stage → live estimate → save
  await page.locator('input[type="file"]').setInputFiles(photo("building_6_structure-formwork.jpg"));
  await page.getByLabel("Date the photo was taken").fill("2026-03-20");
  await page.getByRole("button", { name: "Analyse photo" }).click();
  await expect(page.locator(".step")).toHaveCount(20, { timeout: 60_000 });
  await expect(page.locator(".step").last()).toContainText("Change since the previous photo");
  await page.locator("#stage").selectOption("structural_frame");
  await page.getByLabel("Not sure how much of this stage is done").uncheck();
  await page.locator("#pct").fill("40");
  await expect(page.locator("#estimate")).toContainText("Estimated completion if you save");
  await expect(page.locator("#estimate")).toContainText("39.0%");
  await page.locator("#save").click();
  await expect(page.locator("#result")).toContainText("Structural frame · 40%");
  await page.getByRole("link", { name: "Back to project" }).click();

  // 5. the project now shows progress (0.10 + 0.15 + 0.35 × 0.40) and an estimated completion date
  await expect(page.getByText("Photos (2)")).toBeVisible();
  await expect(page.locator(".big").nth(1)).toHaveText("39.0%");
  await expect(page.getByText("Work left")).toBeVisible();
  await expect(page.locator(".chart svg circle.dot")).toHaveCount(2);

  // 6. the project PDF report downloads
  const [projectPdf] = await Promise.all([page.waitForEvent("download"),
    page.getByRole("link", { name: "Download project report (PDF)" }).click()]);
  expect(await isPdf(projectPdf)).toBe(true);

  // 7. the project list shows the progress; deleting the project removes it
  await page.getByRole("link", { name: "← My projects" }).click();
  await expect(page.locator(".project-card")).toContainText("39.0%");
  await page.locator(".project-card").click();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Delete project" }).click();
  await expect(page.getByRole("heading", { name: "No projects yet" })).toBeVisible();

  expect(errors).toEqual([]);
});

test("the API rejects unauthenticated requests", async ({ request }) => {
  expect((await request.get("/api/projects")).status()).toBe(401);
  expect((await request.get("/api/observations/0123456789abcdef0123456789abcdef/report.pdf")).status()).toBe(401);
  expect((await request.get("/api/auth/session")).status()).toBe(200);
});
