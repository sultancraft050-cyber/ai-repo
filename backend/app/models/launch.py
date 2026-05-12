from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.services.hardware_taxonomy import normalize_category
from app.services.region_config import normalize_region


AnalyticsEventType = Literal[
    "landing_page_visit",
    "region_selection",
    "build_generation",
    "build_save",
    "build_share",
    "watchlist_add",
    "deal_submission",
    "failed_build_generation",
    "incomplete_build_generation",
    "over_budget_build",
    "build_comparison_usage",
]

FeedbackType = Literal[
    "wrong_price",
    "expired_listing",
    "wrong_compatibility",
    "suspicious_recommendation",
    "bad_vendor_listing",
    "broken_product_url",
    "missing_store",
    "missing_product",
    "confusing_warning",
]


class AnalyticsEventCreate(BaseModel):
    event_type: AnalyticsEventType
    region: str = "SA"
    anonymous_session_id: str | None = Field(default=None, min_length=6, max_length=120)
    user_id: str | None = Field(default=None, max_length=120)
    category: str | None = Field(default=None, max_length=80)
    build_status: str | None = Field(default=None, max_length=80)
    budget_sar: float | None = Field(default=None, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("region")
    @classmethod
    def valid_region(cls, value: str) -> str:
        return normalize_region(value)

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str | None) -> str | None:
        return normalize_category(value) if value else None


class AnalyticsEventView(BaseModel):
    event_id: str = Field(default_factory=lambda: f"analytics-{uuid4()}")
    event_type: AnalyticsEventType
    region: str = "SA"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    anonymous_session_id: str | None = None
    user_id: str | None = None
    category: str | None = None
    build_status: str | None = None
    budget_sar: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalyticsEventResponse(BaseModel):
    status: Literal["recorded"]
    event_id: str


class FeedbackSubmissionCreate(BaseModel):
    type: FeedbackType
    region: str = "SA"
    product_id: str | None = Field(default=None, max_length=160)
    build_id: str | None = Field(default=None, max_length=160)
    share_slug: str | None = Field(default=None, max_length=80)
    notes: str = Field(min_length=4, max_length=800)
    anonymous_session_id: str | None = Field(default=None, min_length=6, max_length=120)

    @field_validator("region")
    @classmethod
    def valid_region(cls, value: str) -> str:
        return normalize_region(value)


class FeedbackSubmissionView(BaseModel):
    feedback_id: str = Field(default_factory=lambda: f"feedback-{uuid4()}")
    type: FeedbackType
    product_id: str | None = None
    build_id: str | None = None
    share_slug: str | None = None
    region: str = "SA"
    notes: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["new", "reviewing", "resolved", "dismissed"] = "new"
    anonymous_session_id: str | None = None


class FeedbackSubmissionResponse(BaseModel):
    status: Literal["accepted"]
    feedback_id: str
    message: str


class BuildFailureSummary(BaseModel):
    region: str = "SA"
    top_missing_categories: list[dict[str, Any]] = Field(default_factory=list)
    top_over_budget_causes: list[dict[str, Any]] = Field(default_factory=list)
    most_common_substitution_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    categories_with_weak_saudi_coverage: list[str] = Field(default_factory=list)
    categories_with_highest_uncertainty: list[str] = Field(default_factory=list)


class MarketCoverageSummary(BaseModel):
    region: str = "SA"
    product_count_per_category: dict[str, int] = Field(default_factory=dict)
    trusted_saudi_listing_count: int = 0
    risky_listing_count: int = 0
    stale_listing_count: int = 0
    missing_category_count: int = 0
    duplicate_risk_count: int = 0
    weak_categories: list[str] = Field(default_factory=list)


class CategoryPriorityScore(BaseModel):
    category: str
    score: float = Field(ge=0, le=100)
    readiness_level: Literal["ready", "usable_with_warnings", "not_ready"] = "not_ready"
    build_dependency_weight: float = Field(ge=0, le=1)
    user_search_demand: int = 0
    build_failure_frequency: int = 0
    trusted_saudi_listing_count: int = 0
    stale_listing_count: int = 0
    duplicate_risk: bool = False
    uncertainty_level: Literal["low", "medium", "high"] = "high"
    blocker_reasons: list[str] = Field(default_factory=list)
    recommended_next_action: str


