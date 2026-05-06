# Phase 1: System Design

Short explanation: The platform is split into a deterministic graph data plane, a computational backend, and an XState-driven UI. Component facts are not kept in local files; Neo4j is the system of record.

Architecture diagram:

```text
User
  |
  v
Next.js App Router UI
  |-- XState builder machine prevents impossible UI transitions
  |-- Component selectors request graph-filtered candidates
  |-- Compatibility and performance panels render backend truth
  |
  v
FastAPI Backend
  |-- /components/options
  |-- /compatibility/check
  |-- /api/performance/calculate
  |-- CompatibilityEngine: socket, QVL, power, PCIe, USB, 3D volume
  |-- PerformanceEngine: NumPy workload matrix
  |
  v
Neo4j
  |-- Component nodes
  |-- Socket, memory, physical, bandwidth relationships
  |-- QVL and topology edges
```

Data flow:

```text
1. User selects component
2. XState assigns selected ID and enters validating
3. Next.js calls FastAPI
4. FastAPI queries Neo4j for nodes and relationship evidence
5. CompatibilityEngine evaluates graph-backed constraints
6. PerformanceEngine computes NumPy metrics when CPU and GPU exist
7. UI renders valid, partial, invalid, or degraded states
```

Service boundaries:
- Frontend owns rendering, form state, transitions, and loading/error states.
- Backend owns constraints, numerical modeling, and API contracts.
- Neo4j owns all hardware data, topology, compatibility, QVL, and dimensional facts.

Complete code:
- `frontend/machines/builderMachine.ts`
- `frontend/components/BuilderShell.tsx`
- `backend/app/main.py`
- `backend/app/services/compatibility.py`
- `backend/app/services/performance.py`

Example input/output:

```json
{
  "input": {
    "user_goal": "1440p gaming build",
    "selected_cpu_id": "cpu:amd:7800x3d"
  },
  "output": {
    "next_state": "validating",
    "service": "POST /compatibility/check",
    "data_source": "Neo4j"
  }
}
```

# Phase 2: Graph Database (Neo4j)

Short explanation: Neo4j models parts as typed component nodes and uses compatibility edges for socket, memory, QVL, fitment, bandwidth, and physical-blocking constraints.

Cypher schema:
- `backend/app/graph/schema.cypher`

Node definitions:
- `CPU`, `GPU`, `Motherboard`, `RAM`, `Case`, `Cooler`, `Storage`, `PSU`
- `Socket`, `MemoryType`
- Technical properties use prefixes: `spec_`, `dim_`, `bandwidth_`, `power_`

Relationships:
- `COMPATIBLE_WITH`
- `REQUIRES_SOCKET`
- `SUPPORTS_MEMORY_TYPE`
- `FITS_IN_CASE`
- `USES_PCIe_LANES`
- `SHARES_BANDWIDTH`
- `BLOCKS_PHYSICAL_SPACE`
- `QVL_VALIDATED_ON`

Queries:
- CPU to motherboard: `backend/app/graph/queries.py::CPU_MOTHERBOARD_SOCKET`
- PCIe validation: `backend/app/graph/validation_queries.cypher`
- Collision detection: `backend/app/graph/validation_queries.cypher`

Complete code:
- `backend/app/graph/schema.cypher`
- `backend/app/graph/queries.py`
- `backend/app/graph/validation_queries.cypher`
- `backend/app/graph/repository.py`

Example input/output:

```json
{
  "input": {
    "cpu_id": "cpu:amd:7800x3d",
    "motherboard_id": "motherboard:asus:b650e-i"
  },
  "output": {
    "compatible": true,
    "socket": "AM5"
  }
}
```

# Phase 3: Backend (FastAPI)

Short explanation: FastAPI exposes compatibility and performance endpoints. The compatibility engine reads graph evidence from Neo4j and computes engineering constraints. The performance endpoint computes FPS, frame variance, and bottlenecks with NumPy.

Project structure:

```text
backend/
  app/
    api/
    core/
    graph/
    models/
    services/
    main.py
  tests/
  pyproject.toml
```

Endpoints:
- `POST /compatibility/check`
- `POST /api/performance/calculate`
- `GET /components/options`
- `GET /health`

NumPy matrix logic:
- `backend/app/services/performance.py`
- Inputs are graph benchmark/spec vectors.
- Workload weights vary by gaming, simulation, and workstation purpose.
- Resolution applies a pixel workload multiplier.

Input/output models:
- `backend/app/models/api.py`
- `backend/app/models/domain.py`

Complete code:
- `backend/app/api/compatibility.py`
- `backend/app/api/performance.py`
- `backend/app/services/compatibility.py`
- `backend/app/services/performance.py`

Example input:

```json
{
  "selection": {
    "cpu_id": "cpu:amd:7800x3d",
    "gpu_id": "gpu:nvidia:4070ti-super",
    "motherboard_id": "motherboard:asus:b650e-i",
    "ram_id": "ram:gskill:ddr5-6000-32gb",
    "case_id": "case:fractal:terra",
    "cooler_id": "cooler:noctua:l12s",
    "storage_id": "storage:samsung:990pro-2tb",
    "psu_id": "psu:corsair:sf750"
  },
  "preferences": {
    "purpose": "gaming",
    "resolution": "1440p",
    "brand_bias": ["NVIDIA"],
    "noise_preference": "quiet",
    "upgrade_path_priority": 7
  }
}
```

