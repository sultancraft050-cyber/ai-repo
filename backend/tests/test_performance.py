from app.models.domain import BuildPreferences, ComponentNode, ComponentKind
from app.services.performance import PerformanceEngine


def test_performance_engine_produces_deterministic_metrics():
    cpu = ComponentNode(
        id="cpu:test",
        kind=ComponentKind.CPU,
        name="Test CPU",
        specs={"single_thread_score": 3150, "multi_thread_score": 61000},
        bandwidth={"memory_gbps": 95},
        power={"tdp_w": 125},
    )
    gpu = ComponentNode(
        id="gpu:test",
        kind=ComponentKind.GPU,
        name="Test GPU",
        specs={"raster_score": 45500, "compute_score": 790, "vram_gb": 16},
        power={"board_power_w": 320},
    )
    ram = ComponentNode(
        id="ram:test",
        kind=ComponentKind.RAM,
        name="Test RAM",
        bandwidth={"memory_gbps": 102},
    )

    result = PerformanceEngine().calculate(
        cpu=cpu,
        gpu=gpu,
        ram=ram,
        preferences=BuildPreferences(purpose="gaming", resolution="1440p"),
        display_refresh_hz=165,
    )

    assert result.expected_fps > 0
    assert result.frame_time_ms > 0
    assert result.bottleneck.cpu_percent >= 0
    assert result.bottleneck.gpu_percent >= 0


def test_cpu_bottleneck_increases_when_cpu_is_weaker_than_gpu():
    cpu = ComponentNode(
        id="cpu:weak",
        kind=ComponentKind.CPU,
        name="Weak CPU",
        specs={"single_thread_score": 900, "multi_thread_score": 6000},
        bandwidth={"memory_gbps": 35},
    )
    gpu = ComponentNode(
        id="gpu:strong",
        kind=ComponentKind.GPU,
        name="Strong GPU",
        specs={"raster_score": 62000, "compute_score": 900, "vram_gb": 24},
    )

    result = PerformanceEngine().calculate(
        cpu=cpu,
        gpu=gpu,
        ram=None,
        preferences=BuildPreferences(purpose="gaming", resolution="4K"),
        display_refresh_hz=240,
    )

    assert result.bottleneck.cpu_percent > result.bottleneck.gpu_percent

