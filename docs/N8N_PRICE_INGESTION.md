# Automated n8n Price Ingestion Pipeline

This directory contains two importable n8n workflows for founder-operated Saudi product URL ingestion.

The workflows use the existing backend API only:

- `POST /sources/product-url/preview`
- `POST /sources/product-url/ingest`
- `POST /sources/product-url/refresh`

They do not crawl category pages, scrape search pages, add backend endpoints, store raw HTML, download product images, or hardcode secrets.

## Workflows

| Workflow | File | Purpose |
| --- | --- | --- |
| Telegram product URL import | `n8n/workflows/telegram-product-url-import.json` | Founder pastes a product URL into Telegram. n8n previews it, ingests only accepted priced listings, and replies with status. |
| Nightly known URL refresh | `n8n/workflows/nightly-known-url-refresh.json` | Runs daily at 03:00 Asia/Riyadh and refreshes up to 50 approved known product URLs. |

## Required n8n Configuration

Store these as n8n environment variables or credentials. Do not paste real values into workflow JSON.

```bash
BACKEND_BASE_URL=https://your-backend.example.com
ADMIN_API_KEY=store-in-n8n-secret
FOUNDER_TELEGRAM_CHAT_ID=123456789
```

Also configure the Telegram credential named `Telegram Bot` after importing both workflows.

Both workflow files set n8n success/error execution data retention to `none` by default. Keep that setting unless you have a secure private n8n instance and intentionally need execution payload debugging.

## Telegram Import Behavior

The import workflow accepts messages from `FOUNDER_TELEGRAM_CHAT_ID` only.

Supported input:

```text
https://www.pczonesa.com/en/category/motherboard/asus-prime-b650m-a-wifi-ii/
```

Fallback when category cannot be inferred:

```text
Motherboard https://www.pczonesa.com/en/category/accessory/ambiguous-slug/
```

The Code node strips common tracking parameters before building the idempotency key:

- `utm_*`
- `fbclid`
- `gclid`
- `msclkid`
- `_hsenc`
- `_hsmi`
- `ref`
- `tag`
- `spm`
- `scm`

Category inference is intentionally conservative. If a category is unclear, the workflow asks for an explicit category and does not call the backend.

## Preview Gate

The ingest HTTP request only runs when preview returns:

- `accepted: true`
- `price` or `item_price_sar`
- `source_policy_status` is not `blocked` or `unsupported`

Rejected previews produce a Telegram reply with the sanitized reason and no ingest call.

## Nightly Refresh

The refresh workflow posts:

```json
{
  "region": "SA",
  "limit": 50
}
```

It refreshes approved known URLs only through the backend. It does not discover new URLs. The Telegram summary includes refreshed, failed, and skipped counts plus sanitized top failures.

Noon Saudi and Amazon.sa may remain policy-gated depending on backend source policy.

## Validation

Run the local workflow validation script:

```bash
node n8n/scripts/validate-workflows.mjs
```

The script checks:

- expected endpoint paths
- no deprecated `/pricing/import-url` or `/pricing/known-url-refresh` calls
- founder chat allowlist logic
- URL sanitization and stable idempotency hash
- category inference examples
- unsupported domain and unknown category handling
- preview gating rules
- nightly 03:00 Asia/Riyadh schedule and limit 50
- no obvious literal secrets in workflow JSON

## Manual Smoke Test

1. Import both workflow JSON files into n8n.
2. Configure `Telegram Bot` credentials.
3. Set `BACKEND_BASE_URL`, `ADMIN_API_KEY`, and `FOUNDER_TELEGRAM_CHAT_ID`.
4. Keep the nightly workflow inactive until the founder intentionally enables automatic refresh.
5. Activate the Telegram workflow.
6. From the founder Telegram chat, send:

```text
https://www.pczonesa.com/en/category/motherboard/asus-prime-b650m-a-wifi-ii/
```

Expected result:

- preview runs first
- ingest runs only if preview is accepted and priced
- Telegram reply includes title, vendor, category, price/currency, canonical key, ingest status, warnings, and URL

Negative checks:

- Send the same URL with `utm_source` or `fbclid`; idempotency should remain stable.
- Send an unsupported domain; no backend call should run.
- Send an ambiguous product URL; workflow should ask for `Motherboard https://...` style input.
- Send from a non-founder chat; workflow should reply `Not authorized.` and stop.
