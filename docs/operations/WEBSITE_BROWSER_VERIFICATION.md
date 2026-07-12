# Website Browser Verification

**Date:** 2026-07-12
**Build:** local Next.js production build
**Browser:** Playwright Chromium
**Safety:** all API calls were mocked locally; no production write endpoint, database, secret, Cloud Run, or Vercel operation was used.

## Coverage

The suite in `frontend/e2e/public.spec.ts` covers `/`, `/build/manual`, `/build/generate`, `/release`, an unknown route, theme persistence, mobile navigation, and the production-target localhost guard. The dynamic shared-build route is included in the built route inventory and remains a follow-up for a representative slug fixture because its data contract is API-backed.

Viewports exercised: 1440×900 desktop and 390×844 mobile. The existing responsive CSS and build checks cover intermediate layouts; 1280×800 and 768×1024 are recommended additions when the fixture-backed shared-build flow is added.

## Results

- Playwright: 7 passed.
- Home: title, h1, theme toggle, persistence after reload, desktop navigation, mobile drawer, Escape close, and navigation close-after-click passed.
- Theme: system/default storage path is covered by the pre-paint implementation; light↔dark toggling, `data-theme`, color-scheme styling, keyboard Enter, and reload persistence passed. The same native button supports Space and touch-equivalent click semantics.
- Manual and generated builders: local route rendering passed with mocked API responses; no write request was sent. Full product-selection and generated-result fixtures remain deferred because they require stable response fixtures.
- Release: GET route returned 200 and exposed release/API-contract data.
- 404: unknown route now shows a usable 404 page with a Return home link.
- Console/network: no unexpected page errors or console errors were observed. Resource 404 noise from the absent favicon is ignored as a documented non-application asset gap. No localhost API target is present in the configured production target.
- Accessibility: route titles, page h1s, named buttons/links, native keyboard behavior, mobile drawer labelling, Escape close, and visible focus were verified. Axe was not added; this lightweight pass does not claim automated WCAG contrast scoring.

## Confirmed fixes

Browser failures confirmed and fixed during this iteration:

1. Mobile navigation did not close on Escape or outside click. The drawer now closes for both and after link navigation.
2. Unknown routes had no usable home recovery link. A branded `not-found.tsx` now provides one.
3. The browser test initially selected an ambiguous Generate link; the test now uses the labelled mobile navigation region.

## Screenshots and artifacts

Successful runs generate ignored local screenshots under `frontend/test-results/` for home light/dark desktop/mobile. Playwright traces and reports are also ignored and are not committed. No complete production payloads or credentials are stored.

## Deferred risks

- Add fixture-backed product selection, partial category failure/retry, generated validation/result/error states, shared-build rendering, and axe checks.
- Add the 1280×800 and 768×1024 viewport assertions once those fixtures exist.
- The favicon 404 should be resolved separately if a branded browser tab icon is required.

Safe-off flags remain unchanged:

```text
PRICING_SCHEDULER_ENABLED=false
AUTONOMOUS_AGENTS_ENABLED=false
CPU_SPECS_SEED_ON_START=false
```
