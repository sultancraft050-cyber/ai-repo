from __future__ import annotations

from contextlib import asynccontextmanager
import json
import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import (
    alignment,
    approvals,
    autonomy,
    build,
    catalog,
    cognition,
    compatibility,
    components,
    evolution,
    governance,
    intelligence,
    launch,
    ops,
    performance,
    pricing,
    products,
    sources,
    telemetry,
    user_builds,
)
from app.core.config import settings
from app.core.security import RateLimiter, authenticate_api_key, endpoint_rule, has_role, payload_hash, trace_id
from app.core.version import BACKEND_VERSION, CURRENT_GEN_ENRICHMENT_VERSION, deployment_version_info
from app.graph.driver import Neo4jSessionManager
from app.graph.alignment_repository import Neo4jAlignmentRepository
from app.graph.autonomy_repository import Neo4jAutonomyRepository
from app.graph.cognition_repository import Neo4jCognitionRepository
from app.graph.evolution_repository import Neo4jEvolutionRepository
from app.graph.governance_repository import Neo4jGovernanceRepository
from app.graph.ops_repository import Neo4jOpsRepository
from app.graph.pricing_repository import Neo4jPricingRepository
from app.graph.telemetry_repository import Neo4jTelemetryRepository
from app.graph.user_build_repository import Neo4jUserBuildRepository
from app.models.ops import AuditEvent
from app.services.autonomy import default_agents
from app.services.autonomy_worker import AutonomousAgentWorker
from app.services.cognition_worker import CognitionWorker
from app.services.ops import OpsService
from app.services.launch_analytics import LaunchAnalyticsStore
from app.services.pricing_scheduler import PricingScheduler
from app.services.pricing_worker import PricingWorker

logger = logging.getLogger("pc_builder.ops")
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager = Neo4jSessionManager(settings)
    app.state.neo4j = manager
    app.state.pricing_worker = None
    app.state.pricing_scheduler = None
    app.state.cognition_worker = None
    app.state.autonomous_agent_worker = None
    if manager.verify():
        pricing_repository = Neo4jPricingRepository(manager.driver)
        pricing_repository.apply_schema()
        _seed_cpu_specs_safely(pricing_repository)
        Neo4jTelemetryRepository(manager.driver).apply_schema()
        Neo4jCognitionRepository(manager.driver).apply_schema()
        Neo4jGovernanceRepository(manager.driver).apply_schema()
        Neo4jEvolutionRepository(manager.driver).apply_schema()
        Neo4jAlignmentRepository(manager.driver).apply_schema()
        Neo4jOpsRepository(manager.driver).apply_schema()
        Neo4jUserBuildRepository(manager.driver).apply_schema()
        autonomy_repository = Neo4jAutonomyRepository(manager.driver)
        autonomy_repository.apply_schema()
        autonomy_repository.upsert_agents(default_agents())
        app.state.pricing_worker = PricingWorker(manager.driver)
        app.state.pricing_worker.start()
        app.state.cognition_worker = CognitionWorker(manager.driver)
        app.state.cognition_worker.start()
        if settings.autonomous_agents_enabled:
            app.state.autonomous_agent_worker = AutonomousAgentWorker(
                manager.driver,
                interval_seconds=settings.autonomous_agent_interval_seconds,
                max_products=settings.autonomous_agent_max_products,
            )
            app.state.autonomous_agent_worker.start()
        if settings.pricing_scheduler_enabled:
            app.state.pricing_scheduler = PricingScheduler(
                manager.driver,
                app.state.pricing_worker,
                top_interval_seconds=settings.pricing_top_refresh_seconds,
                standard_interval_seconds=settings.pricing_standard_refresh_seconds,
            )
            app.state.pricing_scheduler.start()
    yield
    if app.state.pricing_scheduler:
        app.state.pricing_scheduler.stop()
    if app.state.pricing_worker:
        app.state.pricing_worker.stop()
    if app.state.cognition_worker:
        app.state.cognition_worker.stop()
    if app.state.autonomous_agent_worker:
        app.state.autonomous_agent_worker.stop()
    manager.close()


