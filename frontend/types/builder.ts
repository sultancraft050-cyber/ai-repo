export type ComponentKind =
  | "CPU"
  | "GPU"
  | "Motherboard"
  | "RAM"
  | "Case"
  | "Cooler"
  | "Storage"
  | "PSU";

export type ProductCategory =
  | ComponentKind
  | "Monitor"
  | "Keyboard"
  | "Mouse"
  | "Headset"
  | "Capture Card"
  | "Fans"
  | "Custom Cooling"
  | "Accessories";

export type Purpose = "gaming" | "simulation" | "workstation";
export type Resolution = "1080p" | "1440p" | "4K";
export type NoisePreference = "quiet" | "balanced" | "performance";
export type CaseSize = "ITX" | "mATX" | "ATX" | "EATX";

export type SelectedComponents = {
  cpu_id?: string;
  gpu_id?: string;
  motherboard_id?: string;
  ram_id?: string;
  case_id?: string;
  cooler_id?: string;
  storage_id?: string;
  psu_id?: string;
};

export type BuildPreferences = {
  budget_usd?: number;
  purpose: Purpose;
  resolution: Resolution;
  region: string;
  brand_bias: string[];
  size?: CaseSize;
  noise_preference: NoisePreference;
  upgrade_path_priority: number;
};

export type ComponentOption = {
  id: string;
  kind: ComponentKind;
  name: string;
  brand?: string;
  price_usd?: number;
  summary?: string;
};

export type ConstraintCheck = {
  id: string;
  label: string;
  status: "pass" | "fail" | "warning" | "unknown";
  severity: "info" | "warning" | "critical";
  details: string;
  evidence: Record<string, unknown>;
};

export type CompatibilityResponse = {
  valid: boolean;
  state: "partial" | "valid_configuration" | "invalid_configuration";
  checks: ConstraintCheck[];
  total_power_draw_w?: number;
  required_psu_w?: number;
  selected_component_count: number;
  missing_component_ids: string[];
};

export type PerformanceResponse = {
  expected_fps: number;
  one_percent_low_fps: number;
  frame_time_ms: number;
  frame_time_variance_ms: number;
  bottleneck: {
    cpu_percent: number;
    gpu_percent: number;
    memory_percent: number;
    display_percent: number;
  };
  confidence: "high" | "medium" | "low";
  model_inputs: Record<string, number>;
  reasoning: string[];
};

export type ValidationBundle = {
  compatibility: CompatibilityResponse;
  performance: PerformanceResponse | null;
};

export type GeneratedPart = {
  kind: ComponentKind;
  id: string;
  name: string;
  brand?: string;
  price_usd: number;
  price_source?: string;
  price_vendor?: string;
  price_freshness_score?: number;
  price_trust_score?: number;
  price_stale: boolean;
  reasoning: string;
};

export type GeneratedBuild = {
  label: "best_performance" | "best_value" | "balanced" | "closest_valid";
  parts: GeneratedPart[];
  selection: SelectedComponents;
  total_cost_usd: number;
  score: number;
  performance: PerformanceResponse;
  compatibility: CompatibilityResponse;
  bottleneck_breakdown: PerformanceResponse["bottleneck"];
  reasoning_summary: string[];
};

export type BuildGenerateResponse = {
  builds: GeneratedBuild[];
  compatibility_status: "valid" | "closest_valid" | "no_solution";
  explored_configurations: number;
  pruned_configurations: number;
  fallback_explanation?: string;
};

export type SourceType =
  | "manufacturer"
  | "retailer_api"
  | "aggregator_api"
  | "verified_scraping"
  | "inferred";

export type ProductSearchResult = {
  id: string;
  canonical_key?: string;
  name: string;
  brand?: string;
  category: ProductCategory | string;
  model?: string;
  image_url?: string;
  current_best_price?: number;
  current_best_currency?: string;
  current_best_vendor?: string;
  current_price_freshness_score?: number;
  current_price_trust_score?: number;
  current_price_timestamp?: string;
  stale: boolean;
  best_value: boolean;
  price_drop_percent?: number;
};

