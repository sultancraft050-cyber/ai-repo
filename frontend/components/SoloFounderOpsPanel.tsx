"use client";

import { AlertTriangle, ClipboardList, KeyRound, Link2, RefreshCw, ServerCog, Target, Wrench } from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import {
  approveRequest,
  cancelAutonomyJob,
  deferRequest,
  getAutonomyQueue,
  getCatalogExpansionTargets,
  getCatalogGrowthWorkflow,
  getCpuDuplicateCandidates,
  getDeploymentChecklist,
  getFounderDailyReport,
  getMvpHealthDashboard,
  getPendingApprovals,
  markApprovalReviewed,
  previewCanonicalMerge,
  rejectRequest
} from "@/lib/api";
import type {
  ApprovalItem,
  AutonomyQueue as AutonomyQueueData,
  CanonicalMergePreviewResponse,
  CatalogExpansionCategorySummary,
  CatalogExpansionTargetFamily,
  CatalogExpansionTargetsResponse,
  CatalogGrowthWorkflowSummary,
  CpuDuplicateReport,
  DailyFounderReport,
  DeploymentChecklist,
  MvpHealthDashboard
} from "@/types/builder";
import { ApprovalCenter } from "@/components/ApprovalCenter";
import { AutonomyQueue } from "@/components/AutonomyQueue";
import { CanonicalImportStagingPanel } from "@/components/CanonicalImportStagingPanel";
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
  const [mvpHealth, setMvpHealth] = useState<LoadState<MvpHealthDashboard>>(initialState);
  const [deployment, setDeployment] = useState<LoadState<DeploymentChecklist>>(initialState);
  const [catalogGrowth, setCatalogGrowth] = useState<LoadState<CatalogGrowthWorkflowSummary>>(initialState);
  const [catalogExpansion, setCatalogExpansion] = useState<LoadState<CatalogExpansionTargetsResponse>>(initialState);
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
    setMvpHealth((current) => ({ ...current, loading: true, error: null }));
    setDeployment((current) => ({ ...current, loading: true, error: null }));
    setCatalogGrowth((current) => ({ ...current, loading: true, error: null }));
    setCatalogExpansion((current) => ({ ...current, loading: true, error: null }));

    const [briefResult, queueResult, approvalsResult, duplicateResult, mvpResult, deploymentResult, catalogGrowthResult, catalogExpansionResult] = await Promise.allSettled([
      getFounderDailyReport(apiKey, region),
      getAutonomyQueue(apiKey),
      getPendingApprovals(apiKey),
      getCpuDuplicateCandidates(apiKey, region),
      getMvpHealthDashboard(apiKey, region),
      getDeploymentChecklist(apiKey, region),
      getCatalogGrowthWorkflow(apiKey, region),
      getCatalogExpansionTargets(apiKey, region)
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
    setMvpHealth((current) =>
      mvpResult.status === "fulfilled"
        ? { data: mvpResult.value, loading: false, error: null }
        : { data: current.data, loading: false, error: errorMessage(mvpResult.reason, "Unable to load MVP health.") }
    );
    setDeployment((current) =>
      deploymentResult.status === "fulfilled"
        ? { data: deploymentResult.value, loading: false, error: null }
        : { data: current.data, loading: false, error: errorMessage(deploymentResult.reason, "Unable to load deployment checklist.") }
    );
    setCatalogGrowth((current) =>
      catalogGrowthResult.status === "fulfilled"
        ? { data: catalogGrowthResult.value, loading: false, error: null }
        : { data: current.data, loading: false, error: errorMessage(catalogGrowthResult.reason, "Unable to load catalog growth workflow.") }
    );
    setCatalogExpansion((current) =>
      catalogExpansionResult.status === "fulfilled"
        ? { data: catalogExpansionResult.value, loading: false, error: null }
        : { data: current.data, loading: false, error: errorMessage(catalogExpansionResult.reason, "Unable to load catalog expansion targets.") }
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

          <FounderLaunchFocusPanel
            catalogGrowth={catalogGrowth.data}
            mvpHealth={mvpHealth.data}
            deployment={deployment.data}
            loading={catalogGrowth.loading || mvpHealth.loading || deployment.loading}
          />
          <FounderDailyBrief report={brief.data} loading={brief.loading} error={brief.error} onRetry={loadAll} />
          <DeploymentChecklistPanel data={deployment.data} loading={deployment.loading} error={deployment.error} />
          <MvpHealthPanel data={mvpHealth.data} loading={mvpHealth.loading} error={mvpHealth.error} />
          <CatalogGrowthPanel data={catalogGrowth.data} loading={catalogGrowth.loading} error={catalogGrowth.error} />
          <CatalogNextActionsPanel data={catalogExpansion.data} loading={catalogExpansion.loading} error={catalogExpansion.error} />
          <CatalogExpansionPanel data={catalogExpansion.data} loading={catalogExpansion.loading} error={catalogExpansion.error} />

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
            <CanonicalImportStagingPanel apiKey={apiKey} />
            <ProductUrlImportPanel apiKey={apiKey} region={region} onIngested={loadAll} />
            <KnownUrlRefreshPanel apiKey={apiKey} region={region} />
          </div>

          <OperationsFooter report={brief.data} />
        </div>
      )}
    </section>
  );
}