def _seed_cpu_specs_safely(pricing_repository: Neo4jPricingRepository) -> None:
    if os.getenv("CPU_SPECS_SEED_ON_START", "true").lower() not in {"1", "true", "yes"}:
        return
    try:
        from scripts.import_pasted_cpu_specs import parse_rows

        response = pricing_repository.import_cpu_specs(
            rows=parse_rows(),
            source_name="TechPowerUp CPU Database",
            dry_run=False,
        )
        logger.info(
            "cpu_specs_seed_complete imported_count=%s skipped_count=%s",
            response.imported_count,
            response.skipped_count,
        )
    except Exception:
        logger.exception("cpu_specs_seed_failed")


app = FastAPI(
    title="Custom PC Compatibility Intelligence Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.rate_limiter = RateLimiter(
    window_seconds=settings.public_rate_limit_window_seconds,
    max_requests=settings.public_rate_limit_max_requests,
)
app.state.launch_analytics = LaunchAnalyticsStore()

if settings.processed_image_storage_dir:
    app.mount(
        "/processed-images",
        StaticFiles(directory=settings.processed_image_storage_dir, check_dir=False),
        name="processed-images",
    )


@app.middleware("http")
async def security_audit_middleware(request: Request, call_next):
    current_trace_id = request.headers.get("X-Trace-ID") or trace_id()
    request.state.trace_id = current_trace_id
    body = await request.body()
    audit_metadata = _audit_metadata(request, body)

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive  # type: ignore[attr-defined]
    rule = endpoint_rule(request.method, request.url.path)
    principal = authenticate_api_key(request.headers.get("X-API-Key"))
    request.state.principal = principal
    if rule:
        rate_key = f"{principal.actor}:{request.client.host if request.client else 'unknown'}:{request.url.path}"
        if not request.app.state.rate_limiter.allow(rate_key):
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limited", "detail": "Too many requests.", "trace_id": current_trace_id},
                headers={"X-Trace-ID": current_trace_id},
            )
        if not principal.authenticated or not has_role(principal, rule.role):
            _write_audit_safely(
                request,
                AuditEvent(
                    actor=principal.actor,
                    role=principal.role,
                    action="unauthorized",
                    endpoint=request.url.path,
                    method=request.method,
                    request_payload_hash=payload_hash(body) if body else None,
                    result="rejected",
                    status_code=403,
                    trace_id=current_trace_id,
                    approval_required=rule.approval_required,
                    risk_level=rule.risk_level,
                    metadata=audit_metadata,
                ),
            )
            return JSONResponse(
                status_code=403,
                content={
                    "error": "forbidden",
                    "detail": f"{rule.role} role required.",
                    "trace_id": current_trace_id,
                },
                headers={"X-Trace-ID": current_trace_id},
            )
        idempotency_key = request.headers.get("X-Idempotency-Key")
        if idempotency_key and request.method.upper() != "GET" and _idempotency_seen_safely(request, idempotency_key):
            return JSONResponse(
                status_code=409,
                content={
                    "error": "duplicate_request",
                    "detail": "Mutation already completed for this idempotency key.",
                    "trace_id": current_trace_id,
                },
                headers={"X-Trace-ID": current_trace_id},
            )
    try:
        response = await call_next(request)
    except Exception as error:  # noqa: BLE001 - sanitize API errors at the edge.
        logger.exception(
            json.dumps({"event": "request_failed", "path": request.url.path, "trace_id": current_trace_id})
        )
        if rule:
            _write_audit_safely(
                request,
                AuditEvent(
                    actor=principal.actor,
                    role=principal.role,
                    action=request.url.path.strip("/").replace("/", "."),
                    endpoint=request.url.path,
                    method=request.method,
                    request_payload_hash=payload_hash(body) if body else None,
                    idempotency_key=request.headers.get("X-Idempotency-Key"),
                    result="failed",
                    status_code=500,
                    trace_id=current_trace_id,
                    approval_required=rule.approval_required,
                    risk_level=rule.risk_level,
                    metadata={**audit_metadata, "error_type": type(error).__name__},
                ),
            )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "detail": (
                    f"Request failed safely: {type(error).__name__}."
                    if request.url.path == "/catalog/import/stage"
                    else "Request failed. Check trace ID."
                ),
                "trace_id": current_trace_id,
            },
            headers={"X-Trace-ID": current_trace_id},
        )
    response.headers["X-Trace-ID"] = current_trace_id
    if rule:
        _write_audit_safely(
            request,
            AuditEvent(
                actor=principal.actor,
                role=principal.role,
                action=request.url.path.strip("/").replace("/", "."),
                endpoint=request.url.path,
                method=request.method,
                request_payload_hash=payload_hash(body) if body else None,
                idempotency_key=request.headers.get("X-Idempotency-Key"),
                result="succeeded" if response.status_code < 400 else "failed",
                status_code=response.status_code,
                trace_id=current_trace_id,
                approval_required=rule.approval_required,
                risk_level=rule.risk_level,
                metadata=audit_metadata,
            ),
        )
    return response


