from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


CATALOG_PRODUCT_STATES = (
    "compatibility_ready_exact",
    "compatibility_ready_family",
    "metadata_only",
    "conflict_requires_review",
)
EXPANSION_PHASE = "phase2_saudi_core"
PRIORITY_TIERS = ("current_gen_priority", "value_fallback", "legacy_deprioritized")
PRIORITY_TIER_WEIGHTS = {
    "current_gen_priority": 0,
    "value_fallback": 1000,
    "legacy_deprioritized": 2000,
}


@dataclass(frozen=True)
class ExpansionTargetMatch:
    phase: str
    category: str
    family_key: str
    family_name: str
    priority: int
    priority_tier: str
    required_specs: tuple[str, ...]


def _manifest_path() -> Path:
    module_path = Path(__file__).resolve()
    candidates = (
        module_path.parents[2] / "data" / "catalog_targets" / "phase2_saudi_core.json",
        module_path.parents[3] / "backend" / "data" / "catalog_targets" / "phase2_saudi_core.json",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def load_expansion_manifest() -> dict[str, Any]:
    return json.loads(_manifest_path().read_text(encoding="utf-8"))


def safe_batch_size(category: str, *, operation: str = "stage") -> int:
    category_config = load_expansion_manifest().get("categories", {}).get(category, {})
    key = "safe_commit_batch_size" if operation == "commit" else "safe_stage_batch_size"
    return int(category_config.get(key) or 100)


def required_specs_for_category(category: str) -> tuple[str, ...]:
    values = load_expansion_manifest().get("categories", {}).get(category, {}).get("required_specs", [])
    return tuple(str(value) for value in values)


def manifest_categories() -> set[str]:
    return set(load_expansion_manifest().get("categories", {}).keys())


def match_expansion_target(record: dict[str, Any], category: str) -> ExpansionTargetMatch | None:
    manifest = load_expansion_manifest()
    category_config = manifest.get("categories", {}).get(category)
    if not category_config:
        return None
    haystack = _record_haystack(record)
    families = _family_entries(category_config)
    required_specs = tuple(str(item) for item in category_config.get("required_specs", []))
    family_entries = sorted(
        families,
        key=lambda item: len(_normalize_text(item["name"])),
        reverse=True,
    )
    for family_entry in family_entries:
        family = str(family_entry["name"])
        if _family_matches(category, family, haystack):
            return ExpansionTargetMatch(
                phase=str(manifest.get("phase") or EXPANSION_PHASE),
                category=category,
                family_key=_family_key(category, family),
                family_name=family,
                priority=_family_priority(family_entry),
                priority_tier=str(family_entry["priority_tier"]),
                required_specs=required_specs,
            )
    return None


def annotate_expansion_target(record: dict[str, Any], category: str) -> ExpansionTargetMatch | None:
    match = match_expansion_target(record, category)
    if not match:
        return None
    record["expansion_phase"] = match.phase
    record["target_family_key"] = match.family_key
    record["target_family_name"] = match.family_name
    record["expansion_priority"] = match.priority
    record["priority_tier"] = match.priority_tier
    missing = _missing_required_specs(record, match.required_specs)
    if missing:
        existing = record.get("missing_compatibility_fields") or []
        record["missing_compatibility_fields"] = list(dict.fromkeys([*existing, *missing]))
        record["compatibility_ready"] = False
        record["required_specs_present"] = False
    elif record.get("compatibility_ready") is None:
        record["compatibility_ready"] = True
        record["required_specs_present"] = True
    return match


def expansion_state(
    *,
    compatibility_ready: bool,
    metadata_only_count: int,
    conflict_count: int,
    family_ready_count: int = 0,
) -> str:
    if conflict_count > 0:
        return "conflict_requires_review"
    if compatibility_ready:
        return "compatibility_ready_exact"
    if family_ready_count > 0:
        return "compatibility_ready_family"
    return "metadata_only"


def _record_haystack(record: dict[str, Any]) -> str:
    specs = record.get("specs")
    if isinstance(specs, str):
        specs_text = specs
    else:
        specs_text = json.dumps(specs or {}, sort_keys=True)
    values = [
        record.get("raw_name"),
        record.get("name"),
        record.get("normalized_name"),
        record.get("canonical_key"),
        record.get("brand"),
        record.get("model"),
        specs_text,
    ]
    return _normalize_text(" ".join(str(value) for value in values if value))


def _family_entries(category_config: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for index, raw in enumerate(category_config.get("families") or [], start=1):
        if isinstance(raw, dict):
            name = str(raw.get("name") or "").strip()
            tier = str(raw.get("priority_tier") or "current_gen_priority").strip()
        else:
            name = str(raw).strip()
            tier = "current_gen_priority"
        if not name:
            continue
        if tier not in PRIORITY_TIER_WEIGHTS:
            tier = "current_gen_priority"
        entries.append({"name": name, "priority_tier": tier, "rank": index})
    return entries


def _family_priority(family_entry: dict[str, Any]) -> int:
    tier = str(family_entry.get("priority_tier") or "current_gen_priority")
    rank = int(family_entry.get("rank") or 0)
    return PRIORITY_TIER_WEIGHTS.get(tier, 0) + rank


def _family_matches(category: str, family: str, haystack: str) -> bool:
    family_norm = _normalize_text(family)
    if category in {"RAM", "Storage", "Case"}:
        parts = family_norm.split()
        return all(part in haystack for part in parts)
    if category == "PSU":
        watts = re.search(r"\b(\d{3,4})W\b", family_norm)
        efficiency = "GOLD" if "GOLD" in family_norm else "PLATINUM" if "PLATINUM" in family_norm else ""
        needs_atx3 = "ATX 3 0" in family_norm or "ATX 3 1" in family_norm
        needs_pcie5 = "PCIE 5" in family_norm or "12VHPWR" in family_norm or "12V2X6" in family_norm
        atx3_match = not needs_atx3 or any(token in haystack for token in ("ATX 3 0", "ATX 3 1", "ATX3", "ATX31", "ATX30"))
        pcie5_match = not needs_pcie5 or any(token in haystack for token in ("PCIE 5", "PCIE5", "12VHPWR", "12V 2X6", "12V2X6"))
        modular_match = "FULLY MODULAR" not in family_norm or "FULLY MODULAR" in haystack
        return bool(
            watts
            and watts.group(1) in haystack
            and (not efficiency or efficiency in haystack)
            and atx3_match
            and pcie5_match
            and modular_match
        )
    if category == "Motherboard":
        parts = [
            part
            for part in family_norm.split()
            if part not in {"INTEL"}
        ]
        return all(part in haystack for part in parts)
    if category == "Cooler" and "AIO" in family_norm:
        parts = family_norm.split()
        size = next((part for part in parts if part.endswith("MM")), "")
        socket_parts = [part for part in parts if part in {"AM5", "LGA1851", "LGA1700"}]
        return (
            ("AIO" in haystack or "LIQUID" in haystack)
            and (not size or size in haystack)
            and all(part in haystack for part in socket_parts)
        )
    if category == "Cooler":
        parts = family_norm.split()
        return all(part in haystack for part in parts)
    return family_norm in haystack


def _missing_required_specs(record: dict[str, Any], required_specs: tuple[str, ...]) -> list[str]:
    specs = record.get("specs")
    if isinstance(specs, str):
        try:
            decoded = json.loads(specs)
        except json.JSONDecodeError:
            decoded = {}
        specs = decoded if isinstance(decoded, dict) else {}
    if not isinstance(specs, dict):
        specs = {}
    inferred_fields = record.get("inferred_fields") or []
    inferred_names = {
        str(item.get("field"))
        for item in inferred_fields
        if isinstance(item, dict) and item.get("field")
    }
    missing: list[str] = []
    for field in required_specs:
        if specs.get(field) in (None, "", []):
            missing.append(field)
        elif field in inferred_names:
            missing.append(field)
    return missing


def _family_key(category: str, family: str) -> str:
    return f"{category}|{_normalize_text(family).replace(' ', '_')}"


def _normalize_text(value: str) -> str:
    text = value.upper().replace("-", " ")
    text = re.sub(r"\b(\d+)\s*GB\b", r"\1 GB", text)
    text = re.sub(r"\b(\d+)\s*TB\b", r"\1 TB", text)
    text = text.replace("WI FI", "WIFI").replace("WI-FI", "WIFI")
    text = text.replace("M ATX", "MATX").replace("MICRO ATX", "MATX")
    text = text.replace("PCI E", "PCIE")
    text = text.replace("PCIE4", "PCIE 4").replace("PCIE5", "PCIE 5")
    text = text.replace("12V 2X6", "12V2X6")
    text = re.sub(r"\s+", " ", text)
    return text.strip()
