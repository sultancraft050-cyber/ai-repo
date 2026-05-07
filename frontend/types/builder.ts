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

export type SaudiBuildUseCase =
  | "gaming"
  | "simulation"
  | "workstation"
  | "content_creation"
  | "ai_ml"
  | "streaming"
  | "general";
export type SaudiBuildResolution = "1080p" | "1440p" | "4k" | "ultrawide";
export type SaudiBuildPriority =
  | "best_value"
  | "maximum_performance"
  | "quiet_build"
  | "upgrade_path"
  | "local_availability"
  | "lowest_risk";
export type SaudiBuildRequest = {
  region: "SA";
  city: string;
  budget_sar: number;
  use_case: SaudiBuildUseCase;
  target_resolution: SaudiBuildResolution;
  refresh_rate_target: 60 | 120 | 144 | 165 | 240;
  brand_preferences: ("AMD" | "Intel" | "NVIDIA" | "no_preference")[];
  case_size: "ATX" | "mATX" | "ITX" | "no_preference";
  priority: SaudiBuildPriority;
  strict_budget: boolean;
  include_monitor: boolean;
  include_peripherals: boolean;
};
export type RecommendedDiscoveryJob = {
  category: string;
  query: string;
  region: "SA";
  city: string;
  limit: number;
  dry_run: boolean;
  reason: string;
};
export type CategoryCoverage = {
  category: string;
  priced_product_count: number;
  trusted_local_listing_count: number;
  risky_listing_count: number;
  usable_with_warnings_count: number;
  unknown_vat_count: number;
  unknown_shipping_count: number;
  unknown_warranty_count: number;
  suspicious_price_count: number;
  recommended_option_count: number;
  stale_listing_count: number;
  ready: boolean;
  readiness_level: "ready" | "usable_with_warnings" | "not_ready";
  notes: string[];
};
export type SaudiBuildDataCompleteness = {
  region: "SA";
  city: string;
  readiness_score: number;
  required_categories: string[];
  ready_categories: string[];
  missing_categories: string[];
  category_coverage: CategoryCoverage[];
  recommended_discovery_jobs: RecommendedDiscoveryJob[];
  enough_data_for_full_build: boolean;
  message: string;
};
export type SaudiBuildComponent = {
  product_id: string;
  name: string;
  category: string;
  brand?: string | null;
  recommended_vendor?: string | null;
  recommended_price_sar?: number | null;
  lowest_market_price_sar?: number | null;
  price_confidence?: number | null;
  seller_type?: string | null;
  vendor_region_type?: string | null;
  stock_badge: "local" | "gcc" | "imported" | "unknown";
  vat_status: string;
  shipping_status: string;
  warranty_status: string;
  reason_selected: string;
  alternatives: string[];
  warnings: string[];
};
export type SaudiBuildSummary = {
  total_recommended_price_sar?: number | null;
  total_lowest_possible_price_sar?: number | null;
  budget_remaining_or_overage?: number | null;
  budget_sar?: number | null;
  budget_delta_sar?: number | null;
  over_budget_amount_sar: number;
  over_budget_percent: number;
  budget_status: "under_budget" | "slightly_over_budget" | "over_budget" | "no_valid_build_under_budget";
  most_expensive_components: string[];
  easiest_savings_opportunities: string[];
  compatibility_status: "valid" | "invalid" | "incomplete" | "not_validated";
  performance_estimate: string;
  bottleneck_summary: string;
  risk_summary: string[];
  data_completeness_score: number;
  warning_summary: string[];
  components_with_uncertainty: string[];
  confidence_level: "high" | "medium" | "low";
  confidence_score: number;
  missing_data_warnings: string[];
};
export type SaudiBuildOption = {
  label: "recommended_saudi_build" | "budget_fit_build" | "best_value_build" | "lowest_risk_local_build";
  title: string;
  components: SaudiBuildComponent[];
  summary: SaudiBuildSummary;
  why_this_build: string;
  upgrade_notes: string[];
};
export type SaudiBuildResponse = {
  region: "SA";
  city: string;
  build_status: "ready" | "incomplete_data" | "no_valid_build" | "incomplete_budget_fit";
  builds: SaudiBuildOption[];
  data_completeness: SaudiBuildDataCompleteness;
  recommended_discovery_jobs: RecommendedDiscoveryJob[];
  missing_data_warnings: string[];
  audit_trace_id?: string | null;
};
export type SaudiBuildValidationRequest = {
  region: "SA";
  city: string;
  component_ids: Record<string, string>;
  budget_sar?: number | null;
};
export type SaudiBuildValidationResponse = {
  valid: boolean;
  compatibility_status: "valid" | "invalid" | "incomplete" | "not_validated";
  market_confidence: number;
  total_recommended_price_sar?: number | null;
  warnings: string[];
  missing_categories: string[];
};
export type DuplicateConfidence = "high" | "medium" | "low";
export type CpuDuplicateCandidate = {
  canonical_cpu_key: string;
  region: string;
  suspected_duplicate_product_ids: string[];
  product_names: string[];
  vendors: string[];
  prices: Record<string, unknown>[];
  confidence: DuplicateConfidence;
  reason: string;
  recommended_action: string;
  approval_required: boolean;
  approval_id?: string | null;
};
export type CpuDuplicateReport = {
  region: string;
  candidates: CpuDuplicateCandidate[];
  approval_items_created: number;
  trace_id?: string | null;
};
export type CanonicalMergePreviewRequest = {
  product_ids: string[];
  region: string;
};
export type CanonicalMergePreviewResponse = {
  proposed_canonical_product: Record<string, unknown>;
  relationships_to_preserve: Record<string, number>;
  price_snapshots_to_preserve: number;
  vendors_to_preserve: number;
  field_evidence_to_preserve: number;
  audit_events_to_preserve: number;
  risks: string[];
  rollback_plan: string;
  would_execute: boolean;
  approval_required: boolean;
  approval_id?: string | null;
};

