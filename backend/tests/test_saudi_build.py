from __future__ import annotations

from app.models.api import SaudiBuildRequest, SaudiBuildValidationRequest
from app.models.pricing import ProductDetail, ProductSearchResult
from app.services.saudi_build_generator import REQUIRED_BUILD_CATEGORIES, SaudiLocalBuildService


def _product(
    category: str,
    *,
    product_id: str | None = None,
    price: float | None = 1000,
    lowest: float | None = None,
    region: str = "SA",
    vendor: str = "Jarir",
    risk: float = 0.1,
    confidence: float = 0.8,
    recommended: bool = True,
    canonical_key: str | None = None,
    name: str | None = None,
    flags: list[str] | None = None,
) -> ProductSearchResult:
    return ProductSearchResult(
        id=product_id or f"{category.lower()}:local",
        canonical_key=canonical_key or f"{category.upper()}_LOCAL",
        name=name or f"Local {category}",
        brand="AMD" if category == "CPU" else "NVIDIA" if category == "GPU" else None,
        category=category,
        data_origin="live",
        price_status="active" if price or lowest else "unavailable",
        region=region,
        region_currency="SAR" if region == "SA" else "USD",
        recommended_level="acceptable_with_risk" if recommended else None,
        price_confidence=confidence,
        current_recommended_price=price if recommended else None,
        current_recommended_currency="SAR" if region == "SA" and recommended else None,
        current_recommended_vendor=vendor if recommended else None,
        current_recommended_seller_type="retailer" if recommended else None,
        current_recommended_marketplace_risk_score=risk if recommended else None,
        lowest_market_price=lowest if lowest is not None else price,
        lowest_market_currency="SAR" if region == "SA" else "USD",
        lowest_market_vendor=vendor,
        lowest_market_seller_type="marketplace" if risk >= 0.6 else "retailer",
        lowest_marketplace_risk_score=risk,
        flags=flags or [],
    )


def _ready_product(category: str, **kwargs) -> ProductSearchResult:
    if category == "RAM":
        kwargs.setdefault("canonical_key", "RAM|CORSAIR|VENGEANCE|DDR5|32GB|6000")
        kwargs.setdefault("name", "Corsair Vengeance 32GB DDR5 6000")
    elif category == "Storage":
        kwargs.setdefault("canonical_key", "STORAGE|WD|BLACK_SN850X|2TB|NVME|M2")
        kwargs.setdefault("name", "WD Black SN850X 2TB NVMe SSD")
    elif category == "Motherboard":
        kwargs.setdefault("canonical_key", "MOTHERBOARD|MSI|B650_TOMAHAWK_WIFI|AM5|DDR5|ATX")
        kwargs.setdefault("name", "MSI B650 Tomahawk WiFi AM5 DDR5 ATX Motherboard")
    return _product(category, **kwargs)


class FakePricingRepository:
    def __init__(
        self,
        products_by_category: dict[str, list[ProductSearchResult]],
        specs_by_product_id: dict[str, dict] | None = None,
    ) -> None:
        self.products_by_category = products_by_category
        self.specs_by_product_id = specs_by_product_id or {}
        self.requested_regions: list[str] = []

    def search_products(self, q: str = "", category: str | None = None, region: str = "SA", limit: int = 20):
        self.requested_regions.append(region)
        return list(self.products_by_category.get(category or "", []))[:limit]

    def product_categories(self):
        return sorted(self.products_by_category)

    def product_detail(self, product_id: str, region: str = "SA"):
        for products in self.products_by_category.values():
            for product in products:
                if product.id == product_id:
                    return ProductDetail(
                        **product.model_dump(),
                        specs=self.specs_by_product_id.get(product_id, {}),
                        latest_prices=[],
                        field_evidence=[],
                    )
        return None


