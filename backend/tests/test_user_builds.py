from __future__ import annotations

from app.models.user_builds import (
    BuildComparisonRequest,
    SavedBuildCreateRequest,
    SavedBuildUpdateRequest,
    UserAccountCreateRequest,
    WatchlistAddRequest,
)
from app.services.user_builds import UserBuildService


class FakeUserBuildRepository:
    def __init__(self) -> None:
        self.users = {}
        self.builds = {}
        self.watchlist = {}
        self.comparisons = []

    def upsert_user(self, request):
        user = {
            "user_id": "user-1",
            "email": request.email.lower(),
            "display_name": request.display_name,
            "region": request.region,
            "created_at": "2026-05-12T00:00:00Z",
            "last_active_at": "2026-05-12T00:00:00Z",
        }
        self.users[user["user_id"]] = user
        return user

    def save_build(self, request):
        build_id = f"build-{len(self.builds) + 1}"
        build = {
            "build_id": build_id,
            "user_id": request.user_id,
            "guest_id": request.guest_id,
            "title": request.title or request.build_mode,
            "region": request.region,
            "created_at": "2026-05-12T00:00:00Z",
            "updated_at": "2026-05-12T00:00:00Z",
            "build_mode": request.build_mode,
            "total_price_sar": request.total_price_sar,
            "confidence_level": request.confidence_level,
            "warning_summary": request.warning_summary,
            "component_ids": request.component_ids,
            "price_snapshot_ids": request.price_snapshot_ids,
            "build_summary": request.build_summary,
            "build_payload": request.build_payload,
            "share_slug": f"share-{len(self.builds) + 1}",
            "public_visibility": request.public_visibility,
            "favorite": request.favorite,
        }
        self.builds[build_id] = build
        return build

    def list_builds(self, *, user_id, guest_id, limit=20):
        return [
            build
            for build in self.builds.values()
            if (user_id and build["user_id"] == user_id) or (guest_id and build["guest_id"] == guest_id)
        ][:limit]

    def get_build(self, build_id):
        return self.builds.get(build_id)

    def get_shared_build(self, share_slug):
        for build in self.builds.values():
            if build["share_slug"] == share_slug and build["public_visibility"]:
                return build
        return None

    def update_build(self, build_id, request):
        build = self.builds.get(build_id)
        if not build:
            return None
        if request.title is not None:
            build["title"] = request.title
        if request.public_visibility is not None:
            build["public_visibility"] = request.public_visibility
        if request.favorite is not None:
            build["favorite"] = request.favorite
        return build

    def delete_build(self, build_id):
        return self.builds.pop(build_id, None) is not None

    def create_comparison(self, build_ids, user_id, guest_id):
        self.comparisons.append((build_ids, user_id, guest_id))
        return "comparison-1"

    def add_watchlist_item(self, *, user_id, guest_id, request, product_name, vendor, current_price_sar):
        item = {
            "item_id": "watch-1",
            "user_id": user_id,
            "guest_id": guest_id,
            "product_id": request.product_id,
            "product_name": product_name,
            "region": request.region,
            "vendor": vendor,
            "target_price_sar": request.target_price_sar,
            "last_seen_price": current_price_sar,
            "current_price_sar": current_price_sar,
            "last_price_change": 0,
            "created_at": "2026-05-12T00:00:00Z",
            "updated_at": "2026-05-12T00:00:00Z",
            "status": "tracking",
        }
        self.watchlist[item["item_id"]] = item
        return item

    def list_watchlist(self, *, user_id, guest_id, region="SA"):
        return list(self.watchlist.values())

    def delete_watchlist_item(self, item_id, user_id, guest_id):
        return self.watchlist.pop(item_id, None) is not None


class FakeProductDetail:
    name = "RTX 4070 Super"
    current_recommended_vendor = "PCZone Saudi"
    current_recommended_price = 2799.0
    current_best_price = 2799.0
    lowest_market_price = 2799.0


