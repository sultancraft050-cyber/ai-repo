from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.domain import BuildPreferences, ComponentOption, SelectedComponents


class CompatibilityRequest(BaseModel):
    selection: SelectedComponents
    preferences: BuildPreferences = Field(default_factory=BuildPreferences)
    qvl_required: bool = True


class ConstraintCheck(BaseModel):
    id: str
    label: str
    status: Literal["pass", "fail", "warning", "unknown"]
    severity: Literal["info", "warning", "critical"]
    details: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class CompatibilityResponse(BaseModel):
    valid: bool
    state: Literal["partial", "valid_configuration", "invalid_configuration"]
    checks: list[ConstraintCheck]
    total_power_draw_w: float | None = None
    required_psu_w: float | None = None
    selected_component_count: int
    missing_component_ids: list[str] = Field(default_factory=list)


class PerformanceRequest(BaseModel):
    selection: SelectedComponents
    preferences: BuildPreferences = Field(default_factory=BuildPreferences)
    display_refresh_hz: int = Field(default=144, ge=30, le=1000)


class BottleneckBreakdown(BaseModel):
    cpu_percent: float
    gpu_percent: float
    memory_percent: float
    display_percent: float


class PerformanceResponse(BaseModel):
    expected_fps: float
    one_percent_low_fps: float
    frame_time_ms: float
    frame_time_variance_ms: float
    bottleneck: BottleneckBreakdown
    confidence: Literal["high", "medium", "low"]
    model_inputs: dict[str, Any]
    reasoning: list[str]


class ComponentOptionsResponse(BaseModel):
    options: list[ComponentOption]
    degraded: bool = False
    message: str | None = None


class BuildGenerateRequest(BaseModel):
    budget_usd: float = Field(ge=0)
    purpose: str = "gaming"
    resolution: str = "1440p"
    preferences: BuildPreferences = Field(default_factory=BuildPreferences)
    max_candidates_per_type: int = Field(default=80, ge=1, le=300)


class GeneratedPart(BaseModel):
    kind: str
    id: str
    name: str
    brand: str | None = None
    price_usd: float
    price_source: str | None = None
    price_vendor: str | None = None
    price_freshness_score: float | None = None
    price_trust_score: float | None = None
    price_stale: bool = False
    reasoning: str


class GeneratedBuild(BaseModel):
    label: Literal["best_performance", "best_value", "balanced", "closest_valid"]
    parts: list[GeneratedPart]
    selection: SelectedComponents
    total_cost_usd: float
    score: float
    performance: PerformanceResponse
    compatibility: CompatibilityResponse
    bottleneck_breakdown: BottleneckBreakdown
    reasoning_summary: list[str]
    longevity_notes: list[str] = Field(default_factory=list)


class BuildSolverMetrics(BaseModel):
    explored_nodes_count: int = 0
    pruned_nodes_count: int = 0
    valid_build_count: int = 0
    average_build_time_ms: float = 0
    max_depth_reached: int = 0
    graph_fetch_time_ms: float = 0
    normalization_time_ms: float = 0
    compatibility_time_ms: float = 0
    scoring_time_ms: float = 0
    serialization_time_ms: float = 0


class BuildGenerateResponse(BaseModel):
    builds: list[GeneratedBuild]
    compatibility_status: Literal["valid", "closest_valid", "no_solution"]
    explored_configurations: int
    pruned_configurations: int
    solver_metrics: BuildSolverMetrics = Field(default_factory=BuildSolverMetrics)
    fallback_explanation: str | None = None


SaudiUseCase = Literal[
    "gaming",
    "simulation",
    "workstation",
    "content_creation",
    "ai_ml",
    "streaming",
    "general",
]
SaudiResolution = Literal["1080p", "1440p", "4k", "ultrawide"]
SaudiBuildPriority = Literal[
    "best_value",
    "maximum_performance",
    "quiet_build",
    "upgrade_path",
    "local_availability",
    "lowest_risk",
]
SaudiCaseSize = Literal["ATX", "mATX", "ITX", "no_preference"]
SaudiBuildLabel = Literal[
    "recommended_saudi_build",
    "budget_fit_build",
    "best_value_build",
    "lowest_risk_local_build",
]
ReadinessLevel = Literal["ready", "usable_with_warnings", "not_ready"]
BudgetStatus = Literal["under_budget", "slightly_over_budget", "over_budget", "no_valid_build_under_budget"]
NextCatalogActionType = Literal[
    "manual_product_url",
    "controlled_dry_run",
    "refresh_known_url",
    "review_suspicious_listing",
    "no_action",
]


