"""
Catalog GCS storage service.

Rules:
- The bucket is ALWAYS private. No public access is ever granted.
- Signed URLs are generated via IAM Credentials API (signBlob) using the
  Cloud Run service account identity — no private key files are downloaded
  or stored.
- When signed URL generation is unavailable (e.g. no GCS credentials at all),
  returns None so callers can fall back to the category placeholder.
- Bucket names, object keys, and signed URLs are NEVER written to logs.
"""
from __future__ import annotations

import datetime
import logging
import os
from hashlib import sha256

logger = logging.getLogger("pc_builder.catalog.storage")


def _get_gcs_client():
    """
    Returns an authenticated GCS client using Application Default Credentials.
    On Cloud Run, ADC resolves to the attached Service Account automatically.
    Raises ImportError when google-cloud-storage is not installed.
    Raises google.auth.exceptions.DefaultCredentialsError when no credentials found.
    """
    from google.cloud import storage as gcs
    import google.auth
    from google.auth.transport.requests import Request as AuthRequest

    credentials, project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(AuthRequest())
    return gcs.Client(project=project, credentials=credentials)


def _get_service_account_email() -> str | None:
    """
    Resolves the runtime service account email for signBlob without storing a key.
    Uses the GCE metadata server on Cloud Run / GCE.
    Returns None if not running on Google Cloud infrastructure.
    """
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email",
            headers={"Metadata-Flavor": "Google"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.read().decode("utf-8").strip()
    except Exception:
        return None


class CatalogStorage:
    """
    Safe wrapper around Google Cloud Storage for private catalog media.

    Signed URLs are generated using signBlob via IAM Credentials API,
    which works without any JSON key file on Cloud Run.

    When signing is unavailable, returns None — callers must use the
    category placeholder instead. NEVER returns an unsigned direct bucket URL.
    """

    REQUIRED_BUCKET = "pc-recomendation-catalog-media-1025898878832"
    SIGNED_URL_EXPIRATION_MINUTES = 30

    def __init__(self) -> None:
        self._bucket_name = os.getenv("CATALOG_MEDIA_BUCKET", self.REQUIRED_BUCKET)
        self._client = None
        self._sa_email: str | None = None

    @property
    def is_configured(self) -> bool:
        # Returns True when the bucket name is the required one.
        # If env var is set to a different name, this is a misconfiguration.
        return self._bucket_name == self.REQUIRED_BUCKET

    def validate_bucket_name(self) -> bool:
        """Validates that the bucket name matches the required target."""
        return self._bucket_name == self.REQUIRED_BUCKET

    def _client_and_email(self):
        """Lazy-initialise GCS client and service account email."""
        if self._client is None:
            try:
                self._client = _get_gcs_client()
                self._sa_email = _get_service_account_email()
            except Exception as exc:  # noqa: BLE001
                logger.warning("gcs_client_unavailable reason=%s", type(exc).__name__)
                return None, None
        return self._client, self._sa_email

    # ------------------------------------------------------------------
    # Object key helpers — no signed URLs here, just key construction
    # ------------------------------------------------------------------

    @staticmethod
    def card_key(product_id: int, checksum: str) -> str:
        return f"products/{product_id}/{checksum}/card.webp"

    @staticmethod
    def summary_key(product_id: int, checksum: str) -> str:
        return f"products/{product_id}/{checksum}/summary.webp"

    @staticmethod
    def detail_key(product_id: int, checksum: str) -> str:
        return f"products/{product_id}/{checksum}/detail.webp"

    @staticmethod
    def original_key(product_id: int, checksum: str, ext: str) -> str:
        return f"products/{product_id}/{checksum}/original.{ext}"

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def upload_object(self, data: bytes, key: str, content_type: str) -> None:
        """Upload bytes to a private object. Raises on failure."""
        if not self.is_configured:
            raise RuntimeError("GCS storage is not configured or bucket name does not match required bucket.")
        client, _ = self._client_and_email()
        if client is None:
            raise RuntimeError("GCS client could not be initialised.")
        bucket = client.bucket(self._bucket_name)
        blob = bucket.blob(key)
        blob.upload_from_string(data, content_type=content_type)

    def object_exists(self, key: str) -> bool:
        """Check whether an object exists without downloading it."""
        if not self.is_configured:
            return False
        client, _ = self._client_and_email()
        if client is None:
            return False
        try:
            bucket = client.bucket(self._bucket_name)
            blob = bucket.blob(key)
            return blob.exists()
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------
    # Signed URL — mandatory; never falls back to unsigned public URL
    # ------------------------------------------------------------------

    def generate_signed_url(self, key: str | None) -> str | None:
        """
        Generate a short-lived signed URL for a private object.

        Returns None when:
        - key is None/empty
        - bucket is not configured
        - GCS client is unavailable
        - signing fails for any reason

        NEVER returns an unsigned direct URL. Callers must handle None
        by showing the category placeholder.
        """
        if not key or not self.is_configured:
            return None
        client, sa_email = self._client_and_email()
        if client is None:
            return None
        try:
            bucket = client.bucket(self._bucket_name)
            blob = bucket.blob(key)
            expiration = datetime.timedelta(minutes=self.SIGNED_URL_EXPIRATION_MINUTES)
            kwargs: dict = dict(expiration=expiration, method="GET", version="v4")
            if sa_email:
                # Cloud Run / GCE: sign using IAM signBlob (no private key needed)
                kwargs["service_account_email"] = sa_email
                kwargs["access_token"] = client._credentials.token  # type: ignore[attr-defined]
            url = blob.generate_signed_url(**kwargs)
            # Log only that signing succeeded, NEVER the URL itself
            logger.debug("signed_url_generated key_prefix=%s", key[:24])
            return url
        except Exception as exc:  # noqa: BLE001
            logger.warning("signed_url_failed reason=%s", type(exc).__name__)
            return None


catalog_storage = CatalogStorage()
