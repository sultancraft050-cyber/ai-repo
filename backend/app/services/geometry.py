from __future__ import annotations

from app.models.domain import BoundingBox, ComponentNode


def aabb_intersects(left: BoundingBox, right: BoundingBox) -> bool:
    return (
        left.x_mm < right.max_x
        and left.max_x > right.x_mm
        and left.y_mm < right.max_y
        and left.max_y > right.y_mm
        and left.z_mm < right.max_z
        and left.max_z > right.z_mm
    )


def volume_from_component(component: ComponentNode) -> BoundingBox | None:
    dims = component.dimensions
    required = ("volume_width_mm", "volume_height_mm", "volume_depth_mm")
    if not all(key in dims for key in required):
        return None
    return BoundingBox(
        component_id=component.id,
        label=component.name,
        x_mm=float(dims.get("volume_x_mm", 0)),
        y_mm=float(dims.get("volume_y_mm", 0)),
        z_mm=float(dims.get("volume_z_mm", 0)),
        width_mm=float(dims["volume_width_mm"]),
        height_mm=float(dims["volume_height_mm"]),
        depth_mm=float(dims["volume_depth_mm"]),
    )


def detect_collisions(components: list[ComponentNode]) -> list[tuple[BoundingBox, BoundingBox]]:
    volumes = [volume for component in components if (volume := volume_from_component(component))]
    collisions: list[tuple[BoundingBox, BoundingBox]] = []
    for index, left in enumerate(volumes):
        for right in volumes[index + 1 :]:
            if aabb_intersects(left, right):
                collisions.append((left, right))
    return collisions

