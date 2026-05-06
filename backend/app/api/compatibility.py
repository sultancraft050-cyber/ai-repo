from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_repository
from app.graph.repository import Neo4jComponentRepository
from app.models.api import CompatibilityRequest, CompatibilityResponse
from app.services.compatibility import CompatibilityEngine

router = APIRouter(tags=["compatibility"])


@router.post("/compatibility/check", response_model=CompatibilityResponse)
def check_compatibility(
    request: CompatibilityRequest,
    repository: Neo4jComponentRepository = Depends(get_repository),
) -> CompatibilityResponse:
    return CompatibilityEngine(repository).check(request)

