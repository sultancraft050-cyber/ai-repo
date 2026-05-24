from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


CATALOG_PRODUCT_STATES = ("compatibility_ready", "metadata_only", "conflict_requires_review")
EXPANSION_PHASE = "phase2_saudi_core"


@dataclass(frozen=True)
class ExpansionTargetMatch:
    phase: str
    category: str
    family_key: str
    family_name: str
    priority: int
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
    families = [str(item) for item in category_config.get("families", [])]
    required_specs = tuple(str(item) for item in category_config.get("required_specs", []))
    family_entries = sorted(
        enumerate(families, start=1),
        key=lambda item: len(_normalize_text(item[1])),
        reverse=True,
    )
    for priority, family in family_entries:
        if _family_matches(category, family, haystack):
            return ExpansionTargetMatch(
                phase=str(manifest.get("phase") or EXPANSION_PHASE),
                category=category,
                family_key=_family_key(category, family),
                family_name=family,
                priority=priority,
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


def expansion_state(*, compatibility_ready: bool, metadata_only_count: int, conflict_count: int) -> str:
    if conflict_count > 0:
        return "conflict_requires_review"
    if compatibility_ready:
        return "compatibility_ready"
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


def _family_matches(category: str, family: str, haystack: str) -> bool:
    family_norm = _normalize_text(family)
    if category == "RAM":
        parts = family_norm.split()
        return all(part in haystack for part in parts)
    if category == "PSU":
        watts = re.search(r"\b(\d{3,4})W\b", family_norm)
        efficiency = "GOLD" if "GOLD" in family_norm else "PLATINUM" if "PLATINUM" in family_norm else ""
        return bool(watts and watts.group(1) in haystack and (not efficiency or efficiency in haystack))
    if category == "Cooler" and "AIO" in family_norm:
        return family_norm.replace(" ", "") in haystack.replace(" ", "") or ("AIO" in haystack and family_norm.split()[0] in haystack)
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
    text = re.sub(r"\s+", " ", text)
    return text.strip()
