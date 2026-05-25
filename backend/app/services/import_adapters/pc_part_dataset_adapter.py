from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


CRITICAL_FIELDS = {
    "CPU": ("socket",),
    "GPU": ("vram_gb", "tdp_w", "length_mm", "pcie_generation", "slots", "power_connectors"),
    "Motherboard": ("socket", "memory_type", "form_factor"),
    "RAM": ("memory_type", "capacity_gb"),
    "Case": ("supported_motherboard_form_factors",),
    "Cooler": ("socket_support", "radiator_size_mm", "height_mm"),
    "PSU": ("wattage_w",),
}


def load_pc_part_dataset_records(path: Path, category: str, limit: int | None) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("records") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("pc_part_dataset JSON must contain a list or records list")
    selected_rows = rows if limit is None else rows[:limit]
    return [adapt_pc_part_dataset_record(dict(row), category) for row in selected_rows if isinstance(row, dict)]


def adapt_pc_part_dataset_record(raw: dict[str, Any], category: str) -> dict[str, Any]:
    name = str(_get(raw, "name", "Name", "title") or "").strip()
    brand = str(_get(raw, "brand", "manufacturer") or _brand_from_name(name) or "").strip()
    specs, inferred, warnings = _map_specs(raw, category, name)
    missing = [field for field in CRITICAL_FIELDS.get(category, ()) if _missing(specs.get(field))]
    inferred_critical = [
        str(item.get("field"))
        for item in inferred
        if isinstance(item, dict) and str(item.get("field")) in CRITICAL_FIELDS.get(category, ())
    ]
    score = _compatibility_score(category, missing, inferred_critical)
    warnings.extend(f"missing critical compatibility field: {field}" for field in missing)
    warnings.extend(f"critical compatibility field is inferred, not confirmed: {field}" for field in inferred_critical)
    record = {
        "name": name,
        "raw_name": name,
        "brand": brand or None,
        "model": _model_from_name(name, brand),
        "category": category,
        "specs": specs,
        "aliases": _as_list(_get(raw, "aliases", "alias")),
        "image_url": _get(raw, "image", "image_url", "imageUrl"),
        "compatibility_ready": not missing and not inferred_critical,
        "compatibility_completeness_score": score,
        "missing_compatibility_fields": missing,
        "inferred_fields": inferred,
        "warning_reasons": warnings,
    }
    if category == "GPU":
        record["canonical_key"] = _gpu_card_canonical_key(
            brand=brand,
            name=name,
            chip_family=str(specs.get("chip_family") or specs.get("model") or ""),
        )
    return record


