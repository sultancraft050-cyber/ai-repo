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
from app.services.pricing_classification import classify_listing_market, classify_product_type


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
    "Lexar",
    "Sabrent",
    "SK hynix",
    "Teamgroup",
    "ADATA",
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
    "DeepCool",
    "Thermalright",
    "GamerTek",
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

STORAGE_BRANDS = (
    "Samsung",
    "WD",
    "Western Digital",
    "Seagate",
    "Kingston",
    "Crucial",
    "Corsair",
    "Sabrent",
    "SK hynix",
    "Lexar",
    "Teamgroup",
    "ADATA",
)

RAM_SERIES_ALIASES: tuple[tuple[str, str], ...] = (
    ("TRIDENT Z5", "TRIDENT_Z5"),
    ("VENGEANCE", "VENGEANCE"),
    ("DOMINATOR", "DOMINATOR"),
    ("FURY BEAST", "FURY_BEAST"),
    ("FURY RENEGADE", "FURY_RENEGADE"),
    ("FURY", "FURY"),
    ("FLARE X5", "FLARE_X5"),
    ("RIPJAWS S5", "RIPJAWS_S5"),
    ("DELTA RGB", "DELTA_RGB"),
    ("T-CREATE", "T_CREATE"),
    ("T CREATE", "T_CREATE"),
    ("PRO", "PRO"),
)

PSU_MODEL_ALIASES: tuple[tuple[str, str], ...] = (
    ("PRIME AP-850G", "PRIME_AP850G"),
    ("PRIME AP 850G", "PRIME_AP850G"),
    ("AP-850G", "AP850G"),
    ("AP850G", "AP850G"),
    ("RM850X", "RM850X"),
    ("RM850E", "RM850E"),
    ("C850", "C850"),
    ("EDGE GOLD", "EDGE"),
    ("EDGE", "EDGE"),
    ("FOCUS GX-850", "FOCUS_GX"),
    ("FOCUS GX 850", "FOCUS_GX"),
    ("FOCUS GX850", "FOCUS_GX"),
    ("MAG A850GL", "MAG_A850GL"),
    ("A850GL", "MAG_A850GL"),
    ("TOUGHPOWER GF", "TOUGHPOWER_GF"),
    ("TOUGHPOWER GF3", "TOUGHPOWER_GF3"),
    ("TOUGHPOWER GF A3", "TOUGHPOWER_GF_A3"),
    ("SUPERFLOWER LEADEX", "LEADEX"),
    ("LEADEX", "LEADEX"),
    ("REVOLUTION D.F.", "REVOLUTION_DF"),
    ("REVOLUTION DF", "REVOLUTION_DF"),
)

GOLD_FULLY_MODULAR_PSU_MODELS = {
    "RM850X",
    "RM850E",
    "FOCUS_GX",
    "MAG_A850GL",
    "TOUGHPOWER_GF",
    "TOUGHPOWER_GF3",
    "TOUGHPOWER_GF_A3",
}

CASE_MODEL_ALIASES: tuple[tuple[str, str], ...] = (
    ("ICUE 4000D RGB AIRFLOW V2", "ICUE_4000D_RGB_AIRFLOW_V2"),
    ("4000D RGB AIRFLOW V2", "4000D_RGB_AIRFLOW_V2"),
    ("4000D AIRFLOW", "4000D_AIRFLOW"),
    ("4000D", "4000D"),
    ("4000X RGB", "4000X_RGB"),
    ("4000X", "4000X"),
    ("5000D AIRFLOW", "5000D_AIRFLOW"),
    ("5000D", "5000D"),
    ("3000D AIRFLOW", "3000D_AIRFLOW"),
    ("3000D", "3000D"),
)

COOLER_MODEL_ALIASES: tuple[tuple[str, str], ...] = (
    ("AQUA FROST", "AQUA_FROST"),
    ("MAG CORELIQUID A13", "MAG_CORELIQUID_A13"),
    ("CORELIQUID A13", "CORELIQUID_A13"),
    ("NAUTILUS 240", "NAUTILUS_240"),
    ("KRAKEN CORE 240", "KRAKEN_CORE"),
    ("KRAKEN ELITE", "KRAKEN_ELITE"),
    ("LIQUID FREEZER III 240", "LIQUID_FREEZER_III"),
    ("LIQUID FREEZER 3 240", "LIQUID_FREEZER_III"),
    ("LS520", "LS520"),
    ("H100I", "H100I"),
    ("KRAKEN 240", "KRAKEN"),
    ("PEERLESS ASSASSIN", "PEERLESS_ASSASSIN"),
    ("AK620", "AK620"),
)

MOTHERBOARD_MODEL_ALIASES: tuple[tuple[str, str], ...] = (
    ("PRIME B650M-A WIFI II", "PRIME_B650M_A_WIFI_II"),
    ("PRIME B650M A WIFI II", "PRIME_B650M_A_WIFI_II"),
    ("B650 TOMAHAWK WIFI", "B650_TOMAHAWK_WIFI"),
    ("MAG B650 TOMAHAWK WIFI", "B650_TOMAHAWK_WIFI"),
    ("TUF GAMING B650-PLUS WIFI", "TUF_B650_PLUS_WIFI"),
    ("TUF B650-PLUS WIFI", "TUF_B650_PLUS_WIFI"),
    ("TUF GAMING B650 PLUS WIFI", "TUF_B650_PLUS_WIFI"),
    ("B650 AORUS ELITE AX", "B650_AORUS_ELITE_AX"),
    ("B650 AORUS ELITE", "B650_AORUS_ELITE"),
    ("B650 STEEL LEGEND WIFI", "B650_STEEL_LEGEND_WIFI"),
    ("B650 STEEL LEGEND", "B650_STEEL_LEGEND"),
)

GPU_BOARD_PARTNER_BRANDS = (
    "ASUS",
    "MSI",
    "Gigabyte",
    "ASRock",
    "Zotac",
    "PNY",
    "Sapphire",
    "PowerColor",
    "EVGA",
)

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
    "GEFORCE",
    "NVIDIA",
    "RADEON",
    "AMD",
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
    "VIDEO",
}

GPU_SKU_ALIASES: tuple[tuple[str, str], ...] = (
    ("FOUNDERS EDITION", "Founders Edition"),
    ("REPUBLIC OF GAMERS STRIX", "ROG Strix"),
    ("ROG STRIX", "ROG Strix"),
    ("PROART", "ProArt"),
    ("TWIN EDGE", "Twin Edge"),
    ("VERTO", "Verto"),
    ("DUAL", "Dual"),
    ("VENTUS", "Ventus"),
    ("WINDFORCE", "Windforce"),
    ("TUF GAMING", "TUF Gaming"),
    ("GAMING X TRIO", "Gaming X Trio"),
    ("GAMING OC", "Gaming OC"),
    ("EAGLE OC", "Eagle OC"),
    ("EAGLE", "Eagle"),
    ("AERO OC", "Aero OC"),
    ("AERO", "Aero"),
    ("AMP EXTREME", "AMP Extreme"),
    ("AMP AIRO", "AMP AIRO"),
    ("TRINITY", "Trinity"),
    ("XLR8", "XLR8"),
)