function FounderLaunchFocusPanel({
  catalogGrowth,
  mvpHealth,
  deployment,
  loading
}: {
  catalogGrowth: CatalogGrowthWorkflowSummary | null;
  mvpHealth: MvpHealthDashboard | null;
  deployment: DeploymentChecklist | null;
  loading: boolean;
}) {
  const topCategory = catalogGrowth?.category_priorities[0];
  const topAction = catalogGrowth?.founder_action_queue[0];
  const topBlockers = catalogGrowth?.top_blockers.slice(0, 3) ?? [];
  const neededUrls = catalogGrowth?.most_needed_urls.slice(0, 4) ?? [];

  return (
    <div className="rounded-lg border border-teal-400/30 bg-teal-400/10 p-3">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold uppercase text-teal-100">Launch Focus</h3>
          <p className="mt-1 text-sm leading-6 text-teal-50/80">
            Start here: biggest blocker, weakest catalog area, needed URLs, stale pricing, and build failures.
          </p>
        </div>
        {loading ? <span className="text-xs text-teal-100/70">Updating launch focus...</span> : null}
      </div>
      {catalogGrowth || mvpHealth || deployment ? (
        <div className="grid gap-3 lg:grid-cols-4">
          <FocusTile
            label="Biggest blocker"
            value={topBlockers[0] ?? deployment?.deployment_blockers[0] ?? "No blocker reported"}
          />
          <FocusTile
            label="Weakest category"
            value={topCategory ? `${topCategory.category}: ${topCategory.readiness_level.replaceAll("_", " ")}` : "No category score yet"}
          />
          <FocusTile
            label="Needed URLs"
            value={neededUrls.length ? neededUrls.join(", ") : topAction?.recommended_products_to_add.join(", ") || "No URL target yet"}
          />
          <FocusTile
            label="Launch health"
            value={`${mvpHealth?.builds_failing ?? 0} failures, ${mvpHealth?.stale_pricing_count ?? 0} stale prices`}
          />
          <div className="rounded border border-teal-300/30 bg-slate-950/50 px-3 py-2 lg:col-span-4">
            <p className="text-xs font-semibold uppercase text-teal-100/70">Recommended founder action</p>
            <p className="mt-1 text-sm leading-6 text-teal-50">
              {topAction?.expected_impact ?? mvpHealth?.founder_insights.action_items[0] ?? "Collect more launch traffic before changing catalog priorities."}
            </p>
          </div>
        </div>
      ) : !loading ? (
        <p className="text-sm text-teal-50/70">Load the command center to see the first founder action list.</p>
      ) : null}
    </div>
  );
}

function FocusTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-teal-300/30 bg-slate-950/50 px-3 py-2">
      <p className="text-xs font-semibold uppercase text-teal-100/70">{label}</p>
      <p className="mt-1 text-sm leading-5 text-teal-50">{value}</p>
    </div>
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

function MvpHealthPanel({ data, loading, error }: { data: MvpHealthDashboard | null; loading: boolean; error: string | null }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase text-slate-300">Public MVP Health</h3>
        {loading ? <span className="text-xs text-slate-500">Loading...</span> : null}
      </div>
      {error ? <p className="rounded border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-sm text-amber-100">{error}</p> : null}
      {data ? (
        <div className="grid gap-3 lg:grid-cols-4">
          <Metric label="Active today" value={data.active_users_today} />
          <Metric label="Builds generated" value={data.builds_generated} />
          <Metric label="Build failures" value={data.builds_failing} />
          <Metric label="SA coverage" value={`${data.saudi_coverage_percent}%`} />
          <div className="lg:col-span-2">
            <p className="mb-2 text-xs font-semibold uppercase text-slate-500">Next founder action</p>
            <p className="rounded border border-slate-800 bg-slate-950 px-3 py-2 text-sm leading-6 text-slate-300">
              {data.founder_insights.action_items[0] ?? "Collect more launch traffic before changing catalog priorities."}
            </p>
          </div>
          <div className="lg:col-span-2">
            <p className="mb-2 text-xs font-semibold uppercase text-slate-500">Top missing categories</p>
            <p className="rounded border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-300">
              {data.top_missing_categories.map((item) => `${item.name} (${item.count})`).join(", ") || "No launch blockers recorded yet."}
            </p>
          </div>
        </div>
      ) : !loading ? (
        <p className="text-sm text-slate-500">Load the command center to see public launch analytics and founder action insights.</p>
      ) : null}
    </div>
  );
}

