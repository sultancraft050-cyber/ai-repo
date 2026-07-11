from __future__ import annotations

import os


BACKEND_VERSION = "0.1.0"
API_CONTRACT_VERSION = "1"
CURRENT_GEN_ENRICHMENT_VERSION = "phase2-current-gen-enrichment-v1"


def deployment_version_info(*, environment: str, backend_url: str | None = None, frontend_url: str | None = None) -> dict[str, str | None]:
    git_sha = (
        os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or os.getenv("RAILWAY_GIT_COMMIT")
        or os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("FLY_MACHINE_VERSION")
        or os.getenv("VERCEL_GIT_COMMIT_SHA")
        or os.getenv("GIT_SHA")
    )
    return {
        "backend_version": os.getenv("BACKEND_VERSION", BACKEND_VERSION),
        "release": os.getenv("BACKEND_VERSION", BACKEND_VERSION),
        "frontend_version": os.getenv("FRONTEND_VERSION"),
        "git_sha": git_sha[:12] if git_sha else None,
        "build_time": os.getenv("BUILD_TIME") or os.getenv("RAILWAY_DEPLOYMENT_TIMESTAMP"),
        "api_contract_version": os.getenv("API_CONTRACT_VERSION", API_CONTRACT_VERSION),
        "environment": environment,
        "backend_url": backend_url,
        "frontend_url": frontend_url,
        "current_gen_enrichment_version": os.getenv(
            "CURRENT_GEN_ENRICHMENT_VERSION",
            CURRENT_GEN_ENRICHMENT_VERSION,
        ),
    }


def public_release_metadata(*, service: str, environment: str, release_info: dict[str, str | None]) -> dict[str, str | None]:
    return {
        "service": service,
        "environment": environment,
        "release": release_info.get("release") or "unknown",
        "git_sha": release_info.get("git_sha"),
        "build_time": release_info.get("build_time"),
        "api_contract_version": release_info.get("api_contract_version") or API_CONTRACT_VERSION,
    }
