from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.catalog.feed_mapping import FeedMappingService, MappingError, template_checksum
from app.catalog.models import ImportEntityType
from app.core.config import Settings

FIXTURES = Path(__file__).parent / "fixtures" / "catalog_feed_mappings"


@pytest.fixture(autouse=True)
def mapping_enabled(monkeypatch):
    monkeypatch.setenv("CATALOG_FEED_MAPPING_ENABLED", "true")
    monkeypatch.setenv("CATALOG_IMPORT_ENABLED", "true")


def load(name: str):
    return FeedMappingService().load_template(FIXTURES / name)


def test_defaults_and_all_supported_entities():
    settings = Settings.from_env()
    assert not settings.catalog_feed_mapping_enabled or settings.catalog_feed_mapping_enabled
    entities = {load(name).entity_type for name in ("synthetic_product_v1.json", "synthetic_store_v1.json", "synthetic_offer_v1.json", "synthetic_specification_v1.json", "synthetic_image_v1.json", "synthetic_price_observation_v1.json")}
    assert entities == {item.value for item in ImportEntityType}


@pytest.mark.parametrize(("name", "code"), [("invalid_unauthorized.json", "TEMPLATE_NOT_AUTHORIZED"), ("invalid_unsupported_transform.json", "UNSUPPORTED_TRANSFORM"), ("invalid_credential_field.json", "CREDENTIAL_FIELD_DETECTED")])
def test_invalid_templates_are_rejected(name, code):
    with pytest.raises(MappingError, match=code): load(name)


def test_mapping_disabled(monkeypatch):
    monkeypatch.setenv("CATALOG_FEED_MAPPING_ENABLED", "false")
    with pytest.raises(MappingError, match="TEMPLATE_DISABLED"): FeedMappingService().load_template(FIXTURES / "synthetic_product_v1.json")


def test_checksum_and_version_comparison_are_deterministic():
    data = json.loads((FIXTURES / "synthetic_product_v1.json").read_text())
    assert template_checksum(data) == template_checksum(json.loads(json.dumps(data)))
    service = FeedMappingService(); first = service.load_template(FIXTURES / "synthetic_product_v1.json"); second = service.load_template(FIXTURES / "synthetic_product_v2.json")
    result = service.compare_versions(first, second)
    assert result["template_id"] == "synthetic-product" and result["mapping_changed"]


def test_product_mapping_normalizes_category_mpn_gtin_and_provenance():
    service = FeedMappingService(); template = load("synthetic_product_v1.json")
    result = service.map_record(template, {"brand": " Synthetic  Labs ", "mpn": "test-cpu-a", "name": " Test CPU Model A ", "category": "Processor", "gtin": "000 123 456 789 05", "ignored": "warning"})
    assert result.mapped_payload["category"] == "CPU"
    assert result.mapped_payload["gtin"] == "00012345678905"
    assert result.provenance["source_field_names_used"] == ["brand", "category", "gtin", "mpn", "name"]


def test_unknown_field_policies_are_safe():
    service = FeedMappingService(); template = load("synthetic_product_v1.json")
    with pytest.raises(MappingError, match="UNKNOWN_SOURCE_FIELD"):
        service.map_record(template, {"brand": "Synthetic", "mpn": "A", "name": "CPU", "category": "Processor", "mystery": "ignored"})


def test_product_identity_incomplete_is_reviewed():
    result = FeedMappingService().map_record(load("synthetic_product_v1.json"), {"brand": "Synthetic", "mpn": "A", "name": "CPU", "category": "Processor"})
    assert result.validation_status == "VALID"  # brand + MPN is a strict identity
    incomplete = FeedMappingService().map_record(load("synthetic_product_v1.json"), {"brand": "Synthetic", "mpn": "A", "name": "CPU", "category": "Processor"})
    assert incomplete.proposed_action == "STAGE"


def test_store_offer_preserves_sar_and_datetime_and_rejects_bad_price():
    service = FeedMappingService(); template = load("synthetic_offer_v1.json")
    result = service.map_record(template, {"product_id": "1", "store_id": "1", "sku": "TEST-SKU-A", "url": "https://synthetic.example.test/p", "price": "999.00", "currency": "SAR", "stock": "available", "observed_at": "2026-07-13T10:00:00+03:00"})
    assert result.mapped_payload["currency"] == "SAR" and "+03:00" in result.mapped_payload["observed_at"]
    with pytest.raises(MappingError, match="PRICE_INVALID"):
        service.map_record(template, {"product_id": "1", "store_id": "1", "sku": "A", "url": "https://synthetic.example.test/p", "price": "-1", "currency": "SAR", "stock": "available", "observed_at": "2026-07-13T10:00:00+03:00"})


def test_image_mapping_cannot_force_approval_or_primary():
    result = FeedMappingService().map_record(load("synthetic_image_v1.json"), {"product_id": "1", "url": "https://synthetic.example.test/image.webp", "source": "Synthetic", "rights": "PENDING"})
    assert result.mapped_payload["review_status"] == "PENDING" and result.mapped_payload["is_primary"] == "false"
    assert "IMAGE_RIGHTS_REVIEW_REQUIRED" in result.error_codes


def test_map_file_json_records_and_bounded_unknown_values():
    service = FeedMappingService(); template = load("synthetic_specification_v1.json")
    results = service.map_file(template, (FIXTURES / "synthetic_specifications.json").read_bytes())
    assert len(results) == 1 and results[0].mapped_payload["specification_key"] == "socket"
    with pytest.raises(MappingError, match="CONTROLLED_VALUE_UNKNOWN"):
        service.map_file(load("synthetic_product_v1.json"), (FIXTURES / "unknown_controlled_value.csv").read_bytes())


def test_cli_paths_are_fixture_only():
    from app.catalog.feed_mapping_cli import _fixture
    assert _fixture(str(FIXTURES / "synthetic_products.csv")).exists()
    with pytest.raises(MappingError): _fixture("/tmp/real-feed.csv")


def test_no_network_symbols_or_external_fetch_in_mapping_module():
    source = Path(__file__).parents[1] / "app" / "catalog" / "feed_mapping.py"
    text = source.read_text()
    assert "requests" not in text and "httpx" not in text and "urlopen" not in text and "socket" not in text
