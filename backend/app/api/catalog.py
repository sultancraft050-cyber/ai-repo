from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_pricing_repository, resolve_market_region
from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.api import CatalogCompletenessResponse
from app.models.catalog import (
    CanonicalEvidenceRequest,
    CanonicalEvidenceResponse,
    CanonicalImportCommitRequest,
    CanonicalImportCommitResponse,
    CanonicalImportStageRequest,
    CanonicalImportStageResponse,
    CanonicalStagedClearResponse,
    CanonicalStagedSummaryResponse,
    CatalogCoverageResponse,
    CatalogFeedImportRequest,
    CatalogFeedImportResponse,
    CatalogFeedRunView,
    HybridDataLayerView,
    HybridGraphIntegrityResponse,
    HybridGraphStrategyResponse,
    HybridSourceView,
)
from app.services.saudi_build_generator import SaudiLocalBuildService

router = APIRouter(prefix="/catalog", tags=["catalog"])
logger = logging.getLogger("pc_builder.catalog_api")


@router.get("/completeness", response_model=CatalogCompletenessResponse)
def catalog_completeness(
    region: str | None = "SA",
    city: str = "Riyadh",
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> CatalogCompletenessResponse:
    resolved_region = resolve_market_region(region)
    try:
        return SaudiLocalBuildService(repository).catalog_completeness(region=resolved_region, city=city)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.post("/feeds/import", response_model=CatalogFeedImportResponse)
def import_catalog_feed(
    request_body: CatalogFeedImportRequest,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> CatalogFeedImportResponse:
    return repository.import_catalog_feed(
        rows=request_body.rows,
        source_name=request_body.source_name,
        category=request_body.category,
        region=resolve_market_region(request_body.region),
        dry_run=request_body.dry_run,
    )


@router.get("/feeds/runs", response_model=list[CatalogFeedRunView])
def catalog_feed_runs(
    limit: int = Query(default=50, ge=1, le=200),
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> list[CatalogFeedRunView]:
    return repository.catalog_feed_runs(limit=limit)


@router.post("/import/commit", response_model=CanonicalImportCommitResponse)
def commit_canonical_import(
    request_body: CanonicalImportCommitRequest,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> CanonicalImportCommitResponse:
    return repository.commit_canonical_import(request_body, region="SA")


@router.post("/import/stage", response_model=CanonicalImportStageResponse)
def stage_canonical_import(
    request_body: CanonicalImportStageRequest,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> CanonicalImportStageResponse:
    try:
        return repository.stage_canonical_import(request_body)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except Exception as error:
        logger.exception(
            "canonical_stage_failed",
            extra={"source_name": request_body.source_name, "category": request_body.category},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"canonical staging failed safely: {type(error).__name__}",
        ) from error


@router.get("/import/staged", response_model=CanonicalStagedSummaryResponse)
def staged_canonical_import_summary(
    source_name: str | None = Query(default=None, min_length=2, max_length=120),
    category: str | None = Query(default=None, min_length=2, max_length=80),
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> CanonicalStagedSummaryResponse:
    return repository.staged_canonical_import_summary(source_name=source_name, category=category)


@router.delete("/import/staged", response_model=CanonicalStagedClearResponse)
def clear_staged_canonical_import(
    source_name: str = Query(min_length=2, max_length=120),
    category: str = Query(min_length=2, max_length=80),
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> CanonicalStagedClearResponse:
    return repository.clear_staged_canonical_import(source_name=source_name, category=category)


@router.get("/coverage", response_model=CatalogCoverageResponse)
def catalog_coverage(
    region: str | None = "SA",
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> CatalogCoverageResponse:
    return repository.catalog_coverage(region=resolve_market_region(region))


@router.get("/hybrid/strategy", response_model=HybridGraphStrategyResponse)
def hybrid_graph_strategy() -> HybridGraphStrategyResponse:
    return HybridGraphStrategyResponse(
        objective="Combine canonical hardware knowledge, Saudi prices, telemetry, and curation without letting one source control the graph.",
        canonicalization_policy=[
            "Canonical product identity is based on model, family, socket/chipset, memory type, capacity, wattage, and form factor evidence.",
            "Saudi URLs map into existing canonical products when possible; they do not own canonical specifications.",
            "Regional prices live in PriceSnapshot/RegionalPriceSnapshot nodes and never overwrite canonical specs.",
            "Community and founder evidence is attached as evidence with approval state instead of directly mutating product truth.",
        ],
        data_layers=[
            HybridDataLayerView(
                layer="Canonical Hardware Knowledge",
                graph_labels=["CanonicalProduct", "ProductFamily", "Brand", "Socket", "MemoryType", "Chipset", "FormFactor", "EfficiencyRating"],
                owns=["stable specs", "compatibility metadata", "product family identity"],
                must_not_own=["regional price", "seller availability", "VAT/shipping/warranty state"],
                trusted_sources=["BuildCores/OpenDB", "approved spec feeds", "official vendor spec pages", "Kaggle seed datasets"],
            ),
            HybridDataLayerView(
                layer="Saudi Market Pricing",
                graph_labels=["RegionalPriceSnapshot", "Vendor", "ProductURL"],
                owns=["SAR price", "availability", "seller", "VAT/shipping/warranty uncertainty", "vendor risk"],
                must_not_own=["canonical socket", "canonical chipset", "canonical wattage"],
                trusted_sources=["approved Saudi product URLs", "founder-approved URL lists", "SerpAPI discovery dry-runs"],
            ),
            HybridDataLayerView(
                layer="Performance/Telemetry",
                graph_labels=["TelemetrySnapshot", "TelemetryEvidence", "HardwareIntelligence"],
                owns=["benchmark observations", "FPS estimates", "thermal/noise observations"],
                must_not_own=["canonical identity", "Saudi price"],
                trusted_sources=["official benchmarks", "structured benchmark imports", "validated user telemetry"],
            ),
            HybridDataLayerView(
                layer="Founder/Community Curation",
                graph_labels=["CommunityEvidence", "FounderApprovalState", "FieldEvidence"],
                owns=["aliases", "duplicate review", "compatibility hints", "approval state"],
                must_not_own=["unapproved canonical mutation", "unverified price certainty"],
                trusted_sources=["founder review", "user-submitted deals", "community compatibility reports"],
            ),
        ],
        source_strategy=[
            HybridSourceView(
                source_name="BuildCores/OpenDB",
                layer="Canonical Hardware Knowledge",
                allowed_use=["canonical specs", "compatibility relationships", "product aliases"],
                disallowed_use=["Saudi prices", "seller trust"],
                trust_weight=0.88,
                requires_founder_approval=False,
            ),
            HybridSourceView(
                source_name="Community repositories",
                layer="Founder/Community Curation",
                allowed_use=["aliases", "PSU tiers", "GPU hierarchy hints", "compatibility hints"],
                disallowed_use=["direct canonical overwrite", "regional price certainty"],
                trust_weight=0.62,
                requires_founder_approval=True,
            ),
            HybridSourceView(
                source_name="Kaggle datasets",
                layer="Canonical Hardware Knowledge",
                allowed_use=["initial catalog seeding", "historical benchmark metadata", "fallback normalization"],
                disallowed_use=["current Saudi price", "unverified availability"],
                trust_weight=0.55,
                requires_founder_approval=True,
            ),
            HybridSourceView(
                source_name="Saudi URL ingestion",
                layer="Saudi Market Pricing",
                allowed_use=["SAR price", "vendor", "stock", "VAT/shipping/warranty warnings"],
                disallowed_use=["canonical spec overwrite", "uncontrolled URL discovery"],
                trust_weight=0.78,
                requires_founder_approval=True,
            ),
            HybridSourceView(
                source_name="SerpAPI",
                layer="Saudi Market Pricing",
                allowed_use=["controlled discovery candidates", "dry-run market leads"],
                disallowed_use=["daily refresh dependency", "automatic canonical truth"],
                trust_weight=0.48,
                requires_founder_approval=True,
            ),
        ],
        safety_rules=[
            "No broad scraping or category crawling is part of this layer.",
            "Every source keeps source_name, trust_score, freshness, and approval state.",
            "Build generation can use regional prices only from the requested region.",
            "Conflicting evidence lowers confidence until founder review or stronger source agreement resolves it.",
        ],
    )


@router.get("/hybrid/integrity", response_model=HybridGraphIntegrityResponse)
def hybrid_graph_integrity(
    region: str | None = "SA",
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> HybridGraphIntegrityResponse:
    return repository.hybrid_graph_integrity(region=resolve_market_region(region))


@router.post("/canonical/evidence", response_model=CanonicalEvidenceResponse)
def attach_canonical_evidence(
    request_body: CanonicalEvidenceRequest,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> CanonicalEvidenceResponse:
    result = repository.attach_canonical_evidence(request_body)
    if not result.attached:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return result