class FounderActionQueueItem(BaseModel):
    category: str
    recommended_products_to_add: list[str] = Field(default_factory=list)
    reason: str
    expected_impact: str
    suggested_store_targets: list[str] = Field(default_factory=list)
    estimated_improvement: str


class ProductFamilyCoverage(BaseModel):
    category: str
    family: str
    saudi_coverage_percent: float = Field(ge=0, le=100)
    trusted_listing_count: int = 0
    cheapest_trusted_listing_sar: float | None = None
    uncertainty_level: Literal["low", "medium", "high"] = "high"
    last_updated: str | None = None


class StoreCoverageQuality(BaseModel):
    store_name: str
    score: float = Field(ge=0, le=100)
    trusted_listing_count: int = 0
    uncertainty_count: int = 0
    stale_url_count: int = 0
    duplicate_issue_count: int = 0
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)


class MarketCoverageTrendPoint(BaseModel):
    label: str
    build_success_rate: float = Field(ge=0, le=1)
    readiness_score: float = Field(ge=0, le=1)
    warning_frequency: int = 0
    trusted_listing_growth: int = 0
    stale_listing_reduction: int = 0


class CatalogGrowthWorkflowSummary(BaseModel):
    region: str = "SA"
    category_priorities: list[CategoryPriorityScore] = Field(default_factory=list)
    founder_action_queue: list[FounderActionQueueItem] = Field(default_factory=list)
    product_family_coverage: list[ProductFamilyCoverage] = Field(default_factory=list)
    store_quality_scores: list[StoreCoverageQuality] = Field(default_factory=list)
    build_blocker_summary: BuildFailureSummary
    readiness_trends: list[MarketCoverageTrendPoint] = Field(default_factory=list)
    top_blockers: list[str] = Field(default_factory=list)
    most_needed_urls: list[str] = Field(default_factory=list)
    message: str


class RuntimeHealthSummary(BaseModel):
    status: Literal["healthy", "watch", "degraded"] = "healthy"
    build_generation_latency_ms: float = 0
    slow_endpoints: list[dict[str, Any]] = Field(default_factory=list)
    graph_query_latency_ms: float = 0
    frontend_payload_size_bytes: dict[str, int] = Field(default_factory=dict)
    refresh_success_failure: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class DeploymentEnvCheck(BaseModel):
    name: str
    required: bool
    configured: bool
    public: bool = False
    status: Literal["ok", "missing", "optional", "warning"]
    message: str


class DeploymentChecklist(BaseModel):
    environment: str
    market_data_mode: str
    version_info: dict[str, str | None] = Field(default_factory=dict)
    env_completeness: list[DeploymentEnvCheck] = Field(default_factory=list)
    neo4j_connectivity: dict[str, Any] = Field(default_factory=dict)
    source_configuration_status: list[dict[str, Any]] = Field(default_factory=list)
    build_readiness_status: dict[str, Any] = Field(default_factory=dict)
    runtime_health: RuntimeHealthSummary
    deployment_blockers: list[str] = Field(default_factory=list)
    launch_ready: bool = False


class FounderInsightsSummary(BaseModel):
    region: str = "SA"
    recommended_next_category: str | None = None
    weak_vendor_coverage: list[str] = Field(default_factory=list)
    most_requested_categories: list[dict[str, Any]] = Field(default_factory=list)
    common_budget_ranges: list[dict[str, Any]] = Field(default_factory=list)
    most_common_failure_modes: list[dict[str, Any]] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)


class MvpHealthDashboard(BaseModel):
    region: str = "SA"
    active_users_today: int = 0
    builds_generated: int = 0
    builds_failing: int = 0
    top_categories_searched: list[dict[str, Any]] = Field(default_factory=list)
    top_missing_categories: list[dict[str, Any]] = Field(default_factory=list)
    stale_pricing_count: int = 0
    saudi_coverage_percent: float = 0
    source_health: list[dict[str, Any]] = Field(default_factory=list)
    watchlist_activity: int = 0
    deal_submissions_pending: int = 0
    feedback_pending: int = 0
    founder_insights: FounderInsightsSummary
