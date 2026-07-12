# Blocked-Request Production Verification

**Status: PARTIAL_SAFE_VERIFICATION**

**Date:** 2026-07-12
**Target:** `https://frontend-lac-nine-09j4x45cj5.vercel.app`

## Guard self-test

`frontend/e2e/blocked-production-check.mjs` creates a local HTTP server and a fresh Chromium context with `serviceWorkers: "block"`. The context route is installed before page creation. GET and HEAD continue; every other method is aborted with `route.abort("blockedbyclient")`; request bodies, headers, cookies, and query strings are never stored. The synthetic server received **0 POST** requests.

## Completed guarded initial load

A fresh guarded context was created before the production page. Service workers were blocked, routing was installed before page creation and navigation, and only GET and HEAD were allowed. The initial production navigation completed without a blocked POST, PUT, PATCH, or DELETE request. Zero non-GET/HEAD requests reached production.

The tool session stopped returning output while attempting the larger interaction sequence. No unguarded retry was made. Theme, drawer, manual search, generated validation, shared-build behavior, reduced motion, and the full route sequence are **NOT VERIFIED** in this guarded run.

## Request accounting

- Blocked POST: 0 during the production initial-load capture
- Blocked PUT: 0 during the production initial-load capture
- Blocked PATCH: 0 during the production initial-load capture
- Blocked DELETE: 0 during the production initial-load capture
- Blocked other methods: 0
- Non-GET/HEAD reaching production: 0
- Cloud Run blocked requests: 0 observed
- Same-origin mutation blocked requests: 0 observed
- Unknown non-telemetry blocked requests: 0 observed

The guard self-test’s synthetic POST is intentionally excluded from production counts. No production request body, header, cookie, token, or query string was recorded.

## Static-source context

The repository static audit confirms that the homepage can automatically call first-party `/analytics/events`. This makes first-party analytics a plausible explanation for historical POST activity, but the historical four POST requests had no captured URLs. Attribution remains unresolved; they are not classified as harmless or as database mutations. The guarded initial-load capture did not reproduce a non-GET request. No Vercel Analytics, Speed Insights, service worker, beacon API, or third-party telemetry SDK is present in the repository.

## Safety and remaining work

No production form was submitted, no valid generated build was invoked, no Neo4j operation occurred, and no deployment or secret change occurred. A future approved run may repeat the guarded interaction sequence with output capture fixed; it must retain the same pre-navigation route guard and stop on any Cloud Run, same-origin mutation, or unknown non-telemetry request.
