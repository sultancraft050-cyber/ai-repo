"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Database, Loader2, RefreshCw } from "lucide-react";
import { getCatalogCompleteness } from "@/lib/api";
import type { CatalogCompletenessResponse, CategoryCoverage } from "@/types/builder";

export function CatalogCompletenessPanel() {
  const [catalog, setCatalog] = useState<CatalogCompletenessResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setCatalog(await getCatalogCompleteness("SA", "Riyadh"));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load catalog completeness.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <section className="rounded-lg border border-line bg-white p-4 shadow-tight">
      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase text-signal">
            <Database size={15} aria-hidden />
            Catalog completeness
          </div>
          <h2 className="text-base font-semibold text-ink">Saudi Catalog Quality Coverage</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-muted">
            Shows build-critical readiness, weak catalog areas, stale data, duplicate risk, and approval-safe next actions.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="inline-flex h-9 items-center gap-2 rounded-md border border-line bg-panel px-3 text-sm font-semibold text-ink hover:bg-white"
        >
          {loading ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <RefreshCw size={15} aria-hidden />}
          Refresh
        </button>
      </div>

      {error ? (
        <div className="mb-3 flex items-start gap-2 rounded-md border border-caution/40 bg-amber-50 px-3 py-2 text-sm text-caution">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden />
          {error}
        </div>
      ) : null}

      {catalog ? (
        <div className="grid gap-4">
          <div className="grid gap-2 md:grid-cols-4">
            <Metric label="Readiness" value={`${Math.round(catalog.readiness_score * 100)}%`} />
            <Metric label="Weak categories" value={String(catalog.weak_categories.length)} />
            <Metric label="Stale categories" value={String(catalog.stale_categories.length)} />
            <Metric label="Duplicate risk" value={String(catalog.duplicate_risk_categories.length)} />
          </div>

          <p className="rounded-md border border-line bg-panel px-3 py-2 text-sm text-muted">{catalog.message}</p>

          <div className="grid gap-3 xl:grid-cols-[1.2fr_0.8fr]">
            <CoverageTable title="Build-critical categories" items={catalog.build_critical_categories} />
            <CoverageTable title="Other catalog categories" items={catalog.non_critical_categories.slice(0, 8)} compact />
          </div>

          {catalog.next_actions.length ? (
            <div className="rounded-md border border-caution/30 bg-amber-50 p-3">
              <div className="mb-2 text-sm font-semibold text-caution">Suggested next actions</div>
              <div className="grid gap-2 md:grid-cols-2">
                {catalog.next_actions.slice(0, 8).map((job) => (
                  <div key={`${job.category}-${job.query}`} className="rounded border border-amber-200 bg-white p-2 text-xs leading-5 text-muted">
                    <div className="font-semibold text-ink">{job.category}</div>
                    <div>{job.query}</div>
                    <div className="mt-1 text-caution">{job.reason}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : loading ? (
        <div className="rounded-md border border-line bg-panel px-3 py-6 text-center text-sm text-muted">Loading catalog coverage...</div>
      ) : null}
    </section>
  );
}

function CoverageTable({ title, items, compact = false }: { title: string; items: CategoryCoverage[]; compact?: boolean }) {
  return (
    <div className="rounded-md border border-line bg-panel p-3">
      <div className="mb-2 text-sm font-semibold text-ink">{title}</div>
      <div className="grid gap-2">
        {items.map((item) => (
          <div key={item.category} className="rounded border border-line bg-white p-2 text-xs leading-5 text-muted">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-ink">{item.category}</span>
              <span className={item.readiness_level === "ready" ? "text-signal" : "text-caution"}>
                {item.readiness_level.replaceAll("_", " ")}
              </span>
            </div>
            <div className={`mt-1 grid gap-1 ${compact ? "" : "md:grid-cols-2"}`}>
              <span>{item.priced_product_count} priced</span>
              <span>{item.trusted_local_listing_count} trusted</span>
              <span>{Math.round(item.identity_confidence * 100)}% identity</span>
              <span>{item.price_freshness_status} prices</span>
            </div>
            {item.blocker_reasons[0] ? <div className="mt-1 text-caution">{item.blocker_reasons[0]}</div> : null}
            {!item.blocker_reasons[0] && item.warning_reasons[0] ? <div className="mt-1 text-caution">{item.warning_reasons[0]}</div> : null}
            <div className="mt-1 rounded border border-line bg-panel px-2 py-1">{item.next_action_type.replaceAll("_", " ")}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-panel px-3 py-2">
      <div className="text-xs font-semibold uppercase text-muted">{label}</div>
      <div className="mt-1 text-lg font-semibold text-ink">{value}</div>
    </div>
  );
}

