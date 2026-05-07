"use client";

import { AlertTriangle, Store } from "lucide-react";
import type { SaudiBuildComponent } from "@/types/builder";

type BuildComponentRowProps = {
  component: SaudiBuildComponent;
};

export function BuildComponentRow({ component }: BuildComponentRowProps) {
  return (
    <div className="grid gap-3 rounded-md border border-line bg-panel px-3 py-3 md:grid-cols-[1.1fr_0.9fr]">
      <div className="min-w-0">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="rounded border border-line bg-white px-2 py-0.5 text-[11px] font-semibold uppercase text-muted">
            {component.category}
          </span>
          <StockBadge stock={component.stock_badge} />
        </div>
        <h4 className="truncate text-sm font-semibold text-ink">{component.name}</h4>
        <p className="mt-1 text-xs leading-5 text-muted">{component.reason_selected}</p>
        {component.warnings.length ? (
          <div className="mt-2 flex items-start gap-1.5 text-xs leading-5 text-caution">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden />
            <span>{component.warnings[0]}</span>
          </div>
        ) : null}
      </div>
      <div className="grid gap-2 text-xs text-muted">
        <div className="flex items-center justify-between gap-2">
          <span>Recommended</span>
          <strong className="text-sm text-ink">{formatSar(component.recommended_price_sar)}</strong>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span>Lowest market</span>
          <strong className="text-sm text-ink">{formatSar(component.lowest_market_price_sar)}</strong>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1">
            <Store size={13} aria-hidden />
            Vendor
          </span>
          <strong className="max-w-[160px] truncate text-right text-ink">{component.recommended_vendor ?? "Unknown"}</strong>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <MetaBadge value={component.vat_status} />
          <MetaBadge value={component.shipping_status} />
          <MetaBadge value={component.warranty_status} />
        </div>
      </div>
    </div>
  );
}

function StockBadge({ stock }: { stock: SaudiBuildComponent["stock_badge"] }) {
  const label = stock === "local" ? "Local" : stock === "gcc" ? "GCC" : stock === "imported" ? "Imported" : "Unknown stock";
  const classes =
    stock === "local"
      ? "border-teal-200 bg-teal-50 text-teal-700"
      : stock === "imported"
        ? "border-amber-200 bg-amber-50 text-amber-700"
        : "border-line bg-white text-muted";
  return <span className={`rounded border px-2 py-0.5 text-[11px] font-semibold ${classes}`}>{label}</span>;
}

function MetaBadge({ value }: { value: string }) {
  return <span className="rounded border border-line bg-white px-2 py-0.5 text-[11px] font-semibold text-muted">{value.replaceAll("_", " ")}</span>;
}

function formatSar(value?: number | null) {
  if (value === null || value === undefined) return "Unavailable";
  return new Intl.NumberFormat("en-SA", {
    style: "currency",
    currency: "SAR",
    maximumFractionDigits: 0
  }).format(value);
}
