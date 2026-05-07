from __future__ import annotations

from dataclasses import dataclass, field
import re

from app.models.pricing import SourceProductRecord
from app.services.hardware_taxonomy import normalize_category


@dataclass(frozen=True)
class ProductTypeClassification:
    product_type: str
    confidence: float
    accepted: bool
    rejected_reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ListingMarketClassification:
    listing_condition: str
    seller_type: str
    marketplace_risk_score: float
    flags: list[str] = field(default_factory=list)


GPU_POSITIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bgraphics\s+card\b", "graphics_card_signal"),
    (r"\bgraphic\s+card\b", "graphics_card_signal"),
    (r"\bvideo\s+card\b", "video_card_signal"),
    (r"\bgpu\b", "gpu_signal"),
    (r"\bgeforce\b", "geforce_signal"),
    (r"\bradeon\b", "radeon_signal"),
    (r"\bgddr6x?\b", "gddr_signal"),
    (r"\bvram\b", "vram_signal"),
    (r"\b(?:8|10|11|12|16|20|24|32|48)\s?gb\b", "gpu_vram_capacity_signal"),
    (r"\bpci(?:e|\s+express)\b", "pcie_signal"),
    (r"\brtx\s?\d{3,5}\b", "rtx_model_signal"),
    (r"\bgtx\s?\d{3,5}\b", "gtx_model_signal"),
    (r"\brx\s?\d{3,4}\b", "radeon_model_signal"),
)

GPU_ACCESSORY_PATTERNS: tuple[str, ...] = (
    r"\bsupport\s+bracket\b",
    r"\banti[- ]?sag\b",
    r"\briser\s+cable\b",
    r"\bbackplate\b",
    r"\bwater\s+block\b",
    r"\breplacement\s+fan\b",
    r"\bshroud\b",
    r"\bmount(?:ing)?\s+kit\b",
    r"\badapter\b",
)

GPU_LAPTOP_PATTERNS: tuple[str, ...] = (
    r"\blaptop\b",
    r"\bnotebook\b",
    r"\bmobile\s+workstation\b",
)

GPU_PREBUILT_PATTERNS: tuple[str, ...] = (
    r"\bgaming\s+pc\b",
    r"\bdesktop\s+(?:pc|computer)\b",
    r"\bcomputer\b",
    r"\btower\b",
    r"\bprebuilt\b",
    r"\bfull\s+system\b",
    r"\bworkstation\b",
    r"\bwindows\s+\d{1,2}\b",
)

GPU_SOFT_SYSTEM_PATTERNS: tuple[str, ...] = (
    r"\bdesktop\b",
    r"\bsystem\b",
)

GPU_BUNDLE_PATTERNS: tuple[str, ...] = (
    r"\bcombo\b",
    r"\bbundle\b",
    r"\bryzen\s+[579]\b",
    r"\b(?:intel\s+)?(?:core\s+)?i[3579]\b",
    r"\b\d+(?:\.\d+)?\s?tb\s+ssd\b",
    r"\b\d{3,5}\s?gb\s+ssd\b",
    r"\bssd\b",
    r"\b\d+\s?gb\s+ddr[45]\b",
    r"\bddr[45]\s+memory\b",
    r"\b\d+\s?gb\s+(?:ram|memory)\b",
    r"\bram\b",
)

CPU_POSITIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bprocessor\b", "processor_signal"),
    (r"\bcpu\b", "cpu_signal"),
    (r"\bryzen\b", "ryzen_signal"),
    (r"\b7800\s?x3d\b", "7800x3d_signal"),
    (r"\b(?:core\s+)?i[3579][-\s]?\d{4,5}[a-z]*\b", "intel_core_model_signal"),
    (r"\bthreadripper\b", "threadripper_signal"),
    (r"\bxeon\b", "xeon_signal"),
    (r"\bam5\b", "cpu_socket_signal"),
    (r"\blga\s?1700\b", "cpu_socket_signal"),
)

CPU_PREBUILT_PATTERNS: tuple[str, ...] = (
    r"\bgaming\s+pc\b",
    r"\bdesktop\s+(?:pc|computer)\b",
    r"\bcomputer\b",
    r"\btower\b",
    r"\bprebuilt\b",
    r"\bfull\s+system\b",
    r"\bworkstation\b",
    r"\blaptop\b",
    r"\bnotebook\b",
    r"\bwindows\s+\d{1,2}\b",
)

CPU_MOTHERBOARD_PATTERNS: tuple[str, ...] = (
    r"\bmotherboard\b",
    r"\bmainboard\b",
    r"\b(?:b650|x670|x870|a620|z790|b760|h770)\b",
)

CPU_COOLER_PATTERNS: tuple[str, ...] = (
    r"\bcooler\b",
    r"\bheatsink\b",
    r"\baio\b",
    r"\bliquid\s+cool",
    r"\bwater\s+block\b",
    r"\bthermal\s+paste\b",
)

CPU_TRAY_UNCLEAR_PATTERNS: tuple[str, ...] = (
    r"\btray\b",
    r"\boem\b",
    r"\bengineering\s+sample\b",
    r"\bes\b",
)

