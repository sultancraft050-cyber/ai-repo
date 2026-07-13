# Current Engineering State

Updated: 2026-07-12

## Objective

Provide trustworthy Saudi PC component discovery, manual picking, and build generation using confirmed specifications, explicit compatibility rules, and Saudi market evidence.

## Architecture

- Frontend: Next.js App Router, React, TypeScript, Tailwind, XState.
- Backend: FastAPI with Neo4j repositories and compatibility/build services.
- Database: Neo4j is the graph source of truth.
- Deployment: Railway backend, Vercel frontend, Neo4j deployment.
- Canonical flow: dataset -> staged record -> evidence/enrichment -> hybrid review -> controlled commit.
- Pricing flow: Product/Vendor/ProductURL plus append-only PriceSnapshot and RegionalPriceSnapshot nodes.

## Commands And Baseline

- Backend: `python -m pytest`, `python -m compileall app` from `backend`.
- Frontend: `npm run typecheck`, `npm run build`, `npm run ui:check` from `frontend`.
- Repository: `git diff --check`.
- Frontend typecheck, production build, and UI contract checks pass for the current worktree.
- The local shell provides Node.js but not `python`, `py`, Docker, or an installed WSL distribution; backend tests and compile require CI or another Python-enabled environment.

## Deployment And Health

- Railway backend uses the backend Dockerfile and exposes `/health`.
- Vercel frontend uses `NEXT_PUBLIC_API_BASE_URL` pointing to Cloud Run.
- Production health must include application health and Neo4j connectivity.
- Secrets are environment-only and must never enter frontend configuration.
- Smoke command: `npm run smoke:production` with `SMOKE_BACKEND_URL`, `SMOKE_FRONTEND_URL`, and optionally `SMOKE_SHARED_BUILD_URL`.
- Backend release metadata: public `/health` JSON.
- Frontend release metadata: public `/release` JSON.
- Public release fields: `service`, `environment`, `release`, `git_sha`, `build_time`, `api_contract_version`.
- Current API contract version: `1`.
- Compatibility rule: matching API contract versions are compatible even when release identifiers or Git SHAs differ; mismatches are incompatible; missing metadata is unverifiable.
- Cloud Run URL: `https://hardware-intelligence-api-lywizc5z5q-ww.a.run.app`.
- Vercel URL: `https://frontend-lac-nine-09j4x45cj5.vercel.app`.
- Shared-build slug: not configured for smoke testing.

## Risks And Invariants

- Startup graph mutation must remain explicitly opt-in.
- Catalog conflicts and inferred specifications require review/evidence.
- Saudi pricing coverage and freshness remain uneven by category.
- Readiness states are `compatibility_ready_exact`, `compatibility_ready_family`, `metadata_only`, and `conflict_requires_review`.
- Canonical-only operations do not mutate Saudi prices.
- Price history is append-only.
- The working tree contains unrelated edits in `frontend/components/SoloFounderOpsPanel.tsx` and `frontend/types/builder.ts`; preserve them.
- Production Cloud Run/Vercel smoke verification is passing; no production result was fabricated.
- Smoke workflow syntax is valid; a run with only the known Railway URL correctly reports required checks as unavailable and exits non-zero.
- The release contract is implemented locally but not yet deployed or verified against live Railway/Vercel targets.

## Focused Release Status

- Branch: `master`, tracking `origin/master`.
- Release baseline: `811c63129053c08247c91a1805a75a703d1d446e`.
- Focused commit: `10d38581b2a991ad372064609838cb8ac8bff267` (`chore: add safe startup and release verification`).
- Push status: pushed to `origin/master`; remote verification returned the same SHA.
- CI status: no repository CI workflow was found; backend validation remains pending.
- Railway deployment: retired historical fallback; the old hostname returned `404 Application not found`.
- Cloud Run deployment: healthy at the recorded Cloud Run URL.
- Vercel deployment: healthy at the recorded Vercel URL.
- Live release compatibility: compatible; API contract version `1`.

