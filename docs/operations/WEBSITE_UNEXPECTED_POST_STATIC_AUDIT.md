# Unexpected Production POST Static Audit

**Date:** 2026-07-12
**Method:** repository and Git-history inspection only; no production request, browser navigation, backend invocation, or database operation was performed.

## Incident summary

The stopped live check observed four POST requests and no PUT, PATCH, or DELETE requests without intentional form submission. Their URLs were not captured. This audit therefore identifies capable sources but does not attribute the four observations to a destination without evidence.

## Static POST-source inventory

| Confidence | Source | Trigger | Destination | Automatic | Data impact/authentication |
|---|---|---|---|---|---|
| CONFIRMED | `PublicLandingPage` mount effect → `recordAnalyticsEvent` | Home mount, including reload/remount | configured API host, `/analytics/events` | Page load; not ordinary client route navigation unless home remounts | Public/rate-limited; stores in memory and attempts Neo4j `AnalyticsEvent` creation |
| CONFIRMED | `PublicLandingPage.sendFeedback` → `submitFeedback` | Explicit Send feedback click | configured API host, `/feedback` | No | Public/rate-limited; stores in memory and attempts Neo4j feedback creation |
| CONFIRMED | `ManualPartPicker` → `validateAndMeasure` | Product selection changes | `/compatibility/check`, then `/api/performance/calculate` for CPU+GPU | No selection means no POST | Public frontend call; calculation/validation, not intended catalog mutation |
| CONFIRMED | `SaudiBuildWizard` | Generate, save, watch controls | `/build/generate-local`, `/builds/saved`, user/guest watchlist | No | Explicit user interaction; generation may record build analytics, save/watch writes application data |
| CONFIRMED | `UserBuildsWorkspace` | Account/save/duplicate/compare/watch controls | users, saved builds, comparison, watchlist routes | No | Explicit user interaction; application-store/Neo4j-capable writes |
| CONFIRMED | Founder/admin components through `frontend/lib/api.ts` | Explicit privileged controls | pricing, catalog, sources, approvals, cognition/governance/alignment/autonomy/ops routes | No | Many require API key; several mutate Neo4j/catalog/operational state |
| NOT_ACTIVE | Vercel Analytics / Speed Insights | None | None | No | Packages/components are absent |
| NOT_ACTIVE | Sentry, PostHog, Segment, GA/gtag, browser beacon, service worker/background sync | None | None | No | No package, provider, registration, `sendBeacon`, or service-worker source found |

The only repository-confirmed page-load POST is the landing-page analytics effect. Its existence and repeated mount behavior are consistent with multiple observations, but the missing live URLs prevent a proven incident attribution.

## Analytics and telemetry findings

No `@vercel/analytics`, `@vercel/speed-insights`, web-vitals reporter, Sentry, PostHog, Segment, Google Analytics, beacon API, or service worker is installed or mounted. The `@opentelemetry/api` lockfile reference is an optional transitive Next.js dependency; no application initialization was found. Product “telemetry” components perform GET reads when their explicit product-intelligence UI loads and are unrelated to browser analytics initialization.

The first-party `/analytics/events` endpoint is public and rate-limited. `LaunchAnalyticsStore` stores a bounded in-memory event and `record_launch_event` attempts `Neo4jOpsRepository.create_analytics_event` when Neo4j is available. Failures are swallowed.

## Backend POST-route inventory reachable from frontend

