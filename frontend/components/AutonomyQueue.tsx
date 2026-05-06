"use client";

import { Ban, Clock3, Loader2, PauseCircle, RotateCcw, ShieldAlert } from "lucide-react";
import type { AutonomyJob, AutonomyJobStatus, AutonomyQueue as AutonomyQueueData, OpsSeverity } from "@/types/builder";
import { SeverityBadge } from "@/components/FounderDailyBrief";

type AutonomyQueueProps = {
  queue: AutonomyQueueData | null;
  loading: boolean;
  error: string | null;
  actingJobId: string | null;
  onRetry: () => void;
  onCancel: (jobId: string) => void;
};

export function AutonomyQueue({
  queue,
  loading,
  error,
  actingJobId,
  onRetry,
  onCancel
}: AutonomyQueueProps) {
  if (loading) {
    return (
      <section className="rounded-lg border border-slate-800 bg-slate-950 p-4 text-slate-100">
        <div className="mb-3 h-5 w-36 animate-pulse rounded bg-slate-800" />
        <div className="grid gap-2">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="h-16 animate-pulse rounded-md border border-slate-800 bg-slate-900" />
          ))}
        </div>
      </section>
    );
  }

  const hasJobs = queue && queue.all_jobs.length > 0;

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-4 text-slate-100">
      <Header error={error} onRetry={onRetry} />
      {!hasJobs ? (
        <div className="rounded-md border border-slate-800 bg-slate-900 px-3 py-8 text-sm text-slate-400">
          No autonomy jobs are queued yet. Scheduled safe jobs will appear here after the operations service reports them.
        </div>
      ) : (
        <div className="grid gap-3">
          <QueueGroup title="Running Now" jobs={queue.running_now} empty="No autonomous job is running." onCancel={onCancel} actingJobId={actingJobId} />
          <QueueGroup title="Waiting Approval" jobs={queue.waiting_approval} empty="No job is waiting for founder approval." onCancel={onCancel} actingJobId={actingJobId} />
          <QueueGroup title="Failed / Needs Attention" jobs={queue.failed_needs_attention} empty="No failed job needs attention." onCancel={onCancel} actingJobId={actingJobId} prominent />
          <QueueGroup title="Recently Completed" jobs={queue.recently_completed} empty="No completed job in the current window." onCancel={onCancel} actingJobId={actingJobId} />
          <QueueGroup title="Scheduled Next" jobs={queue.scheduled_next} empty="No scheduled jobs reported." onCancel={onCancel} actingJobId={actingJobId} />
        </div>
      )}
    </section>
  );
}

function Header({ error, onRetry }: { error: string | null; onRetry: () => void }) {
  return (
    <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase text-teal-300">
          <Clock3 size={15} aria-hidden />
          Autonomy Queue
        </div>
        <h2 className="text-lg font-semibold text-white">What the system is doing or planning</h2>
      </div>
      {error ? (
        <button type="button" onClick={onRetry} className="inline-flex h-8 items-center justify-center gap-1 rounded border border-amber-400/50 px-2 text-xs font-semibold text-amber-100">
          <RotateCcw size={13} aria-hidden />
          Retry
        </button>
      ) : null}
    </div>
  );
}

function QueueGroup({
  title,
  jobs,
  empty,
  prominent = false,
  actingJobId,
  onCancel
}: {
  title: string;
  jobs: AutonomyJob[];
  empty: string;
  prominent?: boolean;
  actingJobId: string | null;
  onCancel: (jobId: string) => void;
}) {
  return (
    <div className={`rounded-md border ${prominent ? "border-amber-400/30" : "border-slate-800"} bg-slate-900 p-3`}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        <span className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-400">{jobs.length}</span>
      </div>
      {jobs.length ? (
        <div className="grid gap-2">
          {jobs.slice(0, 8).map((job) => (
            <JobRow key={job.job_id} job={job} acting={actingJobId === job.job_id} onCancel={onCancel} />
          ))}
        </div>
      ) : (
        <p className="text-sm text-slate-500">{empty}</p>
      )}
    </div>
  );
}

function JobRow({ job, acting, onCancel }: { job: AutonomyJob; acting: boolean; onCancel: (jobId: string) => void }) {
  const riskSeverity = riskToSeverity(job.risk_level);
  const canCancel = job.cancellable && !acting && job.risk_level !== "level_3";
  return (
    <div className="grid gap-2 rounded border border-slate-800 bg-slate-950 px-3 py-2 lg:grid-cols-[1fr_auto] lg:items-center">
      <div className="min-w-0">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-semibold text-slate-100">{job.title}</span>
          <StatusBadge status={job.status} />
          <SeverityBadge severity={riskSeverity} compact />
          {job.approval_required ? (
            <span className="inline-flex items-center gap-1 rounded border border-amber-400/40 bg-amber-400/10 px-2 py-0.5 text-xs font-semibold text-amber-200">
              <ShieldAlert size={12} aria-hidden />
              approval
            </span>
          ) : null}
        </div>
        <p className="line-clamp-2 text-xs leading-5 text-slate-400">{job.description || job.summary}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span>{job.agent_name ?? "System"}</span>
          <span>attempt {job.attempts}/{job.max_attempts}</span>
          <span className="max-w-[220px] truncate">trace {job.trace_id}</span>
          {job.last_error ? <span className="text-amber-200">{job.last_error}</span> : null}
        </div>
      </div>
      {job.cancellable ? (
        <button
          type="button"
          onClick={() => onCancel(job.job_id)}
          disabled={!canCancel}
          className="inline-flex h-8 items-center justify-center gap-1 rounded border border-slate-700 px-2 text-xs font-semibold text-slate-200 disabled:cursor-not-allowed disabled:text-slate-600"
          aria-label={`Cancel ${job.title}`}
        >
          {acting ? <Loader2 size={13} className="animate-spin" aria-hidden /> : <Ban size={13} aria-hidden />}
          Cancel
        </button>
      ) : (
        <div className="inline-flex h-8 items-center justify-center gap-1 rounded border border-slate-800 px-2 text-xs text-slate-500">
          <PauseCircle size={13} aria-hidden />
          Bound
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: AutonomyJobStatus }) {
  const classes =
    status === "failed" || status === "blocked"
      ? "border-rose-400/40 bg-rose-400/10 text-rose-200"
      : status === "retrying" || status === "requires_approval"
      ? "border-amber-400/40 bg-amber-400/10 text-amber-200"
      : status === "running"
      ? "border-sky-400/40 bg-sky-400/10 text-sky-200"
      : "border-slate-700 bg-slate-900 text-slate-300";
  return <span className={`rounded border px-2 py-0.5 text-xs font-semibold capitalize ${classes}`}>{status.replaceAll("_", " ")}</span>;
}

function riskToSeverity(risk: AutonomyJob["risk_level"]): OpsSeverity {
  if (risk === "level_3") return "critical";
  if (risk === "level_2") return "warning";
  if (risk === "level_1") return "watch";
  return "info";
}
