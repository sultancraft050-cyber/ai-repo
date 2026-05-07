from __future__ import annotations

from datetime import UTC, datetime
from math import exp
from typing import Any

from app.models.pricing import DataQualityReport, FieldEvidence, PriceOffer


PRICE_LIMITS_BY_CATEGORY_USD: dict[str, tuple[float, float]] = {
    "CPU": (25, 5000),
    "GPU": (45, 10000),
    "Motherboard": (35, 2500),
    "RAM": (10, 2000),
    "Storage": (10, 3000),
    "PSU": (20, 1500),
    "Case": (20, 2000),
    "Cooler": (8, 1200),
    "Monitor": (45, 10000),
    "Keyboard": (8, 1000),
    "Mouse": (5, 700),
    "Headset": (8, 1500),
    "Capture Card": (20, 2500),
    "Fans": (3, 500),
    "Custom Cooling": (5, 2500),
    "Accessories": (1, 1500),
}

SPEC_LIMITS: dict[str, tuple[float, float]] = {
    "tdp_w": (3, 800),
    "board_power_w": (10, 1000),
    "continuous_wattage": (150, 2500),
    "wattage": (150, 2500),
    "length_mm": (20, 700),
    "width_mm": (10, 350),
    "height_mm": (1, 350),
    "vram_gb": (1, 256),
    "capacity_gb": (1, 262144),
    "speed_mt_s": (800, 12000),
    "speed_mhz": (800, 12000),
    "refresh_hz": (30, 1000),
    "size_in": (5, 80),
    "size_mm": (20, 1000),
}

GPU_FAMILY_PRICE_WINDOWS_USD: dict[str, tuple[float, float, float, float]] = {
    # normal low, normal high, hard low, hard high
    "NVIDIA_GEFORCE_RTX_4070_SUPER": (450, 900, 325, 1050),
}

GPU_FAMILY_PRICE_WINDOWS_SAR: dict[str, tuple[float, float, float, float]] = {
    # Saudi retail can sit above direct FX conversion because of VAT, local distribution and stock scarcity.
    "NVIDIA_GEFORCE_RTX_4070_SUPER": (1700, 3600, 1200, 4600),
}

CPU_MODEL_PRICE_WINDOWS_USD: dict[str, tuple[float, float, float, float]] = {
    # normal low, normal high, hard low, hard high
    "AMD_RYZEN_7_7800X3D": (300, 550, 220, 700),
}

CPU_MODEL_PRICE_WINDOWS_SAR: dict[str, tuple[float, float, float, float]] = {
    # Saudi retail can sit above direct FX conversion because of VAT, local distribution and stock scarcity.
    "AMD_RYZEN_7_7800X3D": (1100, 2200, 800, 3000),
}

STORAGE_MODEL_PRICE_WINDOWS_USD: dict[str, tuple[float, float, float, float]] = {
    "SAMSUNG_990_PRO_2TB_NVME_M2": (110, 260, 75, 360),
}

STORAGE_MODEL_PRICE_WINDOWS_SAR: dict[str, tuple[float, float, float, float]] = {
    # Saudi retail can vary by local stock, VAT, shipping, and warranty clarity.
    "SAMSUNG_990_PRO_2TB_NVME_M2": (450, 1200, 300, 2200),
}

RAM_FAMILY_PRICE_WINDOWS_USD: dict[str, tuple[float, float, float, float]] = {
    "RAM_DDR5_32GB_6000": (75, 190, 45, 300),
}

RAM_FAMILY_PRICE_WINDOWS_SAR: dict[str, tuple[float, float, float, float]] = {
    # Saudi RAM prices vary by local stock, RGB/EXPO binning, VAT, and warranty clarity.
    "RAM_DDR5_32GB_6000": (280, 1000, 170, 2300),
}

PSU_FAMILY_PRICE_WINDOWS_USD: dict[str, tuple[float, float, float, float]] = {
    "PSU_850W_GOLD_FULLY_MODULAR": (90, 220, 55, 350),
}

PSU_FAMILY_PRICE_WINDOWS_SAR: dict[str, tuple[float, float, float, float]] = {
    # Quality desktop PSUs are safety-critical; suspiciously low listings should be reviewed.
    "PSU_850W_GOLD_FULLY_MODULAR": (330, 950, 220, 1600),
}

REQUIRED_IDENTITY_SIGNALS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "CPU": ("model",),
    "GPU": ("model",),
    "Motherboard": ("model",),
    "RAM": ("model",),
    "Storage": ("model",),
    "PSU": ("model",),
    "Monitor": ("model",),
    "Keyboard": ("model",),
    "Mouse": ("model",),
    "Headset": ("model",),
    "Capture Card": ("model",),
}