def normalize_brand(value: str | None, title: str = "") -> str:
    title_has_gpu = bool(re.search(r"\b(RTX|GTX|GEFORCE|RADEON|RX\s?\d{3,4})\b", title, flags=re.IGNORECASE))
    board_partner = _brand_from_title(title, GPU_BOARD_PARTNER_BRANDS) if title_has_gpu else ""
    if board_partner and (not value or compact_key(value) in {"NVIDIA", "GEFORCE", "NVIDIAGEFORCE"}):
        return board_partner
    if value:
        candidate = value.strip()
    else:
        upper_title = f" {re.sub(r'[^A-Z0-9]+', ' ', title.upper()).strip()} "
        candidate = ""
        for brand in sorted(KNOWN_BRANDS, key=len, reverse=True):
            if f" {brand.upper()} " in upper_title:
                candidate = brand
                break
    if not candidate:
        if re.search(r"\b(RTX\s?\d{3,5}|GTX\s?\d{3,5}|GEFORCE)", title, flags=re.IGNORECASE):
            candidate = "NVIDIA"
        elif re.search(r"\b(RADEON|RX\s?\d{3,4})\b", title, flags=re.IGNORECASE):
            candidate = "AMD"
        elif re.search(r"\b(ARC\s?[AB]\d{3})\b", title, flags=re.IGNORECASE):
            candidate = "Intel"
        else:
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


def compact_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", value.upper())


def gpu_family_key_from_title(title: str) -> str | None:
    family = _extract_gpu_family(title)
    return family[1] if family else None


def cpu_model_key_from_title(title: str) -> str | None:
    compact = compact_key(title)
    if "7800X3D" in compact:
        return "AMD_RYZEN_7_7800X3D"
    r7_alias = re.search(r"\bR\s*7\s*[- ]?(\d{4})(X3D|XT|X)?\b", title, flags=re.IGNORECASE)
    if r7_alias:
        suffix = r7_alias.group(2) or ""
        return f"AMD_RYZEN_7_{r7_alias.group(1)}{suffix.upper()}"
    ryzen = re.search(r"RYZEN([3579])(\d{4})(X3D|XT|X)?", compact)
    if ryzen:
        suffix = ryzen.group(3) or ""
        return f"AMD_RYZEN_{ryzen.group(1)}_{ryzen.group(2)}{suffix}"
    intel = re.search(r"(?:CORE)?I([3579])(\d{4,5}[A-Z]*)", compact)
    if intel:
        return f"INTEL_CORE_I{intel.group(1)}_{intel.group(2)}"
    threadripper = re.search(r"THREADRIPPER(\d{4,5}[A-Z]*)", compact)
    if threadripper:
        return f"AMD_THREADRIPPER_{threadripper.group(1)}"
    xeon = re.search(r"XEON([A-Z0-9]{4,})", compact)
    if xeon:
        return f"INTEL_XEON_{xeon.group(1)}"
    return None


def storage_model_key_from_title(title: str) -> str | None:
    compact = compact_key(title)
    if "SAMSUNG" in compact or "990PRO" in compact:
        capacity = _storage_capacity_key(title)
        if "990PRO" in compact and capacity:
            return f"SAMSUNG_990_PRO_{capacity}_NVME_M2"
    if "980PRO" in compact:
        capacity = _storage_capacity_key(title)
        if capacity:
            return f"SAMSUNG_980_PRO_{capacity}_NVME_M2"
    if "990EVO" in compact:
        capacity = _storage_capacity_key(title)
        if capacity:
            return f"SAMSUNG_990_EVO_{capacity}_NVME_M2"
    if "SN850X" in compact:
        capacity = _storage_capacity_key(title)
        if capacity:
            return f"WD_BLACK_SN850X_{capacity}_NVME_M2"
    if "KC3000" in compact:
        capacity = _storage_capacity_key(title)
        if capacity:
            return f"KINGSTON_KC3000_{capacity}_NVME_M2"
    if "CRUCIAL" in compact and "T500" in compact:
        capacity = _storage_capacity_key(title)
        if capacity:
            return f"CRUCIAL_T500_{capacity}_NVME_M2"
    if "P5PLUS" in compact or ("CRUCIAL" in compact and "P5" in compact and "PLUS" in compact):
        capacity = _storage_capacity_key(title)
        if capacity:
            return f"CRUCIAL_P5_PLUS_{capacity}_NVME_M2"
    if "LEXAR" in compact and "NM790" in compact:
        capacity = _storage_capacity_key(title)
        if capacity:
            return f"LEXAR_NM790_{capacity}_NVME_M2"
    return None


def ram_family_key_from_title(title: str) -> str | None:
    compact = compact_key(title)
    memory_type = _ram_memory_type(title)
    capacity_gb = _ram_capacity_gb(title)
    speed_mhz = _ram_speed_mhz(title)
    if not memory_type or not capacity_gb or not speed_mhz:
        return None
    if "SODIMM" in compact or "SODIMM" in title.upper().replace("-", ""):
        return None
    return f"RAM_{memory_type}_{capacity_gb}GB_{speed_mhz}"


def psu_family_key_from_title(title: str) -> str | None:
    wattage = _psu_wattage_w(title)
    efficiency = _psu_efficiency_rating(title)
    modularity = _psu_modularity(title)
    if not wattage or not efficiency or not modularity:
        return None
    return f"PSU_{wattage}W_{efficiency}_{modularity}"


def case_family_key_from_title(title: str) -> str | None:
    compact = compact_key(title)
    if "CORSAIR" in compact or re.search(r"\b4000[DX]\b|\b5000D\b|\b3000D\b", title, flags=re.IGNORECASE):
        if "4000D" in compact and "AIRFLOW" in compact and ("ICUE" in compact or "RGB" in compact or "V2" in compact):
            return "CASE_CORSAIR_4000D_RGB_AIRFLOW_V2"
        if "4000D" in compact and "AIRFLOW" in compact:
            return "CASE_CORSAIR_4000D_AIRFLOW"
        if "4000X" in compact:
            return "CASE_CORSAIR_4000X_RGB"
        if "5000D" in compact:
            return "CASE_CORSAIR_5000D_AIRFLOW" if "AIRFLOW" in compact else "CASE_CORSAIR_5000D"
        if "3000D" in compact:
            return "CASE_CORSAIR_3000D_AIRFLOW" if "AIRFLOW" in compact else "CASE_CORSAIR_3000D"
    return None


def cooler_family_key_from_title(title: str) -> str | None:
    cooler_type = _cooler_type(title)
    if cooler_type == "aio_liquid":
        radiator = _cooler_radiator_size_mm(title)
        if radiator:
            socket_suffix = "_AM5" if _cooler_supports_am5(title) else ""
            return f"COOLER_AIO_{radiator}MM{socket_suffix}"
    if cooler_type == "air":
        socket_suffix = "_AM5" if _cooler_supports_am5(title) else ""
        if _cooler_model_key(title) in {"PEERLESS_ASSASSIN", "AK620"}:
            return f"COOLER_AIR_DUAL_TOWER{socket_suffix}"
        return f"COOLER_AIR{socket_suffix}"
    return None


