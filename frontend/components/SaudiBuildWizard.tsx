"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Cpu, Loader2, Scale, SlidersHorizontal, Wand2 } from "lucide-react";
import { BuildRecommendationCard } from "@/components/BuildRecommendationCard";
import { DataCompletenessPanel } from "@/components/DataCompletenessPanel";
import { useRegion } from "@/components/RegionProvider";
import { addWatchlistItem, generateSaudiLocalBuild, getSaudiBuildDataCompleteness, saveBuild } from "@/lib/api";
import { getIdentity, rememberRecentBuild } from "@/lib/userSession";
import type {
  SaudiBuildDataCompleteness,
  SaudiBuildComponent,
  SaudiBuildOption,
  SaudiBuildPriority,
  SaudiBuildRequest,
  SaudiBuildResolution,
  SaudiBuildResponse,
  SaudiBuildUseCase
} from "@/types/builder";

const useCases: { value: SaudiBuildUseCase; label: string }[] = [
  { value: "gaming", label: "Gaming" },
  { value: "simulation", label: "Simulation" },
  { value: "workstation", label: "Workstation" },
  { value: "content_creation", label: "Content creation" },
  { value: "ai_ml", label: "AI / ML" },
  { value: "streaming", label: "Streaming" },
  { value: "general", label: "General" }
];

const resolutions: { value: SaudiBuildResolution; label: string }[] = [
  { value: "1080p", label: "1080p" },
  { value: "1440p", label: "1440p" },
  { value: "4k", label: "4K" },
  { value: "ultrawide", label: "Ultrawide" }
];

const priorities: { value: SaudiBuildPriority; label: string }[] = [
  { value: "best_value", label: "Best value" },
  { value: "maximum_performance", label: "Maximum performance" },
  { value: "quiet_build", label: "Quiet build" },
  { value: "upgrade_path", label: "Upgrade path" },
  { value: "local_availability", label: "Local availability" },
  { value: "lowest_risk", label: "Lowest risk" }
];

const brandOptions = ["AMD", "Intel", "NVIDIA"] as const;

const buildModeLabels: Record<string, string> = {
  recommended_saudi_build: "Recommended",
  budget_fit_build: "Budget Fit",
  best_value_build: "Best Value",
  lowest_risk_local_build: "Lowest Risk",
};

