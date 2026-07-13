# Authorized Feed Onboarding Checklist

This checklist is reusable for one future source. It is technical-only and contains no billing, cloud purchasing, credentials, contracts, or confidential evidence.

## Source and authorization

- [ ] Feed name and feed type recorded.
- [ ] Supplier/store name recorded.
- [ ] Country, expected currency, and expected timezone recorded.
- [ ] Expected entity types and file format recorded.
- [ ] Source authorized.
- [ ] Allowed data categories authorized.
- [ ] Image rights confirmed separately or explicitly excluded.
- [ ] Authorization reference is a safe internal reference only.
- [ ] Authorization date and expiration recorded when applicable.

## Delivery and bounds

- [ ] Delivery method documented as manual file, partner CSV, partner JSON, future API, or future SFTP.
- [ ] No connection, endpoint, authentication, or credential is configured during readiness.
- [ ] Expected records per delivery defined.
- [ ] Maximum file size defined.
- [ ] Delivery frequency and full/incremental mode defined.
- [ ] Expected categories, store count, and offer count defined.

## Schema and identity

- [ ] Expected schema is known from an approved sample or approved sample schema.
- [ ] GTIN availability recorded.
- [ ] Brand availability recorded.
- [ ] Manufacturer part number availability recorded.
- [ ] Store SKU availability recorded for offers.
- [ ] Product URL availability recorded.
- [ ] Observed timestamp availability and timezone meaning recorded.
- [ ] Product title alone is rejected as identity.
- [ ] Fuzzy matching is not used.
- [ ] Unresolved identities remain review-required.
- [ ] Offers have resolved product, store, and store SKU requirements.

## Mapping and validation

- [ ] Template ID, version, and checksum recorded.
- [ ] Entity type and authorization status recorded.
- [ ] Unknown-field policy selected.
- [ ] Controlled-value maps recorded.
- [ ] Source timezone and currency recorded.
- [ ] Required sample contains 10–50 representative rows.
- [ ] Missing-value examples included.
- [ ] Duplicate examples included.
- [ ] Invalid-value examples included.
- [ ] Price, stock, timestamp, and applicable image metadata examples included.
- [ ] Template validation passes locally.
- [ ] Mapping preview passes locally.
- [ ] Staged dry-run passes against ephemeral SQLite.
- [ ] Identity conflicts and rejected rows reviewed.
- [ ] Duplicate handling verified.
- [ ] Exact replay verified.
- [ ] Interruption recovery verified.
- [ ] Review queue cleared or explicitly accepted.
- [ ] No production connection used.

## Pilot gate

- [ ] No credential-like fields present.
- [ ] Authorization status valid.
- [ ] Identity conflicts remain below the documented threshold: `TO_BE_SET_FOR_FIRST_AUTHORIZED_FEED`.
- [ ] Invalid rows reported with safe errors.
- [ ] Replay is idempotent.
- [ ] Retry matches clean-run state.
- [ ] No duplicate canonical products, stores, or offers.
- [ ] Identical price observations are not duplicated.
- [ ] Stale prices do not replace current prices.
- [ ] Image rights and review gates remain enforced.
- [ ] No external image fetched.
- [ ] No production database or Neo4j operation.

## Retention and rollback

- [ ] Raw source files remain outside Git.
- [ ] Safe evidence contains checksums and summaries only.
- [ ] Template provenance is retained.
- [ ] Image-review decisions remain append-only.
- [ ] Temporary SQLite and generated files have an explicit cleanup owner.
- [ ] Rollback is discard of ephemeral SQLite and temporary files plus Git revert if needed.
