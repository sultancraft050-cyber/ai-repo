export type MarketRegionCode = "SA" | "AE" | "US" | "EU" | "UK";

export type MarketRegionOption = {
  code: MarketRegionCode;
  label: string;
  countryName: string;
  currency: string;
  defaultCity?: string;
};

export const DEFAULT_REGION: MarketRegionCode = "SA";
export const REGION_COOKIE = "market_region";
export const REGION_STORAGE_KEY = "market_region";

export const MARKET_REGIONS: MarketRegionOption[] = [
  { code: "SA", label: "Saudi Arabia", countryName: "Saudi Arabia", currency: "SAR", defaultCity: "Riyadh" },
  { code: "AE", label: "United Arab Emirates", countryName: "United Arab Emirates", currency: "AED", defaultCity: "Dubai" },
  { code: "US", label: "United States", countryName: "United States", currency: "USD" },
  { code: "EU", label: "Europe", countryName: "Europe", currency: "EUR", defaultCity: "Berlin" },
  { code: "UK", label: "United Kingdom", countryName: "United Kingdom", currency: "GBP", defaultCity: "London" }
];

const REGION_CODES = new Set(MARKET_REGIONS.map((region) => region.code));

export function normalizeRegion(value?: string | null): MarketRegionCode {
  const candidate = (value ?? DEFAULT_REGION).trim().toUpperCase();
  if (candidate === "GB") return "UK";
  return REGION_CODES.has(candidate as MarketRegionCode) ? (candidate as MarketRegionCode) : DEFAULT_REGION;
}

export function getRegionOption(value?: string | null): MarketRegionOption {
  const code = normalizeRegion(value);
  return MARKET_REGIONS.find((region) => region.code === code) ?? MARKET_REGIONS[0];
}

export function persistRegion(region: MarketRegionCode) {
  if (typeof document !== "undefined") {
    document.cookie = `${REGION_COOKIE}=${region}; path=/; max-age=31536000; samesite=lax`;
  }
  if (typeof window !== "undefined") {
    window.localStorage.setItem(REGION_STORAGE_KEY, region);
  }
}

export function readStoredRegion(): MarketRegionCode | null {
  if (typeof window === "undefined") return null;
  const localValue = window.localStorage.getItem(REGION_STORAGE_KEY);
  return localValue ? normalizeRegion(localValue) : null;
}