class SaudiBuildRequest(BaseModel):
    region: Literal["SA"] = "SA"
    city: str = "Riyadh"
    budget_sar: float = Field(gt=0)
    use_case: SaudiUseCase = "gaming"
    target_resolution: SaudiResolution = "1440p"
    refresh_rate_target: Literal[60, 120, 144, 165, 240] = 144
    brand_preferences: list[Literal["AMD", "Intel", "NVIDIA", "no_preference"]] = Field(
        default_factory=lambda: ["no_preference"]
    )
    case_size: SaudiCaseSize = "no_preference"
    priority: SaudiBuildPriority = "best_value"
    strict_budget: bool = False
    include_monitor: bool = False
    include_peripherals: bool = False


class RecommendedDiscoveryJob(BaseModel):
    category: str
    query: str
    region: Literal["SA"] = "SA"
    city: str = "Riyadh"
    limit: int = Field(default=5, ge=1, le=25)
    dry_run: bool = True
    reason: str


class CategoryCoverage(BaseModel):
    category: str
    priced_product_count: int = 0
    trusted_local_listing_count: int = 0
    risky_listing_count: int = 0
    usable_with_warnings_count: int = 0
    unknown_vat_count: int = 0
    unknown_shipping_count: int = 0
    unknown_warranty_count: int = 0
    suspicious_price_count: int = 0
    recommended_option_count: int = 0
    stale_listing_count: int = 0
    ready: bool = False
    readiness_level: ReadinessLevel = "not_ready"
    identity_confidence: float = Field(default=0, ge=0, le=1)
    price_freshness_status: Literal["fresh", "stale", "mixed", "missing"] = "missing"
    blocker_reasons: list[str] = Field(default_factory=list)
    warning_reasons: list[str] = Field(default_factory=list)
    next_action_type: NextCatalogActionType = "no_action"
    notes: list[str] = Field(default_factory=list)
    next_action: str = "No action needed."


class CatalogCompletenessResponse(BaseModel):
    region: str = "SA"
    readiness_score: float = Field(ge=0, le=1)
    build_critical_categories: list[CategoryCoverage] = Field(default_factory=list)
    non_critical_categories: list[CategoryCoverage] = Field(default_factory=list)
    ready_categories: list[str] = Field(default_factory=list)
    usable_with_warnings_categories: list[str] = Field(default_factory=list)
    not_ready_categories: list[str] = Field(default_factory=list)
    stale_categories: list[str] = Field(default_factory=list)
    weak_categories: list[str] = Field(default_factory=list)
    duplicate_risk_categories: list[str] = Field(default_factory=list)
    next_actions: list[RecommendedDiscoveryJob] = Field(default_factory=list)
    message: str


class SaudiBuildDataCompleteness(BaseModel):
    region: Literal["SA"] = "SA"
    city: str = "Riyadh"
    readiness_score: float = Field(ge=0, le=1)
    required_categories: list[str]
    ready_categories: list[str]
    missing_categories: list[str]
    category_coverage: list[CategoryCoverage]
    recommended_discovery_jobs: list[RecommendedDiscoveryJob] = Field(default_factory=list)
    enough_data_for_full_build: bool = False
    message: str


class SaudiBuildComponent(BaseModel):
    product_id: str
    name: str
    category: str
    brand: str | None = None
    recommended_vendor: str | None = None
    recommended_price_sar: float | None = None
    lowest_market_price_sar: float | None = None
    price_confidence: float | None = None
    seller_type: str | None = None
    vendor_region_type: str | None = None
    stock_badge: Literal["local", "gcc", "imported", "unknown"] = "unknown"
    vat_status: str = "vat_unknown"
    shipping_status: str = "unknown_shipping"
    warranty_status: str = "unknown_warranty"
    reason_selected: str
    alternatives: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SaudiBuildSummary(BaseModel):
    total_recommended_price_sar: float | None = None
    total_lowest_possible_price_sar: float | None = None
    budget_remaining_or_overage: float | None = None
    budget_sar: float | None = None
    budget_delta_sar: float | None = None
    over_budget_amount_sar: float = 0
    over_budget_percent: float = 0
    budget_status: BudgetStatus = "under_budget"
    most_expensive_components: list[str] = Field(default_factory=list)
    easiest_savings_opportunities: list[str] = Field(default_factory=list)
    compatibility_status: Literal["valid", "invalid", "incomplete", "not_validated"]
    performance_estimate: str
    bottleneck_summary: str
    risk_summary: list[str] = Field(default_factory=list)
    data_completeness_score: float = Field(ge=0, le=1)
    warning_summary: list[str] = Field(default_factory=list)
    components_with_uncertainty: list[str] = Field(default_factory=list)
    confidence_level: Literal["high", "medium", "low"] = "low"
    confidence_score: float = Field(ge=0, le=1)
    missing_data_warnings: list[str] = Field(default_factory=list)