CPU_BUNDLE_PATTERNS: tuple[str, ...] = (
    r"\bcombo\b",
    r"\bbundle\b",
    r"\bkit\b",
    r"\bddr[45]\b",
    r"\bmemory\b",
    r"\bram\b",
    r"\bssd\b",
    r"\bgraphics\s+card\b",
    r"\bgpu\b",
    r"\brtx\s?\d{3,5}\b",
    r"\bradeon\b",
)

STORAGE_POSITIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bnvme\b", "nvme_signal"),
    (r"\bm\.?2\b", "m2_signal"),
    (r"\bssd\b", "ssd_signal"),
    (r"\bsolid\s+state\b", "solid_state_signal"),
    (r"\binternal\s+ssd\b", "internal_ssd_signal"),
    (r"\bpci(?:e|\s+express)\b", "pcie_signal"),
    (r"\b2280\b", "m2_2280_signal"),
    (r"\b(?:1|2|4|8)\s?tb\b", "storage_capacity_signal"),
    (r"\b\d{3,5}\s?gb\b", "storage_capacity_signal"),
)

STORAGE_PREBUILT_PATTERNS: tuple[str, ...] = (
    r"\bgaming\s+pc\b",
    r"\bdesktop\s+(?:pc|computer)\b",
    r"\bcomputer\b",
    r"\btower\b",
    r"\bprebuilt\b",
    r"\bfull\s+system\b",
    r"\bworkstation\b",
    r"\blaptop\b",
    r"\bnotebook\b",
    r"\bwindows\s+\d{1,2}\b",
)

STORAGE_EXTERNAL_PATTERNS: tuple[str, ...] = (
    r"\bexternal\b",
    r"\benclosure\b",
    r"\bportable\b",
    r"\busb\b",
    r"\bthumb\s+drive\b",
    r"\bflash\s+drive\b",
)

STORAGE_BUNDLE_PATTERNS: tuple[str, ...] = (
    r"\bcombo\b",
    r"\bbundle\b",
    r"\bkit\b",
    r"\bmotherboard\b",
    r"\b(?:b650|x670|x870|a620|z790|b760|h770)\b",
    r"\bddr[45]\b",
    r"\bmemory\b",
    r"\bram\b",
    r"\b(?:ryzen|core\s+i[3579]|intel\s+i[3579])\b",
    r"\brtx\s?\d{3,5}\b",
    r"\bgpu\b",
)

STORAGE_WRONG_KIND_PATTERNS: tuple[str, ...] = (
    r"\bhdd\b",
    r"\bhard\s+drive\b",
    r"\bsata\b",
)

STORAGE_USED_OR_REFURB_PATTERNS: tuple[str, ...] = (
    r"\bused\b",
    r"\bpre[\s-]?owned\b",
    r"\brefurbished\b",
    r"\brefurb\b",
    r"\brenewed\b",
)

RAM_POSITIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bddr5\b", "ddr5_signal"),
    (r"\b(?:ram|memory)\b", "memory_signal"),
    (r"\bmemory\s+kit\b", "memory_kit_signal"),
    (r"\bdimm\b", "desktop_dimm_signal"),
    (r"\b(?:2\s?x\s?16|2x16)\s?gb?\b", "kit_2x16_signal"),
    (r"\b32\s?gb\b", "capacity_32gb_signal"),
    (r"\b6000\s?(?:mhz|mt/s|mt)?\b", "speed_6000_signal"),
    (r"\bcl\s?(?:28|30|32|34|36|38|40)\b", "cas_latency_signal"),
)

RAM_PREBUILT_PATTERNS: tuple[str, ...] = (
    r"\bgaming\s+pc\b",
    r"\bdesktop\s+computer\b",
    r"\bprebuilt\b",
    r"\bfull\s+system\b",
    r"\bworkstation\b",
    r"\blaptop\b",
    r"\bnotebook\b",
)

RAM_LAPTOP_PATTERNS: tuple[str, ...] = (
    r"\bso[- ]?dimm\b",
    r"\bsodimm\b",
    r"\blaptop\s+memory\b",
    r"\bnotebook\s+memory\b",
)

RAM_BUNDLE_PATTERNS: tuple[str, ...] = (
    r"\bmotherboard\s+bundle\b",
    r"\bmotherboard\b",
    r"\b(?:b650|x670|x870|a620|z790|b760|h770)\b",
    r"\bcombo\b",
    r"\bbundle\b",
    r"\b(?:ryzen|core\s+i[3579]|intel\s+i[3579])\b",
    r"\bssd\b",
    r"\brtx\s?\d{3,5}\b",
    r"\bgpu\b",
)

RAM_ACCESSORY_PATTERNS: tuple[str, ...] = (
    r"\brgb\s+controller\b",
    r"\blighting\s+controller\b",
    r"\bcontroller\b",
    r"\baccessory\b",
    r"\bheatsink\s+only\b",
)

RAM_USED_OR_REFURB_PATTERNS: tuple[str, ...] = (
    r"\bused\b",
    r"\bpre[\s-]?owned\b",
    r"\brefurbished\b",
    r"\brefurb\b",
    r"\brenewed\b",
)

