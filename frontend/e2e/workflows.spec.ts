import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
import { categories, completeness, generatedBuild, paginatedCpuProducts, product, savedBuild } from "./fixtures/workflows";

async function mockCommon(page: Page) {
  await page.route("**/products/search?*", async (route) => {
    const category = new URL(route.request().url()).searchParams.get("category") ?? "CPU";
    await route.fulfill({ json: [product(category), product(category, "002")] });
  });
  await page.route("**/build/data-completeness?*", (route) => route.fulfill({ json: completeness }));
  await page.route("**/api/compatibility/check", (route) => route.fulfill({ json: { valid: true, checks: [], total_power_draw_w: 450, required_psu_w: 650 } }));
  await page.route("**/api/performance/calculate", (route) => route.fulfill({ json: { expected_fps: 120, one_percent_low_fps: 90 } }));
}

async function expectNoSeriousAxe(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((item) => item.impact === "serious" || item.impact === "critical")).toEqual([]);
}

test("manual builder selects, replaces, removes and retries fixture products", async ({ page }) => {
  let gpuAttempts = 0;
  await mockCommon(page);
  await page.route("**/products/search?*category=GPU*", async (route) => {
    gpuAttempts += 1;
    if (gpuAttempts === 1) await route.fulfill({ status: 500, json: { detail: "Synthetic GPU failure" } });
    else await route.fulfill({ json: [product("GPU")] });
  });
  await page.goto("/build/manual");
  await expect(page.getByRole("button", { name: "Add CPU" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Retry GPU" })).toBeVisible();
  await page.getByRole("button", { name: "Retry GPU" }).click();
  await expect(page.getByRole("button", { name: "Add GPU" })).toBeEnabled();

  await page.getByRole("button", { name: "Add CPU" }).click();
  await page.getByRole("button", { name: "Add to build" }).first().click();
  await expect(page.getByText("Fixture CPU 001").first()).toBeVisible();
  await page.getByRole("button", { name: "Change CPU" }).click();
  await page.getByPlaceholder("Search Processor...").fill("002");
  await page.getByRole("button", { name: "Add to build" }).click();
  await expect(page.getByText("Fixture CPU 002").first()).toBeVisible();
  await page.getByRole("button", { name: "Remove CPU" }).click();
  await expect(page.getByRole("button", { name: "Add CPU" })).toBeVisible();
  await expectNoSeriousAxe(page);
});

test("manual builder renders missing price and vendor safely", async ({ page }) => {
  await mockCommon(page);
  await page.route("**/products/search?*category=CPU*", (route) => route.fulfill({ json: [product("CPU", "missing", { cheapest_price_sar: null, current_recommended_price: null, cheapest_vendor: null, current_recommended_vendor: null })] }));
  await page.goto("/build/manual");
  await page.getByRole("button", { name: "Add CPU" }).click();
  await expect(page.getByText("Price not listed yet")).toBeVisible();
  await expect(page.locator("body")).not.toContainText(/undefined|null|NaN/);
});

test.describe("manual builder pagination edge cases", () => {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 768, height: 1024 }, { width: 390, height: 844 }]) {
    test(`loads deterministic second page without duplicates at ${viewport.width}px`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await mockCommon(page);
      await page.route("**/products/search?*category=CPU*", async (route) => {
        const offset = Number(new URL(route.request().url()).searchParams.get("offset") ?? 0);
        await route.fulfill({ json: paginatedCpuProducts.slice(offset, offset + 24) });
      });
      await page.goto("/build/manual");
      await page.getByRole("button", { name: "Add CPU" }).click();
      await expect(page.getByRole("button", { name: "Load more products" })).toBeVisible();
      await page.getByRole("button", { name: "Load more products" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(page.getByRole("dialog").locator("article h4", { hasText: "Fixture CPU 001" })).toHaveCount(1);
      if (viewport.width > 390) {
        await page.getByPlaceholder("Search Processor...").fill("030");
        await expect(page.getByRole("dialog").locator("article h4", { hasText: "Fixture CPU 001" })).toHaveCount(0);
      }
    });
  }
});

test("generated builder validates locally and renders success and server errors", async ({ page }) => {
  await mockCommon(page);
  let status = 200;
  await page.route("**/build/generate-local", async (route) => {
    if (status === 200) await route.fulfill({ json: generatedBuild });
    else await route.fulfill({ status, json: { detail: status === 429 ? "Please wait before trying again." : "Unable to generate this build." } });
  });
  await page.goto("/build/generate");
  const budget = page.getByLabel("Budget in SAR");
  await budget.fill("-1");
  await expect(page.getByRole("button", { name: "Generate Saudi Build" })).toBeDisabled();
  await budget.fill("7000");
  await page.getByRole("button", { name: "Generate Saudi Build" }).click();
  await expect(page.getByText("Fixture Saudi Build").first()).toBeVisible();
  status = 429;
  await page.getByRole("button", { name: "Generate Saudi Build" }).click();
  await expect(page.getByText(/wait|details need review/i).first()).toBeVisible();
  await expectNoSeriousAxe(page);
});

for (const failure of [
  { name: "HTTP 400", status: 400, detail: "Check the submitted build preferences." },
  { name: "HTTP 500", status: 500, detail: "Build service is temporarily unavailable." },
]) {
  test(`generated builder sanitizes ${failure.name}`, async ({ page }) => {
    await mockCommon(page);
    await page.route("**/build/generate-local", (route) => route.fulfill({ status: failure.status, json: { detail: failure.detail } }));
    await page.goto("/build/generate");
    await page.getByRole("button", { name: "Generate Saudi Build" }).click();
    await expect(page.getByText(/details need review/i).first()).toBeVisible();
    await expect(page.locator("body")).not.toContainText(/Traceback|localhost|127\.0\.0\.1/);
  });
}

test("generated builder handles no-result, malformed and network failure states", async ({ page }) => {
  await mockCommon(page);
  let mode: "none" | "malformed" | "network" = "none";
  await page.route("**/build/generate-local", async (route) => {
    if (mode === "network") await route.abort("connectionfailed");
    else if (mode === "malformed") await route.fulfill({ json: { builds: [{}] } });
    else await route.fulfill({ json: { ...generatedBuild, build_status: "no_valid_build", builds: [], missing_data_warnings: ["No compatible fixture combination."] } });
  });
  await page.goto("/build/generate");
  const generate = page.getByRole("button", { name: "Generate Saudi Build" });
  await generate.click();
  await expect(page.getByText("No compatible build found")).toBeVisible();
  mode = "malformed";
  await generate.click();
  await expect(page.getByText(/details need review/i).first()).toBeVisible();
  mode = "network";
  await generate.click();
  await expect(page.getByText(/details need review/i).first()).toBeVisible();
});

test("generated builder renders a dedicated incomplete-build state", async ({ page }) => {
  await mockCommon(page);
  const incomplete = { ...generatedBuild, build_status: "incomplete_data", builds: [{ ...generatedBuild.builds[0], components: generatedBuild.builds[0].components.filter((item) => ["CPU", "GPU", "RAM", "PSU"].includes(item.category)), summary: { ...generatedBuild.builds[0].summary, total_recommended_price_sar: null, compatibility_status: "incomplete", warning_summary: ["Motherboard and storage are missing."] } }], missing_data_warnings: ["Motherboard, storage, and case need review."] };
  await page.route("**/build/generate-local", (route) => route.fulfill({ json: incomplete }));
  await page.goto("/build/generate");
  await page.getByRole("button", { name: "Generate Saudi Build" }).click();
  await expect(page.getByText("Some data needs review")).toBeVisible();
  await expect(page.getByText(/Motherboard, storage, and case/)).toBeVisible();
  await expect(page.locator("body")).not.toContainText(/undefined|null|NaN|Traceback/);
  await expectNoSeriousAxe(page);
});

test("shared build renders success and failure fixtures", async ({ page }) => {
  await page.route("**/build/share/*", (route) => route.request().resourceType() === "document" ? route.continue() : route.fulfill({ json: savedBuild }));
  await page.goto("/build/share/fixture-share-001");
  await expect(page.getByRole("heading", { name: "Fixture Shared Saudi Build" })).toBeVisible();
  await expect(page.getByText("SAR only")).toBeVisible();
  await expectNoSeriousAxe(page);
  await page.unroute("**/build/share/*");
  await page.route("**/build/share/*", (route) => route.request().resourceType() === "document" ? route.continue() : route.fulfill({ status: 404, json: { detail: "Shared build not found" } }));
  await page.goto("/build/share/missing-fixture");
  await expect(page.getByText("Shared build not available")).toBeVisible();
  await expect(page.getByRole("link", { name: "Start a new build" })).toBeVisible();
});

for (const viewport of [{ name: "laptop", width: 1280, height: 800 }, { name: "tablet", width: 768, height: 1024 }]) {
  test(`${viewport.name} critical layout has no horizontal overflow`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await mockCommon(page);
    await page.goto("/build/manual");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await expect(page.getByRole("button", { name: /Switch to/ })).toBeVisible();
  });
}

test("axe scans home themes, open mobile navigation and 404", async ({ page }) => {
  await page.goto("/");
  await expectNoSeriousAxe(page);
  await page.getByRole("button", { name: /Switch to/ }).click();
  await expectNoSeriousAxe(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation menu" }).click();
  await expectNoSeriousAxe(page);
  await page.goto("/fixture-not-found");
  await expectNoSeriousAxe(page);
});

test("mobile drawer contains focus and returns it after close", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const menu = page.getByRole("button", { name: "Open navigation menu" });
  await menu.focus();
  await menu.press("Enter");
  await expect(page.getByRole("link", { name: "Home", exact: true })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(page.getByRole("link", { name: "Feedback", exact: true })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Open navigation menu" })).toBeFocused();
});

test("reduced motion keeps theme, drawer and loading interactions functional", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByRole("button", { name: /Switch to/ })).toBeVisible();
  await page.getByRole("button", { name: /Switch to/ }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation menu" }).click();
  await expect(page.getByRole("navigation", { name: "Mobile navigation" })).toBeVisible();
  await expect(page).toHaveTitle(/Saudi PC Build Assistant/);
  expect(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(true);
});
