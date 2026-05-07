from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.models.region import RegionConfig, ShippingRules, SupportedRegion, WarrantyRules


DEFAULT_REGION: SupportedRegion = "SA"
SUPPORTED_REGIONS: tuple[SupportedRegion, ...] = ("SA", "AE", "US", "EU", "UK")
TrustTier = Literal["high", "medium", "low", "unknown"]


@dataclass(frozen=True)
class VendorTrustProfile:
    vendor_name: str
    region: str
    vendor_region_type: str
    trust_tier: TrustTier
    serves_saudi: bool
    local_stock_confidence: float
    warranty_confidence: float
    shipping_confidence: float
    marketplace_risk_default: float
    notes: str


REGION_CONFIGS: dict[SupportedRegion, RegionConfig] = {
    "SA": RegionConfig(
        region_code="SA",
        country_name="Saudi Arabia",
        default_city="Riyadh",
        currency="SAR",
        vat_rate=0.15,
        vat_name="VAT",
        google_domain="google.com.sa",
        gl="sa",
        hl="en",
        location="Riyadh, Saudi Arabia",
        local_vendors=[
            "Amazon.sa",
            "Noon Saudi",
            "Noon",
            "Jarir",
            "Extra",
            "Microless Saudi",
            "MTC KSA",
            "PCZone Saudi",
            "GoldenTech Saudi",
            "InfiniArc",
            "OnlyPc",
            "OnlyPc-sa",
            "Newtech Store Saudi Arabia",
            "Mahally",
        ],
        gcc_vendors=["Microless", "Microless Saudi"],
        international_vendors=["Newegg Global", "eBay", "Amazon Global"],
        local_source_targets=[
            "SerpAPI Saudi",
            "Jarir",
            "Extra",
            "Amazon.sa",
            "Noon Saudi",
            "Microless Saudi",
            "MTC KSA",
            "PCZone Saudi",
            "GoldenTech Saudi",
            "InfiniArc",
        ],
        direct_source_targets_disabled_by_default=[
            "Jarir",
            "Extra",
            "Amazon.sa",
            "Noon Saudi",
            "Microless Saudi",
            "MTC KSA",
            "PCZone Saudi",
            "GoldenTech Saudi",
            "InfiniArc",
        ],
        preferred_sources=["SerpAPI", "eBay", "BestBuy", "Amazon"],
        shipping_rules=ShippingRules(
            local_shipping_assumption="Prefer explicit Saudi local stock and delivery terms.",
            imported_shipping_assumption="Treat imported shipping as uncertain unless the source provides it.",
        ),
        warranty_rules=WarrantyRules(
            local_warranty_label="Saudi local warranty",
            imported_warranty_label="Imported or seller warranty",
        ),
    ),
    "AE": RegionConfig(
        region_code="AE",
        country_name="United Arab Emirates",
        default_city="Dubai",
        currency="AED",
        vat_rate=0.05,
        vat_name="VAT",
        google_domain="google.ae",
        gl="ae",
        hl="en",
        location="Dubai, United Arab Emirates",
        local_vendors=["Amazon.ae", "Noon UAE", "Microless", "Sharaf DG", "Virgin Megastore UAE"],
        gcc_vendors=[],
        international_vendors=["Newegg Global", "eBay", "Amazon Global"],
        preferred_sources=["SerpAPI", "eBay", "Amazon"],
        shipping_rules=ShippingRules(
            local_shipping_assumption="Prefer UAE local stock and explicit delivery terms.",
            imported_shipping_assumption="Treat imported delivery and duties as uncertain unless provided.",
        ),
        warranty_rules=WarrantyRules(
            local_warranty_label="UAE local warranty",
            imported_warranty_label="Imported or seller warranty",
        ),
    ),
    "US": RegionConfig(
        region_code="US",
        country_name="United States",
        default_city=None,
        currency="USD",
        vat_rate=None,
        tax_model="state-dependent / unknown",
        google_domain="google.com",
        gl="us",
        hl="en",
        location="United States",
        local_vendors=["BestBuy", "Best Buy", "Micro Center", "Newegg", "Amazon", "B&H", "Walmart"],
        gcc_vendors=[],
        international_vendors=["eBay"],
        preferred_sources=["SerpAPI", "eBay", "BestBuy", "Amazon"],
        shipping_rules=ShippingRules(
            local_shipping_assumption="Prefer US retailers with explicit stock and shipping.",
            imported_shipping_assumption="Treat imported shipping as uncertain unless provided.",
        ),
        warranty_rules=WarrantyRules(
            local_warranty_label="US retailer warranty",
            imported_warranty_label="Imported or seller warranty",
        ),
    ),
    "EU": RegionConfig(
        region_code="EU",
        country_name="Europe",
        default_city="Berlin",
        currency="EUR",
        vat_rate=None,
        tax_model="country-dependent EU VAT",
        google_domain="google.de",
        gl="de",
        hl="en",
        location="Berlin, Germany",
        local_vendors=["Amazon.de", "Mindfactory", "Caseking", "Alternate", "Computeruniverse"],
        gcc_vendors=[],
        international_vendors=["eBay", "Amazon Global"],
        preferred_sources=["SerpAPI", "eBay", "Amazon"],
        shipping_rules=ShippingRules(
            local_shipping_assumption="Prefer EU vendors with explicit VAT and delivery.",
            imported_shipping_assumption="Treat non-EU import fees as uncertain unless provided.",
        ),
        warranty_rules=WarrantyRules(
            local_warranty_label="EU retailer warranty",
            imported_warranty_label="Imported or seller warranty",
        ),
    ),
    "UK": RegionConfig(
        region_code="UK",
        country_name="United Kingdom",
        default_city="London",
        currency="GBP",
        vat_rate=0.20,
        vat_name="VAT",
        google_domain="google.co.uk",
        gl="uk",
        hl="en",
        location="London, United Kingdom",
        local_vendors=["Amazon UK", "Scan", "Overclockers UK", "Currys", "CCL", "Ebuyer"],
        gcc_vendors=[],
        international_vendors=["eBay", "Amazon Global"],
        preferred_sources=["SerpAPI", "eBay", "Amazon"],
        shipping_rules=ShippingRules(
            local_shipping_assumption="Prefer UK local stock with explicit VAT and delivery.",
            imported_shipping_assumption="Treat import fees as uncertain unless provided.",
        ),
        warranty_rules=WarrantyRules(
            local_warranty_label="UK retailer warranty",
            imported_warranty_label="Imported or seller warranty",
        ),
    ),
}


