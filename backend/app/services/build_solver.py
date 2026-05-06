from __future__ import annotations

from dataclasses import dataclass
from math import inf

from app.graph.repository import Neo4jComponentRepository
from app.models.api import (
    BuildGenerateRequest,
    BuildGenerateResponse,
    CompatibilityRequest,
    GeneratedBuild,
    GeneratedPart,
)
from app.models.domain import BuildPreferences, ComponentKind, ComponentNode, SelectedComponents
from app.services.compatibility import CompatibilityEngine
from app.services.performance import PerformanceEngine


SOLVER_ORDER = [
    ComponentKind.CPU,
    ComponentKind.MOTHERBOARD,
    ComponentKind.RAM,
    ComponentKind.GPU,
    ComponentKind.STORAGE,
    ComponentKind.COOLER,
    ComponentKind.CASE,
    ComponentKind.PSU,
]


@dataclass
class CandidateBuild:
    selection: SelectedComponents
    parts: dict[ComponentKind, ComponentNode]
    total_cost: float
    score: float
    performance_score: float
    value_score: float
    balanced_score: float
    compatibility_failures: int


class BuildSolver:
    def __init__(self, repository: Neo4jComponentRepository) -> None:
        self.repository = repository
        self.compatibility = CompatibilityEngine(repository)
        self.performance = PerformanceEngine()
        self.explored_configurations = 0
        self.pruned_configurations = 0
        self._option_cache: dict[tuple[str, str], set[str]] = {}
        self._compatibility_cache = {}

    def generate(self, request: BuildGenerateRequest) -> BuildGenerateResponse:
        preferences = self._normalized_preferences(request)
        catalog = self._load_catalog(request.max_candidates_per_type, preferences)
        valid: list[CandidateBuild] = []
        closest: list[CandidateBuild] = []
        self.explored_configurations = 0
        self.pruned_configurations = 0
        self._option_cache = {}
        self._compatibility_cache = {}

        self._search(
            order=SOLVER_ORDER,
            depth=0,
            partial={},
            catalog=catalog,
            preferences=preferences,
            budget=request.budget_usd,
            valid=valid,
            closest=closest,
        )

        if valid:
            builds = self._select_multi_solution(valid, preferences)
            if not builds:
                return BuildGenerateResponse(
                    builds=[],
                    compatibility_status="no_solution",
                    explored_configurations=self.explored_configurations,
                    pruned_configurations=self.pruned_configurations,
                    fallback_explanation=(
                        "Local pruning found candidates, but the final graph engine rejected each sampled build."
                    ),
                )
            return BuildGenerateResponse(
                builds=builds,
                compatibility_status="valid",
                explored_configurations=self.explored_configurations,
                pruned_configurations=self.pruned_configurations,
            )

        closest_valid = self._first_graph_valid(
            sorted(closest, key=lambda item: (item.compatibility_failures, item.total_cost))
        )
        if closest_valid:
            return BuildGenerateResponse(
                builds=[self._to_generated_build("closest_valid", closest_valid, preferences)],
                compatibility_status="closest_valid",
                explored_configurations=self.explored_configurations,
                pruned_configurations=self.pruned_configurations,
                fallback_explanation=(
                    "No configuration satisfied every constraint inside budget. "
                    "The returned configuration is the nearest graph-evaluated candidate by failure count and cost."
                ),
            )

        return BuildGenerateResponse(
            builds=[],
            compatibility_status="no_solution",
            explored_configurations=self.explored_configurations,
            pruned_configurations=self.pruned_configurations,
            fallback_explanation="Neo4j did not return enough component candidates to build a complete configuration.",
        )

    def _normalized_preferences(self, request: BuildGenerateRequest) -> BuildPreferences:
        data = request.preferences.model_dump()
        data["budget_usd"] = request.budget_usd
        data["purpose"] = request.purpose
        data["resolution"] = request.resolution
        return BuildPreferences(**data)

    def _load_catalog(
        self,
        limit: int,
        preferences: BuildPreferences,
    ) -> dict[ComponentKind, list[ComponentNode]]:
        catalog = {kind: self.repository.components_by_kind(kind, limit=limit) for kind in SOLVER_ORDER}
        for kind, nodes in catalog.items():
            catalog[kind] = sorted(
                nodes,
                key=lambda node: self._candidate_priority(kind, node, preferences),
                reverse=True,
            )
        return catalog

    def _candidate_priority(
        self,
        kind: ComponentKind,
        node: ComponentNode,
        preferences: BuildPreferences,
    ) -> float:
        price = float(node.price_usd or 0)
        brand_bonus = 0.08 if node.brand and node.brand in preferences.brand_bias else 0
        if kind == ComponentKind.CPU:
            raw = (node.number("specs", "single_thread_score", 0) or 0) * 0.42
            raw += (node.number("specs", "multi_thread_score", 0) or 0) * 0.015
        elif kind == ComponentKind.GPU:
            raw = (node.number("specs", "raster_score", 0) or 0) * 0.06
            raw += (node.number("specs", "compute_score", 0) or 0) * 2.5
        elif kind == ComponentKind.RAM:
            raw = (node.number("bandwidth", "memory_gbps", 0) or 0) * 20
        elif kind == ComponentKind.PSU:
            raw = node.number("specs", "continuous_wattage", 0) or 0
        elif kind == ComponentKind.CASE and preferences.size:
            raw = 1000 if preferences.size in str(node.specs.get("supported_form_factors", "")) else -1000
        else:
            raw = 500
        intelligence_bonus = (node.number("raw", "intelligence_value_score", 0) or 0) / 1000
        return raw / max(price, 50) + brand_bonus + intelligence_bonus

    def _search(
        self,
        *,
        order: list[ComponentKind],
        depth: int,
        partial: dict[ComponentKind, ComponentNode],
        catalog: dict[ComponentKind, list[ComponentNode]],
        preferences: BuildPreferences,
        budget: float,
        valid: list[CandidateBuild],
        closest: list[CandidateBuild],
    ) -> None:
        if depth == len(order):
            self.explored_configurations += 1
            candidate = self._evaluate(partial, preferences, budget)
            if candidate.compatibility_failures == 0 and candidate.total_cost <= budget:
                valid.append(candidate)
            else:
                closest.append(candidate)
            return

        kind = order[depth]
        for node in self._filtered_candidates(kind, partial, catalog, preferences):
            next_partial = {**partial, kind: node}
            if not self._partial_is_possible(next_partial, preferences):
                self.pruned_configurations += 1
                continue
            partial_cost = self._cost(next_partial)
            if partial_cost > budget * 1.45:
                self.pruned_configurations += 1
                continue
            self._search(
                order=order,
                depth=depth + 1,
                partial=next_partial,
                catalog=catalog,
                preferences=preferences,
                budget=budget,
                valid=valid,
                closest=closest,
            )

    def _filtered_candidates(
        self,
        kind: ComponentKind,
        partial: dict[ComponentKind, ComponentNode],
        catalog: dict[ComponentKind, list[ComponentNode]],
        preferences: BuildPreferences,
    ) -> list[ComponentNode]:
        candidates = catalog[kind]
        if kind == ComponentKind.MOTHERBOARD and ComponentKind.CPU in partial:
            cpu_id = partial[ComponentKind.CPU].id
            cache_key = ("motherboards_for_cpu", f"{cpu_id}:{preferences.size or '*'}")
            if cache_key in self._option_cache:
                allowed = self._option_cache[cache_key]
                return [candidate for candidate in candidates if candidate.id in allowed]
            options = self.repository.component_options(
                ComponentKind.MOTHERBOARD,
                SelectedComponents(cpu_id=cpu_id),
                limit=120,
                form_factor=preferences.size,
            )
            allowed = {option.id for option in options}
            self._option_cache[cache_key] = allowed
            return [candidate for candidate in candidates if candidate.id in allowed]
        if kind == ComponentKind.RAM and ComponentKind.MOTHERBOARD in partial:
            board_id = partial[ComponentKind.MOTHERBOARD].id
            cache_key = ("ram_for_board", board_id)
            if cache_key in self._option_cache:
                allowed = self._option_cache[cache_key]
                return [candidate for candidate in candidates if candidate.id in allowed]
            options = self.repository.component_options(
                ComponentKind.RAM,
                SelectedComponents(motherboard_id=board_id),
                limit=120,
                qvl_required=True,
            )
            allowed = {option.id for option in options}
            self._option_cache[cache_key] = allowed
            return [candidate for candidate in candidates if candidate.id in allowed]
        if kind == ComponentKind.CASE:
            board = partial.get(ComponentKind.MOTHERBOARD)
            gpu = partial.get(ComponentKind.GPU)
            cache_key = ("cases_for_board_gpu", f"{board.id if board else '*'}:{gpu.id if gpu else '*'}:{preferences.size or '*'}")
            if cache_key in self._option_cache:
                allowed = self._option_cache[cache_key]
                return [candidate for candidate in candidates if candidate.id in allowed]
            selection = SelectedComponents(
                motherboard_id=board.id if board else None,
                gpu_id=gpu.id if gpu else None,
            )
            options = self.repository.component_options(ComponentKind.CASE, selection, limit=120)
            allowed = {option.id for option in options}
            candidates = [candidate for candidate in candidates if candidate.id in allowed]
            if preferences.size:
                candidates = [
                    candidate
                    for candidate in candidates
                    if preferences.size in str(candidate.specs.get("supported_form_factors", ""))
                ]
            self._option_cache[cache_key] = {candidate.id for candidate in candidates}
            return candidates
        return candidates

    def _partial_is_possible(
        self,
        partial: dict[ComponentKind, ComponentNode],
        preferences: BuildPreferences,
    ) -> bool:
        del preferences
        cpu = partial.get(ComponentKind.CPU)
        board = partial.get(ComponentKind.MOTHERBOARD)
        ram = partial.get(ComponentKind.RAM)
        gpu = partial.get(ComponentKind.GPU)
        storage = partial.get(ComponentKind.STORAGE)
        cooler = partial.get(ComponentKind.COOLER)
        case = partial.get(ComponentKind.CASE)
        psu = partial.get(ComponentKind.PSU)

        if cpu and board and cpu.specs.get("socket") != board.specs.get("socket"):
            return False
        if ram and board and ram.specs.get("memory_type") != board.specs.get("memory_type"):
            return False
        if board and case and str(board.specs.get("form_factor")) not in self._split_spec(case, "supported_form_factors"):
            return False
        if gpu and case:
            gpu_length = gpu.number("dimensions", "length_mm")
            clearance = case.number("dimensions", "gpu_clearance_mm")
            if gpu_length is not None and clearance is not None and gpu_length > clearance:
                return False
        if cooler and case:
            cooler_height = cooler.number("dimensions", "height_mm")
            clearance = case.number("dimensions", "cooler_clearance_mm")
            if cooler_height is not None and clearance is not None and cooler_height > clearance:
                return False
        if cooler and cpu:
            cooling_capacity = cooler.number("specs", "cooling_capacity_w")
            cpu_tdp = cpu.number("power", "tdp_w")
            if cooling_capacity is not None and cpu_tdp is not None and cooling_capacity < cpu_tdp * 1.15:
                return False
        if board and case and not self._usb_possible(board, case):
            return False
        if cpu and board and not self._pcie_possible(cpu, board, gpu, storage):
            return False
        if psu and not self._psu_possible(partial, psu):
            return False
        return True

    def _evaluate(
        self,
        parts: dict[ComponentKind, ComponentNode],
        preferences: BuildPreferences,
        budget: float,
    ) -> CandidateBuild:
        selection = self._selection(parts)
        performance = self.performance.calculate(
            cpu=parts[ComponentKind.CPU],
            gpu=parts[ComponentKind.GPU],
            ram=parts.get(ComponentKind.RAM),
            preferences=preferences,
            display_refresh_hz=144,
        )
        total_cost = self._cost(parts)
        perf_score = performance.expected_fps * 3.2 + performance.one_percent_low_fps
        over_budget = max(0.0, total_cost - budget)
        under_budget_fraction = max(0.0, budget - total_cost) / max(budget, 1)
        bottleneck_penalty = (
            performance.bottleneck.cpu_percent
            + performance.bottleneck.gpu_percent
            + performance.bottleneck.memory_percent * 0.6
        ) * 2.8
        cost_penalty = (over_budget / max(budget, 1)) * 900 + (total_cost / max(budget, 1)) * 24
        score = perf_score - cost_penalty - bottleneck_penalty
        value_score = perf_score / max(total_cost, 1) * 1000
        balanced_score = score + under_budget_fraction * 50 - bottleneck_penalty * 1.5
        return CandidateBuild(
            selection=selection,
            parts=parts,
            total_cost=total_cost,
            score=score,
            performance_score=perf_score - cost_penalty,
            value_score=value_score,
            balanced_score=balanced_score,
            compatibility_failures=0,
        )

    def _select_multi_solution(
        self,
        valid: list[CandidateBuild],
        preferences: BuildPreferences,
    ) -> list[GeneratedBuild]:
        by_performance = sorted(valid, key=lambda item: item.performance_score, reverse=True)
        by_value = sorted(valid, key=lambda item: item.value_score, reverse=True)
        by_balanced = sorted(valid, key=lambda item: item.balanced_score, reverse=True)

        selected: list[tuple[str, CandidateBuild]] = []
        used_signatures: set[tuple[str | None, ...]] = set()
        for label, pool in (
            ("best_performance", by_performance),
            ("best_value", by_value),
            ("balanced", by_balanced),
        ):
            chosen = self._first_unique_graph_valid(pool, used_signatures)
            if not chosen:
                continue
            signature = self._signature(chosen.selection)
            used_signatures.add(signature)
            selected.append((label, chosen))
        return [self._to_generated_build(label, candidate, preferences) for label, candidate in selected]

    def _first_unique_graph_valid(
        self,
        pool: list[CandidateBuild],
        used: set[tuple[str | None, ...]],
    ) -> CandidateBuild | None:
        for candidate in pool:
            if self._signature(candidate.selection) not in used and self._graph_valid(candidate.selection):
                return candidate
        return None

    def _first_graph_valid(self, pool: list[CandidateBuild]) -> CandidateBuild | None:
        for candidate in pool:
            if self._graph_valid(candidate.selection):
                return candidate
        return None

    def _graph_valid(self, selection: SelectedComponents) -> bool:
        signature = self._signature(selection)
        if signature not in self._compatibility_cache:
            self._compatibility_cache[signature] = self.compatibility.check(
                CompatibilityRequest(selection=selection, qvl_required=True)
            )
        return bool(self._compatibility_cache[signature].valid)

    def _to_generated_build(
        self,
        label: str,
        candidate: CandidateBuild,
        preferences: BuildPreferences,
    ) -> GeneratedBuild:
        signature = self._signature(candidate.selection)
        compatibility = self._compatibility_cache.get(signature)
        if compatibility is None:
            compatibility = self.compatibility.check(
                CompatibilityRequest(selection=candidate.selection, preferences=preferences, qvl_required=True)
            )
            self._compatibility_cache[signature] = compatibility
        performance = self.performance.calculate(
            cpu=candidate.parts[ComponentKind.CPU],
            gpu=candidate.parts[ComponentKind.GPU],
            ram=candidate.parts.get(ComponentKind.RAM),
            preferences=preferences,
            display_refresh_hz=144,
        )
        return GeneratedBuild(
            label=label,
            parts=[
                GeneratedPart(
                    kind=kind.value,
                    id=node.id,
                    name=node.name,
                    brand=node.brand,
                    price_usd=float(node.price_usd or 0),
                    price_source=node.raw.get("current_price_source"),
                    price_vendor=node.raw.get("current_best_vendor"),
                    price_freshness_score=node.raw.get("current_price_freshness_score"),
                    price_trust_score=node.raw.get("current_price_trust_score"),
                    price_stale=bool(node.raw.get("stale", False)),
                    reasoning=self._part_reasoning(kind, node, candidate.parts, preferences),
                )
                for kind, node in candidate.parts.items()
            ],
            selection=candidate.selection,
            total_cost_usd=round(candidate.total_cost, 2),
            score=round(candidate.score, 3),
            performance=performance,
            compatibility=compatibility,
            bottleneck_breakdown=performance.bottleneck,
            reasoning_summary=self._build_reasoning(candidate, performance, preferences),
        )

    def _part_reasoning(
        self,
        kind: ComponentKind,
        node: ComponentNode,
        parts: dict[ComponentKind, ComponentNode],
        preferences: BuildPreferences,
    ) -> str:
        intelligence_score = node.raw.get("intelligence_value_score")
        intelligence_note = (
            f" Intelligence value score {float(intelligence_score):.1f}/100 reinforced the choice."
            if intelligence_score is not None
            else ""
        )
        if kind == ComponentKind.CPU:
            return f"Selected for {preferences.purpose} CPU throughput on {node.specs.get('socket')}.{intelligence_note}"
        if kind == ComponentKind.GPU:
            return (
                f"Selected for {preferences.resolution} graphics throughput and "
                f"{node.specs.get('vram_gb')} GB VRAM.{intelligence_note}"
            )
        if kind == ComponentKind.MOTHERBOARD:
            return f"Matches CPU socket and provides {node.specs.get('form_factor')} expansion topology.{intelligence_note}"
        if kind == ComponentKind.RAM:
            return f"QVL-filtered kit matching board memory type at {node.specs.get('speed_mt_s')} MT/s.{intelligence_note}"
        if kind == ComponentKind.STORAGE:
            return f"NVMe storage selected within the PCIe lane budget."
        if kind == ComponentKind.COOLER:
            cpu = parts[ComponentKind.CPU]
            return f"Thermal capacity covers {cpu.name}'s modeled TDP headroom."
        if kind == ComponentKind.CASE:
            return "Case clears motherboard form factor, GPU length, cooler height, and USB topology."
        if kind == ComponentKind.PSU:
            return "Continuous wattage exceeds modeled system draw with safety headroom."
        return "Selected by graph-backed compatibility constraints."

    def _build_reasoning(
        self,
        candidate: CandidateBuild,
        performance,
        preferences: BuildPreferences,
    ) -> list[str]:
        budget = preferences.budget_usd or inf
        budget_delta = budget - candidate.total_cost
        return [
            f"Total cost is ${candidate.total_cost:.2f}, {'under' if budget_delta >= 0 else 'over'} budget by ${abs(budget_delta):.2f}.",
            f"Estimated {performance.expected_fps:.1f} FPS at {preferences.resolution} for {preferences.purpose}.",
            f"CPU/GPU bottleneck balance is {performance.bottleneck.cpu_percent:.1f}% CPU and {performance.bottleneck.gpu_percent:.1f}% GPU.",
            "All returned constraints are validated by the Neo4j-backed compatibility engine.",
        ]

    def _selection(self, parts: dict[ComponentKind, ComponentNode]) -> SelectedComponents:
        return SelectedComponents(
            cpu_id=parts.get(ComponentKind.CPU).id if parts.get(ComponentKind.CPU) else None,
            gpu_id=parts.get(ComponentKind.GPU).id if parts.get(ComponentKind.GPU) else None,
            motherboard_id=parts.get(ComponentKind.MOTHERBOARD).id if parts.get(ComponentKind.MOTHERBOARD) else None,
            ram_id=parts.get(ComponentKind.RAM).id if parts.get(ComponentKind.RAM) else None,
            case_id=parts.get(ComponentKind.CASE).id if parts.get(ComponentKind.CASE) else None,
            cooler_id=parts.get(ComponentKind.COOLER).id if parts.get(ComponentKind.COOLER) else None,
            storage_id=parts.get(ComponentKind.STORAGE).id if parts.get(ComponentKind.STORAGE) else None,
            psu_id=parts.get(ComponentKind.PSU).id if parts.get(ComponentKind.PSU) else None,
        )

    def _signature(self, selection: SelectedComponents) -> tuple[str | None, ...]:
        return (
            selection.cpu_id,
            selection.gpu_id,
            selection.motherboard_id,
            selection.ram_id,
            selection.case_id,
            selection.cooler_id,
            selection.storage_id,
            selection.psu_id,
        )

    def _cost(self, parts: dict[ComponentKind, ComponentNode]) -> float:
        return sum(float(node.price_usd or 0) for node in parts.values())

    def _split_spec(self, node: ComponentNode, key: str) -> list[str]:
        raw = node.specs.get(key, "")
        if isinstance(raw, list):
            return [str(item) for item in raw]
        return [value.strip() for value in str(raw).replace(",", "|").split("|") if value.strip()]

    def _usb_possible(self, board: ComponentNode, case: ComponentNode) -> bool:
        required = {
            "usb_20_headers": case.number("bandwidth", "front_usb_20_ports", 0) or 0,
            "usb_32_gen1_headers": case.number("bandwidth", "front_usb_32_gen1_ports", 0) or 0,
            "usb_32_gen2x2_headers": case.number("bandwidth", "front_usb_32_gen2x2_ports", 0) or 0,
        }
        available = {key: board.number("bandwidth", key, 0) or 0 for key in required}
        if any(available[key] < value for key, value in required.items()):
            return False
        controller = board.number("bandwidth", "usb_controller_gbps")
        if controller is None:
            return True
        requested = (
            required["usb_20_headers"] * 0.48
            + required["usb_32_gen1_headers"] * 5
            + required["usb_32_gen2x2_headers"] * 20
        )
        return requested <= controller

    def _pcie_possible(
        self,
        cpu: ComponentNode,
        board: ComponentNode,
        gpu: ComponentNode | None,
        storage: ComponentNode | None,
    ) -> bool:
        cpu_lanes = cpu.number("bandwidth", "pcie_lanes")
        chipset_lanes = board.number("bandwidth", "chipset_pcie_lanes", 0)
        if cpu_lanes is None or chipset_lanes is None:
            return True
        required = sum(
            component.number("bandwidth", "pcie_lanes_required", 0) or 0
            for component in (gpu, storage)
            if component
        )
        return required <= cpu_lanes + chipset_lanes

    def _psu_possible(
        self,
        partial: dict[ComponentKind, ComponentNode],
        psu: ComponentNode,
    ) -> bool:
        wattage = psu.number("specs", "continuous_wattage") or psu.number("power", "12v_w")
        if wattage is None:
            return True
        total_draw = 0.0
        for component in partial.values():
            total_draw += (
                component.number("power", "board_power_w")
                or component.number("power", "tdp_w")
                or component.number("power", "peak_w")
                or component.number("power", "fan_power_w")
                or 0.0
            )
        return wattage >= (total_draw + 60.0) * 1.35
