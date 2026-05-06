# Custom PC Builder & Compatibility Intelligence Platform

This workspace contains a strict-stack implementation of a graph-backed PC compatibility simulator.

Runtime data rules:
- Component facts, compatibility edges, QVL records, dimensions, power, and bandwidth data live in Neo4j.
- The repository contains code, schema, and query templates only.
- Images are not stored locally. Any future product media should be external URLs on Neo4j nodes.

Services:
- `backend/`: FastAPI, Neo4j driver, NumPy performance model, compatibility engines.
- `frontend/`: Next.js App Router, React, TypeScript, Tailwind CSS, XState.
- `docs/PHASES.md`: phase-by-phase architecture, code map, and example input/output.

Key endpoints:
- `POST /compatibility/check`: validates a selected build against graph constraints.
- `POST /api/performance/calculate`: computes NumPy FPS, frame-time, and bottleneck estimates.
- `POST /build/generate`: runs the SAT-style auto build solver and returns best performance, best value, and balanced builds.
- `GET /components/options`: returns graph-filtered component candidates for the UI.
- `GET /products/search`: searches canonical Product/Component nodes with current market price metadata.
- `GET /products/categories`: returns the global hardware taxonomy used by discovery and market search.
- `GET /products/{id}/prices`: returns latest vendor snapshots for a product.
- `GET /products/{id}/history`: returns historical price snapshots.
- `GET /intelligence/products/{id}`: returns benchmark, workload, thermal, longevity, compatibility, and market intelligence for a product.
- `POST /intelligence/enrich`: computes and persists hardware intelligence for selected products or a category batch.
- `POST /intelligence/refresh`: queues a non-blocking enrichment job.
- `POST /telemetry/ingest`: validates and persists real-world benchmark, frame-time, thermal, power, driver, and workload snapshots.
- `GET /telemetry/products/{id}`: returns accepted telemetry snapshots for a product, filterable by resolution and workload.
- `GET /telemetry/products/{id}/summary`: returns aggregate FPS, 1% low, frame pacing, thermal risk, driver, and bottleneck evidence.
- `GET /telemetry/products/{id}/reasoning`: returns persisted or computed anomaly, bottleneck, driver regression, pattern, and predictive reasoning.
- `POST /telemetry/products/{id}/reason`: recomputes telemetry reasoning and attaches the result to Neo4j.
- `GET /cognition/products/{id}`: returns adaptive confidence, uncertainty, active predictions, validation memory, contradictions, and meta-reasoning.
- `POST /cognition/products/{id}/predictions`: generates auditable predictions from accepted telemetry and reasoning.
- `POST /cognition/outcomes/validate`: validates predicted behavior against observed outcomes and updates confidence state.
- `POST /cognition/refresh`: queues or runs cognition refresh jobs without blocking normal user requests.
- `GET /governance/products/{id}`: returns governed confidence, reasoning health, graph hygiene, evidence decay, consensus, and stabilization actions.
- `POST /governance/refresh`: recomputes governance reports for selected products.
- `GET /evolution/products/{id}`: returns cognitive health index, evolution velocity, policy enforcement, sandbox evaluations, promotion decisions, rollback readiness, and memory governance.
- `GET /evolution/policies/active`: returns the active versioned cognitive policy.
- `POST /evolution/policies`: creates candidate or active cognitive policy versions.
- `POST /evolution/refresh`: recomputes evolution orchestration reports for selected products.
- `POST /evolution/rollback`: records a policy rollback request for governance approval.
- `GET /alignment/identity`: returns the protected system identity, objective hierarchy, trust boundaries, ethics, uncertainty philosophy, and cognitive constitution.
- `GET /alignment/products/{id}`: returns alignment health, objective tradeoffs, ethics risks, violations, rollback support, and audit trail.
- `POST /alignment/refresh`: recomputes alignment reports for selected products.
- `GET /autonomy/agents`: returns the governed autonomous cognitive agent roster.
- `GET /autonomy/products/{id}`: returns cognition events, agent tasks, inter-agent signals, investigations, interventions, oversight gates, and autonomy health.
- `POST /autonomy/run`: executes autonomous cognition evaluation for selected products or stale graph candidates.
- `POST /autonomy/events`: records external cognition events and can trigger immediate governed analysis.
- `GET /ops/daily-report`: returns the solo-founder daily operations brief.
- `GET /ops/autonomy-queue`: returns grouped autonomous jobs: running, waiting approval, failed, completed, and scheduled.
- `POST /ops/autonomy-queue/{job_id}/cancel`: cancels a bounded cancellable autonomy job and writes an audit event.
- `GET /ops/workers`: returns pricing, cognition, scheduler, and autonomous worker health.
- `GET /ops/sources`: returns external source configuration and health without exposing key values.
- `GET /ops/source-config`: returns safe source onboarding status without revealing key values.
- `GET /approvals/pending`: returns high-risk autonomous actions waiting for owner decision.
- `GET /approvals/{id}`: returns the full approval request, evidence summary, affected entities, risk explanation, and rollback plan.
- `POST /approvals/{id}/approve` / `POST /approvals/{id}/reject` / `POST /approvals/{id}/defer` / `POST /approvals/{id}/mark-reviewed`: records founder approval decisions with audit events.
- `POST /pricing/refresh`: queues a non-blocking price refresh for existing products.
- `POST /pricing/sync`: queues multi-query product discovery and price ingestion.
- `POST /pricing/discover`: queues global component discovery or runs a bounded controlled discovery with `category`, `query`, `region`, `limit`, and `dry_run`.
- `POST /pricing/canonicalize`: validates raw listing names against the canonical identity engine without mutating Neo4j.