export type PriceSnapshotView = {
  id: string;
  vendor_id: string;
  vendor_name: string;
  price: number;
  currency: string;
  availability: "in_stock" | "out_of_stock" | "preorder" | "backorder" | "unknown";
  timestamp: string;
  shipping_cost: number;
  product_url?: string;
  source: string;
  source_type: SourceType;
  source_tier: number;
  trust_score: number;
  freshness_score: number;
  stale: boolean;
  flags: string[];
};

export type PriceHistoryPoint = {
  timestamp: string;
  vendor_name: string;
  price: number;
  currency: string;
  availability: PriceSnapshotView["availability"];
  trust_score: number;
  freshness_score: number;
};

export type ProductDetail = ProductSearchResult & {
  specs: Record<string, unknown>;
  msrp?: number;
  latest_prices: PriceSnapshotView[];
};

export type PricingRefreshResponse = {
  job_ids: string[];
  status: "queued" | "running" | "completed" | "failed" | "stale";
  message: string;
  accepted_snapshots: number;
  rejected_snapshots: number;
  stale_products: string[];
};

export type ProductDiscoveryResponse = {
  job_ids: string[];
  status: "queued" | "running" | "completed" | "failed" | "stale";
  message: string;
  query_count: number;
  categories: string[];
  accepted_snapshots: number;
  rejected_snapshots: number;
};

export type ProductCategoryResponse = {
  categories: string[];
  build_critical_categories: string[];
};

export type WorkloadName =
  | "gaming"
  | "workstation"
  | "simulation"
  | "rendering"
  | "ai"
  | "streaming"
  | "cad"
  | "video_editing";

export type BenchmarkScores = {
  gaming: number;
  productivity: number;
  ai_ml: number;
  rendering: number;
  simulation: number;
  rasterization: number;
  ray_tracing: number;
  vram_efficiency: number;
  tensor_capability: number;
  single_core: number;
  multi_core: number;
  cache_efficiency: number;
  thermal_efficiency: number;
};

export type WorkloadSuitability = {
  workload: WorkloadName;
  score: number;
  label: "excellent" | "strong" | "usable" | "limited";
  reasons: string[];
};

export type TelemetryBottleneckBreakdown = {
  cpu_percent: number;
  gpu_percent: number;
  vram_percent: number;
  thermal_percent: number;
  driver_percent: number;
  memory_percent: number;
  bandwidth_percent: number;
  storage_percent: number;
};

export type TelemetrySummary = {
  product_id: string;
  sample_count: number;
  confidence: "high" | "medium" | "low";
  average_fps?: number;
  one_percent_low_fps?: number;
  average_frame_time_ms?: number;
  frame_time_instability_score?: number;
  average_power_w?: number;
  peak_power_w?: number;
  average_temp_c?: number;
  hotspot_temp_c?: number;
  bottleneck: TelemetryBottleneckBreakdown;
  primary_limiter: "cpu" | "gpu" | "vram" | "thermal" | "driver" | "memory" | "bandwidth" | "storage" | "none";
  thermal_throttling_risk: "low" | "medium" | "high" | "unknown";
  covered_resolutions: string[];
  covered_workloads: string[];
  latest_driver_versions: string[];
  notes: string[];
  updated_at: string;
};

export type TelemetryEvidencePoint = {
  metric: string;
  value: number | string;
  threshold?: number | string;
  source: string;
  snapshot_id?: string;
  timestamp?: string;
};

export type TelemetrySeverity = "info" | "warning" | "critical";

export type TelemetryAnomaly = {
  id: string;
  kind:
    | "fps_drop"
    | "frame_pacing"
    | "thermal_throttling"
    | "vram_pressure"
    | "cpu_saturation"
    | "driver_regression"
    | "power_spike"
    | "memory_pressure"
    | "benchmark_outlier"
    | "workload_bottleneck";
  severity: TelemetrySeverity;
  title: string;
  explanation: string;
  confidence_score: number;
  sample_size: number;
  evidence: TelemetryEvidencePoint[];
  affected_workloads: string[];
  affected_resolutions: string[];
  likely_causes: string[];
  recommended_actions: string[];
};