def test_data_completeness_reports_missing_categories_and_dry_run_suggestions() -> None:
    repository = FakePricingRepository({"GPU": [_product("GPU")]})
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    completeness = service.data_completeness(region="SA", city="Riyadh")

    assert "GPU" in completeness.ready_categories
    assert "CPU" in completeness.missing_categories
    assert completeness.enough_data_for_full_build is False
    assert any(job.category == "CPU" and job.dry_run for job in completeness.recommended_discovery_jobs)


def test_completeness_reports_blockers_warnings_and_next_action_types() -> None:
    repository = FakePricingRepository(
        {
            "GPU": [_product("GPU", flags=["unknown_vat"], confidence=0.72)],
            "CPU": [],
            "Storage": [
                _ready_product(
                    "Storage",
                    recommended=False,
                    lowest=450,
                    risk=0.4,
                    confidence=0.45,
                    flags=["unknown_shipping", "unknown_warranty"],
                )
            ],
        }
    )
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    completeness = service.data_completeness(region="SA", city="Riyadh")
    coverage = {item.category: item for item in completeness.category_coverage}

    assert coverage["CPU"].readiness_level == "not_ready"
    assert coverage["CPU"].next_action_type == "controlled_dry_run"
    assert coverage["CPU"].blocker_reasons == ["No Saudi price snapshots found."]
    assert coverage["GPU"].warning_reasons == ["VAT evidence is incomplete."]
    assert coverage["Storage"].readiness_level == "usable_with_warnings"
    assert coverage["Storage"].next_action_type == "manual_product_url"


def test_stale_valid_category_is_usable_but_not_silent() -> None:
    stale_gpu = _product("GPU", flags=[], confidence=0.8)
    stale_gpu.price_status = "stale"
    stale_gpu.stale = True
    repository = FakePricingRepository({"GPU": [stale_gpu]})
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    completeness = service.data_completeness(region="SA", city="Riyadh")
    gpu = next(item for item in completeness.category_coverage if item.category == "GPU")

    assert gpu.readiness_level == "ready"
    assert gpu.price_freshness_status == "stale"
    assert gpu.next_action_type == "refresh_known_url"
    assert "One or more Saudi price snapshots are stale." in gpu.warning_reasons


def test_catalog_completeness_includes_non_critical_and_duplicate_risk() -> None:
    repository = FakePricingRepository(
        {
            "GPU": [
                _product("GPU", product_id="gpu-1", canonical_key="GPU|NVIDIA|RTX_4070_SUPER"),
                _product("GPU", product_id="gpu-2", canonical_key="GPU|NVIDIA|RTX_4070_SUPER"),
            ],
            "Monitor": [_product("Monitor", canonical_key="MONITOR|1440P|144HZ")],
        }
    )
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    catalog = service.catalog_completeness(region="SA", city="Riyadh")

    assert any(item.category == "GPU" for item in catalog.build_critical_categories)
    assert any(item.category == "Monitor" for item in catalog.non_critical_categories)
    assert "GPU" in catalog.duplicate_risk_categories
    assert catalog.next_actions


def test_generate_local_refuses_to_fabricate_missing_saudi_prices() -> None:
    repository = FakePricingRepository({"GPU": [_product("GPU")]})
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    response = service.generate_local(
        SaudiBuildRequest(
            budget_sar=6000,
            use_case="gaming",
            target_resolution="1440p",
            brand_preferences=["AMD", "NVIDIA"],
            case_size="ATX",
            priority="best_value",
        )
    )

    assert response.build_status == "incomplete_data"
    assert response.builds == []
    assert response.missing_data_warnings
    assert all(region == "SA" for region in repository.requested_regions)


