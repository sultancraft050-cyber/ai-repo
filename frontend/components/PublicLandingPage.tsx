"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { AlertTriangle, ArrowRight, CheckCircle2, Link as LinkIcon, ShieldCheck } from "lucide-react";
import { recordAnalyticsEvent, submitFeedback, submitPublicDeal } from "@/lib/api";
import { getGuestId } from "@/lib/userSession";
import type { FeedbackSubmissionResponse, FeedbackType, ProductCategory, PublicDealSubmissionResponse } from "@/types/builder";

const categories: ProductCategory[] = ["CPU", "GPU", "Motherboard", "RAM", "Storage", "PSU", "Case", "Cooler"];

export function PublicLandingPage() {
  const [url, setUrl] = useState("");
  const [category, setCategory] = useState<ProductCategory>("GPU");
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<PublicDealSubmissionResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [feedbackType, setFeedbackType] = useState<FeedbackType>("wrong_price");
  const [feedbackNotes, setFeedbackNotes] = useState("");
  const [feedbackStatus, setFeedbackStatus] = useState<FeedbackSubmissionResponse | null>(null);

  useEffect(() => {
    recordAnalyticsEvent({
      event_type: "landing_page_visit",
      anonymous_session_id: getGuestId(),
      metadata: { page: "home" }
    }).catch(() => undefined);
  }, []);

  async function submitDeal() {
    setSubmitting(true);
    setStatus(null);
    try {
      setStatus(
        await submitPublicDeal({
          url,
          category,
          email: email || null,
          note: "Public landing page deal submission"
        })
      );
      setUrl("");
    } catch (error) {
      setStatus({
        status: "rejected",
        category,
        region: "SA",
        message: error instanceof Error ? error.message : "Unable to submit deal."
      });
    } finally {
      setSubmitting(false);
    }
  }

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
    <section className="border-b border-line bg-white">
      <div className="mx-auto grid w-full max-w-7xl gap-8 px-4 py-8 sm:px-6 lg:grid-cols-[1.15fr_0.85fr] lg:py-10">
        <div className="grid content-center gap-5">
          <div className="inline-flex w-fit items-center gap-2 rounded-md border border-teal-200 bg-teal-50 px-3 py-1 text-xs font-semibold uppercase text-signal">
            <ShieldCheck size={14} aria-hidden />
            Saudi PC buying assistant
          </div>
          <div>
            <h1 className="max-w-3xl text-3xl font-semibold leading-tight text-ink sm:text-5xl">
              Build a compatible PC with Saudi prices, risks, and confidence in view.
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-7 text-muted">
              Plan a gaming or workstation PC using Saudi-region listings only. The system shows budget fit, compatibility,
              local availability, VAT/shipping/warranty uncertainty, and safer alternatives before you buy.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <a
              href="#builder"
              className="inline-flex h-11 items-center justify-center gap-2 rounded-md border border-signal bg-signal px-4 text-sm font-semibold text-white"
            >
              Start a build
              <ArrowRight size={16} aria-hidden />
            </a>
            <a
              href="#submit-deal"
              className="inline-flex h-11 items-center justify-center gap-2 rounded-md border border-line bg-panel px-4 text-sm font-semibold text-ink"
            >
              Submit a deal
            </a>
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
        </div>

        <div id="submit-deal" className="rounded-lg border border-line bg-panel p-4 shadow-tight">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
            <LinkIcon size={16} aria-hidden />
            Submit a Saudi deal URL
          </div>
          <p className="mb-3 text-sm leading-6 text-muted">
            Paste a supported public product page. This only validates the URL for founder review; it does not ingest prices.
          </p>
          <div className="grid gap-3">
            <label className="grid gap-1 text-sm font-semibold text-ink">
              Product URL
              <input
                value={url}
                onChange={(event) => setUrl(event.target.value.slice(0, 2048))}
                placeholder="https://www.pczonesa.com/..."
                className="h-10 rounded-md border border-line bg-white px-3 text-sm font-normal text-ink outline-none focus:border-signal"
              />
            </label>
            <div className="grid gap-3 sm:grid-cols-[1fr_1fr]">
              <label className="grid gap-1 text-sm font-semibold text-ink">
                Category
                <select
                  value={category}
                  onChange={(event) => setCategory(event.target.value as ProductCategory)}
                  className="h-10 rounded-md border border-line bg-white px-3 text-sm font-normal text-ink outline-none focus:border-signal"
                >
                  {categories.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
              <label className="grid gap-1 text-sm font-semibold text-ink">
                Email optional
                <input
                  value={email}
                  onChange={(event) => setEmail(event.target.value.slice(0, 254))}
                  placeholder="for follow-up"
                  className="h-10 rounded-md border border-line bg-white px-3 text-sm font-normal text-ink outline-none focus:border-signal"
                />
              </label>
            </div>
            <button
              type="button"
              onClick={submitDeal}
              disabled={submitting || url.length < 8}
              className="inline-flex h-10 items-center justify-center rounded-md border border-signal bg-signal px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? "Checking URL" : "Submit for review"}
            </button>
          </div>
          {status ? (
            <div
              className={`mt-3 flex items-start gap-2 rounded-md border px-3 py-2 text-sm ${
                status.status === "accepted" ? "border-teal-200 bg-teal-50 text-signal" : "border-caution/40 bg-amber-50 text-caution"
              }`}
            >
              {status.status === "accepted" ? <CheckCircle2 size={16} className="mt-0.5 shrink-0" /> : <AlertTriangle size={16} className="mt-0.5 shrink-0" />}
              <span>{status.message}</span>
            </div>
          ) : null}

          <div className="mt-5 border-t border-line pt-4">
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
