"use client";

import { AlertTriangle, Gauge, PiggyBank, ShieldCheck, WalletCards } from "lucide-react";
import type { ReactNode } from "react";
import { BuildComponentRow } from "@/components/BuildComponentRow";
import type { SaudiBuildOption } from "@/types/builder";

type BuildRecommendationCardProps = {
  build: SaudiBuildOption;
};

export function BuildRecommendationCard({ build }: BuildRecommendationCardProps) {
  const overBudget =
    build.summary.budget_remaining_or_overage !== null &&
    build.summary.budget_remaining_or_overage !== undefined &&
    build.summary.budget_remaining_or_overage < 0;
  const budgetLabel = build.summary.budget_status.replaceAll("_", " ");

  return (
    <article className="rounded-lg border border-line bg-white p-4 shadow-tight">
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="rounded border border-line bg-panel px-2 py-1 text-xs font-semibold uppercase text-muted">
              {build.label.replaceAll("_", " ")}
            </span>
            <span className="rounded border border-teal-200 bg-teal-50 px-2 py-1 text-xs font-semibold text-teal-700">
              {build.summary.confidence_level} confidence
            </span>
            {build.summary.components_with_uncertainty.length ? (
              <span className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-semibold text-caution">
                Build generated with market-data warnings
              </span>
            ) : null}
            <span
              className={`rounded border px-2 py-1 text-xs font-semibold ${
                overBudget ? "border-amber-200 bg-amber-50 text-caution" : "border-teal-200 bg-teal-50 text-teal-700"
              }`}
            >
              {budgetLabel}
            </span>
          </div>
          <h3 className="text-lg font-semibold text-ink">{build.title}</h3>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted">{build.why_this_build}</p>
        </div>
        <div className="grid min-w-[240px] gap-2 rounded-md border border-line bg-panel p-3">
          <Metric
            icon={<WalletCards size={15} />}
            label="Recommended total"
            value={formatSar(build.summary.total_recommended_price_sar)}
          />
          <Metric
            icon={<Gauge size={15} />}
            label={overBudget ? "Over budget" : "Budget remaining"}
            value={formatSar(Math.abs(build.summary.budget_remaining_or_overage ?? 0))}
            tone={overBudget ? "caution" : "signal"}
          />
          <Metric
            icon={<PiggyBank size={15} />}
            label="Budget"
            value={formatSar(build.summary.budget_sar)}
          />
          <Metric
            icon={<ShieldCheck size={15} />}
            label="Compatibility"
            value={build.summary.compatibility_status.replaceAll("_", " ")}
          />
        </div>
      </div>

      <div className="grid gap-3">
        {build.components.map((component) => (
          <BuildComponentRow key={`${component.category}-${component.product_id}`} component={component} />
        ))}
      </div>

      <details className="mt-4 rounded-md border border-line bg-panel px-3 py-2">
        <summary className="cursor-pointer text-sm font-semibold text-ink">Risks, bottlenecks, and upgrade notes</summary>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <InfoList title="Budget Pressure" items={build.summary.most_expensive_components} fallback="No budget pressure reported." />
          <InfoList title="Savings" items={build.summary.easiest_savings_opportunities} fallback="No cheaper ingested substitution found." />
          <InfoList title="Risk Summary" items={build.summary.risk_summary} fallback="No major market risk reported." />
          <InfoList title="Market Warnings" items={build.summary.warning_summary} fallback="No category-level market warning reported." />
          <InfoList title="Bottleneck" items={[build.summary.bottleneck_summary]} />
          <InfoList title="Upgrade Notes" items={build.upgrade_notes} />
        </div>
      </details>
    </article>
  );
}

function Metric({
  icon,
  label,
  value,
  tone
}: {
  icon: ReactNode;
  label: string;
  value: string;
  tone?: "signal" | "caution";
}) {
  const valueClass = tone === "caution" ? "text-caution" : tone === "signal" ? "text-signal" : "text-ink";
  return (
    <div className="flex items-center justify-between gap-3 text-xs text-muted">
      <span className="inline-flex items-center gap-1.5">
        {icon}
        {label}
      </span>
      <strong className={`text-sm capitalize ${valueClass}`}>{value}</strong>
    </div>
  );
}

function InfoList({ title, items, fallback }: { title: string; items: string[]; fallback?: string }) {
  const visible = items.length ? items : fallback ? [fallback] : [];
  return (
    <div>
      <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted">
        <AlertTriangle size={13} aria-hidden />
        {title}
      </div>
      <div className="grid gap-1 text-xs leading-5 text-muted">
        {visible.map((item) => (
          <span key={item}>{item}</span>
        ))}
      </div>
    </div>
  );
}

function formatSar(value?: number | null) {
  if (value === null || value === undefined) return "Unavailable";
  return new Intl.NumberFormat("en-SA", {
    style: "currency",
    currency: "SAR",
    maximumFractionDigits: 0
  }).format(value);
}
