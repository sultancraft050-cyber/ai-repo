# Product Image Rendering Implementation

**Date:** 2026-07-13
**Scope:** public product imagery in the manual picker and selected-build summary
**Data/deployment impact:** none; no production API, Neo4j, secret, image download, or deployment was used.

## Rendering inventory

| Location | Component | Image field | Previous behavior | New behavior |
|---|---|---|---|---|
| `frontend/components/ManualPartPicker.tsx` selected row | `PartRow` | `processed_image_url` then `image_url` | Optional empty-alt native image, fixed 64×48, no error fallback | `ProductImage` build-summary variant, explicit frame, meaningful alt/placeholder |
| `frontend/components/ManualPartPicker.tsx` picker cards | `ProductArtwork` / `ProductCard` | `processed_image_url` then `image_url` | Native image could be absent or fail, card-specific placeholder could vary | `ProductImage` card variant, contain fitting, stable 320×160 frame, one-shot fallback |

The audit found no separate product-image renderers in generated-build, shared-build, saved-build, comparison, recommendation, or vendor cards. Those contexts currently render product details without an image and therefore were not changed.

## Previous problems

Images could crop or collapse their frame, missing URLs removed the artwork entirely, broken URLs showed browser failure UI, and the selected-row image had no useful accessible description. There was no consistent URL policy or failure state.

## Reusable component contract

`frontend/components/ProductImage.tsx` accepts a URL, product name, category, explicit `width`/`height`, `card`/`build-summary`/`detail` variant, optional priority loading, and an optional class name. It uses a stable aspect-ratio container, `object-contain`, centered content, and explicit image dimensions. Normal images are lazy-loaded; `priority` is opt-in and is not used by current cards.

## Category placeholders

The local, lightweight inline SVG placeholder labels CPU, GPU, Motherboard, RAM, Storage, Power supply, Case, Cooler, and unknown categories. It is category-aware, theme-safe, and hidden from assistive technology while the surrounding placeholder supplies an accessible description.

## URL safety and broken-image behavior

Blank, malformed, unsupported-scheme, protocol-relative, and unapproved remote URLs use the placeholder without creating a request. Local root-relative assets are supported. HTTPS remote hosts require an explicit reviewed allowlist entry; the current deterministic fixture host is `cdn.example.test`. The component does not use Next.js remote optimization, so `next.config.mjs` was not broadened. A failed load flips a local state once and renders the placeholder; it never retries, clears selection, or exposes technical details.

## Accessibility and responsive results

Real images have alt text containing the product name and category. Placeholders have useful `role="img"` labels, while decorative SVG geometry is `aria-hidden`. Frames use contain fitting so long GPUs and tall cases remain visible without cropping. Explicit dimensions prevent layout shift at desktop, laptop, tablet, and mobile widths; the compact summary variant remains readable on narrow screens. Existing light/dark theme classes style both image and placeholder backgrounds.

## Tests

`frontend/e2e/workflows.spec.ts` adds deterministic synthetic coverage for approved external and local URLs, unsafe schemes, missing images, category placeholders, alt text, stable aspect ratio, lazy loading, and fallback rendering. Existing fixture-backed manual, generated, shared-build, viewport, and axe tests remain unchanged and continue to use mocked API responses only.

## Deferred work

There are no current image renderers in generated/shared/saved/comparison contexts to migrate. Future work should add image fields to those views only when their API contracts expose them, then add the detail variant and representative long/tall asset fixtures. No deletion or image-storage decision is made here.

## Future image-storage pipeline

Any future pipeline must use reviewed source domains, bounded downloads, malware/content checks, derived local/object-storage URLs, provenance, and explicit retention. This iteration intentionally performs none of those operations.

## Rollback procedure

Revert the `ProductImage` import/usages and remove the component and its fixture test/documentation changes. No backend, schema, environment, or deployment rollback is required.

Safe-off flags remain unchanged:

```text
PRICING_SCHEDULER_ENABLED=false
AUTONOMOUS_AGENTS_ENABLED=false
CPU_SPECS_SEED_ON_START=false
```
