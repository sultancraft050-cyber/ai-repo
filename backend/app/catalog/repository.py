from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.catalog.models import (
    ApprovalStatus,
    Product,
    ProductImage,
    ProductSpecification,
    ReviewStatus,
    StockStatus,
    Store,
    StoreOffer,
    PriceHistory,
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class CatalogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_products(self, *, offset: int, limit: int, category: str | None = None, search: str | None = None) -> list[Product]:
        query = select(Product).where(Product.approval_status == ApprovalStatus.APPROVED).order_by(Product.canonical_name, Product.id).offset(offset).limit(limit)
        if category:
            query = query.where(Product.category == category)
        if search:
            pattern = f"%{search.strip()[:80]}%"
            query = query.where(or_(Product.canonical_name.ilike(pattern), Product.brand.ilike(pattern), Product.manufacturer_part_number.ilike(pattern)))
        return list(self.session.scalars(query))

    def get_product(self, product_id: int) -> Product | None:
        return self.session.scalar(select(Product).options(selectinload(Product.specifications), selectinload(Product.images)).where(Product.id == product_id, Product.approval_status == ApprovalStatus.APPROVED))

    def list_specifications(self, product_id: int) -> list[ProductSpecification]:
        return list(self.session.scalars(select(ProductSpecification).where(ProductSpecification.product_id == product_id).order_by(ProductSpecification.specification_key)))

    def list_approved_images(self, product_id: int) -> list[ProductImage]:
        return list(self.session.scalars(select(ProductImage).where(ProductImage.product_id == product_id, ProductImage.review_status == ReviewStatus.APPROVED, ProductImage.rights_status == "approved").order_by(ProductImage.is_primary.desc(), ProductImage.id)))

    def list_stores(self, *, offset: int, limit: int) -> list[Store]:
        return list(self.session.scalars(select(Store).where(Store.status == "active").order_by(Store.name, Store.id).offset(offset).limit(limit)))

    def list_current_offers(self, product_id: int, *, now: datetime | None = None) -> list[StoreOffer]:
        observed = now or now_utc()
        query = select(StoreOffer).options(selectinload(StoreOffer.store)).join(StoreOffer.product).where(StoreOffer.product_id == product_id, Product.approval_status == ApprovalStatus.APPROVED, StoreOffer.expires_at.is_(None) | (StoreOffer.expires_at >= observed)).order_by(StoreOffer.sale_price.is_(None), StoreOffer.sale_price, StoreOffer.regular_price, StoreOffer.id)
        return list(self.session.scalars(query))

    def cheapest_sar_offer(self, product_id: int, *, now: datetime | None = None) -> StoreOffer | None:
        offers = [offer for offer in self.list_current_offers(product_id, now=now) if offer.currency == "SAR" and offer.stock_status == StockStatus.IN_STOCK and (offer.sale_price is not None or offer.regular_price is not None)]
        return min(offers, key=lambda offer: (offer.sale_price if offer.sale_price is not None else offer.regular_price, offer.id), default=None)

    def list_price_history(self, offer_id: int, *, limit: int = 100) -> list[PriceHistory]:
        return list(self.session.scalars(select(PriceHistory).where(PriceHistory.offer_id == offer_id).order_by(PriceHistory.observed_at.desc(), PriceHistory.id.desc()).limit(min(limit, 100))))
