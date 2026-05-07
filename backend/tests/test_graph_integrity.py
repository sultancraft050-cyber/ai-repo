from __future__ import annotations

from datetime import UTC, datetime

from app.models.ops import ApprovalItem
from app.models.pricing import PriceSnapshotView, ProductSearchResult, SourceTier, SourceType
from app.services.graph_integrity import GraphIntegrityService, cpu_canonical_identity


def _product(product_id: str, name: str, canonical_key: str | None = None) -> ProductSearchResult:
    return ProductSearchResult(
        id=product_id,
        canonical_key=canonical_key,
        name=name,
        brand="AMD",
        category="CPU",
        model=name,
        region="SA",
        price_status="active",
        current_recommended_price=1599,
        lowest_market_price=1599,
    )


def _price(product_id: str, vendor: str = "Amazon.sa") -> PriceSnapshotView:
    return PriceSnapshotView(
        id=f"snapshot:{product_id}:{vendor}",
        vendor_id=vendor.lower().replace(".", "-"),
        vendor_name=vendor,
        price=1599,
        currency="SAR",
        region="SA",
        final_landed_price_sar=1599,
        availability="in_stock",
        timestamp=datetime.now(UTC),
        source="SerpAPI Saudi",
        source_type=SourceType.AGGREGATOR_API,
        source_tier=SourceTier.AGGREGATOR_API,
        trust_score=0.82,
        freshness_score=0.95,
        accepted=True,
    )


class FakePricingRepository:
    def __init__(self) -> None:
        self.products = [
            _product("cpu:1", "AMD Ryzen 7 7800X3D Processor", "CPU|AMD|RYZEN_7_7800X3D"),
            _product("cpu:2", "AMD R7 7800X3D 8-Core CPU", "CPU|AMD|7800X3D|socket:AM5"),
        ]

    def search_products(self, q: str = "", category: str | None = None, region: str = "SA", limit: int = 500):
        return self.products[:limit]

    def vendor_prices(self, product_id: str, region: str = "SA"):
        return [_price(product_id)]

    def product_merge_facts(self, product_id: str, region: str = "SA"):
        product = next((item for item in self.products if item.id == product_id), None)
        if not product:
            return None
        return {
            "id": product.id,
            "canonical_key": product.canonical_key,
            "name": product.name,
            "brand": product.brand,
            "category": product.category,
            "model": product.model,
            "price_snapshot_count": 1,
            "vendors": ["Amazon.sa"],
            "field_evidence_count": 2,
            "audit_event_count": 1,
            "prices": [{"region": region, "price": 1599, "currency": "SAR"}],
        }


class FakeOpsRepository:
    def __init__(self) -> None:
        self.approvals: list[ApprovalItem] = []

    def unresolved_approval_exists(self, approval_id: str) -> bool:
        return any(item.id == approval_id and item.status in {"pending", "deferred"} for item in self.approvals)

    def approval_by_id(self, approval_id: str) -> ApprovalItem | None:
        return next((item for item in self.approvals if item.id == approval_id), None)

    def upsert_approval(self, approval: ApprovalItem) -> ApprovalItem:
        self.approvals = [item for item in self.approvals if item.id != approval.id]
        self.approvals.append(approval)
        return approval


def test_cpu_canonical_identity_groups_7800x3d_variants() -> None:
    variants = [
        _product("a", "AMD Ryzen 7 7800X3D"),
        _product("b", "Ryzen 7 7800X3D Processor"),
        _product("c", "AMD R7 7800X3D"),
        _product("d", "7800X3D CPU"),
    ]

    assert {cpu_canonical_identity(product) for product in variants} == {"CPU|AMD|RYZEN_7_7800X3D"}


def test_duplicate_candidates_create_approval_without_merging() -> None:
    pricing = FakePricingRepository()
    ops = FakeOpsRepository()

    report = GraphIntegrityService(pricing, ops).cpu_duplicates(region="SA", trace_id="trace-test")  # type: ignore[arg-type]

    assert len(report.candidates) == 1
    assert report.candidates[0].approval_required is True
    assert report.candidates[0].approval_id
    assert len(ops.approvals) == 1
    assert ops.approvals[0].action_type == "canonical_product_merge"
    assert ops.approvals[0].status == "pending"


def test_merge_preview_is_read_only_and_preserves_relationship_counts() -> None:
    pricing = FakePricingRepository()
    ops = FakeOpsRepository()

    preview = GraphIntegrityService(pricing, ops).merge_preview(
        product_ids=["cpu:1", "cpu:2"],
        region="SA",
        trace_id="trace-preview",
    )  # type: ignore[arg-type]

    assert preview.would_execute is False
    assert preview.approval_required is True
    assert preview.price_snapshots_to_preserve == 2
    assert preview.vendors_to_preserve == 1
    assert preview.field_evidence_to_preserve == 4
    assert preview.audit_events_to_preserve == 2
    assert preview.approval_id
