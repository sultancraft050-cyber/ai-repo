from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_database: str
    cors_origins: tuple[str, ...]
    frontend_url: str
    backend_url: str
    log_level: str
    pricing_scheduler_enabled: bool
    pricing_top_refresh_seconds: int
    pricing_standard_refresh_seconds: int
    autonomous_agents_enabled: bool
    autonomous_agent_interval_seconds: int
    autonomous_agent_max_products: int
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
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            pricing_scheduler_enabled=os.getenv("PRICING_SCHEDULER_ENABLED", "true").lower()
            in {"1", "true", "yes"},
            pricing_top_refresh_seconds=int(os.getenv("PRICING_TOP_REFRESH_SECONDS", "3600")),
            pricing_standard_refresh_seconds=int(os.getenv("PRICING_STANDARD_REFRESH_SECONDS", "21600")),
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
            autonomous_agents_enabled=os.getenv("AUTONOMOUS_AGENTS_ENABLED", "true").lower()
            in {"1", "true", "yes"},
            autonomous_agent_interval_seconds=int(os.getenv("AUTONOMOUS_AGENT_INTERVAL_SECONDS", "900")),
            autonomous_agent_max_products=int(os.getenv("AUTONOMOUS_AGENT_MAX_PRODUCTS", "6")),
        )


settings = Settings.from_env()
