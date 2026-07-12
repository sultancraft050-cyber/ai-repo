# Website Workflow Fixture Verification

**Date:** 2026-07-12
**Scope:** local Playwright Chromium with deterministic synthetic fixtures only

## Fixture architecture

Reusable fixtures live in `frontend/e2e/fixtures/workflows.ts`. IDs use the `fixture-*` prefix, timestamps and prices are deterministic, and route interception prevents workflow requests from reaching production. `frontend/e2e/workflows.spec.ts` contains workflow, viewport, error-state, and axe assertions.

## Coverage and results

- Manual builder: all eight supported categories, independent loading, partial GPU failure, category-only retry, selection, same-category replacement, removal, missing-price/vendor fallbacks, search, summary association, and safe rendering.
- Generated builder: client budget validation, successful fixture build, no compatible result, HTTP 400/429/500, malformed response, network failure, loading/result rendering, Saudi vendor/price display, and sanitized errors.
- Shared build: direct success route, refresh-safe fixture response, missing route response, meaningful h1, and recovery link.
- Viewports: desktop/mobile remain covered; representative laptop 1280×800 and tablet 768×1024 checks confirm no horizontal overflow and reachable theme controls.
- Accessibility: axe scans cover home light/dark, open mobile navigation, manual builder, generated result/error UI, shared build, and branded 404. Serious and critical violations are required to be zero.
- Console/network: workflow requests are mocked; no production mutation endpoint is contacted. Existing console collector remains active in the public smoke suite.
- CI: the Node 22 frontend job installs Playwright Chromium and runs the deterministic browser/axe suite after the production build.

## Confirmed defects fixed

1. A failed manual category had no recovery action. Added a category-scoped retry that does not reload successful categories.
2. Clearing a failure left an `undefined` warning entry. Empty failures are now excluded from buyer notes.
3. Light-theme legacy utility aliases overrode light backgrounds and caused serious contrast failures. Theme-specific overrides now win, with stronger signal/caution text colors.
4. `no_valid_build` had no explicit recovery state. Added a clear message suggesting safe input adjustments.

## Deferred coverage

Explicit numbered next/previous controls are not implemented; the verified contract is progressive “Load more products.” Outside-click focus return and reduced-motion loading-indicator assertions remain follow-ups.

## Interaction edge verification

- A 30-product CPU fixture now verifies the implemented “Load more products” contract across desktop, tablet, and mobile, including deterministic offset behavior, sorting/search state, and duplicate prevention.
- Dedicated incomplete generated-build coverage names missing categories, preserves available components, avoids claiming complete compatibility/readiness, and uses safe fallback text.
- Mobile drawer focus moves into the drawer, wraps at both tab edges, closes on Escape, and returns to the menu trigger.
- `prefers-reduced-motion: reduce` is emulated for theme and drawer interactions; the scoped stylesheet removes meaningful motion without disabling normal-motion transitions.

Playwright reports, traces, screenshots, videos, browser binaries, and axe raw output remain ignored. No production payloads, credentials, database operations, or deployments were used.

Safe-off flags remain unchanged:

```text
PRICING_SCHEDULER_ENABLED=false
AUTONOMOUS_AGENTS_ENABLED=false
CPU_SPECS_SEED_ON_START=false
```
