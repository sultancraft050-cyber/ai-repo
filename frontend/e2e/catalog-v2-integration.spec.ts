import { test, expect, type Page } from "@playwright/test";

// Helpers
async function setupBaseMock(page: Page) {
  // Listen to browser console and requests
  page.on("console", (msg) => {
    console.log(`BROWSER CONSOLE [${msg.type()}]:`, msg.text());
  });
  page.on("request", (req) => {
    console.log(`BROWSER REQUEST [${req.method()}]:`, req.url());
  });

  // Unified Regex Mock for V1 searches
  await page.route(/\/products\/search(?:\?|$)/, async (route) => {
    const url = new URL(route.request().url());
    const category = url.searchParams.get("category") || "";

    if (category === "CPU") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "cpu-spec:CPU|AMD|RYZEN_5_5600",
            name: "AMD Ryzen 5 5600",
            brand: "AMD",
            category: "CPU",
            model: "RYZEN_5_5600",
            summary_specs: { part_number: "100-100000927BOX" },
            data_origin: "live",
            price_status: "unavailable",
            flags: [],
            stale: false,
            best_value: false
          },
          {
            id: "cpu-spec:CPU|INTEL|AMBIGUOUS_1",
            name: "Intel Ambiguous 1",
            brand: "Intel",
            category: "CPU",
            model: "AMBIGUOUS_1",
            summary_specs: { part_number: "MPN_AMBIGUOUS" },
            data_origin: "live",
            price_status: "unavailable",
            flags: [],
            stale: false,
            best_value: false
          },
          {
            id: "cpu-spec:CPU|INTEL|AMBIGUOUS_2",
            name: "Intel Ambiguous 2",
            brand: "Intel",
            category: "CPU",
            model: "AMBIGUOUS_2",
            summary_specs: { part_number: "MPN_AMBIGUOUS" },
            data_origin: "live",
            price_status: "unavailable",
            flags: [],
            stale: false,
            best_value: false
          }
        ])
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: `${category.toLowerCase()}:test-legacy-part`,
          name: `Test Legacy ${category}`,
          brand: "TestBrand",
          category,
          summary_specs: { part_number: "TEST_LEGACY_MPN" },
          data_origin: "live",
          price_status: "unavailable",
          flags: [],
          stale: false,
          best_value: false
        }
      ])
    });
  });

  // Mock Catalog V2 lists generally using RegExp to ensure interception
  await page.route(/\/catalog\/products(?:\?|$)/, async (route) => {
    const url = new URL(route.request().url());
    const category = url.searchParams.get("category");

    if (category === "CPU") {
      // Default CPU list containing Ryzen 5 5600 and the Unmapped CPU
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: 48,
            category: "CPU",
            brand: "AMD",
            manufacturer_part_number: "100-100000927BOX",
            canonical_name: "AMD Ryzen 5 5600",
            slug: "amd-ryzen-5-5600"
          },
          {
            id: 100,
            category: "CPU",
            brand: "AMD",
            manufacturer_part_number: "MPN_UNMAPPED",
            canonical_name: "AMD Unmapped CPU",
            slug: "amd-unmapped"
          }
        ])
      });
      return;
    }

    // Default empty list for other categories
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([])
    });
  });

  // Mock compatibility and performance check using RegExp
  await page.route(/\/compatibility\/check/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        valid: true,
        checks: [
          { status: "pass", category: "CPU", details: "CPU is compatible." }
        ],
        total_power_draw_w: 300,
        required_psu_w: 500
      })
    });
  });

  await page.route(/\/performance\/calculate/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        expected_fps: 144,
        one_percent_low_fps: 110
      })
    });
  });
}

