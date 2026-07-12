import type {
  BuildPreferences,
  BuildGenerateResponse,
  BuildComparisonResponse,
  AnalyticsEventResponse,
  CategoryCoverage,
  AlignmentInspectionReport,
  AutonomousCognitionReport,
  AutonomyQueue,
  ApprovalItem,
  CompatibilityResponse,
  CatalogGrowthWorkflowSummary,
  CatalogCompletenessResponse,
  ComponentKind,
  ComponentOption,
  CanonicalMergePreviewRequest,
  CanonicalMergePreviewResponse,
  CanonicalImportStageRequest,
  CanonicalImportStageResponse,
  CanonicalStagedClearResponse,
  CanonicalStagedSummaryResponse,
  CatalogExpansionTargetsResponse,
  ConfirmedSpecEnrichmentRequest,
  CpuDuplicateReport,
  DailyFounderReport,
  DeploymentChecklist,
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
  PublicDealSubmissionResponse,
  FeedbackSubmissionResponse,
  FeedbackType,
  MvpHealthDashboard,
  ProductCategory,
  HardwareCognitionReport,
  HardwareIntelligence,
  HybridImportReviewResponse,
  MarketEvidenceLinkResponse,
  ProductSearchResult,
  ReasoningGovernanceReport,
  SaudiBuildDataCompleteness,
  SaudiBuildRequest,
  SaudiBuildResponse,
  SaudiBuildValidationRequest,
  SaudiBuildValidationResponse,
  SavedBuild,
  SavedBuildCreateRequest,
  SourceConfigStatus,
  SourceMatrixEntry,
  SelectedComponents,
  TelemetryReasoningReport,
  TelemetrySummary,
  UserAccount,
  ValidationBundle,
  WatchlistItem
} from "@/types/builder";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? (
  process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : ""
);

type ApiErrorBody = {
  detail?: string;
  error?: string;
};

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...publicSessionHeaders(),
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

function asArray<T>(value: T[] | undefined | null): T[] {
  return Array.isArray(value) ? value : [];
}

function authHeaders(apiKey: string): Record<string, string> {
  return apiKey ? { "X-API-Key": apiKey } : {};
}

function publicSessionHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const existing = window.localStorage.getItem("pc_builder_guest_id");
  return existing ? { "X-Session-ID": existing } : {};
}