PSU_POSITIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bpower\s+supply\b", "power_supply_signal"),
    (r"\bpsu\b", "psu_signal"),
    (r"\b(?:550|650|750|850|1000|1200)\s?w\b", "psu_wattage_signal"),
    (r"\b80\s?\+\b", "80_plus_signal"),
    (r"\b80\s+plus\b", "80_plus_signal"),
    (r"\bgold\b", "gold_efficiency_signal"),
    (r"\bfully\s+modular\b", "fully_modular_signal"),
    (r"\bfull\s+modular\b", "fully_modular_signal"),
    (r"\bmodular\b", "modular_signal"),
    (r"\batx\s?3(?:\.0|\.1)?\b", "atx3_signal"),
    (r"\bpcie\s?5(?:\.0)?\b", "pcie5_signal"),
    (r"\b12vhpwr\b", "12vhpwr_signal"),
    (r"\brm850[xe]\b", "known_psu_model_signal"),
    (r"\bfocus\s+gx[- ]?850\b", "known_psu_model_signal"),
    (r"\bmag\s+a850gl\b", "known_psu_model_signal"),
    (r"\btoughpower\s+gf\b", "known_psu_model_signal"),
)

PSU_UPS_PATTERNS: tuple[str, ...] = (
    r"\bups\b",
    r"\bbattery\s+backup\b",
    r"\buninterruptible\b",
)

PSU_CHARGER_ADAPTER_PATTERNS: tuple[str, ...] = (
    r"\blaptop\s+charger\b",
    r"\bcharger\b",
    r"\badapter\b",
    r"\bac\s+adapter\b",
    r"\bdc\s+adapter\b",
)

PSU_CABLE_ACCESSORY_PATTERNS: tuple[str, ...] = (
    r"\bcable\b",
    r"\bextension\b",
    r"\bpower\s+strip\b",
    r"\brgb\s+cable\b",
    r"\bsleeved\s+cable\b",
    r"\bconnector\b",
)

PSU_CASE_BUNDLE_PATTERNS: tuple[str, ...] = (
    r"\bcase\s+with\s+(?:psu|power\s+supply)\b",
    r"\b(?:psu|power\s+supply)\s+included\b",
    r"\bchassis\s+with\s+(?:psu|power\s+supply)\b",
)

PSU_USED_OR_REFURB_PATTERNS: tuple[str, ...] = (
    r"\bused\b",
    r"\bpre[\s-]?owned\b",
    r"\brefurbished\b",
    r"\brefurb\b",
    r"\brenewed\b",
)

CASE_POSITIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bpc\s+case\b", "pc_case_signal"),
    (r"\bcomputer\s+case\b", "pc_case_signal"),
    (r"\bcase\b", "case_signal"),
    (r"\bchassis\b", "chassis_signal"),
    (r"\batx\b", "atx_signal"),
    (r"\bmid\s+tower\b", "mid_tower_signal"),
    (r"\bfull\s+tower\b", "full_tower_signal"),
    (r"\bmini[- ]?itx\b", "mini_itx_signal"),
    (r"\bairflow\b", "airflow_signal"),
    (r"\btempered\s+glass\b", "tempered_glass_signal"),
    (r"\b4000d\b", "4000d_signal"),
)

CASE_PREBUILT_PATTERNS: tuple[str, ...] = (
    r"\bgaming\s+pc\b",
    r"\bdesktop\s+pc\b",
    r"\bdesktop\s+computer\b",
    r"\bprebuilt\b",
    r"\bfull\s+build\b",
    r"\bworkstation\s+system\b",
    r"\bbarebone\s+system\b",
)

CASE_ACCESSORY_PATTERNS: tuple[str, ...] = (
    r"\bfan\s+only\b",
    r"\bcase\s+fan\b",
    r"\brgb\s+controller\b",
    r"\blighting\s+controller\b",
    r"\bcontroller\b",
    r"\bpower\s+supply\s+only\b",
    r"\bpsu\s+only\b",
    r"\blaptop\s+bag\b",
    r"\benclosure\b",
    r"\bexternal\s+enclosure\b",
    r"\bserver\s+rack\b",
)

CASE_BUNDLE_PATTERNS: tuple[str, ...] = (
    r"\bbundle\b",
    r"\bcombo\b",
    r"\bwith\s+(?:motherboard|cpu|processor|ram|memory|ssd|gpu|graphics\s+card)\b",
)

COOLER_POSITIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bcpu\s+cooler\b", "cpu_cooler_signal"),
    (r"\baio\b", "aio_signal"),
    (r"\bliquid\s+(?:cpu\s+)?cooler\b", "liquid_cooler_signal"),
    (r"\bliquid\s+cooling\b", "liquid_cooling_signal"),
    (r"\bwater\s+cooler\b", "liquid_cooler_signal"),
    (r"\bair\s+cooler\b", "air_cooler_signal"),
    (r"\b240\s?mm\b", "radiator_240mm_signal"),
    (r"\b(?:am5|am4|lga\s?1700)\b", "socket_signal"),
    (r"\bh100i\b", "known_cooler_model_signal"),
    (r"\bls520\b", "known_cooler_model_signal"),
    (r"\bcoreliquid\b", "known_cooler_model_signal"),
    (r"\bnautilus\s+240\b", "known_cooler_model_signal"),
    (r"\bkraken\s+240\b", "known_cooler_model_signal"),
    (r"\bkraken\s+(?:core|elite)\b", "known_cooler_model_signal"),
    (r"\bliquid\s+freezer\s+(?:iii|3)\s+240\b", "known_cooler_model_signal"),
    (r"\bpeerless\s+assassin\b", "known_cooler_model_signal"),
    (r"\bak620\b", "known_cooler_model_signal"),
)

