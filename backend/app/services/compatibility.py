from __future__ import annotations

from collections.abc import Iterable
from math import ceil

from app.graph.repository import Neo4jComponentRepository
from app.models.api import CompatibilityRequest, CompatibilityResponse, ConstraintCheck
from app.models.domain import ComponentKind, ComponentNode
from app.services.geometry import detect_collisions


class CompatibilityEngine:
    def __init__(self, repository: Neo4jComponentRepository) -> None:
        self.repository = repository

    def check(self, request: CompatibilityRequest) -> CompatibilityResponse:
        selection = request.selection
        component_ids = selection.ids()
        components = self.repository.components_by_ids(component_ids)
        checks: list[ConstraintCheck] = []

        missing_ids = [component_id for component_id in component_ids if component_id not in components]
        for component_id in missing_ids:
            checks.append(
                ConstraintCheck(
                    id=f"missing:{component_id}",
                    label="Selected component exists in graph",
                    status="fail",
                    severity="critical",
                    details=f"{component_id} was selected but does not exist in Neo4j.",
                )
            )

        cpu = components.get(selection.cpu_id or "")
        gpu = components.get(selection.gpu_id or "")
        board = components.get(selection.motherboard_id or "")
        ram = components.get(selection.ram_id or "")
        case = components.get(selection.case_id or "")
        cooler = components.get(selection.cooler_id or "")
        storage = components.get(selection.storage_id or "")
        psu = components.get(selection.psu_id or "")

        self._socket_check(checks, cpu, board)
        self._ram_check(checks, ram, board, request.qvl_required)
        self._case_fit_checks(checks, gpu, board, case, cooler)
        self._cooler_check(checks, cooler, cpu, case)
        total_draw, required_psu = self._power_check(checks, components.values(), psu)
        self._pcie_lane_check(checks, cpu, board, gpu, storage)
        self._usb_topology_check(checks, board, case)
        self._physical_collision_check(checks, list(components.values()), component_ids)

        selected_count = len(component_ids) - len(missing_ids)
        has_failure = any(check.status == "fail" for check in checks)
        complete = selected_count == 8 and not missing_ids
        state = "invalid_configuration" if has_failure else "valid_configuration" if complete else "partial"

        if not checks:
            checks.append(
                ConstraintCheck(
                    id="selection:empty",
                    label="Selection has graph-backed components",
                    status="unknown",
                    severity="info",
                    details="No components selected yet. Add a CPU to start graph-constrained validation.",
                )
            )

        return CompatibilityResponse(
            valid=not has_failure,
            state=state,
            checks=checks,
            total_power_draw_w=total_draw,
            required_psu_w=required_psu,
            selected_component_count=selected_count,
            missing_component_ids=missing_ids,
        )

    def _socket_check(
        self,
        checks: list[ConstraintCheck],
        cpu: ComponentNode | None,
        board: ComponentNode | None,
    ) -> None:
        if not cpu or not board:
            return
        result = self.repository.has_cpu_motherboard_socket_match(cpu.id, board.id)
        checks.append(
            ConstraintCheck(
                id="cpu:motherboard:socket",
                label="CPU socket matches motherboard socket",
                status="pass" if result.get("compatible") else "fail",
                severity="critical",
                details=(
                    f"{cpu.name} and {board.name} share socket {result.get('socket')}."
                    if result.get("compatible")
                    else f"{cpu.name} does not match the socket exposed by {board.name}."
                ),
                evidence=result,
            )
        )

    def _ram_check(
        self,
        checks: list[ConstraintCheck],
        ram: ComponentNode | None,
        board: ComponentNode | None,
        qvl_required: bool,
    ) -> None:
        if not ram or not board:
            return
        result = self.repository.ram_board_qvl(ram.id, board.id)
        memory_ok = bool(result.get("memory_type_supported"))
        qvl_ok = bool(result.get("qvl_validated"))
        checks.append(
            ConstraintCheck(
                id="ram:motherboard:memory_type",
                label="RAM memory type is supported",
                status="pass" if memory_ok else "fail",
                severity="critical",
                details=(
                    f"{ram.name} uses {result.get('memory_type')} supported by {board.name}."
                    if memory_ok
                    else f"{ram.name} memory type is not supported by {board.name}."
                ),
                evidence=result,
            )
        )
        checks.append(
            ConstraintCheck(
                id="ram:motherboard:qvl",
                label="RAM kit is QVL validated",
                status="pass" if qvl_ok else "fail" if qvl_required else "warning",
                severity="critical" if qvl_required else "warning",
                details=(
                    f"{ram.name} is QVL validated on {board.name}."
                    if qvl_ok
                    else f"{ram.name} has no QVL validation edge to {board.name}."
                ),
                evidence=result,
            )
        )

    def _case_fit_checks(
        self,
        checks: list[ConstraintCheck],
        gpu: ComponentNode | None,
        board: ComponentNode | None,
        case: ComponentNode | None,
        cooler: ComponentNode | None,
    ) -> None:
        if board and case:
            supported_raw = case.specs.get("supported_form_factors", "")
            supported_values = (
                [str(value) for value in supported_raw]
                if isinstance(supported_raw, list)
                else [value.strip() for value in str(supported_raw).replace(",", "|").split("|") if value.strip()]
            )
            form_factor = str(board.specs.get("form_factor", ""))
            if supported_values and form_factor:
                fits = form_factor in supported_values
                checks.append(
                    ConstraintCheck(
                        id="motherboard:case:form_factor",
                        label="Motherboard form factor fits case",
                        status="pass" if fits else "fail",
                        severity="critical",
                        details=(
                            f"{case.name} supports {form_factor} motherboards."
                            if fits
                            else f"{case.name} does not support {form_factor} motherboards."
                        ),
                        evidence={"case_supported_form_factors": supported_values, "board_form_factor": form_factor},
                    )
                )
            else:
                self._unknown(checks, "motherboard:case:form_factor", "Motherboard form factor fit")

        if gpu and case:
            gpu_length = gpu.number("dimensions", "length_mm")
            clearance = case.number("dimensions", "gpu_clearance_mm")
            if gpu_length is None or clearance is None:
                self._unknown(checks, "gpu:case:length", "GPU length clearance")
            else:
                fits = gpu_length <= clearance
                checks.append(
                    ConstraintCheck(
                        id="gpu:case:length",
                        label="GPU length fits case clearance",
                        status="pass" if fits else "fail",
                        severity="critical",
                        details=(
                            f"{gpu.name} is {gpu_length:.0f} mm within {case.name}'s {clearance:.0f} mm clearance."
                            if fits
                            else f"{gpu.name} is {gpu_length:.0f} mm and exceeds {case.name}'s {clearance:.0f} mm clearance."
                        ),
                        evidence={"gpu_length_mm": gpu_length, "case_clearance_mm": clearance},
                    )
                )

        if cooler and case:
            cooler_height = cooler.number("dimensions", "height_mm")
            clearance = case.number("dimensions", "cooler_clearance_mm")
            if cooler_height is None or clearance is None:
                self._unknown(checks, "cooler:case:height", "Cooler height clearance")
            else:
                fits = cooler_height <= clearance
                checks.append(
                    ConstraintCheck(
                        id="cooler:case:height",
                        label="Cooler height fits case clearance",
                        status="pass" if fits else "fail",
                        severity="critical",
                        details=(
                            f"{cooler.name} height is within case clearance."
                            if fits
                            else f"{cooler.name} exceeds case cooler clearance."
                        ),
                        evidence={"cooler_height_mm": cooler_height, "case_clearance_mm": clearance},
                    )
                )

    def _cooler_check(
        self,
        checks: list[ConstraintCheck],
        cooler: ComponentNode | None,
        cpu: ComponentNode | None,
        case: ComponentNode | None,
    ) -> None:
        del case
        if not cooler or not cpu:
            return
        socket = self.repository.cooler_socket_support(cooler.id, cpu.id)
        checks.append(
            ConstraintCheck(
                id="cooler:cpu:socket",
                label="Cooler supports CPU socket",
                status="pass" if socket.get("supported") else "fail",
                severity="critical",
                details=(
                    f"{cooler.name} supports CPU socket {socket.get('socket')}."
                    if socket.get("supported")
                    else f"{cooler.name} does not advertise support for {cpu.name}'s socket."
                ),
                evidence=socket,
            )
        )
        cooling_capacity = cooler.number("specs", "cooling_capacity_w")
        cpu_tdp = cpu.number("power", "tdp_w")
        if cooling_capacity is None or cpu_tdp is None:
            self._unknown(checks, "cooler:cpu:thermal", "Cooler thermal capacity")
            return
        thermal_ok = cooling_capacity >= cpu_tdp * 1.15
        checks.append(
            ConstraintCheck(
                id="cooler:cpu:thermal",
                label="Cooler thermal headroom",
                status="pass" if thermal_ok else "fail",
                severity="critical",
                details=(
                    f"{cooler.name} has at least 15% thermal headroom over CPU TDP."
                    if thermal_ok
                    else f"{cooler.name} cooling capacity is below required CPU thermal headroom."
                ),
                evidence={"cooling_capacity_w": cooling_capacity, "cpu_tdp_w": cpu_tdp},
            )
        )

    def _power_check(
        self,
        checks: list[ConstraintCheck],
        components: Iterable[ComponentNode],
        psu: ComponentNode | None,
    ) -> tuple[float, float]:
        total_draw = 0.0
        for component in components:
            draw = (
                component.number("power", "board_power_w")
                or component.number("power", "tdp_w")
                or component.number("power", "peak_w")
                or component.number("power", "fan_power_w")
                or 0.0
            )
            total_draw += draw
        required_psu = float(ceil((total_draw + 60.0) * 1.35))
        if not psu:
            return total_draw, required_psu
        wattage = psu.number("specs", "continuous_wattage") or psu.number("power", "12v_w")
        if wattage is None:
            self._unknown(checks, "psu:system:wattage", "PSU continuous wattage")
            return total_draw, required_psu
        ok = wattage >= required_psu
        checks.append(
            ConstraintCheck(
                id="psu:system:wattage",
                label="PSU wattage exceeds modeled system draw",
                status="pass" if ok else "fail",
                severity="critical",
                details=(
                    f"{psu.name} supplies {wattage:.0f} W against a {required_psu:.0f} W requirement."
                    if ok
                    else f"{psu.name} supplies {wattage:.0f} W, below the {required_psu:.0f} W requirement."
                ),
                evidence={"modeled_draw_w": total_draw, "required_psu_w": required_psu, "psu_w": wattage},
            )
        )
        return total_draw, required_psu

    def _pcie_lane_check(
        self,
        checks: list[ConstraintCheck],
        cpu: ComponentNode | None,
        board: ComponentNode | None,
        gpu: ComponentNode | None,
        storage: ComponentNode | None,
    ) -> None:
        if not cpu or not board:
            return
        cpu_lanes = cpu.number("bandwidth", "pcie_lanes")
        chipset_lanes = board.number("bandwidth", "chipset_pcie_lanes", 0)
        if cpu_lanes is None or chipset_lanes is None:
            self._unknown(checks, "pcie:lane_budget", "PCIe lane budget")
            return

        lane_consumers = [component for component in (gpu, storage) if component]
        required_lanes = sum(
            component.number("bandwidth", "pcie_lanes_required", 0) or 0 for component in lane_consumers
        )
        total_lanes = cpu_lanes + chipset_lanes
        lane_ok = required_lanes <= total_lanes
        checks.append(
            ConstraintCheck(
                id="pcie:lane_budget",
                label="PCIe lanes fit CPU plus chipset budget",
                status="pass" if lane_ok else "fail",
                severity="critical",
                details=(
                    f"Selected PCIe devices require {required_lanes:.0f} lanes out of {total_lanes:.0f} available."
                    if lane_ok
                    else f"Selected PCIe devices require {required_lanes:.0f} lanes but only {total_lanes:.0f} are available."
                ),
                evidence={"required_lanes": required_lanes, "cpu_lanes": cpu_lanes, "chipset_lanes": chipset_lanes},
            )
        )

        cpu_gen = cpu.number("bandwidth", "pcie_generation")
        board_gen = board.number("bandwidth", "pcie_generation")
        required_gen = max(
            [
                component.number("bandwidth", "pcie_generation_required", 0) or 0
                for component in lane_consumers
            ]
            or [0]
        )
        if cpu_gen and board_gen and required_gen:
            gen_ok = min(cpu_gen, board_gen) >= required_gen
            checks.append(
                ConstraintCheck(
                    id="pcie:generation",
                    label="PCIe generation supports selected devices",
                    status="pass" if gen_ok else "warning",
                    severity="warning",
                    details=(
                        f"PCIe Gen {required_gen:.0f} devices are supported by the platform."
                        if gen_ok
                        else f"PCIe devices will negotiate below requested Gen {required_gen:.0f} capability."
                    ),
                    evidence={"required_generation": required_gen, "cpu_generation": cpu_gen, "board_generation": board_gen},
                )
            )

    def _usb_topology_check(
        self,
        checks: list[ConstraintCheck],
        board: ComponentNode | None,
        case: ComponentNode | None,
    ) -> None:
        if not board or not case:
            return
        header_requirements = {
            "usb_20_headers": case.number("bandwidth", "front_usb_20_ports", 0) or 0,
            "usb_32_gen1_headers": case.number("bandwidth", "front_usb_32_gen1_ports", 0) or 0,
            "usb_32_gen2x2_headers": case.number("bandwidth", "front_usb_32_gen2x2_ports", 0) or 0,
        }
        header_supply = {
            key: board.number("bandwidth", key, 0) or 0 for key in header_requirements
        }
        header_ok = all(header_supply[key] >= required for key, required in header_requirements.items())
        checks.append(
            ConstraintCheck(
                id="usb:headers",
                label="Case USB front-panel headers are available",
                status="pass" if header_ok else "fail",
                severity="critical",
                details=(
                    "Motherboard exposes enough internal USB headers for the case front panel."
                    if header_ok
                    else "Case front-panel USB connectors exceed motherboard internal header availability."
                ),
                evidence={"required": header_requirements, "available": header_supply},
            )
        )

        controller_budget = board.number("bandwidth", "usb_controller_gbps")
        if controller_budget is None:
            self._unknown(checks, "usb:bandwidth", "USB controller bandwidth")
            return
        requested_gbps = (
            header_requirements["usb_20_headers"] * 0.48
            + header_requirements["usb_32_gen1_headers"] * 5
            + header_requirements["usb_32_gen2x2_headers"] * 20
        )
        bandwidth_ok = requested_gbps <= controller_budget
        checks.append(
            ConstraintCheck(
                id="usb:bandwidth",
                label="USB front-panel bandwidth fits controller topology",
                status="pass" if bandwidth_ok else "fail",
                severity="critical",
                details=(
                    f"Front-panel USB requests {requested_gbps:.1f} Gbps from a {controller_budget:.1f} Gbps controller budget."
                    if bandwidth_ok
                    else f"Front-panel USB requests {requested_gbps:.1f} Gbps, exceeding the {controller_budget:.1f} Gbps controller budget."
                ),
                evidence={"requested_gbps": requested_gbps, "controller_budget_gbps": controller_budget},
            )
        )

    def _physical_collision_check(
        self,
        checks: list[ConstraintCheck],
        components: list[ComponentNode],
        component_ids: list[str],
    ) -> None:
        for blocker in self.repository.known_space_blockers(component_ids):
            checks.append(
                ConstraintCheck(
                    id=f"space:blocker:{blocker['source_id']}:{blocker['target_id']}",
                    label="Known physical blocking relationship",
                    status="fail",
                    severity="critical",
                    details=blocker["reason"],
                    evidence=blocker,
                )
            )

        collisions = detect_collisions(components)
        if not collisions:
            if any(component.dimensions.get("volume_width_mm") for component in components):
                checks.append(
                    ConstraintCheck(
                        id="space:aabb",
                        label="3D volumetric collision detection",
                        status="pass",
                        severity="info",
                        details="No selected component bounding boxes overlap.",
                    )
                )
            return
        for left, right in collisions:
            checks.append(
                ConstraintCheck(
                    id=f"space:aabb:{left.component_id}:{right.component_id}",
                    label="3D volumetric collision detection",
                    status="fail",
                    severity="critical",
                    details=f"{left.label} intersects {right.label} in the modeled case volume.",
                    evidence={
                        "left": left.model_dump(),
                        "right": right.model_dump(),
                    },
                )
            )

    def _unknown(self, checks: list[ConstraintCheck], check_id: str, label: str) -> None:
        checks.append(
            ConstraintCheck(
                id=check_id,
                label=label,
                status="unknown",
                severity="warning",
                details="Neo4j data is missing required technical fields for deterministic validation.",
            )
        )
