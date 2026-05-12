"use client";

import { AlertTriangle, CheckCircle2, ClipboardList, Info } from "lucide-react";
import type { SaudiBuildDataCompleteness } from "@/types/builder";

type DataCompletenessPanelProps = {
  completeness: SaudiBuildDataCompleteness | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
};

export function DataCompletenessPanel({ completeness, loading = false, error, onRetry }: DataCompletenessPanelProps) {
  if (loading) {
    return (
      <section className="rounded-lg border border-line bg-white p-4 shadow-tight">
        <div className="mb-3 h-5 w-48 animate-pulse rounded bg-slate-200" />
        <div className="grid gap-2 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-20 animate-pulse rounded-md border border-line bg-panel" />
          ))}
        </div>
      </section>
    );
  }

  if (!completeness) {
    return (
      <section className="rounded-lg border border-line bg-white p-4 shadow-tight">
        <PanelTitle />
        {error ? <InlineError message={error} onRetry={onRetry} /> : null}
        <p className="text-sm text-muted">No Saudi build readiness data yet.</p>
      </section>
    );
  }

  const readinessPercent = Math.round(completeness.readiness_score * 100);

  return (
    <section className="rounded-lg border border-line bg-white p-4 shadow-tight">
      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <PanelTitle />
        <span className="inline-flex w-fit items-center rounded border border-line bg-panel px-2 py-1 text-xs font-semibold text-ink">
          {readinessPercent}% ready
        </span>
      </div>
      {error ? <InlineError message={error} onRetry={onRetry} /> : null}
      <p className="mb-3 text-sm text-muted">{completeness.message}</p>

      <div className="grid gap-2 md:grid-cols-4">
        {completeness.category_coverage.map((coverage) => (
          <div key={coverage.category} className="rounded-md border border-line bg-panel px-3 py-2">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-sm font-semibold text-ink">{coverage.category}</span>
              <ReadinessBadge level={coverage.readiness_level} />
            </div>
            <div className="grid gap-1 text-xs text-muted">
              <span>{coverage.priced_product_count} priced products</span>
              <span>{coverage.trusted_local_listing_count} trusted listings</span>
              <span>{Math.round(coverage.identity_confidence * 100)}% identity confidence</span>
              <span>Freshness: {coverage.price_freshness_status}</span>
              {coverage.usable_with_warnings_count ? <span>{coverage.usable_with_warnings_count} usable with warnings</span> : null}
              <span>{coverage.risky_listing_count} risky listings</span>
            </div>
            {coverage.blocker_reasons.length ? (
              <div className="mt-2 grid gap-1 text-[11px] leading-4 text-caution">
                {coverage.blocker_reasons.slice(0, 2).map((reason) => (
                  <span key={reason}>{reason}</span>
                ))}
              </div>
            ) : null}
            {coverage.readiness_level === "usable_with_warnings" ? (
              <div className="mt-2 grid gap-1 text-[11px] leading-4 text-caution">
                {coverage.unknown_vat_count ? <span>{coverage.unknown_vat_count} VAT unclear</span> : null}
                {coverage.unknown_shipping_count ? <span>{coverage.unknown_shipping_count} shipping unclear</span> : null}
                {coverage.unknown_warranty_count ? <span>{coverage.unknown_warranty_count} warranty unclear</span> : null}
                {coverage.warning_reasons.slice(0, 2).map((reason) => (
                  <span key={reason}>{reason}</span>
                ))}
              </div>
            ) : null}
            {coverage.notes.length ? (
              <p className="mt-2 text-xs leading-5 text-caution">{coverage.notes[0]}</p>
            ) : null}
            <p className="mt-2 rounded border border-line bg-white px-2 py-1 text-[11px] leading-4 text-muted">
              Next: {coverage.next_action}
            </p>
          </div>
        ))}
      </div>

      {completeness.recommended_discovery_jobs.length ? (
        <div className="mt-4 rounded-md border border-caution/30 bg-amber-50 px-3 py-3">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-caution">
            <ClipboardList size={16} aria-hidden />
            Suggested dry-run discovery jobs
          </div>
          <div className="grid gap-2">
            {completeness.recommended_discovery_jobs.slice(0, 6).map((job) => (
              <div key={`${job.category}-${job.query}`} className="rounded border border-amber-200 bg-white px-3 py-2">
                <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                  <span className="font-semibold text-ink">{job.category}</span>
                  <code className="rounded bg-panel px-2 py-1 text-xs text-muted">dry_run=true</code>
                </div>
                <p className="mt-1 text-xs leading-5 text-muted">{job.query}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function PanelTitle() {
  return (
    <div>
      <h2 className="text-base font-semibold text-ink">Saudi Build Readiness</h2>
      <p className="mt-1 text-sm text-muted">Checks whether each required category has usable Saudi market prices.</p>
    </div>
  );
}

function ReadinessBadge({ level }: { level: SaudiBuildDataCompleteness["category_coverage"][number]["readiness_level"] }) {
  if (level === "ready") {
    return (
      <span className="inline-flex items-center gap-1 rounded border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-signal">
        <CheckCircle2 size={13} aria-hidden />
        Ready
      </span>
    );
  }
  if (level === "usable_with_warnings") {
    return (
      <span className="inline-flex items-center gap-1 rounded border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-caution">
        <Info size={13} aria-hidden />
        Usable
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded border border-amber-200 bg-white px-2 py-0.5 text-[11px] font-semibold text-caution">
      <AlertTriangle size={13} aria-hidden />
      Not ready
    </span>
  );
}

function InlineError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="mb-3 flex flex-col gap-2 rounded-md border border-caution/40 bg-amber-50 px-3 py-2 text-sm text-caution sm:flex-row sm:items-center sm:justify-between">
      <span>{message}</span>
      {onRetry ? (
        <button type="button" onClick={onRetry} className="rounded border border-caution/40 px-2 py-1 text-xs font-semibold">
          Retry
        </button>
      ) : null}
    </div>
  );
}
