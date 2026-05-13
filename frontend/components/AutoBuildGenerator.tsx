"use client";

import { Bot, CheckCircle2, Gauge, Loader2, Play, ShieldCheck, Store, TriangleAlert } from "lucide-react";
import type { BuildGenerateResponse, GeneratedBuild, SelectedComponents } from "@/types/builder";

const labelText: Record<GeneratedBuild["label"], string> = {
  best_performance: "Best performance",
  best_value: "Best value",
  balanced: "Balanced",
  closest_valid: "Closest valid"
};

export function AutoBuildGenerator({
  budget,
  response,
  error,
  generating,
  onGenerate,
  onApply
}: {
  budget?: number;
  response: BuildGenerateResponse | null;
  error: string | null;
  generating: boolean;
  onGenerate: () => void;
  onApply: (selection: SelectedComponents) => void;
}) {
  const hasBudget = typeof budget === "number" && budget > 0;
  return (
    <section className="rounded-lg border border-line bg-white p-4 shadow-tight">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.08em] text-signal">
            <Bot size={17} aria-hidden />
            Auto Build Generator
          </div>
          <h2 className="text-lg font-semibold text-ink">SAT-style graph solver</h2>
        </div>
        <button
          type="button"
          onClick={onGenerate}
          disabled={!hasBudget || generating}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-signal px-4 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {generating ? <Loader2 size={17} className="animate-spin" aria-hidden /> : <Play size={17} aria-hidden />}
          Generate
        </button>
      </div>

      {!hasBudget ? (
        <div className="rounded-md border border-caution/40 bg-amber-50 px-3 py-2 text-sm text-caution">
          Enter a budget to let the solver optimize inside a real constraint.
        </div>
      ) : null}

      {error ? (
        <div className="rounded-md border border-danger/30 bg-red-50 px-3 py-2 text-sm text-danger">
          {error}
        </div>
      ) : null}

      {generating ? (
        <div className="grid gap-3 md:grid-cols-3">
          {[0, 1, 2].map((item) => (
            <div key={item} className="h-64 animate-pulse rounded-md border border-line bg-panel" />
          ))}
        </div>
      ) : null}

      {!generating && response ? (
        <div className="grid gap-4">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <StatusPill
              ok={response.compatibility_status === "valid"}
              text={
                response.compatibility_status === "valid"
                  ? "Only valid builds returned"
                  : response.compatibility_status.replaceAll("_", " ")
              }
            />
            <span className="rounded bg-panel px-2 py-1 text-slate-600">
              explored {response.explored_configurations.toLocaleString()}
            </span>
            <span className="rounded bg-panel px-2 py-1 text-slate-600">
              pruned {response.pruned_configurations.toLocaleString()}
            </span>
            <span className="rounded bg-panel px-2 py-1 text-slate-600">
              max depth {response.solver_metrics.max_depth_reached}
            </span>
            <span className="rounded bg-panel px-2 py-1 text-slate-600">
              fetch {response.solver_metrics.graph_fetch_time_ms.toFixed(1)}ms
            </span>
            <span className="rounded bg-panel px-2 py-1 text-slate-600">
              score {response.solver_metrics.scoring_time_ms.toFixed(1)}ms
            </span>
          </div>

          {response.fallback_explanation ? (
            <div className="rounded-md border border-caution/40 bg-amber-50 px-3 py-2 text-sm text-caution">
              {response.fallback_explanation}
            </div>
          ) : null}

          {response.builds.length === 0 ? (
            <div className="rounded-md border border-line bg-panel px-3 py-6 text-sm text-slate-600">
              The graph did not return enough candidates to assemble a complete build.
            </div>
          ) : (
            <div className="grid gap-3 xl:grid-cols-3">
              {response.builds.map((build) => (
                <BuildCard key={`${build.label}-${build.score}`} build={build} onApply={onApply} />
              ))}
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}

function BuildCard({
  build,
  onApply
}: {
  build: GeneratedBuild;
  onApply: (selection: SelectedComponents) => void;
}) {
  return (
    <article className="flex min-h-[420px] flex-col rounded-md border border-line bg-panel p-3">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-ink">{labelText[build.label]}</h3>
          <div className="mt-1 text-sm text-slate-600">${build.total_cost_usd.toFixed(2)}</div>
        </div>
        <ShieldCheck size={19} className="text-signal" aria-label="Valid compatibility" />
      </div>

      <div className="mb-3 grid grid-cols-2 gap-2">
        <Metric label="FPS" value={build.performance.expected_fps.toFixed(1)} />
        <Metric label="1% low" value={build.performance.one_percent_low_fps.toFixed(1)} />
        <Metric label="CPU bottleneck" value={`${build.bottleneck_breakdown.cpu_percent.toFixed(1)}%`} />
        <Metric label="GPU bottleneck" value={`${build.bottleneck_breakdown.gpu_percent.toFixed(1)}%`} />
      </div>

      <div className="mb-3 grid gap-1 rounded border border-line bg-white px-2 py-2 text-[11px] text-slate-600">
        <div>Baseline: {String(build.performance.model_inputs.baseline_version ?? "unknown")}</div>
        <div>Thermal factor: {String(build.performance.model_inputs.thermal_derate_factor ?? "1")}</div>
        <div>Noise mode: {String(build.performance.model_inputs.noise_preference ?? "balanced")}</div>
      </div>

      <div className="grid flex-1 gap-2">
        {build.parts.map((part) => (
          <div key={part.id} className="rounded border border-line bg-white px-2 py-2">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-xs font-semibold uppercase text-slate-500">{part.kind}</div>
                <div className="truncate text-sm font-semibold text-ink" title={part.name}>
                  {part.name}
                </div>
              </div>
              <div className="shrink-0 text-xs font-medium text-slate-600">${part.price_usd.toFixed(0)}</div>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
              <Store size={12} aria-hidden />
              <span>{part.price_vendor ?? part.price_source ?? "catalog price"}</span>
              {typeof part.price_freshness_score === "number" ? (
                <span>{Math.round(part.price_freshness_score * 100)}% fresh</span>
              ) : null}
              {part.price_stale ? <span className="text-caution">stale</span> : null}
            </div>
          </div>
        ))}
      </div>

      <ul className="mt-3 grid gap-1 text-xs leading-5 text-slate-600">
        {build.reasoning_summary.slice(0, 3).map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>

      <ul className="mt-3 grid gap-1 text-xs leading-5 text-slate-600">
        {build.longevity_notes.slice(0, 2).map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>

      <button
        type="button"
        onClick={() => onApply(build.selection)}
        className="mt-3 inline-flex h-9 items-center justify-center rounded-md border border-line bg-white text-sm font-semibold text-ink hover:bg-panel"
      >
        Apply to manual builder
      </button>
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-line bg-white px-2 py-2">
      <div className="mb-1 flex items-center gap-1 text-[11px] font-semibold uppercase text-slate-500">
        <Gauge size={13} aria-hidden />
        {label}
      </div>
      <div className="text-sm font-semibold text-ink">{value}</div>
    </div>
  );
}

function StatusPill({ ok, text }: { ok: boolean; text: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-2 py-1 text-sm font-medium ${
        ok ? "bg-emerald-50 text-signal" : "bg-amber-50 text-caution"
      }`}
    >
      {ok ? <CheckCircle2 size={15} aria-hidden /> : <TriangleAlert size={15} aria-hidden />}
      {text}
    </span>
  );
}
