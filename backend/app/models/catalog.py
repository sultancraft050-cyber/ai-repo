from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.catalog_expansion import safe_batch_size


CatalogCategory = Literal[
    "CPU",
    "GPU",
    "Motherboard",
    "RAM",
    "Storage",
    "PSU",
    "Case",
    "Cooler",
    "Monitor",
    "Keyboard",
    "Mouse",
    "Speaker",
    "Accessories",
]


class CatalogFeedImportRow(BaseModel):
    name: str = Field(min_length=2, max_length=240)
    category: CatalogCategory | None = None
    brand: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=120)
    canonical_key: str | None = Field(default=None, max_length=240)
    image_url: str | None = Field(default=None, max_length=2048)
    processed_image_url: str | None = Field(default=None, max_length=2048)
    specs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("brand", "model", "canonical_key", "image_url", "processed_image_url", mode="before")
    @classmethod
    def blank_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class CatalogFeedImportRequest(BaseModel):
    source_name: str = Field(min_length=2, max_length=120)
    category: CatalogCategory
    region: str = Field(default="SA", min_length=2, max_length=8)
    dry_run: bool = True
    rows: list[CatalogFeedImportRow] = Field(default_factory=list, max_length=1000)


class CatalogFeedImportResponse(BaseModel):
    run_id: str
    source_name: str
    category: str
    region: str
    dry_run: bool
    status: str
    imported_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    sanitized_error: str | None = None


class CatalogFeedRunView(BaseModel):
    run_id: str
    source_name: str
    category: str
    region: str
    status: str
    imported_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    dry_run: bool
    started_at: datetime | None = None
    finished_at: datetime | None = None
    sanitized_error: str | None = None


CanonicalImportSourceType = Literal[
    "canonical_specs",
    "benchmark_metadata",
    "community_repository",
    "kaggle_dataset",
]
CanonicalImportAdapter = Literal["pc_part_dataset"]


class CanonicalImportCommitRequest(BaseModel):
    source_name: str = Field(min_length=2, max_length=120)
    source_type: CanonicalImportSourceType
    category: CatalogCategory
    batch_limit: int = Field(default=25, ge=1, le=100)
    commit: bool = False
    approval_required_for_conflicts: bool = True

    @model_validator(mode="after")
    def enforce_controlled_batch_size(self) -> "CanonicalImportCommitRequest":
        cap = safe_batch_size(self.category, operation="commit")
        if self.batch_limit > cap:
            raise ValueError(f"{self.category} canonical imports are capped at batch_limit={cap}")
        return self


class CanonicalImportConflictView(BaseModel):
    canonical_key: str
    incoming_name: str
    existing_product_id: str | None = None
    conflict_fields: list[str] = Field(default_factory=list)
    evidence_id: str | None = None
    approval_id: str | None = None


class CanonicalImportCommitResponse(BaseModel):
    run_id: str
    source_name: str
    source_type: CanonicalImportSourceType
    category: str
    commit: bool
    batch_limit: int
    status: str
    imported_count: int
    updated_count: int
    skipped_count: int
    conflict_count: int
    approvals_created: int
    duplicate_risk: int
    categories_improved: list[str] = Field(default_factory=list)
    graph_integrity_status: Literal["pass", "warn", "fail"]
    conflicts: list[CanonicalImportConflictView] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CanonicalImportReasonCount(BaseModel):
    reason: str
    count: int


class CanonicalImportStageRequest(BaseModel):
    source_name: str = Field(min_length=2, max_length=120)
    source_type: CanonicalImportSourceType
    dataset_path: str = Field(min_length=3, max_length=500)
    category: CatalogCategory
    batch_limit: int = Field(default=25, ge=1, le=100)
    adapter: CanonicalImportAdapter | None = None
    target_priority_tier: CatalogExpansionPriorityTier | None = None
    license_note: str = Field(min_length=3, max_length=500)
    dry_run: bool = True

    @model_validator(mode="after")
    def enforce_stage_batch_size(self) -> "CanonicalImportStageRequest":
        cap = safe_batch_size(self.category, operation="stage")
        if self.batch_limit > cap:
            raise ValueError(f"{self.category} canonical staging is capped at batch_limit={cap}")
        return self


