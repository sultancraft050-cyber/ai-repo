from __future__ import annotations

from datetime import UTC, datetime
from statistics import mean
from typing import Any

from app.graph.pricing_repository import Neo4jPricingRepository
from app.graph.telemetry_repository import Neo4jTelemetryRepository
from app.models.intelligence import (
    BenchmarkScores,
    CompatibilityEnrichment,
    EnrichmentRequest,
    EnrichmentResponse,
    HardwareIntelligence,
    IntelligenceWarning,
    LongevityProfile,
    MarketIntelligence,
    PowerThermalProfile,
    WorkloadSuitability,
)
from app.models.telemetry import TelemetrySummary
from app.services.telemetry_analysis import TelemetryAnalysisEngine


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _score(value: float, baseline: float, *, curve: float = 1.0) -> float:
    if baseline <= 0:
        return 0
    normalized = max(0.0, value / baseline)
    curved = normalized**curve
    return round(max(0.0, min(100.0, curved * 100)), 1)


def _label(score: float) -> str:
    if score >= 82:
        return "excellent"
    if score >= 66:
        return "strong"
    if score >= 42:
        return "usable"
    return "limited"


def _confidence(
    facts: dict[str, Any],
    benchmark: BenchmarkScores,
    telemetry_summary: TelemetrySummary | None = None,
) -> str:
    non_zero = sum(value > 0 for value in benchmark.model_dump().values())
    vendor_count = facts.get("vendor_count", 0)
    telemetry_samples = telemetry_summary.sample_count if telemetry_summary else 0
    if telemetry_samples >= 8 and telemetry_summary and telemetry_summary.confidence == "high":
        return "high"
    if non_zero >= 5 and vendor_count >= 2:
        return "high"
    if telemetry_samples >= 3 or non_zero >= 3 or vendor_count >= 1:
        return "medium"
    return "low"