def freshness_score(timestamp: datetime, half_life_hours: float = 24) -> float:
    now = datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    age_hours = max(0.0, (now - timestamp).total_seconds() / 3600)
    return round(exp(-age_hours / max(half_life_hours, 1)), 4)


def trusted_field_winner(candidates: list[FieldEvidence]) -> FieldEvidence | None:
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            int(item.source_tier),
            -item.trust_score,
            -item.freshness_score,
            -item.timestamp.timestamp(),
        ),
    )[0]


class PriceQualityValidator:
    def validate_offer(
        self,
        offer: PriceOffer,
        previous_price: float | None = None,
    ) -> DataQualityReport:
        rejected: list[str] = []
        flags: list[str] = list(offer.flags)
        category = offer.product.category

        if category == "Accessories" and offer.source.trust_score < 0.8:
            rejected.append("unclassified_low_trust_listing")
        if category == "GPU" and offer.product.specs.get("product_type") != "standalone_gpu":
            rejected.append("gpu_listing_not_standalone_graphics_card")
        if category == "CPU" and offer.product.specs.get("product_type") != "standalone_cpu":
            rejected.append("cpu_listing_not_standalone_processor")
        if category == "Storage" and offer.product.specs.get("product_type") != "standalone_storage":
            rejected.append("storage_listing_not_standalone_internal_ssd")
        if category == "RAM" and offer.product.specs.get("product_type") != "standalone_ram":
            rejected.append("ram_listing_not_standalone_desktop_memory_kit")
        if category == "PSU" and offer.product.specs.get("product_type") != "standalone_psu":
            rejected.append("psu_listing_not_standalone_desktop_power_supply")
        if category == "Case" and offer.product.specs.get("product_type") != "standalone_case":
            rejected.append("case_listing_not_standalone_pc_chassis")
        if category == "Cooler" and offer.product.specs.get("product_type") != "standalone_cooler":
            rejected.append("cooler_listing_not_standalone_cpu_cooler")
        if not offer.product.model or len(offer.product.normalized_model) < 3:
            rejected.append("malformed_model_name")
        for signal in REQUIRED_IDENTITY_SIGNALS_BY_CATEGORY.get(category, ()):
            if signal == "model" and not offer.product.model:
                rejected.append("incomplete_identity_model")
        if offer.currency != offer.currency.upper() or len(offer.currency) != 3:
            rejected.append("missing_or_invalid_currency")
        if offer.price <= 0:
            rejected.append("impossible_non_positive_price")

        price_limits = PRICE_LIMITS_BY_CATEGORY_USD.get(category)
        if offer.currency == "USD" and price_limits:
            low, high = price_limits
            if offer.price < low:
                rejected.append("impossible_price_below_category_floor")
            if offer.price > high:
                rejected.append("impossible_price_above_category_ceiling")

        if offer.currency == "USD" and category == "GPU":
            family_key = str(offer.product.specs.get("gpu_family_key") or "")
            if family_key in GPU_FAMILY_PRICE_WINDOWS_USD:
                normal_low, normal_high, hard_low, hard_high = GPU_FAMILY_PRICE_WINDOWS_USD[family_key]
                if offer.price < normal_low:
                    flags.append("suspicious_price_below_gpu_family_market_range")
                    flags.append("unusually_low_price")
                elif offer.price > normal_high:
                    flags.append("suspicious_price_above_gpu_family_market_range")
                    flags.append("unusually_high_price")
                if offer.price < hard_low or offer.price > hard_high:
                    rejected.append("suspicious_price_outside_gpu_family_hard_bounds")
        elif offer.currency == "SAR" and category == "GPU":
            family_key = str(offer.product.specs.get("gpu_family_key") or "")
            if family_key in GPU_FAMILY_PRICE_WINDOWS_SAR:
                normal_low, normal_high, hard_low, hard_high = GPU_FAMILY_PRICE_WINDOWS_SAR[family_key]
                if offer.price < normal_low:
                    flags.append("suspicious_price_below_gpu_family_market_range")
                    flags.append("unusually_low_price")
                elif offer.price > normal_high:
                    flags.append("suspicious_price_above_gpu_family_market_range")
                    flags.append("unusually_high_price")
                if offer.price < hard_low or offer.price > hard_high:
                    rejected.append("suspicious_price_outside_gpu_family_hard_bounds")
        elif category == "CPU":
            model_key = str(offer.product.specs.get("cpu_model_key") or "")
            windows = (
                CPU_MODEL_PRICE_WINDOWS_USD if offer.currency == "USD" else CPU_MODEL_PRICE_WINDOWS_SAR if offer.currency == "SAR" else {}
            )
            if model_key in windows:
                normal_low, normal_high, hard_low, hard_high = windows[model_key]
                if offer.price < normal_low:
                    flags.append("suspicious_price_below_cpu_model_market_range")
                    flags.append("unusually_low_price")
                elif offer.price > normal_high:
                    flags.append("suspicious_price_above_cpu_model_market_range")
                    flags.append("unusually_high_price")
                if offer.price < hard_low or offer.price > hard_high:
                    rejected.append("suspicious_price_outside_cpu_model_hard_bounds")
        elif category == "Storage":
            model_key = str(offer.product.specs.get("storage_model_key") or "")
            windows = (
                STORAGE_MODEL_PRICE_WINDOWS_USD
                if offer.currency == "USD"
                else STORAGE_MODEL_PRICE_WINDOWS_SAR
                if offer.currency == "SAR"
                else {}
            )
            if model_key in windows:
                normal_low, normal_high, hard_low, hard_high = windows[model_key]
                if offer.price < normal_low:
                    flags.append("suspicious_price_below_storage_model_market_range")
                    flags.append("unusually_low_price")
                elif offer.price > normal_high:
                    flags.append("suspicious_price_above_storage_model_market_range")
                    flags.append("unusually_high_price")
                if offer.price < hard_low or offer.price > hard_high:
                    rejected.append("suspicious_price_outside_storage_model_hard_bounds")
        elif category == "RAM":
            family_key = str(offer.product.specs.get("ram_family_key") or "")
            windows = (
                RAM_FAMILY_PRICE_WINDOWS_USD
                if offer.currency == "USD"
                else RAM_FAMILY_PRICE_WINDOWS_SAR
                if offer.currency == "SAR"
                else {}
            )
            if family_key in windows:
                normal_low, normal_high, hard_low, hard_high = windows[family_key]
                if offer.price < normal_low:
                    flags.append("suspicious_price_below_ram_family_market_range")
                    flags.append("unusually_low_price")
                elif offer.price > normal_high:
                    flags.append("suspicious_price_above_ram_family_market_range")
                    flags.append("unusually_high_price")
                if offer.price < hard_low or offer.price > hard_high:
                    rejected.append("suspicious_price_outside_ram_family_hard_bounds")
        elif category == "PSU":
            family_key = str(offer.product.specs.get("psu_family_key") or "")
            windows = (
                PSU_FAMILY_PRICE_WINDOWS_USD
                if offer.currency == "USD"
                else PSU_FAMILY_PRICE_WINDOWS_SAR
                if offer.currency == "SAR"
                else {}
            )
            if family_key in windows:
                normal_low, normal_high, hard_low, hard_high = windows[family_key]
                if offer.price < normal_low:
                    flags.append("suspicious_price_below_psu_family_market_range")
                    flags.append("suspicious_low_price")
                    flags.append("unusually_low_price")
                elif offer.price > normal_high:
                    flags.append("suspicious_price_above_psu_family_market_range")
                    flags.append("unusually_high_price")
                if offer.price < hard_low or offer.price > hard_high:
                    rejected.append("suspicious_price_outside_psu_family_hard_bounds")

        if offer.seller_type == "marketplace":
            flags.append("marketplace_listing")
        elif offer.seller_type == "third_party":
            flags.append("third_party_seller")
        if offer.listing_condition == "unknown":
            flags.append("condition_unknown")
            flags.append("price_requires_review")
        if offer.marketplace_risk_score >= 0.65:
            flags.append("price_requires_review")

        for key, value in self._flatten_specs(offer.product.specs).items():
            if key not in SPEC_LIMITS:
                continue
            number = self._as_float(value)
            if number is None:
                rejected.append(f"corrupted_{key}")
                continue
            low, high = SPEC_LIMITS[key]
            if number < low or number > high:
                rejected.append(f"impossible_{key}")

        if previous_price and previous_price > 0:
            change = (offer.price - previous_price) / previous_price
            if change <= -0.7:
                flags.append("suspicious_price_drop_over_70_percent")
            elif change >= 2.0:
                flags.append("suspicious_price_spike_over_200_percent")

        if offer.availability == "unknown":
            flags.append("availability_unknown")
        if offer.source.trust_score < 0.5:
            flags.append("low_trust_source")

        anomaly_score = min(1.0, len(flags) * 0.18 + len(rejected) * 0.34)
        return DataQualityReport(
            accepted=not rejected,
            rejected_reasons=list(dict.fromkeys(rejected)),
            flags=list(dict.fromkeys(flags)),
            anomaly_score=round(anomaly_score, 3),
        )

    def _flatten_specs(self, specs: dict[str, Any]) -> dict[str, Any]:
        flattened: dict[str, Any] = {}
        for key, value in specs.items():
            if isinstance(value, dict):
                flattened.update(self._flatten_specs(value))
            else:
                flattened[key] = value
        return flattened

    def _as_float(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