class SaudiSavingsSuggestion(BaseModel):
    category: str
    current: str
    alternative: str
    estimated_savings_sar: float | None = None
    performance_impact: Literal["low", "moderate", "high", "unknown"] = "unknown"
    reason: str


class SaudiBuildConfidenceBreakdown(BaseModel):
    compatibility_confidence: float = Field(ge=0, le=1)
    market_confidence: float = Field(ge=0, le=1)
    vendor_confidence: float = Field(ge=0, le=1)
    pricing_confidence: float = Field(ge=0, le=1)
    shipping_confidence: float = Field(ge=0, le=1)
    warranty_confidence: float = Field(ge=0, le=1)
    overall_confidence: float = Field(ge=0, le=1)


class SaudiComponentExplanation(BaseModel):
    category: str
    selected_product: str
    reason_selected: str
    cheaper_alternative: str | None = None
    stronger_alternative: str | None = None
    risk_summary: str
    confidence: float = Field(ge=0, le=1)
    local_availability: str
    warranty_confidence: float = Field(ge=0, le=1)
    shipping_confidence: float = Field(ge=0, le=1)
    compatibility_confidence: float = Field(ge=0, le=1)
    market_confidence: float = Field(ge=0, le=1)


class SaudiBuildExplanation(BaseModel):
    build_id: str
    build_mode: SaudiBuildLabel
    confidence_level: Literal["high", "medium", "low"]
    summary: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    budget_analysis: str
    upgrade_path: list[str] = Field(default_factory=list)
    future_limitations: list[str] = Field(default_factory=list)
    recommended_purchase_order: list[str] = Field(default_factory=list)
    component_explanations: list[SaudiComponentExplanation] = Field(default_factory=list)


class SaudiBuildComparisonItem(BaseModel):
    label: SaudiBuildLabel
    title: str
    total_price_sar: float | None = None
    budget_status: BudgetStatus
    risk_level: Literal["low", "medium", "high"]
    confidence_score: float = Field(ge=0, le=1)
    local_availability_summary: str
    upgrade_path_summary: str
    cheapest_option: bool = False
    safest_option: bool = False


class SaudiBuildExport(BaseModel):
    shareable_build_url: str
    json_summary: dict[str, Any]
    markdown_summary: str
    printable_summary: str


class SaudiNoBudgetFitGuidance(BaseModel):
    reason: str
    missing_cheaper_categories: list[str] = Field(default_factory=list)
    suggested_products_to_add: list[str] = Field(default_factory=list)
    suggested_discovery_targets: list[RecommendedDiscoveryJob] = Field(default_factory=list)
    suggested_manual_url_targets: list[str] = Field(default_factory=list)


class SaudiBuildOption(BaseModel):
    label: SaudiBuildLabel
    title: str
    components: list[SaudiBuildComponent]
    summary: SaudiBuildSummary
    explanation: SaudiBuildExplanation
    confidence_breakdown: SaudiBuildConfidenceBreakdown
    savings_suggestions: list[SaudiSavingsSuggestion] = Field(default_factory=list)
    comparison_metrics: SaudiBuildComparisonItem
    export: SaudiBuildExport
    why_this_build: str
    upgrade_notes: list[str] = Field(default_factory=list)


class SaudiBuildResponse(BaseModel):
    region: Literal["SA"] = "SA"
    city: str = "Riyadh"
    build_status: Literal["ready", "incomplete_data", "no_valid_build", "no_budget_fit"]
    builds: list[SaudiBuildOption] = Field(default_factory=list)
    data_completeness: SaudiBuildDataCompleteness
    recommended_discovery_jobs: list[RecommendedDiscoveryJob] = Field(default_factory=list)
    missing_data_warnings: list[str] = Field(default_factory=list)
    strict_budget_failure: SaudiNoBudgetFitGuidance | None = None
    build_comparison: list[SaudiBuildComparisonItem] = Field(default_factory=list)
    audit_trace_id: str | None = None


class SaudiBuildValidationRequest(BaseModel):
    region: Literal["SA"] = "SA"
    city: str = "Riyadh"
    component_ids: dict[str, str] = Field(default_factory=dict)
    budget_sar: float | None = Field(default=None, gt=0)


class SaudiBuildValidationResponse(BaseModel):
    valid: bool
    compatibility_status: Literal["valid", "invalid", "incomplete", "not_validated"]
    market_confidence: float = Field(ge=0, le=1)
    total_recommended_price_sar: float | None = None
    warnings: list[str] = Field(default_factory=list)
    missing_categories: list[str] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