export function SaudiBuildWizard() {
  const { region, setRegion } = useRegion();
  const [budget, setBudget] = useState("6000");
  const [useCase, setUseCase] = useState<SaudiBuildUseCase>("gaming");
  const [resolution, setResolution] = useState<SaudiBuildResolution>("1440p");
  const [refreshRate, setRefreshRate] = useState<60 | 120 | 144 | 165 | 240>(144);
  const [brands, setBrands] = useState<SaudiBuildRequest["brand_preferences"]>(["AMD", "NVIDIA"]);
  const [caseSize, setCaseSize] = useState<SaudiBuildRequest["case_size"]>("ATX");
  const [priority, setPriority] = useState<SaudiBuildPriority>("best_value");
  const [includeMonitor, setIncludeMonitor] = useState(false);
  const [includePeripherals, setIncludePeripherals] = useState(false);
  const [strictBudget, setStrictBudget] = useState(false);
  const [selectedBuildLabel, setSelectedBuildLabel] = useState<string>("recommended_saudi_build");
  const [completeness, setCompleteness] = useState<SaudiBuildDataCompleteness | null>(null);
  const [response, setResponse] = useState<SaudiBuildResponse | null>(null);
  const [loadingCompleteness, setLoadingCompleteness] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [savingBuildLabel, setSavingBuildLabel] = useState<string | null>(null);
  const [shareMessage, setShareMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isSaudiRegion = region === "SA";
  const numericBudget = Number(budget);
  const budgetValid = Number.isFinite(numericBudget) && numericBudget > 0;

  const request = useMemo<SaudiBuildRequest>(
    () => ({
      region: "SA",
      city: "Riyadh",
      budget_sar: budgetValid ? numericBudget : 6000,
      use_case: useCase,
      target_resolution: resolution,
      refresh_rate_target: refreshRate,
      brand_preferences: brands.length ? brands : ["no_preference"],
      case_size: caseSize,
      priority,
      strict_budget: strictBudget,
      include_monitor: includeMonitor,
      include_peripherals: includePeripherals
    }),
    [brands, budgetValid, caseSize, includeMonitor, includePeripherals, numericBudget, priority, refreshRate, resolution, strictBudget, useCase]
  );

  async function loadCompleteness() {
    setLoadingCompleteness(true);
    setError(null);
    try {
      const result = await getSaudiBuildDataCompleteness("SA", "Riyadh");
      setCompleteness(result);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load Saudi build readiness.");
    } finally {
      setLoadingCompleteness(false);
    }
  }

  useEffect(() => {
    loadCompleteness();
  }, []);

  async function generateBuild() {
    if (!budgetValid) {
      setError("Enter a valid SAR budget before generating a build.");
      return;
    }
    setGenerating(true);
    setError(null);
    try {
      const result = await generateSaudiLocalBuild(request);
      setResponse(result);
      setCompleteness(result.data_completeness);
      setSelectedBuildLabel(result.builds[0]?.label ?? "recommended_saudi_build");
      result.builds.slice(0, 4).forEach(rememberRecentBuild);
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : "Unable to generate Saudi build.");
    } finally {
      setGenerating(false);
    }
  }

  function toggleBrand(brand: (typeof brandOptions)[number]) {
    setBrands((current) => {
      const next = current.includes(brand) ? current.filter((item) => item !== brand) : [...current.filter((item) => item !== "no_preference"), brand];
      return next.length ? next : ["no_preference"];
    });
  }

  async function handleSaveBuild(build: SaudiBuildOption) {
    setSavingBuildLabel(build.label);
    setError(null);
    setShareMessage(null);
    try {
      const identity = getIdentity();
      const saved = await saveBuild({
        user_id: identity.user_id ?? null,
        guest_id: identity.user_id ? null : identity.guest_id,
        title: build.title,
        region: "SA",
        build_mode: build.label,
        total_price_sar: build.summary.total_recommended_price_sar ?? null,
        confidence_level: build.summary.confidence_level,
        warning_summary: build.summary.warning_summary,
        component_ids: build.components.map((component) => component.product_id),
        price_snapshot_ids: [],
        build_summary: build.summary as unknown as Record<string, unknown>,
        build_payload: build as unknown as Record<string, unknown>,
        public_visibility: true,
        favorite: false
      });
      const shareUrl = `${window.location.origin}/build/share/${saved.share_slug}`;
      setShareMessage(`Saved. Share link: ${shareUrl}`);
      void navigator.clipboard?.writeText(shareUrl);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save build.");
    } finally {
      setSavingBuildLabel(null);
    }
  }

  function handleShareBuild(build: SaudiBuildOption) {
    const shareText = build.export.shareable_build_url || build.export.markdown_summary;
    void navigator.clipboard?.writeText(shareText);
    setShareMessage("Build export copied. Save the build to create a public share page.");
  }

  async function handleWatchProduct(component: SaudiBuildComponent) {
    setError(null);
    try {
      const identity = getIdentity();
      await addWatchlistItem(
        { user_id: identity.user_id ?? null, guest_id: identity.user_id ? null : identity.guest_id },
        { product_id: component.product_id, target_price_sar: component.recommended_price_sar ?? null, region: "SA" }
      );
      setShareMessage(`${component.category} added to your Saudi price watchlist.`);
    } catch (watchError) {
      setError(watchError instanceof Error ? watchError.message : "Unable to add product to watchlist.");
    }
  }

  return (
    <section className="grid gap-4">
      <div className="rounded-lg border border-line bg-white p-4 shadow-tight">
        <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase text-signal">
              <Cpu size={15} aria-hidden />
              Saudi local PC build generator
            </div>
            <h2 className="text-lg font-semibold text-ink">Build Around Your Saudi Budget</h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-muted">
              Uses Saudi-region pricing only. If a category is missing, the system stops and suggests dry-run discovery instead of inventing a build.
            </p>
          </div>
          {!isSaudiRegion ? (
            <button
              type="button"
              onClick={() => setRegion("SA")}
              className="inline-flex h-9 items-center justify-center rounded-md border border-signal bg-teal-50 px-3 text-sm font-semibold text-signal"
            >
              Switch to Saudi Arabia
            </button>
          ) : (
            <span className="inline-flex h-9 items-center rounded-md border border-line bg-panel px-3 text-sm font-semibold text-ink">
              Saudi Arabia market
            </span>
          )}
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <label className="grid gap-1 text-sm font-semibold text-ink">
            Budget in SAR
            <input
              value={budget}
              onChange={(event) => setBudget(event.target.value)}
              inputMode="numeric"
              className="h-10 rounded-md border border-line bg-white px-3 text-sm font-normal text-ink outline-none focus:border-signal"
            />
          </label>
          <SelectField label="Use case" value={useCase} onChange={(value) => setUseCase(value as SaudiBuildUseCase)} options={useCases} />
          <SelectField
            label="Target resolution"
            value={resolution}
            onChange={(value) => setResolution(value as SaudiBuildResolution)}
            options={resolutions}
          />
        </div>

        <details className="mt-4 rounded-md border border-line bg-panel px-3 py-2">
          <summary className="cursor-pointer text-sm font-semibold text-ink">More options</summary>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <SelectField
              label="Refresh target"
              value={String(refreshRate)}
              onChange={(value) => setRefreshRate(Number(value) as 60 | 120 | 144 | 165 | 240)}
              options={[60, 120, 144, 165, 240].map((value) => ({ value: String(value), label: `${value} Hz` }))}
            />
            <SelectField
              label="Case size"
              value={caseSize}
              onChange={(value) => setCaseSize(value as SaudiBuildRequest["case_size"])}
              options={[
                { value: "ATX", label: "ATX" },
                { value: "mATX", label: "mATX" },
                { value: "ITX", label: "ITX" },
                { value: "no_preference", label: "No preference" }
              ]}
            />
            <SelectField label="Priority" value={priority} onChange={(value) => setPriority(value as SaudiBuildPriority)} options={priorities} />
            <div className="md:col-span-3">
              <div className="mb-2 text-sm font-semibold text-ink">Preferred brands</div>
              <div className="flex flex-wrap gap-2">
                {brandOptions.map((brand) => (
                  <button
                    key={brand}
                    type="button"
                    onClick={() => toggleBrand(brand)}
                    className={`rounded-md border px-3 py-2 text-sm font-semibold ${
                      brands.includes(brand) ? "border-signal bg-teal-50 text-signal" : "border-line bg-panel text-muted"
                    }`}
                  >
                    {brand}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap gap-3 md:col-span-3">
              <label className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
                <input type="checkbox" checked={includeMonitor} onChange={(event) => setIncludeMonitor(event.target.checked)} />
                Include monitor
              </label>
              <label className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
                <input type="checkbox" checked={includePeripherals} onChange={(event) => setIncludePeripherals(event.target.checked)} />
                Include peripherals
              </label>
              <label className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
                <input type="checkbox" checked={strictBudget} onChange={(event) => setStrictBudget(event.target.checked)} />
                Strict budget
              </label>
            </div>
          </div>
        </details>

        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={generateBuild}
            disabled={generating || !isSaudiRegion || !budgetValid}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-signal bg-signal px-4 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {generating ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Wand2 size={16} aria-hidden />}
            Generate Saudi Build
          </button>
        </div>

        {error ? (
          <div className="mt-4 flex items-start gap-2 rounded-md border border-caution/40 bg-amber-50 px-3 py-2 text-sm text-caution">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden />
            <span>{error}</span>
          </div>
        ) : null}
        {shareMessage ? (
          <div className="mt-4 rounded-md border border-teal-200 bg-teal-50 px-3 py-2 text-sm text-signal">
            {shareMessage}
          </div>
        ) : null}
      </div>

      {generating ? (
        <div className="rounded-lg border border-line bg-white p-4 text-sm text-muted shadow-tight" aria-live="polite">
          <div className="mb-2 flex items-center gap-2 font-semibold text-ink">
            <Loader2 size={16} className="animate-spin" aria-hidden />
            Checking Saudi-market build options
          </div>
          <p className="leading-6">
            The generator is validating compatibility, budget fit, warnings, and Saudi-only price snapshots. No US price fallback is used.
          </p>
        </div>
      ) : null}

      <DataCompletenessPanel completeness={completeness} loading={loadingCompleteness} error={error} onRetry={loadCompleteness} />

      {response?.build_status === "incomplete_data" ? (
        <div className="rounded-lg border border-caution/30 bg-amber-50 p-4 text-caution">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <SlidersHorizontal size={16} aria-hidden />
            Not enough Saudi data for a full build yet
          </div>
          <div className="grid gap-1 text-sm leading-6">
            {response.missing_data_warnings.slice(0, 6).map((warning) => (
              <span key={warning}>{warning}</span>
            ))}
          </div>
        </div>
      ) : null}

      {response?.build_status === "no_budget_fit" ? (
        <div className="rounded-lg border border-caution/30 bg-amber-50 p-4 text-caution">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <SlidersHorizontal size={16} aria-hidden />
            No valid build fits this strict budget yet
          </div>
          <div className="grid gap-1 text-sm leading-6">
            {response.missing_data_warnings.slice(0, 4).map((warning) => (
              <span key={warning}>{warning}</span>
            ))}
          </div>
        </div>
      ) : null}

      {response?.build_status === "no_budget_fit" && response.strict_budget_failure ? (
        <div className="rounded-lg border border-caution/30 bg-amber-50 p-4 text-caution">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <SlidersHorizontal size={16} aria-hidden />
            Strict budget guidance
          </div>
          <div className="grid gap-2 text-sm leading-6">
            <span>{response.strict_budget_failure.reason}</span>
            <span>
              Missing cheaper categories: {response.strict_budget_failure.missing_cheaper_categories.join(", ")}
            </span>
            <span>
              Suggested product families: {response.strict_budget_failure.suggested_products_to_add.slice(0, 5).join(", ")}
            </span>
          </div>
        </div>
      ) : null}

      {response?.recommended_discovery_jobs.length ? (
        <div className="rounded-lg border border-line bg-white p-4 shadow-tight">
          <div className="mb-3 text-sm font-semibold text-ink">Budget discovery suggestions</div>
          <div className="grid gap-2 md:grid-cols-2">
            {response.recommended_discovery_jobs.slice(0, 8).map((job) => (
              <div key={`${job.category}-${job.query}`} className="rounded-md border border-line bg-panel p-3 text-sm">
                <div className="font-semibold text-ink">{job.category}</div>
                <div className="mt-1 text-muted">{job.query}</div>
                <div className="mt-2 text-xs leading-5 text-muted">{job.reason}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {response?.build_comparison.length ? (
        <div className="rounded-lg border border-line bg-white p-4 shadow-tight">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
            <Scale size={16} aria-hidden />
            Build comparison
          </div>
          <div className="grid gap-2 lg:grid-cols-4">
            {response.build_comparison.map((item) => (
              <button
                key={item.label}
                type="button"
                onClick={() => setSelectedBuildLabel(item.label)}
                className={`rounded-md border p-3 text-left text-sm ${
                  selectedBuildLabel === item.label ? "border-signal bg-teal-50" : "border-line bg-panel"
                }`}
              >
                <div className="mb-2 flex flex-wrap gap-1">
                  {item.cheapest_option ? (
                    <span className="rounded border border-teal-200 bg-white px-1.5 py-0.5 text-[11px] font-semibold text-signal">
                      Cheapest
                    </span>
                  ) : null}
                  {item.safest_option ? (
                    <span className="rounded border border-teal-200 bg-white px-1.5 py-0.5 text-[11px] font-semibold text-signal">
                      Safest
                    </span>
                  ) : null}
                </div>
                <div className="font-semibold text-ink">{buildModeLabels[item.label] ?? item.title}</div>
                <div className="mt-1 text-xs leading-5 text-muted">
                  {formatSar(item.total_price_sar)} · {item.budget_status.replaceAll("_", " ")}
                </div>
                <div className="mt-2 text-xs leading-5 text-muted">
                  Risk {item.risk_level}; confidence {Math.round(item.confidence_score * 100)}%
                </div>
                <div className="mt-2 text-xs leading-5 text-muted">{item.local_availability_summary}</div>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {response?.builds.length ? (
        <div className="grid gap-4">
          <div className="rounded-lg border border-teal-200 bg-teal-50 p-3 text-sm leading-6 text-signal">
            Save a build to revisit it later, share it publicly, and watch component prices as Saudi listings change.
          </div>
          <div className="flex flex-wrap gap-2">
            {response.builds.map((build) => (
              <button
                key={build.label}
                type="button"
                onClick={() => setSelectedBuildLabel(build.label)}
                className={`rounded-md border px-3 py-2 text-sm font-semibold ${
                  selectedBuildLabel === build.label ? "border-signal bg-teal-50 text-signal" : "border-line bg-white text-muted"
                }`}
              >
                {buildModeLabels[build.label] ?? build.label.replaceAll("_", " ")}
              </button>
            ))}
          </div>
          {response.builds
            .filter((build) => build.label === selectedBuildLabel)
            .map((build) => (
              <BuildRecommendationCard
                key={build.label}
                build={build}
                onSave={handleSaveBuild}
                onShare={handleShareBuild}
                onWatchProduct={handleWatchProduct}
                saving={savingBuildLabel === build.label}
              />
            ))}
        </div>
      ) : null}
    </section>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="grid gap-1 text-sm font-semibold text-ink">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 rounded-md border border-line bg-white px-3 text-sm font-normal text-ink outline-none focus:border-signal"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function formatSar(value?: number | null) {
  if (value === null || value === undefined) return "Unavailable";
  return new Intl.NumberFormat("en-SA", {
    style: "currency",
    currency: "SAR",
    maximumFractionDigits: 0
  }).format(value);
}