def motherboard_family_key_from_title(title: str) -> str | None:
    chipset = _motherboard_chipset(title)
    socket = _motherboard_socket(title)
    memory_type = _motherboard_memory_type(title)
    if chipset == "B650" and socket == "AM5" and memory_type == "DDR5":
        return "MOTHERBOARD_B650_AM5_DDR5"
    return None


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
    elif category == "CPU":
        cpu_key = cpu_model_key_from_title(title)
        if cpu_key:
            specs["cpu_model_key"] = cpu_key
            specs["cpu_family_key"] = cpu_key
            specs["cpu_family_name"] = _cpu_family_name(cpu_key)
        if "AM5" in text and "socket" not in specs:
            specs["socket"] = "AM5"
        elif "LGA1700" in compact_key(title) and "socket" not in specs:
            specs["socket"] = "LGA1700"
        if re.search(r"\b(TRAY|OEM)\b", text):
            specs["cpu_package"] = "TRAY"
        elif re.search(r"\b(BOXED|BOX|RETAIL)\b", text):
            specs["cpu_package"] = "BOXED"
    elif category == "RAM":
        memory_type = _ram_memory_type(title)
        capacity_gb = _ram_capacity_gb(title)
        speed_mhz = _ram_speed_mhz(title)
        family_key = ram_family_key_from_title(title)
        if memory_type:
            specs.setdefault("memory_type", memory_type)
        if capacity_gb is not None:
            specs.setdefault("capacity_gb", capacity_gb)
        if speed_mhz is not None:
            specs.setdefault("speed_mt_s", speed_mhz)
            specs.setdefault("speed_mhz", speed_mhz)
        kit_config = _ram_kit_config(title)
        if kit_config:
            specs.setdefault("kit_config", kit_config)
        cas_latency = _ram_cas_latency(title)
        if cas_latency is not None:
            specs.setdefault("cas_latency", cas_latency)
        specs.setdefault("desktop_or_laptop", "laptop" if _ram_is_laptop_memory(title) else "desktop")
        specs.setdefault("ecc", _ram_ecc(title))
        if family_key:
            specs["ram_family_key"] = family_key
            specs["ram_family_name"] = _ram_family_name(family_key)
    elif category == "Storage":
        storage_key = storage_model_key_from_title(title)
        if storage_key:
            specs["storage_model_key"] = storage_key
            specs["storage_family_key"] = storage_key
            specs["storage_family_name"] = _storage_family_name(storage_key)
            specs["interface"] = "NVMe"
            specs["form_factor"] = "M.2"
        tb = re.search(r"\b(\d+(?:\.\d+)?)\s?TB\b", text)
        gb = re.search(r"\b(\d{2,5})\s?GB\b", text)
        if tb and "capacity_gb" not in specs:
            specs["capacity_gb"] = int(float(tb.group(1)) * 1024)
        elif gb and "capacity_gb" not in specs:
            specs["capacity_gb"] = int(gb.group(1))
        if (
            re.search(r"\bHEATSINK\b", text)
            or ("\u0645\u0628\u062f\u062f" in title and "\u062d\u0631\u0627\u0631" in title)
        ) and "heatsink" not in specs:
            specs["heatsink"] = True
    elif category == "PSU":
        wattage = _psu_wattage_w(title)
        efficiency = _psu_efficiency_rating(title)
        modularity = _psu_modularity(title)
        atx_version = _psu_atx_version(title)
        pcie_5 = _psu_pcie_5_support(title)
        native_12vhpwr = _psu_native_12vhpwr(title)
        family_key = psu_family_key_from_title(title)
        if wattage is not None:
            specs.setdefault("wattage", wattage)
            specs.setdefault("wattage_w", wattage)
            specs.setdefault("continuous_wattage", wattage)
        if efficiency:
            specs.setdefault("efficiency_rating", efficiency)
        if modularity:
            specs.setdefault("modularity", modularity)
        if atx_version:
            specs.setdefault("atx_version", atx_version)
        specs.setdefault("pcie_5_support", pcie_5)
        specs.setdefault("native_12vhpwr", native_12vhpwr)
        specs.setdefault("form_factor", "ATX")
        warranty_years = _psu_warranty_years(title)
        if warranty_years is not None:
            specs.setdefault("warranty_years", warranty_years)
        if family_key:
            specs["psu_family_key"] = family_key
            specs["psu_family_name"] = _psu_family_name(family_key)
    elif category == "Case":
        family_key = case_family_key_from_title(title)
        supported = _case_supported_motherboard_form_factors(title)
        case_type = _case_type(title)
        if supported:
            specs.setdefault("supported_motherboard_form_factors", supported)
        if case_type:
            specs.setdefault("case_type", case_type)
        specs.setdefault("psu_form_factor", "ATX")
        specs.setdefault("airflow_focus", "AIRFLOW" in text)
        specs.setdefault("tempered_glass", bool(re.search(r"\bTEMPERED\s+GLASS\b|\bTG\b", text)))
        color = _case_color(title)
        if color:
            specs.setdefault("color", color)
        fans = _case_included_fans_count(title, family_key)
        if fans is not None:
            specs.setdefault("included_fans_count", fans)
        if family_key == "CASE_CORSAIR_4000D_AIRFLOW":
            specs.setdefault("supported_motherboard_form_factors", ["ATX", "mATX", "ITX"])
            specs.setdefault("case_type", "mid_tower")
            specs.setdefault("max_gpu_length_mm", 360)
            specs.setdefault("max_cpu_cooler_height_mm", 170)
            specs.setdefault("radiator_support_top_mm", 280)
            specs.setdefault("radiator_support_front_mm", 360)
            specs.setdefault("psu_form_factor", "ATX")
            specs.setdefault("included_fans_count", 2)
            specs.setdefault("airflow_focus", True)
        if family_key:
            specs["case_family_key"] = family_key
            specs["case_family_name"] = _case_family_name(family_key)
    elif category == "Cooler":
        cooler_type = _cooler_type(title)
        radiator_size = _cooler_radiator_size_mm(title)
        fan_count = _cooler_radiator_fan_count(radiator_size)
        fan_size = _cooler_fan_size_mm(title, radiator_size)
        supported_sockets = _cooler_supported_sockets(title)
        model_key = _cooler_model_key(title)
        family_key = cooler_family_key_from_title(title)
        if cooler_type:
            specs.setdefault("cooler_type", cooler_type)
        if supported_sockets:
            specs.setdefault("supported_sockets", supported_sockets)
            specs.setdefault("socket_confidence", 0.9)
        else:
            specs.setdefault("socket_confidence", 0.35)
        if radiator_size is not None:
            specs.setdefault("radiator_size_mm", radiator_size)
        if fan_count is not None:
            specs.setdefault("radiator_fan_count", fan_count)
        if fan_size is not None:
            specs.setdefault("fan_size_mm", fan_size)
        height = _cooler_height_mm(title, model_key)
        if height is not None:
            specs.setdefault("cooler_height_mm", height)
            specs.setdefault("height_mm", height)
        tdp = _cooler_tdp_rating_w(title, model_key)
        if tdp is not None:
            specs.setdefault("tdp_rating_w", tdp)
            specs.setdefault("cooling_capacity_w", tdp)
        if model_key:
            specs["cooler_model_key"] = model_key
        if family_key:
            specs["cooler_family_key"] = family_key
            specs["cooler_family_name"] = _cooler_family_name(family_key)
    elif category == "Motherboard":
        chipset = _motherboard_chipset(title)
        socket = _motherboard_socket(title)
        memory_type = _motherboard_memory_type(title)
        form_factor = _motherboard_form_factor(title)
        model_key = _motherboard_model_key(title)
        family_key = motherboard_family_key_from_title(title)
        if socket:
            specs.setdefault("socket", socket)
        if chipset:
            specs.setdefault("chipset", chipset)
        if memory_type:
            specs.setdefault("memory_type", memory_type)
        if form_factor:
            specs.setdefault("form_factor", form_factor)
            specs.setdefault("motherboard_form_factor", form_factor)
        m2_slots = _motherboard_m2_slots(title, model_key)
        if m2_slots is not None:
            specs.setdefault("m2_slots", m2_slots)
        specs.setdefault("pcie_x16_slots", _motherboard_pcie_x16_slots(title, model_key))
        pcie_generation = _motherboard_pcie_generation(title, chipset)
        if pcie_generation:
            specs.setdefault("pcie_generation", pcie_generation)
        specs.setdefault("wifi", _motherboard_wifi(title, model_key))
        specs.setdefault("bios_flashback", _motherboard_bios_flashback(title, model_key))
        vrm_hint = _motherboard_vrm_quality_hint(title, model_key)
        if vrm_hint:
            specs.setdefault("vrm_quality_hint", vrm_hint)
        max_memory = _motherboard_max_memory_gb(title)
        if max_memory is not None:
            specs.setdefault("max_memory_gb", max_memory)
        memory_slots = _motherboard_memory_slots(title, form_factor)
        if memory_slots is not None:
            specs.setdefault("memory_slots", memory_slots)
        if model_key:
            specs["motherboard_model_key"] = model_key
        if family_key:
            specs["motherboard_family_key"] = family_key
            specs["motherboard_family_name"] = _motherboard_family_name(family_key)
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


