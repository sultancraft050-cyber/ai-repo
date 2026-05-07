"use client";

import { DatabaseZap, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { getKnownProductUrls, getSourceMatrix, refreshKnownProductUrls } from "@/lib/api";
import type { KnownProductUrlView, ProductUrlRefreshResponse, SourceMatrixEntry } from "@/types/builder";

export function KnownUrlRefreshPanel({
  apiKey,
  region
}: {
  apiKey: string;
  region: string;
}) {
  const [knownUrls, setKnownUrls] = useState<KnownProductUrlView[]>([]);
  const [sourceMatrix, setSourceMatrix] = useState<SourceMatrixEntry[]>([]);
  const [refreshResult, setRefreshResult] = useState<ProductUrlRefreshResponse | null>(null);
  const [vendor, setVendor] = useState("");
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState<"load" | "refresh" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadKnownUrls();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiKey, region]);

  async function loadKnownUrls() {
    if (!apiKey) return;
    setLoading("load");
    setError(null);
    try {
      const [urls, matrix] = await Promise.all([
        getKnownProductUrls(apiKey, { region, category: category || undefined, vendor: vendor || undefined, limit: 20 }),
        getSourceMatrix(apiKey, region)
      ]);
      setKnownUrls(urls);
      setSourceMatrix(matrix);
    } catch (loadError) {
      setError(errorMessage(loadError, "Unable to load known product URLs."));
    } finally {
      setLoading(null);
    }
  }

  async function refreshUrls() {
    const confirmed = window.confirm("Refresh approved known product URLs only? This will not discover or crawl new links.");
    if (!confirmed) return;
    setLoading("refresh");
    setError(null);
    try {
      const result = await refreshKnownProductUrls(apiKey, {
        region,
        category: category || undefined,
        vendor: vendor || undefined,
        limit: 20
      });
      setRefreshResult(result);
      await loadKnownUrls();
    } catch (refreshError) {
      setError(errorMessage(refreshError, "Unable to refresh known product URLs."));
    } finally {
      setLoading(null);
    }
  }

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900 p-3">
      <div className="mb-3 flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase text-teal-300">
            <DatabaseZap size={15} aria-hidden />
            Known URL refresh
          </div>
          <p className="mt-1 text-xs text-slate-500">Refreshes approved ProductURL nodes only. Search/category pages and unknown links stay blocked.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            value={vendor}
            onChange={(event) => setVendor(event.target.value)}
            placeholder="Vendor filter"
            className="h-9 w-36 rounded-md border border-slate-700 bg-slate-950 px-2 text-sm text-slate-100 placeholder:text-slate-600"
          />
          <input
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            placeholder="Category"
            className="h-9 w-28 rounded-md border border-slate-700 bg-slate-950 px-2 text-sm text-slate-100 placeholder:text-slate-600"
          />
          <button
            type="button"
            onClick={loadKnownUrls}
            disabled={loading !== null}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-slate-700 px-3 text-sm font-semibold text-slate-200 disabled:text-slate-500"
          >
            Load
          </button>
          <button
            type="button"
            onClick={refreshUrls}
            disabled={loading !== null}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-teal-600 px-3 text-sm font-semibold text-white disabled:bg-slate-700 disabled:text-slate-400"
          >
            <RefreshCw size={15} className={loading === "refresh" ? "animate-spin" : ""} aria-hidden />
            Refresh
          </button>
        </div>
      </div>
      {error ? <div className="mb-3 rounded border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-100">{error}</div> : null}
      <div className="grid gap-3 xl:grid-cols-[1fr_0.8fr]">
        <div className="rounded border border-slate-800 bg-slate-950">
          <div className="grid grid-cols-[1fr_90px_100px] border-b border-slate-800 px-3 py-2 text-xs font-semibold uppercase text-slate-500">
            <span>Approved URL</span>
            <span>Price</span>
            <span>Status</span>
          </div>
          {loading === "load" && !knownUrls.length ? (
            <div className="px-3 py-6 text-sm text-slate-500">Loading approved product URLs...</div>
          ) : knownUrls.length ? (
            knownUrls.map((item) => (
              <div key={item.normalized_url} className="grid grid-cols-[1fr_90px_100px] gap-2 border-b border-slate-900 px-3 py-2 text-xs last:border-b-0">
                <div className="min-w-0">
                  <div className="font-semibold text-slate-200">{item.vendor_name}</div>
                  <div className="truncate text-slate-500">{item.normalized_url}</div>
                  <div className="mt-1 text-slate-600">{item.category} · {item.region}</div>
                </div>
                <div className="text-slate-300">{item.last_price ? `${item.last_price.toLocaleString()} ${item.last_currency ?? ""}` : "n/a"}</div>
                <div className="capitalize text-slate-500">{item.source_policy_status.replaceAll("_", " ")}</div>
              </div>
            ))
          ) : (
            <div className="px-3 py-6 text-sm text-slate-500">No approved product URLs yet. Preview and ingest one exact product page first.</div>
          )}
        </div>
        <div className="grid gap-3">
          <div className="rounded border border-slate-800 bg-slate-950 p-3">
            <h3 className="text-xs font-semibold uppercase text-slate-500">Source matrix</h3>
            <div className="mt-2 grid gap-2">
              {sourceMatrix.map((source) => (
                <div key={source.source_name} className="rounded border border-slate-800 bg-slate-900 px-2 py-2 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-slate-200">{source.source_name}</span>
                    <span className="capitalize text-slate-500">{source.policy_status.replaceAll("_", " ")}</span>
                  </div>
                  <p className="mt-1 leading-5 text-slate-500">{source.known_url_refresh_supported === "policy_gated" ? "Refresh policy-gated" : "Known URL refresh allowed"} · broad scraping disabled</p>
                </div>
              ))}
            </div>
          </div>
          {refreshResult ? (
            <div className="rounded border border-slate-800 bg-slate-950 p-3 text-xs">
              <h3 className="font-semibold uppercase text-slate-500">Last refresh</h3>
              <p className="mt-1 text-slate-300">
                {refreshResult.refreshed_count} refreshed, {refreshResult.skipped_count} skipped, {refreshResult.failed_count} failed
              </p>
              <p className="mt-1 truncate text-slate-500">trace {refreshResult.trace_id}</p>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}
