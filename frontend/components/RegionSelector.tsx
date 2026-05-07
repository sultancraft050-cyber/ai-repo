"use client";

import { Globe2 } from "lucide-react";
import { MARKET_REGIONS } from "@/lib/region";
import { useRegion } from "@/components/RegionProvider";

export function RegionSelector() {
  const { region, regionOption, setRegion } = useRegion();
  return (
    <label className="grid gap-1 text-xs font-semibold uppercase text-slate-500">
      Market
      <span className="relative block">
        <Globe2 size={15} className="pointer-events-none absolute left-3 top-3 text-signal" aria-hidden />
        <select
          value={region}
          onChange={(event) => setRegion(event.target.value)}
          className="h-10 min-w-52 rounded-md border border-line bg-white pl-9 pr-3 text-sm font-medium normal-case text-ink"
          aria-label="Selected market region"
        >
          {MARKET_REGIONS.map((option) => (
            <option key={option.code} value={option.code}>
              {option.label}
            </option>
          ))}
        </select>
      </span>
      <span className="normal-case text-slate-500">{regionOption.currency} pricing context</span>
    </label>
  );
}
