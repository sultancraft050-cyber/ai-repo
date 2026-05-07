"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  DEFAULT_REGION,
  getRegionOption,
  normalizeRegion,
  persistRegion,
  readStoredRegion,
  type MarketRegionCode,
  type MarketRegionOption
} from "@/lib/region";

type RegionContextValue = {
  region: MarketRegionCode;
  regionOption: MarketRegionOption;
  setRegion: (region: string) => void;
};

const RegionContext = createContext<RegionContextValue | null>(null);

export function RegionProvider({
  initialRegion,
  children
}: {
  initialRegion?: string | null;
  children: ReactNode;
}) {
  const [region, setRegionState] = useState<MarketRegionCode>(() => normalizeRegion(initialRegion ?? DEFAULT_REGION));

  useEffect(() => {
    const stored = readStoredRegion();
    if (stored && stored !== region) {
      setRegionState(stored);
      persistRegion(stored);
    } else {
      persistRegion(region);
    }
  }, []);

  const value = useMemo<RegionContextValue>(
    () => ({
      region,
      regionOption: getRegionOption(region),
      setRegion: (nextRegion: string) => {
        const normalized = normalizeRegion(nextRegion);
        setRegionState(normalized);
        persistRegion(normalized);
      }
    }),
    [region]
  );

  return <RegionContext.Provider value={value}>{children}</RegionContext.Provider>;
}

export function useRegion() {
  const context = useContext(RegionContext);
  if (!context) {
    throw new Error("useRegion must be used inside RegionProvider");
  }
  return context;
}
