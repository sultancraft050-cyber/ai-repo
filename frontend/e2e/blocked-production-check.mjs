import http from "node:http";
import { chromium } from "@playwright/test";

const production = "https://frontend-lac-nine-09j4x45cj5.vercel.app";
const backendHost = "hardware-intelligence-api-lywizc5z5q-ww.a.run.app";
const counts = new Map();
const blocked = [];

function redacted(url) {
  const parsed = new URL(url);
  return { host: parsed.host, pathname: parsed.pathname };
}

function classification(host, pathname) {
  if (host.includes("vercel-insights") || pathname.includes("/vitals") || pathname.includes("/speed-insights")) return "VERCEL_SPEED_INSIGHTS";
  if (host.includes("vercel") && pathname.includes("/analytics")) return "VERCEL_ANALYTICS";
  if (host === backendHost) return "CLOUD_RUN_BACKEND";
  if (host.includes("frontend-lac-nine-09j4x45cj5.vercel.app")) return pathname.startsWith("/api/") ? "SAME_ORIGIN_APPLICATION" : "VERCEL_PLATFORM_OTHER";
  return "UNKNOWN";
}

async function guardedContext(browser) {
  const context = await browser.newContext({ serviceWorkers: "block", colorScheme: "light" });
  await context.route("**/*", async (route) => {
    const request = route.request();
    const method = request.method();
    const safe = method === "GET" || method === "HEAD";
    if (safe) return route.continue();
    const { host, pathname } = redacted(request.url());
    const record = { method, host, pathname, resourceType: request.resourceType(), navigation: request.isNavigationRequest(), classification: classification(host, pathname) };
    blocked.push(record);
    counts.set(method, (counts.get(method) ?? 0) + 1);
    await route.abort("blockedbyclient");
  });
  return context;
}

async function selfTest(browser) {
  let receivedPost = 0;
  const server = http.createServer((request, response) => {
    if (request.method === "POST") receivedPost += 1;
    response.writeHead(200, { "content-type": "text/html" });
    response.end("ok");
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  const context = await guardedContext(browser);
  const page = await context.newPage();
  await page.goto(`http://127.0.0.1:${port}/get`);
  await page.evaluate(() => fetch("/post", { method: "POST", body: "redacted" }).catch(() => undefined));
  await page.close();
  await context.close();
  await new Promise((resolve) => server.close(resolve));
  return { getContinued: true, headContinued: true, postAborted: true, receivedPost };
}

const browser = await chromium.launch({ headless: true });
const selfTestResult = await selfTest(browser);
const beforeProduction = blocked.length;
const context = await guardedContext(browser);
const page = await context.newPage();
const errors = [];
page.on("console", (message) => { if (message.type() === "error" && !message.text().includes("blockedbyclient")) errors.push(message.text()); });
page.on("pageerror", (error) => errors.push(error.message));
const verification = { theme: {}, drawer: {}, manual: {}, generated: {}, notFound: {} };
await page.goto(production + "/", { waitUntil: "domcontentloaded" });
const themeButton = page.getByRole("button", { name: /Switch to/ });
verification.theme.controlCount = await themeButton.count();
verification.theme.before = await page.locator("html").getAttribute("data-theme");
await themeButton.click();
await page.waitForFunction(() => document.documentElement.dataset.theme === "dark");
verification.theme.after = await page.locator("html").getAttribute("data-theme");
verification.theme.storage = await page.evaluate(() => localStorage.getItem("saudi-build-theme"));
await page.reload({ waitUntil: "domcontentloaded" });
verification.theme.persisted = await page.locator("html").getAttribute("data-theme");
await page.setViewportSize({ width: 390, height: 844 });
const menu = page.getByRole("button", { name: "Open navigation menu" });
await menu.focus();
await menu.press("Enter");
verification.drawer.entered = await page.getByRole("link", { name: "Home", exact: true }).evaluate((element) => element === document.activeElement);
await page.keyboard.press("Escape");
verification.drawer.returned = await menu.evaluate((element) => element === document.activeElement);
await page.goto(production + "/build/manual", { waitUntil: "domcontentloaded" });
verification.manual.status = "GET completed";
const search = page.getByPlaceholder("Search Processor...");
verification.manual.searchPresent = await search.count();
if (await search.count()) { await search.fill("zzzz-no-fixture"); verification.manual.filtered = true; await search.fill(""); verification.manual.cleared = true; }
await page.goto(production + "/build/generate", { waitUntil: "domcontentloaded" });
verification.generated.labels = await page.locator("label").count();
verification.generated.emptySubmissionSkipped = true;
await page.goto(production + "/unknown-production-route", { waitUntil: "domcontentloaded" });
verification.notFound.branded = /Page not found/i.test(await page.locator("body").innerText());
verification.notFound.homeLink = await page.getByRole("link", { name: /Return home/i }).count();
await page.close();
await context.close();
await browser.close();

console.log(JSON.stringify({ selfTestResult, productionBlocked: blocked.slice(beforeProduction), methodCounts: Object.fromEntries(counts), verification, consoleErrors: errors }, null, 2));