function normalizeCoverage(coverage: Partial<CategoryCoverage>): CategoryCoverage {
  return {
    ...coverage,
    category: coverage.category ?? "Unknown",
    priced_product_count: coverage.priced_product_count ?? 0,
    trusted_local_listing_count: coverage.trusted_local_listing_count ?? 0,
    risky_listing_count: coverage.risky_listing_count ?? 0,
    usable_with_warnings_count: coverage.usable_with_warnings_count ?? 0,
    unknown_vat_count: coverage.unknown_vat_count ?? 0,
    unknown_shipping_count: coverage.unknown_shipping_count ?? 0,
    unknown_warranty_count: coverage.unknown_warranty_count ?? 0,
    suspicious_price_count: coverage.suspicious_price_count ?? 0,
    recommended_option_count: coverage.recommended_option_count ?? 0,
    stale_listing_count: coverage.stale_listing_count ?? 0,
    ready: Boolean(coverage.ready),
    readiness_level: coverage.readiness_level ?? "not_ready",
    blocker_reasons: asArray(coverage.blocker_reasons),
    warning_reasons: asArray(coverage.warning_reasons),
    notes: asArray(coverage.notes),
    next_action_type: coverage.next_action_type ?? "no_action",
    price_freshness_status: coverage.price_freshness_status ?? "missing",
    identity_confidence: coverage.identity_confidence ?? 0,
    next_action: coverage.next_action ?? "No action needed."
  };
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
  limit = 12,
  offset = 0,
  brand,
  socket,
  chipset,
  memoryType,
  minPriceSar,
  maxPriceSar,
  inStockPricedOnly,
  sort
}: {
  query?: string;
  category?: ProductCategory | "";
  region?: string;
  limit?: number;
  offset?: number;
  brand?: string;
  socket?: string;
  chipset?: string;
  memoryType?: string;
  minPriceSar?: number;
  maxPriceSar?: number;
  inStockPricedOnly?: boolean;
  sort?: "recommended" | "cheapest" | "newest" | "name";
}): Promise<ProductSearchResult[]> {
  const params = new URLSearchParams({
    q: query ?? "",
    limit: String(limit),
    offset: String(offset)
  });
  if (category) params.set("category", category);
  if (region) params.set("region", region);
  if (brand) params.set("brand", brand);
  if (socket) params.set("socket", socket);
  if (chipset) params.set("chipset", chipset);
  if (memoryType) params.set("memory_type", memoryType);
  if (typeof minPriceSar === "number") params.set("min_price_sar", String(minPriceSar));
  if (typeof maxPriceSar === "number") params.set("max_price_sar", String(maxPriceSar));
  if (inStockPricedOnly) params.set("in_stock_priced_only", "true");
  if (sort) params.set("sort", sort);
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

export async function getMvpHealthDashboard(apiKey: string, region = "SA"): Promise<MvpHealthDashboard> {
  const params = new URLSearchParams({ region });
  return requestJson<MvpHealthDashboard>(`/ops/mvp-health-dashboard?${params.toString()}`, {
    headers: authHeaders(apiKey)
  });
}

export async function getDeploymentChecklist(apiKey: string, region = "SA"): Promise<DeploymentChecklist> {
  const params = new URLSearchParams({ region });
  return requestJson<DeploymentChecklist>(`/ops/deployment-checklist?${params.toString()}`, {
    headers: authHeaders(apiKey)
  });
}

export async function getCatalogGrowthWorkflow(apiKey: string, region = "SA"): Promise<CatalogGrowthWorkflowSummary> {
  const params = new URLSearchParams({ region });
  return requestJson<CatalogGrowthWorkflowSummary>(`/ops/catalog-growth-workflow?${params.toString()}`, {
    headers: authHeaders(apiKey)
  });
}

export async function getCatalogExpansionTargets(apiKey: string, region = "SA"): Promise<CatalogExpansionTargetsResponse> {
  const params = new URLSearchParams({ region });
  return requestJson<CatalogExpansionTargetsResponse>(`/catalog/expansion/targets?${params.toString()}`, {
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

export async function stageCanonicalDataset(
  apiKey: string,
  request: CanonicalImportStageRequest
): Promise<CanonicalImportStageResponse> {
  return requestJson<CanonicalImportStageResponse>("/catalog/import/stage", {
    method: "POST",
    headers: authHeaders(apiKey),
    body: JSON.stringify(request)
  });
}

export async function getStagedCanonicalSummary(
  apiKey: string,
  request: { source_name?: string; category?: string }
): Promise<CanonicalStagedSummaryResponse> {
  const params = new URLSearchParams();
  if (request.source_name) params.set("source_name", request.source_name);
  if (request.category) params.set("category", request.category);
  return requestJson<CanonicalStagedSummaryResponse>(`/catalog/import/staged?${params.toString()}`, {
    headers: authHeaders(apiKey)
  });
}

export async function clearStagedCanonicalRecords(
  apiKey: string,
  request: { source_name: string; category: string }
): Promise<CanonicalStagedClearResponse> {
  const params = new URLSearchParams({
    source_name: request.source_name,
    category: request.category
  });
  return requestJson<CanonicalStagedClearResponse>(`/catalog/import/staged?${params.toString()}`, {
    method: "DELETE",
    headers: authHeaders(apiKey)
  });
}

export async function getHybridImportReview(
  apiKey: string,
  request: { source_name: string; category: string; region?: string }
): Promise<HybridImportReviewResponse> {
  const params = new URLSearchParams({
    source_name: request.source_name,
    category: request.category,
    region: request.region ?? "SA"
  });
  return requestJson<HybridImportReviewResponse>(`/catalog/import/hybrid-review?${params.toString()}`, {
    headers: authHeaders(apiKey)
  });
}

export async function enrichConfirmedSpecs(
  apiKey: string,
  request: ConfirmedSpecEnrichmentRequest
): Promise<unknown> {
  return requestJson<unknown>("/catalog/canonical/enrich-specs", {
    method: "POST",
    headers: authHeaders(apiKey),
    body: JSON.stringify(request)
  });
}

export async function linkMarketEvidenceDryRun(
  apiKey: string,
  request: { source_name?: string; region?: string; category?: string; canonical_keys?: string[]; limit?: number }
): Promise<MarketEvidenceLinkResponse> {
  return requestJson<MarketEvidenceLinkResponse>("/catalog/canonical/link-market-evidence", {
    method: "POST",
    headers: authHeaders(apiKey),
    body: JSON.stringify({ dry_run: true, region: "SA", ...request })
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
    body: JSON.stringify({ selection, preferences, display_refresh_hz: preferences.display_refresh_hz ?? 144 })
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
  const payload = await requestJson<BuildGenerateResponse>("/build/generate", {
    method: "POST",
    body: JSON.stringify({
      budget_usd: preferences.budget_usd ?? 1500,
      purpose: preferences.purpose,
      resolution: preferences.resolution,
      preferences: { ...preferences, display_refresh_hz: preferences.display_refresh_hz ?? 144 },
      max_candidates_per_type: 120
    })
  });
  return {
    ...payload,
    builds: asArray(payload.builds).map((build) => ({
      ...build,
      reasoning_summary: asArray(build.reasoning_summary),
      longevity_notes: asArray(build.longevity_notes)
    })),
    solver_metrics: payload.solver_metrics ?? {
      explored_nodes_count: payload.explored_configurations ?? 0,
      pruned_nodes_count: payload.pruned_configurations ?? 0,
      valid_build_count: payload.builds?.length ?? 0,
      average_build_time_ms: 0,
      max_depth_reached: 0,
      graph_fetch_time_ms: 0,
      normalization_time_ms: 0,
      compatibility_time_ms: 0,
      scoring_time_ms: 0,
      serialization_time_ms: 0
    }
  };
}

export async function getSaudiBuildDataCompleteness(
  region = "SA",
  city = "Riyadh"
): Promise<SaudiBuildDataCompleteness> {
  const params = new URLSearchParams({ region, city });
  const payload = await requestJson<SaudiBuildDataCompleteness>(`/build/data-completeness?${params.toString()}`);
  return {
    ...payload,
    required_categories: asArray(payload.required_categories),
    ready_categories: asArray(payload.ready_categories),
    missing_categories: asArray(payload.missing_categories),
    category_coverage: asArray(payload.category_coverage).map(normalizeCoverage),
    recommended_discovery_jobs: asArray(payload.recommended_discovery_jobs)
  };
}

export async function getCatalogCompleteness(region = "SA", city = "Riyadh"): Promise<CatalogCompletenessResponse> {
  const params = new URLSearchParams({ region, city });
  const payload = await requestJson<CatalogCompletenessResponse>(`/catalog/completeness?${params.toString()}`);
  return {
    ...payload,
    build_critical_categories: asArray(payload.build_critical_categories).map(normalizeCoverage),
    non_critical_categories: asArray(payload.non_critical_categories).map(normalizeCoverage),
    ready_categories: asArray(payload.ready_categories),
    usable_with_warnings_categories: asArray(payload.usable_with_warnings_categories),
    not_ready_categories: asArray(payload.not_ready_categories),
    stale_categories: asArray(payload.stale_categories),
    weak_categories: asArray(payload.weak_categories),
    duplicate_risk_categories: asArray(payload.duplicate_risk_categories),
    next_actions: asArray(payload.next_actions)
  };
}

export async function generateSaudiLocalBuild(request: SaudiBuildRequest): Promise<SaudiBuildResponse> {
  const payload = await requestJson<SaudiBuildResponse>("/build/generate-local", {
    method: "POST",
    body: JSON.stringify(request)
  });
  if (!payload || !Array.isArray(payload.builds) || !Array.isArray(payload.missing_data_warnings) || typeof payload.build_status !== "string") {
    throw new Error("Build service returned incomplete data. Please try again.");
  }
  if (payload.builds.some((build) => !build?.summary || !Array.isArray(build.components))) {
    throw new Error("Build service returned incomplete data. Please try again.");
  }
  return {
    ...payload,
    builds: asArray(payload.builds).map((build) => ({
      ...build,
      components: asArray(build.components),
      upgrade_notes: asArray(build.upgrade_notes),
      savings_suggestions: asArray(build.savings_suggestions),
      summary: {
        ...build.summary,
        most_expensive_components: asArray(build.summary?.most_expensive_components),
        easiest_savings_opportunities: asArray(build.summary?.easiest_savings_opportunities),
        risk_summary: asArray(build.summary?.risk_summary),
        warning_summary: asArray(build.summary?.warning_summary),
        components_with_uncertainty: asArray(build.summary?.components_with_uncertainty),
        missing_data_warnings: asArray(build.summary?.missing_data_warnings)
      },
      explanation: {
        ...build.explanation,
        strengths: asArray(build.explanation?.strengths),
        weaknesses: asArray(build.explanation?.weaknesses),
        risks: asArray(build.explanation?.risks),
        upgrade_path: asArray(build.explanation?.upgrade_path),
        future_limitations: asArray(build.explanation?.future_limitations),
        recommended_purchase_order: asArray(build.explanation?.recommended_purchase_order),
        component_explanations: asArray(build.explanation?.component_explanations)
      }
    })),
    recommended_discovery_jobs: asArray(payload.recommended_discovery_jobs),
    missing_data_warnings: asArray(payload.missing_data_warnings),
    build_comparison: asArray(payload.build_comparison)
  };
}

export async function validateSaudiLocalBuild(
  request: SaudiBuildValidationRequest
): Promise<SaudiBuildValidationResponse> {
  return requestJson<SaudiBuildValidationResponse>("/build/validate", {
    method: "POST",
    body: JSON.stringify(request)
  });
}

export async function createUserAccount(request: {
  email: string;
  display_name?: string | null;
  region?: string;
}): Promise<UserAccount> {
  return requestJson<UserAccount>("/users", {
    method: "POST",
    body: JSON.stringify({ region: "SA", ...request })
  });
}

export async function saveBuild(request: SavedBuildCreateRequest): Promise<SavedBuild> {
  return normalizeSavedBuild(
    await requestJson<SavedBuild>("/builds/saved", {
      method: "POST",
      body: JSON.stringify(request)
    })
  );
}

export async function listSavedBuilds(identity: { user_id?: string | null; guest_id?: string | null }): Promise<SavedBuild[]> {
  const path = identity.user_id ? `/users/${identity.user_id}/builds` : `/guests/${identity.guest_id}/builds`;
  const payload = await requestJson<{ builds: SavedBuild[] }>(path);
  return asArray(payload.builds).map(normalizeSavedBuild);
}

export async function getSharedBuild(shareSlug: string): Promise<SavedBuild> {
  return normalizeSavedBuild(await requestJson<SavedBuild>(`/build/share/${shareSlug}`));
}

export async function updateSavedBuild(
  buildId: string,
  request: { title?: string; public_visibility?: boolean; favorite?: boolean }
): Promise<SavedBuild> {
  return normalizeSavedBuild(
    await requestJson<SavedBuild>(`/builds/saved/${buildId}`, {
      method: "PATCH",
      body: JSON.stringify(request)
    })
  );
}

export async function duplicateSavedBuild(
  buildId: string,
  identity: { user_id?: string | null; guest_id?: string | null }
): Promise<SavedBuild> {
  const params = new URLSearchParams();
  if (identity.user_id) params.set("user_id", identity.user_id);
  if (identity.guest_id) params.set("guest_id", identity.guest_id);
  return normalizeSavedBuild(
    await requestJson<SavedBuild>(`/builds/saved/${buildId}/duplicate?${params.toString()}`, {
      method: "POST"
    })
  );
}

export async function deleteSavedBuild(buildId: string): Promise<boolean> {
  const payload = await requestJson<{ deleted: boolean }>(`/builds/saved/${buildId}`, {
    method: "DELETE"
  });
  return payload.deleted;
}

export async function compareSavedBuilds(
  buildIds: string[],
  identity: { user_id?: string | null; guest_id?: string | null }
): Promise<BuildComparisonResponse> {
  return requestJson<BuildComparisonResponse>("/builds/compare", {
    method: "POST",
    body: JSON.stringify({ build_ids: buildIds, ...identity })
  });
}

export async function listWatchlist(identity: { user_id?: string | null; guest_id?: string | null }, region = "SA"): Promise<WatchlistItem[]> {
  const params = new URLSearchParams({ region });
  const path = identity.user_id ? `/users/${identity.user_id}/watchlist` : `/guests/${identity.guest_id}/watchlist`;
  const payload = await requestJson<{ items: WatchlistItem[] }>(`${path}?${params.toString()}`);
  return asArray(payload.items);
}

export async function addWatchlistItem(
  identity: { user_id?: string | null; guest_id?: string | null },
  request: { product_id: string; target_price_sar?: number | null; region?: string }
): Promise<WatchlistItem[]> {
  const path = identity.user_id ? `/users/${identity.user_id}/watchlist` : `/guests/${identity.guest_id}/watchlist`;
  const payload = await requestJson<{ items: WatchlistItem[] }>(path, {
    method: "POST",
    body: JSON.stringify({ region: "SA", ...request })
  });
  return asArray(payload.items);
}

export async function removeWatchlistItem(
  identity: { user_id?: string | null; guest_id?: string | null },
  itemId: string
): Promise<boolean> {
  const path = identity.user_id
    ? `/users/${identity.user_id}/watchlist/${itemId}`
    : `/guests/${identity.guest_id}/watchlist/${itemId}`;
  const payload = await requestJson<{ deleted: boolean }>(path, { method: "DELETE" });
  return payload.deleted;
}

export async function submitPublicDeal(request: {
  url: string;
  region?: string;
  category: ProductCategory | string;
  email?: string | null;
  note?: string | null;
}): Promise<PublicDealSubmissionResponse> {
  return requestJson<PublicDealSubmissionResponse>("/sources/deal-submissions", {
    method: "POST",
    body: JSON.stringify({ region: "SA", ...request })
  });
}

export async function recordAnalyticsEvent(request: {
  event_type: string;
  region?: string;
  anonymous_session_id?: string | null;
  user_id?: string | null;
  category?: string | null;
  build_status?: string | null;
  budget_sar?: number | null;
  metadata?: Record<string, unknown>;
}): Promise<AnalyticsEventResponse> {
  return requestJson<AnalyticsEventResponse>("/analytics/events", {
    method: "POST",
    body: JSON.stringify({ region: "SA", ...request })
  });
}

export async function submitFeedback(request: {
  type: FeedbackType;
  region?: string;
  product_id?: string | null;
  build_id?: string | null;
  share_slug?: string | null;
  notes: string;
  anonymous_session_id?: string | null;
}): Promise<FeedbackSubmissionResponse> {
  return requestJson<FeedbackSubmissionResponse>("/feedback", {
    method: "POST",
    body: JSON.stringify({ region: "SA", ...request })
  });
}

function normalizeSavedBuild(build: SavedBuild): SavedBuild {
  return {
    ...build,
    warning_summary: asArray(build.warning_summary),
    component_ids: asArray(build.component_ids),
    price_snapshot_ids: asArray(build.price_snapshot_ids),
    build_summary: build.build_summary ?? {},
    build_payload: build.build_payload ?? {},
    favorite: Boolean(build.favorite),
    public_visibility: Boolean(build.public_visibility)
  };
}