def _map_specs(raw: dict[str, Any], category: str, name: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    inferred: list[dict[str, Any]] = []
    if category == "CPU":
        socket = _clean_socket(_get(raw, "socket"))
        if not socket:
            socket, inference = _infer_cpu_socket(name)
            if inference:
                inferred.append(inference)
                warnings.append("socket inferred from CPU product family; verify before compatibility use")
        specs = {
            "socket": socket,
            "cores": _as_int(_get(raw, "core_count", "cores")),
            "threads": _as_int(_get(raw, "thread_count", "threads")),
            "tdp_w": _as_int(_get(raw, "tdp", "tdp_w")),
            "base_clock_ghz": _as_float(_get(raw, "core_clock", "base_clock")),
            "boost_clock_ghz": _as_float(_get(raw, "boost_clock")),
        }
        return _clean(specs), inferred, warnings
    if category == "GPU":
        chip_family = _get(raw, "chipset", "gpu_family", "chip_family")
        specs = {
            "chip_vendor": _gpu_chip_vendor(chip_family),
            "chip_family": chip_family,
            "model": chip_family or _get(raw, "model"),
            "vram_gb": _capacity_to_gb(_get(raw, "memory")),
            "length_mm": _as_int(_get(raw, "length")),
            "pcie_generation": _get(raw, "pcie_generation", "pcie", "interface"),
        }
        tdp = _as_int(_get(raw, "tdp", "power"))
        if tdp:
            inferred.append(
                {
                    "field": "tdp_w",
                    "inferred_value": tdp,
                    "inference_method": "pc-part-dataset power hint",
                    "confidence": 0.55,
                    "warning_reason": "GPU TDP is a performance hint, not confirmed official spec",
                }
            )
            specs["tdp_w"] = tdp
            warnings.append("GPU TDP stored as inferred performance hint")
        return _clean(specs), inferred, warnings
    if category == "Motherboard":
        specs = {
            "chipset": _get(raw, "chipset"),
            "socket": _clean_socket(_get(raw, "socket")),
            "memory_type": _memory_type_from_value(_get(raw, "memory_type", "memory")),
            "form_factor": _get(raw, "form_factor"),
            "m2_slots": _as_int(_get(raw, "m2_slots", "m.2_slots")),
            "pcie_x16_slots": _as_int(_get(raw, "pcie_x16_slots")),
        }
        return _clean(specs), inferred, warnings
    if category == "RAM":
        modules = _as_list(_get(raw, "modules"))
        speed_values = _as_list(_get(raw, "speed"))
        capacity_gb, kit_config = _parse_modules(modules)
        memory_type, speed_mhz, memory_type_inferred = _parse_memory_speed(speed_values)
        specs = {
            "memory_type": memory_type,
            "capacity_gb": capacity_gb,
            "speed_mhz": speed_mhz,
            "kit_config": kit_config,
            "cas_latency": _get(raw, "cas_latency", "cl"),
        }
        if specs["memory_type"] and memory_type_inferred:
            inferred.append(
                {
                    "field": "memory_type",
                    "inferred_value": specs["memory_type"],
                    "inference_method": "RAM speed range",
                    "confidence": 0.72,
                    "warning_reason": "DDR type inferred from listed speed",
                }
            )
        return _clean(specs), inferred, warnings
    if category == "Storage":
        capacity_gb = _capacity_to_gb(_get(raw, "capacity"))
        specs = {
            "capacity_gb": capacity_gb,
            "capacity_tb": round(capacity_gb / 1024, 2) if capacity_gb else None,
            "interface": _get(raw, "interface"),
            "form_factor": _get(raw, "form_factor"),
            "protocol": _storage_protocol(_get(raw, "interface", "form_factor")),
        }
        return _clean(specs), inferred, warnings
    if category == "PSU":
        specs = {
            "wattage_w": _as_int(_get(raw, "wattage")),
            "efficiency_rating": _get(raw, "efficiency"),
            "modularity": _get(raw, "modular"),
        }
        return _clean(specs), inferred, warnings
    if category == "Case":
        specs = {
            "supported_motherboard_form_factors": _as_list(_get(raw, "motherboard_form_factor", "type")),
            "max_gpu_length_mm": _as_int(_get(raw, "maximum_video_card_length")),
            "max_cpu_cooler_height_mm": _as_int(_get(raw, "maximum_cpu_cooler_height")),
        }
        if _missing(specs["max_gpu_length_mm"]) or _missing(specs["max_cpu_cooler_height_mm"]):
            warnings.append("case clearance_unknown; do not assume GPU or cooler fit")
        return _clean(specs), inferred, warnings
    if category == "Cooler":
        specs = {
            "cooler_type": _cooler_type(raw, name),
            "socket_support": _as_list(_get(raw, "socket_support", "sockets")),
            "radiator_size_mm": _as_int(_get(raw, "radiator_size")),
            "height_mm": _as_int(_get(raw, "height")),
        }
        if _missing(specs["radiator_size_mm"]) and _missing(specs["height_mm"]):
            warnings.append("cooler dimensions unknown; compatibility requires enrichment")
        return _clean(specs), inferred, warnings
    return {}, inferred, warnings


def _get(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    lowered = {str(key).lower(): value for key, value in raw.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _clean(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if not _missing(value)}


def _gpu_card_canonical_key(*, brand: str, name: str, chip_family: str) -> str:
    parts = ["GPU", brand or _brand_from_name(name) or "UNKNOWN", chip_family or "UNKNOWN_FAMILY", name]
    normalized = [
        re.sub(r"[^A-Z0-9]+", "_", str(part).upper()).strip("_")
        for part in parts
        if str(part).strip()
    ]
    return "|".join(normalized)


def _gpu_chip_vendor(chip_family: Any) -> str | None:
    text = str(chip_family or "").upper()
    if "GEFORCE" in text or text.startswith("RTX") or text.startswith("GTX"):
        return "NVIDIA"
    if "RADEON" in text or text.startswith("RX "):
        return "AMD"
    if "ARC" in text:
        return "Intel"
    return None


def _missing(value: Any) -> bool:
    return value in (None, "", [])


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        return [part.strip() for part in re.split(r"[,/]", stripped) if part.strip()]
    return [value]


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"\d+", str(value).replace(",", ""))
    return int(match.group(0)) if match else None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else None


def _first_int(values: list[Any]) -> int | None:
    for value in values:
        parsed = _as_int(value)
        if parsed:
            return parsed
    return None


def _brand_from_name(name: str) -> str | None:
    upper = name.upper()
    if upper.startswith("AMD ") or " RYZEN " in f" {upper} ":
        return "AMD"
    if upper.startswith("INTEL ") or upper.startswith("CORE "):
        return "Intel"
    if "NVIDIA" in upper or "GEFORCE" in upper or "RTX " in upper:
        return "NVIDIA"
    if "RADEON" in upper or re.search(r"\bRX\s?\d", upper):
        return "AMD"
    return None


def _model_from_name(name: str, brand: str) -> str:
    if brand and name.upper().startswith(brand.upper()):
        return name[len(brand) :].strip()
    return name


def _clean_socket(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).upper().replace("SOCKET", "").strip()
    text = text.replace("LGA ", "LGA").replace("AM ", "AM")
    return text or None


def _infer_cpu_socket(name: str) -> tuple[str | None, dict[str, Any] | None]:
    upper = name.upper()
    ryzen = re.search(r"RYZEN\s+\d\s+(\d{4})", upper)
    if ryzen:
        model = int(ryzen.group(1))
        if 7000 <= model < 10000:
            return "AM5", _inference("socket", "AM5", "Ryzen 7000/8000/9000 family", 0.8)
        if 1000 <= model < 6000:
            return "AM4", _inference("socket", "AM4", "Ryzen 1000-5000 family", 0.75)
    intel = re.search(r"(?:I[3579]-|CORE\s+\w+\s+)(1[234]\d{3})", upper)
    if intel:
        return "LGA1700", _inference("socket", "LGA1700", "Intel 12th/13th/14th generation family", 0.75)
    return None, None


def _inference(field: str, value: Any, method: str, confidence: float) -> dict[str, Any]:
    return {
        "field": field,
        "inferred_value": value,
        "inference_method": method,
        "confidence": confidence,
        "warning_reason": "Inferred compatibility value; verify before treating as official",
    }


def _memory_type_from_speed(speed_mhz: int | None) -> str | None:
    if speed_mhz is None:
        return None
    if 4800 <= speed_mhz <= 9000:
        return "DDR5"
    if 2133 <= speed_mhz < 4800:
        return "DDR4"
    return None


def _parse_memory_speed(speed_values: list[Any]) -> tuple[str | None, int | None, bool]:
    values = [_as_int(item) for item in speed_values]
    values = [item for item in values if item]
    if len(values) >= 2:
        generation, speed_mhz = values[0], values[1]
        if generation in {4, 5} and 2133 <= speed_mhz <= 9000:
            return f"DDR{generation}", speed_mhz, False
        return None, None, False
    speed_mhz = values[0] if values else None
    return _memory_type_from_speed(speed_mhz), speed_mhz, bool(speed_mhz)


def _memory_type_from_value(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).upper()
    if "DDR5" in text:
        return "DDR5"
    if "DDR4" in text:
        return "DDR4"
    parsed = _as_int(text)
    return _memory_type_from_speed(parsed)


def _parse_modules(modules: list[Any]) -> tuple[int | None, str | None]:
    if not modules:
        return None, None
    text = str(modules[0])
    match = re.search(r"(\d+)\s*x\s*(\d+)", text, flags=re.IGNORECASE)
    if match:
        count = int(match.group(1))
        size = int(match.group(2))
        if _valid_memory_module_pair(count, size):
            return count * size, f"{count}x{size}GB"
        return None, None
    values = [_as_int(item) for item in modules]
    values = [item for item in values if item]
    if len(values) >= 2:
        count, size = values[0], values[1]
        if _valid_memory_module_pair(count, size):
            return count * size, f"{count}x{size}GB"
        return None, None
    if values:
        return sum(values), f"{len(values)}x{values[0]}GB" if len(set(values)) == 1 else None
    return None, None


def _valid_memory_module_pair(count: int, size_gb: int) -> bool:
    return count in {1, 2, 4, 8} and size_gb in {4, 8, 16, 24, 32, 48, 64}


def _capacity_to_gb(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    text = str(value).upper().replace(" ", "")
    parsed = _as_float(text)
    if parsed is None:
        return None
    if "TB" in text:
        return int(parsed * 1024)
    return int(parsed)


def _storage_protocol(value: Any) -> str | None:
    text = str(value or "").upper()
    if "NVME" in text or "M.2" in text:
        return "NVMe"
    if "SATA" in text:
        return "SATA"
    return None


def _cooler_type(raw: dict[str, Any], name: str) -> str | None:
    value = _get(raw, "type")
    text = f"{value or ''} {name}".lower()
    if "aio" in text or "liquid" in text or "radiator" in text:
        return "AIO"
    if "air" in text or "heatsink" in text:
        return "Air"
    return value


def _compatibility_score(category: str, missing: list[str], inferred_critical: list[str] | None = None) -> float:
    critical = len(CRITICAL_FIELDS.get(category, ()))
    if critical == 0:
        return 1.0
    effective_missing = len(set(missing) | set(inferred_critical or []))
    return round(max(0.0, (critical - effective_missing) / critical), 2)
