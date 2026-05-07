"use client";

import { ClipboardList, KeyRound, RefreshCw, ServerCog } from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import {
  approveRequest,
  cancelAutonomyJob,
  deferRequest,
  getAutonomyQueue,
  getCpuDuplicateCandidates,
  getFounderDailyReport,
  getPendingApprovals,
  markApprovalReviewed,
  previewCanonicalMerge,
  rejectRequest
} from "@/lib/api";
import type { ApprovalItem, AutonomyQueue as AutonomyQueueData, CanonicalMergePreviewResponse, CpuDuplicateReport, DailyFounderReport } from "@/types/builder";
import { ApprovalCenter } from "@/components/ApprovalCenter";
import { AutonomyQueue } from "@/components/AutonomyQueue";
import { FounderDailyBrief } from "@/components/FounderDailyBrief";
import { GraphIntegrityPanel } from "@/components/GraphIntegrityPanel";
import { KnownUrlRefreshPanel } from "@/components/KnownUrlRefreshPanel";
import { ProductUrlImportPanel } from "@/components/ProductUrlImportPanel";
import { useRegion } from "@/components/RegionProvider";

type LoadState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
};

function initialState<T>(): LoadState<T> {
  return { data: null, loading: false, error: null };
}

export function SoloFounderOpsPanel() {
  const { region, regionOption } = useRegion();
  const [apiKey, setApiKey] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [brief, setBrief] = useState<LoadState<DailyFounderReport>>(initialState);
  const [queue, setQueue] = useState<LoadState<AutonomyQueueData>>(initialState);
  const [approvals, setApprovals] = useState<LoadState<ApprovalItem[]>>(initialState);
  const [cpuDuplicates, setCpuDuplicates] = useState<LoadState<CpuDuplicateReport>>(initialState);
  const [mergePreview, setMergePreview] = useState<CanonicalMergePreviewResponse | null>(null);
  const [actingApprovalId, setActingApprovalId] = useState<string | null>(null);
  const [actingJobId, setActingJobId] = useState<string | null>(null);
  const [previewingCpuKey, setPreviewingCpuKey] = useState<string | null>(null);

  const pendingApprovals = useMemo(() => {
    const direct = approvals.data ?? [];
    if (direct.length) return direct;
    return brief.data?.approval_items_waiting ?? [];
  }, [approvals.data, brief.data]);

  async function loadAll() {
    if (!apiKey) return;
    setMessage(null);
    setBrief((current) => ({ ...current, loading: true, error: null }));
    setQueue((current) => ({ ...current, loading: true, error: null }));
    setApprovals((current) => ({ ...current, loading: true, error: null }));
    setCpuDuplicates((current) => ({ ...current, loading: true, error: null }));

    const [briefResult, queueResult, approvalsResult, duplicateResult] = await Promise.allSettled([
      getFounderDailyReport(apiKey, region),
      getAutonomyQueue(apiKey),
      getPendingApprovals(apiKey),
      getCpuDuplicateCandidates(apiKey, region)
    ]);

    setBrief((current) =>
      briefResult.status === "fulfilled"
        ? { data: briefResult.value, loading: false, error: null }
        : { data: current.data, loading: false, error: errorMessage(briefResult.reason, "Unable to load daily brief.") }
    );
    setQueue((current) =>
      queueResult.status === "fulfilled"
        ? { data: queueResult.value, loading: false, error: null }
        : { data: current.data, loading: false, error: errorMessage(queueResult.reason, "Unable to load autonomy queue.") }
    );
    setApprovals((current) =>
      approvalsResult.status === "fulfilled"
        ? { data: approvalsResult.value, loading: false, error: null }
        : { data: current.data, loading: false, error: errorMessage(approvalsResult.reason, "Unable to load approvals.") }
    );
    setCpuDuplicates((current) =>
      duplicateResult.status === "fulfilled"
        ? { data: duplicateResult.value, loading: false, error: null }
        : { data: current.data, loading: false, error: errorMessage(duplicateResult.reason, "Unable to load CPU duplicate candidates.") }
    );
  }

  async function refreshApprovalsAndBrief() {
    const [pending, daily] = await Promise.allSettled([getPendingApprovals(apiKey), getFounderDailyReport(apiKey, region)]);
    if (pending.status === "fulfilled") setApprovals({ data: pending.value, loading: false, error: null });
    if (daily.status === "fulfilled") setBrief({ data: daily.value, loading: false, error: null });
  }

  async function decide(
    approvalId: string,
    action: "approve" | "reject" | "defer" | "review",
    note?: string
  ) {
    setActingApprovalId(approvalId);
    setMessage(null);
    try {
      if (action === "approve") await approveRequest(apiKey, approvalId, note);
      if (action === "reject") await rejectRequest(apiKey, approvalId, note);
      if (action === "defer") await deferRequest(apiKey, approvalId, note);
      if (action === "review") await markApprovalReviewed(apiKey, approvalId, note);
      setMessage(`Approval ${action} recorded with audit trail.`);
      await refreshApprovalsAndBrief();
    } catch (error) {
      setApprovals((current) => ({
        ...current,
        error: errorMessage(error, `Unable to ${action} approval.`)
      }));
    } finally {
      setActingApprovalId(null);
    }
  }

  async function cancelJob(jobId: string) {
    const confirmed = window.confirm("Cancel this bounded autonomy job? This writes an audit event.");
    if (!confirmed) return;
    setActingJobId(jobId);
    try {
      await cancelAutonomyJob(apiKey, jobId);
      setMessage("Autonomy job cancellation recorded.");
      const nextQueue = await getAutonomyQueue(apiKey);
      setQueue({ data: nextQueue, loading: false, error: null });
    } catch (error) {
      setQueue((current) => ({
        ...current,
        error: errorMessage(error, "Unable to cancel autonomy job.")
      }));
    } finally {
      setActingJobId(null);
    }
  }

  async function loadCpuDuplicates() {
    if (!apiKey) return;
    setCpuDuplicates((current) => ({ ...current, loading: true, error: null }));
    try {
      const report = await getCpuDuplicateCandidates(apiKey, region);
      setCpuDuplicates({ data: report, loading: false, error: null });
      await refreshApprovalsAndBrief();
    } catch (error) {
      setCpuDuplicates((current) => ({
        ...current,
        loading: false,
        error: errorMessage(error, "Unable to load CPU duplicate candidates.")
      }));
    }
  }

  async function previewMerge(productIds: string[]) {
    setPreviewingCpuKey(productIds.join("|"));
    setCpuDuplicates((current) => ({ ...current, error: null }));
    try {
      const preview = await previewCanonicalMerge(apiKey, { product_ids: productIds, region });
      setMergePreview(preview);
      await refreshApprovalsAndBrief();
      setMessage("Canonical merge preview created. No product merge was executed.");
    } catch (error) {
      setCpuDuplicates((current) => ({
        ...current,
        error: errorMessage(error, "Unable to preview canonical merge.")
      }));
    } finally {
      setPreviewingCpuKey(null);
    }
  }

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-3 shadow-tight">
      <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase text-teal-300">
            <ServerCog size={16} aria-hidden />
            Solo Founder Operations Command Center
          </div>
          <h2 className="text-xl font-semibold text-white">Autonomy supervision cockpit</h2>
          <p className="mt-1 max-w-2xl text-sm text-slate-400">
            Shows what needs judgment now, what the system handled, and what is safely queued for {regionOption.countryName}.
          </p>
        </div>
        <div className="grid gap-2 sm:grid-cols-[minmax(240px,1fr)_auto]">
          <label className="relative block">
            <span className="sr-only">Admin API key</span>
            <KeyRound size={16} className="pointer-events-none absolute left-3 top-3 text-slate-500" aria-hidden />
            <input
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="Analyst/Admin API key"
              type="password"
              className="h-10 w-full rounded-md border border-slate-700 bg-slate-900 pl-9 pr-3 text-sm text-slate-100 placeholder:text-slate-500"
            />
          </label>
          <button
            type="button"
            onClick={loadAll}
            disabled={!apiKey || brief.loading || queue.loading || approvals.loading}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-teal-600 px-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
          >
            <RefreshCw size={16} className={brief.loading || queue.loading || approvals.loading ? "animate-spin" : ""} aria-hidden />
            Load command center
          </button>
        </div>
      </div>

      {!apiKey ? (
        <div className="rounded-md border border-slate-800 bg-slate-900 px-3 py-8 text-sm text-slate-400">
          Admin operations are hidden until an analyst/admin API key is provided. Keys stay in memory and are never shown back.
        </div>
      ) : (
        <div className="grid gap-3">
          {message ? (
            <div className="flex items-start gap-2 rounded-md border border-teal-400/40 bg-teal-400/10 px-3 py-2 text-sm text-teal-100" aria-live="polite">
              <ClipboardList size={16} className="mt-0.5 shrink-0" aria-hidden />
              <span>{message}</span>
            </div>
          ) : null}

          <FounderDailyBrief report={brief.data} loading={brief.loading} error={brief.error} onRetry={loadAll} />

          <div className="grid gap-3 xl:grid-cols-[0.95fr_1.05fr]">
            <ApprovalCenter
              approvals={pendingApprovals}
              loading={approvals.loading}
              error={approvals.error}
              actingApprovalId={actingApprovalId}
              onApprove={(id, note) => decide(id, "approve", note)}
              onReject={(id, note) => decide(id, "reject", note)}
              onDefer={(id, note) => decide(id, "defer", note)}
              onMarkReviewed={(id, note) => decide(id, "review", note)}
            />
            <AutonomyQueue
              queue={queue.data}
              loading={queue.loading}
              error={queue.error}
              actingJobId={actingJobId}
              onRetry={loadAll}
              onCancel={cancelJob}
            />
          </div>

          <GraphIntegrityPanel
            report={cpuDuplicates.data}
            preview={mergePreview}
            loading={cpuDuplicates.loading}
            previewingId={previewingCpuKey}
            error={cpuDuplicates.error}
            onLoad={loadCpuDuplicates}
            onPreview={previewMerge}
          />

          <div className="grid gap-3">
            <ProductUrlImportPanel apiKey={apiKey} region={region} onIngested={loadAll} />
            <KnownUrlRefreshPanel apiKey={apiKey} region={region} />
          </div>

          <OperationsFooter report={brief.data} />
        </div>
      )}
    </section>
  );
}

