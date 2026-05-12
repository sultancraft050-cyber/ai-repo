from __future__ import annotations

from collections import Counter, deque
from datetime import UTC, datetime, timedelta
import os
from threading import Lock
from typing import Any

from app.models.launch import (
    AnalyticsEventCreate,
    AnalyticsEventView,
    BuildFailureSummary,
    CatalogGrowthWorkflowSummary,
    CategoryPriorityScore,
    DeploymentChecklist,
    DeploymentEnvCheck,
    FeedbackSubmissionCreate,
    FeedbackSubmissionView,
    FounderActionQueueItem,
    FounderInsightsSummary,
    MarketCoverageSummary,
    MarketCoverageTrendPoint,
    MvpHealthDashboard,
    ProductFamilyCoverage,
    RuntimeHealthSummary,
    StoreCoverageQuality,
)
from app.services.performance_observer import performance_observer


SENSITIVE_METADATA_KEYS = {
    "email",
    "user_email",
    "api_key",
    "secret",
    "token",
    "trace_id",
    "audit_id",
    "audit_event_id",
    "internal_audit_ids",
    "raw_url",
    "url",
}

REQUIRED_DEPLOYMENT_ENV = (
    ("NEO4J_URI", False),
    ("NEO4J_USER", False),
    ("NEO4J_PASSWORD", False),
    ("NEO4J_DATABASE", False),
    ("FRONTEND_URL", True),
    ("BACKEND_URL", True),
    ("CORS_ORIGINS", True),
    ("AUTH_REQUIRED", False),
    ("ANALYST_API_KEY", False),
    ("ADMIN_API_KEY", False),
    ("SUPER_ADMIN_API_KEY", False),
)

OPTIONAL_SOURCE_ENV = (
    "SERPAPI_KEY",
    "EBAY_BROWSE_TOKEN",
    "BESTBUY_API_KEY",
    "AMAZON_PAAPI_ACCESS_KEY",
    "AMAZON_PAAPI_SECRET_KEY",
    "AMAZON_PAAPI_PARTNER_TAG",
)

TARGET_PRODUCT_FAMILIES: dict[str, list[str]] = {
    "GPU": ["RTX 4070", "RTX 4070 Super", "RX 7800 XT"],
    "CPU": ["Ryzen 5 7600", "Ryzen 5 7500F", "Ryzen 7 7800X3D"],
    "Motherboard": ["B650 AM5 DDR5 ATX", "B650 mATX"],
    "RAM": ["DDR5 32GB 6000"],
    "Storage": ["2TB NVMe PCIe 4.0"],
    "PSU": ["750W Gold", "850W Gold"],
    "Case": ["airflow ATX case"],
    "Cooler": ["240mm AIO", "AM5 air cooler"],
}

DEPENDENCY_WEIGHTS: dict[str, float] = {
    "GPU": 1.0,
    "CPU": 0.95,
    "Motherboard": 0.95,
    "PSU": 0.85,
    "RAM": 0.8,
    "Storage": 0.75,
    "Cooler": 0.7,
    "Case": 0.65,
}

SUGGESTED_STORE_TARGETS = ["PCZone Saudi", "Microless Saudi", "MTC KSA", "Noon Saudi", "Amazon.sa"]


class LaunchAnalyticsStore:
    def __init__(self, *, max_events: int = 3000, max_feedback: int = 1000) -> None:
        self._lock = Lock()
        self._events: deque[AnalyticsEventView] = deque(maxlen=max_events)
        self._feedback: deque[FeedbackSubmissionView] = deque(maxlen=max_feedback)

    def record_event(self, request: AnalyticsEventCreate) -> AnalyticsEventView:
        payload = request.model_dump()
        payload["metadata"] = _safe_metadata(request.metadata)
        event = AnalyticsEventView(**payload)
        with self._lock:
            self._events.append(event)
        return event

    def submit_feedback(self, request: FeedbackSubmissionCreate) -> FeedbackSubmissionView:
        feedback = FeedbackSubmissionView(**request.model_dump())
        with self._lock:
            self._feedback.append(feedback)
        return feedback

    def events(self, *, region: str | None = None, limit: int = 500) -> list[AnalyticsEventView]:
        with self._lock:
            events = list(self._events)
        if region:
            events = [event for event in events if event.region == region]
        return events[-limit:]

    def feedback(self, *, region: str | None = None, limit: int = 200) -> list[FeedbackSubmissionView]:
        with self._lock:
            feedback = list(self._feedback)
        if region:
            feedback = [item for item in feedback if item.region == region]
        return feedback[-limit:]


