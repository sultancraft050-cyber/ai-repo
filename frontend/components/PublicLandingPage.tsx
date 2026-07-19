"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import dynamic from "next/dynamic";
import { ArrowRight, CheckCircle2, Cpu, MessageSquare, ShieldCheck, Wand2 } from "lucide-react";
import { recordAnalyticsEvent, submitFeedback, listCatalogProducts, CatalogProduct } from "@/lib/api";
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

  const [homepageProducts, setHomepageProducts] = useState<CatalogProduct[]>([]);
  const [homepageLoading, setHomepageLoading] = useState(true);
  const [homepageError, setHomepageError] = useState("");

  useEffect(() => {
    recordAnalyticsEvent({
      event_type: "landing_page_visit",
      anonymous_session_id: getGuestId(),
      metadata: { page: "home" }
    }).catch(() => undefined);

    async function loadHomepageProducts() {
      try {
        setHomepageLoading(true);
        const data = await listCatalogProducts(0, 8);
        setHomepageProducts(data);
      } catch (err: any) {
        setHomepageError(err.message || "Failed to load components.");
      } finally {
        setHomepageLoading(false);
      }
    }
    loadHomepageProducts();
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

              <div className="grid gap-3 sm:grid-cols-2">
                <PathCard
                  title="Generate a build for me"
                  text="Best for normal buyers. Enter budget, game target, and resolution."
                  href="/build/generate"
                  primary
                  icon={<Wand2 size={18} aria-hidden />}
                />
                <PathCard
                  title="Pick every part myself"
                  text="Expert mode with manual product picking, wattage, FPS, and compatibility."
                  href="/build/manual"
                  icon={<Cpu size={18} aria-hidden />}
                />
              </div>

              <div className="grid gap-2 text-sm text-muted sm:grid-cols-3">
                <TrustPoint>Saudi prices only</TrustPoint>
                <TrustPoint>Warnings visible</TrustPoint>
                <TrustPoint>Compatibility checked</TrustPoint>
              </div>
            </div>

            <div className="grid gap-3">
              <Hero3DScene />
              <div className="grid gap-3 sm:grid-cols-2">
                <QuickStartCard title="6000 SAR 1440p Gaming" text="Open the auto builder with the common Saudi starter target." href="/build/generate" />
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

        {/* Browse PC Components Section */}
        <div className="rounded-xl border border-line bg-[#0b101d] p-6 sm:p-8 shadow-tight relative overflow-hidden">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6 border-b border-line pb-4">
            <div>
              <h2 className="text-2xl font-bold text-ink">Browse PC Components</h2>
              <p className="text-sm text-muted mt-1">
                Explore our catalog of <strong>280</strong> high-quality PC hardware options.
              </p>
            </div>
            <a
              href="/components"
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-signal hover:bg-signal/80 text-slate-950 font-bold rounded-lg text-sm transition-all"
            >
              View all components
              <ArrowRight size={15} />
            </a>
          </div>

          {/* Category quick selectors */}
          <div className="flex flex-wrap gap-2 mb-6">
            {["CPU", "GPU", "MOTHERBOARD", "RAM", "STORAGE", "PSU", "CASE", "COOLER"].map((cat) => (
              <a
                key={cat}
                href={`/components?category=${cat}`}
                className="px-3 py-1.5 bg-panel border border-line hover:border-signal text-xs font-bold text-muted hover:text-ink rounded-full transition-all"
              >
                {cat}
              </a>
            ))}
          </div>

          {/* Catalog items selection grid */}
          {homepageLoading && (
            <div className="grid place-items-center py-10">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-signal border-t-transparent"></div>
            </div>
          )}

          {homepageError && (
            <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-4 rounded-lg text-xs">
              {homepageError}
            </div>
          )}

          {!homepageLoading && !homepageError && (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
              {homepageProducts.map((p) => (
                <div
                  key={p.id}
                  className="bg-panel border border-line rounded-lg p-4 flex flex-col justify-between hover:border-signal/40 transition-all"
                >
                  <div>
                    <span className="text-[9px] font-black uppercase text-signal bg-signal/10 px-1.5 py-0.5 rounded border border-signal/20">
                      {p.category}
                    </span>
                    <h3 className="text-sm font-bold text-ink mt-2 line-clamp-2 hover:text-signal">
                      <a href={`/components/${p.id}`}>{p.canonical_name}</a>
                    </h3>
                    <p className="text-[11px] text-muted font-medium mt-0.5">By {p.brand}</p>
                  </div>
                  <a
                    href={`/components/${p.id}`}
                    className="text-xs font-black text-signal hover:underline mt-4 flex items-center gap-1"
                  >
                    View details
                    <ArrowRight size={12} />
                  </a>
                </div>
              ))}
            </div>
          )}
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

function PathCard({
  title,
  text,
  href,
  icon,
  primary = false
}: {
  title: string;
  text: string;
  href: string;
  icon: ReactNode;
  primary?: boolean;
 }) {
  return (
    <a
      href={href}
      className={`group rounded-lg border p-4 transition hover:-translate-y-0.5 ${
        primary ? "border-signal bg-signal text-slate-950" : "border-line bg-panel text-ink hover:border-signal"
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="grid h-9 w-9 place-items-center rounded-md bg-black/10">{icon}</span>
        <ArrowRight size={16} className="transition group-hover:translate-x-0.5" aria-hidden />
      </div>
      <div className="mt-4 text-base font-semibold">{title}</div>
      <p className={`mt-1 text-sm leading-6 ${primary ? "text-slate-900/75" : "text-muted"}`}>{text}</p>
    </a>
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