def normalize_region(region: str | None) -> SupportedRegion:
    value = (region or DEFAULT_REGION).strip().upper()
    if value == "GB":
        value = "UK"
    if value in REGION_CONFIGS:
        return value  # type: ignore[return-value]
    raise ValueError(f"Unsupported market region '{region}'. Supported regions: {', '.join(SUPPORTED_REGIONS)}.")


def get_region_config(region: str | None) -> RegionConfig:
    return REGION_CONFIGS[normalize_region(region)]


def vendor_region_type(vendor_name: str | None, region: str | None) -> str:
    config = get_region_config(region)
    normalized_vendor = _compact(vendor_name or "")
    if not normalized_vendor:
        return "unknown_vendor"
    if _infiniarc_looks_saudi_or_gcc(vendor_name or ""):
        return "local_saudi_vendor"
    if any(_compact(vendor) in normalized_vendor for vendor in config.local_vendors):
        return "local_saudi_vendor" if config.region_code == "SA" else "local"
    if any(_compact(vendor) in normalized_vendor for vendor in config.gcc_vendors):
        return "gcc_vendor"
    if any(_compact(vendor) in normalized_vendor for vendor in config.international_vendors):
        return "international_vendor"
    if any(token in normalized_vendor for token in ("EBAY", "SWAPPA")):
        return "marketplace_vendor"
    return "unknown_vendor"


def serves_saudi(vendor_name: str | None, region: str | None) -> bool:
    region_type = vendor_region_type(vendor_name, region)
    return normalize_region(region) == "SA" and region_type in {"local_saudi_vendor", "gcc_vendor"}


