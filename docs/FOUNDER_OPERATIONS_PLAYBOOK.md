# Founder Operations Playbook

This playbook is for running the Saudi MVP without a full DevOps team. It assumes public traffic is live, broad ingestion is off, and catalog improvements happen through approved URLs or controlled dry-runs.

## Daily Routine

1. Open Founder Operations and load the command center with an analyst/admin key.
2. Check `GET /ops/deployment-checklist?region=SA`.
3. Check `GET /ops/mvp-health-dashboard?region=SA`.
4. Review failed and incomplete builds in `GET /ops/build-failure-summary?region=SA`.
5. Review pending user feedback and deal submissions.
6. Check stale or weak categories in `GET /ops/market-coverage-summary?region=SA`.
7. Refresh only approved known product URLs when the category is active and the source policy allows it.

Daily decision rule:

- If builds fail because a category is missing, improve that category first.
- If builds fail because budget is impossible, add cheaper compatible Saudi alternatives.
- If users report wrong prices, verify the product URL before changing recommendations.
- If runtime health is degraded, fix reliability before expanding catalog coverage.

## Weekly Routine

1. Improve the weakest build-critical category.
2. Review duplicate candidates and graph-integrity warnings.
3. Review suspicious pricing and marketplace/imported-only products.
4. Add a small number of trusted product URLs for the most requested categories.
5. Re-run backend tests, frontend typecheck, and production build before deploying changes.

Weekly priority order:

1. Categories blocking builds.
2. Categories causing strict-budget failures.
3. Categories with high user demand.
4. Categories with stale or risky-only listings.

## Monthly Routine

1. Review source coverage and cost.
2. Review common budget ranges and shared builds.
3. Review feedback themes: confusing warnings, bad vendor listings, wrong compatibility, expired listings.
4. Audit deployment health and secrets rotation needs.
5. Decide whether the next market/category expansion is justified by usage.

## Neo4j Capacity Recovery

Use this when Neo4j Aura reports the free-tier logical node limit or canonical imports stop with a capacity error.

1. Run `GET /ops/neo4j-capacity-report`.
2. Review `largest_labels`, `estimated_safe_to_prune_labels`, and `production_critical_labels`.
3. Run `POST /ops/neo4j-prune-preview` with only safe temporary labels such as `StagedCanonicalRecord`, `CanonicalStageRun`, `CanonicalImportRun`, `OperationalSignal`, `AutonomyJob`, or `AnalyticsEvent`.
4. Confirm the preview does not include `Product`, `CanonicalProduct`, `Vendor`, `PriceSnapshot`, `RegionalPriceSnapshot`, `ProductURL`, `SavedBuild`, `User`, `WatchlistItem`, feedback, deal, approval, or live linked evidence nodes.
5. Execute `POST /ops/neo4j-prune-execute` only after reviewing the signed preview id and setting `approved=true`.
6. Rerun `GET /ops/neo4j-capacity-report`.
7. Retry the canonical import stage after node count drops below the Aura free-tier limit.

If safe pruning does not recover enough space, upgrade Neo4j Aura instead of deleting useful Saudi product, price, build, user, or URL data.

## Support And Feedback Workflow

1. Triage feedback as wrong price, expired listing, wrong compatibility, suspicious recommendation, bad vendor listing, or broken URL.
2. Verify the store page manually.
3. If the product is valid, run product URL preview first.
4. Ingest only after preview passes and the source policy allows it.
5. If the report is invalid or uncertain, leave the recommendation conservative and keep warnings visible.

## Market Coverage Strategy

Use founder insights to answer:

- What categories block builds most often?
- Which budget ranges are common?
- Which categories trigger over-budget failures?
- Which categories have stale, risky, or imported-only listings?
- Which product families are submitted by users?

Recommended first catalog actions:

- Add cheaper GPU alternatives for budget-fit builds.
- Improve RAM and Storage certainty when warnings confuse users.
- Add motherboard URLs when AM5/B650 coverage is thin.
- Add budget-safe 750W Gold PSUs.
- Prefer local/GCC trusted vendors over risky marketplace listings.

## Safe Launch Rules

- Never turn broad ingestion on during a public incident.
- Never hide VAT, shipping, warranty, marketplace, imported, stale, or condition uncertainty.
- Never use US prices for Saudi builds.
- Never store raw page HTML or download product images.
- Never expose audit IDs, API traces, user email, or secret-bearing metadata on shared builds.

## Deployment Smoke Test

After each deploy:

1. `GET /health`
2. `GET /health/neo4j`
3. `GET /ops/deployment-checklist?region=SA`
4. Open the landing page.
5. Generate a 6000 SAR Saudi build.
6. Save the build as a guest.
7. Open the shared build URL.
8. Add one component to watchlist.
9. Submit a test feedback item.
10. Confirm Founder Operations shows the new activity.