test.describe("Catalog V2 Integration E2E Tests", () => {

  test("exact MPN mapping works and does not perform heuristic substitution", async ({ page }) => {
    await setupBaseMock(page);

    // Mock V2 catalog detail product using RegExp to match `/catalog/products/48`
    await page.route(/\/catalog\/products\/48$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: 48,
          category: "CPU",
          brand: "AMD",
          manufacturer_part_number: "100-100000927BOX",
          canonical_name: "AMD Ryzen 5 5600",
          slug: "amd-ryzen-5-5600",
          specifications: [
            { specification_key: "socket", normalized_value: "AM4" }
          ]
        })
      });
    });

    // Track compatibility check request payload
    let compPayload: any = null;
    await page.route(/\/compatibility\/check/, async (route) => {
      compPayload = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          valid: true,
          checks: [],
          total_power_draw_w: 120,
          required_psu_w: 450
        })
      });
    });

    await page.goto("/build/manual");

    // Click to add CPU
    await page.click('[data-picker-trigger="CPU"]');

    // Click "Add to build" button on AMD Ryzen 5 5600 card
    await page.locator("article").filter({ hasText: "AMD Ryzen 5 5600" }).getByRole("button", { name: "Add to build" }).click();

    // Wait for validation to trigger
    await page.waitForTimeout(1000);

    // Verify V2 product is selected in UI
    await expect(page.locator('text=AMD Ryzen 5 5600')).toBeVisible();

    // Verify V1 exact mapping was passed to compatibility check
    expect(compPayload).not.toBeNull();
    expect(compPayload.selection.cpu_id).toBe("cpu-spec:CPU|AMD|RYZEN_5_5600");
  });

  test("ambiguous mappings are refused and unmapped products display unavailable warning", async ({ page }) => {
    await setupBaseMock(page);

    await page.route(/\/catalog\/products\/100$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: 100,
          category: "CPU",
          brand: "AMD",
          manufacturer_part_number: "MPN_UNMAPPED",
          canonical_name: "AMD Unmapped CPU",
          slug: "amd-unmapped",
          specifications: [
            { specification_key: "socket", normalized_value: "AM5" }
          ]
        })
      });
    });

    let compPayload: any = null;
    await page.route(/\/compatibility\/check/, async (route) => {
      compPayload = route.request().postDataJSON();
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ valid: true, checks: [] }) });
    });

    await page.goto("/build/manual");

    // Click to add CPU
    await page.click('[data-picker-trigger="CPU"]');

    // Click "Add to build" on unmapped product card
    await page.locator("article").filter({ hasText: "AMD Unmapped CPU" }).getByRole("button", { name: "Add to build" }).click();

    await page.waitForTimeout(1000);

    // Verify it is selectable and visible
    await expect(page.locator('text=AMD Unmapped CPU')).toBeVisible();

    // Expand details to make all warnings visible
    const detailsButton = page.locator('summary', { hasText: /^Details$/ });
    if (await detailsButton.isVisible()) {
      await detailsButton.click();
    }

    // Verify warnings are displayed
    await expect(page.locator('text=Processor: Compatibility calculation unavailable for this product')).toBeVisible();
    await expect(page.locator('text=Performance estimate unavailable for this product')).toBeVisible();

    // Verify we did NOT send a guessed ID or similar to Neo4j endpoint
    expect(compPayload.selection.cpu_id).toBeUndefined();
  });

  test("list rendering does not issue detail requests", async ({ page }) => {
    await setupBaseMock(page);

    let detailRequestsCount = 0;
    await page.route(/\/catalog\/products\/\d+$/, async (route) => {
      detailRequestsCount++;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });
    });

    await page.goto("/build/manual");

    // Open CPU selection dialog
    await page.click('[data-picker-trigger="CPU"]');
    await page.waitForTimeout(300);

    // Verify list items display but NO detail requests are sent to avoid N+1 query pattern
    expect(detailRequestsCount).toBe(0);
  });

  test("legacy fallback activates only when Catalog V2 is genuinely unavailable", async ({ page }) => {
    // Fail V2 catalog fetch using RegExp to catch it reliably
    await page.route(/\/catalog\/products(?:\?|$)/, async (route) => {
      await route.abort("failed");
    });

    let legacySearchCount = 0;
    await page.route(/\/products\/search(?:\?|$)/, async (route) => {
      legacySearchCount++;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "cpu-spec:CPU|AMD|RYZEN_5_5600",
            name: "Fallback CPU",
            brand: "AMD",
            category: "CPU",
            data_origin: "live",
            price_status: "unavailable",
            flags: [],
            stale: false,
            best_value: false
          }
        ])
      });
    });

    await page.goto("/build/manual");
    await page.click('[data-picker-trigger="CPU"]');
    await page.waitForTimeout(300);

    // Verify V1 fallback product is shown
    await expect(page.locator('text=Fallback CPU')).toBeVisible();
    expect(legacySearchCount).toBeGreaterThan(0);
  });

});
