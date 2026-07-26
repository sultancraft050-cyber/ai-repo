from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ProductCategory(str, Enum):
    CPU = "CPU"
    GPU = "GPU"
    MOTHERBOARD = "MOTHERBOARD"
    RAM = "RAM"
    STORAGE = "STORAGE"
    PSU = "PSU"
    CASE = "CASE"
    COOLER = "COOLER"


class LifecycleStatus(str, Enum):
    ACTIVE = "active"
    DISCONTINUED = "discontinued"
    UNKNOWN = "unknown"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ImageRightsStatus(str, Enum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ImageQualityStatus(str, Enum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    ACCEPTABLE = "acceptable"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ImageReviewDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    MARK_DUPLICATE = "MARK_DUPLICATE"
    APPROVE_PRIMARY = "APPROVE_PRIMARY"
    REMOVE_PRIMARY = "REMOVE_PRIMARY"
    EXPIRE_RIGHTS = "EXPIRE_RIGHTS"


class StockStatus(str, Enum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"


class SourceType(str, Enum):
    MANUAL = "manual"
    CSV = "csv"
    JSON = "json"
    API = "api"
    OFFICIAL = "official"


class ImportBatchStatus(str, Enum):
    RECEIVED = "received"
    PARSING = "parsing"
    VALIDATING = "validating"
    STAGED = "staged"
    REVIEW_REQUIRED = "review_required"
    READY = "ready"
    COMMITTING = "committing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    CANCELED = "canceled"


class ImportEntityType(str, Enum):
    PRODUCT = "PRODUCT"
    PRODUCT_SPECIFICATION = "PRODUCT_SPECIFICATION"
    PRODUCT_IMAGE_METADATA = "PRODUCT_IMAGE_METADATA"
    STORE = "STORE"
    STORE_OFFER = "STORE_OFFER"
    PRICE_OBSERVATION = "PRICE_OBSERVATION"


class ImportValidationStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    DUPLICATE = "DUPLICATE"
    AMBIGUOUS = "AMBIGUOUS"
    BLOCKED = "BLOCKED"


class ImportReviewStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NOT_REQUIRED = "NOT_REQUIRED"


class ImportProposedAction(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    SKIP = "SKIP"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


class Product(Base):
    __tablename__ = "catalog_products"
    __table_args__ = (
        UniqueConstraint("normalized_brand", "manufacturer_part_number", name="uq_catalog_product_brand_mpn"),
        Index("ix_catalog_product_category", "category"),
        Index("ix_catalog_product_approval", "approval_status"),
        CheckConstraint("category IN ('CPU','GPU','MOTHERBOARD','RAM','STORAGE','PSU','CASE','COOLER')", name="ck_catalog_product_category"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[ProductCategory] = mapped_column(String(24), nullable=False)
    brand: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized_brand: Mapped[str] = mapped_column(String(160), nullable=False)
    manufacturer_part_number: Mapped[str] = mapped_column(String(160), nullable=False)
    gtin: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    exact_model: Mapped[str | None] = mapped_column(String(240))
    variant: Mapped[str | None] = mapped_column(String(160))
    canonical_name: Mapped[str] = mapped_column(String(320), nullable=False)
    slug: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    lifecycle_status: Mapped[LifecycleStatus] = mapped_column(String(32), default=LifecycleStatus.ACTIVE, nullable=False)
    approval_status: Mapped[ApprovalStatus] = mapped_column(String(32), default=ApprovalStatus.PENDING, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    specifications: Mapped[list["ProductSpecification"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    images: Mapped[list["ProductImage"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    offers: Mapped[list["StoreOffer"]] = relationship(back_populates="product")


class ProductSpecification(Base):
    __tablename__ = "catalog_product_specifications"
    __table_args__ = (UniqueConstraint("product_id", "specification_key", name="uq_catalog_product_spec_key"), Index("ix_catalog_spec_product", "product_id"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("catalog_products.id", ondelete="CASCADE"), nullable=False)
    specification_key: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_value: Mapped[str] = mapped_column(Text, nullable=False)
    display_value: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_import_sources.id"))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    product: Mapped[Product] = relationship(back_populates="specifications")


class ProductImage(Base):
    __tablename__ = "catalog_product_images"
    __table_args__ = (Index("ix_catalog_image_checksum", "checksum"), Index("ix_catalog_image_primary", "product_id", "is_primary"), Index("uq_catalog_approved_primary", "product_id", unique=True, postgresql_where=text("is_primary = true AND review_status = 'approved'"), sqlite_where=text("is_primary = 1 AND review_status = 'approved'")))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("catalog_products.id", ondelete="CASCADE"), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(String(512))
    source_name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(String(32), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    format: Mapped[str | None] = mapped_column(String(24))
    file_size: Mapped[int | None] = mapped_column(Integer)
    checksum: Mapped[str | None] = mapped_column(String(128))
    rights_status: Mapped[ImageRightsStatus] = mapped_column(String(32), default=ImageRightsStatus.UNKNOWN, nullable=False)
    quality_status: Mapped[ImageQualityStatus] = mapped_column(String(32), default=ImageQualityStatus.UNKNOWN, nullable=False)
    review_status: Mapped[ReviewStatus] = mapped_column(String(32), default=ReviewStatus.PENDING, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    icecat_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    access_level: Mapped[str | None] = mapped_column(String(100), nullable=True)
    match_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_brand: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_mpn: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_gtin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    license_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    product: Mapped[Product] = relationship(back_populates="images")

    @property
    def role(self) -> str:
        return "primary" if self.is_primary else "alternate"

    @property
    def card_url(self) -> str | None:
        from app.catalog.storage import catalog_storage
        return catalog_storage.generate_signed_url(self.storage_key) if self.storage_key else None

    @property
    def summary_url(self) -> str | None:
        from app.catalog.storage import catalog_storage
        if not self.storage_key:
            return None
        key = self.storage_key.replace("card.webp", "summary.webp")
        return catalog_storage.generate_signed_url(key)

    @property
    def detail_url(self) -> str | None:
        from app.catalog.storage import catalog_storage
        if not self.storage_key:
            return None
        key = self.storage_key.replace("card.webp", "detail.webp")
        return catalog_storage.generate_signed_url(key)

    @property
    def alt_text(self) -> str:
        product_name = self.product.canonical_name if self.product else "Product"
        category = self.product.category if self.product else "part"
        return f"{product_name} {category} image"


class PipelineLease(Base):
    __tablename__ = "catalog_pipeline_leases"
    job_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    token: Mapped[str] = mapped_column(String(100), nullable=False)



class ProductImageReview(Base):
    __tablename__ = "catalog_product_image_reviews"
    __table_args__ = (
        Index("ix_catalog_image_review_image", "image_id"),
        Index("ix_catalog_image_review_decision", "decision"),
        Index("ix_catalog_image_review_created", "created_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("catalog_product_images.id", ondelete="RESTRICT"), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    safe_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    reviewer_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    previous_rights_status: Mapped[str] = mapped_column(String(32), nullable=False)
    new_rights_status: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
    new_quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_review_status: Mapped[str] = mapped_column(String(32), nullable=False)
    new_review_status: Mapped[str] = mapped_column(String(32), nullable=False)
    proposed_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Store(Base):
    __tablename__ = "catalog_stores"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    country: Mapped[str] = mapped_column(String(2), default="SA", nullable=False)
    website: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    offers: Mapped[list["StoreOffer"]] = relationship(back_populates="store")


class StoreOffer(Base):
    __tablename__ = "catalog_store_offers"
    __table_args__ = (UniqueConstraint("store_id", "store_sku", name="uq_catalog_store_sku"), Index("ix_catalog_offer_product_store", "product_id", "store_id"), Index("ix_catalog_offer_observed", "observed_at"), CheckConstraint("regular_price >= 0", name="ck_catalog_regular_price_nonnegative"), CheckConstraint("sale_price >= 0", name="ck_catalog_sale_price_nonnegative"), CheckConstraint("sale_price IS NULL OR regular_price IS NULL OR sale_price <= regular_price", name="ck_catalog_sale_not_above_regular"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("catalog_products.id"), nullable=False)
    store_id: Mapped[int] = mapped_column(ForeignKey("catalog_stores.id"), nullable=False)
    store_sku: Mapped[str] = mapped_column(String(160), nullable=False)
    product_url: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="SAR", nullable=False)
    regular_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    stock_status: Mapped[StockStatus] = mapped_column(String(32), default=StockStatus.UNKNOWN, nullable=False)
    warranty: Mapped[str | None] = mapped_column(String(240))
    shipping_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    product: Mapped[Product] = relationship(back_populates="offers")
    store: Mapped[Store] = relationship(back_populates="offers")
    price_history: Mapped[list["PriceHistory"]] = relationship(back_populates="offer", cascade="all, delete-orphan")


class PriceHistory(Base):
    __tablename__ = "catalog_price_history"
    __table_args__ = (Index("ix_catalog_price_history_offer_observed", "offer_id", "observed_at"), CheckConstraint("price >= 0", name="ck_catalog_history_price_nonnegative"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("catalog_store_offers.id", ondelete="CASCADE"), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="SAR", nullable=False)
    availability: Mapped[StockStatus] = mapped_column(String(32), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    offer: Mapped[StoreOffer] = relationship(back_populates="price_history")


class ImportSource(Base):
    __tablename__ = "catalog_import_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    source_type: Mapped[SourceType] = mapped_column(String(32), nullable=False)
    rights_status: Mapped[ImageRightsStatus] = mapped_column(String(32), default=ImageRightsStatus.UNKNOWN, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImportBatch(Base):
    __tablename__ = "catalog_import_batches"
    __table_args__ = (Index("ix_catalog_batch_source_status", "source_id", "status"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("catalog_import_sources.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[ImportBatchStatus] = mapped_column(String(32), nullable=False)
    received_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ambiguous_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    staged_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    committed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImportError(Base):
    __tablename__ = "catalog_import_errors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("catalog_import_batches.id", ondelete="CASCADE"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str] = mapped_column(String(80), nullable=False)
    safe_message: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImportRecord(Base):
    __tablename__ = "catalog_import_records"
    __table_args__ = (
        UniqueConstraint("batch_id", "row_number", name="uq_catalog_import_record_row"),
        UniqueConstraint("batch_id", "record_checksum", name="uq_catalog_import_record_checksum"),
        Index("ix_catalog_import_record_batch_status", "batch_id", "validation_status", "review_status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("catalog_import_batches.id", ondelete="CASCADE"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    record_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_payload: Mapped[str] = mapped_column(Text, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(24), nullable=False)
    review_status: Mapped[str] = mapped_column(String(24), nullable=False)
    proposed_action: Mapped[str] = mapped_column(String(24), nullable=False)
    matched_product_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_products.id"))
    matched_store_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_stores.id"))
    matched_offer_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_store_offers.id"))
    safe_error_code: Mapped[str | None] = mapped_column(String(80))
    safe_error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
