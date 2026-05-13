"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { useMachine } from "@xstate/react";
import { RotateCcw } from "lucide-react";
import { builderMachine } from "@/machines/builderMachine";
import { fetchComponentOptions } from "@/lib/api";
import { useRegion } from "@/components/RegionProvider";
import {
  componentOrder,
  selectionKeyByKind,
  type BuildPreferences,
  type ComponentKind,
  type ComponentOption
} from "@/types/builder";
import { ComponentSelector } from "@/components/ComponentSelector";
import { PreferencePanel } from "@/components/PreferencePanel";
import { SaudiBuildWizard } from "@/components/SaudiBuildWizard";
import { RegionSelector } from "@/components/RegionSelector";

const AutoBuildGenerator = dynamic(
  () => import("@/components/AutoBuildGenerator").then((module) => module.AutoBuildGenerator),
  { loading: () => <PanelLoading label="Loading generator" /> }
);
const CompatibilityPanel = dynamic(
  () => import("@/components/CompatibilityPanel").then((module) => module.CompatibilityPanel),
  { loading: () => <PanelLoading label="Loading compatibility" /> }
);
const PerformancePanel = dynamic(
  () => import("@/components/PerformancePanel").then((module) => module.PerformancePanel),
  { loading: () => <PanelLoading label="Loading performance" /> }
);
const PricingIntelligencePanel = dynamic(
  () => import("@/components/PricingIntelligencePanel").then((module) => module.PricingIntelligencePanel),
  { loading: () => <PanelLoading label="Loading price intelligence" /> }
);
const CatalogCompletenessPanel = dynamic(
  () => import("@/components/CatalogCompletenessPanel").then((module) => module.CatalogCompletenessPanel),
  { loading: () => <PanelLoading label="Loading catalog completeness" /> }
);
const SoloFounderOpsPanel = dynamic(
  () => import("@/components/SoloFounderOpsPanel").then((module) => module.SoloFounderOpsPanel),
  { loading: () => <PanelLoading label="Loading operations" /> }
);
const UserBuildsWorkspace = dynamic(
  () => import("@/components/UserBuildsWorkspace").then((module) => module.UserBuildsWorkspace),
  { loading: () => <PanelLoading label="Loading saved builds" /> }
);

const kindIcon: Record<ComponentKind, string> = {
  CPU: "CPU",
  GPU: "GPU",
  Motherboard: "MB",
  RAM: "RAM",
  Case: "CASE",
  Cooler: "FAN",
  Storage: "SSD",
  PSU: "PSU"
};

function createEmptyOptions(): Record<ComponentKind, ComponentOption[]> {
  return componentOrder.reduce(
    (accumulator, kind) => ({
      ...accumulator,
      [kind]: []
    }),
    {} as Record<ComponentKind, ComponentOption[]>
  );
}