class HardwareEnrichmentEngine:
    def enrich(
        self,
        facts: dict[str, Any],
        telemetry_summary: TelemetrySummary | None = None,
    ) -> HardwareIntelligence:
        telemetry_summary = telemetry_summary if telemetry_summary and telemetry_summary.sample_count else None
        benchmark = self._apply_telemetry(self._benchmark_scores(facts), facts, telemetry_summary)
        workloads = self._workloads(facts, benchmark)
        power = self._power_thermal(facts, benchmark, telemetry_summary)
        longevity = self._longevity(facts, benchmark)
        compatibility = self._compatibility(facts)
        market = self._market(facts, benchmark)
        warnings = self._warnings(facts, power, compatibility, market, telemetry_summary)
        summary = self._summary(facts, benchmark, workloads, power, longevity, market, telemetry_summary)
        return HardwareIntelligence(
            product_id=facts["id"],
            product_name=str(facts.get("name") or facts["id"]),
            category=str(facts.get("category") or "Accessories"),
            generated_at=datetime.now(UTC),
            confidence=_confidence(facts, benchmark, telemetry_summary),
            benchmark=benchmark,
            workloads=workloads,
            power_thermal=power,
            longevity=longevity,
            compatibility=compatibility,
            market=market,
            telemetry=telemetry_summary,
            recommendation_summary=summary,
            warnings=warnings,
            evidence={
                "spec_fields": sorted(facts.get("specs", {}).keys()),
                "power_fields": sorted(facts.get("power", {}).keys()),
                "bandwidth_fields": sorted(facts.get("bandwidth", {}).keys()),
                "price_snapshot_count": len(facts.get("price_snapshots", [])),
                "vendor_count": facts.get("vendor_count", 0),
                "telemetry_sample_count": telemetry_summary.sample_count if telemetry_summary else 0,
                "telemetry_resolutions": telemetry_summary.covered_resolutions if telemetry_summary else [],
                "telemetry_primary_limiter": telemetry_summary.primary_limiter if telemetry_summary else "none",
            },
        )

    def _benchmark_scores(self, facts: dict[str, Any]) -> BenchmarkScores:
        category = facts.get("category")
        specs = facts.get("specs", {})
        power = facts.get("power", {})
        bandwidth = facts.get("bandwidth", {})
        raw = facts.get("raw", {})

        single = _score(_num(specs.get("single_thread_score")), 3200)
        multi = _score(_num(specs.get("multi_thread_score")), 62000)
        raster = _score(_num(specs.get("raster_score")), 46000)
        compute = _score(_num(specs.get("compute_score")), 62)
        ray = _score(_num(specs.get("ray_tracing_score"), _num(specs.get("raster_score")) * 0.55), 30000)
        vram = _score(_num(specs.get("vram_gb")), 24, curve=0.8)
        tensor = _score(_num(specs.get("tensor_score"), _num(specs.get("compute_score")) * 1.1), 85)
        memory_bw = _score(_num(bandwidth.get("memory_gbps")), 110)

        tdp = _num(power.get("tdp_w") or power.get("board_power_w") or power.get("peak_w"))
        perf_anchor = max(single * 0.35 + multi * 0.4, raster * 0.5 + compute * 0.35, memory_bw)
        thermal = round(max(0.0, min(100.0, perf_anchor / max(tdp, 35) * 62)), 1) if tdp else 50.0

        if category == "CPU":
            gaming = round(single * 0.52 + multi * 0.18 + _score(_num(specs.get("cache_mb")), 96) * 0.3, 1)
            productivity = round(single * 0.25 + multi * 0.65 + memory_bw * 0.1, 1)
            simulation = round(single * 0.28 + multi * 0.55 + memory_bw * 0.17, 1)
            rendering = round(multi * 0.8 + thermal * 0.2, 1)
            ai = round(multi * 0.35 + memory_bw * 0.25, 1)
        elif category == "GPU":
            gaming = round(raster * 0.62 + ray * 0.18 + vram * 0.2, 1)
            productivity = round(compute * 0.5 + vram * 0.25 + raster * 0.15, 1)
            simulation = round(compute * 0.45 + vram * 0.3 + raster * 0.1, 1)
            rendering = round(compute * 0.48 + ray * 0.22 + vram * 0.2, 1)
            ai = round(tensor * 0.58 + vram * 0.32 + compute * 0.1, 1)
        elif category == "RAM":
            gaming = round(memory_bw * 0.48 + _score(_num(specs.get("capacity_gb")), 64) * 0.28, 1)
            productivity = round(memory_bw * 0.42 + _score(_num(specs.get("capacity_gb")), 128) * 0.45, 1)
            simulation = round(memory_bw * 0.48 + _score(_num(specs.get("capacity_gb")), 128) * 0.42, 1)
            rendering = productivity
            ai = round(_score(_num(specs.get("capacity_gb")), 192) * 0.6 + memory_bw * 0.25, 1)
        elif category == "Storage":
            storage_score = _score(_num(bandwidth.get("sequential_read_mb_s") or specs.get("sequential_read_mb_s")), 7500)
            capacity = _score(_num(specs.get("capacity_gb")), 4096, curve=0.75)
            gaming = round(storage_score * 0.48 + capacity * 0.28, 1)
            productivity = round(storage_score * 0.55 + capacity * 0.35, 1)
            simulation = productivity
            rendering = productivity
            ai = round(storage_score * 0.5 + capacity * 0.35, 1)
        elif category == "Monitor":
            refresh = _score(_num(specs.get("refresh_hz")), 240)
            size = _score(_num(specs.get("size_in")), 32)
            gaming = round(refresh * 0.55 + size * 0.2, 1)
            productivity = round(size * 0.45 + _score(_num(raw.get("spec_resolution_pixels")), 8294400) * 0.35, 1)
            simulation = gaming * 0.75
            rendering = productivity
            ai = 25.0
        else:
            base = 40.0 if category in {"Keyboard", "Mouse", "Headset", "Fans", "Capture Card"} else 25.0
            gaming = productivity = simulation = rendering = ai = base

        cache = _score(_num(specs.get("cache_mb")), 96)
        return BenchmarkScores(
            gaming=max(0, min(100, gaming)),
            productivity=max(0, min(100, productivity)),
            ai_ml=max(0, min(100, ai)),
            rendering=max(0, min(100, rendering)),
            simulation=max(0, min(100, simulation)),
            rasterization=raster,
            ray_tracing=ray,
            vram_efficiency=vram,
            tensor_capability=tensor,
            single_core=single,
            multi_core=multi,
            cache_efficiency=cache,
            thermal_efficiency=thermal,
        )

    def _apply_telemetry(
        self,
        benchmark: BenchmarkScores,
        facts: dict[str, Any],
        telemetry_summary: TelemetrySummary | None,
    ) -> BenchmarkScores:
        if not telemetry_summary or telemetry_summary.sample_count == 0:
            return benchmark
        category = facts.get("category")
        confidence_weight = {"high": 1.0, "medium": 0.72, "low": 0.42}[telemetry_summary.confidence]
        sample_weight = min(0.34, 0.08 + telemetry_summary.sample_count * 0.028) * confidence_weight
        resolution_baseline = self._telemetry_fps_baseline(telemetry_summary.covered_resolutions)
        fps_score = _score(_num(telemetry_summary.average_fps), resolution_baseline)
        low_score = _score(_num(telemetry_summary.one_percent_low_fps), resolution_baseline * 0.72)
        instability = _num(telemetry_summary.frame_time_instability_score)
        pacing_score = max(0.0, 100.0 - instability)
        telemetry_gaming = round(fps_score * 0.48 + low_score * 0.32 + pacing_score * 0.2, 1)
        updates: dict[str, float] = {}
        if telemetry_summary.average_fps is not None and category in {"CPU", "GPU", "Monitor"}:
            updates["gaming"] = round(benchmark.gaming * (1 - sample_weight) + telemetry_gaming * sample_weight, 1)
        thermal_penalty = {"high": 18.0, "medium": 8.0, "low": -3.0, "unknown": 0.0}[
            telemetry_summary.thermal_throttling_risk
        ]
        thermal_score = max(0.0, min(100.0, benchmark.thermal_efficiency - thermal_penalty))
        if telemetry_summary.average_temp_c is not None and telemetry_summary.average_temp_c <= 72:
            thermal_score = min(100.0, thermal_score + 4)
        updates["thermal_efficiency"] = round(thermal_score, 1)
        if telemetry_summary.primary_limiter == "vram":
            updates["vram_efficiency"] = round(max(0.0, benchmark.vram_efficiency - 8 * sample_weight), 1)
        if telemetry_summary.primary_limiter == "driver":
            updates["gaming"] = round(max(0.0, updates.get("gaming", benchmark.gaming) - 5 * sample_weight), 1)
        if any("simulation" in item.lower() for item in telemetry_summary.covered_workloads):
            stability = max(0.0, 100 - instability)
            updates["simulation"] = round(benchmark.simulation * 0.86 + stability * 0.14, 1)
        return benchmark.model_copy(update={key: max(0, min(100, value)) for key, value in updates.items()})

    def _telemetry_fps_baseline(self, resolutions: list[str]) -> float:
        if "4K" in resolutions:
            return 105
        if "ultrawide" in resolutions:
            return 120
        if "1440p" in resolutions:
            return 150
        return 190

    def _workloads(self, facts: dict[str, Any], benchmark: BenchmarkScores) -> list[WorkloadSuitability]:
        category = facts.get("category")
        scores = {
            "gaming": benchmark.gaming,
            "workstation": benchmark.productivity,
            "simulation": benchmark.simulation,
            "rendering": benchmark.rendering,
            "ai": benchmark.ai_ml,
            "streaming": round(benchmark.gaming * 0.35 + benchmark.productivity * 0.35 + benchmark.ai_ml * 0.15, 1),
            "cad": round(benchmark.single_core * 0.38 + benchmark.rasterization * 0.28 + benchmark.productivity * 0.24, 1),
            "video_editing": round(benchmark.rendering * 0.42 + benchmark.productivity * 0.35 + benchmark.ai_ml * 0.12, 1),
        }
        workloads: list[WorkloadSuitability] = []
        for workload, score in scores.items():
            reasons = self._workload_reasons(category, workload, score, benchmark)
            workloads.append(
                WorkloadSuitability(
                    workload=workload,
                    score=max(0, min(100, score)),
                    label=_label(score),
                    reasons=reasons,
                )
            )
        return workloads

    def _workload_reasons(
        self,
        category: str,
        workload: str,
        score: float,
        benchmark: BenchmarkScores,
    ) -> list[str]:
        reasons = [f"{category} modeled as {_label(score)} for {workload.replace('_', ' ')}."]
        if workload == "gaming" and benchmark.cache_efficiency >= 70:
            reasons.append("Large cache profile improves frame-time consistency.")
        if workload == "ai" and benchmark.tensor_capability >= 65:
            reasons.append("Tensor/compute capability supports AI acceleration.")
        if workload in {"rendering", "video_editing"} and benchmark.rendering >= 70:
            reasons.append("Rendering score is supported by compute and memory capacity.")
        if benchmark.thermal_efficiency < 35:
            reasons.append("Thermal efficiency limits sustained workload behavior.")
        return reasons[:3]

    def _power_thermal(
        self,
        facts: dict[str, Any],
        benchmark: BenchmarkScores,
        telemetry_summary: TelemetrySummary | None = None,
    ) -> PowerThermalProfile:
        category = facts.get("category")
        power = facts.get("power", {})
        specs = facts.get("specs", {})
        tdp = _num(power.get("tdp_w") or power.get("board_power_w") or power.get("fan_power_w"), 0)
        peak = _num(power.get("peak_w"), tdp * 1.25 if tdp else 0)
        if telemetry_summary and telemetry_summary.peak_power_w:
            peak = max(peak, telemetry_summary.peak_power_w)
        if tdp >= 280 or peak >= 420:
            cooling = "high airflow case and premium cooling"
            risk = "high"
        elif tdp >= 140 or peak >= 220:
            cooling = "quality tower cooler or 240mm liquid cooling"
            risk = "medium"
        elif category == "CPU":
            cooling = "mainstream tower cooler"
            risk = "low"
        elif category == "GPU":
            cooling = "case airflow with unobstructed GPU intake"
            risk = "medium" if peak >= 180 else "low"
        else:
            cooling = "standard system airflow"
            risk = "low"
        recommended_psu = None
        if category == "GPU" and peak:
            recommended_psu = int(max(450, round((peak + 180) * 1.45 / 50) * 50))
        elif category == "CPU" and tdp:
            recommended_psu = int(max(450, round((tdp + 250) * 1.35 / 50) * 50))
        warnings = []
        if benchmark.thermal_efficiency < 35:
            warnings.append("Low modeled performance per watt can raise sustained-load temperatures.")
        if telemetry_summary and telemetry_summary.thermal_throttling_risk in {"medium", "high"}:
            warnings.append(
                f"Real-world telemetry indicates {telemetry_summary.thermal_throttling_risk} thermal throttling risk."
            )
        if _num(specs.get("cooling_capacity_w")) and tdp and _num(specs.get("cooling_capacity_w")) < tdp * 1.15:
            warnings.append("Cooling capacity has limited modeled headroom.")
        return PowerThermalProfile(
            tdp_w=round(tdp, 1) if tdp else None,
            peak_power_w=round(peak, 1) if peak else None,
            thermal_efficiency=benchmark.thermal_efficiency,
            expected_cooling_requirement=cooling,
            recommended_psu_w=recommended_psu,
            power_spike_risk=risk,
            warnings=warnings,
        )

    def _longevity(self, facts: dict[str, Any], benchmark: BenchmarkScores) -> LongevityProfile:
        category = facts.get("category")
        specs = facts.get("specs", {})
        bandwidth = facts.get("bandwidth", {})
        limiting: list[str] = []
        base = mean([benchmark.gaming, benchmark.productivity, benchmark.rendering])
        platform_bonus = 0.0
        if specs.get("socket") in {"AM5", "LGA1851"}:
            platform_bonus += 14
        elif specs.get("socket") == "LGA1700":
            limiting.append("Platform is closer to the end of its upgrade window.")
        if specs.get("memory_type") == "DDR5":
            platform_bonus += 8
        elif specs.get("memory_type") == "DDR4":
            limiting.append("DDR4 platform has less forward memory bandwidth headroom.")
        if _num(bandwidth.get("pcie_generation")) >= 5 or _num(bandwidth.get("pcie_generation_required")) >= 5:
            platform_bonus += 5
        if category == "GPU" and _num(specs.get("vram_gb")) < 12:
            limiting.append("VRAM capacity can limit future high-resolution textures and AI workloads.")
        future = max(0, min(100, base * 0.62 + platform_bonus + benchmark.thermal_efficiency * 0.16))
        years = round(2.0 + future / 18, 1)
        return LongevityProfile(
            upgrade_longevity=round(max(0, min(100, future + platform_bonus * 0.4)), 1),
            future_proof_score=round(future, 1),
            platform_lifespan_years=min(8.0, years),
            limiting_factors=limiting[:4],
        )

    def _compatibility(self, facts: dict[str, Any]) -> CompatibilityEnrichment:
        specs = facts.get("specs", {})
        bandwidth = facts.get("bandwidth", {})
        category = facts.get("category")
        bios: list[str] = []
        chipset: list[str] = []
        cooling: list[str] = []
        if category == "CPU" and specs.get("socket") == "AM5":
            bios.append("Verify motherboard BIOS supports this CPU generation before first boot.")
        if category == "CPU" and str(specs.get("model", facts.get("name", ""))).lower().find("14") >= 0:
            bios.append("Intel 14th-gen CPUs may require updated BIOS on older 600/700-series boards.")
        if category == "GPU" and _num(bandwidth.get("pcie_lanes_required")) >= 16:
            chipset.append("Full x16 slot wiring is recommended for maximum GPU bandwidth.")
        if category == "RAM" and _num(specs.get("speed_mt_s")) >= 6400:
            chipset.append("High memory clocks depend on CPU memory controller and motherboard trace quality.")
        thermal_capacity = _num(specs.get("cooling_capacity_w"))
        if category == "Cooler" and thermal_capacity:
            cooling.append(f"Recommended for CPUs up to about {int(thermal_capacity / 1.15)} W sustained draw.")
        stability = "unknown"
        if category == "RAM":
            speed = _num(specs.get("speed_mt_s"))
            stability = "high" if speed <= 6000 else "medium" if speed <= 7200 else "low"
        return CompatibilityEnrichment(
            bios_requirements=bios,
            chipset_limitations=chipset,
            pcie_generation_support=(
                f"PCIe Gen {int(_num(bandwidth.get('pcie_generation') or bandwidth.get('pcie_generation_required')))}"
                if _num(bandwidth.get("pcie_generation") or bandwidth.get("pcie_generation_required"))
                else None
            ),
            memory_overclock_stability=stability,
            cooling_recommendations=cooling,
        )

    def _market(self, facts: dict[str, Any], benchmark: BenchmarkScores) -> MarketIntelligence:
        price = _num(facts.get("price"), 0)
        perf = max(benchmark.gaming, benchmark.productivity, benchmark.rendering, benchmark.ai_ml)
        ratio = round(perf / price * 100, 4) if price > 0 else None
        vendor_count = _num(facts.get("vendor_count"), 0)
        popularity = round(max(0, min(100, vendor_count * 16 + len(facts.get("price_snapshots", [])) * 4)), 1)
        value = round(max(0, min(100, (ratio or 0) * 120 + popularity * 0.18)), 1)
        trend = self._price_trend(facts.get("price_snapshots", []))
        return MarketIntelligence(
            price_performance_ratio=ratio,
            market_popularity=popularity,
            value_score=value,
            price_trend=trend,
            best_value_badge=value >= 72 and trend in {"falling", "stable"},
        )

    def _price_trend(self, snapshots: list[dict[str, Any]]) -> str:
        accepted = [snapshot for snapshot in snapshots if snapshot.get("accepted", True)]
        if len(accepted) < 3:
            return "insufficient_history"
        prices = [_num(snapshot.get("price")) + _num(snapshot.get("shipping_cost")) for snapshot in accepted[-6:]]
        if len(prices) < 3 or prices[0] <= 0:
            return "insufficient_history"
        delta = (prices[-1] - prices[0]) / prices[0]
        if delta <= -0.05:
            return "falling"
        if delta >= 0.05:
            return "rising"
        return "stable"

    def _warnings(
        self,
        facts: dict[str, Any],
        power: PowerThermalProfile,
        compatibility: CompatibilityEnrichment,
        market: MarketIntelligence,
        telemetry_summary: TelemetrySummary | None = None,
    ) -> list[IntelligenceWarning]:
        warnings: list[IntelligenceWarning] = []
        if power.power_spike_risk == "high":
            warnings.append(
                IntelligenceWarning(
                    severity="warning",
                    message="High modeled transient power risk; pair with PSU headroom.",
                    evidence={"peak_power_w": power.peak_power_w, "recommended_psu_w": power.recommended_psu_w},
                )
            )
        if market.price_trend == "rising":
            warnings.append(
                IntelligenceWarning(
                    severity="info",
                    message="Recent accepted snapshots indicate rising price trend.",
                )
            )
        if compatibility.chipset_limitations:
            warnings.append(
                IntelligenceWarning(
                    severity="warning",
                    message="Compatibility enrichment found platform limitations.",
                    evidence={"limitations": compatibility.chipset_limitations},
                )
            )
        if facts.get("raw", {}).get("stale"):
            warnings.append(
                IntelligenceWarning(
                    severity="warning",
                    message="Market data is stale; previous valid snapshot is preserved.",
                )
            )
        if telemetry_summary:
            if telemetry_summary.frame_time_instability_score and telemetry_summary.frame_time_instability_score >= 45:
                warnings.append(
                    IntelligenceWarning(
                        severity="warning",
                        message="Telemetry shows frame-time instability under tested workloads.",
                        evidence={
                            "instability_score": telemetry_summary.frame_time_instability_score,
                            "sample_count": telemetry_summary.sample_count,
                        },
                    )
                )
            if telemetry_summary.thermal_throttling_risk == "high":
                warnings.append(
                    IntelligenceWarning(
                        severity="critical",
                        message="Telemetry indicates high thermal throttling risk; cooling headroom is required.",
                        evidence={
                            "average_temp_c": telemetry_summary.average_temp_c,
                            "hotspot_temp_c": telemetry_summary.hotspot_temp_c,
                        },
                    )
                )
            if telemetry_summary.primary_limiter not in {"none", "thermal"}:
                warnings.append(
                    IntelligenceWarning(
                        severity="info",
                        message=f"Observed telemetry limiter is {telemetry_summary.primary_limiter.upper()}.",
                        evidence=telemetry_summary.bottleneck.model_dump(),
                    )
                )
        return warnings

    def _summary(
        self,
        facts: dict[str, Any],
        benchmark: BenchmarkScores,
        workloads: list[WorkloadSuitability],
        power: PowerThermalProfile,
        longevity: LongevityProfile,
        market: MarketIntelligence,
        telemetry_summary: TelemetrySummary | None = None,
    ) -> list[str]:
        best_workloads = sorted(workloads, key=lambda item: item.score, reverse=True)[:2]
        name = str(facts.get("name") or facts["id"])
        lines = [
            f"{name} is strongest for {best_workloads[0].workload.replace('_', ' ')} ({best_workloads[0].score:.1f}) and {best_workloads[1].workload.replace('_', ' ')} ({best_workloads[1].score:.1f}).",
            f"Thermal model rates efficiency at {power.thermal_efficiency:.1f}/100 with {power.power_spike_risk} spike risk.",
            f"Future-proof score is {longevity.future_proof_score:.1f}/100 across platform, bandwidth, and capacity signals.",
        ]
        if market.price_performance_ratio is not None:
            lines.append(f"Market value score is {market.value_score:.1f}/100 from accepted price/performance data.")
        if benchmark.cache_efficiency >= 70:
            lines.append("Large cache profile supports lower frame-time variance in gaming workloads.")
        if benchmark.tensor_capability >= 70:
            lines.append("Tensor/compute profile improves AI and accelerated rendering suitability.")
        if telemetry_summary:
            if telemetry_summary.average_fps and telemetry_summary.one_percent_low_fps:
                lines.insert(
                    1,
                    f"Telemetry evidence reports {telemetry_summary.average_fps:.1f} FPS average and {telemetry_summary.one_percent_low_fps:.1f} FPS 1% lows across {telemetry_summary.sample_count} sample(s).",
                )
            elif telemetry_summary.notes:
                lines.insert(1, telemetry_summary.notes[0])
        return lines[:5]