Environment:

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4j-password
NEO4J_DATABASE=neo4j
CORS_ORIGINS=http://localhost:3000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
BESTBUY_API_KEY=
EBAY_BROWSE_TOKEN=
SERPAPI_KEY=
AMAZON_PAAPI_ACCESS_KEY=
AMAZON_PAAPI_SECRET_KEY=
AMAZON_PAAPI_PARTNER_TAG=
AUTH_REQUIRED=true
VIEWER_API_KEY=
ANALYST_API_KEY=
ADMIN_API_KEY=
SUPER_ADMIN_API_KEY=
FRONTEND_URL=http://localhost:3000
BACKEND_URL=http://localhost:8000
LOG_LEVEL=INFO
```

Live source credentials belong only in `backend/.env`. The frontend never receives raw vendor API keys. If no source key is configured, discovery dry runs return a safe `no configured pricing sources` result instead of fabricating data.

Pricing intelligence:
- Product, Vendor, PriceSnapshot, FieldEvidence, and PricingJob nodes are stored in Neo4j.
- PriceSnapshot nodes are append-only. Current product price fields are resolved views from accepted snapshots.
- Official/manufacturer and retailer data outrank aggregators for conflicting facts.
- Invalid prices, malformed identity data, and corrupted specs are rejected before graph merge.
- If sources are unavailable, the previous valid snapshot remains active and the product is marked stale.
- Discovery jobs classify unseen listings, canonicalize vendor naming variants, and merge new products into one Product node per canonical identity.
- The scheduler queues top-product hourly refreshes and broader six-hour discovery/refresh sweeps without blocking API requests.

Hardware intelligence:
- HardwareIntelligence nodes are derived from graph specs, accepted price snapshots, market history, and benchmark-like technical fields already stored in Neo4j.
- Validated telemetry snapshots can adjust enrichment scores, confidence, warnings, and reasoning without overwriting source facts.
- Enrichment computes workload suitability for gaming, workstation, simulation, rendering, AI, streaming, CAD, and video editing.
- Power and thermal modeling tracks TDP, peak draw, cooling requirements, PSU guidance, and transient spike risk.
- Longevity scoring models platform lifespan, future-proofing, and limiting factors such as VRAM, PCIe generation, socket, and memory generation.
- Compatibility enrichment adds BIOS, chipset, PCIe, memory stability, and cooling recommendation signals.
- Auto-build candidate ranking can use persisted intelligence value scores while preserving graph compatibility as the final gate.

Real-world telemetry:
- Benchmark, Game, Workload, DriverVersion, TelemetrySnapshot, and BottleneckFactor nodes are stored in Neo4j.
- Relationships include TESTED_ON, BENCHMARKED_WITH, AFFECTS, LIMITED_BY, HAS_TELEMETRY, HAS_ANOMALY, SHOWS_THROTTLING, REGRESSION_DETECTED, HAS_PATTERN, HAS_PREDICTION, and RECOMMENDED_FOR.
- Ingestion rejects low-trust sources, impossible FPS relationships, invalid frame-time percentiles, corrupted power readings, and malformed thermals.
- Snapshots preserve source, source URL, source tier, trust score, freshness score, driver/BIOS/firmware identifiers, resolution, workload engine, API dependencies, and sensitivity factors.
- The telemetry summary computes observed CPU/GPU/VRAM/thermal/driver/memory/bandwidth/storage bottlenecks, frame-time instability, thermal throttling risk, covered resolutions, and latest driver evidence.
- The reasoning engine detects FPS-low collapse, unstable frame pacing, thermal throttling, VRAM pressure, CPU saturation, power spikes, suspicious benchmark outliers, driver regressions, recurring instability patterns, BIOS-linked risk, memory pressure, cooling limits, PSU transient risk, and future workload limitations.
- Every reasoning report includes confidence score, sample size, evidence sources, a generated explanation, workload reasoning, bottleneck explanations, anomaly causes, recommended actions, and predictive mitigation.
- External benchmark feeds are accepted through the ingestion API; no local files or raw scraping dumps are stored.

Adaptive hardware cognition:
- HardwareCognition, Prediction, OutcomeObservation, PredictionValidation, ConfidenceState, CognitionEvidence, Contradiction, Hypothesis, and LearningJob nodes extend Neo4j into an adaptive experience graph.
- The cognition layer treats recommendations as probabilistic claims with confidence, evidence strength, sample size, telemetry stability, contradiction count, assumptions, and uncertainty.
- Predictions are validated against observed telemetry outcomes such as FPS, limiter, thermals, power, and instability.
- Confidence is updated per product, workload, and inference path when validation outcomes confirm or contradict prior predictions.
- Meta-reasoning exposes weak evidence, telemetry gaps, self-corrections, and contradiction density instead of hiding uncertainty.
- `docs/ADAPTIVE_COGNITION.md` describes graph extensions, learning flow, endpoint contracts, worker design, observability, UI behavior, and failure handling.

Reasoning governance:
- ReasoningGovernance, GovernanceSignal, EvidenceDecay, StabilizationAction, and GovernanceTarget nodes regulate cognition without deleting source facts.
- Governance computes confidence drift, confidence oscillation, calibration risk, contradiction density, telemetry freshness, evidence decay pressure, graph integrity, recursive feedback risk, anomaly density, and coverage gaps.
- Governed confidence is bounded by confidence ceilings, dampening factors, evidence decay, and multi-strategy consensus.
- Graph hygiene detects polluted nodes, corrupted inference chains, unstable telemetry clusters, circular evidence, stale telemetry dominance, and low-trust reasoning paths.
- Self-stabilization actions recommend confidence damping, evidence quarantine, recommendation downgrades, graph hygiene review, and revalidation jobs.
- `docs/REASONING_GOVERNANCE.md` describes the governance graph, stability controls, evidence decay, recursive protection, consensus, observability, and failure handling.

Evolution orchestration:
- CognitivePolicy, EvolutionOrchestration, PolicyEnforcement, SandboxEvaluation, PromotionDecision, RollbackEvent, MemoryDecision, and EvolutionAuditEvent nodes govern how cognition may evolve.
- Policies are versioned, scoped, auditable, reversible, and define confidence ceilings, freshness requirements, contradiction tolerances, anomaly escalation thresholds, adaptation speed, recommendation aggressiveness, self-generated trust caps, and telemetry trust growth.
- The orchestrator computes cognitive health index, evolution velocity, graph mutation velocity, anomaly growth, contradiction propagation, policy drift, adaptation pressure, confidence volatility, and intervention rate.
- Experimental reasoning strategies run as isolated sandbox evaluations before promotion.
- Rollback events preserve a path back to prior policy state when instability or policy violations are detected.
- `docs/EVOLUTION_ORCHESTRATION.md` describes policy enforcement, sandboxing, promotion, rollback, long-term memory governance, observability, and safety invariants.

Cognitive alignment:
- SystemIdentity, CognitiveConstitution, ObjectivePriority, AlignmentReport, AlignmentViolation, ObjectiveTradeoff, EthicsAssessment, AlignmentRollbackEvent, and AlignmentAuditEvent nodes preserve stable reasoning objectives.
- The objective hierarchy is explicit: correctness, safety/stability, evidence quality, transparency, optimization quality, then performance maximization.
- Alignment detects objective drift, safety ignored by performance optimization, hidden uncertainty, benchmark overfit, confidence without evidence, popularity over correctness, policy incoherence, and governance fragmentation.
- Recommendation ethics assesses misleading confidence, unsafe recommendations, unstable configurations, and biased optimization paths.
- Alignment health computes identity stability, objective coherence, optimization consistency, governance alignment, confidence integrity, transparency, and safety priority.
- `docs/COGNITIVE_ALIGNMENT.md` describes the system identity, constitution, alignment constraints, ethics, graph model, API, human governance support, and safety invariants.

Autonomous cognition:
- AutonomousAgent, CognitionEvent, AgentTask, AgentSignal, InvestigationRecord, AutonomousIntervention, HumanOversightAction, and AutonomousCognitionReport nodes turn cognition into an active governed agent system.
- Agents monitor telemetry freshness, benchmark contradictions, anomaly spikes, confidence inflation, governance stability, evolution drift, alignment integrity, and recommendation risk.
- Reversible risk-reducing actions can be applied automatically; graph quarantine, policy escalation, and rollback remain approval-bound.
- The FastAPI lifespan starts an optional `AutonomousAgentWorker` controlled by `AUTONOMOUS_AGENTS_ENABLED`, `AUTONOMOUS_AGENT_INTERVAL_SECONDS`, and `AUTONOMOUS_AGENT_MAX_PRODUCTS`.
- `docs/AUTONOMOUS_COGNITION.md` describes the agent roster, event queue, graph model, API, worker, observability, and safety boundaries.

Production operations:
- Protected endpoints require `X-API-Key`; public read endpoints remain separate from admin operations.
- Roles are hierarchical: viewer, analyst, admin, super_admin.
- Protected requests receive `X-Trace-ID`, write Neo4j `AuditEvent` nodes, and support `X-Idempotency-Key` for duplicate prevention.
- High-risk autonomous actions create `ApprovalItem` nodes instead of executing automatically.
- The Solo-Founder Operations Command Center combines Founder Daily Brief, Autonomy Queue, Approval Center, source/worker health, and recent audit visibility.
- Level 3 actions are blocked from autonomous execution and cannot be approved through the approval endpoint.
- `docs/OPERATIONS.md` covers security, idempotency, backups, restore, deployment, and solo-founder operations.

Backend:

```bash
cd backend
copy .env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
copy .env.example .env.local
npm install
npm run dev
```

Local production stack:

```bash
docker compose up --build
```

Docker configuration is provided but not locally verified because Docker CLI is not installed in this workspace.

Security notes:
- Do not commit `.env`, `.env.local`, logs, dumps, backups, or API keys.
- Backend owns all external vendor API keys.
- Frontend only receives `NEXT_PUBLIC_API_BASE_URL`.
- Use `AUTH_REQUIRED=true` outside isolated development.
- Use Level 2 approval workflows for graph quarantine, rollback, policy change, and high-impact autonomous actions.

Tests:

```bash
cd backend
python -m pytest
```
