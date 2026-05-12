from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.models.user_builds import (
    SavedBuildCreateRequest,
    SavedBuildUpdateRequest,
    UserAccountCreateRequest,
    WatchlistAddRequest,
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _list_json(value: list[Any] | None) -> str:
    return _json(value or [])


def _safe_json_load(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


class Neo4jUserBuildRepository:
    def __init__(self, driver) -> None:
        self.driver = driver

    def apply_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (n:User) REQUIRE n.user_id IS UNIQUE",
            "CREATE CONSTRAINT saved_build_id IF NOT EXISTS FOR (n:SavedBuild) REQUIRE n.build_id IS UNIQUE",
            "CREATE CONSTRAINT saved_build_share_slug IF NOT EXISTS FOR (n:SavedBuild) REQUIRE n.share_slug IS UNIQUE",
            "CREATE CONSTRAINT watchlist_item_id IF NOT EXISTS FOR (n:WatchlistItem) REQUIRE n.item_id IS UNIQUE",
            "CREATE CONSTRAINT build_comparison_id IF NOT EXISTS FOR (n:BuildComparison) REQUIRE n.comparison_id IS UNIQUE",
            "CREATE INDEX saved_build_user IF NOT EXISTS FOR (n:SavedBuild) ON (n.user_id)",
            "CREATE INDEX saved_build_guest IF NOT EXISTS FOR (n:SavedBuild) ON (n.guest_id)",
            "CREATE INDEX watchlist_user IF NOT EXISTS FOR (n:WatchlistItem) ON (n.user_id)",
            "CREATE INDEX watchlist_guest IF NOT EXISTS FOR (n:WatchlistItem) ON (n.guest_id)",
        ]
        for statement in statements:
            self.driver.execute_query(statement, database_=settings.neo4j_database)

    def upsert_user(self, request: UserAccountCreateRequest) -> dict[str, Any]:
        user_id = f"user-{uuid4()}"
        records, _, _ = self.driver.execute_query(
            """
            MERGE (user:User {email: toLower($email)})
            ON CREATE SET user.user_id = $user_id,
                          user.created_at = datetime()
            SET user.display_name = $display_name,
                user.region = $region,
                user.last_active_at = datetime()
            RETURN user.user_id AS user_id,
                   user.email AS email,
                   user.display_name AS display_name,
                   user.region AS region,
                   toString(user.created_at) AS created_at,
                   toString(user.last_active_at) AS last_active_at
            """,
            user_id=user_id,
            email=request.email.strip().lower(),
            display_name=request.display_name,
            region=request.region.upper(),
            database_=settings.neo4j_database,
        )
        return records[0].data()

    def save_build(self, request: SavedBuildCreateRequest) -> dict[str, Any]:
        build_id = f"build-{uuid4()}"
        share_slug = uuid4().hex[:10]
        title = request.title or _default_build_title(request.build_mode)
        records, _, _ = self.driver.execute_query(
            """
            CREATE (build:SavedBuild {
              build_id: $build_id,
              share_slug: $share_slug,
              user_id: $user_id,
              guest_id: $guest_id,
              title: $title,
              region: $region,
              build_mode: $build_mode,
              total_price_sar: $total_price_sar,
              confidence_level: $confidence_level,
              warning_summary_json: $warning_summary_json,
              component_ids_json: $component_ids_json,
              price_snapshot_ids_json: $price_snapshot_ids_json,
              build_summary_json: $build_summary_json,
              build_payload_json: $build_payload_json,
              public_visibility: $public_visibility,
              favorite: $favorite,
              created_at: datetime(),
              updated_at: datetime()
            })
            WITH build
            OPTIONAL MATCH (user:User {user_id: $user_id})
            FOREACH (_ IN CASE WHEN user IS NULL THEN [] ELSE [1] END |
              MERGE (user)-[:SAVED]->(build)
            )
            RETURN build
            """,
            build_id=build_id,
            share_slug=share_slug,
            user_id=request.user_id,
            guest_id=request.guest_id,
            title=title,
            region=request.region.upper(),
            build_mode=request.build_mode,
            total_price_sar=request.total_price_sar,
            confidence_level=request.confidence_level,
            warning_summary_json=_list_json(request.warning_summary),
            component_ids_json=_list_json(request.component_ids),
            price_snapshot_ids_json=_list_json(request.price_snapshot_ids),
            build_summary_json=_json(request.build_summary),
            build_payload_json=_json(_sanitize_build_payload(request.build_payload)),
            public_visibility=request.public_visibility,
            favorite=request.favorite,
            database_=settings.neo4j_database,
        )
        if request.component_ids:
            self.driver.execute_query(
                """
                MATCH (build:SavedBuild {build_id: $build_id})
                UNWIND $component_ids AS component_id
                MATCH (product:Product {id: component_id})
                MERGE (build)-[:USES_PRODUCT]->(product)
                """,
                build_id=build_id,
                component_ids=request.component_ids,
                database_=settings.neo4j_database,
            )
        if request.price_snapshot_ids:
            self.driver.execute_query(
                """
                MATCH (build:SavedBuild {build_id: $build_id})
                UNWIND $price_snapshot_ids AS snapshot_id
                MATCH (snapshot:PriceSnapshot {id: snapshot_id})
                MERGE (build)-[:USES_SNAPSHOT]->(snapshot)
                """,
                build_id=build_id,
                price_snapshot_ids=request.price_snapshot_ids,
                database_=settings.neo4j_database,
            )
        return _saved_build_record(records[0]["build"])

    def list_builds(self, *, user_id: str | None, guest_id: str | None, limit: int = 20) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (build:SavedBuild)
            WHERE ($user_id IS NOT NULL AND build.user_id = $user_id)
               OR ($guest_id IS NOT NULL AND build.guest_id = $guest_id)
            RETURN build
            ORDER BY build.updated_at DESC
            LIMIT $limit
            """,
            user_id=user_id,
            guest_id=guest_id,
            limit=limit,
            database_=settings.neo4j_database,
        )
        return [_saved_build_record(record["build"]) for record in records]

    def get_build(self, build_id: str) -> dict[str, Any] | None:
        records, _, _ = self.driver.execute_query(
            "MATCH (build:SavedBuild {build_id: $build_id}) RETURN build LIMIT 1",
            build_id=build_id,
            database_=settings.neo4j_database,
        )
        return _saved_build_record(records[0]["build"]) if records else None

    def get_shared_build(self, share_slug: str) -> dict[str, Any] | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (build:SavedBuild {share_slug: $share_slug})
            WHERE build.public_visibility = true
            RETURN build
            LIMIT 1
            """,
            share_slug=share_slug,
            database_=settings.neo4j_database,
        )
        return _saved_build_record(records[0]["build"]) if records else None

    def update_build(self, build_id: str, request: SavedBuildUpdateRequest) -> dict[str, Any] | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (build:SavedBuild {build_id: $build_id})
            SET build.title = coalesce($title, build.title),
                build.public_visibility = coalesce($public_visibility, build.public_visibility),
                build.favorite = coalesce($favorite, build.favorite),
                build.updated_at = datetime()
            RETURN build
            """,
            build_id=build_id,
            title=request.title,
            public_visibility=request.public_visibility,
            favorite=request.favorite,
            database_=settings.neo4j_database,
        )
        return _saved_build_record(records[0]["build"]) if records else None

    def delete_build(self, build_id: str) -> bool:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (build:SavedBuild {build_id: $build_id})
            DETACH DELETE build
            RETURN count(build) AS deleted
            """,
            build_id=build_id,
            database_=settings.neo4j_database,
        )
        return bool(records and records[0]["deleted"])

    def create_comparison(self, build_ids: list[str], user_id: str | None, guest_id: str | None) -> str:
        comparison_id = f"comparison-{uuid4()}"
        self.driver.execute_query(
            """
            CREATE (comparison:BuildComparison {
              comparison_id: $comparison_id,
              user_id: $user_id,
              guest_id: $guest_id,
              build_ids_json: $build_ids_json,
              created_at: datetime()
            })
            WITH comparison
            UNWIND $build_ids AS build_id
            MATCH (build:SavedBuild {build_id: build_id})
            MERGE (comparison)-[:COMPARES]->(build)
            """,
            comparison_id=comparison_id,
            user_id=user_id,
            guest_id=guest_id,
            build_ids=build_ids,
            build_ids_json=_list_json(build_ids),
            database_=settings.neo4j_database,
        )
        return comparison_id

    def add_watchlist_item(
        self,
        *,
        user_id: str | None,
        guest_id: str | None,
        request: WatchlistAddRequest,
        product_name: str | None,
        vendor: str | None,
        current_price_sar: float | None,
    ) -> dict[str, Any]:
        item_id = f"watch-{uuid4()}"
        records, _, _ = self.driver.execute_query(
            """
            CREATE (item:WatchlistItem {
              item_id: $item_id,
              user_id: $user_id,
              guest_id: $guest_id,
              product_id: $product_id,
              region: $region,
              created_at: datetime()
            })
            SET item.target_price_sar = $target_price_sar,
                item.product_name = $product_name,
                item.vendor = $vendor,
                item.last_seen_price = coalesce(item.current_price_sar, $current_price_sar),
                item.current_price_sar = $current_price_sar,
                item.last_price_change = CASE
                  WHEN item.last_seen_price IS NULL OR $current_price_sar IS NULL THEN null
                  ELSE $current_price_sar - item.last_seen_price
                END,
                item.updated_at = datetime()
            WITH item
            OPTIONAL MATCH (user:User {user_id: $user_id})
            FOREACH (_ IN CASE WHEN user IS NULL THEN [] ELSE [1] END |
              MERGE (user)-[:WATCHES]->(item)
            )
            WITH item
            OPTIONAL MATCH (product:Product {id: $product_id})
            FOREACH (_ IN CASE WHEN product IS NULL THEN [] ELSE [1] END |
              MERGE (item)-[:WATCHES_PRODUCT]->(product)
            )
            RETURN item
            """,
            item_id=item_id,
            user_id=user_id,
            guest_id=guest_id,
            product_id=request.product_id,
            region=request.region.upper(),
            target_price_sar=request.target_price_sar,
            product_name=product_name,
            vendor=vendor,
            current_price_sar=current_price_sar,
            database_=settings.neo4j_database,
        )
        return _watchlist_record(records[0]["item"])

    def list_watchlist(self, *, user_id: str | None, guest_id: str | None, region: str = "SA") -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (item:WatchlistItem)
            WHERE item.region = $region
              AND (($user_id IS NOT NULL AND item.user_id = $user_id)
                OR ($guest_id IS NOT NULL AND item.guest_id = $guest_id))
            RETURN item
            ORDER BY item.updated_at DESC
            """,
            user_id=user_id,
            guest_id=guest_id,
            region=region.upper(),
            database_=settings.neo4j_database,
        )
        return [_watchlist_record(record["item"]) for record in records]

    def delete_watchlist_item(self, item_id: str, user_id: str | None, guest_id: str | None) -> bool:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (item:WatchlistItem {item_id: $item_id})
            WHERE ($user_id IS NOT NULL AND item.user_id = $user_id)
               OR ($guest_id IS NOT NULL AND item.guest_id = $guest_id)
            DETACH DELETE item
            RETURN count(item) AS deleted
            """,
            item_id=item_id,
            user_id=user_id,
            guest_id=guest_id,
            database_=settings.neo4j_database,
        )
        return bool(records and records[0]["deleted"])