COOLER_ACCESSORY_PATTERNS: tuple[str, ...] = (
    r"\bcase\s+fan\b",
    r"\bfan\s+only\b",
    r"\bcooling\s+pad\b",
    r"\blaptop\s+cooler\b",
    r"\bthermal\s+paste\b",
    r"\bcontroller\b",
    r"\brgb\s+controller\b",
    r"\bfan\s+controller\b",
    r"\bfitting\b",
    r"\btube\b",
    r"\breservoir\s+only\b",
    r"\bradiator\s+only\b",
    r"\bgpu\s+cooler\b",
    r"\bcase\s+included\b",
)

COOLER_CASE_PATTERNS: tuple[str, ...] = (
    r"\bpc\s+case\b",
    r"\bcomputer\s+case\b",
    r"\bchassis\b",
    r"\bcase\s+with\s+fans?\b",
)

MOTHERBOARD_POSITIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bmotherboard\b", "motherboard_signal"),
    (r"\bmainboard\b", "motherboard_signal"),
    (r"\bb650\b", "b650_chipset_signal"),
    (r"\bb650m\b", "b650_chipset_signal"),
    (r"\bam5\b", "am5_socket_signal"),
    (r"\bddr5\b", "ddr5_memory_signal"),
    (r"\batx\b", "atx_form_factor_signal"),
    (r"\bm[- ]?atx\b", "matx_form_factor_signal"),
    (r"\bmicro[- ]?atx\b", "matx_form_factor_signal"),
    (r"\bmini[- ]?itx\b", "itx_form_factor_signal"),
    (r"\bwi[- ]?fi\b", "wifi_signal"),
    (r"\bprime\s+b650m[- ]?a\s+wi[- ]?fi\s+ii\b", "known_motherboard_model_signal"),
    (r"\baorus\s+elite\b", "known_motherboard_model_signal"),
    (r"\btomahawk\b", "known_motherboard_model_signal"),
    (r"\btuf\s+gaming\b", "known_motherboard_model_signal"),
    (r"\bsteel\s+legend\b", "known_motherboard_model_signal"),
)

MOTHERBOARD_WRONG_PLATFORM_PATTERNS: tuple[str, ...] = (
    r"\bintel\b",
    r"\blga\s?1700\b",
    r"\bz690\b",
    r"\bz790\b",
    r"\bb760\b",
    r"\bh610\b",
    r"\bddr4\b",
    r"\ba620\b",
)

MOTHERBOARD_BUNDLE_SYSTEM_PATTERNS: tuple[str, ...] = (
    r"\bcombo\b",
    r"\bbundle\b",
    r"\bgaming\s+pc\b",
    r"\bdesktop\s+pc\b",
    r"\bdesktop\s+computer\b",
    r"\bprebuilt\b",
    r"\bfull\s+build\b",
    r"\blaptop\b",
    r"\bmini\s+pc\b",
)

MOTHERBOARD_ACCESSORY_PATTERNS: tuple[str, ...] = (
    r"\bserver\b",
    r"\bbackplate\b",
    r"\bio\s+shield\s+only\b",
    r"\bbox\s+only\b",
    r"\baccessory\b",
)

MARKETPLACE_VENDOR_PATTERNS: tuple[str, ...] = (
    "swappa",
    "ebay",
    "mercari",
    "stockx",
    "facebook marketplace",
)

TRUSTED_RETAILER_PATTERNS: tuple[str, ...] = (
    "bestbuy",
    "best buy",
    "micro center",
    "b&h",
    "bh photo",
    "newegg",
    "amazon",
)

MANUFACTURER_PATTERNS: tuple[str, ...] = (
    "nvidia",
    "amd",
    "asus",
    "msi",
    "gigabyte",
    "zotac",
    "pny",
    "sapphire",
    "powercolor",
)


