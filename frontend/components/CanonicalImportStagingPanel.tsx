"use client";

import { DatabaseZap, Eraser, FileCheck2, RefreshCw } from "lucide-react";
import { useState } from "react";
import { clearStagedCanonicalRecords, getStagedCanonicalSummary, stageCanonicalDataset } from "@/lib/api";
import type {
  CanonicalImportSourceType,
  CanonicalImportStageResponse,
  CanonicalStagedSummaryResponse,
  ProductCategory
} from "@/types/builder";
import { productCategories } from "@/types/builder";

type Props = {
  apiKey: string;
};

const sourceOptions: { name: string; type: CanonicalImportSourceType; label: string }[] = [
  { name: "BuildCores/OpenDB", type: "canonical_specs", label: "BuildCores/OpenDB specs" },
  { name: "Kaggle PC Parts Dataset", type: "kaggle_dataset", label: "Kaggle PC parts dataset" },
  { name: "Community Hardware Repository", type: "community_repository", label: "Community hardware repository" }
];

export function CanonicalImportStagingPanel({ apiKey }: Props) {
  const [sourceIndex, setSourceIndex] = useState(0);
  const [category, setCategory] = useState<ProductCategory>("CPU");
  const [datasetPath, setDatasetPath] = useState("samples/cpu_sample.json");
  const [licenseNote, setLicenseNote] = useState("Founder-approved local dataset usage note.");
  const [batchLimit, setBatchLimit] = useState(100);
  const [dryRun, setDryRun] = useState(true);
  const [loading, setLoading] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [stageResult, setStageResult] = useState<CanonicalImportStageResponse | null>(null);
  const [summary, setSummary] = useState<CanonicalStagedSummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const source = sourceOptions[sourceIndex] ?? sourceOptions[0];

  async function runStage() {
    setLoading(true);
    setError(null);
    try {
      const result = await stageCanonicalDataset(apiKey, {
        source_name: source.name,
        source_type: source.type,
        dataset_path: datasetPath,
        category,
        batch_limit: batchLimit,
        license_note: licenseNote,
        dry_run: dryRun
      });
      setStageResult(result);
      const nextSummary = await getStagedCanonicalSummary(apiKey, { source_name: source.name, category });
      setSummary(nextSummary);
    } catch (stageError) {
      setError(stageError instanceof Error ? stageError.message : "Unable to stage canonical dataset.");
    } finally {
      setLoading(false);
    }
  }

  async function refreshSummary() {
    setLoading(true);
    setError(null);
    try {
      setSummary(await getStagedCanonicalSummary(apiKey, { source_name: source.name, category }));
    } catch (summaryError) {
      setError(summaryError instanceof Error ? summaryError.message : "Unable to load staged summary.");
    } finally {
      setLoading(false);
    }
  }

  async function clearStaged() {
    const confirmed = window.confirm(`Clear staged ${category} records for ${source.name}?`);
    if (!confirmed) return;
    setClearing(true);
    setError(null);
    try {
      const result = await clearStagedCanonicalRecords(apiKey, { source_name: source.name, category });
      setStageResult(null);
      setSummary({
        source_name: result.source_name,
        source_type: source.type,
        category: result.category,
        staged_count: 0,
        valid_count: 0,
        invalid_count: 0,
        duplicate_candidate_count: 0,
        conflict_candidate_count: 0,
        categories: [],
        readiness_for_commit: "not_ready"
      });
    } catch (clearError) {
      setError(clearError instanceof Error ? clearError.message : "Unable to clear staged records.");
    } finally {
      setClearing(false);
    }
  }

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase text-teal-300">
            <DatabaseZap size={15} aria-hidden />
            Canonical dataset staging
          </div>
          <h3 className="text-base font-semibold text-white">Stage local specs before canonical commit</h3>
          <p className="mt-1 text-sm leading-6 text-slate-400">
            Reads files only from <span className="font-mono text-slate-200">data/imports</span>, validates quality,
            and prepares clean records for the existing commit gate.
          </p>
        </div>
        <button
          type="button"
          onClick={refreshSummary}
          disabled={loading}
          className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 text-sm font-semibold text-slate-100 hover:border-teal-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} aria-hidden />
          Refresh summary
        </button>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-slate-300">Source</span>
          <select
            value={sourceIndex}
            onChange={(event) => setSourceIndex(Number(event.target.value))}
            className="h-10 rounded-md border border-slate-700 bg-slate-900 px-3 text-slate-100"
          >
            {sourceOptions.map((option, index) => (
              <option key={`${option.name}-${option.type}`} value={index}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-slate-300">Category</span>
          <select
            value={category}
            onChange={(event) => {
              const nextCategory = event.target.value as ProductCategory;
              setCategory(nextCategory);
              if (nextCategory === "Motherboard" && batchLimit > 50) setBatchLimit(50);
            }}
            className="h-10 rounded-md border border-slate-700 bg-slate-900 px-3 text-slate-100"
          >
            {productCategories.slice(0, 8).map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-slate-300">Batch limit</span>
          <input
            type="number"
            min={1}
            max={category === "Motherboard" ? 50 : 100}
            value={batchLimit}
            onChange={(event) => setBatchLimit(Number(event.target.value))}
            className="h-10 rounded-md border border-slate-700 bg-slate-900 px-3 text-slate-100"
          />
        </label>
        <label className="grid gap-1 text-sm lg:col-span-2">
          <span className="font-medium text-slate-300">Dataset path under data/imports</span>
          <input
            value={datasetPath}
            onChange={(event) => setDatasetPath(event.target.value)}
            placeholder="samples/cpu_sample.json"
            className="h-10 rounded-md border border-slate-700 bg-slate-900 px-3 font-mono text-sm text-slate-100 placeholder:text-slate-500"
          />
        </label>
        <label className="flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200">
          <input
            type="checkbox"
            checked={dryRun}
            onChange={(event) => setDryRun(event.target.checked)}
            className="h-4 w-4 accent-teal-400"
          />
          Dry run only
        </label>
        <label className="grid gap-1 text-sm lg:col-span-3">
          <span className="font-medium text-slate-300">License or usage note</span>
          <textarea
            value={licenseNote}
            onChange={(event) => setLicenseNote(event.target.value)}
            rows={2}
            className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 placeholder:text-slate-500"
          />
        </label>
      </div>

      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <button
          type="button"
          onClick={runStage}
          disabled={loading || !datasetPath || !licenseNote}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-teal-500 px-4 text-sm font-semibold text-slate-950 hover:bg-teal-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
        >
          <FileCheck2 size={16} aria-hidden />
          {dryRun ? "Dry-run stage" : "Stage records"}
        </button>
        <button
          type="button"
          onClick={clearStaged}
          disabled={clearing}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-4 text-sm font-semibold text-slate-100 hover:border-rose-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Eraser size={16} aria-hidden />
          Clear staged records
        </button>
      </div>

      {error ? (
        <div className="mt-3 rounded-md border border-rose-400/40 bg-rose-400/10 px-3 py-2 text-sm text-rose-100" role="alert">
          {error}
        </div>
      ) : null}

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <StageResultCard result={stageResult} />
        <SummaryCard summary={summary} />
      </div>
    </section>
  );
}

function StageResultCard({ result }: { result: CanonicalImportStageResponse | null }) {
  if (!result) {
    return (
      <div className="rounded-md border border-slate-800 bg-slate-900 px-3 py-4 text-sm text-slate-400">
        No staging run yet. Use dry run first, then uncheck dry run when the report looks clean.
      </div>
    );
  }
  return (
    <div className="rounded-md border border-slate-800 bg-slate-900 p-3">
      <h4 className="text-sm font-semibold text-slate-100">Latest staging report</h4>
      <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <Metric label="Seen" value={result.total_records_seen} />
        <Metric label="Staged" value={result.staged_records} />
        <Metric label="Rejected" value={result.rejected_records} />
        <Metric label="Conflicts" value={result.conflict_candidates} />
      </div>
      <p className="mt-3 rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-300">
        {result.recommended_next_action}
      </p>
      <ReasonList title="Top rejection reasons" items={result.top_rejection_reasons} />
      <ReasonList title="Top warnings" items={result.top_warning_reasons} />
    </div>
  );
}

function SummaryCard({ summary }: { summary: CanonicalStagedSummaryResponse | null }) {
  if (!summary) {
    return (
      <div className="rounded-md border border-slate-800 bg-slate-900 px-3 py-4 text-sm text-slate-400">
        Summary appears after staging or refresh.
      </div>
    );
  }
  return (
    <div className="rounded-md border border-slate-800 bg-slate-900 p-3">
      <h4 className="text-sm font-semibold text-slate-100">Staged records summary</h4>
      <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <Metric label="Total" value={summary.staged_count} />
        <Metric label="Commit-ready" value={summary.valid_count} />
        <Metric label="Invalid" value={summary.invalid_count} />
        <Metric label="Duplicate risk" value={summary.duplicate_candidate_count} />
      </div>
      <div className="mt-3 rounded border border-slate-700 bg-slate-950 px-3 py-2">
        <p className="text-xs font-semibold uppercase text-slate-500">Readiness</p>
        <p className="mt-1 text-sm font-semibold text-teal-200">{summary.readiness_for_commit.replaceAll("_", " ")}</p>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-950 px-3 py-2">
      <p className="text-xs font-semibold uppercase text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-white">{value}</p>
    </div>
  );
}

function ReasonList({ title, items }: { title: string; items: { reason: string; count: number }[] }) {
  if (!items.length) return null;
  return (
    <div className="mt-3">
      <p className="text-xs font-semibold uppercase text-slate-500">{title}</p>
      <ul className="mt-2 space-y-1 text-sm text-slate-300">
        {items.map((item) => (
          <li key={item.reason} className="flex justify-between gap-3 rounded border border-slate-800 bg-slate-950 px-2 py-1">
            <span>{item.reason}</span>
            <span className="font-semibold text-slate-100">{item.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
