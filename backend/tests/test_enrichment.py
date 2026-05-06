from __future__ import annotations

from app.services.hardware_enrichment import HardwareEnrichmentEngine


def test_gpu_enrichment_scores_ai_and_power() -> None:
    facts = {
        "id": "gpu:test",
        "name": "NVIDIA GeForce RTX 4070 Super",
        "category": "GPU",
        "price": 599,
        "vendor_count": 3,
        "specs": {"raster_score": 36000, "compute_score": 48, "vram_gb": 12},
        "power": {"board_power_w": 220, "peak_w": 310},
        "bandwidth": {"pcie_generation_required": 4, "pcie_lanes_required": 16},
        "raw": {},
        "price_snapshots": [
            {"price": 649, "shipping_cost": 0, "accepted": True},
            {"price": 629, "shipping_cost": 0, "accepted": True},
            {"price": 599, "shipping_cost": 0, "accepted": True},
        ],
    }
    intelligence = HardwareEnrichmentEngine().enrich(facts)
    assert intelligence.benchmark.gaming > 60
    assert intelligence.benchmark.ai_ml > 40
    assert intelligence.power_thermal.recommended_psu_w is not None
    assert intelligence.market.price_trend == "falling"


def test_cpu_enrichment_explains_cache_and_platform() -> None:
    facts = {
        "id": "cpu:test",
        "name": "AMD Ryzen 7 7800X3D",
        "category": "CPU",
        "price": 369,
        "vendor_count": 2,
        "specs": {
            "single_thread_score": 3050,
            "multi_thread_score": 36000,
            "cache_mb": 104,
            "socket": "AM5",
            "memory_type": "DDR5",
        },
        "power": {"tdp_w": 120},
        "bandwidth": {"pcie_generation": 5, "memory_gbps": 89},
        "raw": {},
        "price_snapshots": [],
    }
    intelligence = HardwareEnrichmentEngine().enrich(facts)
    assert intelligence.benchmark.cache_efficiency >= 100
    assert intelligence.longevity.future_proof_score > 60
    assert any("cache" in item.lower() for item in intelligence.recommendation_summary)
