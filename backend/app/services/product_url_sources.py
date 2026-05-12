from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
import json
import re
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from uuid import uuid5, NAMESPACE_URL

from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.pricing import SourceMetadata, SourceProductRecord, SourceTier, SourceType
from app.models.source_url import (
    KnownProductUrlView,
    ProductUrlIngestResponse,
    ProductUrlPreviewRequest,
    ProductUrlPreviewResponse,
    ProductUrlRefreshItem,
    ProductUrlRefreshRequest,
    ProductUrlRefreshResponse,
    ProductUrlSourcePolicy,
    SourceMatrixEntry,
)
from app.services.hardware_taxonomy import normalize_category
from app.services.pricing_classification import classify_product_type
from app.services.pricing_ingestion import _apply_region_context, _preview_item, _target_model_rejections
from app.services.pricing_normalization import CanonicalProductEngine
from app.services.pricing_quality import PriceQualityValidator
from app.services.region_config import normalize_region


class ProductUrlError(RuntimeError):
    pass


class ProductUrlPolicyError(ProductUrlError):
    pass


FetchHtml = Callable[[str], str]


@dataclass(frozen=True)
class ExtractedProductPage:
    title: str | None = None
    price: float | None = None
    currency: str | None = None
    image_url: str | None = None
    availability: str = "unknown"
    condition: str | None = None


PRODUCT_URL_POLICIES: tuple[ProductUrlSourcePolicy, ...] = (
    ProductUrlSourcePolicy(
        source_name="PCZone Saudi",
        domains=[
            "pczone.com.sa",
            "www.pczone.com.sa",
            "pczone.sa",
            "www.pczone.sa",
            "pczonesa.com",
            "www.pczonesa.com",
        ],
        known_url_refresh_supported="true",
        notes="Single public product URL preview and approved known-URL refresh only; broad scraping disabled.",
    ),
    ProductUrlSourcePolicy(
        source_name="Microless Saudi",
        domains=["microless.com", "www.microless.com", "saudi.microless.com"],
        known_url_refresh_supported="true",
        notes="Single public product URL preview and approved known-URL refresh only; broad scraping disabled.",
    ),
    ProductUrlSourcePolicy(
        source_name="MTC KSA",
        domains=["mtc.com.sa", "www.mtc.com.sa", "mtc-ksa.com", "www.mtc-ksa.com"],
        known_url_refresh_supported="true",
        notes="Single public product URL preview and approved known-URL refresh only; broad scraping disabled.",
    ),
    ProductUrlSourcePolicy(
        source_name="Noon Saudi",
        domains=["noon.com", "www.noon.com", "noon.sa", "www.noon.sa"],
        known_url_refresh_supported="policy_gated",
        policy_status="policy_gated",
        notes="Manual product URL preview is allowed; automated known-URL refresh is policy-gated.",
    ),
    ProductUrlSourcePolicy(
        source_name="Amazon.sa",
        domains=["amazon.sa", "www.amazon.sa"],
        known_url_refresh_supported="policy_gated",
        policy_status="policy_gated",
        notes="Manual product URL preview is allowed; automated known-URL refresh is policy-gated. No private APIs.",
    ),
)


class ProductPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self.visible_text: list[str] = []
        self._in_json_ld = False
        self._script_buffer: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "meta":
            key = attr.get("property") or attr.get("name") or attr.get("itemprop")
            content = attr.get("content")
            if key and content:
                self.meta[key.lower()] = content.strip()
        if tag.lower() == "script" and attr.get("type", "").lower() == "application/ld+json":
            self._in_json_ld = True
            self._script_buffer = []
        if tag.lower() in {"script", "style", "noscript", "svg"} and not self._in_json_ld:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._script_buffer).strip())
            self._in_json_ld = False
            self._script_buffer = []
            return
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._script_buffer.append(data)
            return
        text = " ".join(data.split())
        if text and not self._skip_depth:
            self.visible_text.append(text)


