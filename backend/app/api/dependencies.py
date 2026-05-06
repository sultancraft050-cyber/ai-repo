from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.graph.alignment_repository import Neo4jAlignmentRepository
from app.graph.autonomy_repository import Neo4jAutonomyRepository
from app.graph.ops_repository import Neo4jOpsRepository
from app.graph.repository import Neo4jComponentRepository
from app.graph.cognition_repository import Neo4jCognitionRepository
from app.graph.evolution_repository import Neo4jEvolutionRepository
from app.graph.governance_repository import Neo4jGovernanceRepository
from app.graph.pricing_repository import Neo4jPricingRepository
from app.graph.telemetry_repository import Neo4jTelemetryRepository


def get_repository(request: Request) -> Neo4jComponentRepository:
    manager = request.app.state.neo4j
    manager.verify()
    if manager.unavailable_reason:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Neo4j is unavailable: {manager.unavailable_reason}",
        )
    return Neo4jComponentRepository(manager.driver)


def get_pricing_repository(request: Request) -> Neo4jPricingRepository:
    manager = request.app.state.neo4j
    manager.verify()
    if manager.unavailable_reason:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Neo4j is unavailable: {manager.unavailable_reason}",
        )
    return Neo4jPricingRepository(manager.driver)


def get_telemetry_repository(request: Request) -> Neo4jTelemetryRepository:
    manager = request.app.state.neo4j
    manager.verify()
    if manager.unavailable_reason:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Neo4j is unavailable: {manager.unavailable_reason}",
        )
    return Neo4jTelemetryRepository(manager.driver)


def get_cognition_repository(request: Request) -> Neo4jCognitionRepository:
    manager = request.app.state.neo4j
    manager.verify()
    if manager.unavailable_reason:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Neo4j is unavailable: {manager.unavailable_reason}",
        )
    return Neo4jCognitionRepository(manager.driver)


def get_governance_repository(request: Request) -> Neo4jGovernanceRepository:
    manager = request.app.state.neo4j
    manager.verify()
    if manager.unavailable_reason:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Neo4j is unavailable: {manager.unavailable_reason}",
        )
    return Neo4jGovernanceRepository(manager.driver)


def get_evolution_repository(request: Request) -> Neo4jEvolutionRepository:
    manager = request.app.state.neo4j
    manager.verify()
    if manager.unavailable_reason:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Neo4j is unavailable: {manager.unavailable_reason}",
        )
    return Neo4jEvolutionRepository(manager.driver)


def get_alignment_repository(request: Request) -> Neo4jAlignmentRepository:
    manager = request.app.state.neo4j
    manager.verify()
    if manager.unavailable_reason:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Neo4j is unavailable: {manager.unavailable_reason}",
        )
    return Neo4jAlignmentRepository(manager.driver)


def get_autonomy_repository(request: Request) -> Neo4jAutonomyRepository:
    manager = request.app.state.neo4j
    manager.verify()
    if manager.unavailable_reason:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Neo4j is unavailable: {manager.unavailable_reason}",
        )
    return Neo4jAutonomyRepository(manager.driver)


def get_ops_repository(request: Request) -> Neo4jOpsRepository:
    manager = request.app.state.neo4j
    manager.verify()
    if manager.unavailable_reason:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Neo4j is unavailable: {manager.unavailable_reason}",
        )
    return Neo4jOpsRepository(manager.driver)
