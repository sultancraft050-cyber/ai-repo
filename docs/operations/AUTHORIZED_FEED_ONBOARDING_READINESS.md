# Authorized Feed Onboarding Readiness

## Scope

This is the minimum technical package for receiving one future authorized product or store feed sample. It does not approve a real feed, create a connector, request credentials, ingest a sample, or enable production behavior. Source-specific values remain blank until the user supplies an authorized sample or approved sample schema.

## Confirmed technical capabilities

The repository already has a relational catalog foundation, staged CSV/JSON import pipeline, metadata-only product-image review, loopback local review/import interface, versioned mapping templates, a disabled synthetic feed simulator, and a deterministic replay/failure-injection harness. All catalog flags default to false, no public catalog write routes exist, and production/Neo4j behavior remains unchanged.

## Minimal onboarding record

Use one record per future source. Do not attach contracts, credentials, confidential document contents, endpoint secrets, billing data, or ownership matrices.

### Feed identity

| Field | Value | Rule |
|---|---|---|
| `feed_name` | TO_BE_SUPPLIED | Short internal name |
| `feed_type` | `MANUAL_AUTHORIZED_FILE`, `PARTNER_CSV`, `PARTNER_JSON`, `FUTURE_AUTHENTICATED_API`, or `FUTURE_SFTP` | No connection is created in this iteration |
| `supplier_or_store_name` | TO_BE_SUPPLIED | Must be source-authorized later |
| `country` | TO_BE_SUPPLIED | Explicit ISO country required |
| `expected_currency` | TO_BE_SUPPLIED | Saudi prices require `SAR`; no conversion is invented |
| `expected_timezone` | TO_BE_SUPPLIED | Timestamps must carry or define timezone |
| `expected_entity_types` | TO_BE_SUPPLIED | Product/store/offer entities must be explicit |
| `expected_file_format` | TO_BE_SUPPLIED | CSV, JSON array, or JSON records |

### Authorization evidence

| Field | Value | Rule |
|---|---|---|
| `authorization_status` | `TO_BE_SUPPLIED` | Must be valid before sample review |
| `authorization_reference` | TO_BE_SUPPLIED | Safe internal reference only; no contract contents |
| `authorization_date` | TO_BE_SUPPLIED | Date only |
| `allowed_data_categories` | TO_BE_SUPPLIED | Product, specification, offer, price, store, or image metadata |
| `image_rights_included` | `YES`, `NO`, or `TO_BE_SUPPLIED` | Recorded separately from feed authorization |
| `authorization_expiration` | TO_BE_SUPPLIED or `NOT_APPLICABLE` | Required when applicable |

Authorization references never contain credentials or confidential documents. Image rights are a separate review gate and do not follow automatically from general feed authorization.

## Delivery, volume, and identity requirements

Record expected records per delivery, maximum file size, delivery frequency, full versus incremental mode, product categories, store count, and offer count. Delivery documentation may describe a manual file, partner CSV/JSON, future authenticated API, or future SFTP, but this iteration creates no connection, endpoint, authentication, or credential request.

The source must declare whether it supplies GTIN, brand, manufacturer part number, store SKU, product URL, and observed timestamp. Product title alone is insufficient. Fuzzy matching is prohibited. Unresolved identities remain review-required. A store offer requires a resolved product, resolved store, and store SKU.

## Mapping-template readiness

Before accepting a real sample, record the template ID, version, SHA-256 checksum, entity type, authorization status, unknown-field policy, controlled-value maps, source timezone, and source currency. Do not create a real template without a sample schema. Existing templates are fixture-only and remain disabled by default.

## Authorized sample gate

The later sample must contain 10–50 supplier-approved or synthetic rows representing valid records, missing values, duplicates, invalid values, prices, stock, timestamps, and image metadata when applicable. No credentials are needed. No sample is requested, connected, or ingested in this iteration.

## Local pilot sequence

1. Confirm source authorization.
2. Receive one approved sample file.
3. Inspect its schema without connecting production.
4. Create mapping-template version 1.
5. Validate the template locally.
6. Run mapping preview.
7. Run staged dry-run against ephemeral SQLite.
8. Review identity conflicts and rejected rows.
9. Run deterministic replay.
10. Run the failure-injection suite.
11. Compare final state with a clean run.
12. Approve or reject the feed for a local pilot.
13. Run a bounded local pilot.
14. Produce a pilot result report.
15. Only then design staging infrastructure.

The pilot remains local and excludes production import and production deployment.

## Retention and rollback

Authorized source files remain outside Git. Raw files are never committed. Normalized staging follows existing import retention rules; safe errors contain no complete rows. Audit records retain template ID/version/checksum. Image-review decisions remain append-only. Temporary local evidence can be removed after validation. Production retention remains undecided until a real source is selected.

Rollback is local-only: discard the ephemeral SQLite database, remove temporary generated files, retain safe documentation/checksums, leave production and Neo4j untouched, keep catalog flags disabled, and revert repository changes when necessary.

## Readiness classification

**READY_FOR_AUTHORIZED_SAMPLE**

The technical definition, authorization evidence fields, identity requirements, sample requirements, mapping requirements, local validation sequence, retention rules, and rollback rules are defined. This means the project is ready to receive an authorized sample later; it does not mean a real feed is approved.

Pilot conflict acceptance remains `TO_BE_SET_FOR_FIRST_AUTHORIZED_FEED`; no acceptable conflict percentage is invented.