class CanonicalImportStageResponse(BaseModel):
    run_id: str
    source_name: str
    source_type: CanonicalImportSourceType
    category: str
    dataset_path: str
    dry_run: bool
    status: str
    total_records_seen: int
    staged_records: int
    rejected_records: int
    true_rejected_count: int = 0
    deferred_records: int = 0
    near_match_count: int = 0
    accepted_current_gen_count: int = 0
    accepted_value_fallback_count: int = 0
    duplicate_candidates: int
    conflict_candidates: int
    categories: list[str] = Field(default_factory=list)
    top_rejection_reasons: list[CanonicalImportReasonCount] = Field(default_factory=list)
    top_warning_reasons: list[CanonicalImportReasonCount] = Field(default_factory=list)
    recommended_next_action: str


class CanonicalStagedSummaryResponse(BaseModel):
    source_name: str | None = None
    source_type: CanonicalImportSourceType | None = None
    category: str | None = None
    staged_count: int
    valid_count: int
    invalid_count: int
    duplicate_candidate_count: int
    conflict_candidate_count: int
    categories: list[str] = Field(default_factory=list)
    readiness_for_commit: str


class CanonicalStagedClearResponse(BaseModel):
    source_name: str
    category: str
    deleted_count: int
    status: str


class CatalogCategoryCoverage(BaseModel):
    category: str
    product_count: int
    priced_product_count: int
    trusted_listing_count: int
    stale_listing_count: int
    missing_processed_image_count: int
    missing_compatibility_spec_count: int
    duplicate_risk_count: int
    readiness_level: str
    next_best_action: str


class CatalogCoverageResponse(BaseModel):
    region: str
    category_count: int
    product_count: int
    priced_product_count: int
    stale_listing_count: int
    categories: list[CatalogCategoryCoverage]


CatalogProductState = Literal[
    "compatibility_ready_exact",
    "compatibility_ready_family",
    "metadata_only",
    "conflict_requires_review",
]
CatalogExpansionPriorityTier = Literal["current_gen_priority", "value_fallback", "legacy_deprioritized"]


class CatalogExpansionTargetFamily(BaseModel):
    category: str
    family_key: str
    family_name: str
    priority: int
    priority_tier: CatalogExpansionPriorityTier = "current_gen_priority"
    target_min: int
    target_max: int
    canonical_count: int
    compatibility_ready_count: int
    saudi_priced_count: int
    trusted_vendor_count: int
    staged_count: int
    metadata_only_count: int
    conflict_count: int
    missing_required_specs: list[str] = Field(default_factory=list)
    readiness_state: CatalogProductState
    next_action: str


class CatalogExpansionCategorySummary(BaseModel):
    category: str
    priority_order: int
    target_min: int
    target_max: int
    safe_stage_batch_size: int
    safe_commit_batch_size: int
    canonical_count: int
    compatibility_ready_count: int
    saudi_priced_count: int
    trusted_vendor_count: int
    staged_count: int
    metadata_only_count: int
    conflict_count: int
    missing_required_specs: list[str] = Field(default_factory=list)
    readiness_state: CatalogProductState
    next_action: str
    families: list[CatalogExpansionTargetFamily] = Field(default_factory=list)


class CatalogExpansionTargetsResponse(BaseModel):
    region: str
    phase: str
    first_milestone_min: int
    first_milestone_max: int
    final_milestone_min: int
    final_milestone_max: int
    total_canonical_count: int
    total_compatibility_ready_count: int
    total_saudi_priced_count: int
    total_trusted_vendor_count: int
    product_states: list[CatalogProductState]
    categories: list[CatalogExpansionCategorySummary] = Field(default_factory=list)


