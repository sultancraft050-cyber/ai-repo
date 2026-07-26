"""
Alembic migration: automated image pipeline fields and pipeline lease table.

Adds to catalog_product_images:
  - icecat_id, access_level, match_method
  - source_brand, source_mpn, source_gtin
  - license_metadata (JSON text)
  - retrieved_at

Creates catalog_pipeline_leases for distributed execution lock.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_automated_image_pipeline"
down_revision = "0003_product_image_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_cols = {c["name"] for c in inspector.get_columns("catalog_product_images")}

    new_cols = [
        ("icecat_id", sa.Integer(), {}),
        ("access_level", sa.String(100), {}),
        ("match_method", sa.String(100), {}),
        ("source_brand", sa.String(160), {}),
        ("source_mpn", sa.String(160), {}),
        ("source_gtin", sa.String(32), {}),
        ("license_metadata", sa.Text(), {}),
        ("retrieved_at", sa.DateTime(timezone=True), {}),
    ]
    for col_name, col_type, kwargs in new_cols:
        if col_name not in existing_cols:
            op.add_column("catalog_product_images", sa.Column(col_name, col_type, nullable=True, **kwargs))

    tables = inspector.get_table_names()
    if "catalog_pipeline_leases" not in tables:
        op.create_table(
            "catalog_pipeline_leases",
            sa.Column("job_name", sa.String(100), primary_key=True),
            sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("token", sa.String(100), nullable=False),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_cols = {c["name"] for c in inspector.get_columns("catalog_product_images")}
    for col_name in ("icecat_id", "access_level", "match_method", "source_brand",
                     "source_mpn", "source_gtin", "license_metadata", "retrieved_at"):
        if col_name in existing_cols:
            op.drop_column("catalog_product_images", col_name)
    tables = inspector.get_table_names()
    if "catalog_pipeline_leases" in tables:
        op.drop_table("catalog_pipeline_leases")