def enrich_gpu_identity(title: str, brand: str, model: str, specs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if specs.get("gpu_family_key"):
        return model, specs

    enriched = dict(specs)
    family = _extract_gpu_family(title)
    if not family:
        return model, enriched

    family_name, family_key, chipset = family
    board_sku = _extract_gpu_board_sku(title)
    if brand == "NVIDIA" and board_sku != "Founders Edition":
        board_partner = "NVIDIA"
    else:
        board_partner = brand

    enriched["gpu_family_name"] = family_name
    enriched["gpu_family_key"] = family_key
    enriched["chipset"] = chipset
    enriched["board_partner"] = board_partner
    if board_sku:
        enriched["board_sku"] = board_sku
        enriched["board_sku_key"] = compact_key(board_sku)

    model_parts = [family_name]
    if board_sku:
        model_parts.append(board_sku)
    return " ".join(model_parts), enriched


def canonical_key(category: str, brand: str, model: str, specs: dict[str, Any]) -> str:
    if normalize_category(category) == "CPU" and specs.get("cpu_model_key"):
        parts = ["CPU", compact_key(brand), str(specs["cpu_model_key"]).replace(f"{compact_key(brand)}_", "", 1)]
        package = specs.get("cpu_package")
        if package == "TRAY":
            parts.append("TRAY")
        return "|".join(parts)

    if normalize_category(category) == "Storage" and specs.get("storage_model_key"):
        model_key = str(specs["storage_model_key"]).replace(f"{compact_key(brand)}_", "", 1)
        if model_key.startswith("990_PRO_"):
            model_parts = ["990_PRO", *model_key.removeprefix("990_PRO_").split("_")]
        elif model_key.startswith("980_PRO_"):
            model_parts = ["980_PRO", *model_key.removeprefix("980_PRO_").split("_")]
        elif model_key.startswith("990_EVO_"):
            model_parts = ["990_EVO", *model_key.removeprefix("990_EVO_").split("_")]
        elif model_key.startswith("BLACK_SN850X_"):
            model_parts = ["BLACK_SN850X", *model_key.removeprefix("BLACK_SN850X_").split("_")]
        elif model_key.startswith("P5_PLUS_"):
            model_parts = ["P5_PLUS", *model_key.removeprefix("P5_PLUS_").split("_")]
        else:
            model_parts = model_key.split("_")
        parts = ["STORAGE", compact_key(brand), *model_parts]
        if specs.get("heatsink"):
            parts.append("HEATSINK")
        return "|".join(parts)

    if normalize_category(category) == "RAM" and specs.get("ram_family_key"):
        memory_type = str(specs.get("memory_type") or "DDR").upper()
        capacity = f"{int(specs['capacity_gb'])}GB" if specs.get("capacity_gb") is not None else "UNKNOWN"
        speed = str(specs.get("speed_mhz") or specs.get("speed_mt_s") or "").upper()
        series = _ram_series_key(model) or _ram_series_key(str(specs.get("ram_family_name") or ""))
        if compact_key(brand) != "UNKNOWN" and series:
            return "|".join(["RAM", compact_key(brand), series, memory_type, capacity, speed])
        return "|".join(["RAM", memory_type, capacity, speed])

    if normalize_category(category) == "PSU" and specs.get("psu_family_key"):
        wattage = f"{int(specs['wattage_w'])}W" if specs.get("wattage_w") is not None else "UNKNOWN"
        efficiency = str(specs.get("efficiency_rating") or "UNKNOWN").upper()
        modularity = str(specs.get("modularity") or "UNKNOWN").upper()
        model_key = _psu_model_key(model) or _psu_model_key(f"{brand} {model}") or _psu_fallback_model_key(model)
        suffix = "PCIE5" if specs.get("pcie_5_support") else modularity
        if compact_key(brand) != "UNKNOWN" and model_key:
            return "|".join(["PSU", compact_key(brand), model_key, wattage, efficiency, suffix])
        if model_key:
            return "|".join(["PSU", "UNKNOWN", model_key, wattage, efficiency, suffix])
        return "|".join(["PSU", wattage, f"80PLUS_{efficiency}", modularity])

    if normalize_category(category) == "Case" and specs.get("case_family_key"):
        family_key = str(specs["case_family_key"])
        model_key = family_key.replace("CASE_", "").replace(f"{compact_key(brand)}_", "", 1)
        form_factor = "ATX" if "ATX" in specs.get("supported_motherboard_form_factors", []) else "UNKNOWN"
        case_type = str(specs.get("case_type") or "UNKNOWN").upper()
        return "|".join(["CASE", compact_key(brand), model_key, form_factor, case_type])

    if normalize_category(category) == "Cooler" and specs.get("cooler_family_key"):
        model_key = _cooler_model_key(model) or _cooler_model_key(f"{brand} {model}")
        cooler_type = str(specs.get("cooler_type") or "UNKNOWN").upper()
        if cooler_type == "AIO_LIQUID":
            cooler_type = "AIO"
        radiator = f"{int(specs['radiator_size_mm'])}MM" if specs.get("radiator_size_mm") is not None else None
        if compact_key(brand) != "UNKNOWN" and model_key:
            parts = ["COOLER", compact_key(brand), model_key, cooler_type]
            if radiator:
                parts.append(radiator)
            return "|".join(parts)
        family_key = str(specs["cooler_family_key"]).replace("COOLER_", "")
        return "|".join(["COOLER", family_key])

    if normalize_category(category) == "Motherboard" and specs.get("motherboard_family_key"):
        model_key = (
            str(specs.get("motherboard_model_key") or "")
            or _motherboard_model_key(model)
            or _motherboard_model_key(f"{brand} {model}")
        )
        socket = str(specs.get("socket") or "UNKNOWN").upper()
        memory_type = str(specs.get("memory_type") or "UNKNOWN").upper()
        form_factor = str(specs.get("form_factor") or "UNKNOWN").upper()
        if compact_key(brand) != "UNKNOWN" and model_key:
            return "|".join(["MOTHERBOARD", compact_key(brand), model_key, socket, memory_type, form_factor])
        chipset = str(specs.get("chipset") or "B650").upper()
        return "|".join(["MOTHERBOARD", chipset, socket, memory_type])

    if normalize_category(category) == "GPU" and specs.get("gpu_family_key"):
        disambiguators: list[str] = []
        vram = specs.get("vram_gb")
        if vram is not None:
            disambiguators.append(f"vram_gb:{str(vram).upper()}")
        board_sku_key = str(specs.get("board_sku_key") or "GENERIC")
        return "|".join(
            [
                "GPU",
                compact_key(brand),
                str(specs["gpu_family_key"]),
                board_sku_key,
                *disambiguators,
            ]
        )

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


def _cpu_family_name(cpu_key: str) -> str:
    parts = cpu_key.split("_")
    if parts[:3] == ["AMD", "RYZEN", "7"] and len(parts) >= 4:
        return f"AMD Ryzen 7 {parts[3]}"
    if parts[:3] == ["AMD", "RYZEN", "5"] and len(parts) >= 4:
        return f"AMD Ryzen 5 {parts[3]}"
    if parts[:3] == ["AMD", "RYZEN", "9"] and len(parts) >= 4:
        return f"AMD Ryzen 9 {parts[3]}"
    if parts[:3] == ["INTEL", "CORE", "I5"] and len(parts) >= 4:
        return f"Intel Core i5 {parts[3]}"
    if parts[:3] == ["INTEL", "CORE", "I7"] and len(parts) >= 4:
        return f"Intel Core i7 {parts[3]}"
    if parts[:3] == ["INTEL", "CORE", "I9"] and len(parts) >= 4:
        return f"Intel Core i9 {parts[3]}"
    return cpu_key.replace("_", " ").title()


def _storage_capacity_key(title: str) -> str | None:
    text = title.upper()
    tb = re.search(r"\b(\d+(?:\.\d+)?)\s?TB\b", text)
    if tb:
        value = float(tb.group(1))
        return f"{int(value) if value.is_integer() else str(value).replace('.', '_')}TB"
    gb = re.search(r"\b(\d{3,5})\s?GB\b", text)
    if gb:
        return f"{gb.group(1)}GB"
    return None


def _storage_family_name(storage_key: str) -> str:
    if storage_key.startswith("SAMSUNG_990_PRO_"):
        capacity = storage_key.removeprefix("SAMSUNG_990_PRO_").removesuffix("_NVME_M2")
        return f"Samsung 990 Pro {capacity.replace('_', '.')}"
    if storage_key.startswith("SAMSUNG_980_PRO_"):
        capacity = storage_key.removeprefix("SAMSUNG_980_PRO_").removesuffix("_NVME_M2")
        return f"Samsung 980 Pro {capacity.replace('_', '.')}"
    if storage_key.startswith("SAMSUNG_990_EVO_"):
        capacity = storage_key.removeprefix("SAMSUNG_990_EVO_").removesuffix("_NVME_M2")
        return f"Samsung 990 Evo {capacity.replace('_', '.')}"
    if storage_key.startswith("WD_BLACK_SN850X_"):
        capacity = storage_key.removeprefix("WD_BLACK_SN850X_").removesuffix("_NVME_M2")
        return f"WD Black SN850X {capacity.replace('_', '.')}"
    if storage_key.startswith("KINGSTON_KC3000_"):
        capacity = storage_key.removeprefix("KINGSTON_KC3000_").removesuffix("_NVME_M2")
        return f"Kingston KC3000 {capacity.replace('_', '.')}"
    if storage_key.startswith("CRUCIAL_T500_"):
        capacity = storage_key.removeprefix("CRUCIAL_T500_").removesuffix("_NVME_M2")
        return f"Crucial T500 {capacity.replace('_', '.')}"
    if storage_key.startswith("CRUCIAL_P5_PLUS_"):
        capacity = storage_key.removeprefix("CRUCIAL_P5_PLUS_").removesuffix("_NVME_M2")
        return f"Crucial P5 Plus {capacity.replace('_', '.')}"
    if storage_key.startswith("LEXAR_NM790_"):
        capacity = storage_key.removeprefix("LEXAR_NM790_").removesuffix("_NVME_M2")
        return f"Lexar NM790 {capacity.replace('_', '.')}"
    return storage_key.replace("_", " ").title()


def _ram_memory_type(title: str) -> str | None:
    compact = compact_key(title)
    if "DDR5" in compact:
        return "DDR5"
    if "DDR4" in compact:
        return "DDR4"
    return None


def _ram_capacity_gb(title: str) -> int | None:
    text = title.upper()
    kit = re.search(r"\b(\d)\s?[X\u00d7]\s?(\d{1,3})\s?GB\b", text)
    if kit:
        return int(kit.group(1)) * int(kit.group(2))
    sku_kit = re.search(r"(?:CP|CMH|CMK|KF|F5)[A-Z0-9]*?(\d)K(\d{1,3})G(?:\d{2})?", compact_key(title))
    if sku_kit:
        return int(sku_kit.group(1)) * int(sku_kit.group(2))
    capacity = re.search(r"\b(\d{1,3})\s?GB\b", text)
    if capacity:
        return int(capacity.group(1))
    return None


def _ram_speed_mhz(title: str) -> int | None:
    text = title.upper()
    for match in re.finditer(r"\b(\d{4,5})\s?(?:MHZ|MT/S|MT)?\b", text):
        value = int(match.group(1))
        if 3200 <= value <= 9000:
            return value
    return None


def _ram_kit_config(title: str) -> str | None:
    text = title.upper()
    kit = re.search(r"\b(\d)\s?[X\u00d7]\s?(\d{1,3})\s?GB\b", text)
    if kit:
        return f"{kit.group(1)}x{kit.group(2)}"
    sku_kit = re.search(r"(?:CP|CMH|CMK|KF|F5)[A-Z0-9]*?(\d)K(\d{1,3})G(?:\d{2})?", compact_key(title))
    if sku_kit:
        return f"{sku_kit.group(1)}x{sku_kit.group(2)}"
    if re.search(r"\bKIT\b", text) and _ram_capacity_gb(title) == 32:
        return "2x16_unknown"
    return None


def _ram_cas_latency(title: str) -> int | None:
    match = re.search(r"\bCL\s?(\d{2})\b", title.upper())
    return int(match.group(1)) if match else None


def _ram_is_laptop_memory(title: str) -> bool:
    text = title.upper()
    return bool(re.search(r"\bSO[- ]?DIMM\b|\bSODIMM\b|\bLAPTOP\b|\bNOTEBOOK\b", text))


def _ram_ecc(title: str) -> bool | str:
    text = title.upper()
    if re.search(r"\bNON[- ]?ECC\b", text):
        return False
    if re.search(r"\bECC\b", text):
        return True
    return "unknown"


def _ram_series_key(title: str) -> str | None:
    upper = re.sub(r"[^A-Z0-9]+", " ", title.upper()).strip()
    for phrase, key in RAM_SERIES_ALIASES:
        if re.search(rf"\b{re.escape(phrase)}\b", upper):
            return key
    return None


def _ram_family_name(family_key: str) -> str:
    match = re.fullmatch(r"RAM_(DDR[45])_(\d{1,3})GB_(\d{4,5})", family_key)
    if match:
        return f"{match.group(2)}GB {match.group(1)} {match.group(3)}"
    return family_key.replace("_", " ").title()


def _psu_wattage_w(title: str) -> int | None:
    compact = compact_key(title)
    model_wattage = re.search(r"\b(?:RM|GX|A|GF|GX-|G)(\d{3,4})\b", title.upper())
    if model_wattage:
        value = int(model_wattage.group(1))
        if 300 <= value <= 2500:
            return value
    compact_model_wattage = re.search(r"(?:RM|GX|A|GF)(\d{3,4})", compact)
    if compact_model_wattage:
        value = int(compact_model_wattage.group(1))
        if 300 <= value <= 2500:
            return value
    match = re.search(r"\b(\d{3,4})\s?W\b", title.upper())
    if match:
        return int(match.group(1))
    return None


def _psu_efficiency_rating(title: str) -> str | None:
    text = title.upper()
    if "TITANIUM" in text:
        return "TITANIUM"
    if "PLATINUM" in text:
        return "PLATINUM"
    if "GOLD" in text:
        return "GOLD"
    if "SILVER" in text:
        return "SILVER"
    if "BRONZE" in text:
        return "BRONZE"
    if "80+" in text or "80 PLUS" in text:
        return "UNKNOWN_80PLUS"
    if _psu_model_key(title) in GOLD_FULLY_MODULAR_PSU_MODELS:
        return "GOLD"
    return None


def _psu_modularity(title: str) -> str | None:
    text = title.upper()
    if re.search(r"\b(FULLY|FULL)\s+MODULAR\b", text):
        return "FULLY_MODULAR"
    if re.search(r"\bSEMI[- ]?MODULAR\b", text):
        return "SEMI_MODULAR"
    if re.search(r"\bNON[- ]?MODULAR\b", text):
        return "NON_MODULAR"
    if "MODULAR" in text:
        return "MODULAR_UNKNOWN"
    if _psu_model_key(title) in GOLD_FULLY_MODULAR_PSU_MODELS:
        return "FULLY_MODULAR"
    return None


def _psu_atx_version(title: str) -> str | None:
    text = title.upper()
    if re.search(r"\bATX\s?3\.1\b", text):
        return "ATX_3_1"
    if re.search(r"\bATX\s?3\.0\b", text):
        return "ATX_3_0"
    if re.search(r"\bATX\s?2\.\d\b", text):
        return "ATX_2_X"
    return None


def _psu_pcie_5_support(title: str) -> bool:
    text = title.upper()
    return bool(
        re.search(r"\bPCIE\s?5(?:\.0)?\b|\bPCI-E\s?5(?:\.0)?\b|\bATX\s?3\.[01]\b|\b12VHPWR\b", text)
        or _psu_model_key(title) in {"MAG_A850GL", "TOUGHPOWER_GF3", "TOUGHPOWER_GF_A3"}
    )


def _psu_native_12vhpwr(title: str) -> bool:
    return "12VHPWR" in title.upper() or "12V-2X6" in title.upper()


def _psu_warranty_years(title: str) -> int | None:
    match = re.search(r"\b(\d{1,2})\s?(?:YEAR|YR)\s+WARRANTY\b", title.upper())
    return int(match.group(1)) if match else None


def _psu_model_key(title: str) -> str | None:
    upper = re.sub(r"[^A-Z0-9]+", " ", title.upper()).strip()
    compact = compact_key(title)
    for phrase, key in PSU_MODEL_ALIASES:
        if re.search(rf"\b{re.escape(phrase)}\b", upper) or compact_key(phrase) in compact:
            return key
    return None


def _psu_fallback_model_key(title: str) -> str | None:
    tokens = normalize_model(title).upper().split()
    generic = {
        "850",
        "850W",
        "80",
        "PLUS",
        "GOLD",
        "FULLY",
        "FULL",
        "MODULAR",
        "ATX",
        "EFFICIENCY",
        "POWER",
        "SUPPLY",
        "PSU",
        "W",
    }
    kept = [token for token in tokens if token not in generic and not re.fullmatch(r"\d{3,4}W?", token)]
    if not kept:
        return None
    return "_".join(kept[:4])


def _psu_family_name(family_key: str) -> str:
    match = re.fullmatch(r"PSU_(\d{3,4})W_([A-Z0-9_]+)_([A-Z_]+)", family_key)
    if match:
        efficiency = match.group(2).replace("_", " ").title()
        modularity = match.group(3).replace("_", " ").title()
        return f"{match.group(1)}W {efficiency} {modularity} PSU"
    return family_key.replace("_", " ").title()


def _case_supported_motherboard_form_factors(title: str) -> list[str]:
    text = title.upper()
    if "E-ATX" in text or "EATX" in text:
        return ["E-ATX", "ATX", "mATX", "ITX"]
    if "ATX" in text or "MID TOWER" in text or "FULL TOWER" in text:
        return ["ATX", "mATX", "ITX"]
    if "MICRO ATX" in text or "MATX" in text or "M-ATX" in text:
        return ["mATX", "ITX"]
    if "MINI ITX" in text or "MINI-ITX" in text:
        return ["ITX"]
    return []


def _case_type(title: str) -> str | None:
    text = title.upper()
    if "FULL TOWER" in text:
        return "full_tower"
    if "MID TOWER" in text or "MID-TOWER" in text or "ATX" in text:
        return "mid_tower"
    if "MINI ITX" in text or "MINI-ITX" in text:
        return "mini_itx"
    return None


def _case_color(title: str) -> str | None:
    text = title.upper()
    if "WHITE" in text:
        return "white"
    if "BLACK" in text:
        return "black"
    return None


def _case_included_fans_count(title: str, family_key: str | None) -> int | None:
    match = re.search(r"\b(\d)\s?(?:X\s?)?(?:INCLUDED\s+)?FANS?\b", title.upper())
    if match:
        return int(match.group(1))
    if family_key == "CASE_CORSAIR_4000D_AIRFLOW":
        return 2
    return None


def _case_family_name(family_key: str) -> str:
    if family_key == "CASE_CORSAIR_4000D_AIRFLOW":
        return "Corsair 4000D Airflow"
    if family_key == "CASE_CORSAIR_4000D_RGB_AIRFLOW_V2":
        return "Corsair iCUE 4000D RGB Airflow V2"
    if family_key == "CASE_CORSAIR_4000X_RGB":
        return "Corsair 4000X RGB"
    if family_key == "CASE_CORSAIR_5000D_AIRFLOW":
        return "Corsair 5000D Airflow"
    if family_key == "CASE_CORSAIR_3000D_AIRFLOW":
        return "Corsair 3000D Airflow"
    return family_key.replace("_", " ").title()


def _cooler_model_key(title: str) -> str | None:
    upper = re.sub(r"[^A-Z0-9]+", " ", title.upper()).strip()
    compact = compact_key(title)
    for phrase, key in COOLER_MODEL_ALIASES:
        if re.search(rf"\b{re.escape(phrase)}\b", upper) or compact_key(phrase) in compact:
            return key
    return None


def _cooler_type(title: str) -> str | None:
    text = title.upper()
    model_key = _cooler_model_key(title)
    if model_key in {
        "AQUA_FROST",
        "LS520",
        "H100I",
        "KRAKEN",
        "KRAKEN_CORE",
        "KRAKEN_ELITE",
        "LIQUID_FREEZER_III",
        "MAG_CORELIQUID_A13",
        "CORELIQUID_A13",
        "NAUTILUS_240",
    }:
        return "aio_liquid"
    if model_key in {"PEERLESS_ASSASSIN", "AK620"}:
        return "air"
    if re.search(r"\bAIO\b|\bLIQUID\b|\bWATER\s+COOL", text):
        return "aio_liquid"
    if re.search(r"\bAIR\s+COOLER\b|\bTOWER\s+COOLER\b|\bHEATSINK\b", text):
        return "air"
    return None


def _cooler_radiator_size_mm(title: str) -> int | None:
    text = title.upper()
    match = re.search(r"\b(120|140|240|280|360|420)\s?MM\b", text)
    if match:
        return int(match.group(1))
    if _cooler_model_key(title) in {
        "AQUA_FROST",
        "LS520",
        "H100I",
        "KRAKEN",
        "KRAKEN_CORE",
        "KRAKEN_ELITE",
        "LIQUID_FREEZER_III",
        "MAG_CORELIQUID_A13",
        "CORELIQUID_A13",
        "NAUTILUS_240",
    }:
        return 240
    return None


def _cooler_radiator_fan_count(radiator_size_mm: int | None) -> int | None:
    if radiator_size_mm in {240, 280}:
        return 2
    if radiator_size_mm in {360, 420}:
        return 3
    if radiator_size_mm in {120, 140}:
        return 1
    return None


def _cooler_fan_size_mm(title: str, radiator_size_mm: int | None) -> int | None:
    match = re.search(r"\b(120|140)\s?MM\s+FAN", title.upper())
    if match:
        return int(match.group(1))
    if radiator_size_mm in {120, 240, 360}:
        return 120
    if radiator_size_mm in {140, 280, 420}:
        return 140
    if _cooler_model_key(title) in {"PEERLESS_ASSASSIN", "AK620"}:
        return 120
    return None


def _cooler_supported_sockets(title: str) -> list[str]:
    text = title.upper()
    compact = compact_key(title)
    sockets: list[str] = []
    if "AM5" in compact:
        sockets.append("AM5")
    if "AM4" in compact:
        sockets.append("AM4")
    if "LGA1700" in compact or "LGA 1700" in text:
        sockets.append("LGA1700")
    if _cooler_model_key(title) in {"LS520", "H100I", "KRAKEN", "LIQUID_FREEZER_III", "PEERLESS_ASSASSIN", "AK620"}:
        sockets = [*sockets, "AM5", "AM4", "LGA1700"]
    return list(dict.fromkeys(sockets))


def _cooler_supports_am5(title: str) -> bool:
    return "AM5" in _cooler_supported_sockets(title)


def _cooler_height_mm(title: str, model_key: str | None) -> int | None:
    match = re.search(r"\b(\d{2,3})\s?MM\s+(?:HEIGHT|TALL)\b", title.upper())
    if match:
        value = int(match.group(1))
        if 20 <= value <= 220:
            return value
    known = {
        "PEERLESS_ASSASSIN": 157,
        "AK620": 160,
    }
    return known.get(model_key or "") or None


def _cooler_tdp_rating_w(title: str, model_key: str | None) -> int | None:
    match = re.search(r"\b(\d{2,3})\s?W\s+(?:TDP|COOLING)\b", title.upper())
    if match:
        return int(match.group(1))
    if model_key in {
        "AQUA_FROST",
        "LS520",
        "H100I",
        "KRAKEN",
        "KRAKEN_CORE",
        "KRAKEN_ELITE",
        "LIQUID_FREEZER_III",
        "MAG_CORELIQUID_A13",
        "CORELIQUID_A13",
        "NAUTILUS_240",
    }:
        return 220
    if model_key in {"PEERLESS_ASSASSIN", "AK620"}:
        return 180
    return None


def _cooler_family_name(family_key: str) -> str:
    if family_key == "COOLER_AIO_240MM_AM5":
        return "240mm AIO CPU Cooler AM5"
    if family_key == "COOLER_AIO_240MM":
        return "240mm AIO CPU Cooler"
    if family_key == "COOLER_AIR_DUAL_TOWER_AM5":
        return "Dual Tower Air CPU Cooler AM5"
    if family_key == "COOLER_AIR_DUAL_TOWER":
        return "Dual Tower Air CPU Cooler"
    return family_key.replace("_", " ").title()


def _motherboard_chipset(title: str) -> str | None:
    compact = compact_key(title)
    if "B650" in compact:
        return "B650"
    if "X670" in compact:
        return "X670"
    if "A620" in compact:
        return "A620"
    if "B760" in compact:
        return "B760"
    if "Z790" in compact:
        return "Z790"
    return None


def _motherboard_socket(title: str) -> str | None:
    compact = compact_key(title)
    if "AM5" in compact:
        return "AM5"
    if "LGA1700" in compact:
        return "LGA1700"
    if _motherboard_chipset(title) == "B650" and _motherboard_model_key(title):
        return "AM5"
    return None


def _motherboard_memory_type(title: str) -> str | None:
    compact = compact_key(title)
    if "DDR5" in compact:
        return "DDR5"
    if "DDR4" in compact:
        return "DDR4"
    if _motherboard_chipset(title) == "B650" and _motherboard_model_key(title):
        return "DDR5"
    return None


def _motherboard_form_factor(title: str) -> str | None:
    upper = re.sub(r"[^A-Z0-9]+", " ", title.upper()).strip()
    if re.search(r"\bMINI\s+ITX\b|\bITX\b", upper):
        return "ITX"
    if re.search(r"\bMICRO\s+ATX\b|\bM\s+ATX\b|\bMATX\b", upper):
        return "mATX"
    if re.search(r"\bATX\b", upper):
        return "ATX"
    model_key = _motherboard_model_key(title)
    known = {
        "PRIME_B650M_A_WIFI_II": "mATX",
        "B650_TOMAHAWK_WIFI": "ATX",
        "TUF_B650_PLUS_WIFI": "ATX",
        "B650_AORUS_ELITE_AX": "ATX",
        "B650_AORUS_ELITE": "ATX",
        "B650_STEEL_LEGEND_WIFI": "ATX",
        "B650_STEEL_LEGEND": "ATX",
    }
    return known.get(model_key or "") or None


def _motherboard_model_key(title: str) -> str | None:
    upper = re.sub(r"[^A-Z0-9]+", " ", title.upper()).strip()
    compact = compact_key(title)
    for phrase, key in MOTHERBOARD_MODEL_ALIASES:
        if re.search(rf"\b{re.escape(phrase)}\b", upper) or compact_key(phrase) in compact:
            return key
    return None


def _motherboard_m2_slots(title: str, model_key: str | None) -> int | None:
    match = re.search(r"\b(\d)\s?(?:X\s?)?M\.?2\b", title.upper())
    if match:
        return int(match.group(1))
    known = {
        "PRIME_B650M_A_WIFI_II": 2,
        "B650_TOMAHAWK_WIFI": 3,
        "TUF_B650_PLUS_WIFI": 3,
        "B650_AORUS_ELITE_AX": 3,
        "B650_AORUS_ELITE": 3,
        "B650_STEEL_LEGEND_WIFI": 3,
        "B650_STEEL_LEGEND": 3,
    }
    return known.get(model_key or "") or None


def _motherboard_pcie_x16_slots(title: str, model_key: str | None) -> int:
    match = re.search(r"\b(\d)\s?(?:X\s?)?PCI(?:E| EXPRESS).*?X16\b", title.upper())
    if match:
        return int(match.group(1))
    return 1


def _motherboard_pcie_generation(title: str, chipset: str | None) -> str | None:
    text = title.upper()
    if re.search(r"\bPCIE\s?5(?:\.0)?\b|\bPCI-E\s?5(?:\.0)?\b", text):
        return "PCIe 5.0"
    if re.search(r"\bPCIE\s?4(?:\.0)?\b|\bPCI-E\s?4(?:\.0)?\b", text):
        return "PCIe 4.0"
    if chipset == "B650":
        return "PCIe 4.0"
    return None


def _motherboard_wifi(title: str, model_key: str | None) -> bool:
    return bool(
        re.search(r"\bWI[- ]?FI\b|\bWIFI\b|\bAX\b", title.upper())
        or (model_key or "").endswith(("WIFI", "AX"))
    )


def _motherboard_bios_flashback(title: str, model_key: str | None) -> bool | str:
    if re.search(r"\bBIOS\s+FLASH(?:BACK)?\b|\bFLASHBACK\b", title.upper()):
        return True
    known_flashback_models = {
        "PRIME_B650M_A_WIFI_II",
        "B650_TOMAHAWK_WIFI",
        "TUF_B650_PLUS_WIFI",
        "B650_AORUS_ELITE_AX",
        "B650_STEEL_LEGEND_WIFI",
    }
    if model_key in known_flashback_models:
        return True
    return "unknown"


def _motherboard_vrm_quality_hint(title: str, model_key: str | None) -> str | None:
    if model_key in {"B650_TOMAHAWK_WIFI", "TUF_B650_PLUS_WIFI", "B650_AORUS_ELITE_AX", "B650_STEEL_LEGEND_WIFI"}:
        return "mid_high"
    if model_key == "PRIME_B650M_A_WIFI_II":
        return "mainstream"
    if _motherboard_chipset(title) == "B650":
        return "mainstream"
    return None


def _motherboard_max_memory_gb(title: str) -> int | None:
    match = re.search(r"\b(?:UP\s+TO\s+)?(\d{2,4})\s?GB\b", title.upper())
    if match:
        value = int(match.group(1))
        if 64 <= value <= 512:
            return value
    return None


def _motherboard_memory_slots(title: str, form_factor: str | None) -> int | None:
    match = re.search(r"\b(\d)\s?(?:X\s?)?(?:DIMM|MEMORY\s+SLOTS?)\b", title.upper())
    if match:
        return int(match.group(1))
    if form_factor in {"ATX", "mATX"}:
        return 4
    if form_factor == "ITX":
        return 2
    return None


def _motherboard_family_name(family_key: str) -> str:
    if family_key == "MOTHERBOARD_B650_AM5_DDR5":
        return "B650 AM5 DDR5 Motherboard"
    return family_key.replace("_", " ").title()


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
        requested_category = normalize_category(record.category)
        category = (
            classify_category(record.title, record.category, record.specs)
            if requested_category == "Accessories"
            else requested_category
        )
        specs = infer_specs(record.title, category, record.specs)
        cpu_key = specs.get("cpu_model_key")
        if normalize_category(category) == "CPU" and cpu_key:
            if str(cpu_key).startswith("AMD_") and brand == "Unknown":
                brand = "AMD"
            elif str(cpu_key).startswith("INTEL_") and brand == "Unknown":
                brand = "Intel"
        storage_key = specs.get("storage_model_key")
        if normalize_category(category) == "Storage" and storage_key:
            if str(storage_key).startswith("SAMSUNG_") and brand == "Unknown":
                brand = "Samsung"
            elif str(storage_key).startswith("WD_") and brand == "Unknown":
                brand = "WD"
            elif str(storage_key).startswith("KINGSTON_") and brand == "Unknown":
                brand = "Kingston"
            elif str(storage_key).startswith("CRUCIAL_") and brand == "Unknown":
                brand = "Crucial"
            elif str(storage_key).startswith("LEXAR_") and brand == "Unknown":
                brand = "Lexar"
        classification = classify_product_type(record, category)
        market = classify_listing_market(record)
        specs["product_type"] = classification.product_type
        specs["product_type_confidence"] = classification.confidence
        if normalize_category(category) == "GPU":
            model, specs = enrich_gpu_identity(record.title, brand, model, specs)
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
            field_evidence(record, "product_type", specs.get("product_type")),
            field_evidence(record, "listing_condition", market.listing_condition),
            field_evidence(record, "seller_type", market.seller_type),
            field_evidence(record, "marketplace_risk_score", market.marketplace_risk_score),
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
            region=record.region or record.vendor_region,
            country_code=record.country_code,
            city=record.city,
            raw_price=record.price,
            item_price=record.price,
            final_landed_price=record.price + record.shipping_cost,
            final_landed_currency=record.currency,
            availability=record.availability,
            timestamp=record.source.timestamp,
            shipping_cost=record.shipping_cost,
            product_url=record.product_url,
            image_url=record.image_url,
            source_product_id=record.source_product_id,
            seller=record.seller,
            condition=record.condition,
            listing_condition=market.listing_condition,
            seller_type=market.seller_type,
            marketplace_risk_score=market.marketplace_risk_score,
            rating=record.rating,
            source=record.source,
            field_evidence=evidence,
            flags=market.flags,
        )


