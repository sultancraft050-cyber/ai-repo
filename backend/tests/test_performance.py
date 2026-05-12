from app.models.domain import BuildPreferences, ComponentNode, ComponentKind
from app.services.performance import BASELINE_PROFILE, BASELINE_VERSION, PerformanceEngine


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
    assert result.model_inputs["baseline_version"] == BASELINE_VERSION
    assert result.model_inputs["baseline_profile"] == BASELINE_PROFILE


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


def test_saudi_region_applies_high_power_thermal_adjustment():
    cpu = ComponentNode(
        id="cpu:hot",
        kind=ComponentKind.CPU,
        name="Hot CPU",
        specs={"single_thread_score": 4200, "multi_thread_score": 70000},
        bandwidth={"memory_gbps": 100},
        power={"tdp_w": 170},
    )
    gpu = ComponentNode(
        id="gpu:hot",
        kind=ComponentKind.GPU,
        name="Hot GPU",
        specs={"raster_score": 65000, "compute_score": 1000, "vram_gb": 16},
        power={"board_power_w": 320},
    )
    engine = PerformanceEngine()

    us_result = engine.calculate(
        cpu=cpu,
        gpu=gpu,
        ram=None,
        preferences=BuildPreferences(purpose="gaming", resolution="1440p", region="US"),
        display_refresh_hz=240,
    )
    sa_result = engine.calculate(
        cpu=cpu,
        gpu=gpu,
        ram=None,
        preferences=BuildPreferences(purpose="gaming", resolution="1440p", region="SA"),
        display_refresh_hz=240,
    )

    assert sa_result.expected_fps < us_result.expected_fps
    assert sa_result.model_inputs["thermal_derate_factor"] < 1
    assert any("Saudi region thermal adjustment" in reason for reason in sa_result.reasoning)