def classify_product_type(record: SourceProductRecord, requested_category: str | None = None) -> ProductTypeClassification:
    category = normalize_category(requested_category or record.category)
    if category == "CPU":
        return _classify_cpu_product_type(record)
    if category == "Storage":
        return _classify_storage_product_type(record)
    if category == "RAM":
        return _classify_ram_product_type(record)
    if category == "PSU":
        return _classify_psu_product_type(record)
    if category == "Case":
        return _classify_case_product_type(record)
    if category == "Cooler":
        return _classify_cooler_product_type(record)
    if category == "Motherboard":
        return _classify_motherboard_product_type(record)
    if category != "GPU":
        return ProductTypeClassification(
            product_type="hardware_product",
            confidence=0.7,
            accepted=True,
        )

    text = _normalized_text(record.title)
    positive_signals = _matched_labels(text, GPU_POSITIVE_PATTERNS)
    has_standalone_phrase = bool(
        re.search(r"\b(?:graphics\s+card|video\s+card|pci(?:e|\s+express))\b", text)
    )

    accessory_matches = _matched_patterns(text, GPU_ACCESSORY_PATTERNS)
    if accessory_matches and not has_standalone_phrase:
        return ProductTypeClassification(
            product_type="accessory",
            confidence=0.88,
            accepted=False,
            rejected_reasons=["gpu_listing_is_accessory"],
            flags=[*positive_signals],
        )

    if _matched_patterns(text, GPU_LAPTOP_PATTERNS):
        return ProductTypeClassification(
            product_type="laptop",
            confidence=0.96,
            accepted=False,
            rejected_reasons=["gpu_listing_is_laptop"],
            flags=[*positive_signals],
        )

    prebuilt_matches = _matched_patterns(text, GPU_PREBUILT_PATTERNS)
    soft_system_matches = _matched_patterns(text, GPU_SOFT_SYSTEM_PATTERNS)
    if prebuilt_matches or (soft_system_matches and not has_standalone_phrase):
        return ProductTypeClassification(
            product_type="prebuilt_pc",
            confidence=0.94,
            accepted=False,
            rejected_reasons=["gpu_listing_is_full_system_or_prebuilt_pc"],
            flags=[*positive_signals],
        )

    bundle_matches = _matched_patterns(text, GPU_BUNDLE_PATTERNS)
    if bundle_matches:
        return ProductTypeClassification(
            product_type="bundle",
            confidence=0.9,
            accepted=False,
            rejected_reasons=["gpu_listing_contains_cpu_ram_storage_or_bundle_signals"],
            flags=[*positive_signals],
        )

    if not positive_signals:
        return ProductTypeClassification(
            product_type="unknown_low_confidence",
            confidence=0.36,
            accepted=False,
            rejected_reasons=["gpu_listing_lacks_standalone_gpu_evidence"],
        )

    confidence = min(0.98, 0.68 + len(set(positive_signals)) * 0.06)
    return ProductTypeClassification(
        product_type="standalone_gpu",
        confidence=round(confidence, 2),
        accepted=True,
        flags=positive_signals,
    )


def _classify_cpu_product_type(record: SourceProductRecord) -> ProductTypeClassification:
    text = _normalized_text(record.title)
    positive_signals = _matched_labels(text, CPU_POSITIVE_PATTERNS)

    if _matched_patterns(text, CPU_PREBUILT_PATTERNS):
        return ProductTypeClassification(
            product_type="prebuilt_pc",
            confidence=0.95,
            accepted=False,
            rejected_reasons=["cpu_listing_is_full_system_or_prebuilt_pc"],
            flags=[*positive_signals],
        )

    bundle_matches = _matched_patterns(text, CPU_BUNDLE_PATTERNS)
    motherboard_matches = _matched_patterns(text, CPU_MOTHERBOARD_PATTERNS)
    cooler_matches = _matched_patterns(text, CPU_COOLER_PATTERNS)
    tray_unclear_matches = _matched_patterns(text, CPU_TRAY_UNCLEAR_PATTERNS)
    if bundle_matches and (motherboard_matches or cooler_matches or len(bundle_matches) >= 2):
        return ProductTypeClassification(
            product_type="bundle",
            confidence=0.9,
            accepted=False,
            rejected_reasons=["cpu_listing_contains_bundle_or_extra_component_signals"],
            flags=[*positive_signals],
        )
    if motherboard_matches:
        return ProductTypeClassification(
            product_type="motherboard",
            confidence=0.9,
            accepted=False,
            rejected_reasons=["cpu_listing_is_motherboard_not_processor"],
            flags=[*positive_signals],
        )
    if cooler_matches:
        return ProductTypeClassification(
            product_type="cooler",
            confidence=0.9,
            accepted=False,
            rejected_reasons=["cpu_listing_is_cooler_not_processor"],
            flags=[*positive_signals],
        )
    if tray_unclear_matches and _listing_condition(record.condition, record.title) == "unknown":
        return ProductTypeClassification(
            product_type="unknown_low_confidence",
            confidence=0.82,
            accepted=False,
            rejected_reasons=["cpu_tray_or_engineering_sample_condition_unclear"],
            flags=[*positive_signals, "tray_or_oem_unclear"],
        )
    if not positive_signals:
        return ProductTypeClassification(
            product_type="unknown_low_confidence",
            confidence=0.34,
            accepted=False,
            rejected_reasons=["cpu_listing_lacks_standalone_processor_evidence"],
        )

    confidence = min(0.98, 0.66 + len(set(positive_signals)) * 0.06)
    return ProductTypeClassification(
        product_type="standalone_cpu",
        confidence=round(confidence, 2),
        accepted=True,
        flags=positive_signals,
    )


