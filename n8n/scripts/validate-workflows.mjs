import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");

function readWorkflow(name) {
  return JSON.parse(readFileSync(join(root, "workflows", name), "utf8"));
}

const importWorkflow = readWorkflow("telegram-product-url-import.json");
const refreshWorkflow = readWorkflow("nightly-known-url-refresh.json");

function findNode(workflow, name) {
  return workflow.nodes.find((node) => node.name === name);
}

function workflowText(workflow) {
  return JSON.stringify(workflow);
}

function sanitizeUrl(rawUrl) {
  const parsed = new URL(rawUrl);
  parsed.hash = "";
  const removable = new Set(["fbclid", "gclid", "msclkid", "_hsenc", "_hsmi", "ref", "tag", "spm", "scm"]);
  for (const key of [...parsed.searchParams.keys()]) {
    if (key.toLowerCase().startsWith("utm_") || removable.has(key.toLowerCase())) {
      parsed.searchParams.delete(key);
    }
  }
  return parsed.toString();
}

function inferSource(hostname) {
  const host = hostname.toLowerCase().replace(/^www\./, "");
  if (host === "pczonesa.com" || host.endsWith(".pczonesa.com")) return "PCZone Saudi";
  if (host === "microless.com" || host.endsWith(".microless.com")) return "Microless Saudi";
  if (host === "mtc.com.sa" || host.endsWith(".mtc.com.sa") || host === "mtcsaudi.com") return "MTC KSA";
  if (host === "noon.com" || host.endsWith(".noon.com")) return "Noon Saudi";
  if (host === "amazon.sa" || host.endsWith(".amazon.sa")) return "Amazon.sa";
  return null;
}

function inferCategory(url) {
  const slug = `${url.hostname} ${url.pathname}`.toLowerCase();
  const checks = [
    ["Motherboard", /motherboard|\bb650\b|\bb760\b|\bx670\b|\ba620\b/],
    ["GPU", /\bgpu\b|graphics|\bvga\b|\brtx\b|radeon|\brx-/],
    ["CPU", /\bcpu\b|processor|ryzen|intel-core/],
    ["RAM", /\bram\b|memory|\bddr5\b|\bddr4\b/],
    ["Storage", /\bssd\b|\bnvme\b|\bm2\b|storage/],
    ["PSU", /\bpsu\b|power-supply|\b850w\b|\b750w\b/],
    ["Case", /\bcase\b|chassis|tower/],
    ["Cooler", /cooler|\baio\b|heatsink|thermalright|kraken/],
  ];
  return (checks.find(([, pattern]) => pattern.test(slug)) || [null])[0];
}

function stableHash(value) {
  let hash = 5381;
  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash << 5) + hash) ^ value.charCodeAt(index);
  }
  return (hash >>> 0).toString(16);
}