export type DriverRegressionFinding = {
  id: string;
  driver_from: string;
  driver_to: string;
  workload: string;
  resolution: string;
  fps_delta_percent?: number;
  instability_delta?: number;
  thermal_delta_c?: number;
  severity: TelemetrySeverity;
  confidence_score: number;
  explanation: string;
  evidence_sources: string[];
};

export type TelemetryPatternFinding = {
  id: string;
  kind:
    | "recurring_instability"
    | "problematic_driver"
    | "problematic_bios"
    | "unstable_memory_configuration"
    | "workload_incompatibility"
    | "insufficient_cooling"
    | "psu_instability_risk";
  severity: TelemetrySeverity;
  title: string;
  explanation: string;
  confidence_score: number;
  sample_size: number;
  evidence_sources: string[];
  recommended_actions: string[];
};

export type PredictiveTelemetryInsight = {
  id: string;
  horizon: string;
  predicted_limitation: TelemetrySummary["primary_limiter"];
  risk_score: number;
  confidence_score: number;
  explanation: string;
  evidence_sources: string[];
  mitigation: string[];
};

export type TelemetryReasoningReport = {
  id: string;
  product_id: string;
  generated_at: string;
  confidence_score: number;
  sample_size: number;
  evidence_sources: string[];
  ai_explanation?: string;
  summary: string[];
  workload_reasoning: string[];
  bottleneck_explanations: {
    kind: TelemetrySummary["primary_limiter"];
    percent: number;
    reason: string;
  }[];
  anomalies: TelemetryAnomaly[];
  driver_regressions: DriverRegressionFinding[];
  patterns: TelemetryPatternFinding[];
  predictions: PredictiveTelemetryInsight[];
  recommended_for: string[];
  warnings: string[];
};

export type EvidenceQuality = {
  source: string;
  methodology?: string | null;
  benchmark_conditions: Record<string, unknown>;
  hardware_configuration: Record<string, unknown>;
  timestamp: string;
  trust_score: number;
  freshness_score: number;
  repeatability_score: number;
  evidence_rank:
    | "validated_telemetry"
    | "repeated_benchmark_consistency"
    | "official_specification"
    | "historical_trend"
    | "inferred_estimation";
};

export type ConfidenceVector = {
  confidence_score: number;
  evidence_strength: number;
  sample_size: number;
  workload_consistency: number;
  telemetry_stability: number;
  contradiction_count: number;
  uncertainty_score: number;
  assumptions: string[];
  conflicting_evidence: string[];
};

export type PredictionKind = "fps" | "bottleneck" | "thermal" | "power" | "stability" | "upgrade_limit";

export type PredictionRecord = {
  id: string;
  product_id: string;
  reasoning_report_id?: string | null;
  kind: PredictionKind;
  workload?: string | null;
  resolution?: string | null;
  predicted_value?: number | null;
  predicted_unit?: string | null;
  predicted_limiter?: TelemetrySummary["primary_limiter"] | null;
  horizon: string;
  confidence: ConfidenceVector;
  evidence: EvidenceQuality[];
  evidence_sources: string[];
  created_at: string;
  expires_at?: string | null;
};

export type PredictionValidation = {
  id: string;
  prediction_id: string;
  outcome_id: string;
  product_id: string;
  kind: PredictionKind;
  status: "validated" | "partially_validated" | "contradicted" | "insufficient_evidence";
  absolute_error?: number | null;
  relative_error?: number | null;
  confidence_error?: number | null;
  calibrated_confidence: number;
  correctness_score: number;
  severity: TelemetrySeverity;
  explanation: string;
  created_at: string;
};

export type ConfidenceState = {
  id: string;
  scope: "global" | "product" | "workload" | "hardware_family" | "inference_path";
  key: string;
  reliability_score: number;
  calibration_error: number;
  validation_count: number;
  contradiction_rate: number;
  last_updated: string;
  downgrade_reasons: string[];
};