def _classify_storage_product_type(record: SourceProductRecord) -> ProductTypeClassification:
    text = _normalized_text(record.title)
    positive_signals = _matched_labels(text, STORAGE_POSITIVE_PATTERNS)

    if _matched_patterns(text, STORAGE_PREBUILT_PATTERNS):
        return ProductTypeClassification(
            product_type="prebuilt_pc",
            confidence=0.94,
            accepted=False,
            rejected_reasons=["storage_listing_is_full_system_or_laptop"],
            flags=[*positive_signals],
        )
    if _matched_patterns(text, STORAGE_EXTERNAL_PATTERNS):
        return ProductTypeClassification(
            product_type="accessory",
            confidence=0.9,
            accepted=False,
            rejected_reasons=["storage_listing_is_external_drive_or_enclosure"],
            flags=[*positive_signals],
        )
    if _matched_patterns(text, STORAGE_BUNDLE_PATTERNS):
        return ProductTypeClassification(
            product_type="bundle",
            confidence=0.9,
            accepted=False,
            rejected_reasons=["storage_listing_contains_bundle_or_extra_component_signals"],
            flags=[*positive_signals],
        )
    if _matched_patterns(text, STORAGE_WRONG_KIND_PATTERNS):
        return ProductTypeClassification(
            product_type="unknown_low_confidence",
            confidence=0.86,
            accepted=False,
            rejected_reasons=["storage_listing_is_not_ssd_or_nvme_target"],
            flags=[*positive_signals],
        )
    if _matched_patterns(text, STORAGE_USED_OR_REFURB_PATTERNS):
        return ProductTypeClassification(
            product_type="unknown_low_confidence",
            confidence=0.82,
            accepted=False,
            rejected_reasons=["storage_listing_condition_is_used_or_refurbished"],
            flags=[*positive_signals],
        )
    if not positive_signals:
        return ProductTypeClassification(
            product_type="unknown_low_confidence",
            confidence=0.34,
            accepted=False,
            rejected_reasons=["storage_listing_lacks_standalone_ssd_evidence"],
        )

    confidence = min(0.98, 0.66 + len(set(positive_signals)) * 0.06)
    return ProductTypeClassification(
        product_type="standalone_storage",
        confidence=round(confidence, 2),
        accepted=True,
        flags=positive_signals,
    )


def _classify_ram_product_type(record: SourceProductRecord) -> ProductTypeClassification:
    text = _normalized_text(record.title)
    positive_signals = _matched_labels(text, RAM_POSITIVE_PATTERNS)

    if _matched_patterns(text, RAM_LAPTOP_PATTERNS):
        return ProductTypeClassification(
            product_type="laptop",
            confidence=0.92,
            accepted=False,
            rejected_reasons=["ram_listing_is_laptop_sodimm_memory"],
            flags=[*positive_signals],
        )
    if _matched_patterns(text, RAM_PREBUILT_PATTERNS):
        return ProductTypeClassification(
            product_type="prebuilt_pc",
            confidence=0.94,
            accepted=False,
            rejected_reasons=["ram_listing_is_full_system_or_laptop"],
            flags=[*positive_signals],
        )
    if _matched_patterns(text, RAM_BUNDLE_PATTERNS):
        return ProductTypeClassification(
            product_type="bundle",
            confidence=0.9,
            accepted=False,
            rejected_reasons=["ram_listing_contains_bundle_or_extra_component_signals"],
            flags=[*positive_signals],
        )
    if _matched_patterns(text, RAM_ACCESSORY_PATTERNS):
        return ProductTypeClassification(
            product_type="accessory",
            confidence=0.9,
            accepted=False,
            rejected_reasons=["ram_listing_is_controller_or_accessory"],
            flags=[*positive_signals],
        )
    if _matched_patterns(text, RAM_USED_OR_REFURB_PATTERNS):
        return ProductTypeClassification(
            product_type="unknown_low_confidence",
            confidence=0.82,
            accepted=False,
            rejected_reasons=["ram_listing_condition_is_used_or_refurbished"],
            flags=[*positive_signals],
        )
    if not positive_signals or "ddr5_signal" not in positive_signals:
        return ProductTypeClassification(
            product_type="unknown_low_confidence",
            confidence=0.34,
            accepted=False,
            rejected_reasons=["ram_listing_lacks_standalone_ddr5_memory_evidence"],
            flags=[*positive_signals],
        )

    confidence = min(0.98, 0.64 + len(set(positive_signals)) * 0.06)
    return ProductTypeClassification(
        product_type="standalone_ram",
        confidence=round(confidence, 2),
        accepted=True,
        flags=positive_signals,
    )


def _classify_psu_product_type(record: SourceProductRecord) -> ProductTypeClassification:
    text = _normalized_text(record.title)
    positive_signals = _matched_labels(text, PSU_POSITIVE_PATTERNS)

    if _matched_patterns(text, PSU_UPS_PATTERNS):
        return ProductTypeClassification(
            product_type="accessory",
            confidence=0.92,
            accepted=False,
            rejected_reasons=["psu_listing_is_ups_or_battery_backup"],
            flags=[*positive_signals],
        )
    if _matched_patterns(text, PSU_CHARGER_ADAPTER_PATTERNS):
        return ProductTypeClassification(
            product_type="accessory",
            confidence=0.9,
            accepted=False,
            rejected_reasons=["psu_listing_is_charger_or_power_adapter"],
            flags=[*positive_signals],
        )
    if _matched_patterns(text, PSU_CABLE_ACCESSORY_PATTERNS):
        return ProductTypeClassification(
            product_type="accessory",
            confidence=0.88,
            accepted=False,
            rejected_reasons=["psu_listing_is_cable_or_power_accessory"],
            flags=[*positive_signals],
        )
    if _matched_patterns(text, PSU_CASE_BUNDLE_PATTERNS):
        return ProductTypeClassification(
            product_type="bundle",
            confidence=0.9,
            accepted=False,
            rejected_reasons=["psu_listing_is_case_with_included_power_supply"],
            flags=[*positive_signals],
        )
    if _matched_patterns(text, PSU_USED_OR_REFURB_PATTERNS):
        return ProductTypeClassification(
            product_type="unknown_low_confidence",
            confidence=0.82,
            accepted=False,
            rejected_reasons=["psu_listing_condition_is_used_or_refurbished"],
            flags=[*positive_signals],
        )
    if not positive_signals or not {
        "power_supply_signal",
        "psu_signal",
        "psu_wattage_signal",
        "known_psu_model_signal",
    }.intersection(
        positive_signals
    ):
        return ProductTypeClassification(
            product_type="unknown_low_confidence",
            confidence=0.34,
            accepted=False,
            rejected_reasons=["psu_listing_lacks_standalone_power_supply_evidence"],
            flags=[*positive_signals],
        )

    confidence = min(0.98, 0.64 + len(set(positive_signals)) * 0.06)
    return ProductTypeClassification(
        product_type="standalone_psu",
        confidence=round(confidence, 2),
        accepted=True,
        flags=positive_signals,
    )