class HybridDataLayerView(BaseModel):
    layer: str
    graph_labels: list[str]
    owns: list[str]
    must_not_own: list[str]
    trusted_sources: list[str]


class HybridSourceView(BaseModel):
    source_name: str
    layer: str
    allowed_use: list[str]
    disallowed_use: list[str]
    trust_weight: float = Field(ge=0, le=1)
    requires_founder_approval: bool


class HybridGraphStrategyResponse(BaseModel):
    objective: str
    canonicalization_policy: list[str]
    data_layers: list[HybridDataLayerView]
    source_strategy: list[HybridSourceView]
    safety_rules: list[str]


class HybridIntegrityCheck(BaseModel):
    name: str
    status: Literal["pass", "warn", "fail"]
    detail: str
    count: int = 0


class HybridGraphIntegrityResponse(BaseModel):
    region: str
    canonical_product_count: int
    regional_price_snapshot_count: int
    telemetry_evidence_count: int
    community_evidence_count: int
    founder_approval_state_count: int
    checks: list[HybridIntegrityCheck]


CanonicalEvidenceType = Literal[
    "canonical_spec",
    "compatibility_hint",
    "community_hint",
    "founder_note",
    "performance_hint",
]


class CanonicalEvidenceRequest(BaseModel):
    product_id: str = Field(min_length=2, max_length=240)
    source_name: str = Field(min_length=2, max_length=120)
    evidence_type: CanonicalEvidenceType
    field: str = Field(min_length=2, max_length=120)
    value: Any
    trust_score: float = Field(default=0.5, ge=0, le=1)
    note: str | None = Field(default=None, max_length=500)
    approved_by_founder: bool = False


class CanonicalEvidenceResponse(BaseModel):
    product_id: str
    evidence_id: str
    evidence_type: CanonicalEvidenceType
    source_name: str
    attached: bool
    approval_state: str


class ConfirmedCpuSpecRecord(BaseModel):
    canonical_key: str = Field(min_length=3, max_length=240)
    socket: str = Field(min_length=2, max_length=40)
    cores: int = Field(ge=1, le=512)
    threads: int = Field(ge=1, le=1024)
    tdp_w: int | None = Field(default=None, ge=1, le=1000)
    evidence_note: str = Field(min_length=3, max_length=500)

    @field_validator("canonical_key")
    @classmethod
    def require_cpu_key(cls, value: str) -> str:
        if not value.upper().startswith("CPU|"):
            raise ValueError("canonical_key must be a CPU canonical key")
        return value


class ConfirmedCpuSpecEnrichmentRequest(BaseModel):
    source_name: str = Field(min_length=2, max_length=120)
    license_note: str = Field(min_length=3, max_length=500)
    records: list[ConfirmedCpuSpecRecord] = Field(default_factory=list, min_length=1, max_length=100)
    dry_run: bool = True


class ConfirmedCpuSpecEnrichmentItem(BaseModel):
    canonical_key: str
    status: Literal["would_enrich", "enriched", "skipped"]
    staged_record_found: bool
    evidence_attached: bool = False
    reason: str | None = None
    confirmed_fields: list[str] = Field(default_factory=list)


class ConfirmedCpuSpecEnrichmentResponse(BaseModel):
    source_name: str
    dry_run: bool
    total_records: int
    matched_staged_records: int
    enriched_records: int
    skipped_records: int
    evidence_created: int
    items: list[ConfirmedCpuSpecEnrichmentItem] = Field(default_factory=list)


HybridImportClassification = Literal[
    "canonical_ready_and_market_linked",
    "canonical_ready_no_saudi_price",
    "metadata_only_needs_enrichment",
    "conflict_requires_founder_review",
    "reject",
]


