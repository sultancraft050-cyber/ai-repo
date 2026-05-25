"use client";

import { useEffect, useState } from "react";
import { ArrowRight, Clock3, Download, ShieldCheck } from "lucide-react";
import { BuildRecommendationCard } from "@/components/BuildRecommendationCard";
import { CalmNotice, SkeletonBlock, StateBadge, cx, focusRing, interactiveButton } from "@/components/ui/PublicUi";
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
            Public build summary with Saudi prices, confidence, and component choices.
          </p>
          {build ? (
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted">
              <StateBadge>Region {build.region}</StateBadge>
              <StateBadge>{formatSar(build.total_price_sar)}</StateBadge>
              <StateBadge tone="success">{build.confidence_level} confidence</StateBadge>
              {generatedAt ? (
                <StateBadge className="gap-1">
                  <Clock3 size={12} aria-hidden />
                  Generated {generatedAt}
                </StateBadge>
              ) : null}
            </div>
          ) : null}
        </header>

        {error ? (
          <CalmNotice title="Shared build not available" tone="caution">
            <span className="block">{error} The link may be unavailable.</span>
            <a
              href="/#builder"
              className={cx(
                "mt-3 inline-flex rounded-md border border-caution/40 px-3 py-2 text-xs font-semibold hover:bg-white",
                interactiveButton,
                focusRing
              )}
            >
                Start a new build
            </a>
          </CalmNotice>
        ) : null}

        {hasRenderableBuild && payload ? (
          <>
            <section className="grid gap-3 rounded-lg border border-line bg-white p-4 shadow-tight md:grid-cols-3">
              <ShareMetric label="Budget" value={budgetStatus} tone={payload.summary.budget_status === "under_budget" ? "signal" : "caution"} />
              <ShareMetric label="Review notes" value={warningCount ? `${warningCount} visible` : "None visible"} tone={warningCount ? "caution" : "signal"} />
              <ShareMetric label="Saudi price context" value="SAR only" tone="signal" />
              <CalmNotice title="Before buying" tone="info" className="md:col-span-3">
                Store price, stock, delivery, and warranty can change. Check the store page before purchase.
              </CalmNotice>
              <div className="flex flex-wrap gap-2 md:col-span-3">
                <a
                  href="/#builder"
                  className={cx(
                    "inline-flex h-9 items-center justify-center gap-2 rounded-md border border-signal bg-signal px-3 text-sm font-semibold text-slate-950 hover:bg-signal/90 active:bg-signal/80",
                    interactiveButton,
                    focusRing
                  )}
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
              <pre className="max-h-72 max-w-full overflow-auto whitespace-pre-wrap break-words rounded-md border border-line bg-panel p-3 text-xs leading-5 text-muted">
                {payload.export?.markdown_summary ?? JSON.stringify(payload.export?.json_summary ?? payload, null, 2)}
              </pre>
            </section>
          </>
        ) : !error ? (
          build ? (
            <CalmNotice title="Build details are unavailable" tone="info">
              The owner may need to resave this build.
            </CalmNotice>
          ) : (
            <SkeletonBlock className="h-28" label="Loading shared build details" />
          )
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
