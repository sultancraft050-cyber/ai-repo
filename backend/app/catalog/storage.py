from __future__ import annotations

import os

class CatalogStorage:
    def __init__(self) -> None:
        self.bucket_name = os.getenv("CATALOG_MEDIA_BUCKET", "pc-recomendation-catalog-media-1025898878832")

    @property
    def is_configured(self) -> bool:
        return bool(os.getenv("CATALOG_MEDIA_BUCKET"))

    def validate_bucket_name(self) -> bool:
        """Validates that the bucket name matches the required target."""
        return self.bucket_name == "pc-recomendation-catalog-media-1025898878832"

    def get_object_metadata(self, object_key: str) -> dict[str, str] | None:
        """Gets safe metadata representation of an object key without downloading image bytes."""
        if not self.is_configured:
            return None
        return {
            "bucket": self.bucket_name,
            "key": object_key,
            "url": f"gs://{self.bucket_name}/{object_key}"
        }

catalog_storage = CatalogStorage()
