"""
Manufacturer-authorized image source allowlist.

Each entry specifies:
- manufacturer normalized key
- official domains we are permitted to retrieve images from
- retrieval mechanism (json_ld, api, feed)
- product identity field used for matching
- rate limit (requests per minute)
- reuse/syndication basis
- attribution requirements

Rules:
- Only domains listed here are permitted sources.
- No general-purpose scraping is implemented.
- Product data is matched only via exact GTIN or exact normalized brand+MPN.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ManufacturerEntry:
    manufacturer: str
    normalized_key: str
    official_domains: tuple[str, ...]
    retrieval_mechanism: str  # "json_ld" | "feed" | "api"
    identity_field: str       # "gtin" | "brand_mpn"
    reuse_basis: str
    rate_limit_rpm: int = 10
    attribution_required: bool = False
    attribution_text: str = ""


# Allowlist — only manufacturers explicitly listed here are consulted.
# Add new entries through a code review; never auto-populate.
MANUFACTURER_ALLOWLIST: list[ManufacturerEntry] = [
    ManufacturerEntry(
        manufacturer="Intel",
        normalized_key="intel",
        official_domains=("ark.intel.com",),
        retrieval_mechanism="json_ld",
        identity_field="brand_mpn",
        reuse_basis="Intel ARK public product page JSON-LD structured data",
        rate_limit_rpm=10,
    ),
    ManufacturerEntry(
        manufacturer="AMD",
        normalized_key="amd",
        official_domains=("www.amd.com",),
        retrieval_mechanism="json_ld",
        identity_field="brand_mpn",
        reuse_basis="AMD product page JSON-LD structured data",
        rate_limit_rpm=10,
    ),
    ManufacturerEntry(
        manufacturer="NVIDIA",
        normalized_key="nvidia",
        official_domains=("www.nvidia.com",),
        retrieval_mechanism="json_ld",
        identity_field="brand_mpn",
        reuse_basis="NVIDIA product page JSON-LD structured data",
        rate_limit_rpm=10,
    ),
]

# Index by normalized_key for fast lookup
_ALLOWLIST_BY_KEY: dict[str, ManufacturerEntry] = {e.normalized_key: e for e in MANUFACTURER_ALLOWLIST}
_ALLOWED_DOMAINS: set[str] = {d for e in MANUFACTURER_ALLOWLIST for d in e.official_domains}


def get_entry(normalized_brand: str) -> ManufacturerEntry | None:
    return _ALLOWLIST_BY_KEY.get(normalized_brand.lower().strip())


def is_allowed_domain(domain: str) -> bool:
    return domain.lower().strip() in _ALLOWED_DOMAINS
