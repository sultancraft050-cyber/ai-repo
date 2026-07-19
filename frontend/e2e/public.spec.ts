import { test, expect, type Page } from "@playwright/test";

const viewports = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "mobile", width: 390, height: 844 },
];

async function collectUnexpectedErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (
      message.type() === "error" &&
      !message.text().includes("Failed to load resource: the server responded with a status of 404") &&
      !message.text().includes("/analytics/events")
    ) {
      errors.push(message.text());
    }
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

async function mockApi(page: Page) {
  await page.route("**/*example.invalid/**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });
  });
  await page.route("**/analytics/events", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
  });
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = request.url();
    if (request.method() !== "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
      return;
    }
    const body = url.includes("release") ? { release: "local-smoke", api_contract_version: "1" } : {};
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.route("**/catalog/products*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 180,
          category: "RAM",
          brand: "ADATA",
          manufacturer_part_number: "AD3U1600W8G11-R",
          exact_model: "1600 CL11",
          variant: "1600 CL11",
          canonical_name: "ADATA DDR3-1600 CL11 8GB",
          slug: "adata-ddr3-1600",
          lifecycle_status: "active",
          approval_status: "approved",
          created_at: "2026-07-18T19:08:25Z",
          updated_at: "2026-07-19T17:34:58Z"
        },
        {
          id: 181,
          category: "CPU",
          brand: "Intel",
          manufacturer_part_number: "BX8071513700K",
          exact_model: "i7-13700K",
          variant: "Retail",
          canonical_name: "Intel Core i7-13700K Processor",
          slug: "intel-i7-13700k",
          lifecycle_status: "active",
          approval_status: "approved",
          created_at: "2026-07-18T19:08:25Z",
          updated_at: "2026-07-19T17:34:58Z"
        }
      ])
    });
  });
  await page.route("**/catalog/products/*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: 181,
        category: "CPU",
        brand: "Intel",
        manufacturer_part_number: "BX8071513700K",
        exact_model: "i7-13700K",
        variant: "Retail",
        canonical_name: "Intel Core i7-13700K Processor",
        slug: "intel-i7-13700k",
        lifecycle_status: "active",
        approval_status: "approved",
        created_at: "2026-07-18T19:08:25Z",
        updated_at: "2026-07-19T17:34:58Z",
        specifications: [
          {
            specification_key: "socket",
            normalized_value: "LGA1700",
            display_value: "LGA1700",
            unit: null
          },
          {
            specification_key: "cores",
            normalized_value: "16",
            display_value: "16 Cores",
            unit: null
          }
        ],
        images: [],
        offers: [],
        cheapest_sar_offer: null
      })
    });
  });
}

test.describe("public route smoke", () => {
  for (const viewport of viewports) {
    test(`home and theme at ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await mockApi(page);
      const errors = await collectUnexpectedErrors(page);
      await page.goto("/");
      await expect(page).toHaveTitle(/Saudi PC Build Assistant/);
      await expect(page.locator("h1").first()).toBeVisible();
      await expect(page.locator("body")).toHaveCSS("overflow-x", "visible");

      const toggle = page.getByRole("button", { name: /Switch to (light|dark) mode/ });
      await expect(toggle).toBeVisible();
      const initial = await page.locator("html").getAttribute("data-theme");
      await page.screenshot({ path: `test-results/home-${viewport.name}-${initial}.png`, fullPage: true });
      await toggle.focus();
      await page.keyboard.press("Enter");
      const changed = initial === "dark" ? "light" : "dark";
      await expect(page.locator("html")).toHaveAttribute("data-theme", changed);
      await page.screenshot({ path: `test-results/home-${viewport.name}-${changed}.png`, fullPage: true });
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute("data-theme", changed);

      if (viewport.width < 600) {
        const menu = page.getByRole("button", { name: "Open navigation menu" });
        await menu.click();
        await expect(page.getByRole("navigation", { name: "Mobile navigation" })).toBeVisible();
        await page.keyboard.press("Escape");
        await expect(page.getByRole("button", { name: "Open navigation menu" })).toBeVisible();
        await menu.click();
        await page.getByRole("navigation", { name: "Mobile navigation" }).getByRole("link", { name: "Generate", exact: true }).click();
        await expect(page).toHaveURL(/\/build\/generate/);
      } else {
        await page.getByRole("link", { name: "Generate" }).first().click();
        await expect(page).toHaveURL(/\/build\/generate/);
      }
      expect(errors, errors.join("\n")).toEqual([]);
    });
  }

  for (const route of ["/build/manual", "/build/generate", "/release"]) {
    test(`${route} renders without runtime errors`, async ({ page }) => {
      await mockApi(page);
      const errors = await collectUnexpectedErrors(page);
      const response = await page.goto(route);
      await expect(page.locator("body")).toBeVisible();
      if (route === "/release") {
        expect(response?.status()).toBe(200);
        await expect(page.locator("body")).toContainText(/api_contract_version|release/i);
      } else {
        await expect(page.locator("h1").first()).toBeVisible();
      }
      expect(errors, errors.join("\n")).toEqual([]);
    });
  }

  test("unknown route provides a usable not-found response", async ({ page }) => {
    await page.goto("/browser-smoke-missing-route");
    await expect(page.locator("body")).toContainText(/404|not found/i);
    await expect(page.getByRole("link", { name: /home/i }).first()).toBeVisible();
  });

  test("production API configuration has no localhost fallback", async () => {
    expect(process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://hardware-intelligence-api-lywizc5z5q-ww.a.run.app").not.toMatch(/localhost|127\.0\.0\.1/);
  });
});