export function BuilderShell() {
  const [state, send] = useMachine(builderMachine);
  const { region, setRegion } = useRegion();
  const [options, setOptions] = useState<Record<ComponentKind, ComponentOption[]>>(createEmptyOptions);
  const [optionError, setOptionError] = useState<string | null>(null);
  const [loadingKind, setLoadingKind] = useState<ComponentKind | null>(null);
  const [toolVisibility, setToolVisibility] = useState({ advanced: false, ops: false });

  const showAdvanced = toolVisibility.advanced;
  const showOps = toolVisibility.ops;
  const selectedCount = Object.values(state.context.selected).filter(Boolean).length;
  const stateLabel = String(state.value).replaceAll("_", " ");
  const compatibility = state.context.validation?.compatibility;
  const performance = state.context.validation?.performance;

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setToolVisibility({
      advanced: params.get("advanced") === "1",
      ops: params.get("ops") === "1"
    });
  }, []);

  useEffect(() => {
    if (state.context.preferences.region !== region) {
      send({ type: "SET_PREFERENCES", preferences: { ...state.context.preferences, region } });
    }
  }, [region, send, state.context.preferences]);

  useEffect(() => {
    let cancelled = false;
    async function loadAllOptions() {
      if (!showAdvanced) {
        setLoadingKind(null);
        setOptionError(null);
        setOptions(createEmptyOptions());
        return;
      }
      setOptionError(null);
      setLoadingKind(componentOrder[0] ?? null);
      const results = await Promise.allSettled(
        componentOrder.map(async (kind) => ({
          kind,
          options: await fetchComponentOptions(kind, state.context.selected, state.context.preferences)
        }))
      );
      if (cancelled) {
        return;
      }
      const nextOptions = createEmptyOptions();
      const failures: string[] = [];
      for (const result of results) {
        if (result.status === "fulfilled") {
          nextOptions[result.value.kind] = result.value.options;
        } else {
          failures.push(result.reason instanceof Error ? result.reason.message : "Unable to load graph candidates.");
        }
      }
      setOptions(nextOptions);
      setOptionError(failures.length ? Array.from(new Set(failures)).join(" ") : null);
      setLoadingKind(null);
    }
    loadAllOptions();
    return () => {
      cancelled = true;
    };
  }, [showAdvanced, state.context.selected, state.context.preferences]);

  const selectedNames = useMemo(() => {
    const names: Record<string, string> = {};
    for (const kind of componentOrder) {
      const selectedId = state.context.selected[selectionKeyByKind[kind]];
      const option = options[kind].find((candidate) => candidate.id === selectedId);
      if (selectedId) names[kind] = option?.name ?? selectedId;
    }
    return names;
  }, [options, state.context.selected]);

  function updatePreferences(preferences: BuildPreferences) {
    if (preferences.region !== region) {
      setRegion(preferences.region);
    }
    send({ type: "SET_PREFERENCES", preferences });
  }

  return (
    <main id="builder" className="min-h-screen">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 py-5 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-3 rounded-lg border border-line bg-white p-4 shadow-tight md:flex-row md:items-center md:justify-between">
          <div>
            <div className="mb-1 text-xs font-semibold uppercase text-signal">Start here</div>
            <h1 className="text-xl font-semibold text-ink">Generate a Saudi build</h1>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted">
              Enter a budget and target resolution. The assistant chooses compatible Saudi-market parts and keeps warnings visible.
            </p>
          </div>
          <RegionSelector />
        </div>

        <SaudiBuildWizard />

        <details id="saved-builds" className="scroll-mt-20 rounded-lg border border-line bg-white p-3 shadow-tight">
          <summary className="cursor-pointer text-base font-semibold text-ink">Saved builds and price watchlist</summary>
          <div className="mt-4">
            <UserBuildsWorkspace />
          </div>
        </details>

        {showAdvanced ? (
          <details className="rounded-lg border border-line bg-white p-3 shadow-tight" open>
          <summary className="cursor-pointer text-base font-semibold text-ink">
            Advanced graph builder tools ({stateLabel}, {selectedCount}/8 selected)
          </summary>
            <div className="mt-4 grid gap-4">
              <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
                <PreferencePanel preferences={state.context.preferences} onChange={updatePreferences} />
                <div className="grid gap-4">
                <AutoBuildGenerator
                  budget={state.context.preferences.budget_usd}
                  response={state.context.generatedBuilds}
                  error={state.context.buildError}
                  generating={state.matches("generating_build")}
                  onGenerate={() => send({ type: "GENERATE_BUILD" })}
                  onApply={(selection) => send({ type: "APPLY_GENERATED_BUILD", selection })}
                />
                </div>
              </div>

                <div className="rounded-lg border border-line bg-white p-3">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <h2 className="text-base font-semibold text-ink">Graph-filtered selectors</h2>
                    <button
                      type="button"
                      onClick={() => send({ type: "RESET" })}
                      className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-line bg-panel text-ink hover:bg-white"
                      aria-label="Reset builder"
                      title="Reset builder"
                    >
                      <RotateCcw size={16} aria-hidden />
                    </button>
                  </div>
                  {optionError ? (
                    <div className="mb-3 rounded-md border border-caution/40 bg-amber-50 px-3 py-2 text-sm text-caution">
                      {optionError}
                    </div>
                  ) : null}
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    {componentOrder.map((kind) => (
                      <ComponentSelector
                        key={kind}
                        kind={kind}
                        iconText={kindIcon[kind]}
                        options={options[kind]}
                        selectedId={state.context.selected[selectionKeyByKind[kind]]}
                        loading={loadingKind === kind}
                        onSelect={(componentId) => send({ type: "SELECT_COMPONENT", kind, componentId })}
                      />
                    ))}
                  </div>
                </div>

                <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
                  <CompatibilityPanel
                    response={compatibility ?? null}
                    error={state.context.error}
                    selectedNames={selectedNames}
                    validating={state.matches("validating")}
                  />
                  <PerformancePanel response={performance ?? null} validating={state.matches("validating")} />
                </div>
            </div>
          </details>
        ) : null}

        {showOps ? (
          <details className="rounded-lg border border-line bg-white p-3 shadow-tight" open>
            <summary className="cursor-pointer text-base font-semibold text-ink">Founder operations and market data tools</summary>
            <div className="mt-4 grid gap-4">
              <CatalogCompletenessPanel />
              <SoloFounderOpsPanel />
              <PricingIntelligencePanel />
            </div>
          </details>
        ) : null}
      </div>
    </main>
  );
}

function PanelLoading({ label }: { label: string }) {
  return (
    <div className="rounded-md border border-line bg-panel px-3 py-2 text-sm text-muted">
      {label}...
    </div>
  );
}
