from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.dependencies import get_pricing_repository, get_user_build_repository, resolve_market_region
from app.graph.pricing_repository import Neo4jPricingRepository
from app.graph.user_build_repository import Neo4jUserBuildRepository
from app.models.launch import AnalyticsEventCreate
from app.models.user_builds import (
    BuildComparisonRequest,
    BuildComparisonResponse,
    SavedBuildCreateRequest,
    SavedBuildListResponse,
    SavedBuildUpdateRequest,
    SavedBuildView,
    UserAccountCreateRequest,
    UserAccountView,
    WatchlistAddRequest,
    WatchlistResponse,
)
from app.services.launch_analytics import record_launch_event
from app.services.user_builds import UserBuildService

router = APIRouter(tags=["user-builds"])


def _service(
    repository: Neo4jUserBuildRepository,
    pricing_repository: Neo4jPricingRepository | None = None,
) -> UserBuildService:
    return UserBuildService(repository, pricing_repository)


@router.post("/users", response_model=UserAccountView)
def create_user(
    request: UserAccountCreateRequest,
    repository: Neo4jUserBuildRepository = Depends(get_user_build_repository),
) -> UserAccountView:
    return _service(repository).create_user(request)


@router.get("/users/{user_id}/builds", response_model=SavedBuildListResponse)
def user_saved_builds(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    repository: Neo4jUserBuildRepository = Depends(get_user_build_repository),
) -> SavedBuildListResponse:
    return SavedBuildListResponse(builds=_service(repository).list_builds(user_id=user_id, guest_id=None, limit=limit))


@router.get("/guests/{guest_id}/builds", response_model=SavedBuildListResponse)
def guest_saved_builds(
    guest_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    repository: Neo4jUserBuildRepository = Depends(get_user_build_repository),
) -> SavedBuildListResponse:
    return SavedBuildListResponse(builds=_service(repository).list_builds(user_id=None, guest_id=guest_id, limit=limit))


@router.post("/builds/saved", response_model=SavedBuildView)
def save_build(
    request: SavedBuildCreateRequest,
    fastapi_request: Request,
    repository: Neo4jUserBuildRepository = Depends(get_user_build_repository),
) -> SavedBuildView:
    client = fastapi_request.client.host if fastapi_request.client else "unknown"
    limiter = getattr(fastapi_request.app.state, "rate_limiter", None)
    if limiter and not limiter.allow(f"public:save-build:{client}"):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many saved build requests. Try again later.")
    if not request.user_id and not request.guest_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id or guest_id is required.")
    resolve_market_region(request.region)
    saved = _service(repository).save_build(request)
    _record_event(
        fastapi_request,
        AnalyticsEventCreate(
            event_type="build_save",
            region=saved.region,
            anonymous_session_id=request.guest_id,
            user_id=request.user_id,
            build_status=str(saved.build_summary.get("budget_status") or ""),
            budget_sar=_optional_budget(saved.build_summary),
            metadata={"build_mode": saved.build_mode, "favorite": saved.favorite},
        ),
    )
    return saved


@router.get("/builds/saved/{build_id}", response_model=SavedBuildView)
def get_saved_build(
    build_id: str,
    repository: Neo4jUserBuildRepository = Depends(get_user_build_repository),
) -> SavedBuildView:
    build = _service(repository).get_build(build_id)
    if not build:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved build not found.")
    return build


@router.patch("/builds/saved/{build_id}", response_model=SavedBuildView)
def update_saved_build(
    build_id: str,
    request: SavedBuildUpdateRequest,
    repository: Neo4jUserBuildRepository = Depends(get_user_build_repository),
) -> SavedBuildView:
    build = _service(repository).update_build(build_id, request)
    if not build:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved build not found.")
    return build


@router.post("/builds/saved/{build_id}/duplicate", response_model=SavedBuildView)
def duplicate_saved_build(
    build_id: str,
    user_id: str | None = None,
    guest_id: str | None = None,
    repository: Neo4jUserBuildRepository = Depends(get_user_build_repository),
) -> SavedBuildView:
    build = _service(repository).duplicate_build(build_id, user_id=user_id, guest_id=guest_id)
    if not build:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved build not found.")
    return build


@router.delete("/builds/saved/{build_id}")
def delete_saved_build(
    build_id: str,
    repository: Neo4jUserBuildRepository = Depends(get_user_build_repository),
) -> dict[str, bool]:
    return {"deleted": _service(repository).delete_build(build_id)}