export type ContradictionSignal = {
  id: string;
  product_id: string;
  kind: "fps_spread" | "thermal_conflict" | "power_efficiency" | "driver_instability" | "source_disagreement";
  severity: TelemetrySeverity;
  confidence_score: number;
  explanation: string;
  evidence_sources: string[];
  affected_workloads: string[];
  detected_at: string;
};

export type MetaReasoningReport = {
  id: string;
  product_id: string;
  generated_at: string;
  uncertainty_score: number;
  evidence_strength: number;
  weak_evidence: string[];
  assumptions: string[];
  telemetry_gaps: string[];
  contradiction_density: number;
  self_corrections: string[];
};

export type HardwareCognitionReport = {
  product_id: string;
  generated_at: string;
  confidence: ConfidenceVector;
  reliability: ConfidenceState;
  meta_reasoning: MetaReasoningReport;
  active_predictions: PredictionRecord[];
  recent_validations: PredictionValidation[];
  contradictions: ContradictionSignal[];
  bottleneck_memory: TelemetrySummary["bottleneck"];
  learning_summary: string[];
  audit_events: string[];
};

export type GovernanceStatus = "healthy" | "watch" | "degraded" | "unstable" | "quarantined";

export type ReasoningHealthMetrics = {
  reasoning_quality: number;
  confidence_drift: number;
  confidence_oscillation: number;
  calibration_risk: number;
  contradiction_density: number;
  telemetry_freshness: number;
  evidence_decay_pressure: number;
  graph_integrity: number;
  recursive_feedback_risk: number;
  anomaly_density: number;
  coverage_gap_score: number;
  overall_health: number;
};

export type EvidenceDecayRecord = {
  id: string;
  source: string;
  age_days: number;
  original_weight: number;
  decayed_weight: number;
  validation_support: number;
  statistical_stability: number;
  status: "active" | "decayed" | "stale" | "quarantined";
  reason: string;
};

export type GraphHygieneSignal = {
  id: string;
  kind:
    | "polluted_node"
    | "corrupted_inference_chain"
    | "unstable_telemetry_cluster"
    | "low_trust_reasoning_path"
    | "circular_evidence"
    | "stale_telemetry_dominance";
  severity: "info" | "warning" | "critical";
  confidence_score: number;
  affected_nodes: string[];
  explanation: string;
  mitigation: string[];
  detected_at: string;
};

export type ConsensusStrategyScore = {
  strategy: "telemetry_weighted" | "validation_calibrated" | "decay_adjusted" | "contradiction_adverse";
  confidence_score: number;
  evidence_weight: number;
  disagreement_score: number;
  rationale: string;
};

export type StabilityControl = {
  original_confidence: number;
  governed_confidence: number;
  confidence_ceiling: number;
  dampening_factor: number;
  decay_rate: number;
  quarantine_threshold: number;
  revalidation_required: boolean;
  downgrade_reasons: string[];
};

export type StabilizationAction = {
  id: string;
  kind:
    | "confidence_damping"
    | "evidence_decay"
    | "evidence_quarantine"
    | "revalidation_job"
    | "recommendation_downgrade"
    | "graph_hygiene_review";
  severity: "info" | "warning" | "critical";
  status: "recommended" | "queued" | "applied";
  target: string;
  reason: string;
  created_at: string;
};

export type ReasoningGovernanceReport = {
  id: string;
  product_id: string;
  generated_at: string;
  status: GovernanceStatus;
  metrics: ReasoningHealthMetrics;
  stability: StabilityControl;
  evidence_decay: EvidenceDecayRecord[];
  graph_hygiene: GraphHygieneSignal[];
  consensus: ConsensusStrategyScore[];
  stabilization_actions: StabilizationAction[];
  audit_trail: {
    evidence_sources: string[];
    reasoning_paths: string[];
    confidence_evolution: string[];
    anomaly_history: string[];
    contradiction_history: string[];
  };
  governance_summary: string[];
};

