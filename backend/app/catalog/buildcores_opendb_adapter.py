from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.catalog.models import (
    ImportSource, SourceType, ImageRightsStatus, ImportBatch, ImportRecord,
    ImportValidationStatus, ImportReviewStatus, ImportProposedAction, Product,
    ProductSpecification, ProductCategory
)
from app.catalog.import_pipeline import CatalogImportPipeline, stage_result, commit_batch

# Bounded category limits (per-spec: total <= 300):
CATEGORY_LIMITS = {
    "CPU": 40,
    "GPU": 40,
    "MOTHERBOARD": 40,
    "RAM": 40,
    "STORAGE": 40,
    "PSU": 30,
    "CASE": 30,
    "COOLER": 20,
}

CATEGORY_FOLDERS = {
    "CPU": "CPU",
    "GPU": "GPU",
    "MOTHERBOARD": "Motherboard",
    "RAM": "RAM",
    "STORAGE": "Storage",
    "PSU": "PSU",
    "CASE": "PCCase",
    "COOLER": "CPUCooler"
}

COMPATIBILITY_FIELDS = {
    "CPU": ["socket", "cores.total", "cores.threads", "clocks.performance.base", "clocks.performance.boost", "specifications.tdp", "specifications.integratedGraphics.model", "specifications.memory.types"],
    "GPU": ["chipset", "memory", "length", "total_slot_width", "tdp", "power_connectors"],
    "MOTHERBOARD": ["socket", "chipset", "form_factor", "memory.ram_type", "memory.slots", "memory.max", "storage_devices", "pcie_slots"],
    "RAM": ["ram_type", "capacity", "modules.quantity", "speed", "cas_latency", "form_factor"],
    "STORAGE": ["capacity", "interface", "form_factor", "nvme"],
    "PSU": ["wattage", "efficiency_rating", "form_factor", "modular", "connectors"],
    "CASE": ["supported_motherboard_form_factors", "max_video_card_length", "max_cpu_cooler_height", "power_supply"],
    "COOLER": ["cpu_sockets", "water_cooled", "height", "radiator_size"]
}

@dataclass
class CategoryStats:
    category: str
    files_discovered: int = 0
    records_parsed: int = 0
    valid_count: int = 0
    review_required_count: int = 0
    rejected_count: int = 0
    duplicate_count: int = 0
    missing_mpn_count: int = 0
    missing_gtin_count: int = 0
    missing_compatibility_fields: int = 0
    spec_keys_discovered: set[str] = field(default_factory=set)
    unmapped_fields: dict[str, int] = field(default_factory=dict)
    controlled_value_conflicts: int = 0

def get_git_revision(source_dir: Path) -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(source_dir),
            capture_output=True,
            text=True,
            check=True
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"

def validate_checkout(source_dir: Path) -> bool:
    if not source_dir.exists():
        return False
    if not (source_dir / "LICENSE.txt").exists():
        return False
    if not (source_dir / "README.md").exists():
        return False
    if not (source_dir / "schemas").exists():
        return False
    if not (source_dir / "open-db").exists():
        return False
    for cat, folder in CATEGORY_FOLDERS.items():
        schema_file = source_dir / "schemas" / f"{folder}.schema.json"
        if not schema_file.exists():
            return False
    return True

def extract_mpn(metadata: dict) -> str | None:
    part_numbers = metadata.get("part_numbers") or []
    name = metadata.get("name") or ""
    filtered = [p.strip() for p in part_numbers if p and p.strip() and p.strip().lower() != name.strip().lower()]
    if filtered:
        return filtered[0]
    if part_numbers:
        return part_numbers[0].strip()
    if name:
        return name.strip()
    return None

def has_reliable_identity(p_payload: dict) -> bool:
    if p_payload.get("gtin"):
        return True
    mpn = p_payload.get("manufacturer_part_number")
    name = p_payload.get("canonical_name") or p_payload.get("brand")
    if mpn and name and mpn.strip().lower() != name.strip().lower() and " " not in mpn:
        return True
    return False

def get_nested_val(data: dict, path_str: str) -> Any:
    parts = path_str.split(".")
    curr = data
    for p in parts:
        if isinstance(curr, dict):
            curr = curr.get(p)
        else:
            return None
    return curr

