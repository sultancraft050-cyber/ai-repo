# BuildCores OpenDB — Attribution Notice

This project imports structured hardware product metadata from the
**BuildCores OpenDB** database under the terms of the
**Open Data Commons Attribution License (ODC-By 1.0)**.

---

## Database Information

| Field | Value |
|---|---|
| Database name | BuildCores OpenDB |
| Upstream repository | https://github.com/buildcores/buildcores-open-db |
| License | Open Data Commons Attribution License (ODC-By) v1.0 |
| License file | LICENSE.txt |
| Attribution requirement | Required for any public conveyance of the database or derivative database |

---

## Attribution Notice

> Portions of this product catalog are derived from the
> **BuildCores OpenDB** database, available at
> https://github.com/buildcores/buildcores-open-db,
> licensed under the Open Data Commons Attribution License (ODC-By) v1.0.
>
> This project does not claim ownership of the source data.
> All hardware metadata originating from BuildCores OpenDB
> is attributed to the respective copyright holders.

---

## Import Provenance

| Field | Value |
|---|---|
| Upstream commit SHA | 784f6c2b5988bf5a7e94bd2121f9d56521386dd9 |
| Retrieval timestamp | 2026-07-18T21:41:25Z |
| Import date | 2026-07-18 |
| Import executed by | Automated bounded import pipeline |

---

## Categories Imported

| Category | OpenDB Folder | Max Records |
|---|---|---|
| CPU | open-db/CPU/ | 40 |
| GPU | open-db/GPU/ | 40 |
| Motherboard | open-db/Motherboard/ | 40 |
| RAM | open-db/RAM/ | 40 |
| Storage | open-db/Storage/ | 40 |
| PSU | open-db/PSU/ | 30 |
| Case | open-db/PCCase/ | 30 |
| CPU Cooler | open-db/CPUCooler/ | 20 |

**Total bounded import limit:** 300 products

---

## What Was Imported

- Product name, manufacturer, series, variant, manufacturer part numbers
- Structured technical specifications (socket, TDP, memory type, etc.)

## What Was Explicitly NOT Imported

- Prices or price history
- Retailer offers, store SKUs, or affiliate links
- Product images or image URLs
- 3D models or assets
- BuildCores branding assets
- BuildCores application code
- Private/internal BuildCores API data
- Retailer inventory or stock information

---

## Excluded Source Fields

The following fields from `general_product_information` were **not imported**:
`amazon_sku`, `newegg_sku`, `walmart_sku`, and any other retailer identifiers.

---

## Mapping Rules

1. `opendb_id` → stored as source identifier in `ImportSource` / `ImportBatch` provenance
2. `metadata.manufacturer` → `Product.brand`
3. `metadata.part_numbers[0]` → `Product.manufacturer_part_number`
4. `metadata.name` → `Product.canonical_name`
5. `metadata.series` → (informational, included in canonical name)
6. `metadata.variant` → `Product.variant`
7. Category-specific technical fields → `ProductSpecification` rows
8. `general_product_information` → **excluded entirely**

---

## Identity Priority

1. **GTIN** — used when available (OpenDB does not currently expose GTIN)
2. **Normalized manufacturer + manufacturer part number** — primary stable identity
3. **OpenDB source ID** — preserved in import batch provenance; not used as GTIN

---

## License Text Reference

The full ODC-By 1.0 license text is available at:
- https://opendatacommons.org/licenses/by/1-0/
- `LICENSE.txt` in the source repository

---

## Machine-Readable Provenance

Every `ImportSource` record created by this import contains:
```
name = "BuildCores OpenDB (commit: <SHA>)"
source_type = JSON
rights_status = APPROVED
```

Every `ImportBatch` record contains:
```
entity_type = PRODUCT
source_id = <ImportSource.id>
```

Every `ProductSpecification` record contains:
```
source_id = <ImportSource.id>
```
