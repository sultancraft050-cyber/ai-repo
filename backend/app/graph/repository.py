from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from neo4j import Driver

from app.core.config import settings
from app.graph import queries
from app.models.domain import ComponentKind, ComponentNode, ComponentOption, SelectedComponents


KIND_LABELS = {kind.value for kind in ComponentKind}


def _split_properties(properties: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, Any] = {
        "specs": {},
        "dimensions": {},
        "bandwidth": {},
        "power": {},
        "raw": {},
    }
    for key, value in properties.items():
        if key.startswith("spec_"):
            groups["specs"][key.removeprefix("spec_")] = value
        elif key.startswith("dim_"):
            groups["dimensions"][key.removeprefix("dim_")] = value
        elif key.startswith("bandwidth_"):
            groups["bandwidth"][key.removeprefix("bandwidth_")] = value
        elif key.startswith("power_"):
            groups["power"][key.removeprefix("power_")] = value
        else:
            groups["raw"][key] = value
    return groups


def _component_kind(labels: Iterable[str]) -> ComponentKind:
    for label in labels:
        if label in KIND_LABELS:
            return ComponentKind(label)
    raise ValueError(f"component node missing supported label: {list(labels)}")


def _node_from_record(record: dict[str, Any]) -> ComponentNode:
    properties = dict(record["properties"])
    groups = _split_properties(properties)
    return ComponentNode(
        id=record["id"],
        kind=_component_kind(record["labels"]),
        name=str(properties.get("name", record["id"])),
        brand=properties.get("brand"),
        price_usd=properties.get("price_usd"),
        specs=groups["specs"],
        dimensions=groups["dimensions"],
        bandwidth=groups["bandwidth"],
        power=groups["power"],
        raw=groups["raw"],
    )


def _option_from_node(node: ComponentNode) -> ComponentOption:
    summary_parts = []
    if node.kind == ComponentKind.CPU:
        cores = node.specs.get("core_count")
        socket = node.specs.get("socket")
        summary_parts.extend(part for part in (f"{cores} cores" if cores else None, socket) if part)
    elif node.kind == ComponentKind.GPU:
        vram = node.specs.get("vram_gb")
        length = node.dimensions.get("length_mm")
        summary_parts.extend(
            part for part in (f"{vram} GB VRAM" if vram else None, f"{length} mm" if length else None) if part
        )
    elif node.kind == ComponentKind.MOTHERBOARD:
        summary_parts.extend(
            part
            for part in (node.specs.get("form_factor"), node.specs.get("memory_type"))
            if part
        )
    elif node.kind == ComponentKind.PSU:
        watts = node.specs.get("continuous_wattage")
        summary_parts.append(f"{watts} W" if watts else "")
    return ComponentOption(
        id=node.id,
        kind=node.kind,
        name=node.name,
        brand=node.brand,
        price_usd=node.price_usd,
        summary=", ".join(part for part in summary_parts if part) or None,
    )


class Neo4jComponentRepository:
    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    def components_by_ids(self, component_ids: list[str]) -> dict[str, ComponentNode]:
        if not component_ids:
            return {}
        records, _, _ = self.driver.execute_query(
            queries.COMPONENTS_BY_IDS,
            component_ids=component_ids,
            database_=settings.neo4j_database,
        )
        return {record["id"]: _node_from_record(record.data()) for record in records}

    def components_by_kind(self, kind: ComponentKind, limit: int = 200) -> list[ComponentNode]:
        records, _, _ = self.driver.execute_query(
            queries.COMPONENTS_BY_KIND,
            kind=kind.value,
            limit=limit,
            database_=settings.neo4j_database,
        )
        return [_node_from_record(record.data()) for record in records]

    def relationships_between_selected(self, component_ids: list[str]) -> list[dict[str, Any]]:
        if len(component_ids) < 2:
            return []
        records, _, _ = self.driver.execute_query(
            queries.RELATIONSHIPS_BETWEEN_SELECTED,
            component_ids=component_ids,
            database_=settings.neo4j_database,
        )
        return [record.data() for record in records]

    def has_cpu_motherboard_socket_match(self, cpu_id: str, motherboard_id: str) -> dict[str, Any]:
        records, _, _ = self.driver.execute_query(
            queries.CPU_MOTHERBOARD_SOCKET,
            cpu_id=cpu_id,
            motherboard_id=motherboard_id,
            database_=settings.neo4j_database,
        )
        return records[0].data() if records else {"compatible": False}

    def ram_board_qvl(self, ram_id: str, motherboard_id: str) -> dict[str, Any]:
        records, _, _ = self.driver.execute_query(
            queries.RAM_MOTHERBOARD_QVL,
            ram_id=ram_id,
            motherboard_id=motherboard_id,
            database_=settings.neo4j_database,
        )
        return records[0].data() if records else {
            "memory_type_supported": False,
            "qvl_validated": False,
        }

    def cooler_socket_support(self, cooler_id: str, cpu_id: str) -> dict[str, Any]:
        records, _, _ = self.driver.execute_query(
            queries.COOLER_SOCKET_SUPPORT,
            cooler_id=cooler_id,
            cpu_id=cpu_id,
            database_=settings.neo4j_database,
        )
        return records[0].data() if records else {"supported": False}

    def known_space_blockers(self, component_ids: list[str]) -> list[dict[str, Any]]:
        if len(component_ids) < 2:
            return []
        records, _, _ = self.driver.execute_query(
            queries.KNOWN_SPACE_BLOCKERS,
            component_ids=component_ids,
            database_=settings.neo4j_database,
        )
        return [record.data() for record in records]

    def component_options(
        self,
        kind: ComponentKind,
        selection: SelectedComponents,
        limit: int = 25,
        brand_bias: list[str] | None = None,
        max_price: float | None = None,
        qvl_required: bool = True,
        form_factor: str | None = None,
    ) -> list[ComponentOption]:
        brand_bias = brand_bias or []
        if kind == ComponentKind.MOTHERBOARD and selection.cpu_id:
            records, _, _ = self.driver.execute_query(
                queries.MOTHERBOARD_OPTIONS_FOR_CPU,
                cpu_id=selection.cpu_id,
                form_factor=form_factor,
                limit=limit,
                database_=settings.neo4j_database,
            )
        elif kind == ComponentKind.RAM and selection.motherboard_id:
            records, _, _ = self.driver.execute_query(
                queries.RAM_OPTIONS_FOR_BOARD,
                motherboard_id=selection.motherboard_id,
                qvl_required=qvl_required,
                limit=limit,
                database_=settings.neo4j_database,
            )
        elif kind == ComponentKind.CASE and (selection.motherboard_id or selection.gpu_id):
            nodes = self.components_by_ids(
                [value for value in (selection.motherboard_id, selection.gpu_id) if value]
            )
            board = nodes.get(selection.motherboard_id or "")
            gpu = nodes.get(selection.gpu_id or "")
            records, _, _ = self.driver.execute_query(
                queries.CASE_OPTIONS_FOR_BOARD_AND_GPU,
                form_factor=board.specs.get("form_factor") if board else None,
                gpu_length_mm=gpu.dimensions.get("length_mm") if gpu else None,
                limit=limit,
                database_=settings.neo4j_database,
            )
        else:
            records, _, _ = self.driver.execute_query(
                queries.COMPONENT_OPTIONS,
                kind=kind.value,
                max_price=max_price,
                brand_bias=brand_bias,
                limit=limit,
                database_=settings.neo4j_database,
            )
        return [_option_from_node(_node_from_record(record.data())) for record in records]
