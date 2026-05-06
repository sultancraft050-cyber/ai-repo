from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any
from uuid import uuid4

from neo4j import Driver

from app.core.config import settings
from app.models.pricing import (
    FieldEvidence,
    PriceHistoryPoint,
    PriceOffer,
    PriceSnapshotView,
    PricingJob,
    ProductDetail,
    ProductIdentity,
    ProductSearchResult,
    SourceTier,
    SourceType,
)
from app.models.intelligence import HardwareIntelligence
from app.services.hardware_taxonomy import GLOBAL_HARDWARE_CATEGORIES


def _clean_properties(values: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool, datetime)):
            clean[key] = value
        elif isinstance(value, list) and all(isinstance(item, (str, int, float, bool)) for item in value):
            clean[key] = value
        else:
            clean[key] = json.dumps(value, sort_keys=True)
    return clean


def _product_properties(identity: ProductIdentity) -> dict[str, Any]:
    props = {
        "name": identity.name,
        "brand": identity.brand,
        "category": identity.category,
        "model": identity.model,
        "normalized_model": identity.normalized_model,
        "canonical_key": identity.canonical_key,
        "msrp": identity.msrp,
        "imageUrl": identity.image_url,
        "updated_at": datetime.now(UTC),
    }
    for key, value in identity.specs.items():
        props[f"spec_{key}"] = value
    return _clean_properties(props)


def _evidence_payload(evidence: FieldEvidence) -> dict[str, Any]:
    return _clean_properties(
        {
            "field": evidence.field,
            "value_json": json.dumps(evidence.value, sort_keys=True),
            "source": evidence.source,
            "timestamp": evidence.timestamp,
            "trust_score": evidence.trust_score,
            "freshness_score": evidence.freshness_score,
            "source_tier": int(evidence.source_tier),
        }
    )


def _snapshot_view(data: dict[str, Any]) -> PriceSnapshotView:
    return PriceSnapshotView(
        id=data["id"],
        vendor_id=data["vendor_id"],
        vendor_name=data["vendor_name"],
        price=float(data["price"]),
        currency=data["currency"],
        availability=data["availability"],
        timestamp=data["timestamp"],
        shipping_cost=float(data.get("shipping_cost") or 0),
        product_url=data.get("product_url"),
        source=data["source"],
        source_type=SourceType(data["source_type"]),
        source_tier=SourceTier(int(data["source_tier"])),
        trust_score=float(data["trust_score"]),
        freshness_score=float(data["freshness_score"]),
        stale=bool(data.get("stale", False)),
        flags=list(data.get("flags") or []),
    )


def _search_result(data: dict[str, Any]) -> ProductSearchResult:
    current = data.get("current_best_price")
    previous = data.get("previous_price")
    drop = None
    if current and previous and previous > 0 and current < previous:
        drop = round((previous - current) / previous * 100, 2)
    return ProductSearchResult(
        id=data["id"],
        canonical_key=data.get("canonical_key"),
        name=data["name"],
        brand=data.get("brand"),
        category=data["category"],
        model=data.get("model"),
        image_url=data.get("image_url"),
        current_best_price=float(current) if current is not None else None,
        current_best_currency=data.get("current_best_currency"),
        current_best_vendor=data.get("current_best_vendor"),
        current_price_freshness_score=data.get("current_price_freshness_score"),
        current_price_trust_score=data.get("current_price_trust_score"),
        current_price_timestamp=data.get("current_price_timestamp"),
        stale=bool(data.get("stale", False)),
        best_value=bool(data.get("best_value", False)),
        price_drop_percent=drop,
    )


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _intelligence_from_record(data: dict[str, Any]) -> HardwareIntelligence:
    return HardwareIntelligence.model_validate_json(data["payload_json"])


