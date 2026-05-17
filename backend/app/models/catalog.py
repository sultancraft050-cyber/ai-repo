from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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


class CanonicalImportCommitRequest(BaseModel):
    source_name: str = Field(min_length=2, max_length=120)
    source_type: CanonicalImportSourceType
    category: CatalogCategory
    batch_limit: int = Field(default=50, ge=1, le=100)
    commit: bool = False
    approval_required_for_conflicts: bool = True

    @model_validator(mode="after")
    def enforce_controlled_batch_size(self) -> "CanonicalImportCommitRequest":
        if self.category == "Motherboard" and self.batch_limit > 50:
            raise ValueError("Motherboard canonical imports are capped at batch_limit=50")
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
    batch_limit: int = Field(default=100, ge=1, le=100)
    license_note: str = Field(min_length=3, max_length=500)
    dry_run: bool = True

    @model_validator(mode="after")
    def enforce_stage_batch_size(self) -> "CanonicalImportStageRequest":
        if self.category == "Motherboard" and self.batch_limit > 50:
            raise ValueError("Motherboard canonical staging is capped at batch_limit=50")
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
