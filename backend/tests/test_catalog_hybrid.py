from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.catalog import hybrid_graph_strategy
from app.graph.pricing_repository import (
    _canonical_conflict_fields,
    _canonical_import_skip_reason,
    _catalog_row_from_staged_record,
)
from app.models.catalog import CanonicalEvidenceRequest, CanonicalImportCommitRequest


def test_hybrid_strategy_keeps_specs_and_prices_in_separate_layers() -> None:
    strategy = hybrid_graph_strategy()

    canonical_layer = next(layer for layer in strategy.data_layers if layer.layer == "Canonical Hardware Knowledge")
    pricing_layer = next(layer for layer in strategy.data_layers if layer.layer == "Saudi Market Pricing")

    assert "CanonicalProduct" in canonical_layer.graph_labels
    assert "RegionalPriceSnapshot" in pricing_layer.graph_labels
    assert "regional price" in canonical_layer.must_not_own
    assert "canonical socket" in pricing_layer.must_not_own
    assert any("Regional prices" in rule for rule in strategy.canonicalization_policy)


def test_canonical_evidence_request_is_source_gated_and_typed() -> None:
    request = CanonicalEvidenceRequest(
        product_id="CPU|AMD|RYZEN_7_7800X3D",
        source_name="BuildCores/OpenDB",
        evidence_type="canonical_spec",
        field="socket",
        value="AM5",
        trust_score=0.86,
    )

    assert request.evidence_type == "canonical_spec"
    assert request.trust_score == pytest.approx(0.86)


def test_unknown_canonical_evidence_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CanonicalEvidenceRequest(
            product_id="cpu:test",
            source_name="unknown",
            evidence_type="uncontrolled_mutation",
            field="socket",
            value="AM5",
        )


def test_canonical_import_request_caps_motherboard_batches() -> None:
    with pytest.raises(ValidationError):
        CanonicalImportCommitRequest(
            source_name="BuildCores/OpenDB",
            source_type="canonical_specs",
            category="Motherboard",
            batch_limit=100,
            commit=True,
        )


def test_clean_canonical_import_record_requires_license_and_specs() -> None:
    request = CanonicalImportCommitRequest(
        source_name="BuildCores/OpenDB",
        source_type="canonical_specs",
        category="CPU",
        batch_limit=25,
        commit=True,
    )
    clean_record = {
        "source_name": "BuildCores/OpenDB",
        "source_type": "canonical_specs",
        "category": "CPU",
        "name": "AMD Ryzen 7 7800X3D",
        "canonical_key": "CPU|AMD|RYZEN_7_7800X3D",
        "brand": "AMD",
        "identity_confidence": 0.94,
        "license_note": "Allowed canonical specs import for controlled founder use.",
        "spec_socket": "AM5",
        "spec_cores": 8,
        "spec_threads": 16,
        "spec_tdp_w": 120,
    }

    row = _catalog_row_from_staged_record(clean_record, "CPU")

    assert _canonical_import_skip_reason(record=clean_record, row=row, request=request) is None
    assert row.specs["socket"] == "AM5"


def test_canonical_import_rejects_records_without_attribution_license() -> None:
    request = CanonicalImportCommitRequest(
        source_name="BuildCores/OpenDB",
        source_type="canonical_specs",
        category="CPU",
    )
    record = {
        "source_name": "BuildCores/OpenDB",
        "source_type": "canonical_specs",
        "category": "CPU",
        "name": "AMD Ryzen 7 7800X3D",
        "canonical_key": "CPU|AMD|RYZEN_7_7800X3D",
        "identity_confidence": 0.94,
        "spec_socket": "AM5",
        "spec_cores": 8,
        "spec_threads": 16,
        "spec_tdp_w": 120,
    }
    row = _catalog_row_from_staged_record(record, "CPU")

    assert _canonical_import_skip_reason(record=record, row=row, request=request) == "missing license/usage note"


def test_canonical_import_detects_spec_conflicts_without_price_fields() -> None:
    existing = {"spec_socket": "AM4", "spec_cores": 8, "current_recommended_price": 1500}
    incoming = {"spec_socket": "AM5", "spec_cores": 8, "current_recommended_price": 999}

    assert _canonical_conflict_fields(existing, incoming) == ["spec_socket"]
