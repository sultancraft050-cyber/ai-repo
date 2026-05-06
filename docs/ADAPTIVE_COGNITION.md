# Adaptive Learning, Outcome Validation, and Hardware Cognition

This document describes the production architecture now implemented around `backend/app/services/cognition.py`, `backend/app/graph/cognition_repository.py`, `backend/app/api/cognition.py`, and the frontend cognition panel in `frontend/components/PricingIntelligencePanel.tsx`.

The system treats hardware recommendations as probabilistic claims. It stores predictions, validates them against observed telemetry, adjusts confidence, exposes uncertainty, and persists the learning state back into Neo4j.

## 1. Architecture Explanation

Text architecture:

```text
Frontend cognition panel
  -> FastAPI /cognition endpoints
    -> HardwareCognitionService
      -> Neo4jTelemetryRepository
      -> TelemetryAnalysisEngine
      -> TelemetryReasoningEngine
      -> HardwareCognitionEngine
      -> Neo4jCognitionRepository
        -> Neo4j graph: Product, TelemetrySnapshot, Prediction, Validation, ConfidenceState, Contradiction
```

Production reasoning:
- User requests do not run global learning loops synchronously.
- The API reads accepted telemetry and stored reasoning, then emits a bounded cognition report.
- Long-running refresh is queue-oriented through `CognitionWorker`.
- No fabricated benchmarks are inserted. Missing telemetry becomes uncertainty, assumptions, and coverage gaps.

Example flow:

```text
GET /cognition/products/gpu:amd:radeon-rx-7600-reference
  -> load telemetry snapshots
  -> compute summary and reasoning if missing
  -> detect contradictions
  -> generate active predictions
  -> return confidence, uncertainty, meta-reasoning, predictions, validations
```

## 2. Neo4j Graph Extensions

New node labels:
- `HardwareCognition`
- `Prediction`
- `OutcomeObservation`
- `PredictionValidation`
- `ConfidenceState`
- `CognitionEvidence`
- `Hypothesis`
- `Contradiction`
- `LearningJob`

Key relationships:
- `(Product)-[:HAS_COGNITION]->(HardwareCognition)`
- `(Product)-[:HAS_PREDICTION]->(Prediction)`
- `(Product)-[:HAS_OUTCOME]->(OutcomeObservation)`
- `(Prediction)-[:SUPPORTED_BY]->(CognitionEvidence)`
- `(Prediction)-[:HAS_CONFIDENCE]->(ConfidenceState)`
- `(Prediction)-[:VALIDATED_BY]->(PredictionValidation)`
- `(Prediction)-[:CONTRADICTED_BY]->(PredictionValidation)`
- `(Product)-[:HAS_CONTRADICTION]->(Contradiction)`

Schema constraints are applied at startup:

```cypher
CREATE CONSTRAINT cognition_prediction_id IF NOT EXISTS
FOR (n:Prediction) REQUIRE n.id IS UNIQUE;

CREATE INDEX confidence_key IF NOT EXISTS
FOR (n:ConfidenceState) ON (n.scope, n.key);
```

Implementation detail:
- Full payloads are stored as validated JSON on the graph node.
- Queryable scalar fields such as `confidence_score`, `kind`, `product_id`, `created_at`, and `status` are projected into node properties.

## 3. Learning Pipeline Design

The learning loop is:

```text
generate prediction
  -> store reasoning path and evidence
  -> observe telemetry outcome
  -> validate predicted vs observed value
  -> compute correctness and calibration error
  -> update product/workload/inference-path confidence
  -> persist contradictions and confidence downgrades
  -> rebuild cognition report
```

Implementation detail:
- `HardwareCognitionEngine.generate_predictions` creates FPS, bottleneck, thermal, power, and upgrade-limit predictions from accepted telemetry.
- `HardwareCognitionEngine.validate_outcome` compares observations against predictions.
- `HardwareCognitionService.validate_outcome` persists outcomes, validations, confidence state, contradictions, and refreshed reports when `persist=true`.

Example outcome validation request:

```json
{
  "persist": true,
  "outcome": {
    "product_id": "gpu:test",
    "prediction_id": "prediction-123",
    "workload": "ARK Survival Ascended",
    "resolution": "1440p",
    "observed_fps": 48,
    "evidence": {
      "source": "post-build telemetry",
      "methodology": "10 minute gameplay capture",
      "trust_score": 0.82,
      "freshness_score": 0.97,
      "repeatability_score": 0.72,
      "evidence_rank": "validated_telemetry"
    }
  }
}
```

