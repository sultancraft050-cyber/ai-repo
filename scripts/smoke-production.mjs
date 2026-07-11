#!/usr/bin/env node

import process from "node:process";
import { compareReleaseContracts } from "./release-contract.mjs";

const args = new Map();
for (let index = 2; index < process.argv.length; index += 1) {
  const value = process.argv[index];
  if (!value.startsWith("--")) continue;
  const key = value.slice(2);
  const next = process.argv[index + 1];
  args.set(key, next && !next.startsWith("--") ? next : "true");
  if (next && !next.startsWith("--")) index += 1;
}

const backend = normalizeUrl(args.get("backend") ?? process.env.SMOKE_BACKEND_URL);
const frontend = normalizeUrl(args.get("frontend") ?? process.env.SMOKE_FRONTEND_URL);
const expectedApi = normalizeUrl(args.get("frontend-api") ?? process.env.SMOKE_FRONTEND_API_URL ?? backend);
const shared = normalizeUrl(args.get("shared") ?? process.env.SMOKE_SHARED_BUILD_URL);
const timeoutMs = Number(args.get("timeout-ms") ?? process.env.SMOKE_TIMEOUT_MS ?? 15000);

const results = [];

function normalizeUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (!/^https?:$/.test(url.protocol)) return null;
    url.hash = "";
    return url.toString().replace(/\/$/, "");
  } catch {
    return null;
  }
}

function record(name, status, detail, required = true) {
  results.push({ name, status, detail, required });
  const label = status.toUpperCase().padEnd(9);
  console.log(`${label} ${name}: ${detail}`);
}

async function get(url, name, required = true) {
  if (!url) {
    record(name, "skipped", "URL not configured", required);
    return null;
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method: "GET",
      redirect: "follow",
      signal: controller.signal,
      headers: { Accept: "application/json,text/html,*/*" },
    });
    const body = await response.text();
    return { response, body };
  } catch (error) {
    record(name, "unavailable", error instanceof Error ? error.message : "request failed", required);
    return null;
  } finally {
    clearTimeout(timer);
  }
}

async function scanFrontendAssets(pageUrl, html) {
  const sources = [...html.matchAll(/<script[^>]+src=["']([^"']+)["']/gi)].map((match) => match[1]);
  const uniqueSources = [...new Set(sources)]
    .filter((source) => !source.toLowerCase().includes("polyfills"))
    .slice(0, 40);
  let scanned = 0;
  for (const source of uniqueSources) {
    const assetUrl = new URL(source, pageUrl).toString();
    const result = await get(assetUrl, "frontend.asset", false);
    if (!result) continue;
    scanned += 1;
    if (/https?:\/\/(?:localhost|127\.0\.0\.1)(?::\d+)?/i.test(result.body)) {
      record("frontend.asset-api-target", "fail", `local API target found in ${assetUrl}`);
    }
    if (expectedApi && result.body.includes(expectedApi)) {
      record("frontend.asset-api-target", "pass", "expected API target found in JavaScript asset", false);
    }
  }
  record("frontend.asset-scan", "pass", `${scanned} JavaScript assets scanned`, false);
}

function statusCheck(name, result, allowed, required = true) {
  if (!result) return;
  const code = result.response.status;
  if (allowed.includes(code)) record(name, "pass", `HTTP ${code}`, required);
  else record(name, "fail", `HTTP ${code}`, required);
}

async function run() {
  if (!backend) record("configuration.backend", "fail", "A valid backend URL is required");
  if (!frontend) record("configuration.frontend", "skipped", "Frontend URL not configured", false);
  if (expectedApi && !expectedApi.startsWith("https://")) {
    record("configuration.frontend-api", "fail", "Expected production API must use HTTPS");
  } else if (expectedApi) {
    record("configuration.frontend-api", "pass", "HTTPS API target configured", false);
  }

  const health = await get(backend ? `${backend}/health` : null, "backend.health");
  statusCheck("backend.health", health, [200]);
  if (health) {
    try {
      const payload = JSON.parse(health.body);
      const details = [payload.backend_version, payload.git_sha].filter(Boolean).join(" / ") || "no release metadata";
      record("backend.release", "pass", details, false);
      record("backend.neo4j-status", payload.neo4j === "connected" ? "pass" : "fail", String(payload.neo4j ?? "unknown"));
    } catch {
      record("backend.release", "fail", "Health response was not valid JSON", false);
    }
  }

  let backendRelease = null;
  if (health) {
    try {
      backendRelease = JSON.parse(health.body);
    } catch {
      backendRelease = null;
    }
  }

  const neo4j = await get(backend ? `${backend}/health/neo4j` : null, "backend.health-neo4j");
  statusCheck("backend.health-neo4j", neo4j, [200]);

  const openapi = await get(backend ? `${backend}/openapi.json` : null, "backend.openapi");
  statusCheck("backend.openapi", openapi, [200]);
  if (openapi) {
    try {
      const paths = Object.keys(JSON.parse(openapi.body).paths ?? {});
      const requiredPaths = ["/health", "/build/generate", "/catalog/import/hybrid-review", "/catalog/spec-audit/run", "/catalog/hybrid/integrity"];
      const missing = requiredPaths.filter((path) => !paths.includes(path));
      record("backend.critical-paths", missing.length ? "fail" : "pass", missing.length ? `missing ${missing.join(", ")}` : `${requiredPaths.length} paths present`);
    } catch {
      record("backend.critical-paths", "fail", "OpenAPI response was not valid JSON");
    }
  }

  const protectedRoute = await get(backend ? `${backend}/ops/deployment-checklist?region=SA` : null, "backend.admin-protection");
  statusCheck("backend.admin-protection", protectedRoute, [401, 403]);

  for (const path of ["/", "/build/manual", "/build/generate"]) {
    const result = await get(frontend ? `${frontend}${path}` : null, `frontend${path}`);
    statusCheck(`frontend${path}`, result, [200]);
    if (result && /https?:\/\/(?:localhost|127\.0\.0\.1)(?::\d+)?/i.test(result.body)) {
      record(`frontend${path}.api-target-scan`, "fail", "local API target found in response");
    }
    if (result && path === "/") await scanFrontendAssets(frontend, result.body);
  }

  const frontendReleaseResponse = await get(frontend ? `${frontend}/release` : null, "frontend.release");
  statusCheck("frontend.release", frontendReleaseResponse, [200]);
  let frontendRelease = null;
  if (frontendReleaseResponse) {
    try {
      frontendRelease = JSON.parse(frontendReleaseResponse.body);
      const contract = compareReleaseContracts(frontendRelease, backendRelease);
      record("release.compatibility", contract.status, contract.detail);
    } catch {
      record("frontend.release", "fail", "Release response was not valid JSON");
    }
  } else if (backendRelease) {
    record("release.compatibility", "unverifiable", "frontend release endpoint unavailable");
  }

  const sharedResult = await get(shared, "frontend.shared-build", false);
  statusCheck("frontend.shared-build", sharedResult, [200], false);

  const requiredFailures = results.filter((result) => result.required && (result.status === "fail" || result.status === "incompatible" || result.status === "unavailable" || result.status === "skipped"));
  console.log(`\nSummary: ${results.filter((result) => result.status === "pass").length} passed, ${results.filter((result) => result.status === "skipped").length} skipped, ${requiredFailures.length} required failures.`);
  process.exitCode = requiredFailures.length ? 1 : 0;
}

await run();
