from __future__ import annotations

import os
import sys
import urllib.parse
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.catalog.database import build_db_url
from app.catalog.models import (
    Product, ProductSpecification, ProductImage, Store, StoreOffer, PriceHistory,
    ImportSource, ImportBatch, ImportRecord, ApprovalStatus, ReviewStatus, StockStatus,
    SourceType, ImageRightsStatus, ImportValidationStatus, ImportReviewStatus
)
from app.catalog.repository import CatalogRepository

def get_row_counts(session: Session) -> dict[str, int]:
    return {
        "Product": session.scalar(select(func.count(Product.id))) or 0,
        "ProductSpecification": session.scalar(select(func.count(ProductSpecification.id))) or 0,
        "ProductImage": session.scalar(select(func.count(ProductImage.id))) or 0,
        "Store": session.scalar(select(func.count(Store.id))) or 0,
        "StoreOffer": session.scalar(select(func.count(StoreOffer.id))) or 0,
        "PriceHistory": session.scalar(select(func.count(PriceHistory.id))) or 0,
        "ImportSource": session.scalar(select(func.count(ImportSource.id))) or 0,
        "ImportBatch": session.scalar(select(func.count(ImportBatch.id))) or 0,
        "ImportRecord": session.scalar(select(func.count(ImportRecord.id))) or 0,
    }

