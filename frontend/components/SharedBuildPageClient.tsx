"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, Clock3, Download, ShieldCheck } from "lucide-react";
import { BuildRecommendationCard } from "@/components/BuildRecommendationCard";
import { getSharedBuild } from "@/lib/api";
import type { SavedBuild, SaudiBuildOption } from "@/types/builder";

export function SharedBuildPageClient({ slug }: { slug: string }) {
  const [build, setBuild] = useState<SavedBuild | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getSharedBuild(slug)
      .then(setBuild)
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Shared build not found."));
  }, [slug]);

  const payload = build?.build_payload as SaudiBuildOption | undefined;
  const shareSummary = payload?.summary;
  const warningCount = shareSummary?.warning_summary?.length ?? build?.warning_summary?.length ?? 0;
  const budgetStatus = shareSummary?.budget_status?.replaceAll("_", " ") ?? "budget status unavailable";
  const generatedAt = build?.created_at ? formatDate(build.created_at) : null;
  const hasRenderableBuild = Boolean(
    payload?.components?.length &&
      payload.summary &&
      payload.explanation &&
      payload.confidence_breakdown &&
      payload.export
  );

  return (
    <main className="min-h-screen">
      <div className="mx-auto grid w-full max-w-5xl gap-4 px-4 py-6 sm:px-6">
        <header className="rounded-lg border border-line bg-white p-4 shadow-tight">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-signal">
            <ShieldCheck size={15} aria-hidden />
            Shared Saudi Build
          </div>
          <h1 className="text-2xl font-semibold text-ink">{build?.title ?? "Loading shared build"}</h1>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-muted">
            Public build summary with Saudi prices, warnings, confidence, and component choices. Store pages should still be verified before purchase.
          </p>
          {build ? (
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted">
              <span className="rounded border border-line bg-panel px-2 py-1">Region {build.region}</span>
              <span className="rounded border border-line bg-panel px-2 py-1">{formatSar(build.total_price_sar)}</span>
              <span className="rounded border border-line bg-panel px-2 py-1">{build.confidence_level} confidence</span>
              {generatedAt ? (
                <span className="inline-flex items-center gap-1 rounded border border-line bg-panel px-2 py-1">
                  <Clock3 size={12} aria-hidden />
                  Generated {generatedAt}
                </span>
              ) : null}
            </div>
          ) : null}
        </header>

        {error ? (
          <div className="flex items-start gap-2 rounded-lg border border-caution/40 bg-amber-50 p-4 text-sm text-caution">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden />
            <div>
              <div className="font-semibold">Shared build not available</div>
              <p className="mt-1 leading-6">{error} The owner may have disabled public sharing or the link may be wrong.</p>
              <a href="/#builder" className="mt-3 inline-flex rounded-md border border-caution/40 px-3 py-2 text-xs font-semibold">
                Start a new build
              </a>
            </div>
          </div>
        ) : null}

        {hasRenderableBuild && payload ? (
          <>
            <section className="grid gap-3 rounded-lg border border-line bg-white p-4 shadow-tight md:grid-cols-3">
              <ShareMetric label="Budget" value={budgetStatus} tone={payload.summary.budget_status === "under_budget" ? "signal" : "caution"} />
              <ShareMetric label="Warnings" value={warningCount ? `${warningCount} visible` : "None visible"} tone={warningCount ? "caution" : "signal"} />
              <ShareMetric label="Saudi price context" value="SAR only" tone="signal" />
              <div className="md:col-span-3 grid gap-2 rounded-md border border-caution/30 bg-amber-50 px-3 py-2 text-sm leading-6 text-caution">
                <span>
                  Prices, VAT, shipping, warranty, and stock may change after this build was shared. Verify each linked store page before buying.
                </span>
              </div>
              <div className="flex flex-wrap gap-2 md:col-span-3">
                <a
                  href="/#builder"
                  className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-signal bg-signal px-3 text-sm font-semibold text-slate-950"
                >
                  Start your own build
                  <ArrowRight size={15} aria-hidden />
                </a>
              </div>
            </section>
            <BuildRecommendationCard build={payload} />
            <section className="rounded-lg border border-line bg-white p-4 shadow-tight">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
                <Download size={15} aria-hidden />
                Export
              </div>
              <pre className="max-h-72 overflow-auto rounded-md border border-line bg-panel p-3 text-xs leading-5 text-muted">
                {payload.export?.markdown_summary ?? JSON.stringify(payload.export?.json_summary ?? payload, null, 2)}
              </pre>
            </section>
          </>
        ) : !error ? (
          <div className="rounded-lg border border-line bg-white p-4 text-sm leading-6 text-muted shadow-tight">
            {build ? "This shared build is missing public component details. The owner may need to resave it." : "Loading build details..."}
          </div>
        ) : null}
      </div>
    </main>
  );
}

function ShareMetric({
  label,
  value,
  tone
}: {
  label: string;
  value: string;
  tone: "signal" | "caution";
}) {
  return (
    <div className="rounded-md border border-line bg-panel p-3">
      <div className="text-xs font-semibold uppercase text-muted">{label}</div>
      <div className={`mt-1 text-lg font-semibold capitalize ${tone === "signal" ? "text-signal" : "text-caution"}`}>
        {value}
      </div>
    </div>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-SA", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

function formatSar(value?: number | null) {
  if (value === null || value === undefined) return "Unavailable";
  return new Intl.NumberFormat("en-SA", {
    style: "currency",
    currency: "SAR",
    maximumFractionDigits: 0
  }).format(value);
}