export type SourceType =
  | "manufacturer"
  | "retailer_api"
  | "aggregator_api"
  | "verified_scraping"
  | "inferred";

export type ListingCondition = "new" | "used" | "refurbished" | "open_box" | "unknown";
export type SellerType = "retailer" | "manufacturer" | "marketplace" | "third_party" | "unknown";
export type PriceStatus = "active" | "stale" | "unavailable";
export type DataOrigin = "live" | "seed" | "demo" | "unknown";
export type BuyRecommendationLevel =
  | "recommended"
  | "good_if_price_matters"
  | "acceptable_with_risk"
  | "not_recommended"
  | "insufficient_data";
export type TrustTier = "high" | "medium" | "low" | "unknown";
export type VatStatus = "vat_included" | "vat_excluded" | "vat_unknown";
export type ShippingStatus = "free_shipping" | "paid_shipping" | "unknown_shipping" | "pickup_only";
export type WarrantyStatus =
  | "local_warranty"
  | "seller_warranty"
  | "manufacturer_warranty"
  | "unknown_warranty";
export type LocalStockStatus = "local_stock" | "gcc_stock" | "imported_stock" | "unknown_stock";
export type VendorRegionType =
  | "local_saudi_vendor"
  | "gcc_vendor"
  | "international_vendor"
  | "marketplace_vendor"
  | "unknown_vendor"
  | "local";

