import type {
  BuildPreferences,
  BuildGenerateResponse,
  AlignmentInspectionReport,
  AutonomousCognitionReport,
  ApprovalItem,
  CompatibilityResponse,
  ComponentKind,
  ComponentOption,
  DailyFounderReport,
  EvolutionOrchestrationReport,
  PerformanceResponse,
  PriceHistoryPoint,
  PriceSnapshotView,
  PricingRefreshResponse,
  ProductCategoryResponse,
  ProductDiscoveryResponse,
  ProductCategory,
  HardwareCognitionReport,
  HardwareIntelligence,
  ProductSearchResult,
  ReasoningGovernanceReport,
  SelectedComponents,
  TelemetryReasoningReport,
  TelemetrySummary,
  ValidationBundle
} from "@/types/builder";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type ApiErrorBody = {
  detail?: string;
  error?: string;
};

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    cache: "no-store"
  });
  if (!response.ok) {
    let body: ApiErrorBody = {};
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      body = {};
    }
    throw new Error(body.detail ?? body.error ?? `Request failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

function authHeaders(apiKey: string): Record<string, string> {
  return apiKey ? { "X-API-Key": apiKey } : {};
}

export async function fetchComponentOptions(
  kind: ComponentKind,
  selection: SelectedComponents,
  preferences: BuildPreferences
): Promise<ComponentOption[]> {
  const params = new URLSearchParams({
    kind,
    purpose: preferences.purpose,
    resolution: preferences.resolution
  });
  Object.entries(selection).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  const result = await requestJson<{ options: ComponentOption[] }>(`/components/options?${params.toString()}`);
  return result.options;
}

export async function searchProducts({
  query,
  category,
  region,
  limit = 12
}: {
  query?: string;
  category?: ProductCategory | "";
  region?: string;
  limit?: number;
}): Promise<ProductSearchResult[]> {
  const params = new URLSearchParams({
    q: query ?? "",
    limit: String(limit)
  });
  if (category) params.set("category", category);
  if (region) params.set("region", region);
  return requestJson<ProductSearchResult[]>(`/products/search?${params.toString()}`);
}

export async function fetchProductCategories(): Promise<ProductCategoryResponse> {
  return requestJson<ProductCategoryResponse>("/products/categories");
}

export async function fetchProductPrices(productId: string, region?: string): Promise<PriceSnapshotView[]> {
  const params = new URLSearchParams();
  if (region) params.set("region", region);
  return requestJson<PriceSnapshotView[]>(`/products/${productId}/prices?${params.toString()}`);
}

export async function fetchProductHistory(productId: string, region?: string): Promise<PriceHistoryPoint[]> {
  const params = new URLSearchParams({ limit: "60" });
  if (region) params.set("region", region);
  return requestJson<PriceHistoryPoint[]>(`/products/${productId}/history?${params.toString()}`);
}

export async function fetchProductIntelligence(productId: string): Promise<HardwareIntelligence> {
  return requestJson<HardwareIntelligence>(`/intelligence/products/${productId}`);
}

export async function fetchTelemetrySummary(productId: string): Promise<TelemetrySummary> {
  return requestJson<TelemetrySummary>(`/telemetry/products/${productId}/summary`);
}

export async function fetchTelemetryReasoning(productId: string): Promise<TelemetryReasoningReport> {
  return requestJson<TelemetryReasoningReport>(`/telemetry/products/${productId}/reasoning`);
}

export async function fetchCognitionReport(productId: string): Promise<HardwareCognitionReport> {
  return requestJson<HardwareCognitionReport>(`/cognition/products/${productId}?refresh=true&persist=true`);
}

export async function fetchGovernanceReport(productId: string): Promise<ReasoningGovernanceReport> {
  return requestJson<ReasoningGovernanceReport>(`/governance/products/${productId}?refresh=true&persist=true`);
}

export async function fetchEvolutionReport(productId: string): Promise<EvolutionOrchestrationReport> {
  return requestJson<EvolutionOrchestrationReport>(`/evolution/products/${productId}?refresh=true&persist=true`);
}

export async function fetchAlignmentReport(productId: string): Promise<AlignmentInspectionReport> {
  return requestJson<AlignmentInspectionReport>(`/alignment/products/${productId}?refresh=true&persist=true`);
}

export async function fetchAutonomyReport(productId: string): Promise<AutonomousCognitionReport> {
  return requestJson<AutonomousCognitionReport>(`/autonomy/products/${productId}?refresh=true&persist=true`);
}

export async function fetchDailyFounderReport(apiKey: string): Promise<DailyFounderReport> {
  return requestJson<DailyFounderReport>("/ops/daily-report", {
    headers: authHeaders(apiKey)
  });
}

export async function fetchPendingApprovals(apiKey: string): Promise<ApprovalItem[]> {
  return requestJson<ApprovalItem[]>("/approvals/pending", {
    headers: authHeaders(apiKey)
  });
}

export async function approveItem(apiKey: string, approvalId: string, note?: string): Promise<{ approval: ApprovalItem }> {
  return requestJson<{ approval: ApprovalItem }>(`/approvals/${approvalId}/approve`, {
    method: "POST",
    headers: {
      ...authHeaders(apiKey),
      "X-Idempotency-Key": `approval-approve-${approvalId}`
    },
    body: JSON.stringify({ note })
  });
}

export async function rejectItem(apiKey: string, approvalId: string, note?: string): Promise<{ approval: ApprovalItem }> {
  return requestJson<{ approval: ApprovalItem }>(`/approvals/${approvalId}/reject`, {
    method: "POST",
    headers: {
      ...authHeaders(apiKey),
      "X-Idempotency-Key": `approval-reject-${approvalId}`
    },
    body: JSON.stringify({ note })
  });
}

export async function enrichProducts(productIds: string[]): Promise<{ enriched_count: number; skipped_count: number }> {
  return requestJson<{ enriched_count: number; skipped_count: number }>("/intelligence/enrich", {
    method: "POST",
    body: JSON.stringify({
      product_ids: productIds,
      limit: Math.max(productIds.length, 1),
      persist: true
    })
  });
}

export async function refreshPricing(productIds: string[], region: string): Promise<PricingRefreshResponse> {
  return requestJson<PricingRefreshResponse>("/pricing/refresh", {
    method: "POST",
    body: JSON.stringify({
      product_ids: productIds,
      region,
      wait: false
    })
  });
}

export async function discoverProducts({
  categories,
  query,
  region
}: {
  categories: string[];
  query?: string;
  region: string;
}): Promise<ProductDiscoveryResponse> {
  return requestJson<ProductDiscoveryResponse>("/pricing/discover", {
    method: "POST",
    body: JSON.stringify({
      categories,
      query: query || undefined,
      region,
      limit_per_query: 8,
      max_queries: 12,
      wait: false
    })
  });
}

export async function checkCompatibility(
  selection: SelectedComponents,
  preferences: BuildPreferences
): Promise<CompatibilityResponse> {
  return requestJson<CompatibilityResponse>("/compatibility/check", {
    method: "POST",
    body: JSON.stringify({ selection, preferences, qvl_required: true })
  });
}

export async function calculatePerformance(
  selection: SelectedComponents,
  preferences: BuildPreferences
): Promise<PerformanceResponse> {
  return requestJson<PerformanceResponse>("/api/performance/calculate", {
    method: "POST",
    body: JSON.stringify({ selection, preferences, display_refresh_hz: 144 })
  });
}

export async function validateAndMeasure(
  selection: SelectedComponents,
  preferences: BuildPreferences
): Promise<ValidationBundle> {
  const compatibility = await checkCompatibility(selection, preferences);
  const performance =
    selection.cpu_id && selection.gpu_id ? await calculatePerformance(selection, preferences) : null;
  return { compatibility, performance };
}

export async function generateBuild(preferences: BuildPreferences): Promise<BuildGenerateResponse> {
  return requestJson<BuildGenerateResponse>("/build/generate", {
    method: "POST",
    body: JSON.stringify({
      budget_usd: preferences.budget_usd ?? 1500,
      purpose: preferences.purpose,
      resolution: preferences.resolution,
      preferences,
      max_candidates_per_type: 120
    })
  });
}