| Route group | Frontend caller/purpose | Write capability | Authentication | Automatic? |
|---|---|---|---|---|
| `/analytics/events`, `/feedback` | landing analytics and feedback | In-memory plus attempted Neo4j event/feedback nodes | Public, rate-limited | Analytics only: yes on home mount |
| `/compatibility/check`, `/api/performance/calculate`, `/build/validate` | manual validation/performance | Calculation/validation; no intended catalog write | Public | Only after selection/action |
| `/build/generate`, `/build/generate-local` | build generation | Generation and launch analytics; may persist analytics | Public | Explicit Generate only |
| `/users`, `/builds/saved`, duplicate/compare, user/guest watchlist | account and saved workspace | Application data/Neo4j-capable writes | Public session identity | Explicit controls only |
| `/sources/deal-submissions` | public deal submission | Submission/analytics record | Public/rate-limited | Explicit submission only |
| `/sources/product-url/*`, `/products/canonical-merge-preview`, `/catalog/import/stage`, canonical enrich/link routes | founder catalog tools | Preview ranges from dry-run to staging/import/enrichment writes | API key for frontend callers | Explicit founder controls only |
| `/pricing/refresh`, `/pricing/discover`, `/intelligence/enrich` | pricing/intelligence controls | Pricing/discovery/intelligence writes possible | Route-dependent; privileged UI | Explicit controls only |
| `/approvals/*`, `/ops/autonomy-queue/*` | approval and operations controls | Approval/job-state writes | API key | Explicit controls only |
| cognition, governance, evolution, alignment, autonomy refresh/event routes | intelligence administration | Neo4j operational/governance writes possible | Route-dependent privileged access | Explicit controls only |

Other backend POST routes exist for telemetry ingestion/reasoning, CPU imports/images, policies/rollback, catalog commit/evidence/spec audit, Neo4j maintenance, and regional-label execution. No automatic public-page caller was found for them.

## Automatic versus user-triggered behavior

- Automatic: landing `useEffect` POST to `/analytics/events` once per component mount.
- User-triggered: feedback, generation, manual selection validation, save/duplicate/compare/watch, deal submission, and all founder/admin operations.
- No automatic POST was found in `ThemeProvider`, `RegionProvider`, layout, mobile drawer handling, error handling, Next configuration, service workers, or monitoring providers.

## Theme static analysis

Result: **LIKELY_TEST_SELECTOR_PROBLEM** (including assertion timing), not a statically demonstrated production defect.

There is one theme button. Its accessible name switches between `Switch to light mode` and `Switch to dark mode`; `onClick={toggleTheme}` updates `ThemeProvider` state; storage key is `saudi-build-theme`; both the pre-paint script and provider apply `document.documentElement.dataset.theme` and `style.colorScheme`. The control is not disabled and no overlay/pointer handler is evident. Local Playwright tests pass both directions and persistence. A live assertion that reads the attribute immediately after click can race React state/effect application; a blocked-request future test should wait on the expected attribute and accessible name.

## Missing-document investigation

`docs/operations/WEBSITE_INTERACTION_EDGE_VERIFICATION.md` is absent from the working tree, tracked-file list, ignore rules, and all reachable Git history. The Iteration 24 changes updated `WEBSITE_WORKFLOW_FIXTURE_VERIFICATION.md` instead. Result: **never committed under the referenced filename; referenced incorrectly**. It is not recreated here from memory.

## Safe blocked-request verification design (not executed)

1. Launch a fresh Chromium context with `serviceWorkers: "block"`.
2. Install `browserContext.route("**/*", handler)` before creating a page.
3. For each request, record only method, origin, redacted path (query removed), resource type, frame origin/path, and safe initiator/stack metadata where Playwright exposes it.
4. Continue only GET and HEAD. Abort every other method before transmission; never read/store request bodies.
5. Redact query strings, authorization-like headers, tokens, IDs, and credentials. Do not automatically retry aborted requests.
6. Stop immediately if a blocked request targets the configured Cloud Run host or a known mutation path.
7. Use a fresh context per route and report blocked requests without claiming server-side effects.

## Remaining unknowns

- The observed POST URLs, hosts, paths, resource types, frames, and initiators remain unknown.
- Static evidence cannot prove whether all four observations were first-party analytics, Next/Vercel behavior outside the repository, or another source.
- No conclusion is made about production database mutation from the stopped check.

No production request was sent during this static audit.