def test_lowest_risk_build_prefers_local_trusted_over_cheaper_marketplace() -> None:
    products_by_category = {}
    for category in REQUIRED_BUILD_CATEGORIES:
        products_by_category[category] = [
            _ready_product(category, product_id=f"{category}:local", price=1200, lowest=1200, vendor="Jarir", risk=0.05, confidence=0.85),
            _ready_product(
                category,
                product_id=f"{category}:marketplace",
                price=None,
                lowest=800,
                vendor="eBay",
                risk=0.85,
                confidence=0.35,
                recommended=False,
            ),
        ]
    repository = FakePricingRepository(products_by_category)
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    response = service.generate_local(
        SaudiBuildRequest(
            budget_sar=12000,
            use_case="gaming",
            target_resolution="1440p",
            brand_preferences=["no_preference"],
            priority="lowest_risk",
        )
    )
    risk_build = next(build for build in response.builds if build.label == "lowest_risk_local_build")

    assert response.build_status == "ready"
    assert risk_build.components
    assert all(component.recommended_vendor == "Jarir" for component in risk_build.components)
    assert all(component.stock_badge == "local" for component in risk_build.components)


def test_validate_local_build_reports_missing_prices_and_categories() -> None:
    repository = FakePricingRepository({"GPU": [_product("GPU", product_id="gpu:priced")]})
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    result = service.validate_local_build(
        SaudiBuildValidationRequest(
            region="SA",
            city="Riyadh",
            component_ids={"GPU": "gpu:priced", "CPU": "cpu:missing"},
            budget_sar=5000,
        )
    )

    assert result.valid is False
    assert result.compatibility_status == "incomplete"
    assert "Motherboard" in result.missing_categories
    assert any("CPU" in warning for warning in result.warnings)


def test_validate_local_build_rejects_underpowered_psu() -> None:
    products = {
        category: [_product(category, product_id=f"{category}:priced")]
        for category in REQUIRED_BUILD_CATEGORIES
    }
    repository = FakePricingRepository(products, specs_by_product_id={"PSU:priced": {"wattage_w": 550}})
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    result = service.validate_local_build(
        SaudiBuildValidationRequest(
            region="SA",
            city="Riyadh",
            component_ids={category: f"{category}:priced" for category in REQUIRED_BUILD_CATEGORIES},
            budget_sar=12000,
        )
    )

    assert result.valid is False
    assert result.compatibility_status == "not_validated"
    assert any("underpowered" in warning.lower() for warning in result.warnings)


def test_ram_with_valid_saudi_ddr5_32gb_6000_can_be_usable_with_warnings() -> None:
    repository = FakePricingRepository(
        {
            "RAM": [
                _product(
                    "RAM",
                    product_id="ram:one",
                    price=None,
                    lowest=420,
                    recommended=False,
                    risk=0.58,
                    confidence=0.42,
                    canonical_key="RAM|CORSAIR|VENGEANCE|DDR5|32GB|6000",
                    name="Corsair Vengeance 32GB DDR5 6000",
                    flags=["vat_unknown", "unknown_shipping", "unknown_warranty"],
                ),
                _product(
                    "RAM",
                    product_id="ram:two",
                    price=None,
                    lowest=455,
                    recommended=False,
                    risk=0.6,
                    confidence=0.38,
                    canonical_key="RAM|KINGSTON|FURY|DDR5|32GB|6000",
                    name="Kingston Fury 32GB DDR5 6000",
                    flags=["vat_unknown", "unknown_shipping"],
                ),
            ]
        }
    )
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    coverage = service.data_completeness(region="SA", city="Riyadh").category_coverage
    ram = next(item for item in coverage if item.category == "RAM")

    assert ram.readiness_level == "usable_with_warnings"
    assert ram.usable_with_warnings_count == 2
    assert ram.unknown_vat_count == 2
    assert ram.ready is False


def test_storage_with_valid_2tb_nvme_saudi_price_can_be_usable_with_warnings() -> None:
    repository = FakePricingRepository(
        {
            "Storage": [
                _product(
                    "Storage",
                    product_id="storage:sn850x",
                    price=None,
                    lowest=599,
                    recommended=False,
                    risk=0.55,
                    confidence=0.44,
                    canonical_key="STORAGE|WD|BLACK_SN850X|2TB|NVME|M2",
                    name="WD Black SN850X 2TB NVMe SSD",
                    flags=["vat_unknown", "unknown_shipping"],
                )
            ]
        }
    )
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    storage = next(
        item for item in service.data_completeness(region="SA", city="Riyadh").category_coverage if item.category == "Storage"
    )

    assert storage.readiness_level == "usable_with_warnings"
    assert storage.usable_with_warnings_count == 1
    assert "Storage" not in service.data_completeness(region="SA", city="Riyadh").missing_categories


