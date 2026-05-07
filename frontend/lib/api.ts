import type {
  BuildPreferences,
  BuildGenerateResponse,
  AlignmentInspectionReport,
  AutonomousCognitionReport,
  AutonomyQueue,
  ApprovalItem,
  CompatibilityResponse,
  ComponentKind,
  ComponentOption,
  CanonicalMergePreviewRequest,
  CanonicalMergePreviewResponse,
  CpuDuplicateReport,
  DailyFounderReport,
  EvolutionOrchestrationReport,
  PerformanceResponse,
  PriceHistoryPoint,
  PriceSnapshotView,
  KnownProductUrlView,
  ProductUrlIngestResponse,
  ProductUrlPreviewRequest,
  ProductUrlPreviewResponse,
  ProductUrlRefreshResponse,
  PricingRefreshResponse,
  ProductCategoryResponse,
  ProductDiscoveryResponse,
  ProductCategory,
  HardwareCognitionReport,
  HardwareIntelligence,
  ProductSearchResult,
  ReasoningGovernanceReport,
  SaudiBuildDataCompleteness,
  SaudiBuildRequest,
  SaudiBuildResponse,
  SaudiBuildValidationRequest,
  SaudiBuildValidationResponse,
  SourceConfigStatus,
  SourceMatrixEntry,
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

export async function fetchDailyFounderReport(apiKey: string, region?: string): Promise<DailyFounderReport> {
  const params = new URLSearchParams();
  if (region) params.set("region", region);
  return requestJson<DailyFounderReport>(`/ops/daily-report?${params.toString()}`, {
    headers: authHeaders(apiKey)
  });
}

export async function getFounderDailyReport(apiKey: string, region?: string): Promise<DailyFounderReport> {
  return fetchDailyFounderReport(apiKey, region);
}

export async function getAutonomyQueue(apiKey: string): Promise<AutonomyQueue> {
  return requestJson<AutonomyQueue>("/ops/autonomy-queue", {
    headers: authHeaders(apiKey)
  });
}

export async function getSourceConfig(apiKey: string, region?: string): Promise<SourceConfigStatus[]> {
  const params = new URLSearchParams();
  if (region) params.set("region", region);
  return requestJson<SourceConfigStatus[]>(`/ops/source-config?${params.toString()}`, {
    headers: authHeaders(apiKey)
  });
}

export async function getSourceMatrix(apiKey: string, region = "SA"): Promise<SourceMatrixEntry[]> {
  const params = new URLSearchParams({ region });
  return requestJson<SourceMatrixEntry[]>(`/ops/source-matrix?${params.toString()}`, {
    headers: authHeaders(apiKey)
  });
}

export async function previewProductUrl(
  apiKey: string,
  request: ProductUrlPreviewRequest
): Promise<ProductUrlPreviewResponse> {
  return requestJson<ProductUrlPreviewResponse>("/sources/product-url/preview", {
    method: "POST",
    headers: authHeaders(apiKey),
    body: JSON.stringify({ ...request, dry_run: true })
  });
}

export async function ingestProductUrl(
  apiKey: string,
  request: ProductUrlPreviewRequest
): Promise<ProductUrlIngestResponse> {
  return requestJson<ProductUrlIngestResponse>("/sources/product-url/ingest", {
    method: "POST",
    headers: {
      ...authHeaders(apiKey),
      "X-Idempotency-Key": `product-url-ingest-${request.url}-${request.region}-${request.category}`
    },
    body: JSON.stringify({ ...request, approved: true })
  });
}

export async function refreshKnownProductUrls(
  apiKey: string,
  request: {
    region: string;
    category?: string;
    vendor?: string;
    limit?: number;
  }
): Promise<ProductUrlRefreshResponse> {
  return requestJson<ProductUrlRefreshResponse>("/sources/product-url/refresh", {
    method: "POST",
    headers: authHeaders(apiKey),
    body: JSON.stringify(request)
  });
}

export async function getKnownProductUrls(
  apiKey: string,
  request: {
    region: string;
    category?: string;
    vendor?: string;
    limit?: number;
  }
): Promise<KnownProductUrlView[]> {
  const params = new URLSearchParams({
    region: request.region,
    limit: String(request.limit ?? 20)
  });
  if (request.category) params.set("category", request.category);
  if (request.vendor) params.set("vendor", request.vendor);
  return requestJson<KnownProductUrlView[]>(`/sources/product-url/known?${params.toString()}`, {
    headers: authHeaders(apiKey)
  });
}

export async function getCpuDuplicateCandidates(apiKey: string, region = "SA"): Promise<CpuDuplicateReport> {
  const params = new URLSearchParams({ region });
  return requestJson<CpuDuplicateReport>(`/ops/graph-integrity/cpu-duplicates?${params.toString()}`, {
    headers: authHeaders(apiKey)
  });
}

export async function previewCanonicalMerge(
  apiKey: string,
  request: CanonicalMergePreviewRequest
): Promise<CanonicalMergePreviewResponse> {
  return requestJson<CanonicalMergePreviewResponse>("/products/canonical-merge-preview", {
    method: "POST",
    headers: authHeaders(apiKey),
    body: JSON.stringify(request)
  });
}

export async function cancelAutonomyJob(apiKey: string, jobId: string): Promise<{ job_id: string; status: string }> {
  return requestJson<{ job_id: string; status: string }>(`/ops/autonomy-queue/${jobId}/cancel`, {
    method: "POST",
    headers: {
      ...authHeaders(apiKey),
      "X-Idempotency-Key": `ops-cancel-${jobId}`
    }
  });
}

export async function fetchPendingApprovals(apiKey: string): Promise<ApprovalItem[]> {
  return requestJson<ApprovalItem[]>("/approvals/pending", {
    headers: authHeaders(apiKey)
  });
}

export async function getPendingApprovals(apiKey: string): Promise<ApprovalItem[]> {
  return fetchPendingApprovals(apiKey);
}

export async function getApprovalRequest(apiKey: string, approvalId: string): Promise<ApprovalItem> {
  return requestJson<ApprovalItem>(`/approvals/${approvalId}`, {
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

export async function approveRequest(apiKey: string, approvalId: string, note?: string): Promise<{ approval: ApprovalItem }> {
  return approveItem(apiKey, approvalId, note);
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

export async function rejectRequest(apiKey: string, approvalId: string, note?: string): Promise<{ approval: ApprovalItem }> {
  return rejectItem(apiKey, approvalId, note);
}

export async function deferRequest(apiKey: string, approvalId: string, note?: string): Promise<{ approval: ApprovalItem }> {
  return requestJson<{ approval: ApprovalItem }>(`/approvals/${approvalId}/defer`, {
    method: "POST",
    headers: {
      ...authHeaders(apiKey),
      "X-Idempotency-Key": `approval-defer-${approvalId}`
    },
    body: JSON.stringify({ note })
  });
}

export async function markApprovalReviewed(apiKey: string, approvalId: string, note?: string): Promise<{ approval: ApprovalItem }> {
  return requestJson<{ approval: ApprovalItem }>(`/approvals/${approvalId}/mark-reviewed`, {
    method: "POST",
    headers: {
      ...authHeaders(apiKey),
      "X-Idempotency-Key": `approval-reviewed-${approvalId}`
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
  region,
  city,
  dryRun,
  limit
}: {
  categories: string[];
  query?: string;
  region: string;
  city?: string;
  dryRun?: boolean;
  limit?: number;
}): Promise<ProductDiscoveryResponse> {
  return requestJson<ProductDiscoveryResponse>("/pricing/discover", {
    method: "POST",
    body: JSON.stringify({
      categories,
      query: query || undefined,
      region,
      city,
      limit_per_query: limit ?? 8,
      limit,
      max_queries: 12,
      wait: false,
      dry_run: dryRun ?? false
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

export async function getSaudiBuildDataCompleteness(
  region = "SA",
  city = "Riyadh"
): Promise<SaudiBuildDataCompleteness> {
  const params = new URLSearchParams({ region, city });
  return requestJson<SaudiBuildDataCompleteness>(`/build/data-completeness?${params.toString()}`);
}

export async function generateSaudiLocalBuild(request: SaudiBuildRequest): Promise<SaudiBuildResponse> {
  return requestJson<SaudiBuildResponse>("/build/generate-local", {
    method: "POST",
    body: JSON.stringify(request)
  });
}

export async function validateSaudiLocalBuild(
  request: SaudiBuildValidationRequest
): Promise<SaudiBuildValidationResponse> {
  return requestJson<SaudiBuildValidationResponse>("/build/validate", {
    method: "POST",
    body: JSON.stringify(request)
  });
}
