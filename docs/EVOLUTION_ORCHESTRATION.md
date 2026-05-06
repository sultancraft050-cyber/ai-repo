# Evolution Orchestration and Cognitive Policy Engine

This layer governs how cognition is allowed to evolve over time. It is deliberately separate from telemetry, cognition, and governance so policy changes remain versioned, auditable, reversible, and inspectable.

## Architecture

```text
Governed cognition report
  -> active CognitivePolicy
  -> EvolutionOrchestrator
    -> evolution metrics
    -> policy enforcement decisions
    -> sandbox evaluations
    -> model promotion decisions
    -> rollback events
    -> long-term memory decisions
  -> Neo4j evolution graph
  -> FastAPI /evolution endpoints
  -> frontend evolution orchestration panel
```

## Cognitive Policy Layer

`CognitivePolicy` controls:
- maximum confidence ceiling
- evidence freshness requirement
- contradiction tolerance
- anomaly escalation threshold
- adaptation rate limit
- recommendation aggressiveness
- self-generated trust cap
- telemetry trust growth rate
- policy drift limit
- human approval requirement

Policies are:
- versioned with `version`
- reversible with `supersedes_policy_id`
- auditable with `created_by`, `created_at`, and `change_reason`
- scoped, currently defaulting to `global`

## Evolution Orchestrator

The orchestrator monitors:
- evolution velocity
- graph mutation velocity
- anomaly growth
- contradiction propagation
- policy drift
- adaptation pressure
- confidence volatility
- intervention rate

These metrics are combined into a `CognitiveHealthIndex`:
- reasoning stability
- graph health
- evidence freshness
- contradiction resilience
- anomaly pressure
- adaptation volatility
- policy alignment

## Adaptation Rate Control

Adaptation is throttled when:
- adaptation pressure exceeds the active policy rate limit
- confidence volatility rises
- contradiction propagation grows
- graph mutation velocity increases too quickly

The enforcement output never silently rewrites canonical reasoning. It emits policy decisions such as `allow`, `throttle`, `block`, or `escalate`.

## Policy Enforcement

Rules enforced:
- `confidence_ceiling`
- `evidence_freshness`
- `contradiction_tolerance`
- `anomaly_escalation`
- `adaptation_rate`
- `self_generated_trust`
- `policy_drift`

Example:

```json
{
  "rule": "adaptation_rate",
  "status": "throttle",
  "observed_value": 0.19,
  "threshold": 0.12,
  "action": "smooth transition and delay policy promotion"
}
```

## Cognitive Sandboxing

Experimental reasoning strategies are evaluated as isolated sandbox models:
- `strategy:telemetry_weighted`
- `strategy:validation_calibrated`
- `strategy:decay_adjusted`
- `strategy:contradiction_adverse`

Promotion requires:
- stability above threshold
- acceptable prediction accuracy
- low contradiction impact
- sufficient telemetry consistency
- human approval when required by policy

## Model Promotion

Promotion decisions can be:
- `promote`
- `hold`
- `reject`
- `quarantine`

The default policy requires human approval, so even ready strategies are held until approved.

## Rollback

Rollback events are emitted when:
- policy enforcement blocks or escalates evolution
- governance reports unstable or quarantined cognition
- adaptation pressure exceeds safe limits

Rollback events include:
- source policy
- target policy
- trigger
- reason
- approval state

## Long-Term Memory Governance

Memory decisions:
- `strengthen`: repeatedly validated and stable patterns
- `retain`: usable but not yet strongly validated
- `decay`: stale or unsupported patterns
- `archive`: quarantined or obsolete patterns

This keeps historical cognition from dominating current recommendations without evidence support.

## API

Endpoints:

```text
GET  /evolution/products/{product_id}
GET  /evolution/policies/active
POST /evolution/policies
POST /evolution/refresh
POST /evolution/rollback
```

## Observability

The frontend exposes:
- cognitive health index
- evolution velocity
- policy drift
- adaptation pressure
- confidence volatility
- policy envelope
- enforcement decisions
- sandbox promotion readiness
- rollback readiness
- memory governance

## Safety Invariants

The system must never:
- fully trust self-generated conclusions
- recursively validate itself indefinitely
- mutate canonical reasoning rules without policy and governance approval
- promote experimental reasoning behavior outside sandbox evaluation
- hide rollback requirements

## Failure Handling

No active policy:
- the default stable policy is created and applied.

Unstable evolution:
- enforcement emits block/throttle/escalation decisions.
- rollback event is prepared for approval.

Policy drift:
- changes beyond policy drift limit require human approval.

Stale cognition memory:
- unsupported evidence is decayed or archived.

Neo4j unavailable:
- repository boundary returns service failure.
- UI panel degrades independently.
