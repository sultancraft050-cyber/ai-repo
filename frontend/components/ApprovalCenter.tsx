"use client";

import { CheckCircle2, Eye, Hourglass, Loader2, ShieldAlert, XCircle } from "lucide-react";
import { useState } from "react";
import type { ApprovalItem, OpsSeverity } from "@/types/builder";
import { SeverityBadge } from "@/components/FounderDailyBrief";

type ApprovalCenterProps = {
  approvals: ApprovalItem[];
  loading: boolean;
  error: string | null;
  actingApprovalId: string | null;
  onApprove: (approvalId: string, note?: string) => void;
  onReject: (approvalId: string, note?: string) => void;
  onDefer: (approvalId: string, note?: string) => void;
  onMarkReviewed: (approvalId: string, note?: string) => void;
};

type ConfirmState =
  | { kind: "approve"; approval: ApprovalItem }
  | { kind: "reject"; approval: ApprovalItem }
  | { kind: "defer"; approval: ApprovalItem }
  | null;

export function ApprovalCenter({
  approvals,
  loading,
  error,
  actingApprovalId,
  onApprove,
  onReject,
  onDefer,
  onMarkReviewed
}: ApprovalCenterProps) {
  const [confirming, setConfirming] = useState<ConfirmState>(null);
  const [note, setNote] = useState("");

  function submitDecision() {
    if (!confirming) return;
    if (confirming.kind === "approve") onApprove(confirming.approval.id, note);
    if (confirming.kind === "reject") onReject(confirming.approval.id, note);
    if (confirming.kind === "defer") onDefer(confirming.approval.id, note);
    setConfirming(null);
    setNote("");
  }

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-4 text-slate-100">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase text-teal-300">
            <ShieldAlert size={15} aria-hidden />
            Approval Center
          </div>
          <h2 className="text-lg font-semibold text-white">High-risk actions waiting on founder judgment</h2>
        </div>
        <span className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-400">{approvals.length} pending</span>
      </div>

      {error ? <div className="mb-3 rounded-md border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-sm text-amber-100">{error}</div> : null}

      {loading ? (
        <div className="grid gap-2">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="h-32 animate-pulse rounded-md border border-slate-800 bg-slate-900" />
          ))}
        </div>
      ) : approvals.length ? (
        <div className="grid gap-3">
          {approvals.map((approval) => (
            <ApprovalCard
              key={approval.id}
              approval={approval}
              acting={actingApprovalId === approval.id}
              onOpenDecision={(kind) => {
                setNote("");
                setConfirming({ kind, approval });
              }}
              onMarkReviewed={onMarkReviewed}
            />
          ))}
        </div>
      ) : (
        <div className="rounded-md border border-slate-800 bg-slate-900 px-3 py-8 text-sm text-slate-400">
          No approval is pending. Level 0 and Level 1 automation can keep running with audit coverage.
        </div>
      )}

      {confirming ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4" role="presentation">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="approval-confirm-title"
            className="w-full max-w-lg rounded-lg border border-slate-700 bg-slate-950 p-4 text-slate-100 shadow-xl"
          >
            <h3 id="approval-confirm-title" className="text-base font-semibold text-white">
              Confirm {confirming.kind}
            </h3>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              This records an audit event before any follow-on execution. Review the rollback plan before approving high-risk work.
            </p>
            <div className="mt-3 rounded border border-slate-800 bg-slate-900 p-3 text-xs text-slate-300">
              <div className="font-semibold text-slate-100">{approvalTitle(confirming.approval)}</div>
              <div className="mt-1">{confirming.approval.rollback_plan}</div>
            </div>
            <label className="mt-3 block">
              <span className="text-xs font-semibold uppercase text-slate-500">Decision note</span>
              <textarea
                value={note}
                onChange={(event) => setNote(event.target.value)}
                rows={3}
                className="mt-1 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
                placeholder="Optional audit note"
              />
            </label>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => setConfirming(null)} className="rounded border border-slate-700 px-3 py-2 text-sm font-semibold text-slate-200">
                Cancel
              </button>
              <button type="button" onClick={submitDecision} className="rounded bg-teal-600 px-3 py-2 text-sm font-semibold text-white">
                Record decision
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function ApprovalCard({
  approval,
  acting,
  onOpenDecision,
  onMarkReviewed
}: {
  approval: ApprovalItem;
  acting: boolean;
  onOpenDecision: (kind: "approve" | "reject" | "defer") => void;
  onMarkReviewed: (approvalId: string, note?: string) => void;
}) {
  const severity = riskToSeverity(approval.risk_level);
  const manualOnly = approval.risk_level === "level_3";
  return (
    <article className="rounded-md border border-slate-800 bg-slate-900 p-3">
      <div className="mb-2 flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-white">{approvalTitle(approval)}</h3>
            <SeverityBadge severity={severity} compact />
            <span className="rounded border border-slate-700 px-2 py-0.5 text-xs font-semibold capitalize text-slate-300">
              {approval.status}
            </span>
          </div>
          <p className="text-xs leading-5 text-slate-400">{approval.description ?? approval.reasoning}</p>
        </div>
        <div className="text-xs text-slate-500">trace {approval.trace_id}</div>
      </div>

      <div className="grid gap-2 md:grid-cols-2">
        <DetailBlock title="Evidence" value={approval.evidence_summary || Object.keys(approval.evidence).join(", ") || "Evidence attached in graph."} />
        <DetailBlock title="Risk" value={approval.risk_explanation || "High-impact action requires approval."} />
        <DetailBlock title="Affected Entities" value={`${approval.affected_count ?? approval.affected_entities.length} affected: ${(approval.target_entities ?? approval.affected_entities).join(", ") || "not specified"}`} />
        <DetailBlock title="Expected Impact" value={approval.expected_impact || "No execution occurs until approval is audited."} />
      </div>

      <div className="mt-2 rounded border border-slate-800 bg-slate-950 px-3 py-2">
        <div className="mb-1 text-xs font-semibold uppercase text-slate-500">Rollback Plan</div>
        <p className="text-xs leading-5 text-slate-400">{approval.rollback_plan}</p>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onOpenDecision("approve")}
          disabled={acting || manualOnly}
          className="inline-flex h-8 items-center justify-center gap-1 rounded bg-teal-600 px-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
        >
          {acting ? <Loader2 size={13} className="animate-spin" aria-hidden /> : <CheckCircle2 size={13} aria-hidden />}
          Approve
        </button>
        <button
          type="button"
          onClick={() => onOpenDecision("reject")}
          disabled={acting}
          className="inline-flex h-8 items-center justify-center gap-1 rounded border border-slate-700 px-2 text-xs font-semibold text-slate-200 disabled:text-slate-600"
        >
          <XCircle size={13} aria-hidden />
          Reject
        </button>
        <button
          type="button"
          onClick={() => onOpenDecision("defer")}
          disabled={acting}
          className="inline-flex h-8 items-center justify-center gap-1 rounded border border-slate-700 px-2 text-xs font-semibold text-slate-200 disabled:text-slate-600"
        >
          <Hourglass size={13} aria-hidden />
          Defer
        </button>
        <button
          type="button"
          onClick={() => onMarkReviewed(approval.id, "Marked reviewed from approval center.")}
          disabled={acting}
          className="inline-flex h-8 items-center justify-center gap-1 rounded border border-slate-700 px-2 text-xs font-semibold text-slate-200 disabled:text-slate-600"
        >
          <Eye size={13} aria-hidden />
          Mark reviewed
        </button>
      </div>
      {manualOnly ? (
        <p className="mt-2 text-xs text-rose-200">Level 3 manual-only actions cannot be approved for autonomous execution.</p>
      ) : null}
    </article>
  );
}

function DetailBlock({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-950 px-3 py-2">
      <div className="mb-1 text-xs font-semibold uppercase text-slate-500">{title}</div>
      <p className="text-xs leading-5 text-slate-400">{value}</p>
    </div>
  );
}

function approvalTitle(approval: ApprovalItem) {
  return approval.title || approval.action_type.replaceAll("_", " ");
}

function riskToSeverity(risk: ApprovalItem["risk_level"]): OpsSeverity {
  if (risk === "level_3") return "critical";
  if (risk === "level_2") return "warning";
  if (risk === "level_1") return "watch";
  return "info";
}