export type ProductSearchResult = {
  id: string;
  canonical_key?: string;
  name: string;
  brand?: string;
  category: ProductCategory | string;
  model?: string;
  image_url?: string;
  data_origin: DataOrigin;
  price_status: PriceStatus;
  flags: string[];
  region: string;
  region_currency?: string;
  region_price_status?: PriceStatus;
  recommended_reason?: string;
  recommended_level?: BuyRecommendationLevel | null;
  price_confidence?: number;
  lowest_price_warning?: string | null;
  current_best_price?: number;
  current_best_currency?: string;
  current_best_vendor?: string;
  current_recommended_price?: number;
  current_recommended_currency?: string;
  current_recommended_vendor?: string;
  current_recommended_condition?: ListingCondition;
  current_recommended_seller_type?: SellerType;
  current_recommended_marketplace_risk_score?: number;
  lowest_market_price?: number;
  lowest_market_currency?: string;
  lowest_market_vendor?: string;
  lowest_market_condition?: ListingCondition;
  lowest_market_seller_type?: SellerType;
  lowest_marketplace_risk_score?: number;
  best_new_price?: number;
  best_new_currency?: string;
  best_new_vendor?: string;
  best_trusted_price?: number;
  best_trusted_currency?: string;
  best_trusted_vendor?: string;
  best_local_price?: number;
  best_local_currency?: string;
  best_local_vendor?: string;
  best_used_price?: number;
  best_used_currency?: string;
  best_used_vendor?: string;
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
  region: string;
  country_code?: string | null;
  city?: string | null;
  raw_price?: number | null;
  item_price?: number | null;
  item_price_sar?: number | null;
  shipping_cost_sar?: number | null;
  final_landed_price?: number | null;
  final_landed_currency?: string | null;
  final_landed_price_sar?: number | null;
  vat_included?: boolean | null;
  vat_status: VatStatus;
  shipping_status: ShippingStatus;
  warranty_status: WarrantyStatus;
  local_stock_status: LocalStockStatus;
  vendor_region_type: VendorRegionType;
  estimated_vat?: number | null;
  import_fee?: number | null;
  estimated_delivery_days?: number | null;
  seller_country?: string | null;
  is_local_stock?: boolean | null;
  is_imported?: boolean | null;
  serves_saudi?: boolean | null;
  warranty_type?: string | null;
  local_warranty?: boolean | null;
  region_rank_score?: number | null;
  recommended_saudi_price_candidate: boolean;
  final_landed_price_confidence?: number | null;
  price_completeness_score?: number | null;
  trust_tier: TrustTier;
  delivery_status: ShippingStatus;
  confidence_score?: number | null;
  buy_recommendation_level: BuyRecommendationLevel;
  buy_recommendation_reason?: string | null;
  recommendation_reason?: string | null;
  warnings: string[];
  local_stock_confidence?: number | null;
  warranty_confidence?: number | null;
  delivery_confidence?: number | null;
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
  accepted: boolean;
  listing_condition: ListingCondition;
  seller_type: SellerType;
  marketplace_risk_score: number;
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
  dry_run?: boolean;
  trace_id?: string | null;
  source_errors?: string[];
  preview?: DiscoveryPreviewItem[];
};

