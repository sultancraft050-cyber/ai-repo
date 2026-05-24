from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.api import (
    CatalogCompletenessResponse,
    CategoryCoverage,
    RecommendedDiscoveryJob,
    SaudiBuildComponent,
    SaudiBuildDataCompleteness,
    SaudiBuildComparisonItem,
    SaudiBuildOption,
    SaudiBuildRequest,
    SaudiBuildResponse,
    SaudiBuildSummary,
    SaudiBuildConfidenceBreakdown,
    SaudiBuildExplanation,
    SaudiBuildExport,
    SaudiComponentExplanation,
    SaudiNoBudgetFitGuidance,
    SaudiSavingsSuggestion,
    SaudiBuildValidationRequest,
    SaudiBuildValidationResponse,
)
from app.models.pricing import ProductSearchResult
from app.services.performance_observer import performance_observer


REQUIRED_BUILD_CATEGORIES = ["CPU", "GPU", "Motherboard", "RAM", "Storage", "PSU", "Case", "Cooler"]
OPTIONAL_MONITOR_CATEGORY = "Monitor"
OPTIONAL_PERIPHERAL_CATEGORIES = ["Keyboard", "Mouse", "Headset"]

DISCOVERY_QUERIES: dict[str, list[str]] = {
    "CPU": ["Ryzen 7 7800X3D processor", "Intel Core i5 14600K processor"],
    "GPU": ["RTX 4070 Super graphics card", "RTX 4060 Ti graphics card"],
    "Motherboard": ["B650 AM5 DDR5 ATX motherboard", "B760 DDR5 ATX motherboard"],
    "RAM": ["32GB DDR5 6000 RAM kit", "32GB DDR5 desktop memory"],
    "Storage": ["1TB NVMe PCIe 4 SSD", "2TB NVMe SSD"],
    "PSU": ["750W Gold PSU", "Corsair RM750e PSU", "850W Gold PSU"],
    "Case": ["ATX airflow PC case", "mATX airflow PC case"],
    "Cooler": ["AM5 CPU air cooler", "240mm AIO CPU cooler"],
    "Monitor": ["1440p 144Hz gaming monitor"],
    "Keyboard": ["mechanical gaming keyboard"],
    "Mouse": ["wireless gaming mouse"],
    "Headset": ["gaming headset"],
}

ALLOWED_BUDGET_SUBSTITUTIONS: dict[str, list[str]] = {
    "GPU": [
        "RTX 4070 Super",
        "RTX 4070",
        "RX 7800 XT",
        "RX 7700 XT",
        "RTX 4060 Ti 16GB",
    ],
    "CPU": ["Ryzen 7 7800X3D", "Ryzen 7 7700", "Ryzen 5 7600", "Ryzen 5 7500F"],
    "Motherboard": ["B650 ATX", "B650 mATX AM5 DDR5", "A620 AM5 DDR5"],
    "RAM": ["DDR5 32GB 6000", "DDR5 32GB 5600", "DDR5 16GB"],
    "Storage": ["2TB NVMe SSD", "1TB NVMe SSD", "SSD"],
    "PSU": ["850W Gold", "750W Gold"],
    "Case": ["ATX airflow case", "mATX airflow case"],
    "Cooler": ["240mm AIO", "AM5 air cooler"],
}

BUDGET_DISCOVERY_QUERIES: dict[str, list[str]] = {
    "GPU": [
        "RTX 4070 Super graphics card",
        "RTX 4070 graphics card",
        "RX 7800 XT graphics card",
        "RX 7700 XT graphics card",
        "RTX 4060 Ti 16GB graphics card",
    ],
    "CPU": ["Ryzen 7 7800X3D processor", "Ryzen 7 7700 processor", "Ryzen 5 7600 processor", "Ryzen 5 7500F processor"],
    "Motherboard": ["B650 ATX motherboard", "B650 mATX AM5 motherboard", "A620 AM5 motherboard"],
    "RAM": ["DDR5 32GB 6000 RAM kit", "DDR5 32GB 5600 RAM kit", "DDR5 16GB RAM kit"],
    "Storage": ["2TB NVMe SSD", "1TB NVMe SSD PCIe 4.0", "1TB NVMe SSD"],
    "PSU": ["850W Gold PSU", "750W Gold PSU"],
    "Case": ["ATX airflow case", "mATX airflow case"],
    "Cooler": ["240mm AIO CPU cooler", "AM5 air cooler"],
}

PERFORMANCE_WEIGHTS = {
    "CPU": 0.17,
    "GPU": 0.33,
    "Motherboard": 0.08,
    "RAM": 0.1,
    "Storage": 0.07,
    "PSU": 0.08,
    "Case": 0.07,
    "Cooler": 0.1,
}


@dataclass(frozen=True)
class ComponentPool:
    category: str
    products: list[ProductSearchResult]