Example output:

```json
{
  "valid": true,
  "state": "valid_configuration",
  "selected_component_count": 8,
  "total_power_draw_w": 503,
  "required_psu_w": 761,
  "checks": [
    {
      "id": "cpu:motherboard:socket",
      "status": "pass",
      "severity": "critical",
      "details": "CPU and motherboard share socket AM5."
    }
  ]
}
```

# Phase 4: State Machine (XState)

Short explanation: The XState machine owns the UI state contract and invokes backend validation on every component or preference change. Backend validation is the enforcement point for compatibility.

States:
- `idle`
- `selecting_cpu`
- `selecting_motherboard`
- `validating`
- `valid_configuration`
- `invalid_configuration`

Transitions:
- `SELECT_COMPONENT` assigns the selected component ID and enters `validating`.
- `SET_PREFERENCES` updates targets and revalidates when already in a result state.
- `RETRY` repeats backend validation.
- `RESET` returns to `idle`.

Guards:
- `backendAccepted` transitions to `valid_configuration` only when backend validation returns `valid: true`.
- The backend validation actor calls `/compatibility/check` and `/api/performance/calculate`.

Complete code:
- `frontend/machines/builderMachine.ts`

Example input/output:

```json
{
  "input": {
    "event": "SELECT_COMPONENT",
    "kind": "Motherboard",
    "componentId": "motherboard:asus:b650e-i"
  },
  "output": {
    "state": "validating",
    "then": "valid_configuration | invalid_configuration"
  }
}
```

# Phase 5: Frontend (Next.js)

Short explanation: The UI is the actual builder screen, not a landing page. It renders preferences, graph-filtered component selectors, backend compatibility checks, and performance telemetry.

File structure:

```text
frontend/
  app/
    layout.tsx
    page.tsx
    globals.css
  components/
  lib/
  machines/
  types/
```

Builder UI:
- `frontend/components/BuilderShell.tsx`
- `frontend/components/PreferencePanel.tsx`
- `frontend/components/ComponentSelector.tsx`

Selectors:
- `GET /components/options` through `frontend/lib/api.ts`
- Options are never locally hardcoded.

Alerts:
- Backend connectivity errors are shown inline.
- Constraint failures render as critical compatibility rows.

API integration:
- `frontend/lib/api.ts`

Complete code:
- `frontend/app/page.tsx`
- `frontend/components/*.tsx`
- `frontend/lib/api.ts`
- `frontend/types/builder.ts`

Example input/output:

```json
{
  "input": {
    "selector": "RAM",
    "current_motherboard": "motherboard:asus:b650e-i"
  },
  "output": {
    "api": "GET /components/options?kind=RAM&motherboard_id=motherboard%3Aasus%3Ab650e-i",
    "renders": "QVL-filtered RAM candidates"
  }
}
```

# Phase 6: Integration

Short explanation: The request lifecycle is deterministic: UI events enter XState, XState calls FastAPI, FastAPI queries Neo4j, backend engines return normalized contracts, and the UI renders the result.

Frontend to backend:
- `validateAndMeasure()` calls `/compatibility/check`, then `/api/performance/calculate` when CPU and GPU are present.

Backend to Neo4j:
- `Neo4jComponentRepository` uses query templates in `backend/app/graph/queries.py`.
- The app starts even if Neo4j is down; graph endpoints return `503` with details instead of breaking the UI.

Full request lifecycle:

```text
SELECT_COMPONENT
  -> builderMachine.validating
  -> POST /compatibility/check
  -> Neo4j query + compatibility engine
  -> optional POST /api/performance/calculate
  -> valid_configuration or invalid_configuration
```

Complete code:
- `frontend/lib/api.ts`
- `frontend/machines/builderMachine.ts`
- `backend/app/api/dependencies.py`
- `backend/app/graph/repository.py`

Example input/output:

```json
{
  "input": {
    "state": "validating",
    "selected": {
      "cpu_id": "cpu:amd:7800x3d",
      "motherboard_id": "motherboard:intel:z790"
    }
  },
  "output": {
    "state": "invalid_configuration",
    "reason": "CPU socket does not match motherboard socket"
  }
}
```

# Phase 7: Validation & Testing

Short explanation: Tests cover the deterministic math and geometry primitives locally. Neo4j integration tests should run against a populated test database because hardware data is not kept in this repository.

Edge cases:
- Incompatible RAM: missing `QVL_VALIDATED_ON` or unsupported `MemoryType` relationship yields a failing check.
- Insufficient PSU: modeled draw plus headroom exceeds `spec_continuous_wattage`.
- PCIe saturation: selected GPU and storage lanes exceed CPU plus chipset lane budget.

Complete code:
- `backend/tests/test_performance.py`
- `backend/tests/test_geometry.py`

Example input/output:

```json
{
  "input": {
    "gpu_length_mm": 340,
    "case_gpu_clearance_mm": 300
  },
  "output": {
    "check": "gpu:case:length",
    "status": "fail",
    "severity": "critical"
  }
}
```

