# Reasoning Governance and Cognitive Stability Engine

This layer regulates the adaptive cognition system. It does not overwrite raw telemetry, fabricate evidence, or silently promote recommendations. It produces governed confidence, graph hygiene signals, evidence decay records, consensus strategy scores, and stabilization actions.

## Architecture

```text
Telemetry snapshots + cognition reports
  -> ReasoningGovernanceEngine
    -> confidence stability checks
    -> evidence decay checks
    -> recursive feedback protection
    -> graph hygiene signals
    -> consensus strategy comparison
    -> stabilization actions
  -> Neo4j ReasoningGovernance subgraph
  -> FastAPI /governance endpoints
  -> Frontend governance panel
```

Implementation files:
- `backend/app/models/governance.py`
- `backend/app/services/governance.py`
- `backend/app/graph/governance_repository.py`
- `backend/app/api/governance.py`
- `frontend/components/PricingIntelligencePanel.tsx`

## Graph Extensions

New nodes:
- `ReasoningGovernance`
- `GovernanceSignal`
- `StabilizationAction`
- `EvidenceDecay`
- `GovernanceTarget`

Relationships:
- `(Product)-[:HAS_REASONING_GOVERNANCE]->(ReasoningGovernance)`
- `(ReasoningGovernance)-[:APPLIES_EVIDENCE_DECAY]->(EvidenceDecay)`
- `(EvidenceDecay)-[:GOVERNS_EVIDENCE]->(CognitionEvidence)`
- `(ReasoningGovernance)-[:RAISES_GOVERNANCE_SIGNAL]->(GovernanceSignal)`
- `(GovernanceSignal)-[:AFFECTS]->(GovernanceTarget)`
- `(ReasoningGovernance)-[:RECOMMENDS_STABILIZATION]->(StabilizationAction)`

Product nodes receive governed projection fields:
- `reasoning_health_score`
- `governed_confidence_score`
- `reasoning_governance_status`
- `reasoning_governance_updated_at`

## Confidence Stability

The stability engine prevents runaway confidence by calculating:
- confidence drift across predictions, validations, current confidence, and reliability
- confidence oscillation through sign changes in confidence deltas
- calibration risk from prediction confidence error
- governed confidence ceiling
- dampening factor

Governed confidence is bounded:

```text
governed_confidence =
  min(
    original_confidence * (1 - dampening)
    + consensus_confidence * dampening,
    confidence_ceiling
  )
```

No-telemetry products cannot exceed the no-evidence confidence ceiling.

## Evidence Decay

Each telemetry source gets an `EvidenceDecayRecord`:
- source
- age in days
- original weight
- decayed weight
- validation support
- statistical stability
- governance status

Older telemetry loses influence unless it is repeatedly validated or statistically stable. Low-trust decayed evidence can be marked `quarantined`.

## Graph Hygiene

Signals detect:
- polluted nodes
- corrupted inference chains
- unstable telemetry clusters
- low-trust reasoning paths
- circular evidence
- stale telemetry dominance

Signals are attached to the governance report and affected targets. They do not delete graph facts; they isolate and annotate risk so downstream recommendation code can lower certainty.

## Recursive Reasoning Protection

Recursive feedback risk rises when:
- predictions reuse concentrated evidence sources
- confidence is high with no independent validation
- contradictions exist without new outcome data
- evidence paths appear self-reinforcing

When risk crosses threshold, governance recommends:
- confidence damping
- recommendation downgrade
- revalidation jobs
- graph hygiene review

## Multi-Strategy Consensus

The engine compares four strategies:
- `telemetry_weighted`
- `validation_calibrated`
- `decay_adjusted`
- `contradiction_adverse`

Disagreement between strategies becomes a governed risk signal. Ranking should prefer governed confidence rather than raw adaptive confidence when recommendations are surfaced.

## API

Endpoints:

```text
GET  /governance/products/{product_id}
POST /governance/refresh
```

Example response excerpt:

```json
{
  "status": "degraded",
  "metrics": {
    "overall_health": 0.61,
    "confidence_drift": 0.18,
    "contradiction_density": 0.25,
    "recursive_feedback_risk": 0.52
  },
  "stability": {
    "original_confidence": 0.72,
    "governed_confidence": 0.58,
    "confidence_ceiling": 0.62,
    "revalidation_required": true
  }
}
```

## Observability

The frontend exposes:
- governance status
- overall health
- governed confidence
- confidence drift
- recursive feedback risk
- graph integrity
- evidence decay
- consensus strategies
- hygiene signals
- stabilization actions

The report also includes an audit trail:
- evidence sources
- reasoning paths
- confidence evolution
- anomaly history
- contradiction history

## Failure Handling

Neo4j unavailable:
- API returns a service error from the repository boundary.
- Frontend panel degrades independently from product search and pricing.

No telemetry:
- Governance returns reduced health and bounded confidence rather than invented certainty.

Stale telemetry dominance:
- Evidence decay records reduce influence.
- Stabilization actions request revalidation.

Contradictory recommendation loop:
- Graph hygiene signal marks the inference chain.
- Governed confidence is dampened.
- Recommendation certainty is downgraded.
