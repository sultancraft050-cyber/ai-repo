"use client";

import { CheckCircle2, Link2, ShieldAlert, UploadCloud } from "lucide-react";
import { useState } from "react";
import { ingestProductUrl, previewProductUrl } from "@/lib/api";
import type { ProductCategory, ProductUrlPreviewResponse } from "@/types/builder";

const categories: ProductCategory[] = ["GPU", "CPU", "Motherboard", "RAM", "Storage", "PSU", "Case", "Cooler"];

export function ProductUrlImportPanel({
  apiKey,
  region,
  onIngested
}: {
  apiKey: string;
  region: string;
  onIngested?: () => void;
}) {
  const [url, setUrl] = useState("");
  const [category, setCategory] = useState<ProductCategory>("GPU");
  const [preview, setPreview] = useState<ProductUrlPreviewResponse | null>(null);
  const [loading, setLoading] = useState<"preview" | "ingest" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function submitPreview() {
    setLoading("preview");
    setError(null);
    setMessage(null);
    setPreview(null);
    try {
      const result = await previewProductUrl(apiKey, { url, region, category, dry_run: true });
      setPreview(result);
    } catch (previewError) {
      setError(errorMessage(previewError, "Unable to preview product URL."));
    } finally {
      setLoading(null);
    }
  }

  async function approveIngest() {
    if (!preview?.accepted) return;
    const confirmed = window.confirm("Approve ingest for this exact product URL? This writes Product, Vendor, PriceSnapshot, FieldEvidence, ProductURL, and AuditEvent metadata.");
    if (!confirmed) return;
    setLoading("ingest");
    setError(null);
    try {
      const result = await ingestProductUrl(apiKey, { url: preview.product_url, region, category });
      setMessage(`Ingested ${result.preview.vendor_name ?? "source"} listing with trace ${result.trace_id}.`);
      onIngested?.();
    } catch (ingestError) {
      setError(errorMessage(ingestError, "Unable to ingest product URL."));
    } finally {
      setLoading(null);
    }
  }

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900 p-3">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase text-teal-300">
            <Link2 size={15} aria-hidden />
            Product URL import
          </div>
          <p className="mt-1 text-xs text-slate-500">Single approved product pages only. No crawling, raw HTML storage, or image downloads.</p>
        </div>
      </div>
      <div className="grid gap-2 md:grid-cols-[1fr_150px_auto]">
        <label className="block">
          <span className="sr-only">Product URL</span>
          <input
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="Paste PCZone, Microless, MTC, Noon, or Amazon.sa product URL"
            className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 text-sm text-slate-100 placeholder:text-slate-600"
          />
        </label>
        <label className="block">
          <span className="sr-only">Category</span>
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value as ProductCategory)}
            className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 text-sm text-slate-100"
          >
            {categories.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={submitPreview}
          disabled={!url || loading !== null}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-teal-600 px-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
        >
          <UploadCloud size={16} aria-hidden />
          {loading === "preview" ? "Previewing" : "Preview"}
        </button>
      </div>
      {error ? <InlineMessage tone="error" text={error} /> : null}
      {message ? <InlineMessage tone="success" text={message} /> : null}
      {preview ? (
        <div className="mt-3 rounded-md border border-slate-800 bg-slate-950 p-3">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge accepted={preview.accepted} />
                <span className="rounded border border-slate-700 px-2 py-0.5 text-xs font-semibold text-slate-300">{preview.source_policy_status.replaceAll("_", " ")}</span>
                <span className="rounded border border-slate-700 px-2 py-0.5 text-xs font-semibold text-slate-300">{preview.product_type.replaceAll("_", " ")}</span>
              </div>
              <h3 className="mt-2 text-sm font-semibold text-slate-100">{preview.raw_title ?? "No title extracted"}</h3>
              <p className="mt-1 break-all text-xs text-slate-500">{preview.normalized_url}</p>
            </div>
            <div className="text-right">
              <div className="text-lg font-semibold text-white">{priceText(preview)}</div>
              <div className="text-xs text-slate-500">{preview.vendor_name ?? "Unknown vendor"}</div>
            </div>
          </div>
          <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Canonical" value={preview.canonical_key ?? "unresolved"} />
            <Metric label="Condition" value={preview.listing_condition.replaceAll("_", " ")} />
            <Metric label="VAT" value={preview.vat_status.replaceAll("_", " ")} />
            <Metric label="Shipping" value={preview.shipping_status.replaceAll("_", " ")} />
            <Metric label="Warranty" value={preview.warranty_status.replaceAll("_", " ")} />
            <Metric label="Risk" value={`${Math.round(preview.marketplace_risk_score * 100)}%`} />
            <Metric label="Final SAR" value={preview.final_landed_price_sar ? `${preview.final_landed_price_sar.toLocaleString()} SAR` : "incomplete"} />
            <Metric label="Recommendation" value={preview.recommendation_level.replaceAll("_", " ")} />
          </div>
          {preview.rejected_reasons.length || preview.flags.length ? (
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              <InfoList title="Rejected reasons" items={preview.rejected_reasons} fallback="No rejection reasons." />
              <InfoList title="Warnings / flags" items={preview.flags} fallback="No warning flags." />
            </div>
          ) : null}
          <div className="mt-3 flex justify-end">
            <button
              type="button"
              onClick={approveIngest}
              disabled={!preview.accepted || loading !== null}
              className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-teal-500 bg-teal-500/10 px-3 text-sm font-semibold text-teal-100 disabled:cursor-not-allowed disabled:border-slate-700 disabled:bg-slate-900 disabled:text-slate-500"
            >
              <CheckCircle2 size={16} aria-hidden />
              {loading === "ingest" ? "Ingesting" : "Approve ingest"}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function StatusBadge({ accepted }: { accepted: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs font-semibold ${accepted ? "border-teal-500/50 bg-teal-500/10 text-teal-200" : "border-amber-500/50 bg-amber-500/10 text-amber-200"}`}>
      <ShieldAlert size={13} aria-hidden />
      {accepted ? "accepted preview" : "blocked preview"}
    </span>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded border border-slate-800 bg-slate-900 px-2 py-1">
      <div className="text-slate-500">{label}</div>
      <div className="truncate font-semibold capitalize text-slate-200">{value}</div>
    </div>
  );
}

function InfoList({ title, items, fallback }: { title: string; items: string[]; fallback: string }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-900 px-3 py-2 text-xs">
      <div className="font-semibold text-slate-400">{title}</div>
      <div className="mt-1 space-y-1 text-slate-500">
        {items.length ? items.slice(0, 5).map((item) => <div key={item}>{item.replaceAll("_", " ")}</div>) : <div>{fallback}</div>}
      </div>
    </div>
  );
}

function InlineMessage({ tone, text }: { tone: "error" | "success"; text: string }) {
  const classes = tone === "error" ? "border-rose-500/40 bg-rose-500/10 text-rose-100" : "border-teal-500/40 bg-teal-500/10 text-teal-100";
  return <div className={`mt-3 rounded border px-3 py-2 text-sm ${classes}`}>{text}</div>;
}

function priceText(preview: ProductUrlPreviewResponse) {
  if (preview.price == null || !preview.currency) return "No price";
  return `${preview.price.toLocaleString()} ${preview.currency}`;
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}
