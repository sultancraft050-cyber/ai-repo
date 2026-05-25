"use client";

import { AlertTriangle, CheckCircle2, Info } from "lucide-react";
import { StateBadge, cx, focusRing, interactiveButton } from "@/components/ui/PublicUi";
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
        <div className="mb-3 h-5 w-48 rounded bg-slate-200 motion-safe:animate-pulse motion-reduce:animate-none" />
        <div className="grid gap-2 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-20 rounded-md border border-line bg-panel motion-safe:animate-pulse motion-reduce:animate-none" />
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
  const readyCount = completeness.category_coverage.filter((coverage) => coverage.readiness_level === "ready").length;
  const warningCount = completeness.category_coverage.filter((coverage) => coverage.readiness_level === "usable_with_warnings").length;
  const notReady = completeness.category_coverage.filter((coverage) => coverage.readiness_level === "not_ready");
  const attention = completeness.category_coverage.filter((coverage) => coverage.readiness_level !== "ready");
  const canGenerate = notReady.length === 0;

  return (
    <section className="rounded-lg border border-line bg-white p-4 shadow-tight">
      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <PanelTitle />
        <StateBadge className="w-fit rounded px-2 py-1 text-ink">
          {readinessPercent}% ready
        </StateBadge>
      </div>
      {error ? <InlineError message={error} onRetry={onRetry} /> : null}
      <div className={`rounded-md border px-3 py-3 ${canGenerate ? "border-teal-200 bg-teal-50" : "border-caution/30 bg-amber-50"}`}>
        <div className={`mb-1 flex items-center gap-2 text-sm font-semibold ${canGenerate ? "text-signal" : "text-caution"}`}>
          {canGenerate ? <CheckCircle2 size={16} aria-hidden /> : <AlertTriangle size={16} aria-hidden />}
          {canGenerate ? "Ready to generate a Saudi build" : "Some data needs review"}
        </div>
        <p className="text-sm leading-6 text-muted">{completeness.message}</p>
        <div className="mt-3 h-2 overflow-hidden rounded bg-white" role="meter" aria-label={`Saudi build readiness ${readinessPercent}%`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={readinessPercent}>
          <div className="h-2 rounded bg-signal" style={{ width: `${Math.max(4, readinessPercent)}%` }} />
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted">
          <StateBadge>{readyCount} ready</StateBadge>
          {warningCount ? <StateBadge tone="caution">{warningCount} usable</StateBadge> : null}
          {notReady.length ? <StateBadge tone="caution">{notReady.length} need data</StateBadge> : null}
        </div>
      </div>

      {attention.length ? (
        <div className="mt-3 grid gap-2">
          <div className="text-sm font-semibold text-ink">Review next</div>
          {attention.slice(0, 3).map((coverage) => (
            <div key={coverage.category} className="rounded-md border border-line bg-panel px-3 py-2 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold text-ink">{coverage.category}</span>
                <ReadinessBadge level={coverage.readiness_level} />
              </div>
              <p className="mt-1 leading-6 text-muted">{simpleCategoryMessage(coverage)}</p>
            </div>
          ))}
        </div>
      ) : null}

      <details className="mt-3 rounded-md border border-line bg-panel px-3 py-2">
        <summary className={cx("cursor-pointer text-sm font-semibold text-ink", focusRing)}>Advanced readiness details</summary>
        <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {completeness.category_coverage.map((coverage) => (
            <div key={coverage.category} className="rounded-md border border-line bg-white px-3 py-2">
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-ink">{coverage.category}</span>
                <ReadinessBadge level={coverage.readiness_level} />
              </div>
              <div className="grid gap-1 text-xs text-muted">
                <span>{coverage.priced_product_count} priced products</span>
                <span>{coverage.trusted_local_listing_count} trusted listings</span>
                <span>{Math.round(coverage.identity_confidence * 100)}% identity confidence</span>
                <span>Freshness: {coverage.price_freshness_status}</span>
                {coverage.unknown_vat_count ? <span>{coverage.unknown_vat_count} VAT unclear</span> : null}
                {coverage.unknown_shipping_count ? <span>{coverage.unknown_shipping_count} shipping unclear</span> : null}
                {coverage.unknown_warranty_count ? <span>{coverage.unknown_warranty_count} warranty unclear</span> : null}
                <span>{coverage.risky_listing_count} risky listings</span>
              </div>
              <p className="mt-2 rounded border border-line bg-panel px-2 py-1 text-[11px] leading-4 text-muted">
                Next: {coverage.next_action}
              </p>
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}

function PanelTitle() {
  return (
    <div>
      <h2 className="text-base font-semibold text-ink">Saudi Build Readiness</h2>
      <p className="mt-1 text-sm text-muted">Checks category readiness for Saudi build generation.</p>
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
    <span className="inline-flex items-center gap-1 rounded border border-amber-200 bg-white px-2 py-0.5 text-[11px] font-semibold text-caution" aria-label="Not ready">
      <AlertTriangle size={13} aria-hidden />
      Needs data
    </span>
  );
}

function InlineError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="mb-3 flex flex-col gap-2 rounded-md border border-caution/40 bg-amber-50 px-3 py-2 text-sm text-caution sm:flex-row sm:items-center sm:justify-between">
      <span>{message}</span>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className={cx("rounded border border-caution/40 px-2 py-1 text-xs font-semibold hover:bg-white", interactiveButton, focusRing)}
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}

function simpleCategoryMessage(coverage: SaudiBuildDataCompleteness["category_coverage"][number]) {
  if (coverage.readiness_level === "not_ready") {
    return coverage.blocker_reasons[0] ?? coverage.next_action ?? "More Saudi market data is needed before this category can be used.";
  }
  const warnings = [
    coverage.unknown_vat_count ? "VAT unclear" : null,
    coverage.unknown_shipping_count ? "shipping unclear" : null,
    coverage.unknown_warranty_count ? "warranty unclear" : null,
    coverage.risky_listing_count ? "some risky listings" : null
  ].filter(Boolean);
  if (warnings.length) {
    return `Usable, but ${warnings.slice(0, 3).join(", ")}.`;
  }
  return "Usable with visible warnings.";
}