def _write_audit_safely(request: Request, event: AuditEvent) -> None:
    try:
        manager = getattr(request.app.state, "neo4j", None)
        if manager and manager.unavailable_reason is None:
            Neo4jOpsRepository(manager.driver).create_audit_event(event)
    except Exception:
        logger.warning(json.dumps({"event": "audit_write_failed", "trace_id": event.trace_id}))


def _audit_metadata(request: Request, body: bytes) -> dict[str, str]:
    metadata: dict[str, str] = {}
    region = request.query_params.get("region")
    market_source = request.query_params.get("provider") or request.query_params.get("source")
    if body:
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, dict):
            if payload.get("region"):
                region = str(payload["region"])
            providers = payload.get("providers")
            if isinstance(providers, list) and providers:
                market_source = ",".join(str(provider) for provider in providers[:5])
            elif payload.get("source"):
                market_source = str(payload["source"])
    if region:
        metadata["region"] = region.upper()
    if market_source:
        metadata["market_source"] = market_source
    return metadata


def _idempotency_seen_safely(request: Request, key: str) -> bool:
    try:
        manager = getattr(request.app.state, "neo4j", None)
        if manager and manager.unavailable_reason is None:
            return Neo4jOpsRepository(manager.driver).idempotency_seen(request.url.path, key)
    except Exception:
        logger.warning(json.dumps({"event": "idempotency_check_failed", "path": request.url.path}))
    return False

app.include_router(compatibility.router)
app.include_router(performance.router)
app.include_router(components.router)
app.include_router(build.router)
app.include_router(catalog.router)
app.include_router(products.router)
app.include_router(pricing.router)
app.include_router(sources.router)
app.include_router(intelligence.router)
app.include_router(launch.router)
app.include_router(telemetry.router)
app.include_router(cognition.router)
app.include_router(governance.router)
app.include_router(evolution.router)
app.include_router(alignment.router)
app.include_router(autonomy.router)
app.include_router(ops.router)
app.include_router(approvals.router)
app.include_router(user_builds.router)


@app.get("/health")
def health() -> dict[str, str | bool | None]:
    manager = app.state.neo4j
    manager.verify()
    version_info = deployment_version_info(
        environment=settings.environment,
        backend_url=settings.backend_url,
        frontend_url=settings.frontend_url,
    )
    return {
        "ok": manager.unavailable_reason is None,
        "neo4j": "connected" if manager.unavailable_reason is None else "unavailable",
        "detail": manager.unavailable_reason,
        "environment": settings.environment,
        "market_data_mode": settings.market_data_mode,
        "backend_version": version_info.get("backend_version") or BACKEND_VERSION,
        "git_sha": version_info.get("git_sha"),
        "current_gen_enrichment_version": version_info.get("current_gen_enrichment_version")
        or CURRENT_GEN_ENRICHMENT_VERSION,
    }


@app.get("/health/neo4j")
def neo4j_health() -> dict[str, str | bool | None]:
    manager = app.state.neo4j
    manager.verify()
    return {
        "ok": manager.unavailable_reason is None,
        "status": "connected" if manager.unavailable_reason is None else "unavailable",
        "detail": manager.unavailable_reason,
    }


@app.get("/health/workers")
def worker_health():
    return OpsService(Neo4jOpsRepository(app.state.neo4j.driver)).worker_health(app.state)


@app.get("/health/external-sources")
def external_source_health():
    return OpsService(Neo4jOpsRepository(app.state.neo4j.driver)).source_health()
