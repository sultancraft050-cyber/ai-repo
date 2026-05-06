"use client";

import { BarChart3, Gauge, Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import type { PerformanceResponse } from "@/types/builder";

export function PerformancePanel({
  response,
  validating
}: {
  response: PerformanceResponse | null;
  validating: boolean;
}) {
  return (
    <section className="rounded-lg border border-line bg-white p-4 shadow-tight">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-ink">Performance model</h2>
          <p className="text-sm text-slate-600">NumPy estimate from graph benchmark vectors.</p>
        </div>
        {validating ? <Loader2 size={20} className="animate-spin text-signal" aria-label="Calculating" /> : null}
      </div>

      {!response ? (
        <div className="rounded-md border border-line bg-panel px-3 py-6 text-sm text-slate-600">
          CPU and GPU selections unlock FPS, variance, and bottleneck telemetry.
        </div>
      ) : (
        <div className="grid gap-4">
          <div className="grid grid-cols-2 gap-3">
            <Metric icon={<Gauge size={18} />} label="Expected FPS" value={response.expected_fps.toFixed(1)} />
            <Metric icon={<BarChart3 size={18} />} label="1% low" value={response.one_percent_low_fps.toFixed(1)} />
            <Metric label="Frame time" value={`${response.frame_time_ms.toFixed(2)} ms`} />
            <Metric label="Variance" value={`${response.frame_time_variance_ms.toFixed(2)} ms`} />
          </div>

          <div className="grid gap-3">
            <BottleneckBar label="CPU" value={response.bottleneck.cpu_percent} color="bg-signal" />
            <BottleneckBar label="GPU" value={response.bottleneck.gpu_percent} color="bg-violet" />
            <BottleneckBar label="Memory" value={response.bottleneck.memory_percent} color="bg-caution" />
            <BottleneckBar label="Display" value={response.bottleneck.display_percent} color="bg-ink" />
          </div>

          <div className="rounded-md border border-line bg-panel p-3">
            <div className="mb-1 text-xs font-semibold uppercase text-slate-500">
              Confidence: {response.confidence}
            </div>
            <ul className="grid gap-1 text-sm leading-5 text-slate-700">
              {response.reasoning.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}

function Metric({ icon, label, value }: { icon?: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-panel p-3">
      <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase text-slate-500">
        {icon}
        {label}
      </div>
      <div className="text-xl font-semibold text-ink">{value}</div>
    </div>
  );
}

function BottleneckBar({ label, value, color }: { label: string; value: number; color: string }) {
  const width = Math.max(0, Math.min(100, value));
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="font-medium text-ink">{label}</span>
        <span className="text-slate-600">{value.toFixed(1)}%</span>
      </div>
      <div className="h-2 rounded bg-slate-200">
        <div className={`h-2 rounded ${color}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}
