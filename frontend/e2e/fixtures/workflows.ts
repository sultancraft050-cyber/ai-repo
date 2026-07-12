export const categories = ["CPU", "GPU", "RAM", "Motherboard", "Storage", "PSU", "Case", "Cooler"] as const;

export function product(category: string, suffix = "001", overrides: Record<string, unknown> = {}) {
  return {
    id: `fixture-${category.toLowerCase()}-${suffix}`,
    name: `Fixture ${category} ${suffix}`,
    brand: "Fixture Labs",
    category,
    summary_specs: { socket: category === "CPU" ? "AM5" : undefined, memory_type: category === "RAM" ? "DDR5" : undefined },
    cheapest_vendor: "Fixture Saudi Store",
    cheapest_price_sar: 500 + categories.indexOf(category as (typeof categories)[number]) * 100,
    current_recommended_vendor: "Fixture Saudi Store",
    current_recommended_price: 500 + categories.indexOf(category as (typeof categories)[number]) * 100,
    catalog_state: "saudi_priced",
    compatibility_ready: true,
    compatibility_ready_exact: true,
    readiness_state: "compatibility_ready_exact",
    data_origin: "canonical",
    price_status: "available",
    flags: [],
    region: "SA",
    region_currency: "SAR",
    stale: false,
    best_value: suffix === "001",
    ...overrides,
  };
}

export const completeness = {
  region: "SA", city: "Riyadh", readiness_score: 1, required_categories: [...categories], ready_categories: [...categories],
  missing_categories: [], category_coverage: [], recommended_discovery_jobs: [], enough_data_for_full_build: true,
  message: "Synthetic fixture data is ready.",
};

const components = categories.map((category, index) => ({
  product_id: `fixture-${category.toLowerCase()}-001`, name: `Fixture ${category} 001`, category,
  recommended_vendor: "Fixture Saudi Store", recommended_price_sar: 500 + index * 100, lowest_market_price_sar: 500 + index * 100,
  price_confidence: 0.95, stock_badge: "local", vat_status: "included", shipping_status: "local", warranty_status: "known",
  reason_selected: "Deterministic fixture choice", alternatives: [], warnings: [],
}));

export const generatedBuild = {
  region: "SA", city: "Riyadh", build_status: "ready", data_completeness: completeness, recommended_discovery_jobs: [], missing_data_warnings: [],
  build_comparison: [],
  builds: [{
    label: "recommended_saudi_build", title: "Fixture Saudi Build", components,
    summary: { total_recommended_price_sar: 6800, total_lowest_possible_price_sar: 6800, budget_sar: 7000, budget_delta_sar: 200,
      over_budget_amount_sar: 0, over_budget_percent: 0, budget_status: "under_budget", most_expensive_components: ["GPU"],
      easiest_savings_opportunities: [], compatibility_status: "valid", performance_estimate: "Fixture 1440p target", bottleneck_summary: "Balanced",
      risk_summary: [], data_completeness_score: 1, warning_summary: [], components_with_uncertainty: [], confidence_level: "high",
      confidence_score: 0.95, missing_data_warnings: [] },
    explanation: { build_id: "fixture-build-001", build_mode: "recommended_saudi_build", confidence_level: "high", summary: "Synthetic fixture build.",
      strengths: ["Local pricing"], weaknesses: [], risks: [], budget_analysis: "Under budget", upgrade_path: [], future_limitations: [],
      recommended_purchase_order: [], component_explanations: [] },
    confidence_breakdown: { compatibility_confidence: .95, market_confidence: .95, vendor_confidence: .95, pricing_confidence: .95, shipping_confidence: .95, warranty_confidence: .95, overall_confidence: .95 },
    savings_suggestions: [], comparison_metrics: { label: "recommended_saudi_build", title: "Fixture Saudi Build", total_price_sar: 6800,
      budget_status: "under_budget", risk_level: "low", confidence_score: .95, local_availability_summary: "Local", upgrade_path_summary: "Available", cheapest_option: true, safest_option: true },
    export: { shareable_build_url: "", json_summary: {}, markdown_summary: "Fixture Saudi Build", printable_summary: "Fixture Saudi Build" },
    why_this_build: "Deterministic fixture", upgrade_notes: [],
  }],
};

export const savedBuild = {
  build_id: "fixture-saved-001", title: "Fixture Shared Saudi Build", region: "SA", created_at: "2026-07-12T00:00:00Z",
  build_mode: "recommended_saudi_build", total_price_sar: 6800, confidence_level: "high", warning_summary: [],
  component_ids: components.map((item) => item.product_id), price_snapshot_ids: [], build_summary: generatedBuild.builds[0].summary,
  build_payload: generatedBuild.builds[0], share_slug: "fixture-share-001", public_visibility: true, favorite: false,
};
