"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import dynamic from "next/dynamic";
import { ArrowRight, CheckCircle2, MessageSquare, ShieldCheck } from "lucide-react";
import { recordAnalyticsEvent, submitFeedback } from "@/lib/api";
import { getGuestId } from "@/lib/userSession";
import type { FeedbackSubmissionResponse, FeedbackType } from "@/types/builder";

const Hero3DScene = dynamic(() => import("@/components/Hero3DScene").then((module) => module.Hero3DScene), {
  ssr: false,
  loading: () => (
    <div className="grid h-[330px] place-items-center rounded-lg border border-line bg-panel text-sm text-muted sm:h-[430px]">
      Loading 3D preview...
    </div>
  )
});

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
      <div className="mx-auto grid w-full max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-xl border border-line bg-[#0b101d] shadow-tight">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(217,70,239,0.18),transparent_34%),linear-gradient(rgba(255,255,255,0.035)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.035)_1px,transparent_1px)] bg-[length:auto,22px_22px,22px_22px]" />
          <div className="relative grid gap-8 p-4 sm:p-6 lg:grid-cols-[0.9fr_1.1fr] lg:p-10">
            <div className="grid content-center gap-5">
              <div className="inline-flex w-fit items-center gap-2 rounded-full border border-teal-200 bg-teal-50 px-4 py-1.5 text-xs font-semibold uppercase text-signal">
                <ShieldCheck size={14} aria-hidden />
                Saudi PC buying assistant
              </div>

              <div>
                <h1 className="max-w-3xl text-4xl font-semibold leading-tight text-ink sm:text-6xl">
                  Interactive Saudi PC building in 3D.
                </h1>
                <p className="mt-4 max-w-2xl text-base leading-7 text-muted">
                  Pick a budget, see compatibility and Saudi-market warnings, then compare real build options without
                  exposing founder tools to normal users.
                </p>
              </div>

              <div className="flex flex-wrap gap-3">
                <a
                  href="/build/generate"
                  className="inline-flex h-11 items-center justify-center gap-2 rounded-md border border-signal bg-signal px-4 text-sm font-semibold text-slate-950"
                >
                  Start Building
                  <ArrowRight size={16} aria-hidden />
                </a>
                <a
                  href="/build/manual"
                  className="inline-flex h-11 items-center justify-center gap-2 rounded-md border border-line bg-panel px-4 text-sm font-semibold text-ink"
                >
                  Pick Parts Myself
                </a>
              </div>

              <div className="grid gap-2 text-sm text-muted sm:grid-cols-3">
                <TrustPoint>Saudi prices only</TrustPoint>
                <TrustPoint>Warnings visible</TrustPoint>
                <TrustPoint>Compatibility checked</TrustPoint>
              </div>
            </div>

            <div className="grid gap-3">
              <Hero3DScene />
              <div className="grid gap-3 sm:grid-cols-3">
                <QuickStartCard title="Generate a build" text="Fastest path for normal buyers." href="/build/generate" />
                <QuickStartCard title="Pick every part" text="Manual control with final wattage and FPS." href="/build/manual" />
                <button
                  type="button"
                  onClick={() => setFeedbackOpen((open) => !open)}
                  className="rounded-lg border border-line bg-panel p-3 text-left hover:border-signal"
                >
                  <div className="flex items-center gap-2 text-sm font-semibold text-ink">
                    <MessageSquare size={15} aria-hidden />
                    Feedback
                  </div>
                  <p className="mt-1 text-xs leading-5 text-muted">Report a wrong price or confusing warning.</p>
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-md border border-caution/30 bg-amber-50 px-3 py-2 text-sm leading-6 text-caution">
          Prices can change. VAT, shipping, warranty, stock, and store terms may be uncertain. Always verify the store page
          before purchase.
        </div>

        <div id="feedback" className="scroll-mt-20">
          {feedbackOpen ? (
            <div className="rounded-lg border border-line bg-panel p-4 shadow-tight">
              <div className="mb-2 text-sm font-semibold text-ink">Report a problem</div>
              <div className="grid gap-3">
                <select
                  value={feedbackType}
                  onChange={(event) => setFeedbackType(event.target.value as FeedbackType)}
                  className="h-10 rounded-md border border-line bg-panel px-3 text-sm text-ink outline-none focus:border-signal"
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
                  className="min-h-20 rounded-md border border-line bg-panel px-3 py-2 text-sm text-ink outline-none focus:border-signal"
                />
                <button
                  type="button"
                  onClick={sendFeedback}
                  disabled={feedbackNotes.trim().length < 4}
                  className="inline-flex h-10 items-center justify-center rounded-md border border-line bg-panel px-4 text-sm font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-60"
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

function QuickStartCard({ title, text, href }: { title: string; text: string; href: string }) {
  return (
    <a href={href} className="rounded-lg border border-line bg-panel p-3 hover:border-signal">
      <div className="text-sm font-semibold text-ink">{title}</div>
      <p className="mt-1 text-xs leading-5 text-muted">{text}</p>
    </a>
  );
}
