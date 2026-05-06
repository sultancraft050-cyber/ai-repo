from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_repository
from app.graph.repository import Neo4jComponentRepository
from app.models.api import ComponentOptionsResponse
from app.models.domain import BuildPreferences, ComponentKind, SelectedComponents

router = APIRouter(prefix="/components", tags=["components"])


@router.get("/options", response_model=ComponentOptionsResponse)
def component_options(
    kind: ComponentKind,
    cpu_id: str | None = None,
    gpu_id: str | None = None,
    motherboard_id: str | None = None,
    ram_id: str | None = None,
    case_id: str | None = None,
    cooler_id: str | None = None,
    storage_id: str | None = None,
    psu_id: str | None = None,
    purpose: str = "gaming",
    resolution: str = "1440p",
    qvl_required: bool = True,
    limit: int = Query(default=25, ge=1, le=100),
    repository: Neo4jComponentRepository = Depends(get_repository),
) -> ComponentOptionsResponse:
    selection = SelectedComponents(
        cpu_id=cpu_id,
        gpu_id=gpu_id,
        motherboard_id=motherboard_id,
        ram_id=ram_id,
        case_id=case_id,
        cooler_id=cooler_id,
        storage_id=storage_id,
        psu_id=psu_id,
    )
    preferences = BuildPreferences(purpose=purpose, resolution=resolution)
    options = repository.component_options(
        kind=kind,
        selection=selection,
        limit=limit,
        brand_bias=preferences.brand_bias,
        qvl_required=qvl_required,
        form_factor=preferences.size,
    )
    return ComponentOptionsResponse(
        options=options,
        degraded=len(options) == 0,
        message=None if options else "Neo4j returned no compatible candidates for this selection.",
    )

