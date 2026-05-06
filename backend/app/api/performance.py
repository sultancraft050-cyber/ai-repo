from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_repository
from app.graph.repository import Neo4jComponentRepository
from app.models.api import PerformanceRequest, PerformanceResponse
from app.services.performance import PerformanceEngine

router = APIRouter(prefix="/api/performance", tags=["performance"])


@router.post("/calculate", response_model=PerformanceResponse)
def calculate_performance(
    request: PerformanceRequest,
    repository: Neo4jComponentRepository = Depends(get_repository),
) -> PerformanceResponse:
    ids = request.selection.ids()
    components = repository.components_by_ids(ids)
    cpu = components.get(request.selection.cpu_id or "")
    gpu = components.get(request.selection.gpu_id or "")
    ram = components.get(request.selection.ram_id or "")
    if not cpu or not gpu:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Performance calculation requires at least CPU and GPU selections.",
        )
    return PerformanceEngine().calculate(
        cpu=cpu,
        gpu=gpu,
        ram=ram,
        preferences=request.preferences,
        display_refresh_hz=request.display_refresh_hz,
    )