def vendor_trust_profile(vendor_name: str | None, region: str | None) -> VendorTrustProfile:
    config = get_region_config(region)
    name = (vendor_name or "Unknown Vendor").strip() or "Unknown Vendor"
    compact = _compact(name)
    region_type = vendor_region_type(name, config.region_code)

    if config.region_code == "SA":
        local_high = {
            "AMAZONSA",
            "JARIR",
            "EXTRA",
        }
        local_medium = {
            "NOON",
            "NOONSAUDI",
            "INFINIARC",
            "MTCKSA",
            "PCZONESAUDI",
            "GOLDENTECHSAUDI",
            "ONLYPC",
            "ONLYPCSA",
            "NEWTECH",
            "NEWTECHSTORESAUDIARABIA",
            "MAHALLY",
        }
        gcc_medium = {"MICROLESS", "MICROLESSSAUDI"}
        if any(key in compact for key in local_high):
            return VendorTrustProfile(
                vendor_name=name,
                region=config.region_code,
                vendor_region_type="local_saudi_vendor",
                trust_tier="high",
                serves_saudi=True,
                local_stock_confidence=0.92,
                warranty_confidence=0.78,
                shipping_confidence=0.78,
                marketplace_risk_default=0.18,
                notes="Initial Saudi local retailer trust heuristic; verify VAT, warranty, and seller details per listing.",
            )
        if any(key in compact for key in local_medium):
            return VendorTrustProfile(
                vendor_name=name,
                region=config.region_code,
                vendor_region_type="local_saudi_vendor",
                trust_tier="medium",
                serves_saudi=True,
                local_stock_confidence=0.82,
                warranty_confidence=0.64,
                shipping_confidence=0.62,
                marketplace_risk_default=0.38 if "MAHALLY" in compact else 0.28,
                notes="Local or local-serving Saudi vendor heuristic; confidence remains conditional on listing metadata.",
            )
        if any(key in compact for key in gcc_medium):
            return VendorTrustProfile(
                vendor_name=name,
                region=config.region_code,
                vendor_region_type="gcc_vendor",
                trust_tier="medium",
                serves_saudi=True,
                local_stock_confidence=0.72,
                warranty_confidence=0.56,
                shipping_confidence=0.58,
                marketplace_risk_default=0.34,
                notes="GCC local-serving vendor; shipping and warranty clarity affect recommendation level.",
            )
        if "EBAY" in compact:
            return VendorTrustProfile(
                vendor_name=name,
                region=config.region_code,
                vendor_region_type="international_vendor",
                trust_tier="low",
                serves_saudi=False,
                local_stock_confidence=0.18,
                warranty_confidence=0.28,
                shipping_confidence=0.24,
                marketplace_risk_default=0.86,
                notes="International marketplace listing; do not recommend over trusted local options without strong evidence.",
            )
        if "NEWEGG" in compact or "AMAZONGLOBAL" in compact:
            return VendorTrustProfile(
                vendor_name=name,
                region=config.region_code,
                vendor_region_type="international_vendor",
                trust_tier="low",
                serves_saudi=False,
                local_stock_confidence=0.24,
                warranty_confidence=0.34,
                shipping_confidence=0.32,
                marketplace_risk_default=0.64,
                notes="Imported listing; final landed cost and local warranty are uncertain unless the source proves them.",
            )

    if region_type in {"local_saudi_vendor", "local"}:
        return VendorTrustProfile(
            vendor_name=name,
            region=config.region_code,
            vendor_region_type=region_type,
            trust_tier="medium",
            serves_saudi=config.region_code == "SA",
            local_stock_confidence=0.74,
            warranty_confidence=0.58,
            shipping_confidence=0.58,
            marketplace_risk_default=0.32,
            notes="Configured local vendor heuristic.",
        )
    if region_type == "gcc_vendor":
        return VendorTrustProfile(
            vendor_name=name,
            region=config.region_code,
            vendor_region_type=region_type,
            trust_tier="medium",
            serves_saudi=config.region_code == "SA",
            local_stock_confidence=0.68,
            warranty_confidence=0.52,
            shipping_confidence=0.52,
            marketplace_risk_default=0.38,
            notes="Configured regional vendor heuristic.",
        )
    if region_type in {"international_vendor", "marketplace_vendor"}:
        return VendorTrustProfile(
            vendor_name=name,
            region=config.region_code,
            vendor_region_type=region_type,
            trust_tier="low",
            serves_saudi=False,
            local_stock_confidence=0.25,
            warranty_confidence=0.3,
            shipping_confidence=0.3,
            marketplace_risk_default=0.72 if region_type == "marketplace_vendor" else 0.58,
            notes="Imported or marketplace listing heuristic; keep uncertainty visible.",
        )
    return VendorTrustProfile(
        vendor_name=name,
        region=config.region_code,
        vendor_region_type=region_type,
        trust_tier="unknown",
        serves_saudi=False,
        local_stock_confidence=0.25,
        warranty_confidence=0.24,
        shipping_confidence=0.22,
        marketplace_risk_default=0.5,
        notes="Unknown vendor; recommendation requires stronger listing evidence.",
    )


def _infiniarc_looks_saudi_or_gcc(value: str) -> bool:
    normalized = _compact(value)
    if "INFINIARC" not in normalized:
        return False
    return True


def _compact(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())