class FakePricingRepository:
    def product_detail(self, product_id, region=None):
        return FakeProductDetail()


def _sample_saved_build_request(**overrides):
    payload = {
        "label": "recommended_saudi_build",
        "components": [
            {"product_id": "cpu-1", "category": "CPU", "name": "Ryzen 7 7800X3D"},
            {"product_id": "gpu-1", "category": "GPU", "name": "RTX 4070 Super"},
        ],
        "summary": {
            "warning_summary": ["Storage warranty unclear"],
            "risk_summary": ["RAM VAT unclear"],
            "budget_status": "over_budget",
        },
        "explanation": {"upgrade_path": ["AM5 keeps a reasonable future CPU path."]},
        "audit_trace_id": "secret-trace",
    }
    request = {
        "user_id": "user-1",
        "title": "1440p Saudi Build",
        "region": "SA",
        "build_mode": "recommended_saudi_build",
        "total_price_sar": 6400,
        "confidence_level": "medium",
        "build_summary": payload["summary"],
        "build_payload": payload,
        "public_visibility": True,
    }
    request.update(overrides)
    return SavedBuildCreateRequest(**request)


def test_user_can_save_load_rename_duplicate_and_delete_build() -> None:
    service = UserBuildService(FakeUserBuildRepository())
    user = service.create_user(UserAccountCreateRequest(email="Buyer@Example.com", display_name="Buyer"))

    saved = service.save_build(_sample_saved_build_request(user_id=user.user_id))
    assert saved.component_ids == ["cpu-1", "gpu-1"]
    assert "Storage warranty unclear" in saved.warning_summary
    assert "audit_trace_id" not in saved.build_payload

    renamed = service.update_build(saved.build_id, SavedBuildUpdateRequest(title="Updated Build"))
    assert renamed is not None
    assert renamed.title == "Updated Build"

    duplicate = service.duplicate_build(saved.build_id, user_id=user.user_id, guest_id=None)
    assert duplicate is not None
    assert duplicate.build_id != saved.build_id

    assert service.delete_build(saved.build_id) is True


def test_public_share_link_hides_owner_and_snapshot_ids() -> None:
    service = UserBuildService(FakeUserBuildRepository())
    saved = service.save_build(_sample_saved_build_request(price_snapshot_ids=["snapshot-1"]))

    shared = service.get_shared_build(saved.share_slug)
    assert shared is not None
    assert shared.user_id is None
    assert shared.guest_id is None
    assert shared.component_ids == []
    assert shared.price_snapshot_ids == []
    assert shared.build_payload["components"][0]["product_id"] == "public-cpu"
    assert "audit_trace_id" not in shared.build_payload


def test_build_comparison_highlights_cheapest_and_safest() -> None:
    service = UserBuildService(FakeUserBuildRepository())
    first = service.save_build(_sample_saved_build_request(total_price_sar=6400, warning_summary=["VAT unclear"]))
    second = service.save_build(_sample_saved_build_request(total_price_sar=5900, warning_summary=[]))

    comparison = service.compare_builds(BuildComparisonRequest(build_ids=[first.build_id, second.build_id], user_id="user-1"))

    assert comparison.comparison_id == "comparison-1"
    assert any(item.cheapest for item in comparison.compared_builds)
    assert any(item.safest for item in comparison.compared_builds)
    assert comparison.highlights


def test_watchlist_tracks_current_saudi_price_and_target_status() -> None:
    service = UserBuildService(FakeUserBuildRepository(), FakePricingRepository())

    item = service.add_watchlist_item(
        user_id="user-1",
        guest_id=None,
        request=WatchlistAddRequest(product_id="gpu-1", target_price_sar=2800, region="SA"),
    )

    assert item.current_price_sar == 2799
    assert item.vendor == "PCZone Saudi"
    assert item.status == "target_met"