def main() -> None:
    enabled = os.getenv("CATALOG_CLOUD_VERIFICATION_ENABLED", "false").lower() in {"1", "true", "yes"}
    if not enabled:
        print("ERROR: CATALOG_CLOUD_VERIFICATION_ENABLED must be set to 'true'.")
        sys.exit(1)

    db_url = build_db_url()
    if not db_url:
        print("ERROR: Database URL not configured.")
        sys.exit(1)

    if not db_url.startswith("postgresql"):
        print("ERROR: SQLite is not permitted for this verification.")
        sys.exit(1)

    parsed = urllib.parse.urlparse(db_url)
    db_name = parsed.path.strip("/")
    if db_name != "catalog":
        print(f"ERROR: Database name must be 'catalog' (got '{db_name}').")
        sys.exit(1)

    host = parsed.hostname or ""
    if host != "127.0.0.1":
        print(f"ERROR: Database host must be '127.0.0.1' through the local proxy (got '{host}').")
        sys.exit(1)

    print("INFO: Starting Cloud SQL synthetic verification...")
    engine = create_engine(db_url)
    
    source = None
    batch = None
    record = None
    p1 = None
    p2 = None
    s1 = None
    s2 = None
    s3 = None
    img = None
    store = None
    offer1 = None
    offer2 = None

    with Session(engine) as session:
        baselines = get_row_counts(session)
        print("INFO: Baseline row counts:", baselines)

        try:
            # Ingestion Source & Batch
            now = datetime.now(timezone.utc)
            source = ImportSource(
                name="CLOUDSQL-VERIFY-20260718-source",
                source_type=SourceType.JSON.value,
                rights_status=ImageRightsStatus.APPROVED.value,
                active=True,
                created_at=now,
                updated_at=now
            )
            session.add(source)
            session.flush()

            batch = ImportBatch(
                source_id=source.id,
                entity_type="PRODUCT",
                status="completed",
                created_at=now,
                updated_at=now
            )
            session.add(batch)
            session.flush()

            record = ImportRecord(
                batch_id=batch.id,
                row_number=1,
                entity_type="PRODUCT",
                record_checksum="CLOUDSQL-VERIFY-20260718-checksum",
                normalized_payload='{"test": true}',
                validation_status=ImportValidationStatus.VALID.value,
                review_status=ImportReviewStatus.APPROVED.value,
                proposed_action="create",
                created_at=now,
                updated_at=now
            )
            session.add(record)
            session.flush()

            # Create 2 products
            p1 = Product(
                category="CPU",
                brand="Synthetic Brand",
                normalized_brand="synthetic brand",
                manufacturer_part_number="SYN-CPU-CLOUDSQL-VERIFY-1",
                gtin="9999999999991",
                canonical_name="CPU CLOUDSQL-VERIFY-20260718-1",
                slug="cpu-cloudsql-verify-20260718-1",
                approval_status=ApprovalStatus.APPROVED,
                created_at=now,
                updated_at=now
            )
            p2 = Product(
                category="CPU",
                brand="Synthetic Brand",
                normalized_brand="synthetic brand",
                manufacturer_part_number="SYN-CPU-CLOUDSQL-VERIFY-2",
                gtin="9999999999992",
                canonical_name="CPU CLOUDSQL-VERIFY-20260718-2",
                slug="cpu-cloudsql-verify-20260718-2",
                approval_status=ApprovalStatus.APPROVED,
                created_at=now,
                updated_at=now
            )
            session.add_all([p1, p2])
            session.flush()

            # Specifications
            s1 = ProductSpecification(
                product_id=p1.id,
                specification_key="socket",
                normalized_value="AM5",
                display_value="AM5",
                created_at=now,
                updated_at=now
            )
            s2 = ProductSpecification(
                product_id=p1.id,
                specification_key="core_count",
                normalized_value="8",
                display_value="8 Cores",
                created_at=now,
                updated_at=now
            )
            s3 = ProductSpecification(
                product_id=p2.id,
                specification_key="socket",
                normalized_value="LGA1700",
                display_value="LGA1700",
                created_at=now,
                updated_at=now
            )
            session.add_all([s1, s2, s3])
            session.flush()

            # Image Metadata
            img = ProductImage(
                product_id=p1.id,
                source_url="https://fixture.invalid/image1.jpg",
                source_name="CLOUDSQL-VERIFY-20260718-source",
                source_type=SourceType.JSON.value,
                rights_status="approved",
                review_status=ReviewStatus.APPROVED,
                quality_status="acceptable",
                is_primary=True,
                created_at=now,
                updated_at=now
            )
            session.add(img)
            session.flush()

            # Store & Offers
            store = Store(
                name="Verify Store",
                slug="verify-store",
                country="SA",
                status="active",
                created_at=now,
                updated_at=now
            )
            session.add(store)
            session.flush()

            offer1 = StoreOffer(
                product_id=p1.id,
                store_id=store.id,
                store_sku="SYN-SKU-VERIFY-1",
                product_url="https://fixture.invalid/product1",
                currency="SAR",
                regular_price=Decimal("1000.00"),
                sale_price=Decimal("950.00"),
                stock_status=StockStatus.IN_STOCK,
                observed_at=now,
                created_at=now,
                updated_at=now
            )
            offer2 = StoreOffer(
                product_id=p1.id,
                store_id=store.id,
                store_sku="SYN-SKU-VERIFY-2",
                product_url="https://fixture.invalid/product2",
                currency="SAR",
                regular_price=Decimal("980.00"),
                sale_price=None,
                stock_status=StockStatus.IN_STOCK,
                observed_at=now,
                created_at=now,
                updated_at=now
            )
            session.add_all([offer1, offer2])
            session.flush()

            # Price History
            ph1 = PriceHistory(
                offer_id=offer1.id,
                price=Decimal("1000.00"),
                currency="SAR",
                availability=StockStatus.IN_STOCK,
                observed_at=now - timedelta(days=2),
                created_at=now
            )
            ph2 = PriceHistory(
                offer_id=offer1.id,
                price=Decimal("950.00"),
                currency="SAR",
                availability=StockStatus.IN_STOCK,
                observed_at=now,
                created_at=now
            )
            session.add_all([ph1, ph2])
            session.flush()

            session.commit()
            print("INFO: Inserted synthetic verification records successfully.")

            # Verification Reads
            repo = CatalogRepository(session)
            db_p1 = repo.get_product(p1.id)
            assert db_p1 is not None, "Product 1 not found in read check"
            assert len(db_p1.specifications) == 2, f"Expected 2 specs, got {len(db_p1.specifications)}"
            
            db_images = repo.list_approved_images(p1.id)
            assert len(db_images) == 1, f"Expected 1 image, got {len(db_images)}"
            assert db_images[0].source_url == "https://fixture.invalid/image1.jpg"

            db_offers = repo.list_current_offers(p1.id)
            assert len(db_offers) == 2, f"Expected 2 offers, got {len(db_offers)}"

            cheapest = repo.cheapest_sar_offer(p1.id)
            assert cheapest is not None, "Cheapest offer not found"
            assert cheapest.sale_price == Decimal("950.00"), f"Expected 950.00, got {cheapest.sale_price}"

            # Verify Duplicate Rejection Constraint
            duplicate_p = Product(
                category="CPU",
                brand="Synthetic Brand",
                normalized_brand="synthetic brand",
                manufacturer_part_number="SYN-CPU-CLOUDSQL-VERIFY-1",
                gtin="9999999999991",
                canonical_name="CPU CLOUDSQL-VERIFY-20260718-DUP",
                slug="cpu-cloudsql-verify-20260718-dup",
                approval_status=ApprovalStatus.APPROVED,
                created_at=now,
                updated_at=now
            )
            session.add(duplicate_p)
            try:
                session.commit()
                raise AssertionError("Duplicate GTIN constraint did not trigger database IntegrityError!")
            except Exception:
                session.rollback()
                print("INFO: Constraint duplicate rejection check passed successfully.")

            print("INFO: All synthetic read and constraint checks passed.")

        finally:
            print("INFO: Cleaning up synthetic verification records...")
            try:
                if offer1 and offer1.id:
                    session.execute(
                        PriceHistory.__table__.delete().where(PriceHistory.offer_id.in_([offer1.id, offer2.id]))
                    )
                if offer1:
                    session.delete(session.get(StoreOffer, offer1.id))
                if offer2:
                    session.delete(session.get(StoreOffer, offer2.id))
                if store:
                    session.delete(session.get(Store, store.id))
                if img:
                    session.delete(session.get(ProductImage, img.id))
                if s1:
                    session.delete(session.get(ProductSpecification, s1.id))
                if s2:
                    session.delete(session.get(ProductSpecification, s2.id))
                if s3:
                    session.delete(session.get(ProductSpecification, s3.id))
                if p1:
                    session.delete(session.get(Product, p1.id))
                if p2:
                    session.delete(session.get(Product, p2.id))
                if record:
                    session.delete(session.get(ImportRecord, record.id))
                if batch:
                    session.delete(session.get(ImportBatch, batch.id))
                if source:
                    session.delete(session.get(ImportSource, source.id))
                session.commit()
            except Exception as e:
                session.rollback()
                print(f"ERROR: Cleanup failed: {e}")

            # Final counts comparison
            finals = get_row_counts(session)
            print("INFO: Post-cleanup row counts:", finals)
            for k in baselines:
                assert baselines[k] == finals[k], f"Row count mismatch for {k}: baseline={baselines[k]}, final={finals[k]}"

            print("SYNTHETIC_CLOUD_SQL_VERIFICATION_PASSED")

if __name__ == "__main__":
    main()
