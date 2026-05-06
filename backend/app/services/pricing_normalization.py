from __future__ import annotations

import re
from typing import Any

from app.models.pricing import (
    FieldEvidence,
    PriceOffer,
    ProductIdentity,
    SourceProductRecord,
    VendorIdentity,
)
from app.services.hardware_taxonomy import classify_category, normalize_category


BRAND_ALIASES = {
    "ADVANCED MICRO DEVICES": "AMD",
    "ATI": "AMD",
    "GEFORCE": "NVIDIA",
    "NVIDIA GEFORCE": "NVIDIA",
    "INTEL CORPORATION": "Intel",
    "CORSAIR MEMORY": "Corsair",
    "G SKILL": "G.Skill",
    "G.SKILL": "G.Skill",
    "ASUSTEK": "ASUS",
    "MICRO-STAR INTERNATIONAL": "MSI",
    "WESTERN DIGITAL": "WD",
    "LOGITECH G": "Logitech",
    "HEWLETT PACKARD": "HP",
}

KNOWN_BRANDS = {
    "AMD",
    "Intel",
    "NVIDIA",
    "ASUS",
    "MSI",
    "Gigabyte",
    "ASRock",
    "Corsair",
    "G.Skill",
    "Kingston",
    "Crucial",
    "Samsung",
    "WD",
    "Western Digital",
    "Seagate",
    "EVGA",
    "Zotac",
    "PNY",
    "Sapphire",
    "PowerColor",
    "Noctua",
    "Cooler Master",
    "Lian Li",
    "Fractal Design",
    "be quiet!",
    "Thermaltake",
    "NZXT",
    "Seasonic",
    "Logitech",
    "Razer",
    "SteelSeries",
    "HyperX",
    "Elgato",
    "AverMedia",
    "BenQ",
    "AOC",
    "Alienware",
    "Dell",
    "HP",
    "LG",
    "ViewSonic",
    "Arctic",
    "EKWB",
    "EK",
    "Alphacool",
    "Bitspower",
}

MODEL_STOPWORDS = {
    "GRAPHICS",
    "CARD",
    "GPU",
    "CPU",
    "PROCESSOR",
    "DESKTOP",
    "GAMING",
    "OC",
    "EDITION",
    "BLACK",
    "WHITE",
    "RGB",
    "ARGB",
    "DDR4",
    "DDR5",
    "GDDR6",
    "GDDR6X",
    "PCIE",
    "PCI",
    "EXPRESS",
    "MOTHERBOARD",
    "MEMORY",
    "RAM",
    "NVME",
    "SSD",
    "POWER",
    "SUPPLY",
    "CASE",
    "COOLER",
    "MONITOR",
    "DISPLAY",
    "KEYBOARD",
    "MOUSE",
    "HEADSET",
    "HEADPHONES",
    "CAPTURE",
    "FAN",
    "FANS",
    "ACCESSORY",
}


def normalize_brand(value: str | None, title: str = "") -> str:
    if value:
        candidate = value.strip()
    else:
        upper_title = f" {title.upper()} "
        candidate = ""
        for brand in sorted(KNOWN_BRANDS, key=len, reverse=True):
            if f" {brand.upper()} " in upper_title:
                candidate = brand
                break
    if not candidate:
        candidate = "Unknown"
    upper = re.sub(r"[^A-Z0-9]+", " ", candidate.upper()).strip()
    return BRAND_ALIASES.get(upper, candidate.strip())


def normalize_model(value: str) -> str:
    text = value.upper()
    text = re.sub(r"([A-Z]+)(\d{3,5})(SUPER|XT|XTX|TI)?", r"\1 \2 \3", text)
    text = re.sub(r"(RTX|GTX|RX|ARC|RYZEN|CORE)\s*(\d)", r"\1 \2", text)
    text = re.sub(r"\bI\s*([3579])\s*[- ]?\s*(\d{4,5}[A-Z]*)\b", r"I\1 \2", text)
    text = re.sub(r"[^A-Z0-9+]+", " ", text)
    tokens = [token for token in text.split() if token and token not in MODEL_STOPWORDS]
    return " ".join(tokens[:12]).strip()