def record_launch_event(app_state: Any, request: AnalyticsEventCreate) -> AnalyticsEventView:
    event = app_state.launch_analytics.record_event(request)
    try:
        manager = getattr(app_state, "neo4j", None)
        if manager and manager.unavailable_reason is None:
            from app.graph.ops_repository import Neo4jOpsRepository

            Neo4jOpsRepository(manager.driver).create_analytics_event(event)
    except Exception:
        pass
    return event


def record_feedback_submission(app_state: Any, request: FeedbackSubmissionCreate) -> FeedbackSubmissionView:
    feedback = app_state.launch_analytics.submit_feedback(request)
    try:
        manager = getattr(app_state, "neo4j", None)
        if manager and manager.unavailable_reason is None:
            from app.graph.ops_repository import Neo4jOpsRepository

            Neo4jOpsRepository(manager.driver).create_feedback_submission(feedback)
    except Exception:
        pass
    return feedback


class LaunchInsightsService:
    def __init__(self, store: LaunchAnalyticsStore, *, pricing_repository=None, ops_service=None) -> None:
        self.store = store
        self.pricing_repository = pricing_repository
        self.ops_service = ops_service

    def build_failure_summary(self, *, region: str = "SA") -> BuildFailureSummary:
        events = self.store.events(region=region, limit=1000)
        missing_counter: Counter[str] = Counter()
        over_budget_counter: Counter[str] = Counter()
        substitutions_counter: Counter[str] = Counter()
        uncertainty_counter: Counter[str] = Counter()
        for event in events:
            metadata = event.metadata or {}
            for category in _string_list(metadata.get("missing_categories")):
                missing_counter[category] += 1
            for category in _string_list(metadata.get("over_budget_categories")):
                over_budget_counter[category] += 1
            for category in _string_list(metadata.get("substitution_categories")):
                substitutions_counter[category] += 1
            for category in _string_list(metadata.get("uncertain_categories")):
                uncertainty_counter[category] += 1
        weak_categories = self._weak_categories(region=region)
        return BuildFailureSummary(
            region=region,
            top_missing_categories=_counter_rows(missing_counter),
            top_over_budget_causes=_counter_rows(over_budget_counter),
            most_common_substitution_suggestions=_counter_rows(substitutions_counter),
            categories_with_weak_saudi_coverage=weak_categories,
            categories_with_highest_uncertainty=[item for item, _ in uncertainty_counter.most_common(8)] or weak_categories[:8],
        )

    def market_coverage_summary(self, *, region: str = "SA") -> MarketCoverageSummary:
        product_count_per_category: dict[str, int] = {}
        trusted = 0
        risky = 0
        stale = 0
        weak_categories = self._weak_categories(region=region)
        duplicate_risk = 0
        if self.pricing_repository:
            try:
                for category in self.pricing_repository.product_categories():
                    products = self.pricing_repository.search_products(q="", category=category, region=region, limit=80)
                    if not products:
                        continue
                    product_count_per_category[category] = len(products)
                    trusted += len(
                        [
                            product
                            for product in products
                            if product.recommended_level in {"recommended", "good_if_price_matters", "acceptable_with_risk"}
                            and product.current_recommended_price is not None
                        ]
                    )
                    risky += len(
                        [
                            product
                            for product in products
                            if product.current_recommended_marketplace_risk_score
                            and product.current_recommended_marketplace_risk_score >= 0.65
                        ]
                    )
                    stale += len([product for product in products if product.stale or product.price_status == "stale"])
                    canonical_keys = [product.canonical_key for product in products if product.canonical_key]
                    duplicate_risk += max(0, len(canonical_keys) - len(set(canonical_keys)))
            except Exception:
                product_count_per_category = {}
        missing_category_count = len([category for category in self._required_categories() if category not in product_count_per_category])
        return MarketCoverageSummary(
            region=region,
            product_count_per_category=product_count_per_category,
            trusted_saudi_listing_count=trusted,
            risky_listing_count=risky,
            stale_listing_count=stale,
            missing_category_count=missing_category_count,
            duplicate_risk_count=duplicate_risk,
            weak_categories=weak_categories,
        )

    def catalog_growth_workflow(self, *, region: str = "SA") -> CatalogGrowthWorkflowSummary:
        failure_summary = self.build_failure_summary(region=region)
        completeness = self._catalog_completeness(region=region)
        coverage_by_category = {
            item.category: item
            for item in [
                *(getattr(completeness, "build_critical_categories", []) if completeness else []),
                *(getattr(completeness, "non_critical_categories", []) if completeness else []),
            ]
        }
        demand_counter = Counter(event.category for event in self.store.events(region=region, limit=1000) if event.category)
        missing_counter = _rows_to_counter(failure_summary.top_missing_categories)
        over_budget_counter = _rows_to_counter(failure_summary.top_over_budget_causes)
        priorities = [
            self._category_priority(
                category=category,
                coverage=coverage_by_category.get(category),
                demand=int(demand_counter.get(category, 0)),
                failure_frequency=int(missing_counter.get(category, 0) + over_budget_counter.get(category, 0)),
                duplicate_risk=category in (getattr(completeness, "duplicate_risk_categories", []) if completeness else []),
            )
            for category in self._required_categories()
        ]
        priorities = sorted(priorities, key=lambda item: item.score, reverse=True)
        action_queue = [self._founder_action(item) for item in priorities[:6] if item.score >= 20]
        families = self._product_family_coverage(region=region)
        stores = self._store_quality_scores(region=region)
        trends = self._readiness_trends(region=region, completeness=completeness)
        most_needed_urls = [
            f"{item.category}: {product}"
            for item in action_queue[:5]
            for product in item.recommended_products_to_add[:2]
        ][:10]
        top_blockers = [
            item.recommended_next_action
            for item in priorities[:5]
            if item.readiness_level != "ready" or item.uncertainty_level != "low"
        ]
        return CatalogGrowthWorkflowSummary(
            region=region,
            category_priorities=priorities,
            founder_action_queue=action_queue,
            product_family_coverage=families,
            store_quality_scores=stores,
            build_blocker_summary=failure_summary,
            readiness_trends=trends,
            top_blockers=top_blockers,
            most_needed_urls=most_needed_urls,
            message=(
                "Founder action queue is ready. Add targeted URLs for the highest-priority categories first."
                if action_queue
                else "Catalog growth data is sparse; collect more build and feedback activity before expanding coverage."
            ),
        )

    def runtime_health(self) -> RuntimeHealthSummary:
        performance = performance_observer.performance_summary()
        query = performance_observer.query_performance()
        build_latency = float(performance.get("average_build_generation_latency_ms") or 0)
        graph_latency = float(performance.get("average_graph_query_latency_ms") or 0)
        status = "healthy"
        notes: list[str] = []
        if build_latency > 2500 or graph_latency > 800:
            status = "watch"
            notes.append("Runtime latency is elevated; inspect slow endpoints and graph query telemetry.")
        if not performance.get("top_expensive_endpoints"):
            notes.append("Runtime telemetry is sparse until real traffic arrives.")
        return RuntimeHealthSummary(
            status=status,  # type: ignore[arg-type]
            build_generation_latency_ms=build_latency,
            slow_endpoints=list(performance.get("top_expensive_endpoints") or []),
            graph_query_latency_ms=graph_latency,
            frontend_payload_size_bytes=dict(performance.get("frontend_payload_sizes") or {}),
            refresh_success_failure=dict(performance.get("refresh_success_failure") or {}),
            notes=notes,
        )

    def founder_insights(self, *, region: str = "SA") -> FounderInsightsSummary:
        events = self.store.events(region=region, limit=1000)
        category_counter: Counter[str] = Counter()
        budget_counter: Counter[str] = Counter()
        failure_counter: Counter[str] = Counter()
        for event in events:
            if event.category:
                category_counter[event.category] += 1
            if event.budget_sar:
                budget_counter[_budget_bucket(event.budget_sar)] += 1
            if event.event_type in {"failed_build_generation", "incomplete_build_generation"}:
                failure_counter[event.build_status or "unknown_failure"] += 1
        failure_summary = self.build_failure_summary(region=region)
        recommended_next = (
            failure_summary.top_missing_categories[0]["name"]
            if failure_summary.top_missing_categories
            else (failure_summary.categories_with_weak_saudi_coverage[0] if failure_summary.categories_with_weak_saudi_coverage else None)
        )
        action_items = []
        if recommended_next:
            action_items.append(f"Improve {recommended_next} coverage next; it appears most often in build blockers or weak coverage.")
        if failure_summary.top_over_budget_causes:
            action_items.append("Add cheaper compatible Saudi alternatives for the most common over-budget categories.")
        if not events:
            action_items.append("Collect launch traffic before changing scoring weights.")
        return FounderInsightsSummary(
            region=region,
            recommended_next_category=recommended_next,
            weak_vendor_coverage=failure_summary.categories_with_weak_saudi_coverage[:8],
            most_requested_categories=_counter_rows(category_counter),
            common_budget_ranges=_counter_rows(budget_counter),
            most_common_failure_modes=_counter_rows(failure_counter),
            action_items=action_items,
        )

    def mvp_health_dashboard(self, *, region: str = "SA") -> MvpHealthDashboard:
        events = self.store.events(region=region, limit=1000)
        feedback = self.store.feedback(region=region, limit=1000)
        since = datetime.now(UTC) - timedelta(days=1)
        active_sessions = {
            event.anonymous_session_id or event.user_id
            for event in events
            if event.timestamp >= since and (event.anonymous_session_id or event.user_id)
        }
        failure = self.build_failure_summary(region=region)
        coverage = self.market_coverage_summary(region=region)
        insights = self.founder_insights(region=region)
        source_health = []
        if self.ops_service:
            try:
                source_health = [item.model_dump(mode="json") for item in self.ops_service.source_health()]
            except Exception:
                source_health = []
        total_required = max(len(self._required_categories()), 1)
        covered_required = len([category for category in self._required_categories() if category in coverage.product_count_per_category])
        return MvpHealthDashboard(
            region=region,
            active_users_today=len(active_sessions),
            builds_generated=len([event for event in events if event.event_type == "build_generation"]),
            builds_failing=len(
                [
                    event
                    for event in events
                    if event.event_type in {"failed_build_generation", "incomplete_build_generation"}
                ]
            ),
            top_categories_searched=_counter_rows(Counter(event.category for event in events if event.category)),
            top_missing_categories=failure.top_missing_categories,
            stale_pricing_count=coverage.stale_listing_count,
            saudi_coverage_percent=round(covered_required / total_required * 100, 1),
            source_health=source_health,
            watchlist_activity=len([event for event in events if event.event_type == "watchlist_add"]),
            deal_submissions_pending=len([event for event in events if event.event_type == "deal_submission"]),
            feedback_pending=len([item for item in feedback if item.status == "new"]),
            founder_insights=insights,
        )

    def deployment_checklist(
        self,
        *,
        settings,
        neo4j_connected: bool,
        neo4j_detail: str | None,
        source_config: list[Any],
        build_readiness: Any | None,
        region: str = "SA",
    ) -> DeploymentChecklist:
        env_checks = _deployment_env_checks(settings)
        runtime = self.runtime_health()
        blockers = [
            f"Missing required environment variable: {item.name}"
            for item in env_checks
            if item.required and not item.configured
        ]
        if not neo4j_connected:
            blockers.append("Neo4j is not connected.")
        readiness_payload: dict[str, Any] = {"status": "unavailable"}
        if build_readiness is not None:
            readiness_payload = {
                "region": getattr(build_readiness, "region", region),
                "readiness_score": getattr(build_readiness, "readiness_score", 0),
                "enough_data_for_full_build": bool(getattr(build_readiness, "enough_data_for_full_build", False)),
                "missing_categories": list(getattr(build_readiness, "missing_categories", []) or []),
                "message": getattr(build_readiness, "message", "Build readiness unavailable."),
            }
            if not readiness_payload["enough_data_for_full_build"]:
                blockers.append("Saudi build readiness is not complete.")
        source_payload = [
            {
                "source_name": getattr(item, "source_name", "unknown"),
                "configured": bool(getattr(item, "configured", False)),
                "health": getattr(item, "health", "unknown"),
                "source_kind": getattr(item, "source_kind", "unknown"),
                "direct_access_enabled": bool(getattr(item, "direct_access_enabled", False)),
            }
            for item in source_config
        ]
        if getattr(settings, "market_data_mode", "free") == "free":
            blockers = [
                blocker
                for blocker in blockers
                if not blocker.startswith("Missing required environment variable: SERPAPI_KEY")
            ]
        return DeploymentChecklist(
            environment=getattr(settings, "environment", "development"),
            market_data_mode=getattr(settings, "market_data_mode", "free"),
            version_info=_deployment_version_info(settings),
            env_completeness=env_checks,
            neo4j_connectivity={
                "ok": neo4j_connected,
                "status": "connected" if neo4j_connected else "unavailable",
                "detail": neo4j_detail if not neo4j_connected else None,
            },
            source_configuration_status=source_payload,
            build_readiness_status=readiness_payload,
            runtime_health=runtime,
            deployment_blockers=blockers,
            launch_ready=not blockers,
        )

    def _weak_categories(self, *, region: str) -> list[str]:
        if not self.pricing_repository:
            return []
        try:
            from app.services.saudi_build_generator import SaudiLocalBuildService

            completeness = SaudiLocalBuildService(self.pricing_repository).catalog_completeness(region=region)
            return list(dict.fromkeys([*completeness.weak_categories, *completeness.not_ready_categories]))[:12]
        except Exception:
            return []

    def _required_categories(self) -> list[str]:
        return ["CPU", "GPU", "Motherboard", "RAM", "Storage", "PSU", "Case", "Cooler"]

    def _catalog_completeness(self, *, region: str):
        if not self.pricing_repository:
            return None
        try:
            from app.services.saudi_build_generator import SaudiLocalBuildService

            return SaudiLocalBuildService(self.pricing_repository).catalog_completeness(region=region)
        except Exception:
            return None

    def _category_priority(self, *, category: str, coverage: Any, demand: int, failure_frequency: int, duplicate_risk: bool) -> CategoryPriorityScore:
        readiness = getattr(coverage, "readiness_level", "not_ready") if coverage else "not_ready"
        trusted = int(getattr(coverage, "trusted_local_listing_count", 0) or 0) if coverage else 0
        stale = int(getattr(coverage, "stale_listing_count", 0) or 0) if coverage else 0
        uncertainty_count = 0
        blockers: list[str] = []
        if coverage:
            uncertainty_count = int(getattr(coverage, "unknown_vat_count", 0) or 0)
            uncertainty_count += int(getattr(coverage, "unknown_shipping_count", 0) or 0)
            uncertainty_count += int(getattr(coverage, "unknown_warranty_count", 0) or 0)
            blockers = list(getattr(coverage, "blocker_reasons", []) or [])
            blockers.extend(getattr(coverage, "warning_reasons", []) or [])
        else:
            blockers.append("No category coverage data is available.")
        dependency = DEPENDENCY_WEIGHTS.get(category, 0.5)
        readiness_penalty = {"not_ready": 42, "usable_with_warnings": 22, "ready": 0}.get(str(readiness), 42)
        score = readiness_penalty
        score += dependency * 22
        score += min(16, demand * 2)
        score += min(18, failure_frequency * 4)
        score += min(10, stale * 2)
        score += 8 if duplicate_risk else 0
        score += min(14, uncertainty_count * 1.5)
        score -= min(16, trusted * 3)
        uncertainty = "high" if uncertainty_count >= 5 or readiness == "not_ready" else "medium" if uncertainty_count else "low"
        return CategoryPriorityScore(
            category=category,
            score=round(max(0, min(100, score)), 2),
            readiness_level=readiness,  # type: ignore[arg-type]
            build_dependency_weight=dependency,
            user_search_demand=demand,
            build_failure_frequency=failure_frequency,
            trusted_saudi_listing_count=trusted,
            stale_listing_count=stale,
            duplicate_risk=duplicate_risk,
            uncertainty_level=uncertainty,  # type: ignore[arg-type]
            blocker_reasons=list(dict.fromkeys(blockers))[:6],
            recommended_next_action=_category_next_action(category, readiness, uncertainty),
        )

    def _founder_action(self, priority: CategoryPriorityScore) -> FounderActionQueueItem:
        families = TARGET_PRODUCT_FAMILIES.get(priority.category, [priority.category])
        stores = SUGGESTED_STORE_TARGETS[:3] if priority.category in {"Motherboard", "RAM", "Storage", "PSU"} else SUGGESTED_STORE_TARGETS
        return FounderActionQueueItem(
            category=priority.category,
            recommended_products_to_add=families[:4],
            reason="; ".join(priority.blocker_reasons[:2]) or priority.recommended_next_action,
            expected_impact=_expected_impact(priority),
            suggested_store_targets=stores,
            estimated_improvement=_estimated_improvement(priority),
        )

    def _product_family_coverage(self, *, region: str) -> list[ProductFamilyCoverage]:
        if not self.pricing_repository:
            return []
        rows: list[ProductFamilyCoverage] = []
        for category, families in TARGET_PRODUCT_FAMILIES.items():
            for family in families:
                try:
                    products = self.pricing_repository.search_products(q=family, category=category, region=region, limit=12)
                except Exception:
                    products = []
                trusted_prices = [
                    product.current_recommended_price
                    for product in products
                    if product.current_recommended_price is not None
                    and product.recommended_level in {"recommended", "good_if_price_matters", "acceptable_with_risk"}
                ]
                uncertainty = "high"
                if len(trusted_prices) >= 2:
                    uncertainty = "low"
                elif trusted_prices:
                    uncertainty = "medium"
                timestamps = [str(product.current_price_timestamp) for product in products if product.current_price_timestamp]
                rows.append(
                    ProductFamilyCoverage(
                        category=category,
                        family=family,
                        saudi_coverage_percent=round(min(100, len(products) / 3 * 100), 1),
                        trusted_listing_count=len(trusted_prices),
                        cheapest_trusted_listing_sar=min(trusted_prices) if trusted_prices else None,
                        uncertainty_level=uncertainty,  # type: ignore[arg-type]
                        last_updated=max(timestamps) if timestamps else None,
                    )
                )
        return rows

    def _store_quality_scores(self, *, region: str) -> list[StoreCoverageQuality]:
        if not self.pricing_repository:
            return []
        store_data: dict[str, dict[str, Any]] = {}
        for category in self._required_categories():
            try:
                products = self.pricing_repository.search_products(q="", category=category, region=region, limit=80)
            except Exception:
                products = []
            for product in products:
                store = product.current_recommended_vendor or product.current_best_vendor or product.lowest_market_vendor
                if not store:
                    continue
                data = store_data.setdefault(
                    store,
                    {"trusted": 0, "uncertain": 0, "stale": 0, "canonical": [], "strengths": set(), "weaknesses": set()},
                )
                if product.current_recommended_price is not None and product.recommended_level in {"recommended", "good_if_price_matters", "acceptable_with_risk"}:
                    data["trusted"] += 1
                    data["strengths"].add("usable Saudi listings")
                if product.stale or product.price_status == "stale":
                    data["stale"] += 1
                    data["weaknesses"].add("stale prices")
                if any(flag in product.flags for flag in ("vat_unknown", "shipping_unknown", "warranty_unknown")):
                    data["uncertain"] += 1
                    data["weaknesses"].add("VAT/shipping/warranty uncertainty")
                if product.canonical_key:
                    data["canonical"].append(product.canonical_key)
        scores: list[StoreCoverageQuality] = []
        for store, data in store_data.items():
            duplicate_issues = max(0, len(data["canonical"]) - len(set(data["canonical"])))
            score = 45 + data["trusted"] * 7 - data["uncertain"] * 4 - data["stale"] * 5 - duplicate_issues * 3
            scores.append(
                StoreCoverageQuality(
                    store_name=store,
                    score=round(max(0, min(100, score)), 2),
                    trusted_listing_count=int(data["trusted"]),
                    uncertainty_count=int(data["uncertain"]),
                    stale_url_count=int(data["stale"]),
                    duplicate_issue_count=duplicate_issues,
                    strengths=sorted(data["strengths"])[:4] or ["No strong quality signal yet"],
                    weaknesses=sorted(data["weaknesses"])[:4],
                )
            )
        return sorted(scores, key=lambda item: item.score, reverse=True)[:12]

    def _readiness_trends(self, *, region: str, completeness: Any | None) -> list[MarketCoverageTrendPoint]:
        events = self.store.events(region=region, limit=1000)
        success = len([event for event in events if event.event_type == "build_generation" and event.build_status == "ready"])
        failed = len([event for event in events if event.event_type in {"failed_build_generation", "incomplete_build_generation"}])
        total = success + failed
        warning_frequency = sum(len(_string_list(event.metadata.get("uncertain_categories"))) for event in events)
        readiness_score = float(getattr(completeness, "readiness_score", 0) or 0) if completeness else 0
        market = self.market_coverage_summary(region=region)
        return [
            MarketCoverageTrendPoint(
                label="current",
                build_success_rate=round(success / total, 2) if total else 0,
                readiness_score=readiness_score,
                warning_frequency=warning_frequency,
                trusted_listing_growth=market.trusted_saudi_listing_count,
                stale_listing_reduction=0,
            )
        ]


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        normalized_key = str(key).lower()
        if normalized_key in SENSITIVE_METADATA_KEYS or any(token in normalized_key for token in ("secret", "token", "email", "url")):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[str(key)] = value
        elif isinstance(value, list):
            clean[str(key)] = [str(item)[:120] for item in value[:20]]
        elif isinstance(value, dict):
            clean[str(key)] = {
                str(nested_key): str(nested_value)[:120]
                for nested_key, nested_value in value.items()
                if str(nested_key).lower() not in SENSITIVE_METADATA_KEYS
            }
    return clean


