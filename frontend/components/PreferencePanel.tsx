"use client";

import { SlidersHorizontal } from "lucide-react";
import { MARKET_REGIONS } from "@/lib/region";
import type { BuildPreferences, CaseSize, NoisePreference, Purpose, Resolution } from "@/types/builder";

export function PreferencePanel({
  preferences,
  onChange
}: {
  preferences: BuildPreferences;
  onChange: (preferences: BuildPreferences) => void;
}) {
  return (
    <aside className="rounded-lg border border-line bg-white p-4 shadow-tight">
      <div className="mb-4 flex items-center gap-2">
        <SlidersHorizontal size={18} className="text-signal" aria-hidden />
        <h2 className="text-base font-semibold text-ink">Build targets</h2>
      </div>

      <div className="grid gap-4">
        <label className="grid gap-1 text-sm font-medium text-ink">
          Budget
          <input
            type="number"
            min={0}
            value={preferences.budget_usd ?? ""}
            onChange={(event) =>
              onChange({ ...preferences, budget_usd: event.target.value ? Number(event.target.value) : undefined })
            }
            className="h-10 rounded-md border border-line px-3"
            placeholder="1500"
          />
        </label>

        <SelectField
          label="Purpose"
          value={preferences.purpose}
          options={["gaming", "simulation", "workstation"]}
          onChange={(purpose) => onChange({ ...preferences, purpose: purpose as Purpose })}
        />

        <SelectField
          label="Resolution"
          value={preferences.resolution}
          options={["1080p", "1440p", "4K"]}
          onChange={(resolution) => onChange({ ...preferences, resolution: resolution as Resolution })}
        />

        <SelectField
          label="Refresh target"
          value={String(preferences.display_refresh_hz ?? 144)}
          options={["60", "120", "144", "165", "240"]}
          onChange={(refresh) => onChange({ ...preferences, display_refresh_hz: Number(refresh) })}
        />

        <SelectField
          label="Pricing region"
          value={preferences.region}
          options={MARKET_REGIONS.map((region) => region.code)}
          onChange={(region) => onChange({ ...preferences, region })}
        />

        <SelectField
          label="Case size"
          value={preferences.size ?? ""}
          options={["", "ITX", "mATX", "ATX", "EATX"]}
          onChange={(size) => onChange({ ...preferences, size: size ? (size as CaseSize) : undefined })}
        />

        <fieldset className="grid gap-2 text-sm font-medium text-ink">
          <legend>Brand bias</legend>
          <div className="grid grid-cols-3 gap-2">
            {["Intel", "AMD", "NVIDIA"].map((brand) => {
              const active = preferences.brand_bias.includes(brand);
              return (
                <label
                  key={brand}
                  className="flex items-center gap-2 rounded-md border border-line bg-panel px-2 py-2 text-xs"
                >
                  <input
                    type="checkbox"
                    checked={active}
                    onChange={() =>
                      onChange({
                        ...preferences,
                        brand_bias: active
                          ? preferences.brand_bias.filter((item) => item !== brand)
                          : [...preferences.brand_bias, brand]
                      })
                    }
                    className="accent-signal"
                  />
                  {brand}
                </label>
              );
            })}
          </div>
        </fieldset>

        <SelectField
          label="Noise"
          value={preferences.noise_preference}
          options={["quiet", "balanced", "performance"]}
          onChange={(noise) => onChange({ ...preferences, noise_preference: noise as NoisePreference })}
        />

        <label className="grid gap-2 text-sm font-medium text-ink">
          Upgrade path priority
          <input
            type="range"
            min={0}
            max={10}
            value={preferences.upgrade_path_priority}
            onChange={(event) =>
              onChange({ ...preferences, upgrade_path_priority: Number(event.target.value) })
            }
            className="accent-signal"
          />
          <span className="text-xs text-slate-600">{preferences.upgrade_path_priority}/10</span>
        </label>
      </div>
    </aside>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1 text-sm font-medium text-ink">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 rounded-md border border-line bg-white px-3 capitalize"
      >
        {options.map((option) => (
          <option key={option || "any"} value={option}>
            {option || "Any"}
          </option>
        ))}
      </select>
    </label>
  );
}
