from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.api import (
    CategoryCoverage,
    RecommendedDiscoveryJob,
    SaudiBuildComponent,
    SaudiBuildDataCompleteness,
    SaudiBuildOption,
    SaudiBuildRequest,
    SaudiBuildResponse,
    SaudiBuildSummary,
    SaudiBuildValidationRequest,
    SaudiBuildValidationResponse,
)
from app.models.pricing import ProductSearchResult


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

BUDGET_DISCOVERY_QUERIES: dict[str, list[str]] = {
    "GPU": [
        "RTX 4070 graphics card",
        "RX 7800 XT graphics card",
        "RX 7700 XT graphics card",
        "RTX 4060 Ti 16GB graphics card",
    ],
    "CPU": ["Ryzen 5 7600 processor", "Ryzen 5 7500F processor", "Ryzen 7 7700 processor"],
    "Motherboard": ["B650 mATX AM5 DDR5 motherboard", "A620 AM5 DDR5 motherboard budget option"],
    "RAM": ["DDR5 32GB 5600 RAM kit", "DDR5 16GB RAM kit budget option"],
    "Storage": ["1TB NVMe SSD PCIe 4.0", "budget 1TB NVMe SSD"],
    "PSU": ["750W Gold PSU", "750W 80 Plus Gold fully modular PSU"],
    "Case": ["budget ATX airflow case", "mATX airflow PC case"],
    "Cooler": ["AM5 air cooler", "Thermalright Peerless Assassin CPU Cooler AM5"],
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

    def data_completeness(self, *, region: str = "SA", city: str = "Riyadh") -> SaudiBuildDataCompleteness:
        if region != "SA":
            raise ValueError("Saudi local build generation currently supports region=SA only.")
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
        return SaudiBuildDataCompleteness(
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

    def generate_local(self, request: SaudiBuildRequest, *, trace_id: str | None = None) -> SaudiBuildResponse:
        completeness = self.data_completeness(region=request.region, city=request.city)
        warnings = self._missing_warnings(completeness)
        if not completeness.enough_data_for_full_build:
            return SaudiBuildResponse(
                region="SA",
                city=request.city,
                build_status="incomplete_data",
                builds=[],
                data_completeness=completeness,
                recommended_discovery_jobs=completeness.recommended_discovery_jobs,
                missing_data_warnings=warnings,
                audit_trace_id=trace_id,
            )

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
        builds: list[SaudiBuildOption] = []
        for label, title, mode in build_specs:
            components = self._select_components(pools, request=request, mode=mode)
            if len(components) != len(REQUIRED_BUILD_CATEGORIES):
                continue
            builds.append(self._build_option(label, title, components, request, completeness, mode))
        if request.strict_budget:
            builds = [
                build
                for build in builds
                if (build.summary.total_recommended_price_sar is not None and build.summary.total_recommended_price_sar <= request.budget_sar)
            ]
        suggestions = self._budget_gap_discovery_jobs(builds, pools, request=request)
        status = "ready" if builds else "incomplete_budget_fit" if request.strict_budget else "no_valid_build"
        warnings = [] if builds else ["No complete Saudi build could be assembled from compatible priced data."]
        if request.strict_budget and not builds:
            warnings = ["No valid Saudi build fits the selected strict budget with currently ingested prices."]

        return SaudiBuildResponse(
            region="SA",
            city=request.city,
            build_status=status,
            builds=builds,
            data_completeness=completeness,
            recommended_discovery_jobs=suggestions,
            missing_data_warnings=warnings,
            audit_trace_id=trace_id,
        )

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
        return self.pricing_repository.search_products(q="", category=category, region=region, limit=limit)

    def _coverage_for_category(self, category: str, products: list[ProductSearchResult]) -> CategoryCoverage:
        priced = [product for product in products if product.region == "SA" and product.price_status in {"active", "stale"}]
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
        notes = []
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
            notes.append("No Saudi price snapshots found.")
        if priced and not valid_identity:
            notes.append("Saudi listings exist, but product identity does not match the build target.")
        if severe:
            notes.append("Severe suspicious price or category mismatch blocks readiness.")
        if valid_identity and not trusted and not usable:
            notes.append("Only risky or incomplete Saudi listings are available.")
        if readiness_level == "usable_with_warnings":
            notes.append("Usable with warnings: product identity and SAR price are valid, but VAT/shipping/warranty remain incomplete.")
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
            notes=notes,
        )

    def _has_valid_category_identity(self, category: str, product: ProductSearchResult) -> bool:
        text = f"{product.canonical_key or ''} {product.name} {product.model or ''}".upper()
        if product.lowest_market_price is None and product.current_recommended_price is None:
            return False
        if category == "RAM":
            return "DDR5" in text and "32GB" in text and ("6000" in text or "6000MHZ" in text)
        if category == "Storage":
            return "STORAGE|" in text and "2TB" in text and "NVME" in text and "M2" in text
        if category == "Motherboard":
            return "MOTHERBOARD|" in text and "B650" in text and "AM5" in text and "DDR5" in text
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
        if product.region != "SA" or product.lowest_market_currency != "SAR":
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
        candidates = [product for product in products if product.region == "SA" and product.lowest_market_price is not None]
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
        if product.lowest_price_warning:
            warnings.append(product.lowest_price_warning)
        stock_badge = "local" if product.current_recommended_price is not None else "unknown"
        selected_price = price or float("inf")
        alt_names = [
            f"{item.name} ({(item.current_recommended_price or item.lowest_market_price or 0):.0f} SAR)"
            for item in sorted(
                alternatives,
                key=lambda item: item.current_recommended_price or item.lowest_market_price or float("inf"),
            )
            if item.id != product.id
            and item.region == "SA"
            and item.lowest_market_price is not None
            and (item.current_recommended_price or item.lowest_market_price or float("inf")) < selected_price
        ][:3]
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
            reason_selected=self._component_reason(product, category, request),
            alternatives=alt_names,
            warnings=warnings,
        )

    def _component_reason(self, product: ProductSearchResult, category: str, request: SaudiBuildRequest) -> str:
        if product.current_recommended_price is not None:
            return (
                f"{category} selected from Saudi market data with {product.recommended_level or 'usable'} "
                f"recommendation confidence for {request.use_case} at {request.target_resolution}."
            )
        return f"{category} has Saudi market visibility, but current listing risk prevents a safe recommendation."

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
            warnings.append(f"Build is {over_budget_amount:.0f} SAR over the selected budget.")
        expensive = self._most_expensive_components(components)
        savings = self._savings_opportunities(components, request=request)
        confidence_level = "high" if confidence >= 0.75 else "medium" if confidence >= 0.5 else "low"
        return SaudiBuildOption(
            label=label,  # type: ignore[arg-type]
            title=title,
            components=components,
            summary=SaudiBuildSummary(
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
            ),
            why_this_build=self._build_reason(mode, request),
            upgrade_notes=self._upgrade_notes(request),
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
        for category in ["GPU", "CPU", "Storage", "PSU", "Case", "Cooler", "RAM", "Motherboard"]:
            component = by_category.get(category)
            if not component:
                continue
            for alternative in component.alternatives[:2]:
                opportunities.append(f"Check cheaper {category} alternative: {alternative}.")
            if len(opportunities) >= 5:
                break
        if request.budget_sar:
            total = sum(component.recommended_price_sar or component.lowest_market_price_sar or 0 for component in components)
            if total > request.budget_sar:
                opportunities.extend(
                    [
                        "Run dry-run discovery for RTX 4070 or RX 7700 XT before downgrading the whole build.",
                        "Run dry-run discovery for Ryzen 5 7600 or 7500F if CPU savings are needed.",
                        "Run dry-run discovery for 1TB NVMe SSD if storage capacity can be reduced.",
                    ]
                )
        return list(dict.fromkeys(opportunities))[:6]

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