export type CognitivePolicy = {
  id: string;
  version: string;
  status: "active" | "candidate" | "superseded" | "rolled_back" | "archived";
  scope: string;
  confidence_ceiling_max: number;
  evidence_freshness_min: number;
  contradiction_tolerance: number;
  anomaly_escalation_threshold: number;
  adaptation_rate_limit: number;
  recommendation_aggressiveness: number;
  self_generated_trust_cap: number;
  telemetry_trust_growth_rate: number;
  policy_drift_limit: number;
  requires_human_approval: boolean;
  created_by: string;
  change_reason: string;
  supersedes_policy_id?: string | null;
  created_at: string;
};

export type CognitiveHealthIndex = {
  reasoning_stability: number;
  graph_health: number;
  evidence_freshness: number;
  contradiction_resilience: number;
  anomaly_pressure: number;
  adaptation_volatility: number;
  policy_alignment: number;
  index: number;
};

export type EvolutionMetrics = {
  evolution_velocity: number;
  graph_mutation_velocity: number;
  anomaly_growth: number;
  contradiction_propagation: number;
  policy_drift: number;
  adaptation_pressure: number;
  confidence_volatility: number;
  intervention_rate: number;
};

export type PolicyEnforcementDecision = {
  id: string;
  rule:
    | "confidence_ceiling"
    | "evidence_freshness"
    | "contradiction_tolerance"
    | "anomaly_escalation"
    | "adaptation_rate"
    | "self_generated_trust"
    | "policy_drift";
  status: "allow" | "throttle" | "block" | "escalate";
  severity: "info" | "warning" | "critical";
  observed_value: number;
  threshold: number;
  action: string;
};

export type SandboxEvaluation = {
  id: string;
  model_id: string;
  policy_id: string;
  isolated: boolean;
  stability_score: number;
  prediction_accuracy_score: number;
  contradiction_impact: number;
  telemetry_consistency: number;
  promotion_ready: boolean;
  rationale: string;
};

export type ModelPromotionDecision = {
  id: string;
  model_id: string;
  status: "promote" | "hold" | "reject" | "quarantine";
  stability_delta: number;
  contradiction_delta: number;
  prediction_accuracy: number;
  reason: string;
  requires_approval: boolean;
};

export type RollbackEvent = {
  id: string;
  status: "not_required" | "recommended" | "requires_approval" | "applied";
  from_policy_id: string;
  to_policy_id?: string | null;
  trigger: string;
  reason: string;
  created_at: string;
};

export type LongTermMemoryDecision = {
  id: string;
  target: string;
  status: "strengthen" | "decay" | "archive" | "retain";
  support_score: number;
  reason: string;
};

export type EvolutionOrchestrationReport = {
  id: string;
  product_id: string;
  generated_at: string;
  status: GovernanceStatus;
  active_policy: CognitivePolicy;
  health_index: CognitiveHealthIndex;
  metrics: EvolutionMetrics;
  enforcement: PolicyEnforcementDecision[];
  sandbox_evaluations: SandboxEvaluation[];
  promotion_decisions: ModelPromotionDecision[];
  rollback_events: RollbackEvent[];
  memory_decisions: LongTermMemoryDecision[];
  audit_trail: {
    id: string;
    event_type:
      | "policy_evaluated"
      | "adaptation_throttled"
      | "sandbox_evaluated"
      | "promotion_reviewed"
      | "rollback_recommended"
      | "memory_governed";
    severity: "info" | "warning" | "critical";
    message: string;
    timestamp: string;
  }[];
  orchestration_summary: string[];
};

export type ObjectiveName =
  | "correctness"
  | "safety_stability"
  | "evidence_quality"
  | "transparency"
  | "optimization_quality"
  | "performance_maximization";

export type ObjectivePriority = {
  name: ObjectiveName;
  rank: number;
  weight: number;
  description: string;
  protected: boolean;
};

export type SystemIdentity = {
  id: string;
  version: string;
  purpose: string;
  core_reasoning_principles: string[];
  optimization_priorities: ObjectivePriority[];
  trust_boundaries: string[];
  recommendation_ethics: string[];
  uncertainty_handling: string[];
  optimizes_for: string[];
  avoids: string[];
  acceptable_tradeoffs: string[];
  constitution: {
    id: string;
    version: string;
    immutable: boolean;
    non_overridable_constraints: string[];
    protected_governance_rules: string[];
    safety_principles: string[];
    created_at: string;
  };
  created_at: string;
};