class HybridImportReviewItem(BaseModel):
    staged_id: str | None = None
    raw_name: str
    normalized_name: str | None = None
    canonical_key: str | None = None
    category: str
    classification: HybridImportClassification
    identity_confidence: float | None = None
    compatibility_ready: bool = False
    compatibility_ready_exact: bool = False
    compatibility_ready_family: bool = False
    readiness_state: CatalogProductState = "metadata_only"
    market_linked: bool = False
    saudi_price_sar: float | None = None
    saudi_vendor: str | None = None
    missing_compatibility_fields: list[str] = Field(default_factory=list)
    missing_exact_card_fields: list[str] = Field(default_factory=list)
    inferred_fields: list[str] = Field(default_factory=list)
    conflict_candidates: list[str] = Field(default_factory=list)
    duplicate_candidates: list[str] = Field(default_factory=list)
    rejected_reasons: list[str] = Field(default_factory=list)
    warning_reasons: list[str] = Field(default_factory=list)
    target_family_key: str | None = None
    target_family_name: str | None = None
    expansion_priority: int | None = None
    import_status: str | None = None
    already_imported: bool = False
    commit_eligible: bool = False
    next_action: str


class HybridImportReviewResponse(BaseModel):
    source_name: str
    category: str
    region: str
    total_staged: int
    classification_counts: dict[str, int] = Field(default_factory=dict)
    market_linked_count: int
    imported_count: int = 0
    metadata_only_count: int
    conflict_count: int
    reject_count: int
    exact_ready_count: int = 0
    family_ready_count: int = 0
    card_dimension_missing_count: int = 0
    commit_eligible_count: int
    top_missing_compatibility_fields: list[CanonicalImportReasonCount] = Field(default_factory=list)
    top_missing_exact_card_fields: list[CanonicalImportReasonCount] = Field(default_factory=list)
    top_inferred_fields: list[CanonicalImportReasonCount] = Field(default_factory=list)
    items: list[HybridImportReviewItem] = Field(default_factory=list)


class ConfirmedSpecRecord(BaseModel):
    canonical_key: str = Field(min_length=3, max_length=240)
    specs: dict[str, Any] = Field(default_factory=dict)
    evidence_note: str = Field(min_length=3, max_length=500)


class ConfirmedSpecEnrichmentRequest(BaseModel):
    category: CatalogCategory
    source_name: str = Field(min_length=2, max_length=120)
    license_note: str = Field(min_length=3, max_length=500)
    records: list[ConfirmedSpecRecord] = Field(default_factory=list, min_length=1, max_length=100)
    dry_run: bool = True


class ConfirmedSpecEnrichmentItem(BaseModel):
    canonical_key: str
    status: Literal["would_enrich", "enriched", "skipped", "conflict_requires_founder_review"]
    staged_record_found: bool
    evidence_attached: bool = False
    reason: str | None = None
    confirmed_fields: list[str] = Field(default_factory=list)
    missing_required_fields: list[str] = Field(default_factory=list)


class ConfirmedSpecEnrichmentResponse(BaseModel):
    source_name: str
    category: str
    dry_run: bool
    total_records: int
    matched_staged_records: int
    enriched_records: int
    skipped_records: int
    conflict_count: int
    evidence_created: int
    items: list[ConfirmedSpecEnrichmentItem] = Field(default_factory=list)


class MarketEvidenceLinkRequest(BaseModel):
    source_name: str = Field(default="catalog_identity_linker", min_length=2, max_length=120)
    region: str = Field(default="SA", min_length=2, max_length=8)
    category: CatalogCategory | None = None
    canonical_keys: list[str] = Field(default_factory=list, max_length=100)
    confidence_threshold: float = Field(default=0.9, ge=0.5, le=1)
    limit: int = Field(default=50, ge=1, le=100)
    dry_run: bool = True