## 4. Confidence Propagation Logic

Confidence is represented by `ConfidenceVector`:
- `confidence_score`
- `evidence_strength`
- `sample_size`
- `workload_consistency`
- `telemetry_stability`
- `contradiction_count`
- `uncertainty_score`
- `assumptions`
- `conflicting_evidence`

Formula shape:

```text
evidence_strength =
  source_quality * 0.25
+ freshness * 0.12
+ repeatability * 0.20
+ sample_factor * 0.22
+ workload_consistency * 0.12
+ reasoning_confidence * 0.09
- contradiction_penalty

confidence_score =
  evidence_strength * 0.72
+ telemetry_stability * 0.18
+ source_quality * 0.10
```

Production reasoning:
- Small sample sizes increase uncertainty.
- Contradictions reduce evidence strength.
- Workload inconsistency avoids overgeneralizing across games, engines, and resolutions.
- Validation correctness updates `ConfidenceState` for product, workload, and inference path.

## 5. Anomaly Detection Engine

The cognition layer consumes anomaly outputs from telemetry reasoning and adds contradiction signals:
- FPS spread across accepted samples.
- Thermal conflict across accepted samples.
- Unusual FPS-per-watt from low-trust samples.
- Instability across multiple driver versions.
- Source disagreement from contradicted predictions.

Example contradiction:

```json
{
  "kind": "fps_spread",
  "severity": "warning",
  "confidence_score": 0.69,
  "explanation": "Accepted FPS telemetry has 24.0% normalized spread.",
  "affected_workloads": ["ARK Survival Ascended"]
}
```

## 6. Prediction Validation System

Validation compares a stored prediction against an observed outcome:
- FPS predictions compare `predicted_value` to `observed_fps`.
- Thermal predictions compare against `observed_average_temp_c`.
- Power predictions compare against `observed_peak_power_w`.
- Bottleneck predictions compare `predicted_limiter` to `observed_limiter`.

Status thresholds:
- `validated`: relative error <= 8 percent.
- `partially_validated`: relative error <= 18 percent.
- `contradicted`: relative error > 18 percent.
- `insufficient_evidence`: outcome lacks the required observed field.

Output example:

```json
{
  "status": "contradicted",
  "relative_error": 0.9167,
  "confidence_error": 0.42,
  "calibrated_confidence": 0.51,
  "correctness_score": 0.0833
}
```

## 7. Meta-Reasoning Architecture

`MetaReasoningReport` explains how reliable the system believes its own reasoning is.

It exposes:
- weak evidence
- assumptions
- telemetry gaps
- contradiction density
- self-corrections

Examples:
- `small telemetry sample size`
- `hotspot thermal telemetry missing`
- `confidence reduced due to contradiction density`
- `driver-sensitive predictions require revalidation after updates`

Production reasoning:
- The platform does not hide weak evidence.
- Confidence is never treated as certainty.
- Missing telemetry is a first-class output, not a UI failure.

## 8. FastAPI Endpoint Design

Implemented endpoints:

```text
GET  /cognition/products/{product_id}
POST /cognition/products/{product_id}/predictions
POST /cognition/outcomes/validate
POST /cognition/refresh
```

Examples:

```bash
curl "http://127.0.0.1:8000/cognition/products/gpu:test?refresh=true&persist=true"
```

```bash
curl -X POST "http://127.0.0.1:8000/cognition/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"product_ids\":[\"gpu:test\"],\"wait\":false,\"persist\":true}"
```

Production behavior:
- `refresh=true` recomputes the report.
- `persist=false` returns computed cognition without writing graph mutations.
- `/refresh` queues work unless `wait=true`.

## 9. Data Models

Core models live in `backend/app/models/cognition.py`:
- `EvidenceQuality`
- `ConfidenceVector`
- `PredictionRecord`
- `OutcomeObservation`
- `PredictionValidation`
- `ConfidenceState`
- `ContradictionSignal`
- `MetaReasoningReport`
- `HardwareCognitionReport`
- `LearningJob`

Example prediction:

