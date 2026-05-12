from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.launch import AnalyticsEventCreate, FeedbackSubmissionCreate
from app.services.launch_analytics import LaunchAnalyticsStore, LaunchInsightsService


class FakeSettings:
    environment = "production"
    market_data_mode = "free"
    neo4j_uri = "neo4j+s://example.databases.neo4j.io"
    neo4j_user = "neo4j"
    neo4j_password = "super-secret-password"
    neo4j_database = "neo4j"
    frontend_url = "https://example.test"
    backend_url = "https://api.example.test"
    cors_origins = ("https://example.test",)
    auth_required = True
    analyst_api_key = "analyst-secret"
    admin_api_key = "admin-secret"
    super_admin_api_key = "super-secret"
    serpapi_key = None
    ebay_browse_token = None
    bestbuy_api_key = None
    amazon_paapi_access_key = None
    amazon_paapi_secret_key = None
    amazon_paapi_partner_tag = None


class FakeReadiness:
    region = "SA"
    readiness_score = 1.0
    enough_data_for_full_build = True
    missing_categories: list[str] = []
    message = "Saudi data is sufficient for build generation."


class FakeCoverage:
    def __init__(
        self,
        category: str,
        readiness_level: str,
        *,
        trusted: int = 0,
        stale: int = 0,
        unknown_vat: int = 0,
        unknown_shipping: int = 0,
        unknown_warranty: int = 0,
        blockers: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        self.category = category
        self.readiness_level = readiness_level
        self.trusted_local_listing_count = trusted
        self.stale_listing_count = stale
        self.unknown_vat_count = unknown_vat
        self.unknown_shipping_count = unknown_shipping
        self.unknown_warranty_count = unknown_warranty
        self.blocker_reasons = blockers or []
        self.warning_reasons = warnings or []


class FakeCatalogCompleteness:
    readiness_score = 0.72
    duplicate_risk_categories = ["RAM"]
    weak_categories = ["Motherboard", "RAM", "Storage"]
    not_ready_categories = ["Motherboard"]
    build_critical_categories = [
        FakeCoverage("CPU", "ready", trusted=2),
        FakeCoverage("GPU", "ready", trusted=2, stale=1),
        FakeCoverage("Motherboard", "not_ready", blockers=["No trusted B650 motherboard URLs."]),
        FakeCoverage("RAM", "usable_with_warnings", trusted=1, unknown_vat=2, unknown_shipping=2, warnings=["VAT and shipping unclear."]),
        FakeCoverage("Storage", "usable_with_warnings", trusted=1, unknown_warranty=3, warnings=["Warranty unclear."]),
        FakeCoverage("PSU", "ready", trusted=2),
        FakeCoverage("Case", "ready", trusted=1),
        FakeCoverage("Cooler", "ready", trusted=1),
    ]
    non_critical_categories: list[FakeCoverage] = []


class FakeProduct:
    def __init__(
        self,
        *,
        name: str,
        vendor: str,
        price: float | None,
        level: str = "recommended",
        flags: list[str] | None = None,
        stale: bool = False,
        canonical_key: str | None = None,
    ) -> None:
        self.name = name
        self.current_recommended_vendor = vendor
        self.current_best_vendor = vendor
        self.lowest_market_vendor = vendor
        self.current_recommended_price = price
        self.recommended_level = level
        self.current_recommended_marketplace_risk_score = 0.2
        self.stale = stale
        self.price_status = "stale" if stale else "active"
        self.flags = flags or []
        self.canonical_key = canonical_key or name.upper().replace(" ", "_")
        self.current_price_timestamp = "2026-05-12T00:00:00Z"


class FakePricingRepositoryForGrowth:
    def product_categories(self):
        return ["CPU", "GPU", "Motherboard", "RAM", "Storage", "PSU", "Case", "Cooler"]

    def search_products(self, *, q="", category=None, region=None, limit=25):
        products = {
            "Motherboard": [
                FakeProduct(name="ASUS PRIME B650M-A WIFI II", vendor="PCZone Saudi", price=729, flags=["shipping_unknown"]),
            ],
            "RAM": [
                FakeProduct(name="DDR5 32GB 6000", vendor="Microless Saudi", price=449, flags=["vat_unknown", "shipping_unknown"]),
                FakeProduct(name="DDR5 32GB 6000 RGB", vendor="Microless Saudi", price=499, flags=["warranty_unknown"]),
            ],
            "Storage": [
                FakeProduct(name="2TB NVMe PCIe 4.0", vendor="Noon Saudi", price=399, level="acceptable_with_risk", flags=["warranty_unknown"]),
            ],
            "GPU": [
                FakeProduct(name="RTX 4070 Super", vendor="PCZone Saudi", price=2799, stale=True),
                FakeProduct(name="RTX 4070", vendor="PCZone Saudi", price=2399),
            ],
            "CPU": [FakeProduct(name="Ryzen 7 7800X3D", vendor="PCZone Saudi", price=1699)],
            "PSU": [FakeProduct(name="850W Gold PSU", vendor="MTC KSA", price=599)],
            "Case": [FakeProduct(name="airflow ATX case", vendor="PCZone Saudi", price=399)],
            "Cooler": [FakeProduct(name="AM5 air cooler", vendor="PCZone Saudi", price=199)],
        }
        rows = products.get(category or "", [])
        if q:
            rows = [item for item in rows if q.split()[0].lower() in item.name.lower()] or rows[:1]
        return rows[:limit]


class GrowthService(LaunchInsightsService):
    def _catalog_completeness(self, *, region: str):
        return FakeCatalogCompleteness()


def test_analytics_event_creation_sanitizes_sensitive_metadata() -> None:
    store = LaunchAnalyticsStore()

    event = store.record_event(
        AnalyticsEventCreate(
            event_type="build_generation",
            region="SA",
            anonymous_session_id="guest-123456",
            budget_sar=6000,
            metadata={
                "missing_categories": ["Motherboard"],
                "email": "buyer@example.com",
                "raw_url": "https://example.test/product?token=secret",
                "safe": "kept",
            },
        )
    )

    assert event.event_type == "build_generation"
    assert event.metadata["safe"] == "kept"
    assert "email" not in event.metadata
    assert "raw_url" not in event.metadata


def test_feedback_submission_validation_and_storage() -> None:
    store = LaunchAnalyticsStore()

    feedback = store.submit_feedback(
        FeedbackSubmissionCreate(
            type="wrong_price",
            region="SA",
            product_id="public-gpu",
            notes="Price is no longer available.",
            anonymous_session_id="guest-123456",
        )
    )

    assert feedback.status == "new"
    assert store.feedback(region="SA")[0].feedback_id == feedback.feedback_id
    missing_product = store.submit_feedback(
        FeedbackSubmissionCreate(
            type="missing_product",
            region="SA",
            notes="Please add more B650 motherboard options.",
            anonymous_session_id="guest-abcdef",
        )
    )
    confusing_warning = store.submit_feedback(
        FeedbackSubmissionCreate(
            type="confusing_warning",
            region="SA",
            notes="The warranty warning needs a clearer next step.",
            anonymous_session_id="guest-ghijkl",
        )
    )
    assert missing_product.type == "missing_product"
    assert confusing_warning.type == "confusing_warning"
    with pytest.raises(ValidationError):
        FeedbackSubmissionCreate(type="wrong_price", region="SA", notes="bad")


def test_build_failure_summary_counts_missing_and_budget_causes() -> None:
    store = LaunchAnalyticsStore()
    store.record_event(
        AnalyticsEventCreate(
            event_type="incomplete_build_generation",
            region="SA",
            anonymous_session_id="guest-123456",
            build_status="incomplete_data",
            metadata={"missing_categories": ["Motherboard", "RAM"], "uncertain_categories": ["Storage"]},
        )
    )
    store.record_event(
        AnalyticsEventCreate(
            event_type="over_budget_build",
            region="SA",
            anonymous_session_id="guest-123456",
            build_status="ready",
            budget_sar=6000,
            metadata={"over_budget_categories": ["GPU"], "substitution_categories": ["GPU", "CPU"]},
        )
    )

    summary = LaunchInsightsService(store).build_failure_summary(region="SA")

    assert summary.top_missing_categories[0] == {"name": "Motherboard", "count": 1}
    assert summary.top_over_budget_causes[0] == {"name": "GPU", "count": 1}
    assert {"name": "GPU", "count": 1} in summary.most_common_substitution_suggestions


def test_founder_insights_and_mvp_dashboard_are_safe_without_graph() -> None:
    store = LaunchAnalyticsStore()
    store.record_event(
        AnalyticsEventCreate(
            event_type="build_generation",
            region="SA",
            anonymous_session_id="guest-123456",
            category="GPU",
            budget_sar=6000,
        )
    )
    store.record_event(
        AnalyticsEventCreate(
            event_type="failed_build_generation",
            region="SA",
            anonymous_session_id="guest-123456",
            build_status="no_budget_fit",
            budget_sar=6000,
        )
    )
    store.submit_feedback(
        FeedbackSubmissionCreate(type="bad_vendor_listing", region="SA", notes="Vendor data looks wrong.")
    )

    service = LaunchInsightsService(store)
    dashboard = service.mvp_health_dashboard(region="SA")
    runtime = service.runtime_health()

    assert dashboard.active_users_today == 1
    assert dashboard.builds_generated == 1
    assert dashboard.builds_failing == 1
    assert dashboard.feedback_pending == 1
    assert dashboard.founder_insights.common_budget_ranges
    assert runtime.status in {"healthy", "watch", "degraded"}


def test_deployment_checklist_reports_status_without_secret_values() -> None:
    service = LaunchInsightsService(LaunchAnalyticsStore())

    checklist = service.deployment_checklist(
        settings=FakeSettings(),
        neo4j_connected=True,
        neo4j_detail=None,
        source_config=[],
        build_readiness=FakeReadiness(),
        region="SA",
    )
    payload = checklist.model_dump_json()

    assert checklist.launch_ready is True
    assert checklist.version_info["backend_version"] == "0.1.0"
    assert checklist.version_info["environment"] == "production"
    assert all(item.name != "NEO4J_PASSWORD" or item.configured for item in checklist.env_completeness)
    assert "super-secret-password" not in payload
    assert "analyst-secret" not in payload
    assert "admin-secret" not in payload


def test_deployment_checklist_blocks_missing_required_env_and_neo4j() -> None:
    class MissingSettings(FakeSettings):
        neo4j_password = ""
        admin_api_key = ""

    service = LaunchInsightsService(LaunchAnalyticsStore())

    checklist = service.deployment_checklist(
        settings=MissingSettings(),
        neo4j_connected=False,
        neo4j_detail="connection failed",
        source_config=[],
        build_readiness=None,
        region="SA",
    )

    assert checklist.launch_ready is False
    assert "Neo4j is not connected." in checklist.deployment_blockers
    assert any("NEO4J_PASSWORD" in blocker for blocker in checklist.deployment_blockers)


def test_deployment_checklist_rejects_production_placeholders_and_keeps_free_mode_optional_sources() -> None:
    class PlaceholderSettings(FakeSettings):
        neo4j_uri = "neo4j+s://your-aura-instance.databases.neo4j.io"
        neo4j_password = "replace-with-platform-secret"
        frontend_url = "https://your-domain.example"
        backend_url = "https://api.your-domain.example"
        cors_origins = ("http://localhost:3000",)
        analyst_api_key = "replace-with-platform-secret"
        admin_api_key = "replace-with-platform-secret"
        super_admin_api_key = "replace-with-platform-secret"
        market_data_mode = "free"

    service = LaunchInsightsService(LaunchAnalyticsStore())

    checklist = service.deployment_checklist(
        settings=PlaceholderSettings(),
        neo4j_connected=True,
        neo4j_detail=None,
        source_config=[],
        build_readiness=FakeReadiness(),
        region="SA",
    )

    assert checklist.launch_ready is False
    assert any("NEO4J_URI" in blocker for blocker in checklist.deployment_blockers)
    assert any("CORS_ORIGINS" in blocker for blocker in checklist.deployment_blockers)
    assert not any("SERPAPI_KEY" in blocker for blocker in checklist.deployment_blockers)


def test_catalog_growth_workflow_generates_priorities_actions_and_url_targets() -> None:
    store = LaunchAnalyticsStore()
    store.record_event(
        AnalyticsEventCreate(
            event_type="incomplete_build_generation",
            region="SA",
            category="Motherboard",
            metadata={"missing_categories": ["Motherboard"]},
        )
    )
    store.record_event(
        AnalyticsEventCreate(
            event_type="over_budget_build",
            region="SA",
            category="GPU",
            metadata={"over_budget_categories": ["GPU"], "substitution_categories": ["GPU"]},
        )
    )
    service = GrowthService(store, pricing_repository=FakePricingRepositoryForGrowth())

    workflow = service.catalog_growth_workflow(region="SA")

    assert workflow.category_priorities[0].category in {"Motherboard", "GPU", "RAM"}
    assert workflow.founder_action_queue
    assert any("B650" in product for item in workflow.founder_action_queue for product in item.recommended_products_to_add)
    assert workflow.most_needed_urls
    assert workflow.top_blockers


def test_store_quality_scores_and_family_coverage_are_generated() -> None:
    service = GrowthService(LaunchAnalyticsStore(), pricing_repository=FakePricingRepositoryForGrowth())

    workflow = service.catalog_growth_workflow(region="SA")

    assert any(item.store_name == "PCZone Saudi" for item in workflow.store_quality_scores)
    assert any(item.family == "RTX 4070" for item in workflow.product_family_coverage)
    assert workflow.readiness_trends[0].readiness_score == 0.72