def test_severe_suspicious_price_blocks_readiness() -> None:
    repository = FakePricingRepository(
        {
            "Storage": [
                _product(
                    "Storage",
                    product_id="storage:bad",
                    price=None,
                    lowest=50,
                    recommended=False,
                    risk=0.3,
                    confidence=0.4,
                    canonical_key="STORAGE|WD|BLACK_SN850X|2TB|NVME|M2",
                    name="WD Black SN850X 2TB NVMe SSD",
                    flags=["suspicious_price_outside_storage_model_hard_bounds"],
                )
            ]
        }
    )
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    storage = next(
        item for item in service.data_completeness(region="SA", city="Riyadh").category_coverage if item.category == "Storage"
    )

    assert storage.readiness_level == "not_ready"
    assert storage.suspicious_price_count == 1


def test_motherboard_missing_still_blocks_build_when_ram_storage_are_usable() -> None:
    products = {
        category: [_product(category, product_id=f"{category}:priced")]
        for category in REQUIRED_BUILD_CATEGORIES
        if category != "Motherboard"
    }
    products["RAM"] = [
        _product(
            "RAM",
            product_id="ram:usable",
            price=None,
            lowest=420,
            recommended=False,
            risk=0.58,
            confidence=0.42,
            canonical_key="RAM|CORSAIR|VENGEANCE|DDR5|32GB|6000",
            name="Corsair Vengeance 32GB DDR5 6000",
            flags=["vat_unknown", "unknown_shipping"],
        ),
        _product(
            "RAM",
            product_id="ram:usable-two",
            price=None,
            lowest=450,
            recommended=False,
            risk=0.58,
            confidence=0.42,
            canonical_key="RAM|KINGSTON|FURY|DDR5|32GB|6000",
            name="Kingston Fury 32GB DDR5 6000",
            flags=["vat_unknown", "unknown_shipping"],
        ),
    ]
    products["Storage"] = [
        _product(
            "Storage",
            product_id="storage:usable",
            price=None,
            lowest=599,
            recommended=False,
            risk=0.55,
            confidence=0.44,
            canonical_key="STORAGE|WD|BLACK_SN850X|2TB|NVME|M2",
            name="WD Black SN850X 2TB NVMe SSD",
            flags=["vat_unknown", "unknown_shipping"],
        )
    ]
    repository = FakePricingRepository(products)
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    response = service.generate_local(SaudiBuildRequest(budget_sar=6000))

    assert response.build_status == "incomplete_data"
    assert "Motherboard" in response.data_completeness.missing_categories
    assert "RAM" not in response.data_completeness.missing_categories
    assert "Storage" not in response.data_completeness.missing_categories


def test_motherboard_with_valid_b650_am5_ddr5_saudi_price_can_be_usable_with_warnings() -> None:
    repository = FakePricingRepository(
        {
            "Motherboard": [
                _product(
                    "Motherboard",
                    product_id="motherboard:usable",
                    price=None,
                    lowest=899,
                    recommended=False,
                    risk=0.55,
                    confidence=0.45,
                    canonical_key="MOTHERBOARD|MSI|B650_TOMAHAWK_WIFI|AM5|DDR5|ATX",
                    name="MSI B650 Tomahawk WiFi AM5 DDR5 ATX Motherboard",
                    flags=["vat_unknown", "unknown_shipping", "unknown_warranty"],
                )
            ]
        }
    )
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    motherboard = next(
        item
        for item in service.data_completeness(region="SA", city="Riyadh").category_coverage
        if item.category == "Motherboard"
    )

    assert motherboard.readiness_level == "usable_with_warnings"
    assert motherboard.usable_with_warnings_count == 1


