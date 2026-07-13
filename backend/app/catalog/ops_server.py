"""Loopback-only local catalog review and import operations interface.

This module is intentionally separate from :mod:`app.main`.  It is a manually
started, SQLite-only utility for synthetic fixtures and never contacts a
production database, Neo4j, or an external URL.
"""
from __future__ import annotations

import html
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.database import CatalogDatabase
from app.catalog.feed_mapping import FeedMappingService, MappingError
from app.catalog.feed_simulator import SimulatorError, clean_run, generate as generate_simulation, list_adapters, list_runs, list_scenarios, preview as preview_simulation, read_manifest, stage_run
from app.catalog.image_review import ImageReviewService
from app.catalog.import_pipeline import CatalogImportPipeline, ImportLimits, commit_batch, read_file_bounded, stage_result
from app.catalog.models import (
    ApprovalStatus, ImportBatch, ImportBatchStatus, ImportError, ImportRecord,
    ImportReviewStatus, ImportSource, ImportValidationStatus, Product, ProductImage,
    ProductImageReview, PriceHistory, Store, StoreOffer,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = (ROOT / "tests" / "fixtures").resolve()
TRUE = {"1", "true", "yes"}


def _enabled(name: str) -> bool:
    return os.getenv(name, "false").lower() in TRUE


def validate_ops_environment() -> str:
    if not _enabled("CATALOG_OPS_ENABLED"):
        raise RuntimeError("CATALOG_OPS_DISABLED: set CATALOG_OPS_ENABLED=true for local use.")
    url = os.getenv("CATALOG_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("CATALOG_DATABASE_URL_REQUIRED: provide an explicit local SQLite URL.")
    if not url.startswith("sqlite:///") or url.startswith("sqlite+"):
        raise RuntimeError("SQLITE_ONLY: local operations accept only sqlite:/// URLs.")
    return url


def _local_engine(url: str):
    return create_engine(url, connect_args={"check_same_thread": False})


def initialize_local_database(url: str, *, reset: bool = False) -> None:
    """Run the checked-in catalog migrations without ever selecting a remote DB."""
    if reset:
        if not _enabled("CATALOG_OPS_RESET"):
            raise RuntimeError("RESET_DISABLED: set CATALOG_OPS_RESET=true for an explicit local reset.")
        if url != "sqlite:///:memory:":
            path = Path("/" + url.removeprefix("sqlite:////")) if url.startswith("sqlite:////") else None
            if path and path.exists():
                path.unlink()
    executable = shutil.which("alembic")
    if not executable:
        raise RuntimeError("MIGRATION_TOOL_UNAVAILABLE: install the backend dependencies first.")
    environment = {**os.environ, "CATALOG_DATABASE_URL": url}
    result = subprocess.run(
        [executable, "-c", str(ROOT / "alembic.ini"), "upgrade", "head"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("MIGRATION_FAILED: inspect local logs and configuration.")


def _safe(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _status(value: Any) -> str:
    raw = getattr(value, "value", value)
    return f'<span class="badge badge-{_safe(str(raw).lower())}">{_safe(raw)}</span>'


def _layout(title: str, body: str) -> HTMLResponse:
    nav = """<nav aria-label="Operations navigation">
      <a href="/">Overview</a><a href="/batches">Batches</a>
      <a href="/images/pending">Image queue</a><a href="/images/duplicates">Duplicates</a><a href="/feed-simulator">Feed simulator</a>
      <a href="/catalog/products">Products</a><a href="/catalog/stores">Stores</a><a href="/catalog/offers">Offers</a>
    </nav>"""
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1"><title>{_safe(title)} | Local Catalog Ops</title>
      <style>body{{font:16px system-ui,sans-serif;max-width:1200px;margin:auto;padding:1rem;background:Canvas;color:CanvasText}}nav{{display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:1.5rem}}a{{color:LinkText}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}th,td{{border:1px solid #888;padding:.45rem;text-align:left;vertical-align:top}}th{{background:ButtonFace}}.badge{{padding:.15rem .4rem;border-radius:.3rem;border:1px solid #888}}.danger{{border-left:.3rem solid #b00;padding:.6rem}}.ok{{border-left:.3rem solid #087f23;padding:.6rem}}button{{padding:.45rem .7rem}}:focus-visible{{outline:3px solid Highlight;outline-offset:2px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}</style></head><body>{nav}<main><h1>{_safe(title)}</h1>{body}</main></body></html>""")


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th scope=\"col\">{_safe(item)}</th>" for item in headers)
    values = "".join("<tr>" + "".join(f"<td>{item if str(item).startswith('<span') or str(item).startswith('<a') or str(item).startswith('<form') else _safe(item)}</td>" for item in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{values or '<tr><td colspan=\"%d\">No records.</td></tr>' % len(headers)}</tbody></table>"


def _session_factory(url: str):
    return sessionmaker(_local_engine(url), expire_on_commit=False)


def _fixture_path(value: str) -> Path:
    candidate = Path(value).expanduser().resolve()
    if FIXTURE_ROOT not in candidate.parents:
        raise ValueError("FIXTURE_PATH_REQUIRED: imports must use backend/tests/fixtures.")
    if not candidate.is_file():
        raise ValueError("FIXTURE_NOT_FOUND: choose an existing synthetic fixture.")
    return candidate


def _summary_rows(session: Session) -> dict[str, int]:
    pending_images = session.scalar(select(func.count(ProductImage.id)).where(ProductImage.review_status == "pending")) or 0
    pending_records = session.scalar(select(func.count(ImportRecord.id)).where(ImportRecord.review_status == ImportReviewStatus.PENDING.value)) or 0
    failed = session.scalar(select(func.count(ImportRecord.id)).where(ImportRecord.validation_status == ImportValidationStatus.INVALID.value)) or 0
    duplicate = session.scalar(select(func.count(ImportRecord.id)).where(ImportRecord.validation_status == ImportValidationStatus.DUPLICATE.value)) or 0
    return {"products": session.scalar(select(func.count(Product.id))) or 0, "stores": session.scalar(select(func.count(Store.id))) or 0, "offers": session.scalar(select(func.count(StoreOffer.id))) or 0, "images": session.scalar(select(func.count(ProductImage.id))) or 0, "pending_images": pending_images, "batches": session.scalar(select(func.count(ImportBatch.id))) or 0, "review_records": pending_records, "failed_records": failed, "duplicate_records": duplicate}


def create_ops_app() -> FastAPI:
    """Create the unmounted local app; validation happens before serving."""
    url = validate_ops_environment()
    initialize_local_database(url)
    factory = _session_factory(url)
    app = FastAPI(title="Local Catalog Operations", docs_url=None, redoc_url=None)
    app.state.catalog_ops_url = url
    app.state.feed_mapping_previews = {}

    @app.get("/", response_class=HTMLResponse)
    def overview() -> HTMLResponse:
        with factory() as session:
            counts = _summary_rows(session)
        flags = {name: _enabled(name) for name in ("CATALOG_OPS_ENABLED", "CATALOG_IMPORT_ENABLED", "CATALOG_IMAGE_REVIEW_ENABLED", "CATALOG_WRITES_ENABLED")}
        rows = [[key.replace("_", " ").title(), value] for key, value in counts.items()]
        body = "<p class=\"ok\">Local SQLite operations mode. No external network access is used.</p>"
        body += _table(["Metric", "Count"], rows)
        body += _table(["Flag", "Value"], [[key, "enabled" if value else "disabled"] for key, value in flags.items()])
        body += "<h2>Dry-run synthetic import</h2><form method=\"post\" action=\"/imports/dry-run\"><label for=\"path\">Fixture path</label> <input id=\"path\" name=\"path\" required size=\"70\" placeholder=\"backend/tests/fixtures/catalog_import/valid_products.csv\"><label for=\"entity\">Entity type</label> <select id=\"entity\" name=\"entity_type\"><option>PRODUCT</option><option>STORE</option><option>STORE_OFFER</option><option>PRODUCT_IMAGE_METADATA</option></select><button type=\"submit\">Run dry-run</button></form>"
        return _layout("Operations overview", body)

    @app.get("/feed-mappings", response_class=HTMLResponse)
    def feed_mappings() -> HTMLResponse:
        service = FeedMappingService()
        templates = service.list_templates(FIXTURE_ROOT / "catalog_feed_mappings")
        rows = [[f'<a href="/feed-mappings/{item.template_id}/{item.version}">{item.template_id}</a>', item.version, item.checksum, item.entity_type, item.data["source_type"], item.data["authorization_status"], item.data["country"], item.data["default_currency"], item.data["default_timezone"]] for item in templates]
        body = '<p class="ok">Synthetic templates only; no feed is fetched.</p>'
        return _layout("Feed mapping templates", body + _table(["Template", "Version", "Checksum", "Entity", "Source", "Authorization", "Country", "Currency", "Timezone"], rows))

    @app.get("/feed-simulator", response_class=HTMLResponse)
    def feed_simulator() -> HTMLResponse:
        adapters = list_adapters() if _enabled("CATALOG_FEED_SIMULATOR_ENABLED") else []
        scenarios = list_scenarios() if _enabled("CATALOG_FEED_SIMULATOR_ENABLED") else []
        body = "<p class=\"ok\">Synthetic fixture generation only; no transport or external service is available.</p>"
        body += _table(["Adapters", "Scenarios", "Simulator flag"], [[len(adapters), len(scenarios), "enabled" if _enabled("CATALOG_FEED_SIMULATOR_ENABLED") else "disabled"]])
        body += "<p>Use the local CLI for generation and bounded previews. Generated files remain under the system temporary directory.</p>"
        return _layout("Synthetic feed simulator", body)

    @app.get("/feed-simulator/adapters", response_class=HTMLResponse)
    def feed_simulator_adapters() -> HTMLResponse:
        rows = [[item.get("adapter_id"), item.get("adapter_version"), item.get("authorization_status"), ", ".join(item.get("supported_entity_types", []))] for item in list_adapters()] if _enabled("CATALOG_FEED_SIMULATOR_ENABLED") else []
        return _layout("Synthetic feed adapters", _table(["Adapter", "Version", "Authorization", "Entities"], rows))

    @app.get("/feed-simulator/scenarios", response_class=HTMLResponse)
    def feed_simulator_scenarios() -> HTMLResponse:
        rows = [[item.get("scenario_id"), item.get("scenario_name"), item.get("description")] for item in list_scenarios()] if _enabled("CATALOG_FEED_SIMULATOR_ENABLED") else []
        return _layout("Synthetic feed scenarios", _table(["Scenario", "Name", "Description"], rows))

    @app.get("/feed-simulator/runs", response_class=HTMLResponse)
    def feed_simulator_runs() -> HTMLResponse:
        rows = [[f'<a href="/feed-simulator/runs/{item["run_id"]}">{item["run_id"]}</a>', item.get("scenario_id"), item.get("entity_type"), item.get("record_count"), item.get("generated_file_checksum")] for item in list_runs()] if _enabled("CATALOG_FEED_SIMULATOR_ENABLED") else []
        return _layout("Synthetic feed runs", _table(["Run", "Scenario", "Entity", "Records", "Checksum"], rows))

    @app.get("/feed-simulator/runs/{run_id}", response_class=HTMLResponse)
    def feed_simulator_run(run_id: str) -> HTMLResponse:
        try:
            manifest = read_manifest(run_id)
            return _layout("Synthetic feed run", _table(["Field", "Value"], [[key, value] for key, value in manifest.items()]))
        except SimulatorError as error: raise HTTPException(404, error.code) from error

    @app.post("/feed-simulator/generate")
    async def feed_simulator_generate(request: Request):
        form = await _mapping_form(request)
        try:
            run = generate_simulation(adapter_id=form.get("adapter", "synthetic-sa-retailer-v1"), scenario_id=form.get("scenario", "initial-catalog-load"), output_format=form.get("format", "csv"), seed=int(form.get("seed", "20260713")), timestamp_anchor=form.get("timestamp_anchor", "2026-07-13T09:00:00+03:00"), entity_type=form.get("entity_type"))
            return {"run_id": run.run_id, "manifest": run.manifest}
        except (SimulatorError, ValueError) as error:
            raise HTTPException(400, getattr(error, "code", "SCENARIO_INVALID")) from error

    @app.post("/feed-simulator/preview")
    async def feed_simulator_preview(request: Request):
        form = await _mapping_form(request)
        try:
            run = generate_simulation(adapter_id=form.get("adapter", "synthetic-sa-retailer-v1"), scenario_id=form.get("scenario", "initial-catalog-load"), output_format=form.get("format", "csv"), seed=int(form.get("seed", "20260713")), timestamp_anchor=form.get("timestamp_anchor", "2026-07-13T09:00:00+03:00"), entity_type=form.get("entity_type"))
            return preview_simulation(run)
        except (SimulatorError, ValueError) as error:
            raise HTTPException(400, getattr(error, "code", "SCENARIO_INVALID")) from error

    @app.post("/feed-simulator/stage")
    async def feed_simulator_stage(request: Request):
        if not _enabled("CATALOG_IMPORT_ENABLED"): raise HTTPException(409, "STAGING_DISABLED")
        form = await _mapping_form(request)
        try:
            url = app.state.catalog_ops_url
            run = generate_simulation(adapter_id=form.get("adapter", "synthetic-sa-retailer-v1"), scenario_id=form.get("scenario", "initial-catalog-load"), output_format="csv", seed=int(form.get("seed", "20260713")), timestamp_anchor=form.get("timestamp_anchor", "2026-07-13T09:00:00+03:00"), entity_type=form.get("entity_type"))
            return stage_run(run, url)
        except (SimulatorError, MappingError, ValueError) as error:
            raise HTTPException(400, getattr(error, "code", "STAGING_DISABLED")) from error

    @app.post("/feed-simulator/runs/{run_id}/clean")
    async def feed_simulator_clean(run_id: str):
        try: clean_run(run_id); return {"cleaned": run_id}
        except SimulatorError as error: raise HTTPException(404, error.code) from error

    @app.get("/feed-mappings/compare", response_class=HTMLResponse)
    def feed_mapping_compare(first: str | None = None, second: str | None = None) -> HTMLResponse:
        if not first or not second: return _layout("Compare feed mapping versions", "<p>Provide first and second fixture template paths.</p>")
        try:
            service = FeedMappingService(); result = service.compare_versions(service.load_template(_fixture_path(first)), service.load_template(_fixture_path(second)))
            return _layout("Compare feed mapping versions", _table(["Field", "Value"], [[key, json.dumps(value) if isinstance(value, (list, dict)) else value] for key, value in result.items()]))
        except MappingError as error:
            raise HTTPException(400, error.code) from error

    @app.get("/feed-mappings/previews/{preview_id}", response_class=HTMLResponse)
    def feed_mapping_preview(preview_id: str) -> HTMLResponse:
        preview = app.state.feed_mapping_previews.get(preview_id)
        if not preview: raise HTTPException(404, "Preview not found")
        return _layout("Feed mapping preview", f"<pre>{_safe(json.dumps(preview, sort_keys=True))}</pre>")

    @app.get("/feed-mappings/{template_id}/{version}", response_class=HTMLResponse)
    def feed_mapping_detail(template_id: str, version: str) -> HTMLResponse:
        service = FeedMappingService()
        templates = [item for item in service.list_templates(FIXTURE_ROOT / "catalog_feed_mappings") if item.template_id == template_id and item.version == version]
        if not templates: raise HTTPException(404, "Template not found")
        item = templates[0]
        rows = [["Template ID", item.template_id], ["Version", item.version], ["Checksum", item.checksum], ["Entity", item.entity_type], ["Source type", item.data["source_type"]], ["Authorization", item.data["authorization_status"]], ["Mapped fields", ", ".join(mapping["target_field"] for mapping in item.data["field_mappings"])], ["Transforms", json.dumps(item.data["transforms"], sort_keys=True)]]
        return _layout(f"Feed mapping {template_id} v{version}", _table(["Field", "Value"], rows))

    async def _mapping_form(request: Request) -> dict[str, str]:
        body = await request.body()
        if len(body) > 8_192: raise HTTPException(413, "FORM_TOO_LARGE")
        parsed = parse_qs(body.decode("utf-8", errors="strict"), keep_blank_values=True)
        return {key: values[0] for key, values in parsed.items()}

    @app.post("/feed-mappings/validate")
    async def validate_feed_mapping(request: Request):
        form = await _mapping_form(request)
        try:
            item = FeedMappingService().load_template(_fixture_path(form.get("template", "")))
            return {"valid": True, "template_id": item.template_id, "template_version": item.version, "checksum": item.checksum}
        except (MappingError, OSError) as error:
            raise HTTPException(400, getattr(error, "code", "TEMPLATE_INVALID")) from error

    @app.post("/feed-mappings/preview")
    async def preview_feed_mapping(request: Request):
        form = await _mapping_form(request)
        try:
            service = FeedMappingService(); item = service.load_template(_fixture_path(form.get("template", ""))); results = service.map_file(item, _fixture_path(form.get("file", "")).read_bytes())
            preview_id = hashlib.sha256(f"{item.checksum}:{len(results)}".encode()).hexdigest()[:16]
            payload = {"preview_id": preview_id, "template_id": item.template_id, "template_version": item.version, "checksum": item.checksum, "record_count": len(results), "validation_counts": {status: sum(result.validation_status == status for result in results) for status in sorted({result.validation_status for result in results})}, "records": [result.safe_dict() for result in results]}
            app.state.feed_mapping_previews[preview_id] = payload
            return payload
        except (MappingError, OSError) as error:
            raise HTTPException(400, getattr(error, "code", "TEMPLATE_INVALID")) from error

    @app.post("/feed-mappings/stage")
    async def stage_feed_mapping(request: Request):
        form = await _mapping_form(request)
        if not _enabled("CATALOG_IMPORT_ENABLED"): raise HTTPException(409, "TEMPLATE_DISABLED")
        try:
            service = FeedMappingService(); item = service.load_template(_fixture_path(form.get("template", ""))); results = service.map_file(item, _fixture_path(form.get("file", "")).read_bytes())
            with factory() as session: batch = service.stage(session, item, results)
            return {"batch_id": batch.id, "template_id": item.template_id, "template_version": item.version, "checksum": item.checksum}
        except (MappingError, OSError) as error:
            raise HTTPException(400, getattr(error, "code", "TEMPLATE_INVALID")) from error

    @app.post("/imports/dry-run")
    async def dry_run(request: Request) -> RedirectResponse:
        body = await request.body()
        if len(body) > 8_192:
            raise HTTPException(413, "FORM_TOO_LARGE")
        form = parse_qs(body.decode("utf-8", errors="strict"), keep_blank_values=True)
        path = form.get("path", [""])[0]
        entity_type = form.get("entity_type", [""])[0]
        try:
            fixture = _fixture_path(path)
            fmt = fixture.suffix.lstrip(".").lower()
            content = read_file_bounded(fixture, ImportLimits().max_file_size)
            with factory() as session:
                now = datetime.now(timezone.utc)
                source_name = f"local-fixture:{fixture.name}"
                source = session.scalar(select(ImportSource).where(ImportSource.name == source_name))
                if source is None:
                    source = ImportSource(name=source_name, source_type=fmt, rights_status="review", active=True, created_at=now, updated_at=now)
                    session.add(source); session.flush()
                result = CatalogImportPipeline(session).dry_run(content, file_format=fmt, entity_type=entity_type)
                batch = stage_result(session, source, result)
                batch_id = batch.id
            return RedirectResponse(f"/batches/{batch_id}", status_code=303)
        except (ValueError, RuntimeError, OSError) as exc:
            return RedirectResponse("/?" + urlencode({"error": str(exc).split(":", 1)[0]}), status_code=303)

    @app.get("/batches", response_class=HTMLResponse)
    def batches(status: str | None = None, entity_type: str | None = None, source: str | None = None, review_required: bool = False, page: int = 1) -> HTMLResponse:
        page = max(1, min(page, 100)); limit = 50
        with factory() as session:
            query = select(ImportBatch, ImportSource).join(ImportSource).order_by(ImportBatch.id.desc()).offset((page - 1) * limit).limit(limit)
            if status: query = query.where(ImportBatch.status == status)
            if entity_type: query = query.where(ImportBatch.entity_type == entity_type)
            if source: query = query.where(ImportSource.name == source[:200])
            if review_required: query = query.where(ImportBatch.status == ImportBatchStatus.REVIEW_REQUIRED.value)
            rows = []
            for batch, src in session.execute(query):
                rows.append([f'<a href="/batches/{batch.id}">{batch.id}</a>', src.name, batch.entity_type, _status(batch.status), batch.received_count, batch.accepted_count, batch.rejected_count, batch.duplicate_count, batch.ambiguous_count, batch.staged_count, batch.committed_count, batch.created_at.isoformat(), batch.completed_at.isoformat() if batch.completed_at else ""])
        form = '<form method="get"><label>Status <input name="status"></label> <label>Entity <input name="entity_type"></label> <label>Source <input name="source"></label> <label><input type="checkbox" name="review_required" value="true"> review required</label> <button>Filter</button></form>'
        return _layout("Import batches", form + _table(["ID", "Source", "Entity", "Status", "Received", "Accepted", "Rejected", "Duplicate", "Ambiguous", "Staged", "Committed", "Created", "Completed"], rows))

    @app.get("/batches/{batch_id}", response_class=HTMLResponse)
    def batch_detail(batch_id: int) -> HTMLResponse:
        with factory() as session:
            batch = session.get(ImportBatch, batch_id)
            if not batch: raise HTTPException(404, "Batch not found")
            records = session.scalars(select(ImportRecord).where(ImportRecord.batch_id == batch_id).order_by(ImportRecord.row_number)).all()
            counts: dict[str, int] = {}
            proposed: dict[str, int] = {}
            reviews: dict[str, int] = {}
            errors: dict[str, int] = {}
            for record in records:
                counts[record.validation_status] = counts.get(record.validation_status, 0) + 1
                proposed[record.proposed_action] = proposed.get(record.proposed_action, 0) + 1
                reviews[record.review_status] = reviews.get(record.review_status, 0) + 1
                if record.safe_error_code:
                    errors[record.safe_error_code] = errors.get(record.safe_error_code, 0) + 1
            eligible = batch.status == ImportBatchStatus.READY.value and not any(r.validation_status in {"INVALID", "BLOCKED", "AMBIGUOUS"} or r.review_status not in {"APPROVED", "NOT_REQUIRED"} for r in records)
            body = _table(["Field", "Value"], [["Status", _status(batch.status)], ["Entity", batch.entity_type], ["Records", len(records)], ["Validation counts", json.dumps(counts, sort_keys=True)], ["Proposed-action counts", json.dumps(proposed, sort_keys=True)], ["Review-status counts", json.dumps(reviews, sort_keys=True)], ["Safe error-code counts", json.dumps(errors, sort_keys=True)], ["Commit eligibility", "eligible" if eligible else "blocked"]])
            body += f'<p><a href="/batches/{batch_id}/records">Review staged records</a></p>'
            if eligible: body += f'<form method="post" action="/batches/{batch_id}/commit"><button>Commit approved local batch</button></form>'
            else: body += '<p class="danger">Commit blocked until all invalid, ambiguous, blocked, and pending-review rows are resolved.</p>'
            return _layout(f"Batch {batch_id}", body)

    @app.get("/batches/{batch_id}/records", response_class=HTMLResponse)
    def batch_records(batch_id: int) -> HTMLResponse:
        with factory() as session:
            records = session.scalars(select(ImportRecord).where(ImportRecord.batch_id == batch_id).order_by(ImportRecord.row_number).limit(200)).all()
            rows = []
            for record in records:
                actions = ""
                if record.validation_status not in {"INVALID", "BLOCKED", "AMBIGUOUS"}:
                    actions = f'<form method="post" action="/batches/{batch_id}/records/{record.id}/approve"><button>Approve</button></form>'
                actions += f'<form method="post" action="/batches/{batch_id}/records/{record.id}/reject"><button>Reject</button></form>'
                payload = json.loads(record.normalized_payload)
                safe = {key: payload[key] for key in payload if not key.startswith("_")}
                rows.append([record.row_number, record.entity_type, _status(record.validation_status), _status(record.review_status), record.proposed_action, record.matched_product_id or "", record.matched_store_id or "", record.matched_offer_id or "", record.safe_error_code or "", record.safe_error_message or "", f"<pre>{_safe(json.dumps(safe, sort_keys=True))}</pre>", actions])
        return _layout(f"Batch {batch_id} staged records", _table(["Row", "Entity", "Validation", "Review", "Action", "Product", "Store", "Offer", "Error", "Message", "Normalized payload", "Controls"], rows))

    def _record_action(batch_id: int, record_id: int, approve: bool) -> RedirectResponse:
        with factory() as session:
            record = session.get(ImportRecord, record_id)
            if not record or record.batch_id != batch_id: raise HTTPException(404, "Record not found")
            if approve and (record.validation_status in {"INVALID", "BLOCKED", "AMBIGUOUS"} or record.proposed_action == "REVIEW" and record.entity_type == "PRODUCT_IMAGE_METADATA"):
                raise HTTPException(409, "REVIEW_NOT_ALLOWED: validation or image review is unresolved.")
            record.review_status = ImportReviewStatus.APPROVED.value if approve else ImportReviewStatus.REJECTED.value
            record.updated_at = datetime.now(timezone.utc)
            batch = session.get(ImportBatch, batch_id)
            if batch and approve and record.validation_status == ImportValidationStatus.VALID.value: batch.status = ImportBatchStatus.READY.value
            session.commit()
        return RedirectResponse(f"/batches/{batch_id}/records", status_code=303)

    @app.post("/batches/{batch_id}/records/{record_id}/approve")
    def approve_record(batch_id: int, record_id: int): return _record_action(batch_id, record_id, True)

    @app.post("/batches/{batch_id}/records/{record_id}/reject")
    def reject_record(batch_id: int, record_id: int): return _record_action(batch_id, record_id, False)

    @app.post("/batches/{batch_id}/commit")
    def commit(batch_id: int) -> RedirectResponse:
        if not _enabled("CATALOG_WRITES_ENABLED"): raise HTTPException(409, "WRITES_DISABLED: enable local writes explicitly.")
        with factory() as session:
            batch = session.get(ImportBatch, batch_id)
            if not batch: raise HTTPException(404, "Batch not found")
            try: commit_batch(session, batch)
            except RuntimeError as exc: raise HTTPException(409, str(exc).split(":", 1)[0]) from exc
        return RedirectResponse(f"/batches/{batch_id}", status_code=303)

    @app.get("/images/pending", response_class=HTMLResponse)
    def images_pending() -> HTMLResponse:
        with factory() as session:
            service = ImageReviewService(session)
            images = service.list_pending()
            rows = []
            for image in images:
                evaluation = service.evaluate_image(image.id)
                reference = image.storage_key or "local"
                if image.source_url:
                    parsed = urlparse(image.source_url)
                    reference = parsed.hostname or "local-reference"
                rows.append([image.id, image.product_id, image.source_type, reference, image.width, image.height, image.format, image.file_size, image.rights_status, image.quality_status, image.review_status, "yes" if image.is_primary else "no", ", ".join(evaluation.reason_codes), "yes" if evaluation.primary_eligible else "no", f'<form method="post" action="/images/{image.id}/approve"><button>Approve</button></form><form method="post" action="/images/{image.id}/reject"><button>Reject</button></form><form method="post" action="/images/{image.id}/approve-primary"><button>Approve primary</button></form>'])
        return _layout("Pending image metadata reviews", _table(["Image", "Product", "Source", "Reference", "Width", "Height", "Format", "Bytes", "Rights", "Quality", "Review", "Primary", "Reasons", "Primary eligible", "Controls"], rows))

    def _image_decision(image_id: int, decision: str) -> RedirectResponse:
        if not _enabled("CATALOG_IMAGE_REVIEW_ENABLED") or not _enabled("CATALOG_WRITES_ENABLED"): raise HTTPException(409, "IMAGE_REVIEW_DISABLED: enable local review and writes explicitly.")
        with factory() as session:
            try: ImageReviewService(session).record_decision(image_id, decision, reason_code="LOCAL_OPERATOR_DECISION", safe_reason="Recorded through local operations interface.", reviewer_identifier="local-operator")
            except (ValueError, RuntimeError) as exc: raise HTTPException(409, str(exc).split(":", 1)[0]) from exc
        return RedirectResponse("/images/pending", status_code=303)

    for method, decision in (("approve", "APPROVE"), ("reject", "REJECT"), ("approve-primary", "APPROVE_PRIMARY"), ("expire-rights", "EXPIRE_RIGHTS"), ("remove-primary", "REMOVE_PRIMARY"), ("request-changes", "REQUEST_CHANGES"), ("mark-duplicate", "MARK_DUPLICATE")):
        app.add_api_route(f"/images/{{image_id}}/{method}", lambda image_id, _decision=decision: _image_decision(image_id, _decision), methods=["POST"])

    @app.get("/images/duplicates", response_class=HTMLResponse)
    def image_duplicates() -> HTMLResponse:
        with factory() as session:
            groups = ImageReviewService(session).list_duplicate_groups()
        rows = [[str(group.get("checksum", ""))[:16], group.get("count", 0), ", ".join(map(str, group.get("product_ids", []))), group.get("classification", ""), "yes" if group.get("metadata_conflict") else "no"] for group in groups]
        return _layout("Duplicate image metadata groups", _table(["Checksum", "Images", "Products", "Classification", "Metadata conflict"], rows))

    @app.get("/catalog/products", response_class=HTMLResponse)
    def products(page: int = 1) -> HTMLResponse:
        with factory() as session:
            items = session.scalars(select(Product).order_by(Product.canonical_name, Product.id).offset((max(1, page)-1)*50).limit(50)).all()
            rows = []
            for product in items:
                offers = session.scalars(select(StoreOffer).where(StoreOffer.product_id == product.id)).all()
                images = session.scalar(select(func.count(ProductImage.id)).where(ProductImage.product_id == product.id, ProductImage.review_status == "approved")) or 0
                sar = [o.sale_price or o.regular_price for o in offers if o.currency == "SAR" and (o.sale_price is not None or o.regular_price is not None)]
                rows.append([product.id, product.canonical_name, product.category, product.approval_status, len(product.specifications), images, len(offers), min(sar) if sar else ""])
        return _layout("Local catalog products", _table(["ID", "Name", "Category", "Approval", "Specs", "Approved images", "Current offers", "Cheapest SAR"], rows))

    @app.get("/catalog/stores", response_class=HTMLResponse)
    def stores(page: int = 1) -> HTMLResponse:
        with factory() as session:
            items = session.scalars(select(Store).order_by(Store.name, Store.id).offset((max(1, page)-1)*50).limit(50)).all()
            rows = [[item.id, item.name, item.country, item.status, session.scalar(select(func.count(StoreOffer.id)).where(StoreOffer.store_id == item.id)) or 0] for item in items]
        return _layout("Local catalog stores", _table(["ID", "Name", "Country", "Status", "Offers"], rows))

    @app.get("/catalog/offers", response_class=HTMLResponse)
    def offers(page: int = 1) -> HTMLResponse:
        with factory() as session:
            items = session.scalars(select(StoreOffer).order_by(StoreOffer.id).offset((max(1, page)-1)*50).limit(50)).all()
            rows = [[item.id, item.product_id, item.store_id, item.store_sku, item.stock_status, item.regular_price, item.sale_price, item.currency, item.observed_at.isoformat(), item.expires_at.isoformat() if item.expires_at else ""] for item in items]
        return _layout("Local store offers", _table(["ID", "Product", "Store", "SKU", "Stock", "Regular", "Sale", "Currency", "Observed", "Expires"], rows))

    return app


def main() -> int:
    import uvicorn
    try:
        app = create_ops_app()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    host = os.getenv("CATALOG_OPS_HOST", "127.0.0.1")
    if host != "127.0.0.1":
        print("LOOPBACK_ONLY: CATALOG_OPS_HOST must remain 127.0.0.1", file=sys.stderr)
        return 2
    uvicorn.run(app, host=host, port=int(os.getenv("CATALOG_OPS_PORT", "8787")), access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
