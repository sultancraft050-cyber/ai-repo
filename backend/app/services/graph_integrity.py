from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.graph.ops_repository import Neo4jOpsRepository
from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.ops import ApprovalItem
from app.models.pricing import (
    CPUDuplicateCandidate,
    CPUDuplicateReport,
    CanonicalMergePreviewResponse,
    ProductSearchResult,
)
from app.services.pricing_normalization import cpu_model_key_from_title
from app.services.region_config import normalize_region


class GraphIntegrityService:
    def __init__(self, pricing_repository: Neo4jPricingRepository, ops_repository: Neo4jOpsRepository | None = None) -> None:
        self.pricing_repository = pricing_repository
        self.ops_repository = ops_repository

    def cpu_duplicates(self, *, region: str = "SA", trace_id: str | None = None) -> CPUDuplicateReport:
        region = normalize_region(region)
        products = self.pricing_repository.search_products(q="", category="CPU", region=region, limit=500)
        groups: dict[str, list[ProductSearchResult]] = defaultdict(list)
        for product in products:
            cpu_key = cpu_canonical_identity(product)
            if cpu_key:
                groups[cpu_key].append(product)

        candidates: list[CPUDuplicateCandidate] = []
        approvals_created = 0
        for canonical_cpu_key, group in sorted(groups.items()):
            distinct_ids = sorted({item.id for item in group})
            if len(distinct_ids) < 2:
                continue
            candidate = self._candidate(canonical_cpu_key, group)
            if candidate.approval_required and self.ops_repository:
                approval = self._ensure_merge_approval(candidate, region=region, trace_id=trace_id)
                if approval:
                    approvals_created += 1
                    candidate = candidate.model_copy(update={"approval_id": approval.id})
            candidates.append(candidate)
        return CPUDuplicateReport(
            region=region,
            candidates=candidates,
            approval_items_created=approvals_created,
            trace_id=trace_id,
        )

    def merge_preview(
        self,
        *,
        product_ids: list[str],
        region: str = "SA",
        trace_id: str | None = None,
    ) -> CanonicalMergePreviewResponse:
        region = normalize_region(region)
        facts = [self.pricing_repository.product_merge_facts(product_id, region=region) for product_id in product_ids]
        facts = [fact for fact in facts if fact]
        if not facts:
            return CanonicalMergePreviewResponse(
                proposed_canonical_product={},
                relationships_to_preserve={},
                price_snapshots_to_preserve=0,
                vendors_to_preserve=0,
                field_evidence_to_preserve=0,
                audit_events_to_preserve=0,
                risks=["No matching products were found; preview cannot be executed."],
                rollback_plan="No rollback needed because no merge would be performed.",
                approval_required=True,
            )

        canonical_groups: dict[str, list[ProductSearchResult]] = defaultdict(list)
        for fact in facts:
            product = ProductSearchResult(
                id=fact["id"],
                canonical_key=fact.get("canonical_key"),
                name=fact["name"],
                brand=fact.get("brand"),
                category=fact.get("category") or "CPU",
                model=fact.get("model"),
                region=region,
            )
            key = cpu_canonical_identity(product)
            if key:
                canonical_groups[key].append(product)

        canonical_key = max(canonical_groups, key=lambda key: len(canonical_groups[key])) if canonical_groups else None
        target = self._proposed_target(facts, canonical_key)
        counts = {
            "HAS_PRICE": sum(int(fact.get("price_snapshot_count", 0)) for fact in facts),
            "SOLD_BY": len({vendor for fact in facts for vendor in fact.get("vendors", [])}),
            "HAS_FIELD_EVIDENCE": sum(int(fact.get("field_evidence_count", 0)) for fact in facts),
            "AUDIT_REFERENCES": sum(int(fact.get("audit_event_count", 0)) for fact in facts),
        }
        risks = self._merge_risks(facts, canonical_key=canonical_key)
        approval_id = None
        if self.ops_repository:
            candidate = CPUDuplicateCandidate(
                canonical_cpu_key=canonical_key or "UNKNOWN_CPU",
                region=region,
                suspected_duplicate_product_ids=[fact["id"] for fact in facts],
                product_names=[fact["name"] for fact in facts],
                vendors=sorted({vendor for fact in facts for vendor in fact.get("vendors", [])}),
                prices=[price for fact in facts for price in fact.get("prices", [])],
                confidence="medium" if risks else "high",
                reason="Merge preview groups products that appear to describe the same CPU model.",
                recommended_action="Review canonical merge preview; execute only after approval.",
                approval_required=True,
            )
            approval = self._ensure_merge_approval(candidate, region=region, trace_id=trace_id)
            approval_id = approval.id if approval else None

        return CanonicalMergePreviewResponse(
            proposed_canonical_product=target,
            relationships_to_preserve=counts,
            price_snapshots_to_preserve=counts["HAS_PRICE"],
            vendors_to_preserve=counts["SOLD_BY"],
            field_evidence_to_preserve=counts["HAS_FIELD_EVIDENCE"],
            audit_events_to_preserve=counts["AUDIT_REFERENCES"],
            risks=risks,
            rollback_plan=(
                "Merge execution would mark source products as deprecated aliases, preserve all PriceSnapshot, "
                "Vendor, FieldEvidence, and AuditEvent relationships, and retain the original product IDs in alias metadata."
            ),
            would_execute=False,
            approval_required=True,
            approval_id=approval_id,
        )

    def _candidate(self, canonical_cpu_key: str, products: list[ProductSearchResult]) -> CPUDuplicateCandidate:
        prices: list[dict[str, Any]] = []
        vendors: set[str] = set()
        packages = set()
        for product in products:
            detail_prices = self.pricing_repository.vendor_prices(product.id, region=product.region)
            for price in detail_prices[:4]:
                vendors.add(price.vendor_name)
                prices.append(
                    {
                        "product_id": product.id,
                        "vendor": price.vendor_name,
                        "price": price.final_landed_price_sar or price.final_landed_price or price.price,
                        "currency": price.final_landed_currency or price.currency,
                        "region": price.region,
                    }
                )
            package = _package_signal(product.name)
            if package:
                packages.add(package)
        confidence = "high" if len(packages) <= 1 else "medium"
        reason = (
            "Same CPU model key, standalone CPU type, and no conflicting package signals."
            if confidence == "high"
            else "Same CPU model key, but package or warranty wording differs and needs founder review."
        )
        return CPUDuplicateCandidate(
            canonical_cpu_key=canonical_cpu_key,
            region=products[0].region if products else "SA",
            suspected_duplicate_product_ids=sorted({item.id for item in products}),
            product_names=sorted({item.name for item in products}),
            vendors=sorted(vendors),
            prices=prices,
            confidence=confidence,
            reason=reason,
            recommended_action="Create approval-gated canonical product merge review.",
            approval_required=True,
        )

    def _ensure_merge_approval(
        self,
        candidate: CPUDuplicateCandidate,
        *,
        region: str,
        trace_id: str | None,
    ) -> ApprovalItem | None:
        if not self.ops_repository:
            return None
        approval_id = _approval_id(candidate.canonical_cpu_key, region)
        if self.ops_repository.unresolved_approval_exists(approval_id):
            return self.ops_repository.approval_by_id(approval_id)
        approval = ApprovalItem(
            id=approval_id,
            action_type="canonical_product_merge",
            title=f"Review CPU canonical merge: {candidate.canonical_cpu_key}",
            description="Potential duplicate CPU Product nodes were found. No merge has been executed.",
            affected_entities=candidate.suspected_duplicate_product_ids,
            target_entities=candidate.suspected_duplicate_product_ids,
            affected_count=len(candidate.suspected_duplicate_product_ids),
            risk_level="level_2",
            reasoning=candidate.reason,
            evidence_summary=f"{len(candidate.product_names)} CPU product names map to {candidate.canonical_cpu_key}.",
            evidence={
                "canonical_cpu_key": candidate.canonical_cpu_key,
                "product_names": candidate.product_names,
                "vendors": candidate.vendors,
                "prices": candidate.prices[:20],
                "confidence": candidate.confidence,
                "region": region,
            },
            risk_explanation="Canonical merge changes product identity grouping and must preserve price and evidence history.",
            expected_impact="If later executed, duplicate CPU products would be linked under one canonical identity without losing snapshots.",
            rollback_plan=(
                "Keep original product IDs as deprecated aliases and retain all relationships so the merge can be reversed by "
                "clearing alias/deprecated metadata and restoring search visibility."
            ),
            requested_by_agent="Graph Integrity Agent",
            recommended_decision="defer",
            trace_id=trace_id or f"trace-cpu-merge-{candidate.canonical_cpu_key}",
        )
        return self.ops_repository.upsert_approval(approval)

    def _proposed_target(self, facts: list[dict[str, Any]], canonical_key: str | None) -> dict[str, Any]:
        sorted_facts = sorted(
            facts,
            key=lambda fact: (
                0 if fact.get("canonical_key") == canonical_key else 1,
                -int(fact.get("price_snapshot_count", 0)),
                fact.get("name", ""),
            ),
        )
        target = sorted_facts[0]
        return {
            "product_id": target["id"],
            "canonical_key": canonical_key or target.get("canonical_key"),
            "name": target.get("name"),
            "brand": target.get("brand"),
            "category": target.get("category"),
            "model": target.get("model"),
        }

    def _merge_risks(self, facts: list[dict[str, Any]], *, canonical_key: str | None) -> list[str]:
        risks: list[str] = []
        if canonical_key is None:
            risks.append("No confident CPU canonical key could be derived for all products.")
        keys = {fact.get("canonical_key") for fact in facts if fact.get("canonical_key")}
        if len(keys) > 1:
            risks.append("Products currently have different stored canonical keys.")
        packages = {_package_signal(fact.get("name", "")) for fact in facts}
        packages.discard("")
        if len(packages) > 1:
            risks.append("Package or warranty wording differs; merge should remain approval-gated.")
        regions = {price.get("region") for fact in facts for price in fact.get("prices", [])}
        if len(regions) > 1:
            risks.append("Multiple price regions are attached and must remain separated during any merge.")
        return risks


def cpu_canonical_identity(product: ProductSearchResult) -> str | None:
    for value in (product.canonical_key, product.model, product.name):
        if not value:
            continue
        key = cpu_model_key_from_title(value)
        if key:
            brand = "AMD" if key.startswith("AMD_") else "Intel" if key.startswith("INTEL_") else product.brand or "Unknown"
            return f"CPU|{brand.upper()}|{key.replace(f'{brand.upper()}_', '', 1)}"
    return None


def _package_signal(name: str) -> str:
    upper = name.upper()
    if "TRAY" in upper or "OEM" in upper:
        return "TRAY"
    if "BOXED" in upper or " BOX " in f" {upper} " or "RETAIL" in upper:
        return "BOXED"
    return ""


def _approval_id(canonical_cpu_key: str, region: str) -> str:
    safe = canonical_cpu_key.replace("|", ":").replace(" ", "_")
    return f"approval:canonical_product_merge:{region}:{safe}"
