# Autonomous Cognitive Agent System

The autonomous layer turns the governed cognition stack into an active monitoring system. It does not allow agents to mutate policy, promote models, or quarantine evidence without governance checks. Reversible actions such as confidence dampening and recommendation downgrades can be applied immediately because they reduce risk.

## Agent Model

Agents are persisted in Neo4j as `AutonomousAgent` nodes:

- Telemetry Agent monitors freshness, coverage, and refresh triggers.
- Benchmark Validation Agent handles benchmark contradictions and driver-sensitive regressions.
- Anomaly Investigation Agent correlates repeated instability patterns.
- Confidence Audit Agent detects unsupported confidence growth.
- Governance Stability Agent watches graph hygiene and polluted evidence risk.
- Evolution Monitoring Agent watches policy drift and rollback readiness.
- Alignment Integrity Agent enforces the cognitive constitution.
- Recommendation Verification Agent checks recommendation safety before ranking.

Each agent stores responsibilities, allowed actions, forbidden actions, cadence, priority, and governing constraints.

## Event-Driven Cognition

The system emits `CognitionEvent` nodes for:

- stale evidence
- benchmark contradiction
- anomaly spike
- policy drift
- confidence inflation
- alignment drift
- recommendation risk
- graph pollution
- scheduled evaluation ticks

Events are converted into prioritized `AgentTask` nodes. The priority order is safety and stability first, then contradiction resolution, telemetry freshness, anomaly investigation, and recommendation optimization.

## Inter-Agent Communication

Agents communicate by graph-persisted `AgentSignal` nodes. Signals include the channel:

- `event_queue`
- `governance_signal`
- `graph_event`
- `reasoning_notification`

This keeps communication auditable and prevents hidden recursive loops.

## Self-Healing Boundaries

Autonomous interventions are intentionally constrained:

- Applied automatically: confidence reduction, recommendation downgrade, constitution guardrail.
- Queued automatically: telemetry refresh, revalidation request.
- Requires approval: evidence quarantine, policy escalation, evolution rollback.

Agents cannot override the cognitive constitution or increase confidence from self-generated conclusions.

## Neo4j Graph Extension

New nodes:

- `AutonomousAgent`
- `CognitionEvent`
- `AgentTask`
- `AgentSignal`
- `InvestigationRecord`
- `AutonomousIntervention`
- `HumanOversightAction`
- `AutonomousCognitionReport`

New relationships:

- `(Product)-[:HAS_AUTONOMY_REPORT]->(AutonomousCognitionReport)`
- `(AutonomousCognitionReport)-[:HAS_COGNITION_EVENT]->(CognitionEvent)`
- `(AutonomousCognitionReport)-[:HAS_AGENT_TASK]->(AgentTask)`
- `(AutonomousCognitionReport)-[:HAS_AGENT_SIGNAL]->(AgentSignal)`
- `(AutonomousCognitionReport)-[:HAS_INVESTIGATION]->(InvestigationRecord)`
- `(AutonomousCognitionReport)-[:HAS_AUTONOMOUS_INTERVENTION]->(AutonomousIntervention)`
- `(AutonomousCognitionReport)-[:HAS_HUMAN_OVERSIGHT]->(HumanOversightAction)`
- `(AutonomousAgent)-[:PERFORMED]->(AgentTask | InvestigationRecord | AutonomousIntervention)`

## API

- `GET /autonomy/agents`
- `GET /autonomy/products/{product_id}?refresh=true&persist=true`
- `POST /autonomy/run`
- `POST /autonomy/events`

Example run payload:

```json
{
  "product_ids": ["gpu:amd:radeon-rx-7600-reference"],
  "refresh": true,
  "persist": true
}
```

Example event payload:

```json
{
  "event": {
    "kind": "driver_regression",
    "severity": "critical",
    "product_id": "gpu:amd:radeon-rx-7600-reference",
    "source": "telemetry-feed",
    "message": "Driver regression detected in frame-time telemetry.",
    "payload": {
      "driver_from": "551.86",
      "driver_to": "552.22"
    },
    "priority_score": 0.93
  },
  "persist": true,
  "trigger_analysis": true
}
```

## Background Worker

`AutonomousAgentWorker` runs in the FastAPI lifespan when `AUTONOMOUS_AGENTS_ENABLED=true`. It periodically selects graph products with the oldest cognition updates and runs governed autonomous evaluation.

Environment controls:

- `AUTONOMOUS_AGENTS_ENABLED`
- `AUTONOMOUS_AGENT_INTERVAL_SECONDS`
- `AUTONOMOUS_AGENT_MAX_PRODUCTS`

## Observability

The frontend exposes:

- active agents
- cognition event queue
- agent tasks
- inter-agent signals
- investigations
- autonomous interventions
- required human oversight actions
- autonomy health index

The UI avoids fake certainty by showing queue pressure, approval gates, and whether interventions are applied, queued, blocked, or approval-bound.