def add_spec(specs_list: list, p_payload: dict, key: str, normalized_val: Any, display_val: Any, unit: str | None = None):
    if normalized_val is not None and str(normalized_val).strip() != "":
        specs_list.append({
            "brand": p_payload["brand"],
            "manufacturer_part_number": p_payload["manufacturer_part_number"],
            "gtin": p_payload["gtin"],
            "specification_key": key,
            "normalized_value": str(normalized_val).strip(),
            "display_value": str(display_val).strip(),
            "unit": unit
        })

# Map specifications for CPU
def map_cpu_specs(data: dict, p_payload: dict, specs: list):
    socket = data.get("socket")
    add_spec(specs, p_payload, "socket", socket, socket)
    cores_total = data.get("cores", {}).get("total")
    if cores_total:
        add_spec(specs, p_payload, "core_count", cores_total, f"{cores_total} Cores")
    threads = data.get("cores", {}).get("threads")
    if threads:
        add_spec(specs, p_payload, "thread_count", threads, f"{threads} Threads")
    base_clk = data.get("clocks", {}).get("performance", {}).get("base")
    if base_clk:
        add_spec(specs, p_payload, "base_clock", base_clk, f"{base_clk} GHz", "ghz")
    boost_clk = data.get("clocks", {}).get("performance", {}).get("boost")
    if boost_clk:
        add_spec(specs, p_payload, "boost_clock", boost_clk, f"{boost_clk} GHz", "ghz")
    tdp = data.get("specifications", {}).get("tdp")
    if tdp:
        add_spec(specs, p_payload, "tdp", tdp, f"{tdp} W", "w")
    igpu = data.get("specifications", {}).get("integratedGraphics", {}).get("model")
    if igpu:
        add_spec(specs, p_payload, "integrated_graphics", igpu, igpu)
    mem_types = data.get("specifications", {}).get("memory", {}).get("types")
    if mem_types:
        val = ", ".join(mem_types)
        add_spec(specs, p_payload, "supported_memory_generation", val, val)

# Map specifications for GPU
def map_gpu_specs(data: dict, p_payload: dict, specs: list):
    chipset = data.get("chipset")
    add_spec(specs, p_payload, "chipset", chipset, chipset)
    vram = data.get("memory")
    if vram:
        add_spec(specs, p_payload, "vram", vram, f"{vram} GB", "gb")
    length = data.get("length")
    if length:
        add_spec(specs, p_payload, "length", length, f"{length} mm", "mm")
    slot_width = data.get("total_slot_width") or data.get("case_expansion_slot_width")
    if slot_width:
        add_spec(specs, p_payload, "slot_width", slot_width, f"{slot_width} Slots")
    tdp = data.get("tdp")
    if tdp:
        add_spec(specs, p_payload, "power_consumption", tdp, f"{tdp} W", "w")
    connectors = data.get("power_connectors")
    if connectors and isinstance(connectors, dict):
        parts = [f"{v}x {k.replace('pcie_', '').replace('_', ' ').title()}" for k, v in connectors.items() if v and v > 0]
        if parts:
            val = ", ".join(parts)
            add_spec(specs, p_payload, "power_connectors", val, val)

# Map specifications for Motherboard
def map_motherboard_specs(data: dict, p_payload: dict, specs: list):
    socket = data.get("socket")
    add_spec(specs, p_payload, "socket", socket, socket)
    chipset = data.get("chipset")
    add_spec(specs, p_payload, "chipset", chipset, chipset)
    ff = data.get("form_factor")
    add_spec(specs, p_payload, "form_factor", ff, ff)
    ram_type = data.get("memory", {}).get("ram_type")
    add_spec(specs, p_payload, "memory_generation", ram_type, ram_type)
    slots = data.get("memory", {}).get("slots")
    if slots:
        add_spec(specs, p_payload, "memory_slots", slots, str(slots))
    max_mem = data.get("memory", {}).get("max")
    if max_mem:
        add_spec(specs, p_payload, "maximum_memory", max_mem, f"{max_mem} GB", "gb")
    storage = data.get("storage_devices")
    if storage and isinstance(storage, dict):
        parts = [f"{v}x {k.replace('_', ' ').upper()}" for k, v in storage.items() if v and v > 0]
        if parts:
            val = ", ".join(parts)
            add_spec(specs, p_payload, "storage_interfaces", val, val)
    pcie = data.get("pcie_slots")
    if pcie and isinstance(pcie, list):
        parts = [f"Gen {item.get('gen')} x{item.get('length')}" for item in pcie if item.get("gen") or item.get("length")]
        if parts:
            val = ", ".join(parts)
            add_spec(specs, p_payload, "pcie_information", val, val)

