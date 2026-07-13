"""add staged catalog import records"""
from alembic import op
import sqlalchemy as sa

revision = "0002_catalog_import_staging"
down_revision = "0001_catalog_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    batch_columns = {column["name"] for column in inspector.get_columns("catalog_import_batches")}
    missing_columns = [
        name for name in ("ambiguous_count", "staged_count", "committed_count")
        if name not in batch_columns
    ]
    if missing_columns:
        with op.batch_alter_table("catalog_import_batches") as batch:
            for name in missing_columns:
                batch.add_column(sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    if "entity_type" not in batch_columns:
        with op.batch_alter_table("catalog_import_batches") as batch:
            batch.add_column(sa.Column("entity_type", sa.String(48), nullable=False, server_default="PRODUCT"))
    if "catalog_import_records" in inspector.get_table_names():
        return
    op.create_table(
        "catalog_import_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("catalog_import_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(48), nullable=False),
        sa.Column("record_checksum", sa.String(64), nullable=False),
        sa.Column("normalized_payload", sa.Text(), nullable=False),
        sa.Column("validation_status", sa.String(24), nullable=False),
        sa.Column("review_status", sa.String(24), nullable=False),
        sa.Column("proposed_action", sa.String(24), nullable=False),
        sa.Column("matched_product_id", sa.Integer(), sa.ForeignKey("catalog_products.id")),
        sa.Column("matched_store_id", sa.Integer(), sa.ForeignKey("catalog_stores.id")),
        sa.Column("matched_offer_id", sa.Integer(), sa.ForeignKey("catalog_store_offers.id")),
        sa.Column("safe_error_code", sa.String(80)),
        sa.Column("safe_error_message", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("batch_id", "row_number", name="uq_catalog_import_record_row"),
        sa.UniqueConstraint("batch_id", "record_checksum", name="uq_catalog_import_record_checksum"),
    )
    op.create_index("ix_catalog_import_record_batch_status", "catalog_import_records", ["batch_id", "validation_status", "review_status"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "catalog_import_records" in inspector.get_table_names():
        indexes = {index["name"] for index in inspector.get_indexes("catalog_import_records")}
        if "ix_catalog_import_record_batch_status" in indexes:
            op.drop_index("ix_catalog_import_record_batch_status", table_name="catalog_import_records")
        op.drop_table("catalog_import_records")
    batch_columns = {column["name"] for column in inspector.get_columns("catalog_import_batches")}
    removable = [name for name in ("committed_count", "staged_count", "ambiguous_count", "entity_type") if name in batch_columns]
    if removable:
        with op.batch_alter_table("catalog_import_batches") as batch:
            for name in removable:
                batch.drop_column(name)