function OperationsFooter({ report }: { report: DailyFounderReport | null }) {
  if (!report) return null;
  return (
    <div className="grid gap-3 xl:grid-cols-3">
      <FooterPanel title="Source Health">
        {report.source_health.map((source) => (
          <div key={source.source} className="rounded border border-slate-800 bg-slate-950 px-3 py-2 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-slate-200">{source.source}</span>
              <span className="capitalize text-slate-500">{source.configured ? source.status : "not configured"}</span>
            </div>
            <p className="mt-1 leading-5 text-slate-500">{source.message}</p>
          </div>
        ))}
      </FooterPanel>
      <FooterPanel title="Worker Health">
        {report.workers.map((worker) => (
          <div key={worker.name} className="rounded border border-slate-800 bg-slate-950 px-3 py-2 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-slate-200">{worker.name}</span>
              <span className="capitalize text-slate-500">{worker.status}</span>
            </div>
            <p className="mt-1 leading-5 text-slate-500">{worker.message}</p>
          </div>
        ))}
      </FooterPanel>
      <FooterPanel title="Recent Audit Events">
        {report.recent_audit_events.length ? (
          report.recent_audit_events.slice(0, 5).map((event) => (
            <div key={event.id} className="rounded border border-slate-800 bg-slate-950 px-3 py-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-semibold text-slate-200">{event.action}</span>
                <span className="text-slate-500">{event.status_code ?? "n/a"}</span>
              </div>
              <p className="mt-1 truncate text-slate-500">trace {event.trace_id}</p>
            </div>
          ))
        ) : (
          <p className="text-sm text-slate-500">Audit events appear here after protected operations run.</p>
        )}
      </FooterPanel>
    </div>
  );
}

function FooterPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-3">
      <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">{title}</h3>
      <div className="grid gap-2">{children}</div>
    </div>
  );
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}
