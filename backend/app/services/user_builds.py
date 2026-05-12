from __future__ import annotations

from typing import Any

from app.models.user_builds import (
    BuildComparisonMetric,
    BuildComparisonRequest,
    BuildComparisonResponse,
    SavedBuildCreateRequest,
    SavedBuildUpdateRequest,
    SavedBuildView,
    UserAccountCreateRequest,
    UserAccountView,
    WatchlistAddRequest,
    WatchlistItemView,
)


class UserBuildService:
    def __init__(self, repository, pricing_repository=None) -> None:
        self.repository = repository
        self.pricing_repository = pricing_repository

    def create_user(self, request: UserAccountCreateRequest) -> UserAccountView:
        return UserAccountView(**self.repository.upsert_user(request))

    def save_build(self, request: SavedBuildCreateRequest) -> SavedBuildView:
        normalized = request.model_copy(
            update={
                "component_ids": _component_ids(request),
                "price_snapshot_ids": _price_snapshot_ids(request),
                "warning_summary": _warning_summary(request),
                "build_payload": _sanitize_public_payload(request.build_payload),
            }
        )
        return SavedBuildView(**self.repository.save_build(normalized))

    def list_builds(self, *, user_id: str | None, guest_id: str | None, limit: int = 20) -> list[SavedBuildView]:
        return [SavedBuildView(**item) for item in self.repository.list_builds(user_id=user_id, guest_id=guest_id, limit=limit)]

    def get_build(self, build_id: str) -> SavedBuildView | None:
        data = self.repository.get_build(build_id)
        return SavedBuildView(**data) if data else None

    def get_shared_build(self, share_slug: str) -> SavedBuildView | None:
        data = self.repository.get_shared_build(share_slug)
        if not data:
            return None
        data = _sanitize_saved_build_for_public(data)
        return SavedBuildView(**data)

    def update_build(self, build_id: str, request: SavedBuildUpdateRequest) -> SavedBuildView | None:
        data = self.repository.update_build(build_id, request)
        return SavedBuildView(**data) if data else None

    def duplicate_build(self, build_id: str, *, user_id: str | None, guest_id: str | None) -> SavedBuildView | None:
        original = self.get_build(build_id)
        if not original:
            return None
        duplicate_request = SavedBuildCreateRequest(
            user_id=user_id or original.user_id,
            guest_id=guest_id or original.guest_id,
            title=f"{original.title} Copy",
            region=original.region,
            build_mode=original.build_mode,
            total_price_sar=original.total_price_sar,
            confidence_level=original.confidence_level,
            warning_summary=original.warning_summary,
            component_ids=original.component_ids,
            price_snapshot_ids=original.price_snapshot_ids,
            build_summary=original.build_summary,
            build_payload=original.build_payload,
            public_visibility=original.public_visibility,
            favorite=False,
        )
        return self.save_build(duplicate_request)

    def delete_build(self, build_id: str) -> bool:
        return self.repository.delete_build(build_id)

    def compare_builds(self, request: BuildComparisonRequest) -> BuildComparisonResponse:
        builds = [self.get_build(build_id) for build_id in request.build_ids]
        visible_builds = [build for build in builds if build is not None]
        comparison_id = self.repository.create_comparison(
            [build.build_id for build in visible_builds],
            request.user_id,
            request.guest_id,
        )
        metrics = _comparison_metrics(visible_builds)
        return BuildComparisonResponse(
            comparison_id=comparison_id,
            compared_builds=metrics,
            highlights=_comparison_highlights(metrics),
        )

    def add_watchlist_item(
        self,
        *,
        user_id: str | None,
        guest_id: str | None,
        request: WatchlistAddRequest,
    ) -> WatchlistItemView:
        detail = self.pricing_repository.product_detail(request.product_id, region=request.region) if self.pricing_repository else None
        current_price = _current_sa_price(detail)
        vendor = getattr(detail, "current_recommended_vendor", None) if detail else None
        data = self.repository.add_watchlist_item(
            user_id=user_id,
            guest_id=guest_id,
            request=request,
            product_name=getattr(detail, "name", None) if detail else None,
            vendor=vendor,
            current_price_sar=current_price,
        )
        return _watchlist_view(data)

    def list_watchlist(self, *, user_id: str | None, guest_id: str | None, region: str = "SA") -> list[WatchlistItemView]:
        items = [_watchlist_view(item) for item in self.repository.list_watchlist(user_id=user_id, guest_id=guest_id, region=region)]
        if not self.pricing_repository:
            return items
        updated: list[WatchlistItemView] = []
        for item in items:
            detail = self.pricing_repository.product_detail(item.product_id, region=item.region)
            current_price = _current_sa_price(detail)
            if current_price is None:
                updated.append(item)
                continue
            updated.append(
                item.model_copy(
                    update={
                        "product_name": item.product_name or getattr(detail, "name", None),
                        "vendor": getattr(detail, "current_recommended_vendor", None) or item.vendor,
                        "current_price_sar": current_price,
                        "last_price_change": None if item.last_seen_price is None else current_price - item.last_seen_price,
                        "status": "target_met"
                        if item.target_price_sar is not None and current_price <= item.target_price_sar
                        else "tracking",
                    }
                )
            )
        return updated

    def delete_watchlist_item(self, item_id: str, *, user_id: str | None, guest_id: str | None) -> bool:
        return self.repository.delete_watchlist_item(item_id, user_id, guest_id)