class HardwareEnrichmentService:
    def __init__(
        self,
        repository: Neo4jPricingRepository,
        telemetry_repository: Neo4jTelemetryRepository | None = None,
    ) -> None:
        self.repository = repository
        self.telemetry_repository = telemetry_repository or Neo4jTelemetryRepository(repository.driver)
        self.engine = HardwareEnrichmentEngine()

    def enrich(self, request: EnrichmentRequest) -> EnrichmentResponse:
        product_ids = request.product_ids or self.repository.products_for_enrichment(
            category=request.category,
            limit=request.limit,
        )
        intelligence: list[HardwareIntelligence] = []
        skipped = 0
        for product_id in product_ids[: request.limit]:
            facts = self.repository.product_facts(product_id)
            if not facts:
                skipped += 1
                continue
            telemetry_summary = self._telemetry_summary(product_id)
            result = self.engine.enrich(facts, telemetry_summary)
            if request.persist:
                self.repository.upsert_intelligence(result)
            intelligence.append(result)
        return EnrichmentResponse(
            enriched_count=len(intelligence),
            skipped_count=skipped,
            intelligence=intelligence,
        )

    def get_or_create(self, product_id: str) -> HardwareIntelligence | None:
        existing = self.repository.latest_intelligence(product_id)
        telemetry_summary = self._telemetry_summary(product_id)
        if existing and (
            not telemetry_summary
            or (existing.telemetry and existing.telemetry.updated_at >= telemetry_summary.updated_at)
        ):
            return existing
        response = self.enrich(EnrichmentRequest(product_ids=[product_id], limit=1, persist=True))
        return response.intelligence[0] if response.intelligence else None

    def _telemetry_summary(self, product_id: str) -> TelemetrySummary | None:
        try:
            snapshots = self.telemetry_repository.snapshots_for_product(product_id, limit=300)
        except Exception:  # noqa: BLE001 - enrichment must degrade if telemetry graph is unavailable.
            return None
        summary = TelemetryAnalysisEngine().summarize(product_id, snapshots)
        return summary if summary.sample_count else None
