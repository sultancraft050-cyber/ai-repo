"use client";

import { AlertTriangle, GitMerge, Loader2, ShieldAlert } from "lucide-react";
import type { CanonicalMergePreviewResponse, CpuDuplicateReport } from "@/types/builder";

type GraphIntegrityPanelProps = {
  report: CpuDuplicateReport | null;
  preview: CanonicalMergePreviewResponse | null;
  loading: boolean;
  previewingId: string | null;
  error: string | null;
  onLoad: () => void;
  onPreview: (productIds: string[]) => void;
};

export function GraphIntegrityPanel({
  report,
  preview,
  loading,
  previewingId,
  error,
  onLoad,
  onPreview
}: GraphIntegrityPanelProps) {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900 p-3 text-slate-100">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase text-teal-300">
            <GitMerge size={15} aria-hidden />
            Graph integrity
          </div>
          <h3 className="text-sm font-semibold text-white">CPU duplicate candidates</h3>
          <p className="mt-1 text-xs leading-5 text-slate-400">
            Detects same-model CPU products and opens approval-gated merge review. Preview is read-only.
          </p>
        </div>
        <button
          type="button"
          onClick={onLoad}
          disabled={loading}
          className="inline-flex h-8 items-center justify-center gap-2 rounded border border-slate-700 px-2 text-xs font-semibold text-slate-200 disabled:opacity-60"
        >
          {loading ? <Loader2 size={14} className="animate-spin" aria-hidden /> : <ShieldAlert size={14} aria-hidden />}
          Check CPUs
        </button>
      </div>

      {error ? (
        <div className="mb-3 flex items-start gap-2 rounded border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-xs leading-5 text-amber-100">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden />
          <span>{error}</span>
        </div>
      ) : null}

      {loading ? (
        <div className="grid gap-2">
          {Array.from({ length: 2 }).map((_, index) => (
            <div key={index} className="h-24 animate-pulse rounded border border-slate-800 bg-slate-950" />
          ))}
        </div>
      ) : report?.candidates.length ? (
        <div className="grid gap-2">
          {report.candidates.map((candidate) => (
            <div key={candidate.canonical_cpu_key} className="rounded border border-slate-800 bg-slate-950 px-3 py-2">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-white">{candidate.canonical_cpu_key}</div>
                  <div className="mt-1 text-xs text-slate-500">{candidate.suspected_duplicate_product_ids.length} products affected</div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge text={candidate.confidence} />
                  {candidate.approval_required ? <Badge text="approval required" tone="warning" /> : null}
                </div>
              </div>
              <p className="text-xs leading-5 text-slate-400">{candidate.reason}</p>
              <div className="mt-2 grid gap-1 text-xs text-slate-500">
                {candidate.product_names.slice(0, 3).map((name) => (
                  <span key={name} className="truncate">{name}</span>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs text-slate-500">
                  {candidate.approval_id ? `approval ${candidate.approval_id}` : "approval will be created on preview/check"}
                </span>
                <button
                  type="button"
                  onClick={() => onPreview(candidate.suspected_duplicate_product_ids)}
                  disabled={previewingId === candidate.suspected_duplicate_product_ids.join("|")}
                  className="inline-flex h-8 items-center justify-center gap-2 rounded border border-teal-500/50 px-2 text-xs font-semibold text-teal-200 disabled:opacity-60"
                >
                  {previewingId === candidate.suspected_duplicate_product_ids.join("|") ? (
                    <Loader2 size={13} className="animate-spin" aria-hidden />
                  ) : null}
                  Preview merge
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : report ? (
        <p className="rounded border border-slate-800 bg-slate-950 px-3 py-4 text-sm text-slate-400">
          No CPU duplicate candidates detected for {report.region}.
        </p>
      ) : (
        <p className="rounded border border-slate-800 bg-slate-950 px-3 py-4 text-sm text-slate-400">
          Run a check to inspect existing Saudi CPU products.
        </p>
      )}

      {preview ? (
        <div className="mt-3 rounded border border-slate-800 bg-slate-950 px-3 py-3">
          <h4 className="mb-2 text-sm font-semibold text-white">Read-only merge preview</h4>
          <div className="grid gap-1 text-xs leading-5 text-slate-400">
            <span>Would execute: {preview.would_execute ? "yes" : "no"}</span>
            <span>Price snapshots preserved: {preview.price_snapshots_to_preserve}</span>
            <span>Vendors preserved: {preview.vendors_to_preserve}</span>
            <span>Field evidence preserved: {preview.field_evidence_to_preserve}</span>
            <span>Audit events preserved: {preview.audit_events_to_preserve}</span>
            {preview.approval_id ? <span>Approval: {preview.approval_id}</span> : null}
          </div>
          {preview.risks.length ? (
            <div className="mt-2 grid gap-1 text-xs leading-5 text-amber-200">
              {preview.risks.map((risk) => (
                <span key={risk}>{risk}</span>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function Badge({ text, tone = "neutral" }: { text: string; tone?: "neutral" | "warning" }) {
  const classes =
    tone === "warning"
      ? "border-amber-400/40 bg-amber-400/10 text-amber-100"
      : "border-slate-700 bg-slate-900 text-slate-300";
  return <span className={`rounded border px-2 py-1 text-xs font-semibold capitalize ${classes}`}>{text.replaceAll("_", " ")}</span>;
}