# Map specifications for RAM
def map_ram_specs(data: dict, p_payload: dict, specs: list):
    ram_type = data.get("ram_type")
    add_spec(specs, p_payload, "memory_generation", ram_type, ram_type)
    capacity = data.get("capacity")
    if capacity:
        add_spec(specs, p_payload, "capacity", capacity, f"{capacity} GB", "gb")
    qty = data.get("modules", {}).get("quantity")
    if qty:
        add_spec(specs, p_payload, "module_count", qty, str(qty))
    speed = data.get("speed")
    if speed:
        add_spec(specs, p_payload, "speed", speed, f"{speed} MHz", "mhz")
    cas = data.get("cas_latency")
    if cas:
        add_spec(specs, p_payload, "latency", cas, f"CL{cas}")
    ff = data.get("form_factor")
    add_spec(specs, p_payload, "form_factor", ff, ff)

# Map specifications for Storage
def map_storage_specs(data: dict, p_payload: dict, specs: list):
    cap = data.get("capacity")
    if cap:
        add_spec(specs, p_payload, "capacity", cap, f"{cap} GB", "gb")
    interface = data.get("interface")
    add_spec(specs, p_payload, "interface", interface, interface)
    ff = data.get("form_factor")
    add_spec(specs, p_payload, "form_factor", ff, ff)
    nvme = data.get("nvme")
    if nvme is not None:
        protocol = "NVMe" if nvme else "SATA"
        add_spec(specs, p_payload, "protocol", protocol, protocol)

# Map specifications for PSU
def map_psu_specs(data: dict, p_payload: dict, specs: list):
    wattage = data.get("wattage")
    if wattage:
        add_spec(specs, p_payload, "wattage", wattage, f"{wattage} W", "w")
    eff = data.get("efficiency_rating")
    add_spec(specs, p_payload, "efficiency_rating", eff, eff)
    ff = data.get("form_factor")
    add_spec(specs, p_payload, "form_factor", ff, ff)
    modular = data.get("modular")
    add_spec(specs, p_payload, "modularity", modular, modular)
    conn = data.get("connectors")
    if conn and isinstance(conn, dict):
        parts = [f"{v}x {k.replace('_', ' ').title()}" for k, v in conn.items() if v and v > 0]
        if parts:
            val = ", ".join(parts)
            add_spec(specs, p_payload, "connectors", val, val)

# Map specifications for Case
def map_case_specs(data: dict, p_payload: dict, specs: list):
    mbs = data.get("supported_motherboard_form_factors")
    if mbs and isinstance(mbs, list):
        val = ", ".join(mbs)
        add_spec(specs, p_payload, "supported_motherboard_form_factors", val, val)
    gpu_len = data.get("max_video_card_length")
    if gpu_len:
        add_spec(specs, p_payload, "maximum_gpu_length", gpu_len, f"{gpu_len} mm", "mm")
    cooler_ht = data.get("max_cpu_cooler_height")
    if cooler_ht:
        add_spec(specs, p_payload, "maximum_cooler_height", cooler_ht, f"{cooler_ht} mm", "mm")
    psu = data.get("power_supply")
    add_spec(specs, p_payload, "psu_support", psu, psu)

# Map specifications for Cooler
def map_cooler_specs(data: dict, p_payload: dict, specs: list):
    sockets = data.get("cpu_sockets")
    if sockets and isinstance(sockets, list):
        val = ", ".join(sockets)
        add_spec(specs, p_payload, "supported_sockets", val, val)
    wc = data.get("water_cooled")
    if wc is not None:
        c_type = "Liquid / AIO" if wc else "Air Cooler"
        add_spec(specs, p_payload, "cooler_type", c_type, c_type)
    height = data.get("height")
    if height:
        add_spec(specs, p_payload, "height", height, f"{height} mm", "mm")
    rad = data.get("radiator_size")
    if rad:
        add_spec(specs, p_payload, "radiator_size", rad, f"{rad} mm", "mm")

def map_specs(category: str, data: dict, p_payload: dict, specs: list):
    dispatch = {
        "CPU": map_cpu_specs,
        "GPU": map_gpu_specs,
        "MOTHERBOARD": map_motherboard_specs,
        "RAM": map_ram_specs,
        "STORAGE": map_storage_specs,
        "PSU": map_psu_specs,
        "CASE": map_case_specs,
        "COOLER": map_cooler_specs
    }
    func = dispatch.get(category)
    if func:
        func(data, p_payload, specs)