@router.get("/build/share/{share_slug}", response_model=SavedBuildView)
def get_shared_build(
    request: Request,
    share_slug: str,
    repository: Neo4jUserBuildRepository = Depends(get_user_build_repository),
) -> SavedBuildView:
    build = _service(repository).get_shared_build(share_slug)
    if not build:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared build not found.")
    _record_event(
        request,
        AnalyticsEventCreate(
            event_type="build_share",
            region=build.region,
            anonymous_session_id=request.headers.get("X-Session-ID"),
            build_status=str(build.build_summary.get("budget_status") or ""),
            metadata={"public_share_view": True},
        ),
    )
    return build


@router.post("/builds/compare", response_model=BuildComparisonResponse)
def compare_builds(
    request: BuildComparisonRequest,
    fastapi_request: Request,
    repository: Neo4jUserBuildRepository = Depends(get_user_build_repository),
) -> BuildComparisonResponse:
    response = _service(repository).compare_builds(request)
    _record_event(
        fastapi_request,
        AnalyticsEventCreate(
            event_type="build_comparison_usage",
            region="SA",
            anonymous_session_id=request.guest_id,
            user_id=request.user_id,
            metadata={"compared_count": len(request.build_ids)},
        ),
    )
    return response


@router.get("/users/{user_id}/watchlist", response_model=WatchlistResponse)
def user_watchlist(
    user_id: str,
    region: str = "SA",
    repository: Neo4jUserBuildRepository = Depends(get_user_build_repository),
    pricing_repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> WatchlistResponse:
    resolved_region = resolve_market_region(region)
    return WatchlistResponse(
        items=_service(repository, pricing_repository).list_watchlist(user_id=user_id, guest_id=None, region=resolved_region)
    )


@router.get("/guests/{guest_id}/watchlist", response_model=WatchlistResponse)
def guest_watchlist(
    guest_id: str,
    region: str = "SA",
    repository: Neo4jUserBuildRepository = Depends(get_user_build_repository),
    pricing_repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> WatchlistResponse:
    resolved_region = resolve_market_region(region)
    return WatchlistResponse(
        items=_service(repository, pricing_repository).list_watchlist(user_id=None, guest_id=guest_id, region=resolved_region)
    )


@router.post("/users/{user_id}/watchlist", response_model=WatchlistResponse)
def add_user_watchlist_item(
    user_id: str,
    request: WatchlistAddRequest,
    fastapi_request: Request,
    repository: Neo4jUserBuildRepository = Depends(get_user_build_repository),
    pricing_repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> WatchlistResponse:
    resolve_market_region(request.region)
    service = _service(repository, pricing_repository)
    service.add_watchlist_item(user_id=user_id, guest_id=None, request=request)
    _record_event(
        fastapi_request,
        AnalyticsEventCreate(event_type="watchlist_add", region=request.region, user_id=user_id, metadata={"product": "tracked"}),
    )
    return WatchlistResponse(items=service.list_watchlist(user_id=user_id, guest_id=None, region=request.region))


@router.post("/guests/{guest_id}/watchlist", response_model=WatchlistResponse)
def add_guest_watchlist_item(
    guest_id: str,
    request: WatchlistAddRequest,
    fastapi_request: Request,
    repository: Neo4jUserBuildRepository = Depends(get_user_build_repository),
    pricing_repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> WatchlistResponse:
    resolve_market_region(request.region)
    service = _service(repository, pricing_repository)
    service.add_watchlist_item(user_id=None, guest_id=guest_id, request=request)
    _record_event(
        fastapi_request,
        AnalyticsEventCreate(
            event_type="watchlist_add",
            region=request.region,
            anonymous_session_id=guest_id,
            metadata={"product": "tracked"},
        ),
    )
    return WatchlistResponse(items=service.list_watchlist(user_id=None, guest_id=guest_id, region=request.region))


@router.delete("/users/{user_id}/watchlist/{item_id}")
def delete_user_watchlist_item(
    user_id: str,
    item_id: str,
    repository: Neo4jUserBuildRepository = Depends(get_user_build_repository),
) -> dict[str, bool]:
    return {"deleted": _service(repository).delete_watchlist_item(item_id, user_id=user_id, guest_id=None)}


@router.delete("/guests/{guest_id}/watchlist/{item_id}")
def delete_guest_watchlist_item(
    guest_id: str,
    item_id: str,
    repository: Neo4jUserBuildRepository = Depends(get_user_build_repository),
) -> dict[str, bool]:
    return {"deleted": _service(repository).delete_watchlist_item(item_id, user_id=None, guest_id=guest_id)}


def _record_event(request: Request, event: AnalyticsEventCreate) -> None:
    store = getattr(request.app.state, "launch_analytics", None)
    if store:
        record_launch_event(request.app.state, event)


def _optional_budget(summary: dict) -> float | None:
    value = summary.get("budget_sar") if isinstance(summary, dict) else None
    return float(value) if isinstance(value, (int, float)) else None
