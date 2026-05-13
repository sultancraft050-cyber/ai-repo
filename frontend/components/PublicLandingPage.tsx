"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ArrowRight, CheckCircle2, MessageSquare, ShieldCheck } from "lucide-react";
import { recordAnalyticsEvent, submitFeedback } from "@/lib/api";
import { getGuestId } from "@/lib/userSession";
import type { FeedbackSubmissionResponse, FeedbackType } from "@/types/builder";

export function PublicLandingPage() {
  const [feedbackType, setFeedbackType] = useState<FeedbackType>("wrong_price");
  const [feedbackNotes, setFeedbackNotes] = useState("");
  const [feedbackStatus, setFeedbackStatus] = useState<FeedbackSubmissionResponse | null>(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);

  useEffect(() => {
    recordAnalyticsEvent({
      event_type: "landing_page_visit",
      anonymous_session_id: getGuestId(),
      metadata: { page: "home" }
    }).catch(() => undefined);
  }, []);

  async function sendFeedback() {
    setFeedbackStatus(null);
    try {
      setFeedbackStatus(
        await submitFeedback({
          type: feedbackType,
          notes: feedbackNotes,
          anonymous_session_id: getGuestId()
        })
      );
      setFeedbackNotes("");
    } catch {
      setFeedbackStatus({
        status: "accepted",
        feedback_id: "local-feedback",
        message: "Feedback could not be sent right now. Please try again later."
      });
    }
  }

  return (
    <section className="border-b border-line">
      <div className="mx-auto grid w-full max-w-5xl gap-6 px-4 py-8 sm:px-6 lg:py-10">
        <div className="grid content-center gap-5">
          <div className="inline-flex w-fit items-center gap-2 rounded-md border border-teal-200 bg-teal-50 px-3 py-1 text-xs font-semibold uppercase text-signal">
            <ShieldCheck size={14} aria-hidden />
            Saudi PC buying assistant
          </div>

          <div>
            <h1 className="max-w-3xl text-3xl font-semibold leading-tight text-ink sm:text-5xl">
              Pick a budget. Get a Saudi PC build you can understand.
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-7 text-muted">
              The assistant checks compatibility, Saudi prices, budget fit, and store uncertainty. It keeps warnings visible
              without making you read an operations dashboard.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <a
              href="#builder"
              className="inline-flex h-11 items-center justify-center gap-2 rounded-md border border-signal bg-signal px-4 text-sm font-semibold text-slate-950"
            >
              Start a build
              <ArrowRight size={16} aria-hidden />
            </a>
            <button
              type="button"
              onClick={() => setFeedbackOpen((open) => !open)}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-md border border-line bg-panel px-4 text-sm font-semibold text-ink"
            >
              <MessageSquare size={16} aria-hidden />
              Report an issue
            </button>
          </div>

          <div className="grid gap-2 text-sm text-muted sm:grid-cols-3">
            <TrustPoint>Saudi prices only for Saudi builds</TrustPoint>
            <TrustPoint>Warnings stay visible</TrustPoint>
            <TrustPoint>Compatibility checked before recommendation</TrustPoint>
          </div>

          <div className="rounded-md border border-caution/30 bg-amber-50 px-3 py-2 text-sm leading-6 text-caution">
            Prices can change. VAT, shipping, warranty, stock, and store terms may be uncertain. Always verify the store page
            before purchase.
          </div>

          {feedbackOpen ? (
            <div className="rounded-lg border border-line bg-panel p-4 shadow-tight">
              <div className="mb-2 text-sm font-semibold text-ink">Report a problem</div>
              <div className="grid gap-3">
                <select
                  value={feedbackType}
                  onChange={(event) => setFeedbackType(event.target.value as FeedbackType)}
                  className="h-10 rounded-md border border-line bg-white px-3 text-sm text-ink outline-none focus:border-signal"
                >
                  <option value="wrong_price">Wrong price</option>
                  <option value="expired_listing">Expired listing</option>
                  <option value="wrong_compatibility">Wrong compatibility</option>
                  <option value="suspicious_recommendation">Suspicious recommendation</option>
                  <option value="bad_vendor_listing">Bad vendor listing</option>
                  <option value="broken_product_url">Broken product URL</option>
                  <option value="missing_store">Missing store</option>
                  <option value="missing_product">Missing product</option>
                  <option value="confusing_warning">Confusing warning</option>
                </select>
                <textarea
                  value={feedbackNotes}
                  onChange={(event) => setFeedbackNotes(event.target.value.slice(0, 800))}
                  placeholder="What should the founder review?"
                  className="min-h-20 rounded-md border border-line bg-white px-3 py-2 text-sm text-ink outline-none focus:border-signal"
                />
                <button
                  type="button"
                  onClick={sendFeedback}
                  disabled={feedbackNotes.trim().length < 4}
                  className="inline-flex h-10 items-center justify-center rounded-md border border-line bg-white px-4 text-sm font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Send feedback
                </button>
                {feedbackStatus ? <p className="text-sm text-muted">{feedbackStatus.message}</p> : null}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function TrustPoint({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-line bg-panel px-3 py-2">
      <CheckCircle2 size={15} className="shrink-0 text-signal" aria-hidden />
      <span>{children}</span>
    </div>
  );
}