export type AlignmentViolation = {
  id: string;
  kind:
    | "objective_drift"
    | "safety_ignored"
    | "uncertainty_hidden"
    | "benchmark_overfit"
    | "confidence_without_evidence"
    | "popularity_over_correctness"
    | "policy_incoherence"
    | "governance_fragmentation";
  severity: "info" | "warning" | "critical";
  confidence_score: number;
  explanation: string;
  affected_objectives: ObjectiveName[];
  mitigation: string[];
  detected_at: string;
};

export type AlignmentHealthIndex = {
  identity_stability: number;
  objective_coherence: number;
  optimization_consistency: number;
  governance_alignment: number;
  confidence_integrity: number;
  transparency_score: number;
  safety_priority_score: number;
  overall_alignment: number;
};

export type AlignmentInspectionReport = {
  id: string;
  product_id: string;
  generated_at: string;
  status: "aligned" | "watch" | "misaligned" | "violated";
  identity: SystemIdentity;
  health: AlignmentHealthIndex;
  tradeoffs: {
    id: string;
    primary_objective: ObjectiveName;
    competing_objective: ObjectiveName;
    resolution: string;
    acceptable: boolean;
    confidence_score: number;
  }[];
  violations: AlignmentViolation[];
  ethics: {
    misleading_confidence_risk: number;
    unsafe_recommendation_risk: number;
    unstable_configuration_risk: number;
    biased_optimization_risk: number;
    ethics_passed: boolean;
    notes: string[];
  };
  rollback: {
    id: string;
    status: "not_required" | "recommended" | "requires_approval" | "applied";
    trigger: string;
    target_policy_id?: string | null;
    reason: string;
    created_at: string;
  }[];
  audit_trail: {
    id: string;
    event_type:
      | "identity_evaluated"
      | "objective_audited"
      | "ethics_checked"
      | "violation_detected"
      | "rollback_supported"
      | "constitution_enforced";
    severity: "info" | "warning" | "critical";
    message: string;
    timestamp: string;
  }[];
  alignment_summary: string[];
};

export type AgentKind =
  | "telemetry"
  | "benchmark_validation"
  | "anomaly_investigation"
  | "confidence_audit"
  | "governance_stability"
  | "evolution_monitoring"
  | "alignment_integrity"
  | "recommendation_verification";

export type CognitionEventKind =
  | "scheduled_tick"
  | "new_telemetry"
  | "driver_regression"
  | "benchmark_contradiction"
  | "anomaly_spike"
  | "policy_drift"
  | "stale_evidence"
  | "confidence_inflation"
  | "alignment_drift"
  | "recommendation_risk"
  | "graph_pollution";

export type AgentDefinition = {
  id: string;
  kind: AgentKind;
  name: string;
  status: "active" | "idle" | "investigating" | "degraded" | "paused";
  priority_weight: number;
  cadence_seconds: number;
  governed_by: string[];
  responsibilities: string[];
  allowed_actions: string[];
  forbidden_actions: string[];
  last_heartbeat: string;
};

export type CognitionEvent = {
  id: string;
  kind: CognitionEventKind;
  severity: "info" | "warning" | "critical";
  product_id?: string | null;
  source: string;
  message: string;
  payload: Record<string, unknown>;
  priority_score: number;
  handled: boolean;
  created_at: string;
};

export type AgentTask = {
  id: string;
  agent_kind: AgentKind;
  kind:
    | "monitor_telemetry"
    | "refresh_telemetry"
    | "validate_benchmark"
    | "investigate_anomaly"
    | "audit_confidence"
    | "stabilize_governance"
    | "monitor_evolution"
    | "enforce_alignment"
    | "verify_recommendation"
    | "request_revalidation";
  status: "queued" | "running" | "completed" | "blocked" | "failed" | "requires_approval";
  priority_score: number;
  product_id?: string | null;
  triggered_by_event_id?: string | null;
  reason: string;
  expected_actions: string[];
  requires_human_approval: boolean;
  created_at: string;
  completed_at?: string | null;
};

