"use client";

import { CheckCircle2, Loader2, TriangleAlert } from "lucide-react";
import type { CompatibilityResponse } from "@/types/builder";

export function CompatibilityPanel({
  response,
  error,
  selectedNames,
  validating
}: {
  response: CompatibilityResponse | null;
  error: string | null;
  selectedNames: Record<string, string>;
  validating: boolean;
}) {
  return (
    <section className="rounded-lg border border-line bg-white p-4 shadow-tight">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-ink">Compatibility constraints</h2>
          <p className="text-sm text-slate-600">Socket, memory, power, PCIe, USB, and physical-space checks.</p>
        </div>
        {validating ? <Loader2 size={20} className="animate-spin text-signal" aria-label="Validating" /> : null}
      </div>

      {error ? (
        <div className="rounded-md border border-danger/30 bg-red-50 px-3 py-2 text-sm text-danger">
          {error}
        </div>
      ) : null}

      <div className="mb-4 grid gap-2 sm:grid-cols-2">
        {Object.entries(selectedNames).map(([kind, name]) => (
          <div key={kind} className="rounded-md border border-line bg-panel px-3 py-2">
            <div className="text-xs font-semibold uppercase text-slate-500">{kind}</div>
            <div className="truncate text-sm font-medium text-ink">{name}</div>
          </div>
        ))}
      </div>

      {!response ? (
        <div className="rounded-md border border-line bg-panel px-3 py-6 text-sm text-slate-600">
          Select graph-backed components to start deterministic validation.
        </div>
      ) : (
        <div className="grid gap-2">
          {response.checks.map((check) => (
            <div key={check.id} className="rounded-md border border-line bg-panel p-3">
              <div className="mb-1 flex items-center gap-2">
                {check.status === "pass" ? (
                  <CheckCircle2 size={17} className="text-signal" aria-hidden />
                ) : (
                  <TriangleAlert
                    size={17}
                    className={check.status === "fail" ? "text-danger" : "text-caution"}
                    aria-hidden
                  />
                )}
                <h3 className="text-sm font-semibold text-ink">{check.label}</h3>
              </div>
              <p className="text-sm leading-5 text-slate-700">{check.details}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