def _deployment_env_checks(settings) -> list[DeploymentEnvCheck]:
    values = {
        "NEO4J_URI": getattr(settings, "neo4j_uri", None),
        "NEO4J_USER": getattr(settings, "neo4j_user", None),
        "NEO4J_PASSWORD": getattr(settings, "neo4j_password", None),
        "NEO4J_DATABASE": getattr(settings, "neo4j_database", None),
        "FRONTEND_URL": getattr(settings, "frontend_url", None),
        "BACKEND_URL": getattr(settings, "backend_url", None),
        "CORS_ORIGINS": ",".join(getattr(settings, "cors_origins", ()) or ()),
        "AUTH_REQUIRED": str(getattr(settings, "auth_required", "")),
        "ANALYST_API_KEY": getattr(settings, "analyst_api_key", None),
        "ADMIN_API_KEY": getattr(settings, "admin_api_key", None),
        "SUPER_ADMIN_API_KEY": getattr(settings, "super_admin_api_key", None),
        "SERPAPI_KEY": getattr(settings, "serpapi_key", None),
        "EBAY_BROWSE_TOKEN": getattr(settings, "ebay_browse_token", None),
        "BESTBUY_API_KEY": getattr(settings, "bestbuy_api_key", None),
        "AMAZON_PAAPI_ACCESS_KEY": getattr(settings, "amazon_paapi_access_key", None),
        "AMAZON_PAAPI_SECRET_KEY": getattr(settings, "amazon_paapi_secret_key", None),
        "AMAZON_PAAPI_PARTNER_TAG": getattr(settings, "amazon_paapi_partner_tag", None),
    }
    checks: list[DeploymentEnvCheck] = []
    for name, public in REQUIRED_DEPLOYMENT_ENV:
        configured = _deployment_value_configured(name, values.get(name), settings)
        checks.append(
            DeploymentEnvCheck(
                name=name,
                required=True,
                configured=configured,
                public=public,
                status="ok" if configured else "missing",
                message="Configured." if configured else "Required for production deployment.",
            )
        )
    for name in OPTIONAL_SOURCE_ENV:
        configured = bool(values.get(name))
        checks.append(
            DeploymentEnvCheck(
                name=name,
                required=False,
                configured=configured,
                public=False,
                status="optional" if not configured else "ok",
                message=(
                    "Optional paid/source credential configured."
                    if configured
                    else "Optional; leave empty when MARKET_DATA_MODE=free or when this source is not used."
                ),
            )
        )
    return checks