export type AgentSignal = {
  id: string;
  from_agent: AgentKind;
  to_agent: AgentKind;
  channel: "event_queue" | "governance_signal" | "graph_event" | "reasoning_notification";
  event_id?: string | null;
  message: string;
  priority_score: number;
  acknowledged: boolean;
  created_at: string;
};

export type InvestigationRecord = {
  id: string;
  product_id?: string | null;
  agent_kind: AgentKind;
  status: "open" | "correlating" | "resolved" | "escalated";
  hypothesis: string;
  evidence_sources: string[];
  correlated_signals: string[];
  findings: string[];
  recommended_resolution: string[];
  confidence_score: number;
  created_at: string;
};

export type AutonomousIntervention = {
  id: string;
  kind:
    | "confidence_reduction"
    | "telemetry_refresh"
    | "evidence_quarantine"
    | "revalidation_request"
    | "recommendation_downgrade"
    | "policy_escalation"
    | "evolution_rollback"
    | "constitution_guardrail";
  status: "recommended" | "queued" | "applied" | "blocked" | "requires_approval";
  agent_kind: AgentKind;
  target: string;
  severity: "info" | "warning" | "critical";
  reason: string;
  alignment_checked: boolean;
  confidence_delta: number;
  requires_human_approval: boolean;
  created_at: string;
};

export type HumanOversightAction = {
  id: string;
  action_type:
    | "inspect_agent_action"
    | "override_autonomous_decision"
    | "approve_policy_escalation"
    | "review_investigation"
    | "approve_rollback";
  status: "available" | "required" | "completed";
  target: string;
  reason: string;
  created_at: string;
};

export type AutonomousHealthIndex = {
  agent_availability: number;
  queue_pressure: number;
  safety_stability_score: number;
  contradiction_resolution_score: number;
  telemetry_freshness_score: number;
  governance_compliance_score: number;
  intervention_effectiveness: number;
  overall_autonomy_health: number;
};

export type AutonomousCognitionReport = {
  id: string;
  product_id?: string | null;
  generated_at: string;
  status: "active" | "watch" | "degraded" | "blocked";
  agents: AgentDefinition[];
  events: CognitionEvent[];
  tasks: AgentTask[];
  signals: AgentSignal[];
  investigations: InvestigationRecord[];
  interventions: AutonomousIntervention[];
  oversight: HumanOversightAction[];
  health: AutonomousHealthIndex;
  autonomy_summary: string[];
};

export type OpsRole = "anonymous" | "viewer" | "analyst" | "admin" | "super_admin";
export type AutonomyLevel = "level_0" | "level_1" | "level_2" | "level_3";

export type AuditEvent = {
  id: string;
  actor: string;
  role: OpsRole;
  action: string;
  endpoint: string;
  method: string;
  target?: string | null;
  request_payload_hash?: string | null;
  idempotency_key?: string | null;
  timestamp: string;
  result: string;
  status_code?: number | null;
  trace_id: string;
  approval_required: boolean;
  approval_status?: string | null;
  risk_level: AutonomyLevel;
  metadata: Record<string, unknown>;
};

export type ApprovalItem = {
  id: string;
  action_type: string;
  affected_entities: string[];
  risk_level: AutonomyLevel;
  reasoning: string;
  evidence: Record<string, unknown>;
  rollback_plan: string;
  recommended_decision: "approve" | "reject" | "defer" | "review";
  status: "pending" | "approved" | "rejected" | "expired" | "executed" | "deferred" | "reviewed";
  created_at: string;
  expires_at?: string | null;
  decided_at?: string | null;
  decided_by?: string | null;
  decision_note?: string | null;
  trace_id: string;
};

export type SourceHealth = {
  source: string;
  configured: boolean;
  status: "healthy" | "degraded" | "paused" | "not_configured" | "quota_limited" | "unknown";
  last_successful_request?: string | null;
  last_failure?: string | null;
  quota_status: "ok" | "near_limit" | "limited" | "unknown" | "not_configured";
  reliability_score: number;
  freshness_score: number;
  message: string;
};