def test_first_full_saudi_build_generates_when_motherboard_becomes_usable() -> None:
    products = {category: [_ready_product(category, product_id=f"{category}:priced")] for category in REQUIRED_BUILD_CATEGORIES}
    products["RAM"] = [
        _ready_product(
            "RAM",
            product_id="ram:usable",
            price=None,
            lowest=420,
            recommended=False,
            risk=0.58,
            confidence=0.42,
            flags=["vat_unknown", "unknown_shipping"],
        ),
        _ready_product(
            "RAM",
            product_id="ram:usable-two",
            price=None,
            lowest=450,
            recommended=False,
            risk=0.58,
            confidence=0.42,
            canonical_key="RAM|KINGSTON|FURY|DDR5|32GB|6000",
            name="Kingston Fury 32GB DDR5 6000",
            flags=["vat_unknown", "unknown_shipping"],
        ),
    ]
    products["Storage"] = [
        _ready_product(
            "Storage",
            product_id="storage:usable",
            price=None,
            lowest=599,
            recommended=False,
            risk=0.55,
            confidence=0.44,
            flags=["vat_unknown", "unknown_shipping"],
        )
    ]
    products["Motherboard"] = [
        _ready_product(
            "Motherboard",
            product_id="motherboard:usable",
            price=None,
            lowest=899,
            recommended=False,
            risk=0.55,
            confidence=0.45,
            flags=["vat_unknown", "unknown_shipping", "unknown_warranty"],
        )
    ]
    repository = FakePricingRepository(products)
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    response = service.generate_local(
        SaudiBuildRequest(
            budget_sar=6000,
            use_case="gaming",
            target_resolution="1440p",
            refresh_rate_target=144,
            brand_preferences=["AMD", "NVIDIA"],
            case_size="ATX",
            priority="best_value",
        )
    )

    assert response.build_status == "ready"
    assert response.builds
    first = response.builds[0]
    assert first.summary.total_recommended_price_sar is not None
    assert first.summary.confidence_level in {"low", "medium"}
    uncertain = set(first.summary.components_with_uncertainty)
    assert {"RAM", "Storage", "Motherboard"}.issubset(uncertain)
    assert all(component.recommended_price_sar is not None for component in first.components)


def test_over_budget_build_reports_budget_pressure_and_allows_when_not_strict() -> None:
    products = {category: [_ready_product(category, product_id=f"{category}:priced", price=1200, lowest=1200)] for category in REQUIRED_BUILD_CATEGORIES}
    repository = FakePricingRepository(products)
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    response = service.generate_local(SaudiBuildRequest(budget_sar=6000, strict_budget=False))

    assert response.build_status == "ready"
    assert response.builds
    first = response.builds[0]
    assert first.summary.total_recommended_price_sar == 9600
    assert first.summary.over_budget_amount_sar == 3600
    assert first.summary.over_budget_percent > 0
    assert first.summary.budget_status == "over_budget"
    assert first.summary.most_expensive_components
    assert any("over" in warning.lower() for warning in first.summary.warning_summary)
    assert all(region == "SA" for region in repository.requested_regions)


def test_budget_fit_build_uses_cheaper_compatible_saudi_products_when_available() -> None:
    products = {}
    for category in REQUIRED_BUILD_CATEGORIES:
        products[category] = [
            _ready_product(category, product_id=f"{category}:premium", price=1200, lowest=1200),
            _ready_product(category, product_id=f"{category}:budget", price=650, lowest=650, confidence=0.68),
        ]
    repository = FakePricingRepository(products)
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    response = service.generate_local(SaudiBuildRequest(budget_sar=6000, strict_budget=True))

    assert response.build_status == "ready"
    budget_build = next(build for build in response.builds if build.label == "budget_fit_build")
    assert budget_build.summary.total_recommended_price_sar is not None
    assert budget_build.summary.total_recommended_price_sar <= 6000
    assert budget_build.summary.budget_status == "under_budget"
    assert budget_build.summary.over_budget_amount_sar == 0
    assert any(component.product_id.endswith(":budget") for component in budget_build.components)