class Neo4jPricingRepository:
    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    def apply_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT product_canonical_key IF NOT EXISTS "
            "FOR (n:Product) REQUIRE n.canonical_key IS UNIQUE",
            "CREATE CONSTRAINT vendor_id IF NOT EXISTS FOR (n:Vendor) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT price_snapshot_id IF NOT EXISTS "
            "FOR (n:PriceSnapshot) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT pricing_job_id IF NOT EXISTS "
            "FOR (n:PricingJob) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT hardware_intelligence_id IF NOT EXISTS "
            "FOR (n:HardwareIntelligence) REQUIRE n.id IS UNIQUE",
            "CREATE INDEX product_name IF NOT EXISTS FOR (n:Product) ON (n.name)",
            "CREATE INDEX product_category IF NOT EXISTS FOR (n:Product) ON (n.category)",
            "CREATE INDEX product_current_price_timestamp IF NOT EXISTS "
            "FOR (n:Product) ON (n.current_price_timestamp)",
            "CREATE INDEX price_snapshot_timestamp IF NOT EXISTS "
            "FOR (n:PriceSnapshot) ON (n.timestamp)",
            "CREATE INDEX price_snapshot_vendor IF NOT EXISTS "
            "FOR (n:PriceSnapshot) ON (n.vendor_id)",
            "CREATE INDEX hardware_intelligence_generated_at IF NOT EXISTS "
            "FOR (n:HardwareIntelligence) ON (n.generated_at)",
        ]
        for statement in statements:
            self.driver.execute_query(statement, database_=settings.neo4j_database)

    def find_product_id(self, identity: ProductIdentity) -> str | None:
        model_probe = " ".join(identity.model.upper().split()[:3])
        records, _, _ = self.driver.execute_query(
            """
            MATCH (candidate)
            WHERE (candidate:Product OR candidate:Component)
              AND (
                candidate.canonical_key = $canonical_key
                OR toUpper(candidate.name) = toUpper($name)
                OR (
                  $category IN labels(candidate)
                  AND $model_probe <> ""
                  AND toUpper(candidate.name) CONTAINS $model_probe
                )
              )
            RETURN candidate.id AS id,
                   CASE
                     WHEN candidate.canonical_key = $canonical_key THEN 0
                     WHEN toUpper(candidate.name) = toUpper($name) THEN 1
                     ELSE 2
                   END AS rank
            ORDER BY rank
            LIMIT 1
            """,
            canonical_key=identity.canonical_key,
            name=identity.name,
            category=identity.category,
            model_probe=model_probe,
            database_=settings.neo4j_database,
        )
        return records[0]["id"] if records else None

    def previous_price(self, product_id_or_key: str, vendor_id: str | None = None) -> float | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)-[:HAS_PRICE]->(snapshot:PriceSnapshot)
            WHERE (p.id = $product_id_or_key OR p.canonical_key = $product_id_or_key)
              AND ($vendor_id IS NULL OR snapshot.vendor_id = $vendor_id)
              AND snapshot.accepted = true
            RETURN snapshot.price AS price
            ORDER BY snapshot.timestamp DESC
            LIMIT 1
            """,
            product_id_or_key=product_id_or_key,
            vendor_id=vendor_id,
            database_=settings.neo4j_database,
        )
        return float(records[0]["price"]) if records else None

    def upsert_offer(self, offer: PriceOffer, accepted: bool = True) -> str:
        target_id = self.find_product_id(offer.product)
        if target_id:
            records, _, _ = self.driver.execute_query(
                """
                MATCH (p {id: $target_id})
                SET p:Product
                SET p += $product_properties
                RETURN p.id AS id
                """,
                target_id=target_id,
                product_properties=_product_properties(offer.product),
                database_=settings.neo4j_database,
            )
            product_id = records[0]["id"]
        else:
            product_id = f"product-{uuid4()}"
            records, _, _ = self.driver.execute_query(
                """
                MERGE (p:Product {canonical_key: $canonical_key})
                ON CREATE SET p.id = $product_id,
                              p.created_at = datetime()
                SET p += $product_properties
                RETURN p.id AS id
                """,
                canonical_key=offer.product.canonical_key,
                product_id=product_id,
                product_properties=_product_properties(offer.product),
                database_=settings.neo4j_database,
            )
            product_id = records[0]["id"]

        snapshot = _clean_properties(
            {
                "id": offer.id,
                "price": offer.price,
                "currency": offer.currency,
                "availability": offer.availability,
                "timestamp": offer.timestamp,
                "shipping_cost": offer.shipping_cost,
                "product_url": offer.product_url,
                "imageUrl": offer.image_url,
                "source_product_id": offer.source_product_id,
                "seller": offer.seller,
                "condition": offer.condition,
                "rating": offer.rating,
                "source": offer.source.source,
                "source_type": offer.source.source_type.value,
                "source_tier": int(offer.source.tier),
                "trust_score": offer.source.trust_score,
                "freshness_score": offer.source.freshness_score,
                "source_url": offer.source.source_url,
                "vendor_id": offer.vendor.id,
                "accepted": accepted,
                "stale": False,
                "flags": offer.flags,
            }
        )
        vendor = _clean_properties(
            {
                "id": offer.vendor.id,
                "name": offer.vendor.name,
                "region": offer.vendor.region,
                "apiType": offer.vendor.api_type.value,
                "trust_score": offer.vendor.trust_score,
                "updated_at": datetime.now(UTC),
            }
        )
        evidence = [_evidence_payload(item) for item in offer.field_evidence]
        self.driver.execute_query(
            """
            MATCH (p {id: $product_id})
            MERGE (vendor:Vendor {id: $vendor.id})
            SET vendor += $vendor
            MERGE (p)-[:SOLD_BY]->(vendor)
            CREATE (snapshot:PriceSnapshot)
            SET snapshot += $snapshot
            MERGE (p)-[:HAS_PRICE]->(snapshot)
            MERGE (snapshot)-[:FROM_VENDOR]->(vendor)
            WITH p, snapshot
            UNWIND $evidence AS evidence
            CREATE (field:FieldEvidence)
            SET field += evidence,
                field.id = randomUUID()
            MERGE (p)-[:HAS_FIELD_EVIDENCE]->(field)
            WITH DISTINCT p
            OPTIONAL MATCH (p)-[:HAS_PRICE]->(candidate:PriceSnapshot)
            WHERE candidate.accepted = true
              AND candidate.availability IN ["in_stock", "preorder", "backorder"]
            WITH p, candidate
            ORDER BY
              CASE candidate.currency WHEN "USD" THEN 0 ELSE 1 END,
              candidate.price + coalesce(candidate.shipping_cost, 0),
              candidate.source_tier,
              candidate.trust_score DESC,
              candidate.timestamp DESC
            WITH p, collect(candidate)[0] AS best
            OPTIONAL MATCH (best)-[:FROM_VENDOR]->(bestVendor:Vendor)
            SET p.current_best_price = best.price,
                p.current_best_currency = best.currency,
                p.current_best_vendor = bestVendor.name,
                p.current_price_timestamp = best.timestamp,
                p.current_price_freshness_score = best.freshness_score,
                p.current_price_trust_score = best.trust_score,
                p.current_price_source = best.source,
                p.stale = false,
                p.price_usd = CASE WHEN best.currency = "USD" THEN best.price ELSE p.price_usd END
            """,
            product_id=product_id,
            vendor=vendor,
            snapshot=snapshot,
            evidence=evidence,
            database_=settings.neo4j_database,
        )
        return product_id

    def mark_product_stale(self, product_id: str, reason: str) -> None:
        self.driver.execute_query(
            """
            MATCH (p)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            SET p.stale = true,
                p.stale_reason = $reason,
                p.stale_at = datetime()
            """,
            product_id=product_id,
            reason=reason,
            database_=settings.neo4j_database,
        )

    def search_products(
        self,
        *,
        q: str = "",
        category: str | None = None,
        region: str | None = None,
        limit: int = 25,
    ) -> list[ProductSearchResult]:
        del region
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND ($category IS NULL OR p.category = $category OR $category IN labels(p))
              AND (
                $q = ""
                OR toLower(p.name) CONTAINS toLower($q)
                OR toLower(coalesce(p.brand, "")) CONTAINS toLower($q)
                OR toLower(coalesce(p.model, "")) CONTAINS toLower($q)
              )
            OPTIONAL MATCH (p)-[:HAS_PRICE]->(s:PriceSnapshot)
            WITH p, s
            ORDER BY s.timestamp DESC
            WITH p, collect(s)[0..2] AS latest
            RETURN p.id AS id,
                   p.canonical_key AS canonical_key,
                   p.name AS name,
                   p.brand AS brand,
                   coalesce(p.category, head([label IN labels(p) WHERE label <> "Component" AND label <> "Product"])) AS category,
                   p.model AS model,
                   coalesce(p.imageUrl, p.image_url) AS image_url,
                   p.current_best_price AS current_best_price,
                   p.current_best_currency AS current_best_currency,
                   p.current_best_vendor AS current_best_vendor,
                   p.current_price_freshness_score AS current_price_freshness_score,
                   p.current_price_trust_score AS current_price_trust_score,
                   p.current_price_timestamp AS current_price_timestamp,
                   coalesce(p.stale, false) AS stale,
                   coalesce(p.best_value, false) AS best_value,
                   latest[1].price AS previous_price
            ORDER BY coalesce(p.current_best_price, p.price_usd, 999999), p.name
            LIMIT $limit
            """,
            q=q,
            category=category,
            limit=limit,
            database_=settings.neo4j_database,
        )
        return [_search_result(record.data()) for record in records]

    def product_categories(self) -> list[str]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)
            WHERE p:Product OR p:Component
            WITH collect(DISTINCT p.category) AS storedCategories,
                 collect(DISTINCT head([label IN labels(p) WHERE label <> "Product" AND label <> "Component"])) AS labelCategories
            UNWIND storedCategories + labelCategories AS category
            WITH DISTINCT category
            WHERE category IS NOT NULL
            RETURN category
            ORDER BY category
            """,
            database_=settings.neo4j_database,
        )
        stored = {str(record["category"]) for record in records}
        return sorted(set(GLOBAL_HARDWARE_CATEGORIES) | stored)

    def product_facts(self, product_id: str) -> dict[str, Any] | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p.id = $product_id OR p.canonical_key = $product_id)
              AND (p:Product OR p:Component)
            OPTIONAL MATCH (p)-[:HAS_PRICE]->(snapshot:PriceSnapshot)
            OPTIONAL MATCH (p)-[:SOLD_BY]->(vendor:Vendor)
            WITH p, collect(DISTINCT snapshot) AS snapshots, count(DISTINCT vendor) AS vendor_count
            RETURN p.id AS id,
                   labels(p) AS labels,
                   properties(p) AS properties,
                   vendor_count AS vendor_count,
                   [snapshot IN snapshots | properties(snapshot)] AS price_snapshots
            LIMIT 1
            """,
            product_id=product_id,
            database_=settings.neo4j_database,
        )
        if not records:
            return None
        data = records[0].data()
        properties = dict(data["properties"])
        specs = {
            key.removeprefix("spec_"): value
            for key, value in properties.items()
            if str(key).startswith("spec_")
        }
        power = {
            key.removeprefix("power_"): value
            for key, value in properties.items()
            if str(key).startswith("power_")
        }
        bandwidth = {
            key.removeprefix("bandwidth_"): value
            for key, value in properties.items()
            if str(key).startswith("bandwidth_")
        }
        dimensions = {
            key.removeprefix("dim_"): value
            for key, value in properties.items()
            if str(key).startswith("dim_")
        }
        category = properties.get("category") or next(
            (
                label
                for label in data["labels"]
                if label not in {"Product", "Component"}
            ),
            "Accessories",
        )
        prices = sorted(
            [snapshot for snapshot in data.get("price_snapshots", []) if snapshot],
            key=lambda snapshot: snapshot.get("timestamp") or datetime.fromtimestamp(0, UTC),
        )
        return {
            "id": data["id"],
            "labels": data["labels"],
            "name": properties.get("name", data["id"]),
            "brand": properties.get("brand"),
            "category": category,
            "model": properties.get("model"),
            "price": properties.get("current_best_price") or properties.get("price_usd"),
            "currency": properties.get("current_best_currency") or "USD",
            "vendor_count": int(data.get("vendor_count") or 0),
            "specs": specs,
            "power": power,
            "bandwidth": bandwidth,
            "dimensions": dimensions,
            "raw": properties,
            "price_snapshots": prices,
        }

    def products_for_enrichment(
        self,
        *,
        category: str | None = None,
        limit: int = 50,
    ) -> list[str]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND p.id IS NOT NULL
              AND ($category IS NULL OR p.category = $category OR $category IN labels(p))
            OPTIONAL MATCH (p)-[:HAS_INTELLIGENCE]->(intel:HardwareIntelligence)
            WITH p, intel
            ORDER BY intel.generated_at ASC
            RETURN p.id AS id
            ORDER BY
              CASE WHEN intel IS NULL THEN 0 ELSE 1 END,
              coalesce(intel.generated_at, datetime("1970-01-01T00:00:00Z")),
              p.name
            LIMIT $limit
            """,
            category=category,
            limit=limit,
            database_=settings.neo4j_database,
        )
        return [str(record["id"]) for record in records if record["id"]]

    def upsert_intelligence(self, intelligence: HardwareIntelligence) -> None:
        payload_json = intelligence.model_dump_json()
        self.driver.execute_query(
            """
            MATCH (p)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            MERGE (intel:HardwareIntelligence {id: $intelligence_id})
            SET intel.product_id = $product_id,
                intel.category = $category,
                intel.confidence = $confidence,
                intel.generated_at = $generated_at,
                intel.payload_json = $payload_json,
                intel.workload_scores_json = $workload_scores_json,
                intel.value_score = $value_score,
                intel.future_proof_score = $future_proof_score,
                intel.thermal_efficiency = $thermal_efficiency
            MERGE (p)-[:HAS_INTELLIGENCE]->(intel)
            SET p.intelligence_value_score = $value_score,
                p.intelligence_future_proof_score = $future_proof_score,
                p.intelligence_confidence = $confidence,
                p.best_value = $best_value_badge
            """,
            product_id=intelligence.product_id,
            intelligence_id=f"intel:{intelligence.product_id}",
            category=intelligence.category,
            confidence=intelligence.confidence,
            generated_at=intelligence.generated_at,
            payload_json=payload_json,
            workload_scores_json=json.dumps(
                {item.workload: item.score for item in intelligence.workloads},
                sort_keys=True,
                default=_json_default,
            ),
            value_score=intelligence.market.value_score,
            future_proof_score=intelligence.longevity.future_proof_score,
            thermal_efficiency=intelligence.power_thermal.thermal_efficiency,
            best_value_badge=intelligence.market.best_value_badge,
            database_=settings.neo4j_database,
        )

    def latest_intelligence(self, product_id: str) -> HardwareIntelligence | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)-[:HAS_INTELLIGENCE]->(intel:HardwareIntelligence)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            RETURN intel.payload_json AS payload_json
            ORDER BY intel.generated_at DESC
            LIMIT 1
            """,
            product_id=product_id,
            database_=settings.neo4j_database,
        )
        return _intelligence_from_record(records[0].data()) if records else None

    def product_detail(self, product_id: str, region: str | None = None) -> ProductDetail | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            OPTIONAL MATCH (p)-[:HAS_PRICE]->(s:PriceSnapshot)
            WITH p, s
            ORDER BY s.timestamp DESC
            WITH p, collect(s)[0..2] AS latest
            OPTIONAL MATCH (p)-[:HAS_FIELD_EVIDENCE]->(e:FieldEvidence)
            RETURN p.id AS id,
                   p.canonical_key AS canonical_key,
                   p.name AS name,
                   p.brand AS brand,
                   coalesce(p.category, head([label IN labels(p) WHERE label <> "Component" AND label <> "Product"])) AS category,
                   p.model AS model,
                   coalesce(p.imageUrl, p.image_url) AS image_url,
                   p.current_best_price AS current_best_price,
                   p.current_best_currency AS current_best_currency,
                   p.current_best_vendor AS current_best_vendor,
                   p.current_price_freshness_score AS current_price_freshness_score,
                   p.current_price_trust_score AS current_price_trust_score,
                   p.current_price_timestamp AS current_price_timestamp,
                   coalesce(p.stale, false) AS stale,
                   coalesce(p.best_value, false) AS best_value,
                   latest[1].price AS previous_price,
                   properties(p) AS properties,
                   collect(properties(e))[0..30] AS evidence
            LIMIT 1
            """,
            product_id=product_id,
            database_=settings.neo4j_database,
        )
        if not records:
            return None
        product = _search_result(records[0].data())
        props = records[0]["properties"] if records else {}
        specs = {
            key.removeprefix("spec_"): value
            for key, value in props.items()
            if str(key).startswith("spec_")
        }
        evidence = []
        for item in records[0]["evidence"] if records else []:
            if not item:
                continue
            evidence.append(
                FieldEvidence(
                    field=item["field"],
                    value=json.loads(item["value_json"]),
                    source=item["source"],
                    timestamp=item["timestamp"],
                    trust_score=float(item["trust_score"]),
                    freshness_score=float(item["freshness_score"]),
                    source_tier=SourceTier(int(item["source_tier"])),
                )
            )
        return ProductDetail(
            **product.model_dump(),
            specs=specs,
            msrp=props.get("msrp"),
            field_evidence=evidence,
            latest_prices=self.vendor_prices(product_id, region=region),
        )

    def vendor_prices(self, product_id: str, region: str | None = None) -> list[PriceSnapshotView]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)-[:HAS_PRICE]->(snapshot:PriceSnapshot)-[:FROM_VENDOR]->(vendor:Vendor)
            WHERE (p.id = $product_id OR p.canonical_key = $product_id)
              AND ($region IS NULL OR vendor.region = $region)
            WITH vendor, snapshot
            ORDER BY snapshot.timestamp DESC
            WITH vendor, collect(snapshot)[0] AS latest
            RETURN latest.id AS id,
                   vendor.id AS vendor_id,
                   vendor.name AS vendor_name,
                   latest.price AS price,
                   latest.currency AS currency,
                   latest.availability AS availability,
                   latest.timestamp AS timestamp,
                   coalesce(latest.shipping_cost, 0) AS shipping_cost,
                   latest.product_url AS product_url,
                   latest.source AS source,
                   latest.source_type AS source_type,
                   latest.source_tier AS source_tier,
                   latest.trust_score AS trust_score,
                   latest.freshness_score AS freshness_score,
                   coalesce(latest.stale, false) AS stale,
                   coalesce(latest.flags, []) AS flags
            ORDER BY
              CASE latest.availability WHEN "in_stock" THEN 0 ELSE 1 END,
              latest.price + coalesce(latest.shipping_cost, 0)
            """,
            product_id=product_id,
            region=region,
            database_=settings.neo4j_database,
        )
        return [_snapshot_view(record.data()) for record in records]

    def price_history(
        self,
        product_id: str,
        region: str | None = None,
        limit: int = 200,
    ) -> list[PriceHistoryPoint]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)-[:HAS_PRICE]->(snapshot:PriceSnapshot)-[:FROM_VENDOR]->(vendor:Vendor)
            WHERE (p.id = $product_id OR p.canonical_key = $product_id)
              AND ($region IS NULL OR vendor.region = $region)
            RETURN snapshot.timestamp AS timestamp,
                   vendor.name AS vendor_name,
                   snapshot.price AS price,
                   snapshot.currency AS currency,
                   snapshot.availability AS availability,
                   snapshot.trust_score AS trust_score,
                   snapshot.freshness_score AS freshness_score
            ORDER BY snapshot.timestamp ASC
            LIMIT $limit
            """,
            product_id=product_id,
            region=region,
            limit=limit,
            database_=settings.neo4j_database,
        )
        return [
            PriceHistoryPoint(
                timestamp=record["timestamp"],
                vendor_name=record["vendor_name"],
                price=float(record["price"]),
                currency=record["currency"],
                availability=record["availability"],
                trust_score=float(record["trust_score"]),
                freshness_score=float(record["freshness_score"]),
            )
            for record in records
        ]

    def refresh_target(self, product_id: str) -> dict[str, Any] | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            RETURN p.id AS id,
                   p.name AS name,
                   coalesce(p.category, head([label IN labels(p) WHERE label <> "Component" AND label <> "Product"])) AS category,
                   p.model AS model
            LIMIT 1
            """,
            product_id=product_id,
            database_=settings.neo4j_database,
        )
        return records[0].data() if records else None

    def products_due_for_refresh(self, *, limit: int = 50, top_only: bool = False) -> list[str]:
        stale_hours = 1 if top_only else 6
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND p.name IS NOT NULL
              AND (
                p.stale = true
                OR p.current_price_timestamp IS NULL
                OR p.current_price_timestamp < datetime() - duration({hours: $stale_hours})
              )
            RETURN p.id AS id
            ORDER BY
              CASE WHEN p.current_best_price IS NOT NULL THEN 0 ELSE 1 END,
              coalesce(p.current_price_timestamp, datetime("1970-01-01T00:00:00Z")),
              p.name
            LIMIT $limit
            """,
            limit=limit,
            stale_hours=stale_hours,
            database_=settings.neo4j_database,
        )
        return [str(record["id"]) for record in records if record["id"]]

    def create_job(self, job: PricingJob) -> None:
        self.driver.execute_query(
            """
            MERGE (job:PricingJob {id: $id})
            SET job.status = $status,
                job.kind = $kind,
                job.payload_json = $payload_json,
                job.created_at = $created_at,
                job.updated_at = $updated_at,
                job.attempts = $attempts,
                job.max_attempts = $max_attempts,
                job.trace_id = $trace_id,
                job.risk_level = $risk_level,
                job.approval_required = $approval_required
            """,
            id=job.id,
            status=job.status,
            kind=job.kind,
            payload_json=json.dumps(job.payload, sort_keys=True),
            created_at=job.created_at,
            updated_at=job.updated_at,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            trace_id=job.trace_id,
            risk_level=job.risk_level,
            approval_required=job.approval_required,
            database_=settings.neo4j_database,
        )

    def update_job(self, job: PricingJob) -> None:
        self.driver.execute_query(
            """
            MATCH (job:PricingJob {id: $id})
            SET job.status = $status,
                job.updated_at = $updated_at,
                job.error = $error,
                job.accepted_snapshots = $accepted_snapshots,
                job.rejected_snapshots = $rejected_snapshots,
                job.attempts = $attempts,
                job.trace_id = $trace_id,
                job.risk_level = $risk_level,
                job.approval_required = $approval_required
            """,
            id=job.id,
            status=job.status,
            updated_at=datetime.now(UTC),
            error=job.error,
            accepted_snapshots=job.accepted_snapshots,
            rejected_snapshots=job.rejected_snapshots,
            attempts=job.attempts,
            trace_id=job.trace_id,
            risk_level=job.risk_level,
            approval_required=job.approval_required,
            database_=settings.neo4j_database,
        )