export type WorkerHealth = {
  name: string;
  enabled: boolean;
  running: boolean;
  queue_depth: number;
  last_heartbeat?: string | null;
  repeated_failures: number;
  status: "healthy" | "idle" | "degraded" | "stopped";
  message: string;
};

export type JobMonitorItem = {
  job_id: string;
  job_type: string;
  status: "queued" | "running" | "succeeded" | "failed" | "retrying" | "cancelled" | "requires_approval";
  attempts: number;
  started_at?: string | null;
  finished_at?: string | null;
  trace_id: string;
  risk_level: AutonomyLevel;
  approval_required: boolean;
  error?: string | null;
};

export type GraphHealth = {
  status: "healthy" | "watch" | "degraded" | "unavailable";
  neo4j_connected: boolean;
  product_count: number;
  stale_product_count: number;
  pending_approval_count: number;
  recent_audit_count: number;
  message: string;
};

export type FounderAlert = {
  id: string;
  severity: "info" | "warning" | "critical";
  reason: string;
  evidence: Record<string, unknown>;
  suggested_action: string;
  approval_id?: string | null;
};

export type DailyFounderReport = {
  id: string;
  generated_at: string;
  system_health: "healthy" | "watch" | "degraded" | "critical";
  neo4j_health: GraphHealth;
  workers: WorkerHealth[];
  failed_jobs: JobMonitorItem[];
  successful_refreshes: number;
  new_products_discovered: number;
  stale_sources: SourceHealth[];
  source_health: SourceHealth[];
  pricing_anomalies: string[];
  telemetry_gaps: string[];
  cognition_risks: string[];
  approval_items_waiting: ApprovalItem[];
  alerts: FounderAlert[];
  recommended_next_actions: string[];
  recent_audit_events: AuditEvent[];
};

export type HardwareIntelligence = {
  product_id: string;
  product_name: string;
  category: string;
  generated_at: string;
  confidence: "high" | "medium" | "low";
  benchmark: BenchmarkScores;
  workloads: WorkloadSuitability[];
  power_thermal: {
    tdp_w?: number;
    peak_power_w?: number;
    thermal_efficiency: number;
    expected_cooling_requirement: string;
    recommended_psu_w?: number;
    power_spike_risk: "low" | "medium" | "high";
    warnings: string[];
  };
  longevity: {
    upgrade_longevity: number;
    future_proof_score: number;
    platform_lifespan_years: number;
    limiting_factors: string[];
  };
  compatibility: {
    bios_requirements: string[];
    chipset_limitations: string[];
    pcie_generation_support?: string;
    memory_overclock_stability: "unknown" | "low" | "medium" | "high";
    cooling_recommendations: string[];
  };
  market: {
    price_performance_ratio?: number;
    market_popularity: number;
    value_score: number;
    price_trend: "falling" | "stable" | "rising" | "insufficient_history";
    best_value_badge: boolean;
  };
  telemetry?: TelemetrySummary | null;
  recommendation_summary: string[];
  warnings: {
    severity: "info" | "warning" | "critical";
    message: string;
    evidence: Record<string, unknown>;
  }[];
  evidence: Record<string, unknown>;
};

export const selectionKeyByKind: Record<ComponentKind, keyof SelectedComponents> = {
  CPU: "cpu_id",
  GPU: "gpu_id",
  Motherboard: "motherboard_id",
  RAM: "ram_id",
  Case: "case_id",
  Cooler: "cooler_id",
  Storage: "storage_id",
  PSU: "psu_id"
};

export const componentOrder: ComponentKind[] = [
  "CPU",
  "Motherboard",
  "RAM",
  "GPU",
  "Storage",
  "Cooler",
  "Case",
  "PSU"
];

export const productCategories: ProductCategory[] = [
  "CPU",
  "GPU",
  "Motherboard",
  "RAM",
  "PSU",
  "Case",
  "Cooler",
  "Storage",
  "Monitor",
  "Keyboard",
  "Mouse",
  "Headset",
  "Capture Card",
  "Fans",
  "Custom Cooling",
  "Accessories"
];
