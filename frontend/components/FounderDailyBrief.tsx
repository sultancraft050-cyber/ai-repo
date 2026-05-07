"use client";

import { Activity, AlertTriangle, CheckCircle2, Database, RadioTower, ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";
import type { DailyFounderReport, OpsSeverity, RecommendedAction } from "@/types/builder";

type FounderDailyBriefProps = {
  report: DailyFounderReport | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
};

export function FounderDailyBrief({ report, loading, error, onRetry }: FounderDailyBriefProps) {
  if (loading) {
    return (
      <section className="rounded-lg border border-slate-800 bg-slate-950 p-4 text-slate-100">
        <div className="mb-4 h-5 w-44 animate-pulse rounded bg-slate-800" />
        <div className="grid gap-3 md:grid-cols-5">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="h-24 animate-pulse rounded-md border border-slate-800 bg-slate-900" />
          ))}
        </div>
        <div className="mt-3 h-28 animate-pulse rounded-md border border-slate-800 bg-slate-900" />
      </section>
    );
  }

  if (!report) {
    return (
      <section className="rounded-lg border border-slate-800 bg-slate-950 p-4 text-slate-100">
        <PanelHeader title="Founder Daily Brief" subtitle="No daily operations data yet. Run autonomy cycle or wait for scheduled jobs." />
        {error ? <InlineError message={error} onRetry={onRetry} /> : null}
      </section>
    );
  }

  const attention = report.needs_attention.length ? report.needs_attention : report.alerts;
  const primaryAction = report.recommended_next_actions[0];

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-4 text-slate-100 shadow-tight">
      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <PanelHeader
          title="Founder Daily Brief"
          subtitle={`Generated ${formatDate(report.generated_at)}; system is ${report.system_health.replaceAll("_", " ")}.`}
        />
        <SeverityBadge severity={report.system_summary.severity} />
      </div>

      {error ? <InlineError message={error} onRetry={onRetry} /> : null}

      <div className="grid gap-3 md:grid-cols-5">
        <MetricCard icon={<Activity size={16} />} label="Backend" value={report.system_summary.backend_status} severity={report.system_summary.severity} />
        <MetricCard icon={<Database size={16} />} label="Neo4j" value={report.neo4j_health.status} severity={report.neo4j_health.neo4j_connected ? "info" : "critical"} />
        <MetricCard icon={<CheckCircle2 size={16} />} label="Autonomy" value={`${report.autonomy_summary.completed_jobs} done`} detail={`${report.autonomy_summary.failed_jobs} failed`} severity={report.autonomy_summary.failed_jobs ? "warning" : "info"} />
        <MetricCard icon={<RadioTower size={16} />} label="Sources" value={`${report.source_summary.configured_sources} configured`} detail={`${report.source_summary.missing_api_keys.length} missing`} severity={report.source_summary.degraded_sources.length ? "warning" : "watch"} />
        <MetricCard icon={<ShieldAlert size={16} />} label="Approvals" value={`${report.autonomy_summary.pending_approvals} pending`} severity={report.autonomy_summary.pending_approvals ? "warning" : "info"} />
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-md border border-slate-800 bg-slate-900 p-3">
          <h3 className="mb-2 text-sm font-semibold text-white">Needs Your Attention</h3>
          {attention.length ? (
            <div className="grid gap-2">
              {attention.slice(0, 5).map((alert) => (
                <div key={alert.id} className="rounded border border-slate-800 bg-slate-950 px-3 py-2">
                  <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-slate-100">{alert.reason}</span>
                    <SeverityBadge severity={alert.severity} compact />
                  </div>
                  <p className="text-xs leading-5 text-slate-400">{alert.suggested_action}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400">No founder action is required right now.</p>
          )}
        </div>

        <div className="grid gap-3">
          <div className="rounded-md border border-slate-800 bg-slate-900 p-3">
            <h3 className="mb-2 text-sm font-semibold text-white">Handled Automatically</h3>
            <div className="grid gap-2">
              {report.handled_automatically.slice(0, 4).map((item) => (
                <div key={item} className="rounded border border-slate-800 bg-slate-950 px-3 py-2 text-xs leading-5 text-slate-300">
                  {item}
                </div>
              ))}
            </div>
          </div>
          <RecommendedActionCard action={primaryAction} />
        </div>
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <SummaryBlock title="Data" items={[
          `${report.data_summary.new_products_discovered} new products`,
          `${report.data_summary.price_snapshots_updated} pricing refreshes`,
          `${report.data_summary.telemetry_gaps_detected} telemetry gaps`,
          `${report.data_summary.saudi_listings_with_recommended_option} Saudi products with buy options`,
          `${report.data_summary.saudi_risky_only_products} Saudi products risky-only`,
          `${Math.round(report.data_summary.saudi_build_readiness_score * 100)}% Saudi build readiness`,
          `${report.data_summary.saudi_build_missing_categories.length} build categories missing`
        ]} />
        <SummaryBlock title="Cognition" items={[
          `${report.cognition_summary.governance_risks} governance risks`,
          `${report.cognition_summary.alignment_warnings} alignment warnings`,
          `${report.cognition_summary.anomaly_spikes} anomaly spikes`
        ]} />
        <SummaryBlock title="Sources" items={[
          `${report.source_summary.missing_api_keys.length} missing API keys`,
          `${report.source_summary.degraded_sources.length} degraded sources`,
          `${report.source_summary.quota_warnings.length} quota warnings`
        ]} />
      </div>
    </section>
  );
}

function PanelHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div>
      <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase text-teal-300">
        <Activity size={15} aria-hidden />
        Solo-founder command center
      </div>
      <h2 className="text-lg font-semibold text-white">{title}</h2>
      <p className="mt-1 text-sm text-slate-400">{subtitle}</p>
    </div>
  );
}

