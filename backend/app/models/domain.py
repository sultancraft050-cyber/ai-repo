from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ComponentKind(str, Enum):
    CPU = "CPU"
    GPU = "GPU"
    MOTHERBOARD = "Motherboard"
    RAM = "RAM"
    CASE = "Case"
    COOLER = "Cooler"
    STORAGE = "Storage"
    PSU = "PSU"


Purpose = Literal["gaming", "simulation", "workstation"]
Resolution = Literal["1080p", "1440p", "4K"]
CaseSize = Literal["ITX", "mATX", "ATX", "EATX"]
NoisePreference = Literal["quiet", "balanced", "performance"]


class SelectedComponents(BaseModel):
    cpu_id: str | None = None
    gpu_id: str | None = None
    motherboard_id: str | None = None
    ram_id: str | None = None
    case_id: str | None = None
    cooler_id: str | None = None
    storage_id: str | None = None
    psu_id: str | None = None

    def ids(self) -> list[str]:
        return [
            value
            for value in (
                self.cpu_id,
                self.gpu_id,
                self.motherboard_id,
                self.ram_id,
                self.case_id,
                self.cooler_id,
                self.storage_id,
                self.psu_id,
            )
            if value
        ]


class BuildPreferences(BaseModel):
    budget_usd: float | None = Field(default=None, ge=0)
    purpose: Purpose = "gaming"
    resolution: Resolution = "1440p"
    display_refresh_hz: int = Field(default=144, ge=30, le=1000)
    region: str = Field(default="US", min_length=2, max_length=8)
    brand_bias: list[str] = Field(default_factory=list)
    size: CaseSize | None = None
    noise_preference: NoisePreference = "balanced"
    upgrade_path_priority: int = Field(default=5, ge=0, le=10)


class ComponentNode(BaseModel):
    id: str
    kind: ComponentKind
    name: str
    brand: str | None = None
    price_usd: float | None = None
    specs: dict[str, Any] = Field(default_factory=dict)
    dimensions: dict[str, Any] = Field(default_factory=dict)
    bandwidth: dict[str, Any] = Field(default_factory=dict)
    power: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)

    def number(self, group: str, key: str, default: float | None = None) -> float | None:
        data = getattr(self, group)
        value = data.get(key)
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def text(self, group: str, key: str, default: str | None = None) -> str | None:
        data = getattr(self, group)
        value = data.get(key)
        if value is None:
            return default
        return str(value)


class BoundingBox(BaseModel):
    component_id: str
    label: str
    x_mm: float = 0
    y_mm: float = 0
    z_mm: float = 0
    width_mm: float
    height_mm: float
    depth_mm: float

    @field_validator("width_mm", "height_mm", "depth_mm")
    @classmethod
    def positive_dimension(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("bounding volume dimensions must be positive")
        return value

    @property
    def max_x(self) -> float:
        return self.x_mm + self.width_mm

    @property
    def max_y(self) -> float:
        return self.y_mm + self.height_mm

    @property
    def max_z(self) -> float:
        return self.z_mm + self.depth_mm


class ComponentOption(BaseModel):
    id: str
    kind: ComponentKind
    name: str
    brand: str | None = None
    price_usd: float | None = None
    summary: str | None = None
