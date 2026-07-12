# Website-Wide Feature Audit

**Date:** 2026-07-12  
**Scope:** public frontend routes and browser-facing controls  
**Data/deployment impact:** none; no backend writes, Neo4j queries, secret changes, or deployments were performed.

## Executive summary

The audit found and corrected three frontend reliability issues: the theme control was a no-op, the mobile header had no usable navigation, and two logo links targeted `#`. Theme state now persists in browser storage, follows the system preference when unset, is applied before paint, and exposes an accessible toggle. The mobile menu has explicit open/close state, focusable links, and `aria-expanded`/`aria-controls`.

Runtime browser automation was not available in the repository dependencies, so route behavior was verified by source inspection, contract tests, a production build, and the existing UI contract check. API-backed flows remain marked for browser smoke coverage in the next iteration.

## Route and feature matrix

| Route/control | Expected behavior | Evidence/status | Follow-up |
|---|---|---|---|
| `/` landing page | Load hero, navigation, trust/feedback sections | Static route/build verified; desktop links and mobile drawer present | Browser smoke with real viewport |
| Theme toggle | Toggle light/dark, persist choice, keyboard accessible | Fixed; contract test covers handler, labels, storage, system preference, and root provider | Add browser assertion for persisted reload |
| Mobile navigation | Open/close drawer; links navigate to public routes | Fixed; native button and semantic nav with `aria-expanded` | Verify focus return and Escape behavior in browser |
| Desktop sidebar/top bar | Links reach `/`, `/build/generate`, `/build/manual`, saved builds, feedback | Source inspection; logo dead links fixed | Browser click-through |
| `/build/manual` | Search/filter parts, display progressive results, validate selection | Existing UI and retry/progressive loading paths present; API-backed runtime not exercised | Browser test with mocked API and Saudi region |
| `/build/generate` | Validate form, generate build, show loading/error/result states | Form/state paths present; generation is API-backed and was not invoked | Browser test with mocked API |
| `/build/share/[slug]` | Render shared build or useful missing/error state | Dynamic route builds successfully; slug/API cases need runtime coverage | Add not-found/error assertions |
| `/release` | Show release/readiness information without mutation | Static route/build verified | Browser smoke |
| Unknown route | Render a useful not-found experience | Next fallback exists; no custom `not-found.tsx` is defined | Consider a dedicated branded 404 |
| Search/display controls | Be visibly labelled and non-deceptive | Landing search is presentational (“coming later”); no false submission path | Replace placeholder when search is implemented |

## Accessibility and responsive review

Interactive controls use native buttons/links, visible focus styles are retained, and the theme/menu controls have explicit accessible names. The mobile drawer is hidden until opened and uses a labelled navigation region. A full axe/browser run was not possible because no browser automation or axe dependency is checked in; this is an explicit follow-up rather than an unverified pass.

## Theme diagnosis and fix

Before this iteration the theme button rendered an icon but had no click handler, always announced “Dark mode active”, and had no persistence or theme provider. The fix adds `ThemeProvider`, local-storage persistence with private-browsing fallback, system preference detection, a pre-paint bootstrap, `data-theme` styling, and a labelled toggle that changes icon and title with state.

## Network and safety boundaries

No production write endpoints were called. Generation, feedback submission, and any persistence controls remain outside this audit’s runtime checks. Safe-off flags remain unchanged:

```text
PRICING_SCHEDULER_ENABLED=false
AUTONOMOUS_AGENTS_ENABLED=false
CPU_SPECS_SEED_ON_START=false
```

## Deferred work

The next standalone task is to add a browser smoke/accessibility harness covering every route at desktop and mobile widths, mocked API success/error states, keyboard navigation, theme reload persistence, and a no-localhost production-target assertion. No deletion, migration, backend, database, secret, Cloud Run, or Vercel work is part of that task.