def compact_model(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", normalize_model(value).upper())


def extract_model(record: SourceProductRecord) -> str:
    if record.model:
        return normalize_model(record.model)
    title = record.title
    brand = normalize_brand(record.brand, title)
    cleaned = re.sub(re.escape(brand), " ", title, flags=re.IGNORECASE)
    return normalize_model(cleaned)


def infer_specs(title: str, category: str, existing: dict[str, Any]) -> dict[str, Any]:
    specs = dict(existing)
    text = title.upper()
    if category == "GPU":
        vram = re.search(r"\b(\d{1,3})\s?GB\b", text)
        if vram and "vram_gb" not in specs:
            specs["vram_gb"] = int(vram.group(1))
    elif category == "RAM":
        capacity = re.search(r"\b(\d{1,3})\s?GB\b", text)
        speed = re.search(r"\b(\d{4,5})\s?(?:MT/S|MHZ)?\b", text)
        if capacity and "capacity_gb" not in specs:
            specs["capacity_gb"] = int(capacity.group(1))
        if speed and "speed_mt_s" not in specs:
            specs["speed_mt_s"] = int(speed.group(1))
    elif category == "Storage":
        tb = re.search(r"\b(\d+(?:\.\d+)?)\s?TB\b", text)
        gb = re.search(r"\b(\d{2,5})\s?GB\b", text)
        if tb and "capacity_gb" not in specs:
            specs["capacity_gb"] = int(float(tb.group(1)) * 1024)
        elif gb and "capacity_gb" not in specs:
            specs["capacity_gb"] = int(gb.group(1))
    elif category == "PSU":
        watts = re.search(r"\b(\d{3,4})\s?W\b", text)
        if watts and "wattage" not in specs:
            specs["wattage"] = int(watts.group(1))
    elif category == "Monitor":
        size = re.search(r"\b(\d{2}(?:\.\d)?)\s?(?:INCH|\"|-INCH)\b", text)
        refresh = re.search(r"\b(\d{2,3})\s?HZ\b", text)
        if size and "size_in" not in specs:
            specs["size_in"] = float(size.group(1))
        if refresh and "refresh_hz" not in specs:
            specs["refresh_hz"] = int(refresh.group(1))
    elif category in {"Fans", "Cooler", "Custom Cooling"}:
        diameter = re.search(r"\b(80|92|120|140|200|240|280|360|420)\s?MM\b", text)
        if diameter and "size_mm" not in specs:
            specs["size_mm"] = int(diameter.group(1))
    return specs


def canonical_key(category: str, brand: str, model: str, specs: dict[str, Any]) -> str:
    disambiguators: list[str] = []
    for key in ("vram_gb", "socket", "capacity_gb", "speed_mt_s", "chipset", "wattage"):
        value = specs.get(key)
        if value is not None:
            disambiguators.append(f"{key}:{str(value).upper()}")
    base = "|".join(
        [
            category.strip().upper(),
            re.sub(r"[^A-Z0-9]+", "", brand.upper()),
            compact_model(model),
            *disambiguators,
        ]
    )
    return base


def field_evidence(record: SourceProductRecord, field: str, value: Any) -> FieldEvidence:
    return FieldEvidence(
        field=field,
        value=value,
        source=record.source.source,
        timestamp=record.source.timestamp,
        trust_score=record.source.trust_score,
        freshness_score=record.source.freshness_score,
        source_tier=record.source.tier,
    )


class CanonicalProductEngine:
    def normalize_record(self, record: SourceProductRecord) -> PriceOffer:
        brand = normalize_brand(record.brand, record.title)
        model = extract_model(record)
        category = classify_category(record.title, record.category, record.specs)
        specs = infer_specs(record.title, category, record.specs)
        identity = ProductIdentity(
            canonical_key=canonical_key(category, brand, model, specs),
            name=record.title.strip(),
            brand=brand,
            category=normalize_category(category),
            model=model,
            normalized_model=compact_model(model),
            specs=specs,
            image_url=record.image_url,
        )
        vendor_id = re.sub(
            r"[^a-z0-9]+",
            "-",
            f"{record.vendor_region}-{record.vendor_name}".lower(),
        ).strip("-")
        vendor = VendorIdentity(
            id=vendor_id,
            name=record.vendor_name,
            region=record.vendor_region,
            api_type=record.source.source_type,
            trust_score=record.source.trust_score,
        )
        evidence = [
            field_evidence(record, "name", identity.name),
            field_evidence(record, "brand", identity.brand),
            field_evidence(record, "category", identity.category),
            field_evidence(record, "model", identity.model),
            field_evidence(record, "price", record.price),
            field_evidence(record, "availability", record.availability),
        ]
        if identity.image_url:
            evidence.append(field_evidence(record, "image_url", identity.image_url))
        return PriceOffer(
            product=identity,
            vendor=vendor,
            price=record.price,
            currency=record.currency,
            availability=record.availability,
            timestamp=record.source.timestamp,
            shipping_cost=record.shipping_cost,
            product_url=record.product_url,
            image_url=record.image_url,
            source_product_id=record.source_product_id,
            seller=record.seller,
            condition=record.condition,
            rating=record.rating,
            source=record.source,
            field_evidence=evidence,
        )