class ProductUrlPolicyRegistry:
    def __init__(self, policies: tuple[ProductUrlSourcePolicy, ...] = PRODUCT_URL_POLICIES) -> None:
        self.policies = policies

    def source_matrix(
        self,
        region: str = "SA",
        activity: dict[str, dict[str, Any]] | None = None,
    ) -> list[SourceMatrixEntry]:
        region = normalize_region(region)
        activity = activity or {}
        entries: list[SourceMatrixEntry] = []
        for policy in self.policies:
            source_activity = _activity_for(policy.source_name, activity)
            health = "policy_gated" if policy.policy_status == "policy_gated" else "configured"
            if source_activity.get("last_failure") and not source_activity.get("last_success"):
                health = "failed"
            elif source_activity.get("last_success"):
                health = "healthy"
            entries.append(
                SourceMatrixEntry(
                    source_name=policy.source_name,
                    region=region,
                    manual_url_supported=policy.manual_url_supported,
                    known_url_refresh_supported=policy.known_url_refresh_supported,
                    broad_scraping_allowed=policy.broad_scraping_allowed,
                    access_method=policy.access_method,
                    enabled=policy.enabled,
                    policy_status=policy.policy_status,
                    health=health,  # type: ignore[arg-type]
                    last_success=source_activity.get("last_success"),
                    last_failure=source_activity.get("last_failure"),
                    source_policy=policy.notes,
                )
            )
        return entries

    def identify(self, url: str, *, refresh: bool = False) -> tuple[ProductUrlSourcePolicy, str]:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ProductUrlPolicyError("invalid_product_url")
        host = parsed.netloc.lower().split("@")[-1].split(":")[0]
        policy = next((item for item in self.policies if host in item.domains), None)
        if not policy:
            raise ProductUrlPolicyError("unsupported_product_url_domain")
        if not policy.enabled or not policy.manual_url_supported:
            raise ProductUrlPolicyError("source_policy_blocks_manual_url_preview")
        if refresh and policy.known_url_refresh_supported != "true":
            raise ProductUrlPolicyError("known_url_refresh_policy_gated")
        normalized = normalize_product_url(url)
        if not _looks_like_product_url(normalized, policy):
            raise ProductUrlPolicyError("only_specific_product_pages_are_allowed")
        return policy, normalized


class ProductUrlExtractionService:
    def __init__(self, fetch_html: FetchHtml | None = None) -> None:
        self.fetch_html = fetch_html or fetch_product_html

    def extract(self, url: str) -> ExtractedProductPage:
        html = self.fetch_html(url)
        parser = ProductPageParser()
        parser.feed(html)
        from_json_ld = _extract_from_json_ld(parser.json_ld)
        visible_text = _visible_text_window(parser.visible_text)
        title = from_json_ld.title or _meta_first(parser.meta, "og:title", "twitter:title", "title")
        price = from_json_ld.price or _price_from_meta(parser.meta) or _price_from_text(visible_text)
        currency = (
            from_json_ld.currency
            or _currency_from_meta(parser.meta)
            or _currency_from_text(visible_text)
        )
        image_url = from_json_ld.image_url or _meta_first(parser.meta, "og:image", "twitter:image")
        availability = from_json_ld.availability or _availability_from_text(visible_text)
        return ExtractedProductPage(
            title=_clean_title(title),
            price=price,
            currency=(currency or "SAR").upper() if price is not None else currency,
            image_url=image_url,
            availability=availability,
            condition=from_json_ld.condition,
        )


