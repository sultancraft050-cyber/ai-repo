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
    "refresh_hz": (30, 1000),
    "size_in": (5, 80),
    "size_mm": (20, 1000),
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
        flags: list[str] = []
        category = offer.product.category

        if category == "Accessories" and offer.source.trust_score < 0.8:
            rejected.append("unclassified_low_trust_listing")
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
            rejected_reasons=rejected,
            flags=flags,
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