function MetricCard({
  icon,
  label,
  value,
  detail,
  severity
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail?: string;
  severity: OpsSeverity;
}) {
  return (
    <div className="min-h-24 rounded-md border border-slate-800 bg-slate-900 px-3 py-3">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-slate-400">
        {icon}
        <span>{label}</span>
      </div>
      <div className="truncate text-sm font-semibold capitalize text-white">{value.replaceAll("_", " ")}</div>
      <div className="mt-2 flex items-center justify-between gap-2">
        {detail ? <span className="truncate text-xs text-slate-500">{detail}</span> : <span />}
        <SeverityDot severity={severity} />
      </div>
    </div>
  );
}

function RecommendedActionCard({ action }: { action?: RecommendedAction }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-900 p-3">
      <h3 className="mb-2 text-sm font-semibold text-white">Recommended Next Action</h3>
      {action ? (
        <div className="rounded border border-slate-800 bg-slate-950 px-3 py-2">
          <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-semibold text-slate-100">{action.reason}</span>
            <SeverityBadge severity={action.severity} compact />
          </div>
          <p className="text-xs leading-5 text-slate-400">{action.suggested_action}</p>
        </div>
      ) : (
        <p className="text-sm text-slate-400">No next action is recommended right now.</p>
      )}
    </div>
  );
}

function SummaryBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-900 p-3">
      <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">{title}</h3>
      <div className="grid gap-1 text-xs text-slate-300">
        {items.map((item) => (
          <div key={item} className="truncate">{item}</div>
        ))}
      </div>
    </div>
  );
}

function InlineError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="mb-3 flex flex-col gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-2">
        <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden />
        <span>{message}</span>
      </div>
      <button type="button" onClick={onRetry} className="rounded border border-amber-400/50 px-2 py-1 text-xs font-semibold text-amber-100">
        Retry
      </button>
    </div>
  );
}

export function SeverityBadge({ severity, compact = false }: { severity: OpsSeverity; compact?: boolean }) {
  const classes = severityClass(severity);
  return (
    <span className={`inline-flex items-center rounded border px-2 py-1 text-xs font-semibold capitalize ${classes} ${compact ? "py-0.5" : ""}`}>
      {severity}
    </span>
  );
}

function SeverityDot({ severity }: { severity: OpsSeverity }) {
  return <span className={`h-2 w-2 rounded-full ${dotClass(severity)}`} aria-label={`${severity} severity`} />;
}

function severityClass(severity: OpsSeverity) {
  if (severity === "critical") return "border-rose-400/40 bg-rose-400/10 text-rose-200";
  if (severity === "warning") return "border-amber-400/40 bg-amber-400/10 text-amber-200";
  if (severity === "watch") return "border-sky-400/40 bg-sky-400/10 text-sky-200";
  return "border-teal-400/40 bg-teal-400/10 text-teal-200";
}

function dotClass(severity: OpsSeverity) {
  if (severity === "critical") return "bg-rose-300";
  if (severity === "warning") return "bg-amber-300";
  if (severity === "watch") return "bg-sky-300";
  return "bg-teal-300";
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}