def _component_ids(request: SavedBuildCreateRequest) -> list[str]:
    if request.component_ids:
        return list(dict.fromkeys(request.component_ids))
    components = request.build_payload.get("components")
    if not isinstance(components, list):
        return []
    return list(dict.fromkeys(str(component.get("product_id")) for component in components if isinstance(component, dict) and component.get("product_id")))


def _price_snapshot_ids(request: SavedBuildCreateRequest) -> list[str]:
    if request.price_snapshot_ids:
        return list(dict.fromkeys(request.price_snapshot_ids))
    components = request.build_payload.get("components")
    if not isinstance(components, list):
        return []
    ids: list[str] = []
    for component in components:
        if not isinstance(component, dict):
            continue
        snapshot_id = component.get("price_snapshot_id") or component.get("recommended_price_snapshot_id")
        if snapshot_id:
            ids.append(str(snapshot_id))
    return list(dict.fromkeys(ids))


def _warning_summary(request: SavedBuildCreateRequest) -> list[str]:
    warnings = list(request.warning_summary)
    summary = request.build_payload.get("summary")
    if isinstance(summary, dict):
        warnings.extend(str(item) for item in summary.get("warning_summary", []) if item)
        warnings.extend(str(item) for item in summary.get("missing_data_warnings", []) if item)
    return list(dict.fromkeys(warnings))[:20]


def _sanitize_public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _strip_public_fields(dict(payload or {}), public_share=False)


def _sanitize_saved_build_for_public(data: dict[str, Any]) -> dict[str, Any]:
    clean = dict(data)
    clean["user_id"] = None
    clean["guest_id"] = None
    clean["component_ids"] = []
    clean["price_snapshot_ids"] = []
    clean["build_payload"] = _strip_public_fields(clean.get("build_payload") or {}, public_share=True)
    return clean


def _strip_public_fields(value: Any, *, public_share: bool) -> Any:
    blocked_keys = {
        "audit_trace_id",
        "internal_audit_ids",
        "audit_event_id",
        "trace_id",
        "api_key",
        "secret",
        "user_email",
        "email",
        "price_snapshot_id",
        "recommended_price_snapshot_id",
    }
    if isinstance(value, list):
        return [_strip_public_fields(item, public_share=public_share) for item in value]
    if not isinstance(value, dict):
        return value
    clean: dict[str, Any] = {}
    for key, item in value.items():
        if key in blocked_keys:
            continue
        if public_share and key == "product_id":
            clean[key] = f"public-{str(value.get('category') or 'component').lower().replace(' ', '-')}"
            continue
        if public_share and key == "build_id":
            clean[key] = "shared-build"
            continue
        clean[key] = _strip_public_fields(item, public_share=public_share)
    return clean


def _comparison_metrics(builds: list[SavedBuildView]) -> list[BuildComparisonMetric]:
    priced = [build.total_price_sar for build in builds if build.total_price_sar is not None]
    cheapest_price = min(priced) if priced else None
    fewest_warnings = min((len(build.warning_summary) for build in builds), default=0)
    best_confidence = max((_confidence_rank(build.confidence_level) for build in builds), default=0)
    metrics: list[BuildComparisonMetric] = []
    for build in builds:
        summary = build.build_summary or {}
        explanation = build.build_payload.get("explanation") if isinstance(build.build_payload, dict) else {}
        metrics.append(
            BuildComparisonMetric(
                build_id=build.build_id,
                title=build.title,
                total_price_sar=build.total_price_sar,
                confidence_level=build.confidence_level,
                warning_count=len(build.warning_summary),
                budget_status=summary.get("budget_status") if isinstance(summary, dict) else None,
                risk_summary=list(summary.get("risk_summary", [])) if isinstance(summary, dict) else [],
                upgrade_path=list(explanation.get("upgrade_path", [])) if isinstance(explanation, dict) else [],
                cheapest=build.total_price_sar == cheapest_price if cheapest_price is not None else False,
                safest=len(build.warning_summary) == fewest_warnings,
                strongest=_confidence_rank(build.confidence_level) == best_confidence,
                more_upgradeable=bool(isinstance(explanation, dict) and explanation.get("upgrade_path")),
            )
        )
    return metrics


def _comparison_highlights(metrics: list[BuildComparisonMetric]) -> list[str]:
    highlights: list[str] = []
    cheapest = next((item for item in metrics if item.cheapest), None)
    safest = next((item for item in metrics if item.safest), None)
    if cheapest:
        highlights.append(f"{cheapest.title} is the cheapest saved option.")
    if safest:
        highlights.append(f"{safest.title} has the fewest visible warnings.")
    if not highlights:
        highlights.append("Saved builds are close enough that component-level warnings should decide.")
    return highlights


def _confidence_rank(value: str) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(value, 0)


def _current_sa_price(detail: Any) -> float | None:
    if detail is None:
        return None
    for attr in ("current_recommended_price", "current_best_price", "lowest_market_price"):
        value = getattr(detail, attr, None)
        if value is not None:
            return float(value)
    return None


def _watchlist_view(data: dict[str, Any]) -> WatchlistItemView:
    item = WatchlistItemView(**data)
    if item.current_price_sar is None:
        return item.model_copy(update={"status": "price_unavailable"})
    if item.target_price_sar is not None and item.current_price_sar <= item.target_price_sar:
        return item.model_copy(update={"status": "target_met"})
    return item.model_copy(update={"status": "tracking"})
