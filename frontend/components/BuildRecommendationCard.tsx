"use client";

import {
  AlertTriangle,
  Download,
  Gauge,
  PiggyBank,
  ShieldCheck,
  ShoppingCart,
  TrendingDown,
  TrendingUp,
  WalletCards
} from "lucide-react";
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

  const overageAmount = Math.round(Math.abs(build.summary.budget_remaining_or_overage ?? 0));
  const budgetLabel = build.summary.budget_status.replaceAll("_", " ");

  const buildWarnings: string[] = [];
  for (const component of build.components) {
    if (component.stock_badge === "imported") {
      buildWarnings.push(`Imported listing detected for ${component.category}: ${component.name}.`);
    }
    if (component.vat_status === "vat_unknown") {
      buildWarnings.push(`${component.category}: VAT is unknown.`);
    }
    if (component.shipping_status === "unknown_shipping") {
      buildWarnings.push(`${component.category}: shipping status is unknown.`);
    }
    if (component.warranty_status === "unknown_warranty") {
      buildWarnings.push(`${component.category}: warranty status is unknown.`);
    }
    if (component.warnings.length) {
      buildWarnings.push(...component.warnings);
    }
  }
  const riskWarnings = Array.from(new Set(buildWarnings)).slice(0, 10);

  const confidenceRows = [
    ["Compatibility", build.confidence_breakdown.compatibility_confidence],
    ["Market", build.confidence_breakdown.market_confidence],
    ["Vendor", build.confidence_breakdown.vendor_confidence],
    ["Pricing", build.confidence_breakdown.pricing_confidence],
    ["Shipping", build.confidence_breakdown.shipping_confidence],
    ["Warranty", build.confidence_breakdown.warranty_confidence]
  ] as const;

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
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted">{build.explanation.summary}</p>
          {overBudget ? <p className="mt-2 text-sm text-caution">This build is {overageAmount} SAR over your budget.</p> : null}
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

      <div className="mt-4 grid gap-3 lg:grid-cols-[1.3fr_1fr]">
        <section className="rounded-md border border-line bg-panel p-3">
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted">
            <ShieldCheck size={13} aria-hidden />
            Build Summary
          </div>
          <p className="text-sm leading-6 text-muted">{build.explanation.budget_analysis}</p>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <InfoList title="Strengths" items={build.explanation.strengths} fallback="No major strength reported." />
            <InfoList title="Weaknesses" items={build.explanation.weaknesses} fallback="No major weakness reported." />
          </div>
        </section>

        <section className="rounded-md border border-line bg-panel p-3">
          <div className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted">
            <Gauge size={13} aria-hidden />
            Confidence Breakdown
          </div>
          <div className="grid gap-2">
            {confidenceRows.map(([label, value]) => (
              <ConfidenceBar key={label} label={label} value={value} />
            ))}
          </div>
        </section>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <section className="rounded-md border border-line bg-panel p-3">
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted">
            <TrendingDown size={13} aria-hidden />
            Savings Suggestions
          </div>
          {build.savings_suggestions.length ? (
            <div className="grid gap-2">
              {build.savings_suggestions.slice(0, 4).map((suggestion) => (
                <div key={`${suggestion.category}-${suggestion.alternative}`} className="rounded border border-line bg-white p-2 text-xs leading-5 text-muted">
                  <div className="font-semibold text-ink">
                    {suggestion.category}: {suggestion.alternative}
                  </div>
                  <div>{suggestion.reason}</div>
                  <div className="mt-1 text-caution">
                    Saves about {suggestion.estimated_savings_sar ? formatSar(suggestion.estimated_savings_sar) : "an unknown amount"}.
                    Impact: {suggestion.performance_impact}.
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs leading-5 text-muted">No safe cheaper ingested substitution is available yet.</p>
          )}
        </section>

        <section className="rounded-md border border-line bg-panel p-3">
          <InfoList title="Visible Risks" items={build.explanation.risks.length ? build.explanation.risks : riskWarnings} fallback="No visible marketplace warning." />
        </section>

        <section className="rounded-md border border-line bg-panel p-3">
          <InfoList title="Upgrade Path" items={build.explanation.upgrade_path} fallback="No upgrade guidance available." />
          <div className="mt-3">
            <InfoList title="Future Limits" items={build.explanation.future_limitations} fallback="No future limitation reported." />
          </div>
        </section>
      </div>

      <details className="mt-4 rounded-md border border-line bg-panel px-3 py-2">
        <summary className="cursor-pointer text-sm font-semibold text-ink">Buying order, component reasons, and export</summary>
        <div className="mt-3 grid gap-3 lg:grid-cols-[0.8fr_1.2fr]">
          <section className="rounded-md border border-line bg-white p-3">
            <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted">
              <ShoppingCart size={13} aria-hidden />
              Recommended Purchase Order
            </div>
            <ol className="grid gap-1 pl-4 text-xs leading-5 text-muted list-decimal">
              {build.explanation.recommended_purchase_order.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ol>
          </section>

          <section className="rounded-md border border-line bg-white p-3">
            <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted">
              <TrendingUp size={13} aria-hidden />
              Component Reasons
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              {build.explanation.component_explanations.map((item) => (
                <div key={item.category} className="rounded border border-line bg-panel p-2 text-xs leading-5 text-muted">
                  <div className="font-semibold text-ink">{item.category}</div>
                  <div>{item.reason_selected}</div>
                  <div className="mt-1">{item.risk_summary}</div>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="mt-3 rounded-md border border-line bg-white p-3">
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted">
            <Download size={13} aria-hidden />
            Export
          </div>
          <div className="grid gap-2 text-xs leading-5 text-muted md:grid-cols-[240px_1fr]">
            <span className="rounded border border-line bg-panel px-2 py-1 text-ink">{build.export.shareable_build_url}</span>
            <pre className="max-h-32 overflow-auto rounded border border-line bg-panel p-2 font-mono text-[11px] leading-5 text-muted">
              {build.export.markdown_summary}
            </pre>
          </div>
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

function InfoList({
  title,
  items,
  fallback,
  children
}: {
  title: string;
  items: string[];
  fallback?: string;
  children?: ReactNode;
}) {
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
        {children}
      </div>
    </div>
  );
}

function ConfidenceBar({ label, value }: { label: string; value: number }) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div className="grid gap-1">
      <div className="flex items-center justify-between gap-2 text-xs text-muted">
        <span>{label}</span>
        <strong className="text-ink">{pct}%</strong>
      </div>
      <div className="h-2 overflow-hidden rounded bg-white">
        <div className="h-full rounded bg-signal" style={{ width: `${pct}%` }} />
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