def test_strict_budget_blocks_over_budget_build_and_returns_no_budget_fit_guidance() -> None:
    products = {category: [_ready_product(category, product_id=f"{category}:priced", price=1200, lowest=1200)] for category in REQUIRED_BUILD_CATEGORIES}
    repository = FakePricingRepository(products)
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    response = service.generate_local(SaudiBuildRequest(budget_sar=6000, strict_budget=True))

    assert response.build_status == "no_budget_fit"
    assert response.builds == []
    assert response.strict_budget_failure is not None
    assert response.strict_budget_failure.reason
    assert response.strict_budget_failure.missing_cheaper_categories
    assert response.strict_budget_failure.suggested_discovery_targets
    assert "RTX 4070" in " ".join(response.strict_budget_failure.suggested_products_to_add)
    assert response.missing_data_warnings
    assert "9600 SAR" in response.strict_budget_failure.reason
    assert "3600 SAR over budget" in response.strict_budget_failure.reason


def test_over_budget_message_uses_expected_phrase() -> None:
    products = {category: [_ready_product(category, product_id=f"{category}:priced", price=1200, lowest=1200)] for category in REQUIRED_BUILD_CATEGORIES}
    repository = FakePricingRepository(products)
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    response = service.generate_local(SaudiBuildRequest(budget_sar=6000, strict_budget=False))

    first = response.builds[0]
    assert first.summary.over_budget_amount_sar == 3600
    assert f"This build is {int(first.summary.over_budget_amount_sar)} SAR over your budget." in first.summary.warning_summary


def test_no_us_prices_accepted_for_saudi_build_generation() -> None:
    products = {
        category: [_product(category, product_id=f"{category}:us", region="US", price=100, lowest=100)]
        for category in REQUIRED_BUILD_CATEGORIES
    }
    repository = FakePricingRepository(products)
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    response = service.generate_local(SaudiBuildRequest(budget_sar=6000))

    assert response.build_status == "incomplete_data"
    assert response.builds == []
    assert response.data_completeness.missing_categories
    assert set(response.data_completeness.missing_categories) == set(REQUIRED_BUILD_CATEGORIES)

def test_strict_budget_guidance_uses_only_allowed_substitution_targets() -> None:
    products = {category: [_ready_product(category, product_id=f"{category}:priced", price=1200, lowest=1200)] for category in REQUIRED_BUILD_CATEGORIES}
    repository = FakePricingRepository(products)
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    response = service.generate_local(SaudiBuildRequest(budget_sar=6000, strict_budget=True))

    assert response.strict_budget_failure is not None
    allowed = {
        "GPU": {"RTX 4070 Super", "RTX 4070", "RX 7800 XT", "RX 7700 XT", "RTX 4060 Ti 16GB"},
        "CPU": {"Ryzen 7 7800X3D", "Ryzen 7 7700", "Ryzen 5 7600", "Ryzen 5 7500F"},
        "Motherboard": {"B650 ATX", "B650 mATX AM5 DDR5", "A620 AM5 DDR5"},
        "RAM": {"DDR5 32GB 6000", "DDR5 32GB 5600", "DDR5 16GB"},
        "Storage": {"2TB NVMe SSD", "1TB NVMe SSD", "SSD"},
        "PSU": {"850W Gold", "750W Gold"},
        "Case": {"ATX airflow case", "mATX airflow case"},
        "Cooler": {"240mm AIO", "AM5 air cooler"},
    }
    allowed_products = {item for values in allowed.values() for item in values}

    for item in response.strict_budget_failure.suggested_products_to_add:
        assert item in allowed_products

    assert response.strict_budget_failure.suggested_discovery_targets
    assert all(target.limit == 5 and target.region == "SA" and target.city == "Riyadh" for target in response.strict_budget_failure.suggested_discovery_targets)


