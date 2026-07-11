# Repository Engineering Rules

## Mission

Build a trustworthy Saudi-focused PC hardware intelligence platform. Recommendations must be traceable to confirmed specifications, explicit compatibility rules, Saudi-specific market evidence, and visible uncertainty.

## Invariants

- Keep canonical products, evidence, derived intelligence, vendor offers, and Saudi price snapshots separate.
- Price history is append-only; never overwrite or delete historical Saudi prices.
- Never use non-Saudi prices for Saudi recommendations.
- Staged data is evidence, not canonical truth.
- Inferred fields never silently unlock compatibility readiness.
- Use only `compatibility_ready_exact`, `compatibility_ready_family`, `metadata_only`, and `conflict_requires_review`.

## Safety

- Do not auto-merge ambiguous identities or trusted-source conflicts.
- Do not approve founder-review actions automatically.
- Do not delete protected products, evidence, users, builds, URLs, vendors, or price snapshots.
- Startup workers, schedulers, seeding, discovery, and graph mutation must be explicitly enabled.
- Keep secrets in environment configuration only; never print or commit them.

## Commands

- Backend tests: `python -m pytest` from `backend`.
- Backend compile: `python -m compileall app` from `backend`.
- Frontend typecheck: `npm run typecheck` from `frontend`.
- Frontend build: `npm run build` from `frontend`.
- UI checks: `npm run ui:check` from `frontend`.
- Diff validation: `git diff --check`.

Check that the required runtime exists before running commands. Preserve cross-platform path behavior.

## Working Method

- Inspect Git status before editing.
- Make one coherent, reversible improvement per iteration.
- Preserve unrelated uncommitted changes.
- Add focused tests for behavior changes and run relevant checks.
- Review the complete diff for secrets and unrelated modifications.

## Definition Of Done

The change is tested, documented, reversible, compatible with existing APIs and data boundaries, and recorded in the engineering evolution state with a precise next task.