def _classify_case_product_type(record: SourceProductRecord) -> ProductTypeClassification:
    text = _normalized_text(record.title)
    positive_signals = _matched_labels(text, CASE_POSITIVE_PATTERNS)

    if _matched_patterns(text, CASE_PREBUILT_PATTERNS):
        return ProductTypeClassification(
            product_type="prebuilt_pc",
            confidence=0.94,
            accepted=False,
            rejected_reasons=["case_listing_is_full_system_or_prebuilt_pc"],
            flags=[*positive_signals],
        )
    if _matched_patterns(text, CASE_ACCESSORY_PATTERNS):
        return ProductTypeClassification(
            product_type="accessory",
            confidence=0.9,
            accepted=False,
            rejected_reasons=["case_listing_is_accessory_not_chassis"],
            flags=[*positive_signals],
        )
    if _matched_patterns(text, CASE_BUNDLE_PATTERNS):
        return ProductTypeClassification(
            product_type="bundle",
            confidence=0.88,
            accepted=False,
            rejected_reasons=["case_listing_contains_bundle_or_extra_component_signals"],
            flags=[*positive_signals],
        )
    if not positive_signals or not {"pc_case_signal", "case_signal", "chassis_signal", "mid_tower_signal", "4000d_signal"}.intersection(
        positive_signals
    ):
        return ProductTypeClassification(
            product_type="unknown_low_confidence",
            confidence=0.34,
            accepted=False,
            rejected_reasons=["case_listing_lacks_standalone_chassis_evidence"],
            flags=[*positive_signals],
        )

    confidence = min(0.98, 0.64 + len(set(positive_signals)) * 0.06)
    return ProductTypeClassification(
        product_type="standalone_case",
        confidence=round(confidence, 2),
        accepted=True,
        flags=positive_signals,
    )


def _classify_cooler_product_type(record: SourceProductRecord) -> ProductTypeClassification:
    text = _normalized_text(record.title)
    positive_signals = _matched_labels(text, COOLER_POSITIVE_PATTERNS)

    if _matched_patterns(text, COOLER_ACCESSORY_PATTERNS):
        return ProductTypeClassification(
            product_type="accessory",
            confidence=0.9,
            accepted=False,
            rejected_reasons=["cooler_listing_is_accessory_not_cpu_cooler"],
            flags=[*positive_signals],
        )
    if _matched_patterns(text, COOLER_CASE_PATTERNS):
        return ProductTypeClassification(
            product_type="bundle",
            confidence=0.88,
            accepted=False,
            rejected_reasons=["cooler_listing_is_case_or_case_bundle"],
            flags=[*positive_signals],
        )
    if not positive_signals or not {
        "cpu_cooler_signal",
        "aio_signal",
        "liquid_cooler_signal",
        "liquid_cooling_signal",
        "air_cooler_signal",
        "known_cooler_model_signal",
    }.intersection(positive_signals):
        return ProductTypeClassification(
            product_type="unknown_low_confidence",
            confidence=0.34,
            accepted=False,
            rejected_reasons=["cooler_listing_lacks_standalone_cpu_cooler_evidence"],
            flags=[*positive_signals],
        )

    confidence = min(0.98, 0.64 + len(set(positive_signals)) * 0.06)
    return ProductTypeClassification(
        product_type="standalone_cooler",
        confidence=round(confidence, 2),
        accepted=True,
        flags=positive_signals,
    )


def _classify_motherboard_product_type(record: SourceProductRecord) -> ProductTypeClassification:
    text = _normalized_text(record.title)
    positive_signals = _matched_labels(text, MOTHERBOARD_POSITIVE_PATTERNS)

    if _matched_patterns(text, MOTHERBOARD_BUNDLE_SYSTEM_PATTERNS):
        return ProductTypeClassification(
            product_type="bundle",
            confidence=0.92,
            accepted=False,
            rejected_reasons=["motherboard_listing_is_bundle_or_full_system"],
            flags=[*positive_signals],
        )
    if _matched_patterns(text, MOTHERBOARD_ACCESSORY_PATTERNS):
        return ProductTypeClassification(
            product_type="accessory",
            confidence=0.88,
            accepted=False,
            rejected_reasons=["motherboard_listing_is_accessory_or_server_part"],
            flags=[*positive_signals],
        )
    wrong_platform = _matched_patterns(text, MOTHERBOARD_WRONG_PLATFORM_PATTERNS)
    if wrong_platform:
        return ProductTypeClassification(
            product_type="unknown_low_confidence",
            confidence=0.9,
            accepted=False,
            rejected_reasons=["motherboard_listing_not_b650_am5_ddr5_target"],
            flags=[*positive_signals],
        )
    signal_set = set(positive_signals)
    known_b650_model = "known_motherboard_model_signal" in signal_set and "b650_chipset_signal" in signal_set
    has_am5_or_known_b650_model = "am5_socket_signal" in signal_set or known_b650_model
    has_ddr5_or_known_b650_model = "ddr5_memory_signal" in signal_set or known_b650_model
    if "b650_chipset_signal" not in signal_set or not has_am5_or_known_b650_model or not has_ddr5_or_known_b650_model:
        return ProductTypeClassification(
            product_type="unknown_low_confidence",
            confidence=0.36,
            accepted=False,
            rejected_reasons=["motherboard_listing_lacks_b650_am5_ddr5_evidence"],
            flags=[*positive_signals],
        )

    confidence = min(0.98, 0.64 + len(set(positive_signals)) * 0.05)
    return ProductTypeClassification(
        product_type="standalone_motherboard",
        confidence=round(confidence, 2),
        accepted=True,
        flags=positive_signals,
    )