function prepareMessage({ text, chatId, founderChatId }) {
  if (String(chatId) !== String(founderChatId)) return { status: "unauthorized" };
  const categoryCommand = text.match(/^(Motherboard|GPU|CPU|RAM|Storage|PSU|Case|Cooler)\s+(https?:\/\/\S+)/i);
  const explicitCategory = categoryCommand ? categoryCommand[1].replace(/^gpu$/i, "GPU").replace(/^cpu$/i, "CPU").replace(/^ram$/i, "RAM").replace(/^psu$/i, "PSU") : null;
  const urlMatch = text.match(/https?:\/\/[^\s<>"']+/i);
  if (!urlMatch) return { status: "url_required" };
  let url;
  try {
    url = sanitizeUrl(urlMatch[0]);
  } catch {
    return { status: "invalid_url" };
  }
  const parsed = new URL(url);
  const source = inferSource(parsed.hostname);
  if (!source) return { status: "unsupported_domain", url };
  const category = explicitCategory || inferCategory(parsed);
  if (!category) return { status: "category_required", url, source };
  return { status: "ready", url, source, category, normalizedUrlHash: stableHash(url) };
}

function previewCanIngest(preview) {
  const sourcePolicy = String(preview.source_policy_status || "").toLowerCase();
  const price = preview.item_price_sar ?? preview.price ?? null;
  const hasPrice = price !== null && price !== undefined && String(price).trim() !== "";
  return preview.accepted === true && hasPrice && !["blocked", "unsupported"].includes(sourcePolicy);
}

assert.ok(findNode(importWorkflow, "Telegram Trigger"), "telegram trigger exists");
assert.ok(findNode(importWorkflow, "Preview Product URL"), "preview HTTP node exists");
assert.ok(findNode(importWorkflow, "Ingest Approved Product URL"), "ingest HTTP node exists");
assert.ok(findNode(refreshWorkflow, "Daily 3 AM Riyadh"), "nightly schedule exists");
assert.ok(findNode(refreshWorkflow, "Refresh Known Product URLs"), "refresh HTTP node exists");

const importText = workflowText(importWorkflow);
const refreshText = workflowText(refreshWorkflow);

assert.match(importText, /\/sources\/product-url\/preview/, "uses existing preview endpoint");
assert.match(importText, /\/sources\/product-url\/ingest/, "uses existing ingest endpoint");
assert.match(importText, /X-Idempotency-Key/, "uses stable idempotency header");
assert.match(importText, /FOUNDER_TELEGRAM_CHAT_ID/, "uses founder allowlist env var");
assert.match(importText, /ADMIN_API_KEY/, "uses admin key env var");
assert.doesNotMatch(importText, /\/pricing\/import-url/, "does not call deprecated import endpoint");
assert.doesNotMatch(refreshText, /\/pricing\/known-url-refresh/, "does not call deprecated refresh endpoint");
assert.match(refreshText, /\/sources\/product-url\/refresh/, "uses existing refresh endpoint");
assert.match(refreshText, /limit:\s*50/, "refresh limit is 50");
assert.equal(refreshWorkflow.settings.timezone, "Asia/Riyadh");

const schedule = findNode(refreshWorkflow, "Daily 3 AM Riyadh");
assert.equal(schedule.parameters.rule.interval[0].triggerAtHour, 3);
assert.equal(schedule.parameters.rule.interval[0].triggerAtMinute, 0);

const pcZone = prepareMessage({
  chatId: "123",
  founderChatId: "123",
  text: "https://www.pczonesa.com/en/category/motherboard/asus-prime-b650m-a-wifi-ii/?utm_source=test&fbclid=x",
});
assert.equal(pcZone.status, "ready");
assert.equal(pcZone.category, "Motherboard");
assert.equal(pcZone.source, "PCZone Saudi");
assert.equal(pcZone.url, "https://www.pczonesa.com/en/category/motherboard/asus-prime-b650m-a-wifi-ii/");

assert.equal(
  pcZone.normalizedUrlHash,
  stableHash("https://www.pczonesa.com/en/category/motherboard/asus-prime-b650m-a-wifi-ii/"),
  "idempotency hash is stable after tracking params are stripped",
);

assert.equal(
  prepareMessage({ chatId: "999", founderChatId: "123", text: pcZone.url }).status,
  "unauthorized",
);
assert.equal(
  prepareMessage({ chatId: "123", founderChatId: "123", text: "https://example.com/product/thing" }).status,
  "unsupported_domain",
);
assert.equal(
  prepareMessage({ chatId: "123", founderChatId: "123", text: "https://www.pczonesa.com/en/category/accessory/mystery-product/" }).status,
  "category_required",
);
assert.equal(
  prepareMessage({ chatId: "123", founderChatId: "123", text: "GPU https://www.pczonesa.com/en/category/graphics/rtx-4070/" }).category,
  "GPU",
);

assert.equal(previewCanIngest({ accepted: true, item_price_sar: 799, source_policy_status: "allowed" }), true);
assert.equal(previewCanIngest({ accepted: false, item_price_sar: 799, source_policy_status: "allowed" }), false);
assert.equal(previewCanIngest({ accepted: true, source_policy_status: "allowed" }), false);
assert.equal(previewCanIngest({ accepted: true, item_price_sar: 799, source_policy_status: "blocked" }), false);

for (const text of [importText, refreshText]) {
  assert.doesNotMatch(text, /bot\d+:[A-Za-z0-9_-]{20,}/, "no Telegram bot token literal");
  assert.doesNotMatch(text, /sk-[A-Za-z0-9]{20,}/, "no API secret literal");
  assert.doesNotMatch(text, /neo4j\+s:\/\/[^"]+:[^"]+@/, "no Neo4j credentials literal");
}

console.log("n8n workflow validation passed");
