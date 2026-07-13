"""add append-only product image review history"""
from alembic import op
import sqlalchemy as sa

revision = "0003_product_image_reviews"
down_revision = "0002_catalog_import_staging"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "catalog_product_image_reviews" in inspector.get_table_names():
        return
    op.create_table(
        "catalog_product_image_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("image_id", sa.Integer(), sa.ForeignKey("catalog_product_images.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("safe_reason", sa.String(500), nullable=False),
        sa.Column("reviewer_identifier", sa.String(120), nullable=False),
        sa.Column("previous_rights_status", sa.String(32), nullable=False),
        sa.Column("new_rights_status", sa.String(32), nullable=False),
        sa.Column("previous_quality_status", sa.String(32), nullable=False),
        sa.Column("new_quality_status", sa.String(32), nullable=False),
        sa.Column("previous_review_status", sa.String(32), nullable=False),
        sa.Column("new_review_status", sa.String(32), nullable=False),
        sa.Column("proposed_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_catalog_image_review_image", "catalog_product_image_reviews", ["image_id"])
    op.create_index("ix_catalog_image_review_decision", "catalog_product_image_reviews", ["decision"])
    op.create_index("ix_catalog_image_review_created", "catalog_product_image_reviews", ["created_at"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "catalog_product_image_reviews" not in inspector.get_table_names():
        return
    for name in ("ix_catalog_image_review_created", "ix_catalog_image_review_decision", "ix_catalog_image_review_image"):
        if name in {item["name"] for item in inspector.get_indexes("catalog_product_image_reviews")}:
            op.drop_index(name, table_name="catalog_product_image_reviews")
    op.drop_table("catalog_product_image_reviews")