export type DiscoveryPreviewItem = {
  raw_listing_name: string;
  category: string;
  product_type:
    | "standalone_gpu"
    | "standalone_cpu"
    | "standalone_storage"
    | "standalone_ram"
    | "standalone_psu"
    | "standalone_case"
    | "standalone_cooler"
    | "standalone_motherboard"
    | "prebuilt_pc"
    | "laptop"
    | "bundle"
    | "motherboard"
    | "cooler"
    | "accessory"
    | "unknown_low_confidence"
    | "hardware_product";
  product_type_confidence: number;
  normalized_name: string;
  gpu_family_key?: string | null;
  ram_family_key?: string | null;
  psu_family_key?: string | null;
  case_family_key?: string | null;
  cooler_family_key?: string | null;
  motherboard_family_key?: string | null;
  canonical_product_key: string;
  canonical_key: string;
  canonical_product_id?: string | null;
  merge_decision: "new_product" | "merge_existing" | "rejected";
  confidence: number;
  reason: string;
  vendor_name: string;
  price: number;
  currency: string;
  region: string;
  city?: string | null;
  item_price_sar?: number | null;
  shipping_cost_sar?: number | null;
  final_landed_price?: number | null;
  final_landed_currency?: string | null;
  final_landed_price_sar?: number | null;
  is_local_stock?: boolean | null;
  is_imported?: boolean | null;
  serves_saudi?: boolean | null;
  vendor_region_type: VendorRegionType;
  vat_included?: boolean | null;
  vat_status: VatStatus;
  shipping_status: ShippingStatus;
  warranty_status: WarrantyStatus;
  local_stock_status: LocalStockStatus;
  estimated_vat?: number | null;
  warranty_type?: string | null;
  region_rank_score?: number | null;
  recommended_candidate: boolean;
  recommended_saudi_price_candidate: boolean;
  final_landed_price_confidence?: number | null;
  price_completeness_score?: number | null;
  trust_tier: TrustTier;
  local_stock_confidence?: number | null;
  warranty_confidence?: number | null;
  delivery_confidence?: number | null;
  availability: PriceSnapshotView["availability"];
  listing_condition: ListingCondition;
  seller_type: SellerType;
  marketplace_risk_score: number;
  accepted: boolean;
  rejected_reasons: string[];
  flags: string[];
  source: string;
  source_type: SourceType;
  trust_score: number;
  freshness_score: number;
  product_url?: string | null;
  image_url?: string | null;
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
export type AutonomyRiskLevel = AutonomyLevel;
export type OpsSeverity = "info" | "watch" | "warning" | "critical";
export type AutonomyJobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "retrying"
  | "cancelled"
  | "requires_approval"
  | "blocked"
  | "deferred";
export type ApprovalStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "expired"
  | "executed"
  | "deferred"
  | "reviewed";

export type AuditEvent = {
  id: string;
  audit_id?: string;
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
  approval_id?: string;
  action_type: string;
  title?: string | null;
  description?: string | null;
  affected_entities: string[];
  target_entities?: string[];
  affected_count?: number;
  risk_level: AutonomyLevel;
  reasoning: string;
  evidence_summary?: string | null;
  evidence: Record<string, unknown>;
  risk_explanation?: string | null;
  expected_impact?: string | null;
  rollback_plan: string;
  requested_by_agent?: string | null;
  recommended_decision: "approve" | "reject" | "defer" | "review";
  status: ApprovalStatus;
  created_at: string;
  expires_at?: string | null;
  decided_at?: string | null;
  decided_by?: string | null;
  decision_note?: string | null;
  trace_id: string;
};

export type ApprovalRequest = ApprovalItem;

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

export type SourceConfigStatus = {
  source_name: string;
  region: string;
  configured: boolean;
  health: "configured" | "not_configured" | "degraded" | "healthy" | "quota_limited" | "failed";
  last_success?: string | null;
  last_failure?: string | null;
  last_error_sanitized?: string | null;
  quota_status: "ok" | "near_limit" | "limited" | "unknown" | "not_configured";
  source_kind: string;
  discovery_enabled: boolean;
  direct_access_enabled: boolean;
  preferred_discovery_path?: string | null;
  source_policy?: string | null;
};

export type KnownUrlRefreshSupport = "true" | "false" | "policy_gated";
export type SourcePolicyStatus = "allowed" | "policy_gated" | "blocked" | "unsupported";

export type SourceMatrixEntry = {
  source_name: string;
  region: string;
  manual_url_supported: boolean;
  known_url_refresh_supported: KnownUrlRefreshSupport;
  broad_scraping_allowed: boolean;
  access_method: string;
  enabled: boolean;
  policy_status: SourcePolicyStatus;
  health: "healthy" | "configured" | "not_configured" | "degraded" | "failed" | "policy_gated";
  last_success?: string | null;
  last_failure?: string | null;
  source_policy: string;
};

export type ProductUrlPreviewRequest = {
  url: string;
  region: string;
  category: ProductCategory | string;
  dry_run?: boolean;
};

export type ProductUrlPreviewResponse = {
  raw_title?: string | null;
  normalized_name?: string | null;
  price?: number | null;
  currency?: string | null;
  image_url?: string | null;
  availability: "in_stock" | "out_of_stock" | "preorder" | "backorder" | "unknown";
  vendor_name?: string | null;
  product_url: string;
  normalized_url: string;
  category: string;
  product_type: string;
  product_type_confidence: number;
  canonical_key?: string | null;
  region: string;
  source_name?: string | null;
  source_policy_status: SourcePolicyStatus;
  listing_condition: "new" | "used" | "refurbished" | "open_box" | "unknown";
  seller_type: "retailer" | "manufacturer" | "marketplace" | "third_party" | "unknown";
  vendor_region_type: string;
  marketplace_risk_score: number;
  vat_status: "vat_included" | "vat_excluded" | "vat_unknown";
  shipping_status: "free_shipping" | "paid_shipping" | "unknown_shipping" | "pickup_only";
  warranty_status: "local_warranty" | "seller_warranty" | "manufacturer_warranty" | "unknown_warranty";
  item_price_sar?: number | null;
  final_landed_price_sar?: number | null;
  price_confidence?: number | null;
  recommendation_level: PriceSnapshotView["buy_recommendation_level"];
  accepted: boolean;
  rejected_reasons: string[];
  flags: string[];
  extracted_at: string;
};

export type ProductUrlIngestResponse = {
  status: "ingested" | "rejected";
  product_id?: string | null;
  vendor_id?: string | null;
  price_snapshot_id?: string | null;
  product_url: string;
  normalized_url: string;
  audit_event_id?: string | null;
  preview: ProductUrlPreviewResponse;
  trace_id: string;
};

export type KnownProductUrlView = {
  url: string;
  normalized_url: string;
  source_name: string;
  vendor_name: string;
  region: string;
  category: string;
  approved: boolean;
  refresh_allowed: boolean;
  last_checked_at?: string | null;
  last_success_at?: string | null;
  last_failure_at?: string | null;
  last_error_sanitized?: string | null;
  source_policy_status: SourcePolicyStatus;
  last_price?: number | null;
  last_currency?: string | null;
};

export type ProductUrlRefreshResponse = {
  status: "completed";
  region: string;
  refreshed_count: number;
  failed_count: number;
  skipped_count: number;
  items: {
    normalized_url: string;
    vendor_name: string;
    category: string;
    status: "refreshed" | "skipped" | "failed";
    price_snapshot_id?: string | null;
    error?: string | null;
  }[];
  trace_id: string;
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
  status: AutonomyJobStatus;
  attempts: number;
  started_at?: string | null;
  finished_at?: string | null;
  trace_id: string;
  risk_level: AutonomyLevel;
  approval_required: boolean;
  error?: string | null;
};

export type AutonomyJob = {
  job_id: string;
  job_type: string;
  title: string;
  description: string;
  status: AutonomyJobStatus;
  risk_level: AutonomyLevel;
  approval_required: boolean;
  agent_name?: string | null;
  target_entity_id?: string | null;
  target_entity_type?: string | null;
  attempts: number;
  max_attempts: number;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  trace_id: string;
  last_error?: string | null;
  next_retry_at?: string | null;
  summary: string;
  cancellable: boolean;
};

export type AutonomyQueue = {
  generated_at: string;
  running_now: AutonomyJob[];
  waiting_approval: AutonomyJob[];
  failed_needs_attention: AutonomyJob[];
  recently_completed: AutonomyJob[];
  scheduled_next: AutonomyJob[];
  all_jobs: AutonomyJob[];
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
  severity: OpsSeverity;
  reason: string;
  evidence: Record<string, unknown>;
  suggested_action: string;
  approval_id?: string | null;
};

export type RecommendedAction = {
  id: string;
  reason: string;
  severity: OpsSeverity;
  suggested_action: string;
  approval_required: boolean;
  approval_id?: string | null;
};

export type SystemHealthSummary = {
  backend_status: "healthy" | "watch" | "degraded" | "critical";
  neo4j_status: "healthy" | "watch" | "degraded" | "unavailable";
  worker_status: "healthy" | "watch" | "degraded" | "stopped";
  frontend_configured: boolean;
  external_source_status: "healthy" | "watch" | "degraded" | "not_configured";
  severity: OpsSeverity;
};

export type AutonomySummary = {
  completed_jobs: number;
  failed_jobs: number;
  retries: number;
  pending_approvals: number;
  interventions_proposed: number;
  high_risk_alerts: number;
};

export type DataOpsSummary = {
  new_products_discovered: number;
  price_snapshots_updated: number;
  stale_prices_detected: number;
  telemetry_snapshots_ingested: number;
  telemetry_gaps_detected: number;
  enrichment_jobs_completed: number;
  saudi_listings_ingested: number;
  saudi_listings_with_recommended_option: number;
  saudi_risky_only_products: number;
  saudi_local_listing_count: number;
  saudi_imported_listing_count: number;
  saudi_suspicious_price_count: number;
  saudi_products_needing_review: number;
  saudi_unknown_vat_vendors: string[];
  saudi_unknown_shipping_vendors: string[];
  saudi_build_readiness_score: number;
  saudi_build_ready_categories: string[];
  saudi_build_missing_categories: string[];
  saudi_build_request_count: number;
  failed_build_generations: number;
  common_missing_build_components: string[];
  recommended_build_discovery_jobs: Record<string, unknown>[];
};

export type CognitionOpsSummary = {
  low_confidence_products: number;
  governance_risks: number;
  alignment_warnings: number;
  evolution_drift_warnings: number;
  anomaly_spikes: number;
  contradiction_increases: number;
};

export type SourceHealthSummary = {
  configured_sources: number;
  missing_api_keys: string[];
  degraded_sources: string[];
  quota_warnings: string[];
  last_successful_sync_by_source: Record<string, string | null>;
};

export type DailyFounderReport = {
  id: string;
  generated_at: string;
  region: string;
  region_currency?: string | null;
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
  recommended_next_actions: RecommendedAction[];
  recent_audit_events: AuditEvent[];
  system_summary: SystemHealthSummary;
  autonomy_summary: AutonomySummary;
  data_summary: DataOpsSummary;
  cognition_summary: CognitionOpsSummary;
  source_summary: SourceHealthSummary;
  handled_automatically: string[];
  needs_attention: FounderAlert[];
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
