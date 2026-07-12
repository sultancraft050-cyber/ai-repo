# Website Production Verification

**Date:** 2026-07-12
**Verified source commit:** `33db991`
**GitHub Actions prerequisite:** `29186288782` passed

## Deployment status

Production provenance is **VERIFIED** from the user-supplied manual Vercel inspection. No Vercel connection or deployment was performed while recording these facts.

- Team: `sultancraft050-7155s-projects`
- Project: `frontend`
- Deployment identifier: `https://frontend-kg8dgdjt8-sultancraft050-7155s-projects.vercel.app` (deployment ID was not separately recorded)
- Deployment status: `READY`
- Production alias: `https://frontend-lac-nine-09j4x45cj5.vercel.app`
- Repository: `sultancraft050-cyber/ai-repo`
- Production branch: `master`
- Source commit: `33db991`
- Framework: Next.js
- Root directory: `frontend`
- Build command: `npm run build`
- Install command: `npm install`
- `NEXT_PUBLIC_API_BASE_URL` present for Production: yes
- API target correct: yes, `https://hardware-intelligence-api-lywizc5z5q-ww.a.run.app`
- Manual verification date: 2026-07-12

## Local preflight

- `npm ci`: passed.
- Frontend typecheck: passed.
- Production build with `NEXT_PUBLIC_API_BASE_URL=https://hardware-intelligence-api-lywizc5z5q-ww.a.run.app`: passed.
- UI checks: passed.
- Local Playwright suite: passed, 7 tests.
- Root release tests: passed.
- `git diff --check`: passed.
- Built asset inspection found the expected Cloud Run target; no intentional localhost or `127.0.0.1` API target was introduced. Generic browser polyfill text is not an API target.

## Live GET-only verification

Using the existing alias and Playwright Chromium at 390×844, without submitting forms:

- `/`: HTTP 200, expected title, theme toggle works in both directions, `data-theme` changes, refresh persistence works, and mobile navigation opens/closes with Escape.
- `/build/manual`: HTTP 200.
- `/build/generate`: HTTP 200; route loaded only, no generation request submitted.
- `/release`: HTTP 200.
- Unknown route: HTTP 404 and branded title returned.
- Desktop route GET checks were also run against the alias; all listed public routes returned expected HTTP statuses.
- One expected missing-favicon 404 console resource message was observed on the unknown-route pass; no application stack trace or secret was exposed.

Production API target: expected Cloud Run URL above; value was not printed from Vercel configuration.
Production write requests: 0.
Backend revision: unchanged, `hardware-intelligence-api-00005-kvd`.

## Results

Theme, navigation, 404 recovery, route availability, and mobile behavior passed on the live alias. Manual and generated builders were limited to safe route-load checks; no production generation, save, feedback, tracking, or other mutation form was submitted. No Neo4j query was made directly.

Console/network: no application console errors or page errors observed in the home interaction pass; the known favicon 404 is documented separately. No localhost calls, obsolete Cloud Run target, mixed-content error, or CORS failure was observed in the checked routes.

## Rollback

No rollback was executed. If production verification later identifies a defect, first promote the previous known-good Vercel production deployment in the Dashboard. If a code rollback is required, revert `4222233` and deploy the resulting commit through the existing Vercel project only after review.

Safe-off flags remain unchanged:

```text
PRICING_SCHEDULER_ENABLED=false
AUTONOMOUS_AGENTS_ENABLED=false
CPU_SPECS_SEED_ON_START=false
```

The Vercel project ID, tokens, credentials, billing identifiers, and secret values are intentionally not recorded.
