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

## Safe Startup Defaults

- `PRICING_SCHEDULER_ENABLED=false`
- `AUTONOMOUS_AGENTS_ENABLED=false`
- `CPU_SPECS_SEED_ON_START=false`

Workers and CPU seeding may be enabled intentionally through environment configuration after review.

## Approval Boundaries

Approval is required for protected-data deletion, production secret changes, destructive migrations, ambiguous identity merges, trusted-source conflict resolution, autonomous graph mutation, and recommendation-governance changes.