## Automated Reliability CI

- Workflow: `.github/workflows/ci.yml`.
- Triggers: pull requests and pushes to `master`; superseded runs are cancelled per ref.
- Python validation: Python 3.12, editable backend install with test extras, compileall, focused startup-safety tests, release/security tests, and full pytest.
- Frontend validation: Node 22, `npm ci`, typecheck, build, UI contract checks, and `/release` route artifact check run sequentially.
- Contract/tooling validation: release tests, Node syntax checks, shell syntax check, safe-off deployment defaults, secret filename check, and diff check.
- CI uses no production credentials, Neo4j service, provider APIs, or production endpoints. Production smoke remains manual.
- First workflow run for commit `19bcd6d` completed with frontend and contract/tooling jobs passing; backend compile, startup-safety, and release/security steps passed, while the full backend pytest step failed and needs log-level investigation.
- Corrected workflow commit `2c1c823` removed the `.env.example` false positive; its frontend and contract/tooling jobs pass, while the same backend full-suite failure remains.
- GitHub Actions run: [2c1c823 CI run](https://github.com/sultancraft050-cyber/ai-repo/actions/runs/29164807695).
- Manual picker measurement: eight independent `/products/search` requests are issued concurrently; the current UI previously withheld all category results until all settled.
- Read-only Cloud Run timing sample before deployment: parallel total about 20.7s, with CPU about 20.7s, GPU about 11.8s, RAM about 6.7s, and other categories about 2.4-3.7s; responses were approximately 16-58KB each.
- Manual picker improvement is local and pending deployment validation; no API or data changes were made.
- Backend CI diagnosis: run `29164807695`, job `86575990875`, fails only at `Backend test suite`; the public GitHub API permits job/step metadata but denies log download with HTTP 403, so the failing test name and traceback are not available in this environment.
- CI diagnostics update: the backend full-suite step now writes `backend/pytest-output.log` and `backend/pytest-results.xml`, uploads artifact `backend-pytest-results` with `if: always()`, and publishes a bounded `$GITHUB_STEP_SUMMARY` while preserving the real pytest exit code.
- Diagnostic run `29165405260` completed: artifact `backend-pytest-results` was created; backend remained correctly failed; frontend and contract/tooling jobs passed. Artifact download requires authentication in this environment, so exact pytest names remain pending authorized access.
- Diagnostic evidence identified three fixture-path failures in `test_pc_part_dataset_adapter.py`: 285 collected, 282 passed, 3 failed. The tests incorrectly prefixed `backend/` while pytest ran from the backend directory.
- Fixture tests now resolve `data/canonical_specs` from the test file’s backend root, independent of process cwd; fixture contents and production code are unchanged.
- Verification run `29166175755` passed all jobs: backend compile, startup safety, release/security, full pytest (285 passed), frontend, and contract/tooling. The diagnostic artifact also uploaded successfully.
- CPU product-search profiling identified a deterministic N+1 pattern: one candidate query followed by `vendor_prices()` for every candidate (minimum candidate pool 100), producing about 101 Neo4j reads for the default CPU request.
- The focused optimization batches latest-per-vendor price snapshots for all candidate product IDs in one parameterized read query, reducing search query count from about 101 to 2 while preserving existing Python price rollups and response models.
- CI run `29166403191` passed backend, frontend, and contract/tooling jobs with the batch-price-read optimization.
- Cloud Run deployment is pending: the current shell has no `gcloud` executable, and the deployment script stopped before making changes. Production measurements still describe the previous revision.

## Google Cloud Run Migration

- Intended platform: Google Cloud Run.
- Service: `hardware-intelligence-api`.
- Production region: `me-central1`.
- Artifact Registry region: `me-central1`.
- Deployment scripts: `scripts/deploy-cloud-run.ps1` and `scripts/deploy-cloud-run.sh`.
- Deployment method: Cloud Build from the `backend` source context into Artifact Registry, then Cloud Run.
- Resource target: request-based, 1 CPU, 512MiB, min 0, max 1, port 8080.
- Required secret names: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, `ANALYST_API_KEY`, `ADMIN_API_KEY`, `SUPER_ADMIN_API_KEY`.
- Vercel API variable: `NEXT_PUBLIC_API_BASE_URL`; migration remains pending until the Cloud Run URL is verified.
- Cloud Run preparation validation: PowerShell deployment script parsed; frontend/release checks passed.
- Cloud Run deployment status: healthy and smoke-verified.
- Cloud Run image build: `dfd3d99f-4624-4867-9a92-269764064053`; image tag `me-central1-docker.pkg.dev/pc-recomendation-project/pc-builder/hardware-intelligence-api:ac6f32b`.
- Google Cloud preflight: authenticated project `pc-recomendation-project`, billing enabled, required APIs enabled, seven secrets present, runtime service account created, per-secret accessor bindings created, Artifact Registry `pc-builder` created in `me-central1`.
- Deployment scripts default both service and registry locations to `me-central1`, reject empty regions, and require an explicit non-production override for a service-region mismatch before invoking `gcloud`.
- Verified CPU production performance: first request 1.795s; warm requests 1.200s, 1.000s, and 0.879s; median warm response improved from approximately 20.8s to 1.000s. Result count remained 24 and payload remained 47,514 bytes.
- Production smoke after the CPU optimization: 14 passed, 1 optional skipped, 0 required failures.

## Neo4j Capacity Assessment

- Read-only assessment date: 2026-07-12.
- Database reports Neo4j Kernel `5.27-aura`, Enterprise edition, Cypher `5`/`25`; Aura commercial tier and quota meter require console verification.
- Inventory: 200,000 nodes, 208,319 relationships, 202 Products, 38 PriceSnapshots, 22 Vendors, 3 ProductURLs, 137 CanonicalEvidence nodes, 1,368 FieldEvidence nodes, 149 online indexes, and 101 constraints.
- Capacity evidence: exactly 200,000 nodes; seven-day Cloud Run log scan found 40 capacity/limit matches and 2 write-rejection-pattern matches. No capacity percentage was exposed; treat the database as at/near limit until verified in Aura Console.
- Migration recommendation: larger AuraDB Professional, direct purchase by default unless billing confirms Marketplace advantages. GCE is an operational fallback; Spanner Graph is a rewrite, not a drop-in migration.
- Migration plan: freeze writers, confirm safe-off flags, snapshot/export, restore to a larger target, compare aggregates/schema, verify product searches/readiness/Saudi prices, approve secrets and deployment, smoke test, observe, and retain rollback versions.

## Neo4j Node-Volume Inventory

- Read-only inventory date: 2026-07-12.
- Top 25 labels account for 198,455 label memberships (99.23% of the 200,000-node baseline); 1,545 nodes are outside those groups. Memberships may overlap for multi-label nodes.
- Orphans: 1,382 nodes have no relationships and 0 nodes are unlabeled. High-volume orphan groups are AuditEvent (504), PricingJob (353), and ConfidenceState (246).
- Dominant volume is operational/governance/audit data. No deletion decision was made; active-code and retention-policy review is required.

## Neo4j Retention Audit

- Code audit date: 2026-07-12; CI prerequisite run `29184971667` passed.
- High-volume producers are active through governance, evolution, alignment, and autonomy API routes with `persist=true` defaults. Autonomous scheduling is disabled, but manual/API persistence remains available.
- Pricing scheduler is disabled, while the pricing worker and pricing/intelligence APIs remain active. AuditEvent and ConfidenceState producers are also active.
- Timestamped operational archive candidate: up to 93,006 nodes older than 30 days; estimated post-archive online count 106,994 (53.50%). This is a proposal only and requires clone rehearsal.
- Current 7-day and 30-day growth is zero for timestamped audited labels. The May 22–27 active cohort grew at approximately 17,600 timestamped nodes/day, so cleanup buys time but migration remains required.
- Decision: `CLEANUP_BUYS_TIME_BUT_MIGRATION_REQUIRED`. No deletion candidate or retention execution was approved.

## Neo4j Approval and Clone-Rehearsal Preparation

- Preparation date: 2026-07-12; CI prerequisite run `29185252408` passed.
- Approval matrix covers database, governance, security/legal, pricing operations, cognition/AI, application, Google Cloud billing, Neo4j billing, and deployment owners. Every status is `PENDING_OWNER_APPROVAL`.
- Exact read-only preview specifications cover 93,006 timestamped evolution, alignment, governance, and autonomy candidates; protected core labels are excluded.
- Clone plan requires a Neo4j 5.27-compatible managed target larger than 200,000 nodes, isolated credentials/URI, no production connectivity, safe-off flags, snapshot verification, and manual billing verification.
- Rehearsal is not authorized. No snapshot/export, clone, database mutation, retention execution, secret change, or deployment occurred.

## Safe Startup Defaults

## Website Feature Audit

- Frontend audit date: 2026-07-12.
- Fixed the no-op theme control, added persisted/system-aware light/dark state with pre-paint application, restored mobile navigation, and corrected logo links to `/`.
- Route and control inventory is documented in `docs/operations/WEBSITE_FEATURE_AUDIT.md`.
- Static contract tests, typecheck, production build, UI contract checks, and release tests are the current validation evidence. Browser automation is not present in the checked-in frontend dependencies; API-backed runtime flows remain the next task.
- No backend, Neo4j, secret, deployment, or production-data changes occurred.

## Website Browser Verification

- Browser verification date: 2026-07-12.
- Added Playwright Chromium smoke coverage for home, manual/generate routes, release GET, unknown-route recovery, theme persistence, mobile drawer keyboard behavior, console errors, and localhost-target safety.
- Seven local production-build tests passed at 1440×900 and 390×844. API requests were mocked; no production writes or credentials were used.
- Browser-confirmed fixes: Escape/outside-click mobile drawer closure and a usable branded 404 home link.
- Remaining browser work is fixture-backed manual/generated workflow states, shared-build runtime coverage, 1280×800/768×1024 viewports, and automated axe scoring.

## Website Production Verification

- Production verification date: 2026-07-12.
- Existing Vercel alias `frontend-lac-nine-09j4x45cj5.vercel.app` returned expected GET-only route statuses and live theme/mobile interaction behavior.
- Local production build, typecheck, UI checks, release tests, and seven Playwright tests passed with the expected Cloud Run API target.
- User-verified Vercel provenance: team `sultancraft050-7155s-projects`, project `frontend`, status `READY`, repository `sultancraft050-cyber/ai-repo`, branch `master`, source `33db991`, Next.js framework, and `frontend` root.
- Production alias and deployment URL were verified; `NEXT_PUBLIC_API_BASE_URL` is present for Production and targets the expected Cloud Run service. Production provenance is `VERIFIED`.
- No production forms, writes, backend deployment, Neo4j operations, or secret changes occurred.

## Deterministic Workflow Fixtures and Accessibility

- Verification date: 2026-07-12.
- Added synthetic fixture coverage for manual selection/replacement/removal/retry/missing market data, generated success/no-result/400/429/500/network/malformed states, and shared-build success/failure.
- Added laptop and tablet overflow checks plus axe scans for light/dark home, mobile navigation, builders, shared build, and 404; serious/critical violations must be zero.
- Confirmed fixes: category-scoped manual retry, removal of undefined warnings, corrected light-theme override order/contrast, and explicit no-compatible-build recovery messaging.
- No production requests, data changes, secrets, Neo4j operations, or deployments occurred.

## Frontend Interaction Edge Cases

- Added 30-product deterministic pagination coverage for the current “Load more products” contract at desktop, tablet, and mobile sizes.
- Added dedicated incomplete-build and reduced-motion fixtures, plus drawer focus containment and focus-return assertions.
- Confirmed fixes: manual search now filters visible products, menu-trigger focus is correctly referenced and restored after Escape, and reduced-motion CSS is scoped to the user preference.
- No production requests, database operations, secrets, environment changes, or deployments occurred.

## Unexpected Frontend POST Static Audit

- Repository-only audit date: 2026-07-12; no production network or browser request was sent.
- Confirmed automatic producer: `PublicLandingPage` posts `landing_page_visit` to `/analytics/events` on mount. The backend stores it in memory and attempts an `AnalyticsEvent` Neo4j write when connected.
- The four previously observed POST URLs were not captured, so attribution remains unproven. Vercel Analytics, Speed Insights, third-party analytics/error reporting, beacon APIs, and service workers are absent.
- Theme result is `LIKELY_TEST_SELECTOR_PROBLEM`; static implementation and local Playwright coverage support the handler/provider/persistence path.
- `WEBSITE_INTERACTION_EDGE_VERIFICATION.md` never appeared in reachable Git history; the reference was incorrect.

## Blocked-Request Production Verification

- Guarded verification date: 2026-07-12.
- Local guard self-test passed: synthetic GET/HEAD continued, synthetic POST was aborted, and the local server received zero POSTs.
- Fresh guarded production initial load observed zero blocked non-GET requests and allowed zero non-GET/HEAD requests to reach production. No unguarded retry was made after the interaction capture stopped returning output.
- Full theme/drawer/manual/generated/404 interaction closeout remains pending a separately approved guarded run with reliable output capture.

## Guarded Verification Recovery

- Recovery date: 2026-07-12; status `PARTIAL_SAFE_VERIFICATION`.
- Completed evidence is limited to the local guard self-test and one guarded production initial load: service workers blocked, routing installed before page creation/navigation, GET/HEAD only, zero production non-GET/HEAD requests.
- Historical four-POST attribution remains unresolved; static code confirms only that homepage analytics can call `/analytics/events`.
- Theme, drawer, manual search, generated validation, shared build, reduced-motion, and full route interactions are explicitly not verified in this recovery.

- `PRICING_SCHEDULER_ENABLED=false`
- `AUTONOMOUS_AGENTS_ENABLED=false`
- `CPU_SPECS_SEED_ON_START=false`

Workers and CPU seeding may be enabled intentionally through environment configuration after review.

## Approval Boundaries

Approval is required for protected-data deletion, production secret changes, destructive migrations, ambiguous identity merges, trusted-source conflict resolution, autonomous graph mutation, and recommendation-governance changes.

## Product Image Rendering Reliability

- Implementation date: 2026-07-13.
- Added `frontend/components/ProductImage.tsx` as the shared, strict-typed renderer for the selected-part summary and manual picker cards.
- Frames have explicit dimensions, stable aspect ratios, centered `object-contain` fitting, lazy loading by default, category-aware local SVG placeholders, safe URL validation, and one-shot load failure fallback.
- Deterministic fixture coverage exercises approved external/local URLs, missing and unsafe URLs, placeholders, alt text, stable sizing, and fallback behavior. No API, product data, image download, Neo4j, secret, or deployment change occurred.
- Generated/shared/saved/comparison contexts currently do not render product images; they remain deferred until their contracts expose image fields.

## Neo4j Migration Execution Readiness

- Readiness package date: 2026-07-13; result `READY_PENDING_MANUAL_APPROVALS`.
- Repository-only audit mapped 18 Neo4j writer families, including startup schema/default-agent writes, always-started pricing/cognition workers, manual/API persistence routes, analytics/feedback, catalog/imports, user builds/watchlists, telemetry, and ops/audit records.
- The three safe-off flags remain false, but they do not disable manual/API persistence; a route-level writer freeze is required before cutover.
- Recommended path is a larger Neo4j 5.27-compatible AuraDB Professional target, migration before cleanup, clone-rehearsed retention, and source retention for rollback. Direct purchase is preferred pending billing verification; Marketplace credits are not assumed.
- Aura tier/region/limits/utilization, snapshot/export facts, billing, target identity, and all owner approvals remain manual gates. No target, snapshot/export, secret version, deployment, traffic change, or database mutation occurred.

## Minimal Neo4j Migration Approval Gate

- Gate simplification date: 2026-07-13; result `BLOCKED_MISSING_ESSENTIAL_FACTS`.
- The gate now records only the source identifier, current provider facts, snapshot/create-from-snapshot status, selected target/cost/budget facts, purchase path, and migration/billing/deployment approvals.
- No reliable provider values or approvals were invented. Target creation remains prohibited until every required field is supplied and approved.

## Minimal Neo4j Cleanup Preparation

- Cleanup-plan date: 2026-07-13; result `READY_FOR_CLONE_CLEANUP_REHEARSAL` only.
- Added exact read-only selector catalog, protected-label/relationship checks, bounded clone-only batch design, cleanup order, clone identity gates, parity checks, stop conditions, and rollback dependencies.
- Scope is limited to timestamped operational children, terminal PricingJob records older than 90 days, and AuditEvent records only after orphan ownership resolution. Consolidation labels remain deferred.
- No production query, mutation, snapshot/export, clone creation, secret change, deployment, or cloud cost occurred.

## Relational Product Catalog Foundation

- Foundation date: 2026-07-13; Catalog V2 is disabled by default and runs in parallel with the Neo4j product behavior.
- Added SQLAlchemy 2.x/Alembic PostgreSQL-compatible catalog models and a SQLite-test migration for products, specifications, image metadata, stores, offers, price history, import sources/batches/errors.
- Added lazy, read-only `/catalog/*` routes gated by `CATALOG_V2_ENABLED`; missing `CATALOG_DATABASE_URL` never crashes startup. Catalog writes remain disabled and no write route exists.
- Synthetic tests only; no real products, offers, images, PostgreSQL, storage, Neo4j, secrets, or deployments were used.

## Staged Catalog Import Pipeline

- Implementation date: 2026-07-13; CSV/JSON import is internal, local-only, and disabled by default.
- Six explicit batch types cover products, specifications, image metadata, stores, offers, and append-only price observations. Strict identifiers replace title/fuzzy matching, and unresolved or conflicting identities remain staged for review.
- `catalog_import_records` stores allow-listed normalized fields, controlled validation/review/action states, resolved IDs, checksums, and bounded safe errors. Batch lifecycle and aggregate counts now cover parsing through guarded completion.
- `CATALOG_IMPORT_ENABLED=false`, `CATALOG_WRITES_ENABLED=false`, and `CATALOG_V2_ENABLED=false` remain defaults. The CLI refuses non-local database URLs; canonical commit additionally requires a ready, fully reviewed batch and local SQLite.
- Synthetic fixture and in-memory SQLite tests only. No production database, real catalog record, retailer, image download, Neo4j operation, cloud resource, secret change, or deployment was involved.

## Product Image Metadata Quality and Review Pipeline

- Implementation date: 2026-07-13; metadata-only evaluation and review are local and disabled by default with `CATALOG_IMAGE_REVIEW_ENABLED=false`.
- Added bounded URL/host policy, rights and provenance checks, dimensions/aspect/format/file-size/freshness checks, category heuristics, exact checksum/URL duplicate detection, primary-image safeguards, public-visibility filtering, and an append-only review audit table.
- Review decisions require both image-review and catalog-write flags, explicit safe reasons/reviewer identifiers, and local SQLite. No public write route or startup worker was added.
- Product-image import integration remains disabled with catalog imports by default; review failures never create public visibility. No images were downloaded and no visual-quality claim is made.
