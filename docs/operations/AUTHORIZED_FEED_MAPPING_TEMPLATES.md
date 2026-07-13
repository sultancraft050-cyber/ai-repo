# Authorized Product and Store Feed Mapping Templates

## Purpose and scope

This iteration adds versioned JSON mappings for synthetic supplier, retailer, product-specification, image-metadata, price-observation, and store feeds. Mapping is disabled by default, manually started, fixture-only, and local. It does not create connectors, download feeds, fetch URLs/images, or contact external services.

## Feature flag and supported entities

`CATALOG_FEED_MAPPING_ENABLED=false` is the default. Local preview additionally requires `CATALOG_IMPORT_ENABLED=true`; staging uses the existing import pipeline and committing still requires `CATALOG_WRITES_ENABLED=true` and local SQLite. No mapping run starts automatically. Supported entities are `PRODUCT`, `PRODUCT_SPECIFICATION`, `PRODUCT_IMAGE_METADATA`, `STORE`, `STORE_OFFER`, and `PRICE_OBSERVATION`.

## Template schema and authorization

Templates are JSON documents under `backend/tests/fixtures/catalog_feed_mappings/` for this iteration. They contain IDs/versions, source and authorization metadata, format/entity, field mappings, defaults, transforms, identity/provenance rules, validation/staleness rules, unknown-field policy, and timestamps. Controlled authorization values are `AUTHORIZED`, `PENDING_AUTHORIZATION`, `REVOKED`, `EXPIRED`, and `SYNTHETIC_ONLY`; only the first and last can run locally, and all checked-in fixtures are synthetic-only. Authorization does not grant image rights.

Supported source types are `MANUFACTURER_FEED`, `AUTHORIZED_DISTRIBUTOR_FEED`, `AUTHORIZED_RETAILER_FEED`, `PARTNER_CSV`, `PARTNER_JSON`, `MANUAL_AUTHORIZED_FILE`, and `SYNTHETIC_FIXTURE`. Input is bounded UTF-8 CSV, JSON arrays, or `{ "records": [...] }`; malformed, nested, oversized, or over-limit input is rejected.

## Safe transforms and validation

The code whitelist includes trimming, whitespace collapse, case normalization, brand/MPN/GTIN/country/currency normalization, bounded decimal/integer and ISO datetime parsing, URL normalization, stock/category controlled mappings, bounded concatenation, and explicit lookup tables. There is no `eval`, `exec`, shell, dynamic import, regex supplied by feed data, database lookup, or network lookup.

Unknown-field policy defaults to `REJECT`; `IGNORE_WITH_WARNING` and `RECORD_FIELD_NAMES_ONLY` never persist unknown values. Credential-like names (`password`, `token`, `secret`, `authorization`, `cookie`, `api_key`, `private_key`) are rejected. Templates cannot target approval fields or force image approval/primary status.

## Identity, Saudi pricing, and timezones

Product identity remains strict: normalized GTIN, normalized brand + MPN, explicit product ID, otherwise review/create proposal. Store identity uses explicit ID, normalized slug, or exact name + country. Offers require resolved product, resolved store, and store SKU. Saudi sources use `SA`, normally `SAR`, and `Asia/Riyadh`; non-SAR currency is retained without conversion or invented exchange rates. Observed timestamps retain timezone meaning.

## Versioning, checksums, and provenance

The canonical JSON checksum is deterministic SHA-256. A template ID/version cannot silently change content; a conflict is rejected. Mapping results retain template ID/version/checksum, source row number, source field names used, safe source reference, authorization, source type, and mapped timestamp. When staged, the exact mapping provenance is encoded in the linked import-source reference; raw files are never persisted.

## Error codes and CLI

Stable safe codes cover disabled/unauthorized/invalid templates, version conflicts, unsupported source/entity/transforms, missing source or identity, invalid targets/country/currency/timezone/datetime/price, unknown controlled values, credential fields, image-rights review, primary review, and record limits.

```sh
CATALOG_FEED_MAPPING_ENABLED=true CATALOG_IMPORT_ENABLED=true \
python -m app.catalog.feed_mapping_cli validate-template \
  --template backend/tests/fixtures/catalog_feed_mappings/synthetic_product_v1.json

CATALOG_FEED_MAPPING_ENABLED=true CATALOG_IMPORT_ENABLED=true \
python -m app.catalog.feed_mapping_cli preview \
  --template backend/tests/fixtures/catalog_feed_mappings/synthetic_offer_v1.json \
  --file backend/tests/fixtures/catalog_feed_mappings/synthetic_offers.csv
```

`validate-template`, `list-templates`, `preview`, `stage`, and `compare-versions` accept only fixture paths and print safe summaries. Staging requires an explicit local SQLite URL and existing import flag; no database URL or credentials are printed.

## Operations interface and synthetic fixtures

The standalone loopback operations app exposes `/feed-mappings`, version detail, compare, preview, and guarded validate/preview/stage actions. These routes are not mounted in the production application, accept no arbitrary uploads, use no external assets, and bind only to loopback through the existing operations server. Fixtures cover synthetic CPU/GPU products, stores, offers, specifications, image metadata, price observations, invalid authorization/transforms/credential fields, version comparison, unknown values, identity gaps, and duplicate inputs.

## Testing, rollback, and safety confirmation

Tests cover template validation, deterministic transforms, version conflicts/comparison, all entity mappings, Saudi currency/timezone behavior, image review gates, provenance, unknown fields, fixture-only CLI paths, operations route isolation, and no-network static checks. The existing catalog, import, image-review, operations, full backend, and release tests remain required.

Rollback is a normal Git revert of the mapping commit(s); remove only explicitly created local SQLite files. No real feed was ingested. Production, PostgreSQL, Neo4j, Cloud Run, Vercel, Secret Manager, cloud resources, and external services were untouched.
