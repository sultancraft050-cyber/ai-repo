"use client";

import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Database,
  KeyRound,
  ListChecks,
  RefreshCw,
  ServerCog,
  ShieldAlert,
  XCircle
} from "lucide-react";
import { approveItem, fetchDailyFounderReport, fetchPendingApprovals, rejectItem } from "@/lib/api";
import type { ApprovalItem, DailyFounderReport, SourceHealth, WorkerHealth } from "@/types/builder";

export function AdminOperationsPanel() {
  const [apiKey, setApiKey] = useState("");
  const [report, setReport] = useState<DailyFounderReport | null>(null);
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [actingId, setActingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const pendingApprovals = useMemo(
    () => approvals.length ? approvals : report?.approval_items_waiting ?? [],
    [approvals, report]
  );

  async function loadOps() {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const [daily, pending] = await Promise.all([
        fetchDailyFounderReport(apiKey),
        fetchPendingApprovals(apiKey).catch(() => [])
      ]);
      setReport(daily);
      setApprovals(pending);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load founder operations.");
    } finally {
      setLoading(false);
    }
  }

  async function decide(approvalId: string, approved: boolean) {
    setActingId(approvalId);
    setError(null);
    setMessage(null);
    try {
      await (approved ? approveItem(apiKey, approvalId, "Approved from solo-founder operations panel.") : rejectItem(apiKey, approvalId, "Rejected from solo-founder operations panel."));
      setMessage(approved ? "Approval item approved." : "Approval item rejected.");
      const pending = await fetchPendingApprovals(apiKey);
      setApprovals(pending);
    } catch (decisionError) {
      setError(decisionError instanceof Error ? decisionError.message : "Unable to update approval item.");
    } finally {
      setActingId(null);
    }
  }

  return (
    <section className="rounded-lg border border-line bg-white p-4 shadow-tight">
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.08em] text-signal">
            <ServerCog size={17} aria-hidden />
            Solo-founder operations
          </div>
          <h2 className="text-lg font-semibold text-ink">Founder Daily Brief</h2>
        </div>
        <div className="grid gap-2 sm:grid-cols-[minmax(220px,1fr)_auto]">
          <label className="relative block">
            <span className="sr-only">Admin API key</span>
            <KeyRound size={16} className="pointer-events-none absolute left-3 top-3 text-slate-400" aria-hidden />
            <input
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="Admin API key"
              type="password"
              className="h-10 w-full rounded-md border border-line bg-white pl-9 pr-3 text-sm text-ink"
            />
          </label>
          <button
            type="button"
            onClick={loadOps}
            disabled={!apiKey || loading}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-signal px-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} aria-hidden />
            Load brief
          </button>
        </div>
      </div>

      {!apiKey ? (
        <div className="mb-3 rounded-md border border-line bg-panel px-3 py-2 text-sm text-slate-600">
          Admin operations are hidden until an analyst/admin API key is provided. Keys stay in memory and are not stored.
        </div>
      ) : null}
      {error ? <div className="mb-3 rounded-md border border-danger/30 bg-red-50 px-3 py-2 text-sm text-danger">{error}</div> : null}
      {message ? <div className="mb-3 rounded-md border border-line bg-panel px-3 py-2 text-sm text-slate-600">{message}</div> : null}

      {loading ? (
        <div className="h-52 animate-pulse rounded-md border border-line bg-panel" />
      ) : report ? (
        <div className="grid gap-3">
          <div className="grid gap-2 md:grid-cols-4">
            <OpsMetric icon={<ShieldAlert size={15} />} label="System" value={report.system_health} tone={report.system_health === "healthy" ? "signal" : "caution"} />
            <OpsMetric icon={<Database size={15} />} label="Neo4j" value={report.neo4j_health.status} tone={report.neo4j_health.neo4j_connected ? "signal" : "danger"} />
            <OpsMetric icon={<ClipboardCheck size={15} />} label="Approvals" value={String(pendingApprovals.length)} tone={pendingApprovals.length ? "caution" : "signal"} />
            <OpsMetric icon={<ListChecks size={15} />} label="Failed jobs" value={String(report.failed_jobs.length)} tone={report.failed_jobs.length ? "caution" : "signal"} />
          </div>

          <div className="grid gap-3 xl:grid-cols-[1.05fr_0.95fr]">
            <Panel title="What Needs Attention Now">
              {report.alerts.length ? (
                <div className="grid gap-2">
                  {report.alerts.slice(0, 5).map((alert) => (
                    <div key={alert.id} className={`rounded border px-3 py-2 text-xs ${severityClasses(alert.severity)}`}>
                      <div className="mb-1 flex items-center justify-between gap-2">
                        <span className="font-semibold">{alert.reason}</span>
                        <span>{alert.severity}</span>
                      </div>
                      <div>{alert.suggested_action}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-slate-600">No founder action is required right now.</div>
              )}
            </Panel>

            <Panel title="Approval Center">
              {pendingApprovals.length ? (
                <div className="grid gap-2">
                  {pendingApprovals.slice(0, 4).map((approval) => (
                    <div key={approval.id} className="rounded border border-caution/30 bg-amber-50 px-3 py-2 text-xs text-caution">
                      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                        <span className="font-semibold">{approval.action_type.replaceAll("_", " ")}</span>
                        <span>{approval.risk_level.replace("_", " ")}</span>
                      </div>
                      <div className="text-slate-700">{approval.reasoning}</div>
                      <div className="mt-2 grid gap-2 sm:grid-cols-2">
                        <button
                          type="button"
                          onClick={() => decide(approval.id, true)}
                          disabled={actingId === approval.id}
                          className="inline-flex h-8 items-center justify-center gap-1 rounded bg-signal px-2 text-xs font-semibold text-white disabled:bg-slate-300"
                        >
                          <CheckCircle2 size={13} aria-hidden />
                          Approve
                        </button>
                        <button
                          type="button"
                          onClick={() => decide(approval.id, false)}
                          disabled={actingId === approval.id}
                          className="inline-flex h-8 items-center justify-center gap-1 rounded border border-line bg-white px-2 text-xs font-semibold text-ink disabled:text-slate-400"
                        >
                          <XCircle size={13} aria-hidden />
                          Reject
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-slate-600">No high-risk action is waiting for approval.</div>
              )}
            </Panel>
          </div>

          <div className="grid gap-3 xl:grid-cols-3">
            <WorkerPanel workers={report.workers} />
            <SourcePanel sources={report.source_health} />
            <Panel title="System Risk Summary">
              <div className="grid gap-2 text-xs text-slate-600">
                {report.recommended_next_actions.slice(0, 5).map((action) => (
                  <div key={action} className="rounded border border-line bg-panel px-3 py-2">
                    {action}
                  </div>
                ))}
              </div>
            </Panel>
          </div>

          <div className="grid gap-3 xl:grid-cols-2">
            <Panel title="Failed Jobs">
              {report.failed_jobs.length ? (
                <div className="grid gap-2">
                  {report.failed_jobs.slice(0, 5).map((job) => (
                    <div key={job.job_id} className="rounded bg-panel px-3 py-2 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-semibold text-ink">{job.job_type}</span>
                        <span className="text-caution">{job.status}</span>
                      </div>
                      <div className="mt-1 text-slate-600">{job.trace_id}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-slate-600">No failed or retrying jobs in the current brief.</div>
              )}
            </Panel>

            <Panel title="Recent Audit Events">
              {report.recent_audit_events.length ? (
                <div className="grid gap-2">
                  {report.recent_audit_events.slice(0, 5).map((event) => (
                    <div key={event.id} className="rounded bg-panel px-3 py-2 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-semibold text-ink">{event.action}</span>
                        <span className="text-slate-500">{event.status_code ?? "n/a"}</span>
                      </div>
                      <div className="mt-1 text-slate-600">{event.trace_id}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-slate-600">Audit events appear after protected operations run.</div>
              )}
            </Panel>
          </div>
        </div>
      ) : (
        <div className="rounded-md border border-line bg-panel px-3 py-8 text-sm text-slate-600">
          Load the daily brief to see health, source status, jobs, approvals, and what the system handled automatically.
        </div>
      )}
    </section>
  );
}

function WorkerPanel({ workers }: { workers: WorkerHealth[] }) {
  return (
    <Panel title="Worker Status">
      <div className="grid gap-2">
        {workers.map((worker) => (
          <div key={worker.name} className="rounded bg-panel px-3 py-2 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-semibold text-ink">{worker.name}</span>
              <span className={worker.running ? "text-signal" : "text-caution"}>{worker.status}</span>
            </div>
            <div className="mt-1 text-slate-600">Queue {worker.queue_depth}; {worker.message}</div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function SourcePanel({ sources }: { sources: SourceHealth[] }) {
  return (
    <Panel title="Source Health">
      <div className="grid gap-2">
        {sources.map((source) => (
          <div key={source.source} className="rounded bg-panel px-3 py-2 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-semibold text-ink">{source.source}</span>
              <span className={source.configured ? "text-signal" : "text-slate-500"}>
                {source.configured ? source.status : "not configured"}
              </span>
            </div>
            <div className="mt-1 text-slate-600">{source.message}</div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded border border-line bg-white px-3 py-3">
      <div className="mb-2 text-xs font-semibold uppercase text-slate-500">{title}</div>
      {children}
    </div>
  );
}

function OpsMetric({
  icon,
  label,
  value,
  tone
}: {
  icon: ReactNode;
  label: string;
  value: string;
  tone: "signal" | "caution" | "danger";
}) {
  const color = tone === "signal" ? "text-signal" : tone === "danger" ? "text-danger" : "text-caution";
  return (
    <div className="rounded-md border border-line bg-panel px-3 py-2">
      <div className={`mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase ${color}`}>
        {icon}
        <span>{label}</span>
      </div>
      <div className="truncate text-sm font-semibold capitalize text-ink">{value.replaceAll("_", " ")}</div>
    </div>
  );
}

function severityClasses(severity: "info" | "warning" | "critical") {
  if (severity === "critical") return "border-danger/30 bg-red-50 text-danger";
  if (severity === "warning") return "border-caution/30 bg-amber-50 text-caution";
  return "border-line bg-panel text-slate-600";
}
