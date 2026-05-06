from app.models.domain import BoundingBox
from app.services.geometry import aabb_intersects


def test_aabb_collision_detects_overlap():
    gpu = BoundingBox(
        component_id="gpu",
        label="GPU",
        x_mm=0,
        y_mm=0,
        z_mm=0,
        width_mm=300,
        height_mm=60,
        depth_mm=140,
    )
    cooler = BoundingBox(
        component_id="cooler",
        label="Cooler",
        x_mm=250,
        y_mm=10,
        z_mm=20,
        width_mm=80,
        height_mm=80,
        depth_mm=80,
    )

    assert aabb_intersects(gpu, cooler)


def test_aabb_collision_rejects_separated_volumes():
    gpu = BoundingBox(
        component_id="gpu",
        label="GPU",
        x_mm=0,
        y_mm=0,
        z_mm=0,
        width_mm=300,
        height_mm=60,
        depth_mm=140,
    )
    cooler = BoundingBox(
        component_id="cooler",
        label="Cooler",
        x_mm=400,
        y_mm=120,
        z_mm=200,
        width_mm=80,
        height_mm=80,
        depth_mm=80,
    )

    assert not aabb_intersects(gpu, cooler)

