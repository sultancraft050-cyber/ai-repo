from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


def _load_local_env() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_local_env()


@dataclass(frozen=True)
class Settings:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_database: str
    cors_origins: tuple[str, ...]
    frontend_url: str
    backend_url: str
    environment: str
    market_data_mode: str
    log_level: str
    public_analytics_enabled: bool
    public_rate_limit_window_seconds: int
    public_rate_limit_max_requests: int
    pricing_scheduler_enabled: bool
    pricing_top_refresh_seconds: int
    pricing_standard_refresh_seconds: int
    product_image_processing_enabled: bool
    processed_image_storage_dir: str
    processed_image_public_base_url: str
    product_image_max_bytes: int
    object_storage_endpoint: str | None
    object_storage_bucket: str | None
    object_storage_access_key: str | None
    object_storage_secret_key: str | None
    object_storage_public_base_url: str | None
    autonomous_agents_enabled: bool
    autonomous_agent_interval_seconds: int
    autonomous_agent_max_products: int
    catalog_v2_enabled: bool
    catalog_writes_enabled: bool
    catalog_import_enabled: bool
    catalog_database_url: str | None
    auth_required: bool
    viewer_api_key: str | None
    analyst_api_key: str | None
    admin_api_key: str | None
    super_admin_api_key: str | None
    serpapi_key: str | None
    ebay_browse_token: str | None
    bestbuy_api_key: str | None
    amazon_paapi_access_key: str | None
    amazon_paapi_secret_key: str | None
    amazon_paapi_partner_tag: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
        return cls(
            neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", "neo4j-password"),
            neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
            cors_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
            frontend_url=os.getenv("FRONTEND_URL", "http://127.0.0.1:3000"),
            backend_url=os.getenv("BACKEND_URL", "http://127.0.0.1:8000"),
            environment=os.getenv("ENVIRONMENT", "development"),
            market_data_mode=os.getenv("MARKET_DATA_MODE", "free"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            public_analytics_enabled=os.getenv("PUBLIC_ANALYTICS_ENABLED", "true").lower() in {"1", "true", "yes"},
            public_rate_limit_window_seconds=int(os.getenv("PUBLIC_RATE_LIMIT_WINDOW_SECONDS", "60")),
            public_rate_limit_max_requests=int(os.getenv("PUBLIC_RATE_LIMIT_MAX_REQUESTS", "120")),
            pricing_scheduler_enabled=os.getenv("PRICING_SCHEDULER_ENABLED", "false").lower()
            in {"1", "true", "yes"},
            pricing_top_refresh_seconds=int(os.getenv("PRICING_TOP_REFRESH_SECONDS", "3600")),
            pricing_standard_refresh_seconds=int(os.getenv("PRICING_STANDARD_REFRESH_SECONDS", "21600")),
            product_image_processing_enabled=os.getenv("PRODUCT_IMAGE_PROCESSING_ENABLED", "false").lower()
            in {"1", "true", "yes"},
            processed_image_storage_dir=os.getenv("PROCESSED_IMAGE_STORAGE_DIR", ""),
            processed_image_public_base_url=os.getenv("PROCESSED_IMAGE_PUBLIC_BASE_URL", ""),
            product_image_max_bytes=int(os.getenv("PRODUCT_IMAGE_MAX_BYTES", "5000000")),
            object_storage_endpoint=os.getenv("OBJECT_STORAGE_ENDPOINT"),
            object_storage_bucket=os.getenv("OBJECT_STORAGE_BUCKET"),
            object_storage_access_key=os.getenv("OBJECT_STORAGE_ACCESS_KEY"),
            object_storage_secret_key=os.getenv("OBJECT_STORAGE_SECRET_KEY"),
            object_storage_public_base_url=os.getenv("OBJECT_STORAGE_PUBLIC_BASE_URL"),
            auth_required=os.getenv("AUTH_REQUIRED", "true").lower() in {"1", "true", "yes"},
            viewer_api_key=os.getenv("VIEWER_API_KEY"),
            analyst_api_key=os.getenv("ANALYST_API_KEY"),
            admin_api_key=os.getenv("ADMIN_API_KEY"),
            super_admin_api_key=os.getenv("SUPER_ADMIN_API_KEY"),
            serpapi_key=os.getenv("SERPAPI_KEY"),
            ebay_browse_token=os.getenv("EBAY_BROWSE_TOKEN"),
            bestbuy_api_key=os.getenv("BESTBUY_API_KEY"),
            amazon_paapi_access_key=os.getenv("AMAZON_PAAPI_ACCESS_KEY"),
            amazon_paapi_secret_key=os.getenv("AMAZON_PAAPI_SECRET_KEY"),
            amazon_paapi_partner_tag=os.getenv("AMAZON_PAAPI_PARTNER_TAG"),
            autonomous_agents_enabled=os.getenv("AUTONOMOUS_AGENTS_ENABLED", "false").lower()
            in {"1", "true", "yes"},
            autonomous_agent_interval_seconds=int(os.getenv("AUTONOMOUS_AGENT_INTERVAL_SECONDS", "900")),
            autonomous_agent_max_products=int(os.getenv("AUTONOMOUS_AGENT_MAX_PRODUCTS", "6")),
            catalog_v2_enabled=os.getenv("CATALOG_V2_ENABLED", "false").lower() in {"1", "true", "yes"},
            catalog_writes_enabled=os.getenv("CATALOG_WRITES_ENABLED", "false").lower() in {"1", "true", "yes"},
            catalog_import_enabled=os.getenv("CATALOG_IMPORT_ENABLED", "false").lower() in {"1", "true", "yes"},
            catalog_database_url=os.getenv("CATALOG_DATABASE_URL"),
        )


settings = Settings.from_env()
