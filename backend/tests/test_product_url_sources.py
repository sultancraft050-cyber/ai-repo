from __future__ import annotations

from app.models.source_url import ProductUrlIngestRequest, ProductUrlPreviewRequest, ProductUrlRefreshRequest, PublicDealSubmissionRequest
from app.services.product_url_sources import (
    PRODUCT_URL_POLICIES,
    ProductUrlIngestionService,
    ProductUrlPolicyError,
    ProductUrlPolicyRegistry,
)


GPU_HTML = """
<html>
  <head>
    <meta property="og:image" content="https://cdn.example.test/gpu.jpg" />
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Zotac Gaming GeForce RTX 4070 Super 12GB GDDR6X Twin Edge Graphics Card",
        "image": "https://cdn.example.test/gpu.jpg",
        "offers": {
          "@type": "Offer",
          "price": "2799.00",
          "priceCurrency": "SAR",
          "availability": "https://schema.org/InStock",
          "itemCondition": "https://schema.org/NewCondition"
        }
      }
    </script>
  </head>
  <body>VAT included Free shipping Local warranty</body>
</html>
"""


NO_PRICE_HTML = """
<html>
  <head>
    <meta property="og:title" content="Zotac Gaming GeForce RTX 4070 Super Graphics Card" />
  </head>
  <body>Contact us for price</body>
</html>
"""


class FakeProductUrlRepository:
    def __init__(self) -> None:
        self.upserted_offers = []
        self.product_urls = []
        self.updated_refresh = []
        self.audit_links = []

    def previous_price(self, *args, **kwargs):
        return None

    def upsert_offer(self, offer, accepted=True):
        self.upserted_offers.append((offer, accepted))
        return "product-1"

    def upsert_product_url(self, **kwargs):
        self.product_urls.append(kwargs)

    def update_product_url_refresh_status(self, **kwargs):
        self.updated_refresh.append(kwargs)

    def link_product_url_audit(self, **kwargs):
        self.audit_links.append(kwargs)

    def known_product_urls(self, **kwargs):
        return [
            {
                "url": "https://pczone.com.sa/product/zotac-rtx-4070-super",
                "normalized_url": "https://pczone.com.sa/product/zotac-rtx-4070-super",
                "source_name": "PCZone Saudi",
                "vendor_name": "PCZone Saudi",
                "region": "SA",
                "category": "GPU",
                "approved": True,
                "refresh_allowed": True,
                "source_policy_status": "allowed",
                "last_price": 2799.0,
                "last_currency": "SAR",
            }
        ]


def test_source_policy_allows_known_manual_urls_and_blocks_broad_scraping() -> None:
    names = {policy.source_name: policy for policy in PRODUCT_URL_POLICIES}

    assert names["PCZone Saudi"].manual_url_supported is True
    assert names["Microless Saudi"].manual_url_supported is True
    assert names["MTC KSA"].manual_url_supported is True
    assert names["Noon Saudi"].known_url_refresh_supported == "policy_gated"
    assert names["Amazon.sa"].known_url_refresh_supported == "policy_gated"
    assert all(policy.broad_scraping_allowed is False for policy in PRODUCT_URL_POLICIES)


def test_policy_rejects_search_and_unsupported_domains() -> None:
    registry = ProductUrlPolicyRegistry()

    try:
        registry.identify("https://example.com/product/rtx-4070-super")
        raise AssertionError("unsupported domain should fail")
    except ProductUrlPolicyError as error:
        assert "unsupported" in str(error)

    try:
        registry.identify("https://pczone.com.sa/search?q=rtx")
        raise AssertionError("search URL should fail")
    except ProductUrlPolicyError as error:
        assert "specific_product_pages" in str(error)


def test_policy_allows_pczone_product_slug_under_category_path() -> None:
    policy, normalized = ProductUrlPolicyRegistry().identify(
        "https://www.pczonesa.com/en/category/motherboard/asus-prime-b650m-a-wifi-ii/?utm_source=tracking"
    )

    assert policy.source_name == "PCZone Saudi"
    assert normalized == "https://www.pczonesa.com/en/category/motherboard/asus-prime-b650m-a-wifi-ii"


def test_public_deal_submission_request_reuses_safe_url_validation() -> None:
    request = PublicDealSubmissionRequest(
        url="https://www.pczonesa.com/en/category/motherboard/asus-prime-b650m-a-wifi-ii/?utm_source=spam",
        region="SA",
        category="Motherboard",
        email="buyer@example.com",
    )
    policy, normalized = ProductUrlPolicyRegistry().identify(request.url)

    assert policy.source_name == "PCZone Saudi"
    assert normalized == "https://www.pczonesa.com/en/category/motherboard/asus-prime-b650m-a-wifi-ii"


def test_preview_extracts_safe_structured_metadata_without_mutating_graph() -> None:
    repository = FakeProductUrlRepository()
    service = ProductUrlIngestionService(repository, fetch_html=lambda url: GPU_HTML)  # type: ignore[arg-type]

    preview = service.preview(
        ProductUrlPreviewRequest(
            url="https://pczone.com.sa/product/zotac-rtx-4070-super?tracking=secret",
            region="SA",
            category="GPU",
        )
    )

    assert preview.accepted is True
    assert preview.source_name == "PCZone Saudi"
    assert preview.currency == "SAR"
    assert preview.product_type == "standalone_gpu"
    assert preview.canonical_key
    assert "tracking" not in preview.normalized_url
    assert repository.upserted_offers == []
    assert repository.product_urls == []


def test_ingest_creates_offer_and_product_url_metadata_only() -> None:
    repository = FakeProductUrlRepository()
    service = ProductUrlIngestionService(repository, fetch_html=lambda url: GPU_HTML)  # type: ignore[arg-type]

    response = service.ingest(
        ProductUrlIngestRequest(
            url="https://pczone.com.sa/product/zotac-rtx-4070-super",
            region="SA",
            category="GPU",
            approved=True,
        ),
        actor="admin",
        role="admin",
        trace_id="trace-test",
    )

    assert response.status == "ingested"
    assert response.product_id == "product-1"
    assert repository.upserted_offers
    assert repository.product_urls[0]["approved"] is True
    assert repository.product_urls[0]["last_currency"] == "SAR"


def test_ingest_rejects_missing_price() -> None:
    repository = FakeProductUrlRepository()
    service = ProductUrlIngestionService(repository, fetch_html=lambda url: NO_PRICE_HTML)  # type: ignore[arg-type]

    response = service.ingest(
        ProductUrlIngestRequest(
            url="https://pczone.com.sa/product/zotac-rtx-4070-super",
            region="SA",
            category="GPU",
            approved=True,
        ),
        actor="admin",
        role="admin",
        trace_id="trace-test",
    )

    assert response.status == "rejected"
    assert "missing_or_unreadable_price" in response.preview.rejected_reasons
    assert repository.upserted_offers == []


def test_refresh_only_uses_approved_known_urls() -> None:
    repository = FakeProductUrlRepository()
    service = ProductUrlIngestionService(repository, fetch_html=lambda url: GPU_HTML)  # type: ignore[arg-type]

    result = service.refresh(ProductUrlRefreshRequest(region="SA", category="GPU", limit=5), trace_id="trace-refresh")

    assert result.refreshed_count == 1
    assert result.failed_count == 0
    assert repository.upserted_offers
    assert repository.product_urls
