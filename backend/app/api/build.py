from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_repository
from app.graph.repository import Neo4jComponentRepository
from app.models.api import BuildGenerateRequest, BuildGenerateResponse
from app.services.build_solver import BuildSolver

router = APIRouter(prefix="/build", tags=["build-generator"])


@router.post("/generate", response_model=BuildGenerateResponse)
def generate_build(
    request: BuildGenerateRequest,
    repository: Neo4jComponentRepository = Depends(get_repository),
) -> BuildGenerateResponse:
    return BuildSolver(repository).generate(request)