class ProductUrlIngestionService:
    def __init__(
        self,
        repository: Neo4jPricingRepository,
        *,
        fetch_html: FetchHtml | None = None,
        policy_registry: ProductUrlPolicyRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.policy_registry = policy_registry or ProductUrlPolicyRegistry()
        self.extractor = ProductUrlExtractionService(fetch_html)
        self.normalizer = CanonicalProductEngine()
        self.validator = PriceQualityValidator()

    def preview(self, request: ProductUrlPreviewRequest) -> ProductUrlPreviewResponse:
        return self._preview_url(url=request.url, region=request.region, category=request.category)

    def ingest(
        self,
        request,
        *,
        actor: str,
        role: str,
        trace_id: str,
        audit_event_id: str | None = None,
    ) -> ProductUrlIngestResponse:
        preview = self._preview_url(url=request.url, region=request.region, category=request.category)
        if not request.approved:
            return ProductUrlIngestResponse(
                status="rejected",
                product_url=preview.product_url,
                normalized_url=preview.normalized_url,
                preview=preview,
                trace_id=trace_id,
            )
        if not preview.accepted:
            return ProductUrlIngestResponse(
                status="rejected",
                product_url=preview.product_url,
                normalized_url=preview.normalized_url,
                preview=preview,
                trace_id=trace_id,
            )
        record = self._record_from_preview(preview)
        offer = self.normalizer.normalize_record(record)
        offer = _apply_region_context(offer, region=preview.region)
        product_id = self.repository.upsert_offer(offer, accepted=True)
        self.repository.upsert_product_url(
            normalized_url=preview.normalized_url,
            url=preview.product_url,
            source_name=preview.source_name or offer.source.source,
            vendor_name=offer.vendor.name,
            region=offer.region,
            category=offer.product.category,
            product_id=product_id,
            vendor_id=offer.vendor.id,
            approved=True,
            refresh_allowed=preview.source_policy_status == "allowed",
            source_policy_status=preview.source_policy_status,
            last_price=offer.price,
            last_currency=offer.currency,
        )
        return ProductUrlIngestResponse(
            status="ingested",
            product_id=product_id,
            vendor_id=offer.vendor.id,
            price_snapshot_id=offer.id,
            product_url=preview.product_url,
            normalized_url=preview.normalized_url,
            audit_event_id=audit_event_id,
            preview=preview,
            trace_id=trace_id,
        )

    def refresh(
        self,
        request: ProductUrlRefreshRequest,
        *,
        trace_id: str,
    ) -> ProductUrlRefreshResponse:
        known_urls = self.repository.known_product_urls(
            region=request.region,
            category=request.category,
            vendor=request.vendor,
            limit=request.limit,
            due_only=True,
        )
        items: list[ProductUrlRefreshItem] = []
        refreshed = failed = skipped = 0
        for known in known_urls:
            try:
                view = KnownProductUrlView.model_validate(known)
                self.policy_registry.identify(view.normalized_url, refresh=True)
                preview = self._preview_url(
                    url=view.normalized_url,
                    region=view.region,
                    category=view.category,
                    refresh=True,
                )
                if not preview.accepted:
                    skipped += 1
                    self.repository.update_product_url_refresh_status(
                        normalized_url=view.normalized_url,
                        success=False,
                        error="preview_not_accepted",
                    )
                    items.append(
                        ProductUrlRefreshItem(
                            normalized_url=view.normalized_url,
                            vendor_name=view.vendor_name,
                            category=view.category,
                            status="skipped",
                            error="preview_not_accepted",
                        )
                    )
                    continue
                record = self._record_from_preview(preview)
                offer = _apply_region_context(self.normalizer.normalize_record(record), region=view.region)
                price_hash = _price_hash(offer.price, offer.currency)
                if price_hash == view.last_price_hash:
                    skipped += 1
                    self.repository.update_product_url_refresh_status(
                        normalized_url=view.normalized_url,
                        success=True,
                    )
                    items.append(
                        ProductUrlRefreshItem(
                            normalized_url=view.normalized_url,
                            vendor_name=view.vendor_name,
                            category=view.category,
                            status="skipped",
                            error="price_unchanged",
                        )
                    )
                    continue
                product_id = self.repository.upsert_offer(offer, accepted=True)
                self.repository.upsert_product_url(
                    normalized_url=view.normalized_url,
                    url=view.url,
                    source_name=view.source_name,
                    vendor_name=offer.vendor.name,
                    region=offer.region,
                    category=offer.product.category,
                    product_id=product_id,
                    vendor_id=offer.vendor.id,
                    approved=True,
                    refresh_allowed=True,
                    source_policy_status=preview.source_policy_status,
                    last_price=offer.price,
                    last_currency=offer.currency,
                )
                refreshed += 1
                items.append(
                    ProductUrlRefreshItem(
                        normalized_url=view.normalized_url,
                        vendor_name=offer.vendor.name,
                        category=offer.product.category,
                        status="refreshed",
                        price_snapshot_id=offer.id,
                    )
                )
            except Exception as error:  # noqa: BLE001 - isolate known URL refresh failures.
                failed += 1
                url = str(known.get("normalized_url") or "")
                self.repository.update_product_url_refresh_status(
                    normalized_url=url,
                    success=False,
                    error=_sanitize_error(error),
                )
                items.append(
                    ProductUrlRefreshItem(
                        normalized_url=url,
                        vendor_name=str(known.get("vendor_name") or "Unknown"),
                        category=str(known.get("category") or "Unknown"),
                        status="failed",
                        error=_sanitize_error(error),
                    )
                )
        return ProductUrlRefreshResponse(
            status="completed",
            region=request.region,
            refreshed_count=refreshed,
            failed_count=failed,
            skipped_count=skipped,
            items=items,
            trace_id=trace_id,
        )

    def _preview_url(
        self,
        *,
        url: str,
        region: str,
        category: str,
        refresh: bool = False,
    ) -> ProductUrlPreviewResponse:
        region = normalize_region(region)
        category = normalize_category(category)
        try:
            policy, normalized_url = self.policy_registry.identify(url, refresh=refresh)
        except ProductUrlPolicyError as error:
            return ProductUrlPreviewResponse(
                product_url=normalize_product_url(url),
                normalized_url=normalize_product_url(url),
                category=category,
                region=region,
                source_policy_status="blocked" if "unsupported" not in str(error) else "unsupported",
                accepted=False,
                rejected_reasons=[str(error)],
            )
        try:
            extracted = self.extractor.extract(normalized_url)
        except Exception as error:  # noqa: BLE001 - extraction failures are returned safely.
            return ProductUrlPreviewResponse(
                product_url=normalized_url,
                normalized_url=normalized_url,
                category=category,
                region=region,
                vendor_name=policy.source_name,
                source_name=policy.source_name,
                source_policy_status=policy.policy_status,
                accepted=False,
                rejected_reasons=[f"extraction_failed:{type(error).__name__}"],
            )
        base = ProductUrlPreviewResponse(
            raw_title=extracted.title,
            price=extracted.price,
            currency=extracted.currency,
            image_url=extracted.image_url,
            availability=extracted.availability,  # type: ignore[arg-type]
            vendor_name=policy.source_name,
            product_url=normalized_url,
            normalized_url=normalized_url,
            category=category,
            region=region,
            source_name=policy.source_name,
            source_policy_status=policy.policy_status,
        )
        if not extracted.title:
            return base.model_copy(update={"rejected_reasons": ["missing_product_title"]})
        if extracted.price is None or not extracted.currency:
            return base.model_copy(update={"rejected_reasons": ["missing_or_unreadable_price"]})
        if extracted.currency.upper() not in {"SAR", "USD", "AED", "EUR", "GBP"}:
            return base.model_copy(update={"rejected_reasons": ["unsupported_currency"]})

        record = self._record_from_extracted(
            extracted=extracted,
            policy=policy,
            normalized_url=normalized_url,
            category=category,
            region=region,
        )
        classification = classify_product_type(record, category)
        offer = self.normalizer.normalize_record(record)
        offer = _apply_region_context(offer, region=region)
        try:
            previous = self.repository.previous_price(
                offer.product.canonical_key,
                vendor_id=offer.vendor.id,
                region=region,
            )
        except Exception:
            previous = None
        quality = self.validator.validate_offer(offer, previous_price=previous)
        family_rejections = _target_model_rejections(extracted.title, category, offer)
        rejected_reasons = _unique([*classification.rejected_reasons, *quality.rejected_reasons, *family_rejections])
        flags = _unique([*offer.flags, *classification.flags, *quality.flags])
        accepted = classification.accepted and quality.accepted and not family_rejections
        discovery_preview = _preview_item(
            record_title=record.title,
            offer=offer,
            classification=classification,
            accepted=accepted,
            rejected_reasons=rejected_reasons,
            flags=flags,
            existing=None,
        )
        return base.model_copy(
            update={
                "normalized_name": discovery_preview.normalized_name,
                "product_type": discovery_preview.product_type,
                "product_type_confidence": discovery_preview.product_type_confidence,
                "canonical_key": discovery_preview.canonical_key,
                "listing_condition": discovery_preview.listing_condition,
                "seller_type": discovery_preview.seller_type,
                "vendor_region_type": discovery_preview.vendor_region_type,
                "marketplace_risk_score": discovery_preview.marketplace_risk_score,
                "vat_status": discovery_preview.vat_status,
                "shipping_status": discovery_preview.shipping_status,
                "warranty_status": discovery_preview.warranty_status,
                "item_price_sar": discovery_preview.item_price_sar,
                "final_landed_price_sar": discovery_preview.final_landed_price_sar,
                "price_confidence": discovery_preview.price_completeness_score,
                "recommendation_level": _recommendation_level(flags, discovery_preview.recommended_candidate),
                "accepted": accepted,
                "rejected_reasons": rejected_reasons,
                "flags": flags,
            }
        )

    def _record_from_preview(self, preview: ProductUrlPreviewResponse) -> SourceProductRecord:
        extracted = ExtractedProductPage(
            title=preview.raw_title,
            price=preview.price,
            currency=preview.currency,
            image_url=preview.image_url,
            availability=preview.availability,
        )
        policy = next(policy for policy in PRODUCT_URL_POLICIES if policy.source_name == preview.source_name)
        return self._record_from_extracted(
            extracted=extracted,
            policy=policy,
            normalized_url=preview.normalized_url,
            category=preview.category,
            region=preview.region,
        )

    def _record_from_extracted(
        self,
        *,
        extracted: ExtractedProductPage,
        policy: ProductUrlSourcePolicy,
        normalized_url: str,
        category: str,
        region: str,
    ) -> SourceProductRecord:
        return SourceProductRecord(
            source_product_id=f"url-{uuid5(NAMESPACE_URL, normalized_url)}",
            title=extracted.title or "",
            category=category,
            price=float(extracted.price or 0),
            currency=(extracted.currency or "SAR").upper(),
            availability=extracted.availability,  # type: ignore[arg-type]
            vendor_name=policy.source_name,
            vendor_region=region,
            region=region,
            country_code=region,
            product_url=normalized_url,
            image_url=extracted.image_url,
            condition=extracted.condition,
            source=SourceMetadata(
                source=policy.source_name,
                source_type=SourceType.VERIFIED_SCRAPING,
                tier=SourceTier.VERIFIED_SCRAPING,
                timestamp=datetime.now(UTC),
                trust_score=0.76 if policy.policy_status == "allowed" else 0.62,
                freshness_score=1.0,
                source_url=normalized_url,
            ),
            specs={"source_policy_status": policy.policy_status, "access_method": policy.access_method},
        )


def fetch_product_html(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; PCBuilderKnownUrlPreview/1.0; single-product-url)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urlopen(request, timeout=12) as response:  # noqa: S310 - URL is policy-validated before fetch.
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                raise ProductUrlError("product_url_did_not_return_html")
            data = response.read(1_500_000)
    except HTTPError as error:
        raise ProductUrlError(f"http_{error.code}") from error
    except URLError as error:
        raise ProductUrlError("network_fetch_failed") from error
    return data.decode("utf-8", errors="replace")


def normalize_product_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip()
    host = parsed.netloc.lower().split("@")[-1].split(":")[0]
    path = re.sub(r"/+", "/", parsed.path or "/")
    return urlunsplit((parsed.scheme.lower(), host, path.rstrip("/") or "/", "", ""))


def _looks_like_product_url(url: str, policy: ProductUrlSourcePolicy) -> bool:
    path = urlsplit(url).path.lower()
    if policy.source_name == "PCZone Saudi" and _is_pczone_product_slug(path):
        return True
    blocked_parts = (
        "/search",
        "/category",
        "/categories",
        "/collections",
        "/deals",
        "/offers",
        "/sale",
        "/cart",
        "/wishlist",
    )
    if any(part in path for part in blocked_parts):
        return False
    if policy.source_name == "Amazon.sa":
        return "/dp/" in path or "/gp/product/" in path
    if policy.source_name == "Noon Saudi":
        return "/p/" in path or bool(re.search(r"/[a-z0-9-]+/p/?$", path))
    return len([part for part in path.split("/") if part]) >= 1


def _extract_from_json_ld(scripts: list[str]) -> ExtractedProductPage:
    for script in scripts:
        try:
            payload = json.loads(script)
        except json.JSONDecodeError:
            continue
        for item in _walk_json_ld(payload):
            item_type = item.get("@type") or item.get("type")
            if isinstance(item_type, list):
                is_product = any(str(value).lower() == "product" for value in item_type)
            else:
                is_product = str(item_type).lower() == "product"
            if not is_product:
                continue
            offer = _first_offer(item.get("offers"))
            price = _to_price(offer.get("price") if offer else item.get("price"))
            currency = _json_ld_currency(item, offer)
            image = item.get("image")
            if isinstance(image, list):
                image = next((value for value in image if isinstance(value, str)), None)
            availability = str(offer.get("availability") or "").lower() if offer else ""
            return ExtractedProductPage(
                title=str(item.get("name") or "").strip() or None,
                price=price,
                currency=str(currency).strip().upper() if currency else None,
                image_url=str(image).strip() if isinstance(image, str) else None,
                availability=_availability_from_text(availability),
                condition=str(offer.get("itemCondition") or "").strip() if offer else None,
            )
    return ExtractedProductPage()


def _walk_json_ld(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        graph = payload.get("@graph")
        if isinstance(graph, list):
            return [item for item in graph if isinstance(item, dict)] + [payload]
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _first_offer(raw: Any) -> dict[str, Any]:
    if isinstance(raw, list):
        return next((item for item in raw if isinstance(item, dict)), {})
    return raw if isinstance(raw, dict) else {}


def _json_ld_currency(item: dict[str, Any], offer: dict[str, Any]) -> Any:
    if offer:
        return offer.get("priceCurrency") or offer.get("pricecurrency")
    return item.get("priceCurrency")


def _meta_first(meta: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        if meta.get(key):
            return meta[key]
    return None


def _price_from_meta(meta: dict[str, str]) -> float | None:
    for key in ("product:price:amount", "og:price:amount", "price", "twitter:data1"):
        price = _to_price(meta.get(key))
        if price is not None:
            return price
    return None


def _currency_from_meta(meta: dict[str, str]) -> str | None:
    for key in ("product:price:currency", "og:price:currency", "currency"):
        value = meta.get(key)
        if value and re.fullmatch(r"[A-Za-z]{3}", value.strip()):
            return value.strip().upper()
    return None


def _price_from_text(text: str) -> float | None:
    match = re.search(r"(?:SAR|ر\.?س\.?|ريال)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", text, flags=re.IGNORECASE)
    if not match:
        match = re.search(r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?:SAR|ر\.?س\.?|ريال)", text, flags=re.IGNORECASE)
    return _to_price(match.group(1)) if match else None


def _currency_from_text(text: str) -> str | None:
    if re.search(r"\bSAR\b|ر\.?س\.?|ريال", text, flags=re.IGNORECASE):
        return "SAR"
    return None


def _availability_from_text(text: str) -> str:
    normalized = text.lower()
    if "outofstock" in normalized.replace(" ", "") or "out of stock" in normalized:
        return "out_of_stock"
    if "preorder" in normalized or "pre-order" in normalized:
        return "preorder"
    if "backorder" in normalized:
        return "backorder"
    if "instock" in normalized.replace(" ", "") or "in stock" in normalized or "available" in normalized:
        return "in_stock"
    return "unknown"


def _to_price(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    match = re.search(r"[0-9][0-9,]*(?:\.[0-9]{1,2})?", text)
    if not match:
        return None
    return float(match.group(0).replace(",", ""))


def _clean_title(title: str | None) -> str | None:
    if not title:
        return None
    return re.sub(r"\s+", " ", title).strip()


def _recommendation_level(flags: list[str], recommended_candidate: bool) -> str:
    if recommended_candidate:
        return "recommended"
    if any(flag in flags for flag in ("price_requires_review", "marketplace_listing", "imported_listing")):
        return "acceptable_with_risk"
    return "insufficient_data"


def _sanitize_error(error: Exception) -> str:
    text = str(error) or type(error).__name__
    return re.sub(
        r"([?&](?:key|token|signature|api_key|apikey)=)[^&\\s]+",
        r"\1REDACTED",
        text,
        flags=re.IGNORECASE,
    )[:180]


def _price_hash(price: float | None, currency: str | None) -> str:
    normalized_price = f"{float(price):.2f}" if price is not None else "missing"
    return f"{currency or 'unknown'}:{normalized_price}"


def _visible_text_window(values: list[str], limit: int = 300) -> str:
    return " ".join(values[:limit])


def _is_pczone_product_slug(path: str) -> bool:
    return bool(re.fullmatch(r"/(?:en/)?category/motherboard/[a-z0-9-]+/?", path))


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _activity_for(source_name: str, activity: dict[str, dict[str, Any]]) -> dict[str, Any]:
    normalized = source_name.lower()
    for key, value in activity.items():
        if normalized in key.lower() or key.lower() in normalized:
            return value
    return {}
