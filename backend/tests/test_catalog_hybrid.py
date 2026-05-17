from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.catalog import hybrid_graph_strategy
from app.models.catalog import CanonicalEvidenceRequest


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