class MarketEvidenceLinkItem(BaseModel):
    canonical_key: str
    product_id: str | None = None
    product_name: str | None = None
    confidence: float
    status: Literal["would_link", "linked", "skipped"]
    reason: str | None = None
    price_snapshot_count: int = 0
    cheapest_price_sar: float | None = None
    cheapest_vendor: str | None = None


class MarketEvidenceLinkResponse(BaseModel):
    region: str
    dry_run: bool
    matched_count: int
    linked_count: int
    skipped_count: int
    price_mutation_count: int = 0
    items: list[MarketEvidenceLinkItem] = Field(default_factory=list)


SpecAuditStatus = Literal[
    "verified_current",
    "safe_fix_available",
    "missing_trusted_evidence",
    "spec_conflict_requires_review",
    "stale_or_deprioritized",
]
SpecAuditMode = Literal["preview", "apply_safe"]
SpecAuditSourcePolicy = Literal["trusted_mixed"]


class SpecAuditRunRequest(BaseModel):
    region: str = Field(default="SA", min_length=2, max_length=8)
    categories: list[CatalogCategory] = Field(default_factory=list, min_length=1, max_length=8)
    mode: SpecAuditMode = "preview"
    limit: int = Field(default=50, ge=1, le=500)
    source_policy: SpecAuditSourcePolicy = "trusted_mixed"

    @field_validator("categories")
    @classmethod
    def require_pc_component_categories(cls, value: list[CatalogCategory]) -> list[CatalogCategory]:
        allowed = {"CPU", "GPU", "Motherboard", "RAM", "Storage", "PSU", "Case", "Cooler"}
        invalid = [category for category in value if category not in allowed]
        if invalid:
            raise ValueError(f"spec audit only supports PC component categories: {', '.join(invalid)}")
        return list(dict.fromkeys(value))


class SpecAuditEvidenceSummary(BaseModel):
    source_name: str
    field: str
    trust_score: float | None = None
    approval_state: str | None = None


class SpecAuditProductAction(BaseModel):
    product_id: str
    canonical_key: str | None = None
    name: str
    category: str
    status: SpecAuditStatus
    missing_fields: list[str] = Field(default_factory=list)
    conflicting_fields: list[str] = Field(default_factory=list)
    inferred_fields: list[str] = Field(default_factory=list)
    safe_fix_fields: list[str] = Field(default_factory=list)
    safe_fix_values: dict[str, Any] = Field(default_factory=dict)
    safe_fix_sources: dict[str, str] = Field(default_factory=dict)
    safe_fix_applied_fields: list[str] = Field(default_factory=list)
    stale_reason: str | None = None
    evidence_summary: list[SpecAuditEvidenceSummary] = Field(default_factory=list)
    next_action: str


class SpecAuditCategoryMissingFields(BaseModel):
    category: str
    fields: list[CanonicalImportReasonCount] = Field(default_factory=list)


class SpecAuditPriceCountSnapshot(BaseModel):
    before: int
    after: int
    unchanged: bool


class SpecAuditRunResponse(BaseModel):
    audit_id: str
    region: str
    mode: SpecAuditMode
    source_policy: SpecAuditSourcePolicy
    categories: list[str]
    limit: int
    audited_product_count: int
    verified_count: int
    missing_evidence_count: int
    conflict_count: int
    stale_or_deprioritized_count: int
    safe_fixes_available_count: int
    safe_fixes_applied_count: int = 0
    conflict_reviews_created_count: int = 0
    per_category_missing_fields: list[SpecAuditCategoryMissingFields] = Field(default_factory=list)
    product_actions: list[SpecAuditProductAction] = Field(default_factory=list)
    price_snapshot_count: SpecAuditPriceCountSnapshot
    regional_price_snapshot_count: SpecAuditPriceCountSnapshot


class SpecAuditProductListResponse(BaseModel):
    audit_id: str | None = None
    status: SpecAuditStatus | None = None
    category: str | None = None
    products: list[SpecAuditProductAction] = Field(default_factory=list)
