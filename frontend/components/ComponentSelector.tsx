"use client";

import { Loader2 } from "lucide-react";
import type { ComponentKind, ComponentOption } from "@/types/builder";

export function ComponentSelector({
  kind,
  iconText,
  options,
  selectedId,
  loading,
  onSelect
}: {
  kind: ComponentKind;
  iconText: string;
  options: ComponentOption[];
  selectedId?: string;
  loading: boolean;
  onSelect: (componentId: string) => void;
}) {
  return (
    <label className="block rounded-md border border-line bg-panel p-3">
      <span className="mb-2 flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-ink">{kind}</span>
        <span className="inline-flex h-7 min-w-7 items-center justify-center rounded bg-white px-1.5 text-[11px] font-bold text-signal">
          {loading ? <Loader2 size={14} className="animate-spin" aria-hidden /> : iconText}
        </span>
      </span>
      <select
        value={selectedId ?? ""}
        onChange={(event) => {
          if (event.target.value) onSelect(event.target.value);
        }}
        className="h-10 w-full rounded-md border border-line bg-white px-2 text-sm text-ink"
        aria-label={`Select ${kind}`}
        disabled={loading || options.length === 0}
      >
        <option value="">{loading ? "Loading graph candidates" : "Select component"}</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
            {option.price_usd ? ` - $${option.price_usd}` : ""}
          </option>
        ))}
      </select>
      <div className="mt-2 min-h-10 text-xs leading-5 text-slate-600">
        {selectedId
          ? options.find((option) => option.id === selectedId)?.summary ?? selectedId
          : options.length === 0 && !loading
            ? "Waiting for Neo4j candidates."
            : `${options.length} candidate${options.length === 1 ? "" : "s"}`}
      </div>
    </label>
  );
}