function CatalogGrowthPanel({ data, loading, error }: { data: CatalogGrowthWorkflowSummary | null; loading: boolean; error: string | null }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase text-slate-300">Saudi Catalog Growth Workflow</h3>
        {loading ? <span className="text-xs text-slate-500">Scoring...</span> : null}
      </div>
      {error ? <p className="rounded border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-sm text-amber-100">{error}</p> : null}
      {data ? (
        <div className="grid gap-3">
          <p className="rounded border border-slate-800 bg-slate-950 px-3 py-2 text-sm leading-6 text-slate-300">{data.message}</p>
          <div className="grid gap-3 xl:grid-cols-[1.1fr_0.9fr]">
            <div className="overflow-hidden rounded border border-slate-800">
              <table className="w-full min-w-[560px] text-left text-xs">
                <thead className="bg-slate-950 text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Category</th>
                    <th className="px-3 py-2">Score</th>
                    <th className="px-3 py-2">Readiness</th>
                    <th className="px-3 py-2">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {data.category_priorities.slice(0, 8).map((item) => (
                    <tr key={item.category} className="border-t border-slate-800">
                      <td className="px-3 py-2 font-semibold text-slate-200">{item.category}</td>
                      <td className="px-3 py-2 text-slate-300">{Math.round(item.score)}</td>
                      <td className="px-3 py-2 text-slate-400">{item.readiness_level.replaceAll("_", " ")}</td>
                      <td className="px-3 py-2 leading-5 text-slate-400">{item.recommended_next_action}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="grid gap-2">
              <p className="text-xs font-semibold uppercase text-slate-500">Founder Action Queue</p>
              {data.founder_action_queue.slice(0, 4).map((item) => (
                <div key={item.category} className="rounded border border-slate-800 bg-slate-950 px-3 py-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-slate-200">{item.category}</span>
                    <span className="text-xs text-slate-500">{item.estimated_improvement}</span>
                  </div>
                  <p className="mt-1 leading-5 text-slate-400">{item.expected_impact}</p>
                  <p className="mt-1 text-xs text-slate-500">{item.recommended_products_to_add.join(", ")}</p>
                </div>
              ))}
            </div>
          </div>
          <div className="grid gap-3 xl:grid-cols-3">
            <FooterPanel title="Most Needed URLs">
              <p className="text-sm leading-6 text-slate-400">{data.most_needed_urls.join(", ") || "No URL target is obvious yet."}</p>
            </FooterPanel>
            <FooterPanel title="Weak Stores">
              <p className="text-sm leading-6 text-slate-400">
                {data.store_quality_scores
                  .filter((store) => store.weaknesses.length)
                  .slice(0, 4)
                  .map((store) => `${store.store_name} (${Math.round(store.score)})`)
                  .join(", ") || "No weak store signal yet."}
              </p>
            </FooterPanel>
            <FooterPanel title="Trend Snapshot">
              <p className="text-sm leading-6 text-slate-400">
                {data.readiness_trends[0]
                  ? `Success ${Math.round(data.readiness_trends[0].build_success_rate * 100)}%, readiness ${Math.round(data.readiness_trends[0].readiness_score * 100)}%, warnings ${data.readiness_trends[0].warning_frequency}.`
                  : "No trend data yet."}
              </p>
            </FooterPanel>
          </div>
        </div>
      ) : !loading ? (
        <p className="text-sm text-slate-500">Load the command center to see category priorities, URL targets, store quality, and readiness trends.</p>
      ) : null}
    </div>
  );
}

type CatalogActionKind = "url" | "specs" | "conflict" | "coverage";
type CatalogAction = {
  key: string;
  kind: CatalogActionKind;
  category: string;
  title: string;
  detail: string;
  metric: string;
  priority: number;
};

function CatalogNextActionsPanel({ data, loading, error }: { data: CatalogExpansionTargetsResponse | null; loading: boolean; error: string | null }) {
  const actions = useMemo(() => buildCatalogActions(data), [data]);
  const iconByKind: Record<CatalogActionKind, ReactNode> = {
    url: <Link2 size={16} aria-hidden />,
    specs: <Wrench size={16} aria-hidden />,
    conflict: <AlertTriangle size={16} aria-hidden />,
    coverage: <Target size={16} aria-hidden />
  };
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold uppercase text-slate-300">Next Catalog Actions</h3>
          <p className="mt-1 text-xs text-slate-500">Founder-only queue for Core 500 growth, specs, prices, and review blockers.</p>
        </div>
        {loading ? <span className="text-xs text-slate-500">Checking...</span> : null}
      </div>
      {error ? <p className="rounded border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-sm text-amber-100">{error}</p> : null}
      {data ? (
        <div className="grid gap-3 lg:grid-cols-4">
          {actions.length ? (
            actions.slice(0, 8).map((action) => (
              <div key={action.key} className="rounded border border-slate-800 bg-slate-950 px-3 py-3">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <span className={`grid h-8 w-8 place-items-center rounded-md ${catalogActionTone(action.kind)}`}>{iconByKind[action.kind]}</span>
                  <span className="text-xs font-semibold uppercase text-slate-500">{action.category}</span>
                </div>
                <p className="text-sm font-semibold text-white">{action.title}</p>
                <p className="mt-1 text-xs leading-5 text-slate-400">{action.detail}</p>
                <p className="mt-2 text-xs font-semibold text-teal-200">{action.metric}</p>
              </div>
            ))
          ) : (
            <div className="rounded border border-teal-400/30 bg-teal-400/10 px-3 py-3 text-sm text-teal-100 lg:col-span-4">
              No immediate catalog blockers found in the loaded target manifest.
            </div>
          )}
        </div>
      ) : !loading ? (
        <p className="text-sm text-slate-500">Load the command center to see products needing Saudi URLs, exact specs, metadata enrichment, and conflict review.</p>
      ) : null}
    </div>
  );
}

function CatalogExpansionPanel({ data, loading, error }: { data: CatalogExpansionTargetsResponse | null; loading: boolean; error: string | null }) {
  const categories = data?.categories ?? [];
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase text-slate-300">Phase 2 Catalog Expansion</h3>
        {loading ? <span className="text-xs text-slate-500">Reading targets...</span> : null}
      </div>
      {error ? <p className="rounded border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-sm text-amber-100">{error}</p> : null}
      {data ? (
        <div className="grid gap-3">
          <div className="grid gap-3 md:grid-cols-4">
            <Metric label="Canonical" value={data.total_canonical_count} />
            <Metric label="Ready" value={data.total_compatibility_ready_count} />
            <Metric label="Saudi priced" value={data.total_saudi_priced_count} />
            <Metric label="Trusted vendors" value={data.total_trusted_vendor_count} />
          </div>
          <div className="overflow-hidden rounded border border-slate-800">
            <table className="w-full min-w-[720px] text-left text-xs">
              <thead className="bg-slate-950 text-slate-500">
                <tr>
                  <th className="px-3 py-2">Priority</th>
                  <th className="px-3 py-2">Category</th>
                  <th className="px-3 py-2">Canonical</th>
                  <th className="px-3 py-2">Ready</th>
                  <th className="px-3 py-2">Saudi priced</th>
                  <th className="px-3 py-2">State</th>
                  <th className="px-3 py-2">Next action</th>
                </tr>
              </thead>
              <tbody>
                {categories.map((item) => (
                  <tr key={item.category} className="border-t border-slate-800">
                    <td className="px-3 py-2 text-slate-500">{item.priority_order}</td>
                    <td className="px-3 py-2 font-semibold text-slate-200">{item.category}</td>
                    <td className="px-3 py-2 text-slate-300">
                      {item.canonical_count}/{item.target_min}
                    </td>
                    <td className="px-3 py-2 text-slate-300">{item.compatibility_ready_count}</td>
                    <td className="px-3 py-2 text-slate-300">{item.saudi_priced_count}</td>
                    <td className="px-3 py-2 text-slate-400">{item.readiness_state.replaceAll("_", " ")}</td>
                    <td className="px-3 py-2 leading-5 text-slate-400">{item.next_action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="grid gap-3 lg:grid-cols-3">
            {categories.slice(0, 3).map((category) => (
              <FooterPanel key={category.category} title={`${category.category} target families`}>
                <p className="text-sm leading-6 text-slate-400">
                  {category.families
                    .filter((family) => family.conflict_count || family.metadata_only_count || family.saudi_priced_count === 0)
                    .slice(0, 5)
                    .map((family) => `${family.family_name}: ${family.next_action}`)
                    .join(" ")}
                </p>
              </FooterPanel>
            ))}
          </div>
        </div>
      ) : !loading ? (
        <p className="text-sm text-slate-500">Load the command center to see target family coverage, metadata-only rows, conflicts, and Saudi pricing gaps.</p>
      ) : null}
    </div>
  );
}

function DeploymentChecklistPanel({ data, loading, error }: { data: DeploymentChecklist | null; loading: boolean; error: string | null }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase text-slate-300">Deployment Checklist</h3>
        {loading ? <span className="text-xs text-slate-500">Checking...</span> : null}
      </div>
      {error ? <p className="rounded border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-sm text-amber-100">{error}</p> : null}
      {data ? (
        <div className="grid gap-3 lg:grid-cols-[0.6fr_1.4fr]">
          <div className={`rounded border px-3 py-2 ${data.launch_ready ? "border-teal-400/30 bg-teal-400/10" : "border-amber-400/40 bg-amber-400/10"}`}>
            <p className="text-xs uppercase text-slate-400">Launch status</p>
            <p className="mt-1 text-lg font-semibold text-white">{data.launch_ready ? "Ready" : "Blocked"}</p>
            <p className="mt-1 text-xs text-slate-400">
              {data.environment} / {data.market_data_mode} / backend {data.version_info.backend_version ?? "unknown"}
            </p>
          </div>
          <div className="rounded border border-slate-800 bg-slate-950 px-3 py-2">
            <p className="mb-2 text-xs font-semibold uppercase text-slate-500">Blockers</p>
            <p className="text-sm leading-6 text-slate-300">
              {data.deployment_blockers.length ? data.deployment_blockers.join(" ") : "No deployment blockers reported by backend checks."}
            </p>
          </div>
        </div>
      ) : !loading ? (
        <p className="text-sm text-slate-500">Load the command center to verify env, Neo4j, source policy, readiness, and runtime health.</p>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-950 px-3 py-2">
      <p className="text-xs uppercase text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-white">{value}</p>
    </div>
  );
}

function buildCatalogActions(data: CatalogExpansionTargetsResponse | null): CatalogAction[] {
  if (!data) return [];
  const actions: CatalogAction[] = [];
  data.categories.forEach((category) => {
    if (category.conflict_count > 0) actions.push(categoryAction(category, "conflict"));
    if (category.canonical_count < category.target_min) actions.push(categoryAction(category, "coverage"));
    category.families.forEach((family) => {
      if (family.conflict_count > 0) actions.push(familyAction(family, "conflict"));
      if (family.metadata_only_count > 0 || family.missing_required_specs.length > 0) actions.push(familyAction(family, "specs"));
      if (family.compatibility_ready_count > 0 && family.saudi_priced_count === 0) actions.push(familyAction(family, "url"));
    });
  });
  return actions.sort((left, right) => left.priority - right.priority || left.category.localeCompare(right.category)).slice(0, 12);
}

function categoryAction(category: CatalogExpansionCategorySummary, kind: Extract<CatalogActionKind, "conflict" | "coverage">): CatalogAction {
  if (kind === "conflict") {
    return {
      key: `${category.category}-category-conflict`,
      kind,
      category: category.category,
      title: "Review category conflicts",
      detail: "Resolve blocked canonical rows before committing more products in this category.",
      metric: `${category.conflict_count} conflict${category.conflict_count === 1 ? "" : "s"}`,
      priority: 10 + category.priority_order
    };
  }
  return {
    key: `${category.category}-category-coverage`,
    kind,
    category: category.category,
    title: "Grow target coverage",
    detail: category.next_action,
    metric: `${category.canonical_count}/${category.target_min} minimum canonical products`,
    priority: 60 + category.priority_order
  };
}

function familyAction(family: CatalogExpansionTargetFamily, kind: Exclude<CatalogActionKind, "coverage">): CatalogAction {
  if (kind === "conflict") {
    return {
      key: `${family.family_key}-conflict`,
      kind,
      category: family.category,
      title: `${family.family_name}: review conflicts`,
      detail: "Keep records blocked until founder review decides the safe merge path.",
      metric: `${family.conflict_count} conflict${family.conflict_count === 1 ? "" : "s"}`,
      priority: 1 + family.priority
    };
  }
  if (kind === "specs") {
    const missing = family.missing_required_specs.length ? family.missing_required_specs.slice(0, 3).join(", ") : "required specs";
    return {
      key: `${family.family_key}-specs`,
      kind,
      category: family.category,
      title: `${family.family_name}: confirm specs`,
      detail: family.next_action || `Add source-attributed evidence for ${missing}.`,
      metric: `${family.metadata_only_count} metadata-only row${family.metadata_only_count === 1 ? "" : "s"}`,
      priority: 20 + family.priority
    };
  }
  return {
    key: `${family.family_key}-url`,
    kind,
    category: family.category,
    title: `${family.family_name}: add Saudi URL`,
    detail: "Add an exact approved product URL through preview and ingest when the founder is ready.",
    metric: `${family.compatibility_ready_count} ready, 0 Saudi priced`,
    priority: 40 + family.priority
  };
}

function catalogActionTone(kind: CatalogActionKind) {
  if (kind === "conflict") return "bg-amber-300/15 text-amber-100";
  if (kind === "url") return "bg-teal-300/15 text-teal-100";
  if (kind === "specs") return "bg-sky-300/15 text-sky-100";
  return "bg-slate-700 text-slate-200";
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
