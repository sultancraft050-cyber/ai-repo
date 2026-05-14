from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import logging
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from app.core.config import settings
from app.models.pricing import PriceOffer

logger = logging.getLogger("pc_builder.images")


@dataclass(frozen=True)
class ProcessedProductImage:
    source_url: str
    processed_image_url: str
    storage_path: str
    background_removed: bool


class ProductImageProcessor:
    def __init__(
        self,
        *,
        enabled: bool,
        storage_dir: str,
        public_base_url: str,
        max_bytes: int,
        object_storage_endpoint: str | None = None,
        object_storage_bucket: str | None = None,
        object_storage_access_key: str | None = None,
        object_storage_secret_key: str | None = None,
        object_storage_public_base_url: str | None = None,
    ) -> None:
        self.enabled = enabled
        self.storage_dir = Path(storage_dir) if storage_dir else None
        self.public_base_url = public_base_url.rstrip("/")
        self.max_bytes = max_bytes
        self.object_storage_endpoint = (object_storage_endpoint or "").rstrip("/")
        self.object_storage_bucket = object_storage_bucket or ""
        self.object_storage_access_key = object_storage_access_key or ""
        self.object_storage_secret_key = object_storage_secret_key or ""
        self.object_storage_public_base_url = (object_storage_public_base_url or "").rstrip("/")

    @classmethod
    def from_settings(cls) -> "ProductImageProcessor":
        return cls(
            enabled=settings.product_image_processing_enabled,
            storage_dir=settings.processed_image_storage_dir,
            public_base_url=settings.processed_image_public_base_url,
            max_bytes=settings.product_image_max_bytes,
            object_storage_endpoint=settings.object_storage_endpoint,
            object_storage_bucket=settings.object_storage_bucket,
            object_storage_access_key=settings.object_storage_access_key,
            object_storage_secret_key=settings.object_storage_secret_key,
            object_storage_public_base_url=settings.object_storage_public_base_url,
        )

    def process(self, image_url: str | None, *, canonical_key: str | None = None) -> ProcessedProductImage | None:
        has_local_storage = bool(self.storage_dir and self.public_base_url)
        has_object_storage = self._object_storage_configured()
        if not self.enabled or not image_url or not (has_local_storage or has_object_storage):
            return None
        if not _is_safe_image_url(image_url):
            return None

        try:
            from PIL import Image, ImageChops
        except Exception as error:  # noqa: BLE001 - optional dependency.
            logger.info("product_image_processing_unavailable reason=%s", type(error).__name__)
            return None

        try:
            raw = _fetch_image_bytes(image_url, self.max_bytes)
            background_removed = False
            try:
                from rembg import remove

                raw = remove(raw)
                background_removed = True
            except Exception as error:  # noqa: BLE001 - rembg is optional even when Pillow is present.
                logger.info("product_image_background_removal_skipped reason=%s", type(error).__name__)

            image = Image.open(BytesIO(raw)).convert("RGBA")
            image = _crop_to_content(image, ImageChops)
            image = _pad_to_aspect_ratio(image, Image, width=800, height=600)

            digest = sha256(f"{canonical_key or ''}:{image_url}".encode("utf-8")).hexdigest()[:24]
            filename = f"{digest}.png"
            buffer = BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            payload = buffer.getvalue()
            processed_url, storage_path = self._publish_image(filename, payload)

            return ProcessedProductImage(
                source_url=image_url,
                processed_image_url=processed_url,
                storage_path=storage_path,
                background_removed=background_removed,
            )
        except Exception as error:  # noqa: BLE001 - bad vendor images should not block ingestion.
            logger.info("product_image_processing_failed reason=%s", type(error).__name__)
            return None

    def _object_storage_configured(self) -> bool:
        return all(
            (
                self.object_storage_endpoint,
                self.object_storage_bucket,
                self.object_storage_access_key,
                self.object_storage_secret_key,
                self.object_storage_public_base_url,
            )
        )

    def _publish_image(self, filename: str, payload: bytes) -> tuple[str, str]:
        if self._object_storage_configured():
            try:
                import boto3

                client = boto3.client(
                    "s3",
                    endpoint_url=self.object_storage_endpoint,
                    aws_access_key_id=self.object_storage_access_key,
                    aws_secret_access_key=self.object_storage_secret_key,
                )
                key = f"products/{filename}"
                client.put_object(
                    Bucket=self.object_storage_bucket,
                    Key=key,
                    Body=payload,
                    ContentType="image/png",
                    CacheControl="public, max-age=31536000, immutable",
                )
                return f"{self.object_storage_public_base_url}/{key}", f"s3://{self.object_storage_bucket}/{key}"
            except Exception as error:  # noqa: BLE001 - fall back to local storage if available.
                logger.info("product_image_object_storage_skipped reason=%s", type(error).__name__)

        if not self.storage_dir or not self.public_base_url:
            raise ValueError("processed image storage is not configured")
        output_dir = self.storage_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename
        output_path.write_bytes(payload)
        return f"{self.public_base_url}/{filename}", str(output_path)


def attach_processed_image(offer: PriceOffer, processor: ProductImageProcessor | None = None) -> PriceOffer:
    processor = processor or ProductImageProcessor.from_settings()
    processed = processor.process(offer.image_url or offer.product.image_url, canonical_key=offer.product.canonical_key)
    if not processed:
        return offer

    return offer.model_copy(
        update={
            "processed_image_url": processed.processed_image_url,
            "product": offer.product.model_copy(
                update={"processed_image_url": processed.processed_image_url}
            ),
        },
        deep=True,
    )


def _is_safe_image_url(value: str) -> bool:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    return True


def _fetch_image_bytes(image_url: str, max_bytes: int) -> bytes:
    request = Request(
        image_url,
        headers={"User-Agent": "PCBuilderImageProcessor/1.0"},
    )
    with urlopen(request, timeout=12) as response:  # noqa: S310 - URL is validated and capped.
        content_type = response.headers.get("Content-Type", "").lower()
        if content_type and not content_type.startswith("image/"):
            raise ValueError("URL did not return an image content type")
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("image exceeds configured max bytes")
    return data


def _crop_to_content(image, image_chops):
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    alpha_bbox = image.getchannel("A").getbbox()
    if alpha_bbox:
        return image.crop(alpha_bbox)

    background = image.new(image.mode, image.size, image.getpixel((0, 0)))
    diff = image_chops.difference(image, background)
    bbox = diff.getbbox()
    return image.crop(bbox) if bbox else image


def _pad_to_aspect_ratio(image, image_module, *, width: int, height: int):
    image.thumbnail((width, height))
    canvas = image_module.new("RGBA", (width, height), (255, 255, 255, 255))
    x = (width - image.width) // 2
    y = (height - image.height) // 2
    canvas.alpha_composite(image, dest=(x, y))
    return canvas