def _extract_gpu_family(title: str) -> tuple[str, str, str] | None:
    compact = compact_key(title)
    rtx = re.search(r"RTX(\d{4})(TISUPER|SUPER|TI)?", compact)
    if not rtx:
        rtx_reordered = re.search(r"RTX(TISUPER|SUPER|TI)(\d{4})", compact)
        if rtx_reordered:
            class _ReorderedMatch:
                def group(self, index: int) -> str:
                    return rtx_reordered.group(2) if index == 1 else rtx_reordered.group(1)

            rtx = _ReorderedMatch()  # type: ignore[assignment]
    if rtx:
        number = rtx.group(1)
        suffix = rtx.group(2) or ""
        suffix_label = {
            "TISUPER": "Ti Super",
            "SUPER": "Super",
            "TI": "Ti",
            "": "",
        }[suffix]
        chipset = " ".join(part for part in ("RTX", number, suffix_label.upper()) if part).strip()
        family_name = " ".join(part for part in ("NVIDIA GeForce RTX", number, suffix_label) if part).strip()
        family_key = f"NVIDIA_GEFORCE_RTX_{number}{'_' + suffix.upper() if suffix else ''}"
        return family_name, family_key, chipset

    gtx = re.search(r"GTX(\d{3,5})(TI)?", compact)
    if gtx:
        number = gtx.group(1)
        suffix = "Ti" if gtx.group(2) else ""
        chipset = " ".join(part for part in ("GTX", number, suffix.upper()) if part).strip()
        family_name = " ".join(part for part in ("NVIDIA GeForce GTX", number, suffix) if part).strip()
        family_key = f"NVIDIA_GEFORCE_GTX_{number}{'_TI' if suffix else ''}"
        return family_name, family_key, chipset

    rx = re.search(r"RX(\d{3,4})(XT|XTX)?", compact)
    if rx:
        number = rx.group(1)
        suffix = rx.group(2) or ""
        chipset = " ".join(part for part in ("RX", number, suffix) if part).strip()
        family_name = " ".join(part for part in ("AMD Radeon RX", number, suffix) if part).strip()
        family_key = f"AMD_RADEON_RX_{number}{'_' + suffix if suffix else ''}"
        return family_name, family_key, chipset

    return None


def _extract_gpu_board_sku(title: str) -> str | None:
    upper = re.sub(r"[^A-Z0-9]+", " ", title.upper()).strip()
    for phrase, normalized in GPU_SKU_ALIASES:
        if re.search(rf"\b{re.escape(phrase)}\b", upper):
            return normalized
    return None


def _brand_from_title(title: str, brands: tuple[str, ...]) -> str:
    upper_title = f" {re.sub(r'[^A-Z0-9]+', ' ', title.upper()).strip()} "
    for brand in sorted(brands, key=len, reverse=True):
        if re.search(rf"\b{re.escape(brand.upper())}\b", upper_title):
            return brand
    return ""
