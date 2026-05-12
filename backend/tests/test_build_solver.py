from __future__ import annotations

from app.models.api import BuildGenerateRequest, ConstraintCheck
from app.models.domain import BuildPreferences, ComponentKind, ComponentNode, ComponentOption, SelectedComponents
from app.services.build_solver import MAX_VALID_SOLVER_BUILDS, BuildSolver
from app.services.compatibility import CompatibilityEngine


def _node(kind: ComponentKind, index: int = 0, *, price: float = 100.0) -> ComponentNode:
    specs = {}
    dimensions = {}
    bandwidth = {}
    power = {}
    if kind == ComponentKind.CPU:
        specs = {"socket": "AM5", "single_thread_score": 5000, "multi_thread_score": 90000}
        bandwidth = {"memory_gbps": 120, "pcie_lanes": 28, "pcie_generation": 5}
        power = {"tdp_w": 120}
    elif kind == ComponentKind.GPU:
        specs = {"raster_score": 90000, "compute_score": 1200, "vram_gb": 16}
        dimensions = {"length_mm": 300}
        bandwidth = {"pcie_lanes_required": 16, "pcie_generation_required": 4}
        power = {"board_power_w": 260}
    elif kind == ComponentKind.MOTHERBOARD:
        specs = {"socket": "AM5", "memory_type": "DDR5", "form_factor": "ATX"}
        bandwidth = {
            "chipset_pcie_lanes": 12,
            "pcie_generation": 5,
            "usb_20_headers": 2,
            "usb_32_gen1_headers": 2,
            "usb_32_gen2x2_headers": 1,
            "usb_controller_gbps": 40,
        }
    elif kind == ComponentKind.RAM:
        specs = {"memory_type": "DDR5", "speed_mt_s": 6000}
        bandwidth = {"memory_gbps": 110}
    elif kind == ComponentKind.STORAGE:
        bandwidth = {"pcie_lanes_required": 4, "pcie_generation_required": 4}
    elif kind == ComponentKind.COOLER:
        specs = {"cooling_capacity_w": 250}
        dimensions = {"height_mm": 155}
        power = {"fan_power_w": 5}
    elif kind == ComponentKind.CASE:
        specs = {"supported_form_factors": "ATX|mATX|ITX"}
        dimensions = {"gpu_clearance_mm": 360, "cooler_clearance_mm": 170}
        bandwidth = {"front_usb_20_ports": 1, "front_usb_32_gen1_ports": 1, "front_usb_32_gen2x2_ports": 0}
    elif kind == ComponentKind.PSU:
        specs = {"continuous_wattage": 850}
    return ComponentNode(
        id=f"{kind.value}:{index}",
        kind=kind,
        name=f"{kind.value} {index}",
        price_usd=price,
        specs=specs,
        dimensions=dimensions,
        bandwidth=bandwidth,
        power=power,
    )


class FakeComponentRepository:
    def __init__(self, count_per_kind: int = 1) -> None:
        self.nodes = {
            kind: [_node(kind, index) for index in range(count_per_kind)]
            for kind in ComponentKind
        }

    def components_by_kind(self, kind: ComponentKind, limit: int = 200):
        return self.nodes[kind][:limit]

    def component_options(self, kind: ComponentKind, selection: SelectedComponents, **kwargs):
        del selection, kwargs
        return [
            ComponentOption(id=node.id, kind=node.kind, name=node.name, price_usd=node.price_usd)
            for node in self.nodes[kind]
        ]

    def components_by_ids(self, component_ids: list[str]):
        all_nodes = {node.id: node for nodes in self.nodes.values() for node in nodes}
        return {component_id: all_nodes[component_id] for component_id in component_ids if component_id in all_nodes}

    def has_cpu_motherboard_socket_match(self, cpu_id: str, motherboard_id: str):
        del cpu_id, motherboard_id
        return {"compatible": True, "socket": "AM5"}

    def ram_board_qvl(self, ram_id: str, motherboard_id: str):
        del ram_id, motherboard_id
        return {"memory_type_supported": True, "qvl_validated": True}

    def cooler_socket_support(self, cooler_id: str, cpu_id: str):
        del cooler_id, cpu_id
        return {"supported": True, "socket": "AM5"}

    def known_space_blockers(self, component_ids: list[str]):
        del component_ids
        return []


def test_solver_stops_after_valid_result_cap() -> None:
    service = BuildSolver(FakeComponentRepository(count_per_kind=3))  # type: ignore[arg-type]

    response = service.generate(
        BuildGenerateRequest(
            budget_usd=2000,
            purpose="gaming",
            resolution="1440p",
            preferences=BuildPreferences(display_refresh_hz=144),
            max_candidates_per_type=3,
        )
    )

    assert response.compatibility_status == "valid"
    assert service.explored_configurations == MAX_VALID_SOLVER_BUILDS


def test_solver_threads_display_refresh_rate_into_generated_performance() -> None:
    service = BuildSolver(FakeComponentRepository(count_per_kind=1))  # type: ignore[arg-type]

    response = service.generate(
        BuildGenerateRequest(
            budget_usd=2000,
            purpose="gaming",
            resolution="1080p",
            preferences=BuildPreferences(display_refresh_hz=60, resolution="1080p"),
            max_candidates_per_type=1,
        )
    )

    assert response.builds
    assert response.builds[0].performance.expected_fps <= 60
    assert response.builds[0].performance.bottleneck.display_percent > 0


def test_power_check_treats_zero_psu_wattage_as_known_failure() -> None:
    engine = CompatibilityEngine(FakeComponentRepository())  # type: ignore[arg-type]
    checks: list[ConstraintCheck] = []
    cpu = _node(ComponentKind.CPU)
    psu = _node(ComponentKind.PSU)
    psu.specs["continuous_wattage"] = 0
    psu.power["12v_w"] = 850

    total_draw, required_psu = engine._power_check(checks, [cpu, psu], psu)

    assert total_draw > 0
    assert required_psu > 0
    assert any(check.id == "psu:system:wattage" and check.status == "fail" for check in checks)


def test_power_check_does_not_fall_through_from_zero_board_power() -> None:
    engine = CompatibilityEngine(FakeComponentRepository())  # type: ignore[arg-type]
    gpu = _node(ComponentKind.GPU)
    gpu.power["board_power_w"] = 0
    gpu.power["tdp_w"] = 300

    total_draw, _ = engine._power_check([], [gpu], None)

    assert total_draw == 0