class SaudiLocalBuildService:
    def __init__(self, pricing_repository: Neo4jPricingRepository) -> None:
        self.pricing_repository = pricing_repository
        self._category_product_cache: dict[tuple[str, str, int], list[ProductSearchResult]] = {}
        self._data_completeness_cache: dict[tuple[str, str], SaudiBuildDataCompleteness] = {}

    def data_completeness(self, *, region: str = "SA", city: str = "Riyadh") -> SaudiBuildDataCompleteness:
        if region != "SA":
            raise ValueError("Saudi local build generation currently supports region=SA only.")
        cache_key = (region, city)
        cached = self._data_completeness_cache.get(cache_key)
        if cached is not None:
            performance_observer.record_cache(hit=True)
            return cached
        performance_observer.record_cache(hit=False)
        coverages: list[CategoryCoverage] = []
        ready_categories: list[str] = []
        missing_categories: list[str] = []
        for category in REQUIRED_BUILD_CATEGORIES:
            products = self._category_products(category, region=region, limit=80)
            coverage = self._coverage_for_category(category, products)
            coverages.append(coverage)
            if coverage.readiness_level in {"ready", "usable_with_warnings"}:
                ready_categories.append(category)
            else:
                missing_categories.append(category)
        readiness_points = sum(
            1.0 if coverage.readiness_level == "ready" else 0.75 if coverage.readiness_level == "usable_with_warnings" else 0.0
            for coverage in coverages
        )
        readiness = round(readiness_points / len(REQUIRED_BUILD_CATEGORIES), 2)
        jobs = self._discovery_jobs(missing_categories, city=city)
        completeness = SaudiBuildDataCompleteness(
            region="SA",
            city=city,
            readiness_score=readiness,
            required_categories=list(REQUIRED_BUILD_CATEGORIES),
            ready_categories=ready_categories,
            missing_categories=missing_categories,
            category_coverage=coverages,
            recommended_discovery_jobs=jobs,
            enough_data_for_full_build=not missing_categories,
            message=(
                "Saudi data is sufficient for build generation."
                if not missing_categories
                else "Data needed before reliable Saudi build generation."
            ),
        )
        self._data_completeness_cache[cache_key] = completeness
        return completeness

    def catalog_completeness(self, *, region: str = "SA", city: str = "Riyadh") -> CatalogCompletenessResponse:
        if region != "SA":
            raise ValueError("Catalog completeness currently supports region=SA only.")
        build_critical = []
        for category in REQUIRED_BUILD_CATEGORIES:
            build_critical.append(self._coverage_for_category(category, self._category_products(category, region=region, limit=80)))

        known_categories = sorted(
            category
            for category in self.pricing_repository.product_categories()
            if category and category not in REQUIRED_BUILD_CATEGORIES
        )
        non_critical = [
            self._coverage_for_category(category, self._category_products(category, region=region, limit=40))
            for category in known_categories[:24]
        ]
        all_coverages = build_critical + non_critical
        readiness_points = sum(
            1.0 if coverage.readiness_level == "ready" else 0.75 if coverage.readiness_level == "usable_with_warnings" else 0
            for coverage in all_coverages
        )
        readiness_score = round(readiness_points / len(all_coverages), 2) if all_coverages else 0
        not_ready = [coverage.category for coverage in all_coverages if coverage.readiness_level == "not_ready"]
        weak = [
            coverage.category
            for coverage in all_coverages
            if coverage.readiness_level != "ready" or coverage.warning_reasons or coverage.stale_listing_count
        ]
        stale = [
            coverage.category
            for coverage in all_coverages
            if coverage.price_freshness_status in {"stale", "mixed"} or coverage.stale_listing_count
        ]
        duplicate_risk = self._duplicate_risk_categories(all_coverages, region=region)
        return CatalogCompletenessResponse(
            region=region,
            readiness_score=readiness_score,
            build_critical_categories=build_critical,
            non_critical_categories=non_critical,
            ready_categories=[coverage.category for coverage in all_coverages if coverage.readiness_level == "ready"],
            usable_with_warnings_categories=[
                coverage.category for coverage in all_coverages if coverage.readiness_level == "usable_with_warnings"
            ],
            not_ready_categories=not_ready,
            stale_categories=stale,
            weak_categories=weak,
            duplicate_risk_categories=duplicate_risk,
            next_actions=self._discovery_jobs(not_ready[:8], city=city),
            message=(
                "Catalog has enough Saudi build-critical data; weak categories still need quality work."
                if not any(coverage.readiness_level == "not_ready" for coverage in build_critical)
                else "Catalog still has Saudi build-critical blockers."
            ),
        )

    def generate_local(self, request: SaudiBuildRequest, *, trace_id: str | None = None) -> SaudiBuildResponse:
        started = perf_counter()
        completeness = self.data_completeness(region=request.region, city=request.city)
        missing_data_warnings = self._missing_warnings(completeness)
        if not completeness.enough_data_for_full_build:
            response = SaudiBuildResponse(
                region="SA",
                city=request.city,
                build_status="incomplete_data",
                builds=[],
                data_completeness=completeness,
                recommended_discovery_jobs=completeness.recommended_discovery_jobs,
                missing_data_warnings=missing_data_warnings,
                audit_trace_id=trace_id,
            )
            performance_observer.record_endpoint("/build/generate-local", self._elapsed_ms(started))
            return response

        pools = {
            category: ComponentPool(category, self._category_products(category, region="SA", limit=80))
            for category in REQUIRED_BUILD_CATEGORIES
        }
        build_specs = [
            ("recommended_saudi_build", "Recommended Saudi Build", "balanced"),
            ("budget_fit_build", "Budget Fit Build", "budget"),
            ("best_value_build", "Best Value Build", "value"),
            ("lowest_risk_local_build", "Lowest Risk Local Build", "risk"),
        ]

        candidate_builds: list[SaudiBuildOption] = []
        for label, title, mode in build_specs:
            components = self._select_components(pools, request=request, mode=mode)
            if len(components) != len(REQUIRED_BUILD_CATEGORIES):
                continue
            candidate_builds.append(self._build_option(label, title, components, request, completeness, mode))

        strict_budget_failure = None
        builds = list(candidate_builds)
        if request.strict_budget:
            builds = [
                build
                for build in builds
                if (build.summary.total_recommended_price_sar is not None and build.summary.total_recommended_price_sar <= request.budget_sar)
            ]
            if not builds:
                strict_budget_failure = self._build_strict_budget_failure(candidate_builds, pools, request=request)
        status = "ready" if builds else "no_budget_fit" if request.strict_budget else "no_valid_build"
        warnings = [] if builds else ["No complete Saudi build could be assembled from compatible priced data."]
        if request.strict_budget and not builds:
            if strict_budget_failure is not None:
                warnings = [strict_budget_failure.reason]
            else:
                warnings = ["No valid Saudi build fits the selected strict budget with currently ingested prices."]

        response = SaudiBuildResponse(
            region="SA",
            city=request.city,
            build_status=status,
            builds=builds,
            data_completeness=completeness,
            recommended_discovery_jobs=self._budget_gap_discovery_jobs(candidate_builds if candidate_builds else builds, pools, request=request),
            missing_data_warnings=warnings,
            strict_budget_failure=strict_budget_failure,
            build_comparison=self._build_comparison(builds),
            audit_trace_id=trace_id,
        )
        performance_observer.record_endpoint("/build/generate-local", self._elapsed_ms(started))
        return response

    def validate_local_build(self, request: SaudiBuildValidationRequest) -> SaudiBuildValidationResponse:
        categories = set(REQUIRED_BUILD_CATEGORIES)
        missing = sorted(categories - set(request.component_ids))
        warnings = []
        total = 0.0
        confidence_values = []
        for category, product_id in request.component_ids.items():
            detail = self.pricing_repository.product_detail(product_id, region=request.region)
            if not detail:
                warnings.append(f"{category}: product not found in Saudi pricing graph.")
                continue
            if detail.current_recommended_price is None:
                warnings.append(f"{category}: missing recommended Saudi price.")
            else:
                total += detail.current_recommended_price
            if detail.price_confidence is not None:
                confidence_values.append(detail.price_confidence)
            if detail.region != "SA":
                warnings.append(f"{category}: non-Saudi price context detected.")
            if category == "PSU":
                wattage = (
                    detail.specs.get("wattage_w")
                    or detail.specs.get("continuous_wattage")
                    or detail.specs.get("wattage")
                )
                if wattage is None:
                    warnings.append("PSU: wattage is unknown, so power safety cannot be validated.")
                elif float(wattage) < 650:
                    warnings.append("PSU: underpowered for a modern gaming build safety margin.")
        if missing:
            warnings.append("Build is incomplete; compatibility cannot be fully validated.")
        over_budget = request.budget_sar is not None and total > request.budget_sar
        if over_budget:
            warnings.append("Build exceeds the selected SAR budget.")
        confidence = round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.0
        return SaudiBuildValidationResponse(
            valid=not missing and not warnings,
            compatibility_status="incomplete" if missing else "not_validated" if warnings else "valid",
            market_confidence=confidence,
            total_recommended_price_sar=round(total, 2) if total else None,
            warnings=warnings,
            missing_categories=missing,
        )

    def _category_products(self, category: str, *, region: str, limit: int) -> list[ProductSearchResult]:
        cache_key = (category, region, limit)
        if cache_key in self._category_product_cache:
            performance_observer.record_cache(hit=True)
            return self._category_product_cache[cache_key]
        performance_observer.record_cache(hit=False)
        query_started = perf_counter()
        products = self.pricing_repository.search_products(q="", category=category, region=region, limit=limit)
        performance_observer.record_query(f"pricing_search:{region}:{category}", self._elapsed_ms(query_started))
        self._category_product_cache[cache_key] = products
        return products

    def _coverage_for_category(self, category: str, products: list[ProductSearchResult]) -> CategoryCoverage:
        priced = [product for product in products if product.region == "SA" and product.price_status in {"active", "stale"} and self._has_valid_saudi_price(product)]
        valid_identity = [product for product in priced if self._has_valid_category_identity(category, product)]
        severe = [product for product in valid_identity if self._has_severe_price_or_identity_risk(product)]
        trusted = [
            product
            for product in valid_identity
            if product.current_recommended_price is not None
            and (product.recommended_level in {"recommended", "good_if_price_matters", "acceptable_with_risk"})
            and not self._has_severe_price_or_identity_risk(product)
        ]
        usable = [
            product
            for product in valid_identity
            if self._is_usable_with_warnings_candidate(category, product)
            and product not in trusted
        ]
        risky = [
            product
            for product in valid_identity
            if product.current_recommended_price is None
            and (product.lowest_market_price is not None or product.lowest_price_warning)
            and product not in usable
        ]
        stale = [product for product in products if product.price_status == "stale" or product.stale]
        unknown_vat = [product for product in valid_identity if "vat_unknown" in product.flags or "unknown_vat" in product.flags]
        unknown_shipping = [
            product for product in valid_identity if "unknown_shipping" in product.flags or "shipping_unknown" in product.flags
        ]
        unknown_warranty = [
            product for product in valid_identity if "unknown_warranty" in product.flags or "warranty_unknown" in product.flags
        ]
        notes: list[str] = []
        blocker_reasons: list[str] = []
        warning_reasons: list[str] = []
        readiness_level = "ready" if trusted else "not_ready"
        if category == "RAM" and len(valid_identity) >= 2 and (trusted or usable):
            readiness_level = "usable_with_warnings" if not trusted else "ready"
        elif category == "Storage" and valid_identity and (trusted or usable):
            readiness_level = "usable_with_warnings" if not trusted else "ready"
        elif category == "Motherboard" and valid_identity and (trusted or usable):
            readiness_level = "usable_with_warnings" if not trusted else "ready"
        elif not trusted:
            readiness_level = "not_ready"

        if not priced:
            blocker_reasons.append("No Saudi price snapshots found.")
        if priced and not valid_identity:
            blocker_reasons.append("Saudi listings exist, but product identity does not match the build target.")
        if severe:
            blocker_reasons.append("Severe suspicious price or category mismatch blocks readiness.")
        if valid_identity and not trusted and not usable:
            blocker_reasons.append("Only risky or incomplete Saudi listings are available.")
        if readiness_level == "usable_with_warnings":
            warning_reasons.append("Product identity and SAR price are valid, but VAT/shipping/warranty remain incomplete.")
        if stale:
            warning_reasons.append("One or more Saudi price snapshots are stale.")
        if unknown_vat:
            warning_reasons.append("VAT evidence is incomplete.")
        if unknown_shipping:
            warning_reasons.append("Shipping evidence is incomplete.")
        if unknown_warranty:
            warning_reasons.append("Warranty evidence is incomplete.")
        notes.extend(blocker_reasons)
        notes.extend(warning_reasons)
        next_action = self._coverage_next_action(
            category=category,
            readiness_level=readiness_level,
            priced_count=len(priced),
            valid_identity_count=len(valid_identity),
            severe_count=len(severe),
            trusted_count=len(trusted),
            usable_count=len(usable),
        )
        next_action_type = self._coverage_next_action_type(
            readiness_level=readiness_level,
            priced_count=len(priced),
            severe_count=len(severe),
            trusted_count=len(trusted),
            usable_count=len(usable),
            stale_count=len(stale),
        )
        freshness_status = self._price_freshness_status(priced, stale)
        identity_confidence = round(len(valid_identity) / len(priced), 2) if priced else 0.0
        return CategoryCoverage(
            category=category,
            priced_product_count=len(priced),
            trusted_local_listing_count=len(trusted),
            usable_with_warnings_count=len(usable),
            risky_listing_count=len(risky),
            unknown_vat_count=len(unknown_vat),
            unknown_shipping_count=len(unknown_shipping),
            unknown_warranty_count=len(unknown_warranty),
            suspicious_price_count=len(severe),
            recommended_option_count=len(trusted),
            stale_listing_count=len(stale),
            ready=readiness_level == "ready",
            readiness_level=readiness_level,  # type: ignore[arg-type]
            identity_confidence=identity_confidence,
            price_freshness_status=freshness_status,  # type: ignore[arg-type]
            blocker_reasons=list(dict.fromkeys(blocker_reasons)),
            warning_reasons=list(dict.fromkeys(warning_reasons)),
            next_action_type=next_action_type,  # type: ignore[arg-type]
            notes=notes,
            next_action=next_action,
        )

    def _coverage_next_action(
        self,
        *,
        category: str,
        readiness_level: str,
        priced_count: int,
        valid_identity_count: int,
        severe_count: int,
        trusted_count: int,
        usable_count: int,
    ) -> str:
        if readiness_level == "ready":
            return "No action needed; keep normal price refresh monitoring."
        if readiness_level == "usable_with_warnings":
            return "Use in builds with visible warnings; add one trusted manual product URL to improve confidence."
        if not priced_count:
            query = DISCOVERY_QUERIES.get(category, [f"{category} Saudi price"])[0]
            return f"Run controlled dry-run discovery for `{query}` or add one approved manual product URL."
        if severe_count:
            return "Review suspicious listings and add a trusted manual product URL before using this category."
        if valid_identity_count and not trusted_count and not usable_count:
            return "Add a trusted local/GCC listing or approved product URL; current listings are too risky."
        return "Run a narrow identity-quality dry-run and review canonicalization before build use."

    def _coverage_next_action_type(
        self,
        *,
        readiness_level: str,
        priced_count: int,
        severe_count: int,
        trusted_count: int,
        usable_count: int,
        stale_count: int,
    ) -> str:
        if readiness_level == "ready" and not stale_count:
            return "no_action"
        if stale_count and (trusted_count or usable_count):
            return "refresh_known_url"
        if readiness_level == "usable_with_warnings":
            return "manual_product_url"
        if severe_count:
            return "review_suspicious_listing"
        if not priced_count:
            return "controlled_dry_run"
        return "manual_product_url"

    def _price_freshness_status(self, priced: list[ProductSearchResult], stale: list[ProductSearchResult]) -> str:
        if not priced:
            return "missing"
        if len(stale) == len(priced):
            return "stale"
        if stale:
            return "mixed"
        return "fresh"

    def _duplicate_risk_categories(self, coverages: list[CategoryCoverage], *, region: str) -> list[str]:
        risky: list[str] = []
        for coverage in coverages:
            products = self._category_products(coverage.category, region=region, limit=80)
            keys: dict[str, set[str]] = {}
            for product in products:
                if not product.canonical_key:
                    continue
                keys.setdefault(product.canonical_key, set()).add(product.id)
            if any(len(product_ids) > 1 for product_ids in keys.values()):
                risky.append(coverage.category)
        return risky

    def _has_valid_category_identity(self, category: str, product: ProductSearchResult) -> bool:
        text = f"{product.canonical_key or ''} {product.name} {product.model or ''}".upper()
        if product.lowest_market_price is None and product.current_recommended_price is None:
            return False
        if category == "RAM":
            return "DDR5" in text and "32GB" in text and ("6000" in text or "6000MHZ" in text)
        if category == "Storage":
            return "STORAGE|" in text and ("2TB" in text or "1TB" in text) and "NVME" in text and "M2" in text
        if category == "Motherboard":
            return "MOTHERBOARD|" in text and "B650" in text and "AM5" in text and "DDR5" in text
        return True

    def _sar_currency(self, currency: str | None) -> str | None:
        if not currency:
            return None
        return currency.strip().upper().replace("_", "")

    def _has_valid_saudi_price(self, product: ProductSearchResult) -> bool:
        has_price = product.current_recommended_price is not None or product.lowest_market_price is not None
        if not has_price:
            return False
        if product.region != "SA":
            return False

        currencies = [
            product.current_recommended_currency,
            product.lowest_market_currency,
            product.region_currency,
        ]
        normalized = [self._sar_currency(currency) for currency in currencies]
        normalized = [currency for currency in normalized if currency]
        if not normalized:
            return False
        if not all(currency == "SAR" for currency in normalized):
            return False
        return True

    def _has_severe_price_or_identity_risk(self, product: ProductSearchResult) -> bool:
        severe_tokens = (
            "hard_bounds",
            "impossible_price",
            "category_mismatch",
            "not_standalone",
            "sata_not_nvme",
            "does_not_match_requested",
        )
        return any(any(token in flag for token in severe_tokens) for flag in product.flags)

    def _is_usable_with_warnings_candidate(self, category: str, product: ProductSearchResult) -> bool:
        if category not in {"RAM", "Storage", "Motherboard"}:
            return False
        if not self._has_valid_category_identity(category, product):
            return False
        if self._has_severe_price_or_identity_risk(product):
            return False
        if product.region != "SA" or not self._has_valid_saudi_price(product):
            return False
        risk = product.current_recommended_marketplace_risk_score
        if risk is None:
            risk = product.lowest_marketplace_risk_score if product.lowest_marketplace_risk_score is not None else 0.5
        confidence = product.price_confidence if product.price_confidence is not None else 0.35
        risk_ceiling = 0.78 if category == "Motherboard" and {
            "trusted_local_vendor",
            "local_stock_likely",
        }.intersection(product.flags) else 0.72
        return risk <= risk_ceiling and confidence >= 0.3

    def _discovery_jobs(self, categories: list[str], *, city: str) -> list[RecommendedDiscoveryJob]:
        jobs: list[RecommendedDiscoveryJob] = []
        for category in categories:
            for query in DISCOVERY_QUERIES.get(category, [f"{category} PC component"]):
                jobs.append(
                    RecommendedDiscoveryJob(
                        category=category,
                        query=query,
                        region="SA",
                        city=city,
                        limit=5,
                        dry_run=True,
                        reason=f"{category} lacks enough trusted Saudi market data for build generation.",
                    )
                )
        return jobs[:20]

    def _missing_warnings(self, completeness: SaudiBuildDataCompleteness) -> list[str]:
        return [
            f"{category}: no reliable Saudi-priced component yet; run suggested dry-run discovery first."
            for category in completeness.missing_categories
        ]

    def _select_components(
        self,
        pools: dict[str, ComponentPool],
        *,
        request: SaudiBuildRequest,
        mode: str,
    ) -> list[SaudiBuildComponent]:
        selected: list[SaudiBuildComponent] = []
        budget_weights = self._budget_weights(request)
        for category in REQUIRED_BUILD_CATEGORIES:
            products = pools[category].products
            target_budget = request.budget_sar * budget_weights.get(category, 0.1)
            product = self._best_product(products, category=category, request=request, mode=mode, target_budget=target_budget)
            if not product:
                continue
            selected.append(self._component_from_product(product, category, request=request, alternatives=products))
        return selected

    def _budget_weights(self, request: SaudiBuildRequest) -> dict[str, float]:
        weights = dict(PERFORMANCE_WEIGHTS)
        if request.target_resolution in {"1440p", "4k", "ultrawide"}:
            weights["GPU"] += 0.06
            weights["CPU"] -= 0.03
        if request.priority == "upgrade_path":
            weights["Motherboard"] += 0.04
            weights["PSU"] += 0.03
        if request.priority == "quiet_build":
            weights["Cooler"] += 0.04
            weights["Case"] += 0.03
        total = sum(weights.values())
        return {key: value / total for key, value in weights.items()}

    def _best_product(
        self,
        products: list[ProductSearchResult],
        *,
        category: str,
        request: SaudiBuildRequest,
        mode: str,
        target_budget: float,
    ) -> ProductSearchResult | None:
        candidates = [product for product in products if product.region == "SA" and self._has_valid_saudi_price(product)]
        if mode == "risk":
            candidates = [
                product
                for product in candidates
                if product.current_recommended_price is not None or self._is_usable_with_warnings_candidate(category, product)
            ]
        if not candidates:
            return None
        return sorted(
            candidates,
            key=lambda product: self._product_market_score(
                product,
                request=request,
                mode=mode,
                target_budget=target_budget,
            ),
            reverse=True,
        )[0]

    def _product_market_score(
        self,
        product: ProductSearchResult,
        *,
        request: SaudiBuildRequest,
        mode: str,
        target_budget: float,
    ) -> float:
        price = product.current_recommended_price or product.lowest_market_price or 999999
        confidence = product.price_confidence or 0.3
        risk = product.current_recommended_marketplace_risk_score
        if risk is None:
            risk = product.lowest_marketplace_risk_score or 0.5
        brand_bonus = 0.08 if product.brand and product.brand in request.brand_preferences else 0
        under_target = max(0.0, target_budget - price) / max(target_budget, 1)
        over_target = max(0.0, price - target_budget) / max(target_budget, 1)
        local_bonus = 0.12 if product.current_recommended_price is not None else 0
        warning_penalty = 0.08 if product.lowest_price_warning else 0
        score = confidence + local_bonus + brand_bonus + under_target * 0.16 - over_target * 0.35 - risk * 0.22 - warning_penalty
        if product.category == "GPU":
            if product.compatibility_ready_exact:
                score += 0.08
            elif product.compatibility_ready_family:
                score -= 0.07
        if mode == "value":
            score += (1 / max(price, 1)) * target_budget * 0.3
        elif mode == "budget":
            within_budget_bonus = 0.42 if price <= target_budget else 0.0
            score += within_budget_bonus + under_target * 0.28 - over_target * 0.85 - risk * 0.08
        elif mode == "risk":
            score += confidence * 0.25 + local_bonus * 0.5 - risk * 0.25
        elif mode == "balanced":
            score += local_bonus * 0.2
        return score

    def _component_from_product(
        self,
        product: ProductSearchResult,
        category: str,
        *,
        request: SaudiBuildRequest,
        alternatives: list[ProductSearchResult],
    ) -> SaudiBuildComponent:
        price = product.current_recommended_price or product.lowest_market_price
        warnings: list[str] = []
        if product.current_recommended_price is None:
            warnings.append("No recommended Saudi price; using lowest market price with risk label.")
        if category in {"RAM", "Storage", "Motherboard"} and self._is_usable_with_warnings_candidate(category, product):
            warnings.append(f"{category} is usable with market-data warnings; verify VAT, shipping, warranty, and seller terms.")
        if category == "GPU" and product.compatibility_ready_family and not product.compatibility_ready_exact:
            warnings.append(
                "GPU uses confirmed family specs only; verify exact card length, board power, slots, and power connectors before purchase."
            )
        risk = product.current_recommended_marketplace_risk_score
        if risk is not None and risk > 0.72:
            warnings.append(f"{category} has elevated marketplace risk ({risk:.2f}).")
        if category == "PSU" and not self._psu_efficiency_from_text(product):
            warnings.append("PSU efficiency rating is unclear; verify 80+ rating before buying.")
        if product.lowest_price_warning:
            warnings.append(product.lowest_price_warning)
        stock_badge = "imported" if product.current_recommended_seller_type == "marketplace" else "local" if product.current_recommended_price is not None else "unknown"
        selected_price = price or float("inf")
        alt_names = [
            f"{item.name} ({(item.current_recommended_price or item.lowest_market_price or 0):.0f} SAR)"
            for item in sorted(
                alternatives,
                key=lambda item: item.current_recommended_price or item.lowest_market_price or float("inf"),
            )
            if item.id != product.id
            and self._has_valid_saudi_price(item)
            and (item.current_recommended_price or item.lowest_market_price or float("inf")) < selected_price
        ][:3]
        vat_status, shipping_status, warranty_status = self._component_signal_status(product)
        return SaudiBuildComponent(
            product_id=product.id,
            name=product.name,
            category=category,
            brand=product.brand,
            recommended_vendor=product.current_recommended_vendor or product.lowest_market_vendor,
            recommended_price_sar=price,
            lowest_market_price_sar=product.lowest_market_price,
            price_confidence=product.price_confidence,
            seller_type=product.current_recommended_seller_type or product.lowest_market_seller_type,
            vendor_region_type=None,
            stock_badge=stock_badge,
            vat_status=vat_status,
            shipping_status=shipping_status,
            warranty_status=warranty_status,
            reason_selected=self._component_reason(product, category, request),
            alternatives=alt_names,
            warnings=warnings,
        )

    def _component_signal_status(self, product: ProductSearchResult) -> tuple[str, str, str]:
        flags = [flag.lower() for flag in product.flags]
        vat_status = "vat_unknown"
        shipping_status = "unknown_shipping"
        warranty_status = "unknown_warranty"
        if any("vat_included" in flag for flag in flags):
            vat_status = "vat_included"
        elif any("vat_excluded" in flag for flag in flags):
            vat_status = "vat_excluded"
        elif any("vat_unknown" in flag for flag in flags):
            vat_status = "vat_unknown"

        if any("free_shipping" in flag for flag in flags):
            shipping_status = "free_shipping"
        elif any("paid_shipping" in flag for flag in flags):
            shipping_status = "paid_shipping"
        elif any("pickup_only" in flag for flag in flags):
            shipping_status = "pickup_only"
        elif any("unknown_shipping" in flag for flag in flags):
            shipping_status = "unknown_shipping"

        if any("manufacturer_warranty" in flag for flag in flags):
            warranty_status = "manufacturer_warranty"
        elif any("seller_warranty" in flag for flag in flags):
            warranty_status = "seller_warranty"
        elif any("local_warranty" in flag for flag in flags):
            warranty_status = "local_warranty"
        elif any("unknown_warranty" in flag for flag in flags):
            warranty_status = "unknown_warranty"

        return vat_status, shipping_status, warranty_status

    def _component_reason(self, product: ProductSearchResult, category: str, request: SaudiBuildRequest) -> str:
        if category == "PSU":
            efficiency = self._psu_efficiency_from_text(product)
            if efficiency:
                return (
                    f"PSU selected from Saudi market data with {efficiency} efficiency evidence and enough "
                    f"power-safety relevance for {request.use_case}."
                )
        if product.current_recommended_price is not None:
            return (
                f"{category} selected from Saudi market data with {product.recommended_level or 'usable'} "
                f"recommendation confidence for {request.use_case} at {request.target_resolution}."
            )
        return f"{category} has Saudi market visibility, but current listing risk prevents a safe recommendation."

    def _psu_efficiency_from_text(self, product: ProductSearchResult) -> str | None:
        text = f"{product.name} {product.canonical_key or ''} {product.model or ''}".upper()
        for label in ("TITANIUM", "PLATINUM", "GOLD", "SILVER", "BRONZE"):
            if label in text:
                return label
        return None

    def _build_option(
        self,
        label: str,
        title: str,
        components: list[SaudiBuildComponent],
        request: SaudiBuildRequest,
        completeness: SaudiBuildDataCompleteness,
        mode: str,
    ) -> SaudiBuildOption:
        recommended_prices = [item.recommended_price_sar for item in components if item.recommended_price_sar is not None]
        lowest_prices = [item.lowest_market_price_sar for item in components if item.lowest_market_price_sar is not None]
        total_recommended = round(sum(recommended_prices), 2) if len(recommended_prices) == len(components) else None
        total_lowest = round(sum(lowest_prices), 2) if len(lowest_prices) == len(components) else None
        confidence_values = [item.price_confidence for item in components if item.price_confidence is not None]
        confidence = round((sum(confidence_values) / len(confidence_values)) * completeness.readiness_score, 2) if confidence_values else 0
        warnings = [warning for item in components for warning in item.warnings]
        uncertain_components = [item.category for item in components if item.warnings]
        if total_recommended is None:
            warnings.append("At least one component lacks a recommended Saudi price.")
        budget_delta = None if total_recommended is None else round(request.budget_sar - total_recommended, 2)
        over_budget_amount = abs(budget_delta) if budget_delta is not None and budget_delta < 0 else 0
        over_budget_percent = round(over_budget_amount / request.budget_sar, 3) if request.budget_sar and over_budget_amount else 0
        budget_status = self._budget_status(total_recommended, request.budget_sar)
        if over_budget_amount:
            warnings.append(f"This build is {over_budget_amount:.0f} SAR over your budget.")
        expensive = self._most_expensive_components(components)
        savings = self._savings_opportunities(components, request=request)
        confidence_level = "high" if confidence >= 0.75 else "medium" if confidence >= 0.5 else "low"
        summary = SaudiBuildSummary(
            total_recommended_price_sar=total_recommended,
            total_lowest_possible_price_sar=total_lowest,
            budget_remaining_or_overage=budget_delta,
            budget_sar=request.budget_sar,
            budget_delta_sar=budget_delta,
            over_budget_amount_sar=round(over_budget_amount, 2),
            over_budget_percent=over_budget_percent,
            budget_status=budget_status,  # type: ignore[arg-type]
            most_expensive_components=expensive,
            easiest_savings_opportunities=savings,
            compatibility_status="not_validated",
            performance_estimate=self._performance_estimate(request, mode),
            bottleneck_summary=self._bottleneck_summary(request),
            risk_summary=list(dict.fromkeys(warnings))[:8],
            data_completeness_score=completeness.readiness_score,
            warning_summary=list(dict.fromkeys(warnings))[:6],
            components_with_uncertainty=list(dict.fromkeys(uncertain_components)),
            confidence_level=confidence_level,  # type: ignore[arg-type]
            confidence_score=confidence,
            missing_data_warnings=[],
        )
        explanation = self._build_explanation(
            label=label,
            title=title,
            components=components,
            summary=summary,
            request=request,
            mode=mode,
        )
        confidence_breakdown = self._confidence_breakdown(components, summary, completeness)
        savings_suggestions = self._structured_savings_suggestions(components, request=request)
        comparison = self._comparison_item(
            label=label,
            title=title,
            summary=summary,
            components=components,
        )
        export = self._build_export(
            label=label,
            title=title,
            components=components,
            summary=summary,
            explanation=explanation,
            request=request,
        )
        return SaudiBuildOption(
            label=label,  # type: ignore[arg-type]
            title=title,
            components=components,
            summary=summary,
            explanation=explanation,
            confidence_breakdown=confidence_breakdown,
            savings_suggestions=savings_suggestions,
            comparison_metrics=comparison,
            export=export,
            why_this_build=self._build_reason(mode, request),
            upgrade_notes=self._upgrade_notes(request),
        )

    def _build_explanation(
        self,
        *,
        label: str,
        title: str,
        components: list[SaudiBuildComponent],
        summary: SaudiBuildSummary,
        request: SaudiBuildRequest,
        mode: str,
    ) -> SaudiBuildExplanation:
        trusted = [item.category for item in components if item.stock_badge in {"local", "gcc"} and not item.warnings]
        uncertain = list(dict.fromkeys(summary.components_with_uncertainty))
        imported = [item.category for item in components if item.stock_badge == "imported"]
        pressure = summary.most_expensive_components[:2]
        strengths = [
            f"Uses Saudi-region SAR pricing for all {len(components)} core components.",
            self._build_reason(mode, request),
        ]
        if trusted:
            strengths.append(f"Clearer local buying signals on {', '.join(trusted[:4])}.")
        weaknesses = []
        if summary.over_budget_amount_sar:
            weaknesses.append(
                f"Current build is {summary.over_budget_amount_sar:.0f} SAR over the selected budget."
            )
        if uncertain:
            weaknesses.append(f"Market evidence is still incomplete for {', '.join(uncertain[:5])}.")
        risks = list(dict.fromkeys([*summary.warning_summary, *summary.risk_summary]))[:8]
        if imported:
            risks.append(f"Imported or marketplace signals appear on {', '.join(imported[:4])}.")
        budget_analysis = self._budget_analysis(summary)
        return SaudiBuildExplanation(
            build_id=f"sa-{label}-{int(request.budget_sar)}",
            build_mode=label,  # type: ignore[arg-type]
            confidence_level=summary.confidence_level,
            summary=self._human_summary(summary, request, mode),
            strengths=list(dict.fromkeys(strengths))[:5],
            weaknesses=list(dict.fromkeys(weaknesses))[:5],
            risks=list(dict.fromkeys(risks))[:8],
            budget_analysis=budget_analysis,
            upgrade_path=self._upgrade_path_guidance(components),
            future_limitations=self._future_limitations(components, request),
            recommended_purchase_order=self._purchase_order(components),
            component_explanations=[
                self._component_explanation(component)
                for component in components
            ],
        )

    def _human_summary(self, summary: SaudiBuildSummary, request: SaudiBuildRequest, mode: str) -> str:
        market_phrase = "Saudi market"
        if mode == "budget":
            intent = "tries to fit the budget first while keeping compatibility intact"
        elif mode == "risk":
            intent = "prioritizes safer local buying signals over the lowest headline price"
        elif mode == "value":
            intent = "leans toward performance per SAR without treating risky listings as safe"
        else:
            intent = f"balances {request.target_resolution} {request.use_case} needs with local price evidence"
        if summary.over_budget_amount_sar:
            return (
                f"This {market_phrase} build {intent}. It is currently "
                f"{summary.over_budget_amount_sar:.0f} SAR over budget, mostly because of the highest-cost parts."
            )
        return f"This {market_phrase} build {intent} and stays within the selected SAR budget."

    def _budget_analysis(self, summary: SaudiBuildSummary) -> str:
        if summary.total_recommended_price_sar is None:
            return "The build does not have enough recommended Saudi prices to produce a complete budget total."
        if summary.over_budget_amount_sar:
            pressure = "; ".join(summary.most_expensive_components[:3])
            return (
                f"Total is {summary.total_recommended_price_sar:.0f} SAR, "
                f"{summary.over_budget_amount_sar:.0f} SAR over budget. "
                f"Largest pressure: {pressure or 'not enough component detail'}."
            )
        remaining = summary.budget_delta_sar or 0
        return f"Total is {summary.total_recommended_price_sar:.0f} SAR, leaving about {remaining:.0f} SAR."

    def _component_explanation(self, component: SaudiBuildComponent) -> SaudiComponentExplanation:
        cheaper = next((item for item in component.alternatives if "SAR" in item), None)
        risk_summary = "No major market warning visible."
        if component.warnings:
            risk_summary = component.warnings[0]
        elif component.stock_badge == "imported":
            risk_summary = "Imported or marketplace listing needs extra seller and warranty review."
        confidence = component.price_confidence if component.price_confidence is not None else 0.35
        return SaudiComponentExplanation(
            category=component.category,
            selected_product=component.name,
            reason_selected=component.reason_selected,
            cheaper_alternative=cheaper,
            stronger_alternative=None,
            risk_summary=risk_summary,
            confidence=round(max(0.0, min(confidence, 1.0)), 2),
            local_availability=component.stock_badge,
            warranty_confidence=self._status_confidence(component.warranty_status, unknown_token="unknown"),
            shipping_confidence=self._status_confidence(component.shipping_status, unknown_token="unknown"),
            compatibility_confidence=self._component_compatibility_confidence(component),
            market_confidence=round(max(0.0, min(confidence, 1.0)), 2),
        )

    def _confidence_breakdown(
        self,
        components: list[SaudiBuildComponent],
        summary: SaudiBuildSummary,
        completeness: SaudiBuildDataCompleteness,
    ) -> SaudiBuildConfidenceBreakdown:
        pricing_values = [item.price_confidence for item in components if item.price_confidence is not None]
        pricing = sum(pricing_values) / len(pricing_values) if pricing_values else 0.35
        local_ratio = len([item for item in components if item.stock_badge in {"local", "gcc"}]) / max(len(components), 1)
        shipping = sum(self._status_confidence(item.shipping_status, unknown_token="unknown") for item in components)
        shipping /= max(len(components), 1)
        warranty = sum(self._status_confidence(item.warranty_status, unknown_token="unknown") for item in components)
        warranty /= max(len(components), 1)
        compatibility = 0.82 - (0.04 * len(summary.components_with_uncertainty))
        compatibility = max(0.35, compatibility)
        market = max(0.0, min(pricing * completeness.readiness_score, 1.0))
        overall = (compatibility + market + local_ratio + pricing + shipping + warranty) / 6
        return SaudiBuildConfidenceBreakdown(
            compatibility_confidence=round(compatibility, 2),
            market_confidence=round(market, 2),
            vendor_confidence=round(local_ratio, 2),
            pricing_confidence=round(pricing, 2),
            shipping_confidence=round(shipping, 2),
            warranty_confidence=round(warranty, 2),
            overall_confidence=round(overall, 2),
        )

    def _structured_savings_suggestions(
        self,
        components: list[SaudiBuildComponent],
        *,
        request: SaudiBuildRequest,
    ) -> list[SaudiSavingsSuggestion]:
        suggestions: list[SaudiSavingsSuggestion] = []
        for component in sorted(
            components,
            key=lambda item: item.recommended_price_sar or item.lowest_market_price_sar or 0,
            reverse=True,
        ):
            current_price = component.recommended_price_sar or component.lowest_market_price_sar
            alternative = self._first_allowed_substitution(component)
            if not alternative:
                continue
            estimated = self._estimated_savings(component.category, current_price, request)
            suggestions.append(
                SaudiSavingsSuggestion(
                    category=component.category,
                    current=component.name,
                    alternative=alternative,
                    estimated_savings_sar=estimated,
                    performance_impact=self._performance_impact(component.category),
                    reason=self._savings_reason(component.category, alternative),
                )
            )
            if len(suggestions) >= 5:
                break
        return suggestions

    def _first_allowed_substitution(self, component: SaudiBuildComponent) -> str | None:
        for alternative in ALLOWED_BUDGET_SUBSTITUTIONS.get(component.category, []):
            if alternative.upper() not in component.name.upper():
                return alternative
        return None

    def _estimated_savings(
        self,
        category: str,
        current_price: float | None,
        request: SaudiBuildRequest,
    ) -> float | None:
        if current_price is None:
            return None
        ratios = {
            "GPU": 0.2,
            "CPU": 0.25,
            "Storage": 0.28,
            "Cooler": 0.22,
            "PSU": 0.14,
            "Motherboard": 0.16,
            "RAM": 0.12,
            "Case": 0.12,
        }
        ratio = ratios.get(category, 0.12)
        return round(min(current_price * ratio, request.budget_sar * 0.12), 2)

    def _performance_impact(self, category: str) -> str:
        if category in {"GPU", "CPU"}:
            return "moderate"
        if category in {"Storage", "Cooler", "Case"}:
            return "low"
        return "unknown"

    def _savings_reason(self, category: str, alternative: str) -> str:
        reasons = {
            "GPU": "Largest gaming-performance cost lever; validate FPS tradeoff before buying.",
            "CPU": "Can reduce platform cost while keeping AM5 compatibility.",
            "Storage": "Capacity reduction lowers cost with little FPS impact.",
            "Cooler": "A good AM5 air cooler may be enough if thermals are acceptable.",
            "PSU": "750W Gold can be acceptable if power margin remains safe.",
            "Motherboard": "A lower-cost AM5 DDR5 board may preserve compatibility.",
            "RAM": "A slightly slower DDR5 kit may reduce cost with modest impact.",
            "Case": "A cheaper airflow case can work if clearance remains valid.",
        }
        return reasons.get(category, f"Check {alternative} as a lower-cost compatible option.")

    def _upgrade_path_guidance(self, components: list[SaudiBuildComponent]) -> list[str]:
        names = " ".join(component.name.upper() for component in components)
        guidance = []
        if "AM5" in names or "B650" in names:
            guidance.append("AM5/B650 platform gives a practical future CPU upgrade path, subject to BIOS support.")
        if "850W" in names or "750W" in names:
            guidance.append("Gold-rated PSU capacity should leave some GPU upgrade headroom if connector support is verified.")
        if "32GB" in names and "DDR5" in names:
            guidance.append("32GB DDR5 is a strong baseline for modern gaming and general creation workloads.")
        if "1TB" in names:
            guidance.append("1TB storage is acceptable for budget fit, but game libraries may need a second SSD later.")
        return guidance or ["Upgrade guidance is limited until more exact component specs are available."]

    def _future_limitations(
        self,
        components: list[SaudiBuildComponent],
        request: SaudiBuildRequest,
    ) -> list[str]:
        limitations = []
        if request.target_resolution in {"4k", "ultrawide"}:
            limitations.append("Higher resolutions may need stronger GPU data before recommendation confidence increases.")
        if any(item.category in {"RAM", "Storage"} and item.warnings for item in components):
            limitations.append("RAM or storage is usable, but incomplete market evidence lowers buying confidence.")
        if any(item.shipping_status == "unknown_shipping" for item in components):
            limitations.append("Unknown shipping terms may change the final landed price.")
        return limitations or ["No major future limitation is visible from the current Saudi market data."]

    def _purchase_order(self, components: list[SaudiBuildComponent]) -> list[str]:
        priority = {
            "GPU": 0,
            "CPU": 1,
            "Motherboard": 2,
            "PSU": 3,
            "RAM": 4,
            "Storage": 5,
            "Cooler": 6,
            "Case": 7,
        }
        ranked = sorted(
            components,
            key=lambda item: (
                priority.get(item.category, 99),
                0 if item.warnings else 1,
            ),
        )
        return [
            f"{item.category}: buy early if the listed Saudi price/vendor is still available."
            for item in ranked
        ]

    def _component_compatibility_confidence(self, component: SaudiBuildComponent) -> float:
        confidence = 0.78
        if component.category in {"CPU", "GPU", "Motherboard", "PSU"}:
            confidence += 0.08
        if component.warnings:
            confidence -= 0.08
        return round(max(0.35, min(confidence, 1.0)), 2)

    def _status_confidence(self, status: str, *, unknown_token: str) -> float:
        return 0.42 if unknown_token in status else 0.82

    def _comparison_item(
        self,
        *,
        label: str,
        title: str,
        summary: SaudiBuildSummary,
        components: list[SaudiBuildComponent],
    ) -> SaudiBuildComparisonItem:
        warning_count = len(summary.warning_summary) + len(summary.components_with_uncertainty)
        risk_level = "high" if warning_count >= 6 else "medium" if warning_count >= 3 else "low"
        local_count = len([item for item in components if item.stock_badge in {"local", "gcc"}])
        return SaudiBuildComparisonItem(
            label=label,  # type: ignore[arg-type]
            title=title,
            total_price_sar=summary.total_recommended_price_sar,
            budget_status=summary.budget_status,
            risk_level=risk_level,  # type: ignore[arg-type]
            confidence_score=summary.confidence_score,
            local_availability_summary=f"{local_count}/{len(components)} components have local/GCC buying signals.",
            upgrade_path_summary=", ".join(self._upgrade_path_guidance(components)[:2]),
        )

    def _build_comparison(self, builds: list[SaudiBuildOption]) -> list[SaudiBuildComparisonItem]:
        items = [build.comparison_metrics.model_copy() for build in builds]
        priced = [item for item in items if item.total_price_sar is not None]
        if priced:
            cheapest = min(priced, key=lambda item: item.total_price_sar or float("inf"))
            for index, item in enumerate(items):
                if item.label == cheapest.label:
                    items[index].cheapest_option = True
        if items:
            safest = max(items, key=lambda item: (item.risk_level == "low", item.confidence_score))
            for index, item in enumerate(items):
                if item.label == safest.label:
                    items[index].safest_option = True
        return items

    def _build_export(
        self,
        *,
        label: str,
        title: str,
        components: list[SaudiBuildComponent],
        summary: SaudiBuildSummary,
        explanation: SaudiBuildExplanation,
        request: SaudiBuildRequest,
    ) -> SaudiBuildExport:
        component_rows = [
            {
                "category": item.category,
                "name": item.name,
                "vendor": item.recommended_vendor,
                "price_sar": item.recommended_price_sar,
                "warnings": item.warnings,
            }
            for item in components
        ]
        json_summary = {
            "region": "SA",
            "city": request.city,
            "build_mode": label,
            "title": title,
            "total_price_sar": summary.total_recommended_price_sar,
            "budget_sar": request.budget_sar,
            "budget_status": summary.budget_status,
            "confidence": summary.confidence_level,
            "components": component_rows,
        }
        lines = [
            f"# {title}",
            "",
            explanation.summary,
            "",
            f"- Total: {summary.total_recommended_price_sar or 'Unavailable'} SAR",
            f"- Budget: {request.budget_sar:.0f} SAR",
            f"- Status: {summary.budget_status.replace('_', ' ')}",
            "",
            "## Components",
        ]
        lines.extend(
            f"- {item['category']}: {item['name']} - {item['price_sar'] or 'Unavailable'} SAR"
            for item in component_rows
        )
        markdown = "\n".join(lines)
        return SaudiBuildExport(
            shareable_build_url=(
                f"/?market_region=SA&build_mode={label}&budget_sar={int(request.budget_sar)}"
            ),
            json_summary=json_summary,
            markdown_summary=markdown,
            printable_summary=markdown,
        )

    def _performance_estimate(self, request: SaudiBuildRequest, mode: str) -> str:
        if request.target_resolution == "1440p" and request.use_case == "gaming":
            return "Aims for practical 1440p gaming around the requested refresh target when GPU data supports it."
        if mode == "risk":
            return "Prioritizes stable local buying signals over peak benchmark value."
        return "Performance estimate remains confidence-weighted by available Saudi component data."

    def _bottleneck_summary(self, request: SaudiBuildRequest) -> str:
        if request.target_resolution in {"4k", "ultrawide"}:
            return "Likely GPU-limited; GPU Saudi price quality carries the most weight."
        if request.use_case in {"simulation", "workstation", "content_creation"}:
            return "CPU, RAM, and storage data should be improved before high-confidence workstation guidance."
        return "Balanced CPU/GPU fit depends on completing Saudi data across all required categories."

    def _build_reason(self, mode: str, request: SaudiBuildRequest) -> str:
        if mode == "budget":
            return "Attempts to stay inside the SAR budget using only ingested Saudi prices and safe lower-cost substitutions."
        if mode == "value":
            return "Chooses the strongest price-to-confidence options without treating risky marketplace prices as safe."
        if mode == "risk":
            return "Prioritizes trusted local Saudi/GCC listings, warranty clarity, and lower marketplace risk."
        return f"Balances Saudi price, vendor risk, and the {request.priority.replace('_', ' ')} priority."

    def _upgrade_notes(self, request: SaudiBuildRequest) -> list[str]:
        notes = []
        if request.priority == "upgrade_path":
            notes.append("Prioritize motherboard and PSU discovery before finalizing upgrade-path builds.")
        if request.case_size == "ITX":
            notes.append("ITX builds need stronger case, cooler, and GPU clearance data before recommendation.")
        if not notes:
            notes.append("Run dry-run discovery for missing categories before trusting a full Saudi build.")
        return notes

    def _budget_status(self, total: float | None, budget: float) -> str:
        if total is None:
            return "no_valid_build_under_budget"
        delta = total - budget
        if delta <= 0:
            return "under_budget"
        if delta / max(budget, 1) <= 0.08:
            return "slightly_over_budget"
        return "over_budget"

    def _most_expensive_components(self, components: list[SaudiBuildComponent]) -> list[str]:
        priced = [
            (component.category, component.name, component.recommended_price_sar or component.lowest_market_price_sar or 0)
            for component in components
        ]
        return [
            f"{category}: {name} ({price:.0f} SAR)"
            for category, name, price in sorted(priced, key=lambda item: item[2], reverse=True)[:3]
            if price > 0
        ]

    def _savings_opportunities(self, components: list[SaudiBuildComponent], *, request: SaudiBuildRequest) -> list[str]:
        opportunities: list[str] = []
        by_category = {component.category: component for component in components}
        budget_items = ["GPU", "CPU", "Storage", "Cooler", "PSU", "Motherboard", "RAM", "Case"]

        for category in budget_items:
            component = by_category.get(category)
            if not component:
                continue
            for alternative in component.alternatives[:2]:
                opportunities.append(f"Cheaper {category} option: {alternative}.")
            for replacement in ALLOWED_BUDGET_SUBSTITUTIONS.get(category, []):
                replacement_upper = replacement.upper()
                if replacement_upper in (component.name or "").upper():
                    continue
                opportunities.append(f"Cheaper {category} option candidate: {replacement}.")
                break
            if len(opportunities) >= 7:
                break

        if request.budget_sar:
            total = sum(component.recommended_price_sar or component.lowest_market_price_sar or 0 for component in components)
            if total > request.budget_sar:
                opportunities.extend(
                    [
                        "Check cheaper GPU options (RTX 4070 / RTX 4060 Ti 16GB / RX 7700 XT).",
                        "Check cheaper CPU options (Ryzen 5 7600 or Ryzen 5 7500F).",
                        "Run discovery for 1TB NVMe SSD if storage capacity can be reduced by one tier.",
                    ]
                )
        return list(dict.fromkeys(opportunities))[:8]

    def _build_strict_budget_failure(
        self,
        candidate_builds: list[SaudiBuildOption],
        pools: dict[str, ComponentPool],
        *,
        request: SaudiBuildRequest,
    ) -> SaudiNoBudgetFitGuidance:
        by_category_prices = self._cheapest_valid_category_prices(pools)
        cheapest_known_total = (
            round(sum(by_category_prices.values()), 2)
            if len(by_category_prices) == len(REQUIRED_BUILD_CATEGORIES)
            else None
        )

        expensive_categories = [
            category
            for category, _ in sorted(
                by_category_prices.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        ]

        if not expensive_categories:
            missing_cheaper_categories = REQUIRED_BUILD_CATEGORIES[:3]
        else:
            missing_cheaper_categories = expensive_categories[:4]

        suggested_products: list[str] = []
        for category in missing_cheaper_categories:
            suggested_products.extend(ALLOWED_BUDGET_SUBSTITUTIONS.get(category, []))

        discovery_targets = self._build_strict_budget_discovery_targets(
            missing_cheaper_categories,
            pool=pools,
            city=request.city,
        )

        manual_targets = self._manual_url_target_hints(missing_cheaper_categories)
        reason = self._strict_budget_failure_reason(
            request=request,
            cheapest_known_total=cheapest_known_total,
        )

        return SaudiNoBudgetFitGuidance(
            reason=reason,
            missing_cheaper_categories=missing_cheaper_categories,
            suggested_products_to_add=sorted(set(suggested_products))[:10],
            suggested_discovery_targets=discovery_targets,
            suggested_manual_url_targets=manual_targets,
        )

    def _cheapest_valid_category_prices(self, pools: dict[str, ComponentPool]) -> dict[str, float]:
        prices: dict[str, float] = {}
        for category, pool in pools.items():
            valid_prices = [
                product.current_recommended_price or product.lowest_market_price
                for product in pool.products
                if product.region == "SA"
                and self._has_valid_saudi_price(product)
                and self._has_valid_category_identity(category, product)
                and not self._has_severe_price_or_identity_risk(product)
            ]
            valid_prices = [price for price in valid_prices if price is not None]
            if valid_prices:
                prices[category] = min(valid_prices)
        return prices

    def _manual_url_target_hints(self, categories: list[str]) -> list[str]:
        hints = {
            "GPU": "Add known Saudi URLs for RTX 4070, RX 7800 XT, RX 7700 XT, or RTX 4060 Ti 16GB.",
            "CPU": "Add known Saudi URLs for Ryzen 5 7600, Ryzen 5 7500F, or Ryzen 7 7700.",
            "Motherboard": "Add known Saudi URLs for compatible B650 mATX or A620 AM5 DDR5 boards.",
            "RAM": "Add known Saudi URLs for DDR5 32GB 5600 or lower-risk DDR5 32GB 6000 kits.",
            "Storage": "Add known Saudi URLs for 1TB NVMe SSDs or lower-cost 2TB NVMe alternatives.",
            "PSU": "Add known Saudi URLs for safe 750W Gold PSUs.",
            "Case": "Add known Saudi URLs for lower-cost ATX or mATX airflow cases.",
            "Cooler": "Add known Saudi URLs for AM5 air coolers.",
        }
        return [hints[category] for category in categories if category in hints]

    def _strict_budget_failure_reason(
        self,
        *,
        request: SaudiBuildRequest,
        cheapest_known_total: float | None,
    ) -> str:
        if cheapest_known_total is not None and cheapest_known_total > request.budget_sar:
            overage = cheapest_known_total - request.budget_sar
            return (
                f"No full Saudi build fits {request.budget_sar:.0f} SAR with currently ingested data. "
                f"The cheapest compatible known set is about {cheapest_known_total:.0f} SAR, "
                f"which is {overage:.0f} SAR over budget."
            )
        return (
            f"No full Saudi build fits {request.budget_sar:.0f} SAR with currently ingested data. "
            "Check the suggested discovery targets and add cheaper compatible Saudi candidates."
        )

    def _build_strict_budget_discovery_targets(
        self,
        categories: list[str],
        *,
        pool: dict[str, ComponentPool],
        city: str,
    ) -> list[RecommendedDiscoveryJob]:
        targets: list[RecommendedDiscoveryJob] = []
        for category in categories:
            for query in BUDGET_DISCOVERY_QUERIES.get(category, []):
                targets.append(
                    RecommendedDiscoveryJob(
                        category=category,
                        query=query,
                        region="SA",
                        city=city,
                        limit=5,
                        dry_run=True,
                        reason=(
                            f"Cheaper {category} options may be required to reach a strict budget fit for Saudi build generation."
                        ),
                    )
                )
        return targets[:10]

    def _budget_gap_discovery_jobs(
        self,
        builds: list[SaudiBuildOption],
        pools: dict[str, ComponentPool],
        *,
        request: SaudiBuildRequest,
    ) -> list[RecommendedDiscoveryJob]:
        needs_budget_help = not builds or any(
            build.summary.total_recommended_price_sar is None
            or build.summary.total_recommended_price_sar > request.budget_sar
            for build in builds
        )
        if not needs_budget_help:
            return []
        categories = self._budget_pressure_categories(builds, pools)
        jobs: list[RecommendedDiscoveryJob] = []
        for category in categories:
            for query in BUDGET_DISCOVERY_QUERIES.get(category, []):
                jobs.append(
                    RecommendedDiscoveryJob(
                        category=category,
                        query=query,
                        region="SA",
                        city=request.city,
                        limit=5,
                        dry_run=True,
                        reason=f"{category} pricing is pushing the Saudi build above the {request.budget_sar:.0f} SAR budget.",
                    )
                )
        return jobs[:10]

    def _budget_pressure_categories(self, builds: list[SaudiBuildOption], pools: dict[str, ComponentPool]) -> list[str]:
        if builds:
            first = sorted(
                builds,
                key=lambda build: build.summary.total_recommended_price_sar or float("inf"),
            )[0]
            categories = [
                component.category
                for component in sorted(
                    first.components,
                    key=lambda component: component.recommended_price_sar or component.lowest_market_price_sar or 0,
                    reverse=True,
                )
            ]
        else:
            categories = ["GPU", "CPU", "Storage", "PSU", "Case", "Cooler", "RAM", "Motherboard"]
        return [category for category in categories if BUDGET_DISCOVERY_QUERIES.get(category)]

    def _elapsed_ms(self, started: float) -> float:
        return (perf_counter() - started) * 1000