def _deployment_value_configured(name: str, value: Any, settings) -> bool:
    if name == "AUTH_REQUIRED":
        return str(value).lower() in {"1", "true", "yes"}
    if not value:
        return False
    text = str(value).strip()
    if not text:
        return False
    if text in {"replace-with-platform-secret", "your-aura-instance.databases.neo4j.io"}:
        return False
    if name.endswith("_URL") and "your-domain.example" in text:
        return False
    if name == "NEO4J_URI" and text in {"bolt://localhost:7687", "neo4j+s://your-aura-instance.databases.neo4j.io"}:
        return getattr(settings, "environment", "development") != "production"
    if name == "NEO4J_PASSWORD" and text in {"neo4j-password", "password", "replace-with-platform-secret"}:
        return getattr(settings, "environment", "development") != "production"
    if name == "CORS_ORIGINS" and "localhost" in text and getattr(settings, "environment", "development") == "production":
        return False
    if name.endswith("_API_KEY") and text in {"replace-with-platform-secret", "change-me", "secret"}:
        return False
    return True


def _deployment_version_info(settings) -> dict[str, str | None]:
    git_sha = (
        os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("FLY_MACHINE_VERSION")
        or os.getenv("VERCEL_GIT_COMMIT_SHA")
        or os.getenv("GIT_SHA")
    )
    return {
        "backend_version": os.getenv("BACKEND_VERSION", "0.1.0"),
        "frontend_version": os.getenv("FRONTEND_VERSION"),
        "git_sha": git_sha[:12] if git_sha else None,
        "environment": getattr(settings, "environment", "development"),
        "backend_url": getattr(settings, "backend_url", None),
        "frontend_url": getattr(settings, "frontend_url", None),
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _counter_rows(counter: Counter[str], limit: int = 8) -> list[dict[str, int]]:
    return [{"name": name, "count": int(count)} for name, count in counter.most_common(limit) if name]


def _rows_to_counter(rows: list[dict[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        name = row.get("name")
        if name:
            counter[str(name)] += int(row.get("count") or 0)
    return counter


def _category_next_action(category: str, readiness: str, uncertainty: str) -> str:
    families = ", ".join(TARGET_PRODUCT_FAMILIES.get(category, [category])[:3])
    if readiness == "not_ready":
        return f"Add trusted Saudi product URLs for {families}."
    if uncertainty != "low":
        return f"Improve VAT, shipping, warranty, and condition evidence for {families}."
    return f"Maintain freshness for {families} and add budget alternatives only if users ask."


def _expected_impact(priority: CategoryPriorityScore) -> str:
    if priority.readiness_level == "not_ready":
        return "Can unblock failed Saudi builds and improve readiness score."
    if priority.uncertainty_level != "low":
        return "Can raise confidence and reduce visible market-data warnings."
    if priority.stale_listing_count:
        return "Can reduce stale-price warnings and improve buyer trust."
    return "Can improve choice depth and budget-fit flexibility."


def _estimated_improvement(priority: CategoryPriorityScore) -> str:
    if priority.score >= 75:
        return "High: likely moves build success or confidence noticeably."
    if priority.score >= 45:
        return "Medium: likely reduces warnings or improves budget-fit options."
    return "Low: useful maintenance, but not the first catalog priority."


def _budget_bucket(value: float) -> str:
    if value < 4000:
        return "under_4000_sar"
    if value < 6000:
        return "4000_5999_sar"
    if value < 8000:
        return "6000_7999_sar"
    if value < 10000:
        return "8000_9999_sar"
    return "10000_plus_sar"


def analytics_from_build_response(
    *,
    response,
    request_body,
    session_id: str | None,
    user_id: str | None,
) -> list[AnalyticsEventCreate]:
    events: list[AnalyticsEventCreate] = [
        AnalyticsEventCreate(
            event_type="build_generation",
            region=request_body.region,
            anonymous_session_id=session_id,
            user_id=user_id,
            build_status=response.build_status,
            budget_sar=request_body.budget_sar,
            metadata=_build_metadata(response),
        )
    ]
    if response.build_status == "incomplete_data":
        events.append(
            AnalyticsEventCreate(
                event_type="incomplete_build_generation",
                region=request_body.region,
                anonymous_session_id=session_id,
                user_id=user_id,
                build_status=response.build_status,
                budget_sar=request_body.budget_sar,
                metadata=_build_metadata(response),
            )
        )
    if response.build_status in {"no_valid_build", "no_budget_fit"}:
        events.append(
            AnalyticsEventCreate(
                event_type="failed_build_generation",
                region=request_body.region,
                anonymous_session_id=session_id,
                user_id=user_id,
                build_status=response.build_status,
                budget_sar=request_body.budget_sar,
                metadata=_build_metadata(response),
            )
        )
    if any(getattr(build.summary, "over_budget_amount_sar", 0) > 0 for build in response.builds):
        events.append(
            AnalyticsEventCreate(
                event_type="over_budget_build",
                region=request_body.region,
                anonymous_session_id=session_id,
                user_id=user_id,
                build_status=response.build_status,
                budget_sar=request_body.budget_sar,
                metadata=_build_metadata(response),
            )
        )
    return events


def _build_metadata(response) -> dict[str, Any]:
    missing_categories = list(getattr(response.data_completeness, "missing_categories", []) or [])
    over_budget_categories: list[str] = []
    substitution_categories: list[str] = []
    uncertain_categories: list[str] = []
    for build in getattr(response, "builds", []) or []:
        over_budget_categories.extend(
            component.category
            for component in getattr(build, "components", [])
            if getattr(build.summary, "over_budget_amount_sar", 0) > 0
        )
        substitution_categories.extend(
            suggestion.category for suggestion in getattr(build, "savings_suggestions", []) if suggestion.category
        )
        uncertain_categories.extend(getattr(build.summary, "components_with_uncertainty", []) or [])
    return {
        "missing_categories": missing_categories,
        "over_budget_categories": list(dict.fromkeys(over_budget_categories))[:8],
        "substitution_categories": list(dict.fromkeys(substitution_categories))[:8],
        "uncertain_categories": list(dict.fromkeys(str(item).split(":", 1)[0] for item in uncertain_categories))[:8],
        "recommended_discovery_categories": list(
            dict.fromkeys(job.category for job in getattr(response, "recommended_discovery_jobs", []) if job.category)
        )[:8],
    }