def parse_opendb_record(filepath: Path, category: str, stats: CategoryStats) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    stats.records_parsed += 1
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        stats.rejected_count += 1
        return None, []

    metadata = data.get("metadata") or {}
    brand = metadata.get("manufacturer") or ""
    canonical_name = metadata.get("name") or ""
    
    # Trace unmapped fields
    standard_keys = {"opendb_id", "metadata", "general_product_information"}
    for k in data.keys():
        if k not in standard_keys:
            mapped_for_cat = {
                "CPU": {"socket", "cores", "clocks", "specifications", "series", "microarchitecture", "coreFamily", "cache"},
                "GPU": {"chipset", "memory", "length", "total_slot_width", "case_expansion_slot_width", "tdp", "power_connectors", "chipset_manufacturer", "core_count", "core_base_clock", "core_boost_clock", "memory_type", "effective_memory_clock", "memory_bus", "interface", "frame_sync", "color", "lighting", "cooling", "video_outputs"},
                "MOTHERBOARD": {"socket", "chipset", "form_factor", "memory", "storage_devices", "pcie_slots", "color", "lighting", "m2_slots", "onboard_ethernet", "wireless_networking", "usb_headers", "fan_headers", "rgb_headers", "front_panel_headers", "other_headers", "power_connectors", "ecc_support", "raid_support", "back_connect_connectors", "bios_features", "audio", "back_panel_ports"},
                "RAM": {"ram_type", "capacity", "modules", "speed", "cas_latency", "form_factor", "profile_support", "color", "timings", "voltage", "ecc", "registered", "heat_spreader", "rgb", "lighting", "height"},
                "STORAGE": {"capacity", "interface", "form_factor", "nvme", "storage_type", "cache", "lighting"},
                "PSU": {"wattage", "efficiency_rating", "form_factor", "modular", "connectors", "cybernetics_efficiency_rating", "cybernetics_noise_rating", "color", "lighting", "length", "fanless"},
                "CASE": {"supported_motherboard_form_factors", "max_video_card_length", "max_cpu_cooler_height", "power_supply", "form_factor", "color", "lighting", "power_supply_included", "supported_power_supply_form_factors", "side_panel", "has_transparent_side_panel", "front_panel_usb", "front_usb_ports", "max_psu_length", "internal_3_5_bays", "internal_2_5_bays", "external_3_5_bays", "external_5_25_bays", "power_supply_shroud", "expansion_slots", "riser_expansion_slots", "supports_rear_connecting_motherboard", "dimensions", "dimensions_mm", "volume", "weight"},
                "COOLER": {"cpu_sockets", "water_cooled", "height", "radiator_size", "min_fan_rpm", "max_fan_rpm", "min_noise_level", "max_noise_level", "color", "lighting", "fanless", "fan_size", "fan_quantity"}
            }.get(category, set())
            
            if k not in mapped_for_cat:
                stats.unmapped_fields[k] = stats.unmapped_fields.get(k, 0) + 1

    # Extract MPN
    mpn = extract_mpn(metadata)
    if not mpn:
        stats.missing_mpn_count += 1
    
    # Check GTIN
    gtin = None
    stats.missing_gtin_count += 1
    
    # Check compatibility-relevant fields missing
    comp_fields = COMPATIBILITY_FIELDS.get(category, [])
    for cf in comp_fields:
        val = get_nested_val(data, cf)
        if val is None or str(val).strip() == "":
            stats.missing_compatibility_fields += 1

    # Check controlled-value conflicts
    try:
        ProductCategory(category)
    except ValueError:
        stats.controlled_value_conflicts += 1
        stats.rejected_count += 1
        return None, []
        
    socket = data.get("socket") or data.get("cpu_sockets")
    if socket:
        if isinstance(socket, list) and not socket:
            stats.controlled_value_conflicts += 1

    # Build product payload
    slug = re.sub(r"[^a-z0-9]+", "-", canonical_name.lower()).strip("-")
    p_payload = {
        "brand": brand or "Unknown",
        "manufacturer_part_number": mpn or "",
        "gtin": gtin,
        "exact_model": metadata.get("variant") or metadata.get("name"),
        "variant": metadata.get("variant") or "",
        "canonical_name": canonical_name or "Unknown",
        "category": category,
        "slug": slug,
        "lifecycle_status": "active",
        "approval_status": "pending"
    }

    # Build specification payloads
    specs: list[dict[str, Any]] = []
    map_specs(category, data, p_payload, specs)
    
    for sp in specs:
        stats.spec_keys_discovered.add(sp["specification_key"])

    return p_payload, specs
