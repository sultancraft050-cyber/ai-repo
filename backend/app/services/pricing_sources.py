from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from app.models.pricing import SourceMetadata, SourceProductRecord, SourceTier, SourceType
from app.services.pricing_quality import freshness_score


class SourceUnavailable(RuntimeError):
    pass


class PricingSource(Protocol):
    name: str
    tier: SourceTier
    source_type: SourceType

    def configured(self) -> bool:
        ...

    def fetch_offers(
        self,
        *,
        query: str,
        category: str,
        region: str,
        limit: int,
    ) -> list[SourceProductRecord]:
        ...


def _metadata(
    *,
    source: str,
    source_type: SourceType,
    tier: SourceTier,
    trust_score: float,
    source_url: str | None = None,
) -> SourceMetadata:
    timestamp = datetime.now(UTC)
    return SourceMetadata(
        source=source,
        source_type=source_type,
        tier=tier,
        timestamp=timestamp,
        trust_score=trust_score,
        freshness_score=freshness_score(timestamp),
        source_url=_safe_source_url(source_url),
    )


def _safe_source_url(source_url: str | None) -> str | None:
    if not source_url:
        return None
    parts = urlsplit(source_url)
    redacted_keys = {"api_key", "apikey", "token", "access_token", "key", "authorization"}
    query = urlencode(
        [
            (key, "REDACTED" if key.lower() in redacted_keys else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    retries: int = 3,
    timeout_seconds: int = 15,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = Request(url, data=body, headers=headers or {}, method=method)
            with urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
            if isinstance(error, HTTPError) and error.code in {400, 401, 403, 404}:
                break
            time.sleep(min(2**attempt, 8))
    raise SourceUnavailable(f"source request failed: {last_error}")


def _money(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"(\d+(?:,\d{3})*(?:\.\d+)?)", str(value))
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


class BestBuyProductsSource:
    name = "BestBuy"
    tier = SourceTier.RETAILER_API
    source_type = SourceType.RETAILER_API

    def __init__(self) -> None:
        self.api_key = os.getenv("BESTBUY_API_KEY", "")

    def configured(self) -> bool:
        return bool(self.api_key)

    def fetch_offers(
        self,
        *,
        query: str,
        category: str,
        region: str,
        limit: int,
    ) -> list[SourceProductRecord]:
        if not self.configured():
            raise SourceUnavailable("BESTBUY_API_KEY is not configured")
        search = quote(query)
        params = urlencode(
            {
                "apiKey": self.api_key,
                "format": "json",
                "pageSize": max(1, min(limit, 25)),
                "show": "sku,name,manufacturer,modelNumber,salePrice,regularPrice,"
                "onlineAvailability,url,image,customerReviewAverage",
            }
        )
        url = f"https://api.bestbuy.com/v1/products((search={search}))?{params}"
        body = _request_json(url, headers={"Accept": "application/json"})
        products = body.get("products", [])
        records: list[SourceProductRecord] = []
        for product in products:
            price = _money(product.get("salePrice") or product.get("regularPrice"))
            if price is None:
                continue
            records.append(
                SourceProductRecord(
                    source_product_id=str(product.get("sku")),
                    title=str(product.get("name") or query),
                    brand=product.get("manufacturer"),
                    model=product.get("modelNumber"),
                    category=category,
                    price=price,
                    currency="USD",
                    availability="in_stock" if product.get("onlineAvailability") else "out_of_stock",
                    vendor_name="BestBuy",
                    vendor_region=region,
                    product_url=product.get("url"),
                    image_url=product.get("image"),
                    rating=_money(product.get("customerReviewAverage")),
                    source=_metadata(
                        source="BestBuy Products API",
                        source_type=self.source_type,
                        tier=self.tier,
                        trust_score=0.9,
                        source_url=url,
                    ),
                )
            )
        return records


class EbayBrowseSource:
    name = "eBay"
    tier = SourceTier.RETAILER_API
    source_type = SourceType.RETAILER_API

    def __init__(self) -> None:
        self.token = os.getenv("EBAY_BROWSE_TOKEN", "")

    def configured(self) -> bool:
        return bool(self.token)

    def fetch_offers(
        self,
        *,
        query: str,
        category: str,
        region: str,
        limit: int,
    ) -> list[SourceProductRecord]:
        if not self.configured():
            raise SourceUnavailable("EBAY_BROWSE_TOKEN is not configured")
        params = urlencode({"q": query, "limit": max(1, min(limit, 50))})
        url = f"https://api.ebay.com/buy/browse/v1/item_summary/search?{params}"
        body = _request_json(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US" if region.upper() == "US" else "EBAY_GB",
            },
        )
        records: list[SourceProductRecord] = []
        for item in body.get("itemSummaries", []):
            price_data = item.get("price") or {}
            price = _money(price_data.get("value"))
            if price is None:
                continue
            availability = "unknown"
            estimates = item.get("estimatedAvailabilities") or []
            if estimates:
                availability = "in_stock" if estimates[0].get("estimatedAvailabilityStatus") else "unknown"
            records.append(
                SourceProductRecord(
                    source_product_id=str(item.get("itemId")),
                    title=str(item.get("title") or query),
                    category=category,
                    price=price,
                    currency=str(price_data.get("currency") or "USD"),
                    availability=availability,
                    vendor_name="eBay",
                    vendor_region=region,
                    product_url=item.get("itemWebUrl"),
                    image_url=(item.get("image") or {}).get("imageUrl"),
                    seller=(item.get("seller") or {}).get("username"),
                    condition=item.get("condition"),
                    source=_metadata(
                        source="eBay Browse API",
                        source_type=self.source_type,
                        tier=self.tier,
                        trust_score=0.86,
                        source_url=url,
                    ),
                )
            )
        return records


class SerpApiShoppingSource:
    name = "SerpAPI"
    tier = SourceTier.AGGREGATOR_API
    source_type = SourceType.AGGREGATOR_API

    def __init__(self) -> None:
        self.api_key = os.getenv("SERPAPI_KEY", "")

    def configured(self) -> bool:
        return bool(self.api_key)

    def fetch_offers(
        self,
        *,
        query: str,
        category: str,
        region: str,
        limit: int,
    ) -> list[SourceProductRecord]:
        if not self.configured():
            raise SourceUnavailable("SERPAPI_KEY is not configured")
        params = urlencode(
            {
                "engine": "google_shopping",
                "q": query,
                "api_key": self.api_key,
                "gl": region.lower() if len(region) == 2 else "us",
                "hl": "en",
            }
        )
        url = f"https://serpapi.com/search.json?{params}"
        body = _request_json(url, headers={"Accept": "application/json"})
        records: list[SourceProductRecord] = []
        for result in (body.get("shopping_results") or [])[:limit]:
            price = _money(result.get("extracted_price") or result.get("price"))
            if price is None:
                continue
            records.append(
                SourceProductRecord(
                    source_product_id=str(result.get("product_id") or result.get("position")),
                    title=str(result.get("title") or query),
                    category=category,
                    price=price,
                    currency="USD",
                    availability="in_stock" if result.get("source") else "unknown",
                    vendor_name=str(result.get("source") or "Google Shopping"),
                    vendor_region=region,
                    product_url=result.get("link"),
                    image_url=result.get("thumbnail"),
                    shipping_cost=_money(result.get("delivery")) or 0,
                    rating=_money(result.get("rating")),
                    source=_metadata(
                        source="SerpAPI Google Shopping",
                        source_type=self.source_type,
                        tier=self.tier,
                        trust_score=0.78,
                        source_url=url,
                    ),
                )
            )
        return records


class AmazonProductAdvertisingSource:
    name = "Amazon"
    tier = SourceTier.RETAILER_API
    source_type = SourceType.RETAILER_API

    def __init__(self) -> None:
        self.access_key = os.getenv("AMAZON_PAAPI_ACCESS_KEY", "")
        self.secret_key = os.getenv("AMAZON_PAAPI_SECRET_KEY", "")
        self.partner_tag = os.getenv("AMAZON_PAAPI_PARTNER_TAG", "")
        self.host = os.getenv("AMAZON_PAAPI_HOST", "webservices.amazon.com")
        self.region_name = os.getenv("AMAZON_PAAPI_REGION", "us-east-1")

    def configured(self) -> bool:
        return bool(self.access_key and self.secret_key and self.partner_tag)

    def fetch_offers(
        self,
        *,
        query: str,
        category: str,
        region: str,
        limit: int,
    ) -> list[SourceProductRecord]:
        if not self.configured():
            raise SourceUnavailable("Amazon PA-API credentials are not configured")
        path = "/paapi5/searchitems"
        url = f"https://{self.host}{path}"
        payload = {
            "Keywords": query,
            "ItemCount": max(1, min(limit, 10)),
            "PartnerTag": self.partner_tag,
            "PartnerType": "Associates",
            "Marketplace": "www.amazon.com",
            "Resources": [
                "Images.Primary.Medium",
                "ItemInfo.ByLineInfo",
                "ItemInfo.ManufactureInfo",
                "ItemInfo.Title",
                "Offers.Listings.Availability.Message",
                "Offers.Listings.Condition",
                "Offers.Listings.MerchantInfo",
                "Offers.Listings.Price",
            ],
        }
        headers = self._signed_headers(path, payload)
        body = _request_json(url, method="POST", headers=headers, payload=payload)
        items = ((body.get("SearchResult") or {}).get("Items") or [])[:limit]
        records: list[SourceProductRecord] = []
        for item in items:
            listing = (((item.get("Offers") or {}).get("Listings") or []) + [{}])[0]
            price_data = listing.get("Price") or {}
            price = _money(price_data.get("Amount"))
            if price is None:
                continue
            item_info = item.get("ItemInfo") or {}
            title = ((item_info.get("Title") or {}).get("DisplayValue")) or query
            brand = (
                ((item_info.get("ByLineInfo") or {}).get("Brand") or {}).get("DisplayValue")
                or ((item_info.get("ManufactureInfo") or {}).get("ItemPartNumber") or {}).get("DisplayValue")
            )
            records.append(
                SourceProductRecord(
                    source_product_id=str(item.get("ASIN")),
                    title=str(title),
                    brand=brand,
                    category=category,
                    price=price,
                    currency=str(price_data.get("Currency") or "USD"),
                    availability="in_stock"
                    if "stock" in str((listing.get("Availability") or {}).get("Message", "")).lower()
                    else "unknown",
                    vendor_name="Amazon",
                    vendor_region=region,
                    product_url=item.get("DetailPageURL"),
                    image_url=(((item.get("Images") or {}).get("Primary") or {}).get("Medium") or {}).get("URL"),
                    condition=(listing.get("Condition") or {}).get("Value"),
                    source=_metadata(
                        source="Amazon Product Advertising API",
                        source_type=self.source_type,
                        tier=self.tier,
                        trust_score=0.9,
                        source_url=url,
                    ),
                )
            )
        return records

    def _signed_headers(self, path: str, payload: dict[str, Any]) -> dict[str, str]:
        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(json.dumps(payload).encode("utf-8")).hexdigest()
        canonical_headers = (
            "content-encoding:amz-1.0\n"
            "content-type:application/json; charset=utf-8\n"
            f"host:{self.host}\n"
            "x-amz-target:com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems\n"
            f"x-amz-date:{amz_date}\n"
        )
        signed_headers = "content-encoding;content-type;host;x-amz-target;x-amz-date"
        canonical_request = "\n".join(
            ["POST", path, "", canonical_headers, signed_headers, payload_hash]
        )
        credential_scope = f"{date_stamp}/{self.region_name}/ProductAdvertisingAPI/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = self._signature_key(date_stamp)
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        return {
            "Content-Encoding": "amz-1.0",
            "Content-Type": "application/json; charset=utf-8",
            "Host": self.host,
            "X-Amz-Date": amz_date,
            "X-Amz-Target": "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems",
            "Authorization": (
                "AWS4-HMAC-SHA256 "
                f"Credential={self.access_key}/{credential_scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            ),
        }

    def _signature_key(self, date_stamp: str) -> bytes:
        key = ("AWS4" + self.secret_key).encode("utf-8")
        date_key = hmac.new(key, date_stamp.encode("utf-8"), hashlib.sha256).digest()
        region_key = hmac.new(date_key, self.region_name.encode("utf-8"), hashlib.sha256).digest()
        service_key = hmac.new(region_key, b"ProductAdvertisingAPI", hashlib.sha256).digest()
        return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()


class SourceRegistry:
    def __init__(self) -> None:
        self.sources: list[PricingSource] = [
            SerpApiShoppingSource(),
            EbayBrowseSource(),
            BestBuyProductsSource(),
            AmazonProductAdvertisingSource(),
        ]
        self.priority = {
            "serpapi": 0,
            "ebay": 1,
            "bestbuy": 2,
            "amazon": 3,
        }

    def enabled(self, names: list[str] | None = None) -> list[PricingSource]:
        wanted = {name.lower() for name in names or []}
        sources = [
            source
            for source in self.sources
            if source.configured() and (not wanted or source.name.lower() in wanted)
        ]
        return sorted(sources, key=lambda source: self.priority.get(source.name.lower(), 99))

    def all_sources(self) -> list[PricingSource]:
        return list(self.sources)
