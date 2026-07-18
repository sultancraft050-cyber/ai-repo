# BuildCores OpenDB Catalog Bootstrap Operations

## 1. Source and License
- **Source Name:** BuildCores OpenDB
- **Source Repository:** https://github.com/buildcores/buildcores-open-db
- **License Identifier:** ODC-By-1.0 (Open Data Commons Attribution License v1.0)
- **Import Timestamp:** UTC Date of Ingestion
- **Attribution Page:** Located publicly at [/attribution](file:///C:/Users/sulta/Documents/start-clean-project/frontend/app/attribution/page.tsx) and linked via sidebar.

## 2. Content Intentionally Excluded
To maintain strict compliance and system constraints:
- No 3D models or rendering assets are imported.
- No BuildCores application branding, logos, or app code are copied.
- No live retailer pricing, affiliate links, or private API credentials are stored.
- No user-generated comments or reviews are saved.
- No remote images or media assets are downloaded.

## 3. Supported Categories & Field Mappings
We explicitly map 8 categories from the OpenDB directories into the Catalog V2 SQLite database:
1. **CPU:** socket, core count, thread count, base clock, boost clock, TDP, integrated graphics, supported memory types.
2. **GPU:** chipset, VRAM, length, slot width, power consumption, power connectors.
3. **Motherboard:** socket, chipset, form factor, ram type, slots, max memory, storage ports, PCIe slots.
4. **RAM:** memory generation, capacity, modules quantity, speed, latency, form factor.
5. **Storage:** capacity, interface, form factor, NVMe/SATA protocol.
6. **PSU:** wattage, efficiency rating, form factor, modularity, connectors.
7. **Case:** supported motherboard form factors, max GPU length, max cooler height, PSU form factor support.
8. **Cooler:** supported sockets, cooler type (water/air), height, radiator size.

## 4. Identity & Matching Rules
We apply strict identity verification gates during ingestion:
1. **GTIN:** Nullable but unique if present.
2. **Brand & MPN:** Brand must be normalized and MPN must be present and distinct from the generic product name.
3. **Source UUID:** Retained as metadata provenance under `opendb_id` but never used as the sole canonical identifier.
4. **Review Gateway:** Records lacking a clear MPN or containing generic identifiers are staged as `REVIEW_REQUIRED` and will not commit automatically.

## 5. Bounded Import Limits
To prevent database bloating and respect rate limits:
- **Total Limit:** Max 300 products total.
- **Categorical Limits:**
  - CPU: 40
  - GPU: 50
  - Motherboard: 60
  - RAM: 35
  - Storage: 30
  - PSU: 25
  - Case: 25
  - Cooler: 25

## 6. CLI Usage & Commands
The CLI can be invoked inside the `backend` environment:
```bash
# Preview records (dry-run mapping & quality stats)
CATALOG_IMPORT_ENABLED=true \
CATALOG_DATABASE_URL=sqlite:///./catalog-local.sqlite3 \
python -m app.catalog.buildcores_opendb_cli preview \
  --source C:/Users/sulta/Documents/buildcores-open-db \
  --max-total 300

# Stage records into database staging tables
CATALOG_IMPORT_ENABLED=true \
CATALOG_DATABASE_URL=sqlite:///./catalog-local.sqlite3 \
python -m app.catalog.buildcores_opendb_cli stage \
  --source C:/Users/sulta/Documents/buildcores-open-db

# Commit valid staged records to local SQLite
CATALOG_IMPORT_ENABLED=true \
CATALOG_WRITES_ENABLED=true \
CATALOG_DATABASE_URL=sqlite:///./catalog-local.sqlite3 \
python -m app.catalog.buildcores_opendb_cli commit-local \
  --source C:/Users/sulta/Documents/buildcores-open-db
```

## 7. Public Browsing Page Behavior
- **Routes:** `/components`, `/components/[category]`, `/components/[product-id]`, and `/compare`.
- **Search & Filters:** Real search matching brand/MPN/name with category and brand drop-downs.
- **Pricing:** Displays "Price unavailable" and does not invent mock offers.
- **Images:** Renders a clean CSS placeholder if no approved media is available.

## 8. Rollback and Non-Mutating Verification
- **Production Safety:** Both production PostgreSQL and the compatibility Neo4j database are completely untouched.
- **Rollback Procedure:** Delete the local SQLite database file `catalog-local.sqlite3` or execute:
  ```bash
  alembic downgrade base
  ```
