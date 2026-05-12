"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import dynamic from "next/dynamic";
import { useMachine } from "@xstate/react";
import { Activity, Cpu, Database, RotateCcw, ShieldCheck, TriangleAlert } from "lucide-react";
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

  const selectedCount = Object.values(state.context.selected).filter(Boolean).length;
  const stateLabel = String(state.value).replaceAll("_", " ");
  const compatibility = state.context.validation?.compatibility;
  const performance = state.context.validation?.performance;

  useEffect(() => {
    if (state.context.preferences.region !== region) {
      send({ type: "SET_PREFERENCES", preferences: { ...state.context.preferences, region } });
    }
  }, [region, send, state.context.preferences]);

  useEffect(() => {
    let cancelled = false;
    async function loadAllOptions() {
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
  }, [state.context.selected, state.context.preferences]);

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
    <main className="min-h-screen">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 px-4 py-4 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 border-b border-line pb-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.08em] text-signal">
              <Database size={16} aria-hidden />
              Neo4j constraint graph active
            </div>
            <h1 className="text-3xl font-semibold leading-tight text-ink sm:text-4xl">
              Custom PC Compatibility Intelligence
            </h1>
          </div>
          <div className="grid gap-2 text-sm sm:grid-cols-[auto_auto_auto] lg:grid-cols-[minmax(190px,auto)_auto_auto_auto]">
            <RegionSelector />
            <StatusChip icon={<Activity size={16} />} label="State" value={stateLabel} tone="signal" />
            <StatusChip icon={<Cpu size={16} />} label="Selected" value={`${selectedCount}/8`} tone="violet" />
            <StatusChip
              icon={compatibility?.valid ? <ShieldCheck size={16} /> : <TriangleAlert size={16} />}
              label="Graph"
              value={compatibility?.state.replaceAll("_", " ") ?? "pending"}
              tone={compatibility?.valid ? "signal" : "caution"}
            />
          </div>
        </header>

        <section className="grid gap-4 lg:grid-cols-[320px_1fr]">
          <PreferencePanel preferences={state.context.preferences} onChange={updatePreferences} />

          <div className="grid gap-4">
            <SaudiBuildWizard />
            <UserBuildsWorkspace />

            <details className="rounded-lg border border-line bg-white p-3 shadow-tight">
              <summary className="cursor-pointer text-base font-semibold text-ink">Manual graph builder tools</summary>
              <div className="mt-4 grid gap-4">
                <AutoBuildGenerator
                  budget={state.context.preferences.budget_usd}
                  response={state.context.generatedBuilds}
                  error={state.context.buildError}
                  generating={state.matches("generating_build")}
                  onGenerate={() => send({ type: "GENERATE_BUILD" })}
                  onApply={(selection) => send({ type: "APPLY_GENERATED_BUILD", selection })}
                />

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

            <details className="rounded-lg border border-line bg-white p-3 shadow-tight">
              <summary className="cursor-pointer text-base font-semibold text-ink">Founder operations and market data tools</summary>
              <div className="mt-4 grid gap-4">
                <CatalogCompletenessPanel />
                <SoloFounderOpsPanel />
                <PricingIntelligencePanel />
              </div>
            </details>
          </div>
        </section>
      </div>
    </main>
  );
}

function StatusChip({
  icon,
  label,
  value,
  tone
}: {
  icon: ReactNode;
  label: string;
  value: string;
  tone: "signal" | "violet" | "caution";
}) {
  const color = tone === "signal" ? "text-signal" : tone === "violet" ? "text-violet" : "text-caution";
  return (
    <div className="min-w-0 rounded-md border border-line bg-white px-3 py-2 shadow-tight">
      <div className={`mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase ${color}`}>
        {icon}
        <span>{label}</span>
      </div>
      <div className="truncate text-sm font-medium capitalize text-ink">{value}</div>
    </div>
  );
}

function PanelLoading({ label }: { label: string }) {
  return (
    <div className="rounded-md border border-line bg-panel px-3 py-2 text-sm text-muted">
      {label}...
    </div>
  );
}