def _default_build_title(build_mode: str) -> str:
    return build_mode.replace("_", " ").title()


def _sanitize_build_payload(payload: dict[str, Any]) -> dict[str, Any]:
    clean = dict(payload or {})
    clean.pop("audit_trace_id", None)
    clean.pop("internal_audit_ids", None)
    return clean


def _saved_build_record(node: Any) -> dict[str, Any]:
    data = dict(node)
    return {
        "build_id": data.get("build_id"),
        "user_id": data.get("user_id"),
        "guest_id": data.get("guest_id"),
        "title": data.get("title") or "Saved Build",
        "region": data.get("region") or "SA",
        "created_at": str(data.get("created_at")) if data.get("created_at") is not None else None,
        "updated_at": str(data.get("updated_at")) if data.get("updated_at") is not None else None,
        "build_mode": data.get("build_mode") or "recommended_saudi_build",
        "total_price_sar": data.get("total_price_sar"),
        "confidence_level": data.get("confidence_level") or "low",
        "warning_summary": _safe_json_load(data.get("warning_summary_json"), []),
        "component_ids": _safe_json_load(data.get("component_ids_json"), []),
        "price_snapshot_ids": _safe_json_load(data.get("price_snapshot_ids_json"), []),
        "build_summary": _safe_json_load(data.get("build_summary_json"), {}),
        "build_payload": _safe_json_load(data.get("build_payload_json"), {}),
        "share_slug": data.get("share_slug"),
        "public_visibility": bool(data.get("public_visibility")),
        "favorite": bool(data.get("favorite")),
    }


def _watchlist_record(node: Any) -> dict[str, Any]:
    data = dict(node)
    current_price = data.get("current_price_sar")
    target = data.get("target_price_sar")
    status = "price_unavailable" if current_price is None else "tracking"
    if current_price is not None and target is not None and current_price <= target:
        status = "target_met"
    return {
        "item_id": data.get("item_id"),
        "user_id": data.get("user_id"),
        "guest_id": data.get("guest_id"),
        "product_id": data.get("product_id"),
        "product_name": data.get("product_name"),
        "region": data.get("region") or "SA",
        "vendor": data.get("vendor"),
        "target_price_sar": data.get("target_price_sar"),
        "last_seen_price": data.get("last_seen_price"),
        "current_price_sar": current_price,
        "last_price_change": data.get("last_price_change"),
        "status": status,
        "created_at": str(data.get("created_at")) if data.get("created_at") is not None else None,
        "updated_at": str(data.get("updated_at")) if data.get("updated_at") is not None else None,
    }