def test_total_sar_price_calculation_is_exact_for_generated_build() -> None:
    products = {category: [_ready_product(category, product_id=f"{category}:priced", price=100, lowest=100)] for category in REQUIRED_BUILD_CATEGORIES}
    repository = FakePricingRepository(products)
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    response = service.generate_local(SaudiBuildRequest(budget_sar=2000))

    assert response.build_status == "ready"
    first = response.builds[0]
    assert first.summary.total_recommended_price_sar == len(REQUIRED_BUILD_CATEGORIES) * 100


def test_build_explanation_confidence_purchase_order_and_export_are_generated() -> None:
    products = {category: [_ready_product(category, product_id=f"{category}:priced", price=700, lowest=700)] for category in REQUIRED_BUILD_CATEGORIES}
    repository = FakePricingRepository(products)
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    response = service.generate_local(SaudiBuildRequest(budget_sar=6000))

    assert response.build_status == "ready"
    assert response.build_comparison
    first = response.builds[0]
    assert first.explanation.summary
    assert first.explanation.strengths
    assert first.explanation.budget_analysis
    assert len(first.explanation.component_explanations) == len(REQUIRED_BUILD_CATEGORIES)
    assert first.explanation.recommended_purchase_order[0].startswith("GPU:")
    assert first.explanation.upgrade_path
    assert 0 <= first.confidence_breakdown.overall_confidence <= 1
    assert first.comparison_metrics.total_price_sar == first.summary.total_recommended_price_sar
    assert first.export.shareable_build_url.startswith("/?market_region=SA")
    assert "SAR" in first.export.markdown_summary
    export_text = f"{first.export.json_summary} {first.export.markdown_summary}".lower()
    assert "secret" not in export_text
    assert "audit" not in export_text


def test_over_budget_build_generates_structured_savings_suggestions() -> None:
    products = {category: [_ready_product(category, product_id=f"{category}:priced", price=1200, lowest=1200)] for category in REQUIRED_BUILD_CATEGORIES}
    repository = FakePricingRepository(products)
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    response = service.generate_local(SaudiBuildRequest(budget_sar=6000, strict_budget=False))

    first = response.builds[0]
    assert first.summary.over_budget_amount_sar > 0
    assert first.savings_suggestions
    assert all(suggestion.alternative for suggestion in first.savings_suggestions)
    assert all(suggestion.performance_impact in {"low", "moderate", "high", "unknown"} for suggestion in first.savings_suggestions)


def test_marketplace_risk_is_visible_in_build_explanation() -> None:
    products = {category: [_ready_product(category, product_id=f"{category}:priced", price=700, lowest=700)] for category in REQUIRED_BUILD_CATEGORIES}
    products["GPU"] = [
        _ready_product(
            "GPU",
            product_id="GPU:risky",
            price=1700,
            lowest=1700,
            risk=0.9,
            confidence=0.5,
        )
    ]
    repository = FakePricingRepository(products)
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    response = service.generate_local(SaudiBuildRequest(budget_sar=6000))

    first = response.builds[0]
    assert any("marketplace risk" in risk.lower() for risk in first.explanation.risks)
    gpu_explanation = next(item for item in first.explanation.component_explanations if item.category == "GPU")
    assert "marketplace risk" in gpu_explanation.risk_summary.lower()


def test_build_comparison_marks_cheapest_and_safest_options() -> None:
    products = {}
    for category in REQUIRED_BUILD_CATEGORIES:
        products[category] = [
            _ready_product(category, product_id=f"{category}:premium", price=900, lowest=900, risk=0.05, confidence=0.85),
            _ready_product(category, product_id=f"{category}:budget", price=650, lowest=650, risk=0.35, confidence=0.68),
        ]
    repository = FakePricingRepository(products)
    service = SaudiLocalBuildService(repository)  # type: ignore[arg-type]

    response = service.generate_local(SaudiBuildRequest(budget_sar=6000))

    assert len(response.build_comparison) == len(response.builds)
    assert any(item.cheapest_option for item in response.build_comparison)
    assert any(item.safest_option for item in response.build_comparison)
