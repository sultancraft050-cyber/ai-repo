"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useMachine } from "@xstate/react";
import { Activity, Cpu, Database, RotateCcw, ShieldCheck, TriangleAlert } from "lucide-react";
import { builderMachine } from "@/machines/builderMachine";
import { fetchComponentOptions } from "@/lib/api";
import {
  componentOrder,
  selectionKeyByKind,
  type BuildPreferences,
  type ComponentKind,
  type ComponentOption
} from "@/types/builder";
import { ComponentSelector } from "@/components/ComponentSelector";
import { AdminOperationsPanel } from "@/components/AdminOperationsPanel";
import { AutoBuildGenerator } from "@/components/AutoBuildGenerator";
import { CompatibilityPanel } from "@/components/CompatibilityPanel";
import { PerformancePanel } from "@/components/PerformancePanel";
import { PreferencePanel } from "@/components/PreferencePanel";
import { PricingIntelligencePanel } from "@/components/PricingIntelligencePanel";

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
  const [options, setOptions] = useState<Record<ComponentKind, ComponentOption[]>>(createEmptyOptions);
  const [optionError, setOptionError] = useState<string | null>(null);
  const [loadingKind, setLoadingKind] = useState<ComponentKind | null>(null);

  const selectedCount = Object.values(state.context.selected).filter(Boolean).length;
  const stateLabel = String(state.value).replaceAll("_", " ");
  const compatibility = state.context.validation?.compatibility;
  const performance = state.context.validation?.performance;

  useEffect(() => {
    let cancelled = false;
    async function loadAllOptions() {
      setOptionError(null);
      for (const kind of componentOrder) {
        setLoadingKind(kind);
        try {
          const result = await fetchComponentOptions(kind, state.context.selected, state.context.preferences);
          if (!cancelled) {
            setOptions((current) => ({ ...current, [kind]: result }));
          }
        } catch (error) {
          if (!cancelled) {
            setOptions((current) => ({ ...current, [kind]: [] }));
            setOptionError(error instanceof Error ? error.message : "Unable to load graph candidates.");
          }
        }
      }
      if (!cancelled) setLoadingKind(null);
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
          <div className="grid grid-cols-3 gap-2 text-sm">
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
            <AutoBuildGenerator
              budget={state.context.preferences.budget_usd}
              response={state.context.generatedBuilds}
              error={state.context.buildError}
              generating={state.matches("generating_build")}
              onGenerate={() => send({ type: "GENERATE_BUILD" })}
              onApply={(selection) => send({ type: "APPLY_GENERATED_BUILD", selection })}
            />

            <AdminOperationsPanel />

            <PricingIntelligencePanel region={state.context.preferences.region} />

            <div className="rounded-lg border border-line bg-white p-3 shadow-tight">
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