```json
{
  "kind": "fps",
  "predicted_value": 92,
  "predicted_unit": "fps",
  "workload": "ARK Survival Ascended",
  "resolution": "1440p",
  "confidence": {
    "confidence_score": 0.62,
    "evidence_strength": 0.58,
    "sample_size": 1,
    "uncertainty_score": 0.38
  }
}
```

## 10. Async Worker Design

`CognitionWorker` runs as a background thread attached to FastAPI app state.

Supported job kinds:
- `generate_predictions`
- `refresh_cognition`
- `validate_outcome`

Design constraints:
- API requests enqueue work and return job metadata.
- Workers own graph mutation for queued jobs.
- Exceptions update `LearningJob.error` and `LearningJob.status`.
- The worker uses repository/service boundaries rather than direct Cypher.

Example queued job node:

```json
{
  "kind": "refresh_cognition",
  "status": "queued",
  "payload": {
    "product_ids": ["gpu:test"],
    "persist": true
  }
}
```

## 11. Observability and Logging Strategy

Current auditable outputs:
- `HardwareCognitionReport.audit_events`
- `LearningJob.status`
- `LearningJob.error`
- validation explanation payloads
- confidence downgrade reasons
- contradiction nodes

Audit event example:

```text
reasoning_report=telemetry-reasoning-gpu:test
confidence_score=0.6210
evidence_strength=0.5830
contradictions=1
validations=3
```

Production extension point:
- Replace process logging with structured JSON logs.
- Emit OpenTelemetry spans around graph reads, cognition compute, graph writes, and worker job transitions.
- Attach correlation IDs from API request to `LearningJob` and report audit events.

## 12. Frontend Reasoning UX

The frontend exposes cognition in a separate analytical panel:
- confidence
- uncertainty
- evidence strength
- telemetry stability
- reliability
- calibration error
- contradiction rate
- meta-reasoning gaps
- active predictions
- validation memory
- contradiction warnings

UX behavior:
- Loading state is isolated.
- Missing cognition shows a degraded state message.
- Pricing, hardware intelligence, telemetry reasoning, and cognition can fail independently.
- UI avoids simplistic green/red certainty and shows uncertainty explicitly.

## 13. Example Telemetry Flows

Flow A: prediction generation

```text
TelemetrySnapshot accepted
  -> TelemetrySummary computes FPS, 1% low, bottleneck, thermal risk
  -> TelemetryReasoningReport detects anomalies and workload pressure
  -> CognitionReport emits active predictions and assumptions
```

Flow B: outcome validation

```text
User or telemetry source observes FPS after build
  -> POST /cognition/outcomes/validate
  -> prediction error computed
  -> ConfidenceState adjusted
  -> ContradictionSignal created if prediction was wrong
  -> Product cognition report refreshed
```

Flow C: no telemetry

```text
Product has no TelemetrySnapshot
  -> cognition report returns sample_size=0
  -> assumptions and telemetry gaps explain missing evidence
  -> frontend shows waiting state instead of breaking
```

## 14. Example Reasoning Outputs

Example learning summary:

```json
[
  "Confidence 62% from 3 sample(s); uncertainty 40%.",
  "Evidence strength 58%, workload consistency 77%, telemetry stability 64%.",
  "1 contradiction signal(s) reduce certainty.",
  "Current probabilistic limiter memory favors VRAM."
]
```

Example meta-reasoning:

```json
{
  "weak_evidence": [
    "contradictory telemetry detected"
  ],
  "telemetry_gaps": [
    "driver version coverage missing",
    "limited resolution coverage"
  ],
  "self_corrections": [
    "confidence reduced due to contradiction density"
  ]
}
```

## 15. Failure Scenarios and Handling

No telemetry:
- Return a cognition report with low confidence and explicit gaps.
- Do not fabricate performance claims.

Contradictory benchmarks:
- Create `Contradiction` nodes.
- Reduce evidence strength.
- Surface conflicting evidence in the UI.

Wrong prediction:
- Create `PredictionValidation` with `contradicted`.
- Adjust calibration error and reliability.
- Add confidence downgrade reasons.

Neo4j unavailable:
- FastAPI returns a normal service error from the repository boundary.
- Frontend cognition panel degrades without taking down pricing or search.

Worker failure:
- `LearningJob.status` becomes `failed`.
- `LearningJob.error` stores the exception string.
- Existing valid cognition reports remain readable.

Low-trust evidence:
- Evidence remains attributable.
- Confidence is lower.
- The system reports weak evidence instead of hiding it.