def classify_listing_market(record: SourceProductRecord) -> ListingMarketClassification:
    condition = _listing_condition(record.condition, record.title)
    seller_type = _seller_type(record.vendor_name, record.source.source, record.seller)
    risk = _marketplace_risk_score(condition, seller_type, record.vendor_name, record.seller)
    flags: list[str] = []

    if seller_type == "marketplace":
        flags.append("marketplace_listing")
    elif seller_type == "third_party":
        flags.append("third_party_seller")
    if condition == "unknown":
        flags.append("condition_unknown")
    if condition == "unknown" or risk >= 0.65:
        flags.append("price_requires_review")

    return ListingMarketClassification(
        listing_condition=condition,
        seller_type=seller_type,
        marketplace_risk_score=risk,
        flags=flags,
    )


def infer_listing_market(
    *,
    vendor_name: str | None,
    source: str | None = None,
    seller: str | None = None,
    condition: str | None = None,
    title: str | None = None,
) -> ListingMarketClassification:
    synthetic_source = SourceProductRecord(
        source_product_id="inferred",
        title=title or "",
        category="Accessories",
        price=1,
        currency="USD",
        vendor_name=vendor_name or "Unknown",
        seller=seller,
        condition=condition,
        source=record_source(source),
    )
    return classify_listing_market(synthetic_source)


def record_source(source: str | None):
    from datetime import UTC, datetime

    from app.models.pricing import SourceMetadata, SourceTier, SourceType

    return SourceMetadata(
        source=source or "unknown",
        source_type=SourceType.INFERRED,
        tier=SourceTier.INFERRED,
        timestamp=datetime.now(UTC),
        trust_score=0.4,
        freshness_score=0.4,
    )


def _listing_condition(raw_condition: str | None, title: str) -> str:
    text = f" {raw_condition or ''} {title or ''} ".lower()
    if re.search(r"\b(open[\s-]?box|open box)\b", text):
        return "open_box"
    if re.search(r"\b(refurbished|refurb|renewed|recertified)\b", text):
        return "refurbished"
    if re.search(r"\b(used|pre[\s-]?owned|second hand)\b", text):
        return "used"
    if re.search(r"\b(brand new|new sealed|factory sealed|new in box|new)\b", text):
        return "new"
    return "unknown"


def _seller_type(vendor_name: str, source: str, seller: str | None) -> str:
    vendor = vendor_name.lower()
    source_text = source.lower()
    seller_text = (seller or "").strip().lower()

    if any(pattern in vendor or pattern in source_text for pattern in MARKETPLACE_VENDOR_PATTERNS):
        return "marketplace"
    if " - " in vendor_name or (seller_text and seller_text not in {"amazon", "bestbuy", "best buy"}):
        return "third_party"
    if any(pattern in vendor for pattern in TRUSTED_RETAILER_PATTERNS):
        return "retailer"
    if any(pattern in vendor for pattern in MANUFACTURER_PATTERNS):
        return "manufacturer"
    return "unknown"


def _marketplace_risk_score(condition: str, seller_type: str, vendor_name: str, seller: str | None) -> float:
    risk = {
        "manufacturer": 0.08,
        "retailer": 0.16,
        "unknown": 0.48,
        "third_party": 0.62,
        "marketplace": 0.72,
    }.get(seller_type, 0.5)
    if condition == "unknown":
        risk += 0.12
    elif condition == "used":
        risk += 0.1
    elif condition in {"refurbished", "open_box"}:
        risk += 0.06
    elif condition == "new":
        risk -= 0.08
    if "swappa" in vendor_name.lower() or "ebay" in vendor_name.lower():
        risk += 0.08
    if seller:
        risk += 0.04
    return round(max(0.0, min(1.0, risk)), 2)


def _normalized_text(value: str) -> str:
    return f" {re.sub(r'[^a-z0-9+]+', ' ', value.lower()).strip()} "


def _matched_patterns(text: str, patterns: tuple[str, ...]) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text, flags=re.IGNORECASE)]


def _matched_labels(text: str, patterns: tuple[tuple[str, str], ...]) -> list[str]:
    return [label for pattern, label in patterns if re.search(pattern, text, flags=re.IGNORECASE)]
