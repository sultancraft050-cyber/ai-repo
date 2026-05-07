"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  BadgeDollarSign,
  BrainCircuit,
  Clock3,
  Cpu,
  Flame,
  LineChart,
  RefreshCw,
  Search,
  ShieldCheck,
  Store,
  Sparkles,
  Thermometer,
  TrendingDown,
  Zap
} from "lucide-react";
import {
  discoverProducts,
  enrichProducts,
  fetchAlignmentReport,
  fetchAutonomyReport,
  fetchCognitionReport,
  fetchEvolutionReport,
  fetchGovernanceReport,
  fetchProductIntelligence,
  fetchProductHistory,
  fetchProductPrices,
  fetchTelemetryReasoning,
  refreshPricing,
  searchProducts
} from "@/lib/api";
import {
  type AlignmentInspectionReport,
  type AutonomousCognitionReport,
  type EvolutionOrchestrationReport,
  type HardwareCognitionReport,
  type HardwareIntelligence,
  productCategories,
  type PriceHistoryPoint,
  type PriceSnapshotView,
  type ProductCategory,
  type ProductSearchResult,
  type ReasoningGovernanceReport,
  type TelemetryReasoningReport,
  type TelemetrySeverity,
  type TelemetrySummary
} from "@/types/builder";
import { useRegion } from "@/components/RegionProvider";

export function PricingIntelligencePanel({ region: regionOverride }: { region?: string }) {
  const { region: selectedRegion, regionOption } = useRegion();
  const region = regionOverride ?? selectedRegion;
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<ProductCategory | "">("GPU");
  const [products, setProducts] = useState<ProductSearchResult[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [prices, setPrices] = useState<PriceSnapshotView[]>([]);
  const [history, setHistory] = useState<PriceHistoryPoint[]>([]);
  const [intelligence, setIntelligence] = useState<HardwareIntelligence | null>(null);
  const [reasoning, setReasoning] = useState<TelemetryReasoningReport | null>(null);
  const [cognition, setCognition] = useState<HardwareCognitionReport | null>(null);
  const [governance, setGovernance] = useState<ReasoningGovernanceReport | null>(null);
  const [evolution, setEvolution] = useState<EvolutionOrchestrationReport | null>(null);
  const [alignment, setAlignment] = useState<AlignmentInspectionReport | null>(null);
  const [autonomy, setAutonomy] = useState<AutonomousCognitionReport | null>(null);
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [loadingMarket, setLoadingMarket] = useState(false);
  const [loadingIntelligence, setLoadingIntelligence] = useState(false);
  const [loadingReasoning, setLoadingReasoning] = useState(false);
  const [loadingCognition, setLoadingCognition] = useState(false);
  const [loadingGovernance, setLoadingGovernance] = useState(false);
  const [loadingEvolution, setLoadingEvolution] = useState(false);
  const [loadingAlignment, setLoadingAlignment] = useState(false);
  const [loadingAutonomy, setLoadingAutonomy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [enriching, setEnriching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadProducts() {
      setLoadingProducts(true);
      setError(null);
      try {
        const result = await searchProducts({ query, category, region, limit: 10 });
        if (cancelled) return;
        setProducts(result);
        setSelectedId((current) => current ?? result[0]?.id ?? null);
      } catch (loadError) {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Unable to load products.");
      } finally {
        if (!cancelled) setLoadingProducts(false);
      }
    }
    const timer = window.setTimeout(loadProducts, 220);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, category, region]);

  useEffect(() => {
    if (!selectedId) {
      setPrices([]);
      setHistory([]);
      setIntelligence(null);
      setReasoning(null);
      setCognition(null);
      setGovernance(null);
      setEvolution(null);
      setAlignment(null);
      setAutonomy(null);
      return;
    }
    const productId = selectedId;
    let cancelled = false;
    async function loadMarket() {
      setLoadingMarket(true);
      setError(null);
      try {
        const [priceResult, historyResult] = await Promise.all([
          fetchProductPrices(productId, region),
          fetchProductHistory(productId, region)
        ]);
        if (cancelled) return;
        setPrices(priceResult);
        setHistory(historyResult);
      } catch (loadError) {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Unable to load pricing.");
      } finally {
        if (!cancelled) setLoadingMarket(false);
      }
    }
    loadMarket();
    return () => {
      cancelled = true;
    };
  }, [selectedId, region]);

  useEffect(() => {
    if (!selectedId) {
      setIntelligence(null);
      setReasoning(null);
      setCognition(null);
      setGovernance(null);
      setEvolution(null);
      setAlignment(null);
      setAutonomy(null);
      return;
    }
    const productId = selectedId;
    let cancelled = false;
    async function loadIntelligence() {
      setLoadingIntelligence(true);
      setLoadingReasoning(true);
      setLoadingCognition(true);
      setLoadingGovernance(true);
      setLoadingEvolution(true);
      setLoadingAlignment(true);
      setLoadingAutonomy(true);
      try {
        const [intelligenceResult, reasoningResult, cognitionResult, governanceResult, evolutionResult, alignmentResult, autonomyResult] = await Promise.all([
          fetchProductIntelligence(productId).catch(() => null),
          fetchTelemetryReasoning(productId).catch(() => null),
          fetchCognitionReport(productId).catch(() => null),
          fetchGovernanceReport(productId).catch(() => null),
          fetchEvolutionReport(productId).catch(() => null),
          fetchAlignmentReport(productId).catch(() => null),
          fetchAutonomyReport(productId).catch(() => null)
        ]);
        if (!cancelled) {
          setIntelligence(intelligenceResult);
          setReasoning(reasoningResult);
          setCognition(cognitionResult);
          setGovernance(governanceResult);
          setEvolution(evolutionResult);
          setAlignment(alignmentResult);
          setAutonomy(autonomyResult);
        }
      } catch {
        if (!cancelled) {
          setIntelligence(null);
          setReasoning(null);
          setCognition(null);
          setGovernance(null);
          setEvolution(null);
          setAlignment(null);
          setAutonomy(null);
        }
      } finally {
        if (!cancelled) {
          setLoadingIntelligence(false);
          setLoadingReasoning(false);
          setLoadingCognition(false);
          setLoadingGovernance(false);
          setLoadingEvolution(false);
          setLoadingAlignment(false);
          setLoadingAutonomy(false);
        }
      }
    }
    loadIntelligence();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const selectedProduct = useMemo(
    () => products.find((product) => product.id === selectedId) ?? products[0],
    [products, selectedId]
  );
  const productGroupCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const product of products) {
      const key = cpuGroupKey(product);
      if (key) counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return counts;
  }, [products]);

  async function handleRefresh() {
    if (!selectedProduct) return;
    setRefreshing(true);
    setRefreshMessage(null);
    setError(null);
    try {
      const result = await refreshPricing([selectedProduct.id], region);
      setRefreshMessage(result.message);
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Unable to queue refresh.");
    } finally {
      setRefreshing(false);
    }
  }

  async function handleDiscover() {
    setDiscovering(true);
    setRefreshMessage(null);
    setError(null);
    try {
      const result = await discoverProducts({
        categories: category ? [category] : productCategories,
        query,
        region
      });
      setRefreshMessage(`${result.message}; ${result.query_count} discovery queries queued.`);
    } catch (discoverError) {
      setError(discoverError instanceof Error ? discoverError.message : "Unable to queue discovery.");
    } finally {
      setDiscovering(false);
    }
  }

  async function handleEnrich() {
    if (!selectedProduct) return;
    setEnriching(true);
    setLoadingCognition(true);
    setLoadingGovernance(true);
    setLoadingEvolution(true);
    setLoadingAlignment(true);
    setLoadingAutonomy(true);
    setRefreshMessage(null);
    setError(null);
    try {
      await enrichProducts([selectedProduct.id]);
      const [result, reasoningResult, cognitionResult, governanceResult, evolutionResult, alignmentResult, autonomyResult] = await Promise.all([
        fetchProductIntelligence(selectedProduct.id).catch(() => null),
        fetchTelemetryReasoning(selectedProduct.id).catch(() => null),
        fetchCognitionReport(selectedProduct.id).catch(() => null),
        fetchGovernanceReport(selectedProduct.id).catch(() => null),
        fetchEvolutionReport(selectedProduct.id).catch(() => null),
        fetchAlignmentReport(selectedProduct.id).catch(() => null),
        fetchAutonomyReport(selectedProduct.id).catch(() => null)
      ]);
      setIntelligence(result);
      setReasoning(reasoningResult);
      setCognition(cognitionResult);
      setGovernance(governanceResult);
      setEvolution(evolutionResult);
      setAlignment(alignmentResult);
      setAutonomy(autonomyResult);
      setRefreshMessage("hardware intelligence enrichment completed");
    } catch (enrichError) {
      setError(enrichError instanceof Error ? enrichError.message : "Unable to enrich product.");
    } finally {
      setEnriching(false);
      setLoadingCognition(false);
      setLoadingGovernance(false);
      setLoadingEvolution(false);
      setLoadingAlignment(false);
      setLoadingAutonomy(false);
    }
  }

  return (
    <section className="rounded-lg border border-line bg-white p-4 shadow-tight">
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.08em] text-signal">
            <BadgeDollarSign size={17} aria-hidden />
            Price Intelligence
          </div>
          <h2 className="text-lg font-semibold text-ink">Market graph</h2>
          <p className="mt-1 text-sm text-slate-500">
            For your selected market: {regionOption.countryName} ({regionOption.currency})
          </p>
        </div>
        <div className="grid gap-2 sm:grid-cols-[1fr_170px_auto_auto_auto]">
          <label className="relative block">
            <span className="sr-only">Search products</span>
            <Search size={16} className="pointer-events-none absolute left-3 top-3 text-slate-400" aria-hidden />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search model"
              className="h-10 w-full rounded-md border border-line bg-white pl-9 pr-3 text-sm text-ink"
            />
          </label>
          <label className="block">
            <span className="sr-only">Category</span>
            <select
              value={category}
              onChange={(event) => setCategory(event.target.value as ProductCategory | "")}
              className="h-10 w-full rounded-md border border-line bg-white px-3 text-sm"
            >
              <option value="">All</option>
              {productCategories.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={!selectedProduct || refreshing}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-line bg-panel px-3 text-sm font-semibold text-ink disabled:cursor-not-allowed disabled:text-slate-400"
          >
            <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} aria-hidden />
            Refresh
          </button>
          <button
            type="button"
            onClick={handleDiscover}
            disabled={discovering}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-signal px-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            <Sparkles size={16} className={discovering ? "animate-pulse" : ""} aria-hidden />
            Discover
          </button>
          <button
            type="button"
            onClick={handleEnrich}
            disabled={!selectedProduct || enriching}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-line bg-white px-3 text-sm font-semibold text-ink disabled:cursor-not-allowed disabled:text-slate-400"
          >
            <BrainCircuit size={16} className={enriching ? "animate-pulse" : ""} aria-hidden />
            Enrich
          </button>
        </div>
      </div>

      {error ? (
        <div className="mb-3 rounded-md border border-danger/30 bg-red-50 px-3 py-2 text-sm text-danger">
          {error}
        </div>
      ) : null}

      {refreshMessage ? (
        <div className="mb-3 rounded-md border border-line bg-panel px-3 py-2 text-sm text-slate-600">
          {refreshMessage}
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[0.95fr_1.4fr]">
        <div className="rounded-md border border-line bg-panel p-2">
          {loadingProducts ? (
            <div className="grid gap-2">
              {[0, 1, 2, 3].map((item) => (
                <div key={item} className="h-16 animate-pulse rounded bg-white" />
              ))}
            </div>
          ) : products.length === 0 ? (
            <div className="rounded bg-white px-3 py-8 text-sm text-slate-600">
              No live prices yet for this region. Try discovery or switch region.
            </div>
          ) : (
            <div className="grid gap-2">
              {products.map((product) => (
                <ProductResultButton
                  key={product.id}
                  product={product}
                  selected={selectedProduct?.id === product.id}
                  groupCount={productGroupCounts.get(cpuGroupKey(product) ?? "") ?? 0}
                  onSelect={() => setSelectedId(product.id)}
                />
              ))}
            </div>
          )}
        </div>

        <div className="grid gap-3">
          <MarketSummary product={selectedProduct} prices={prices} loading={loadingMarket} regionLabel={regionOption.countryName} />
          <HardwareIntelligenceCard
            intelligence={intelligence}
            reasoning={reasoning}
            loading={loadingIntelligence || loadingReasoning || enriching}
            product={selectedProduct}
          />
          <CognitionCard cognition={cognition} loading={loadingCognition || enriching} product={selectedProduct} />
          <GovernanceCard governance={governance} loading={loadingGovernance || enriching} product={selectedProduct} />
          <EvolutionCard evolution={evolution} loading={loadingEvolution || enriching} product={selectedProduct} />
          <AlignmentCard alignment={alignment} loading={loadingAlignment || enriching} product={selectedProduct} />
          <AutonomyCard autonomy={autonomy} loading={loadingAutonomy || enriching} product={selectedProduct} />
          <VendorComparison prices={prices} loading={loadingMarket} regionLabel={regionOption.countryName} />
          <HistoryChart history={history} loading={loadingMarket} />
        </div>
      </div>
    </section>
  );
}

function ProductResultButton({
  product,
  selected,
  groupCount,
  onSelect
}: {
  product: ProductSearchResult;
  selected: boolean;
  groupCount: number;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`rounded-md border px-3 py-2 text-left ${
        product.data_origin === "seed" && product.price_status === "unavailable" ? "opacity-70" : ""
      } ${selected ? "border-signal bg-white" : "border-line bg-white/70"}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-ink">{product.name}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
            <span>{product.brand ?? "Unknown"}</span>
            <span>{product.category}</span>
            <span className="capitalize">{product.price_status.replaceAll("_", " ")}</span>
            {groupCount > 1 ? <span className="text-signal">CPU group x{groupCount}</span> : null}
            {product.data_origin === "seed" ? <span className="text-caution">seed</span> : null}
            {product.flags.includes("price_requires_review") ? (
              <span className="text-caution">price review</span>
            ) : null}
          </div>
        </div>
        <PriceBadge product={product} />
      </div>
    </button>
  );
}

function cpuGroupKey(product: ProductSearchResult) {
  if (product.category !== "CPU") return null;
  const compact = `${product.canonical_key ?? ""} ${product.model ?? ""} ${product.name}`.toUpperCase().replace(/[^A-Z0-9]+/g, "");
  if (compact.includes("7800X3D")) return "CPU|AMD|RYZEN_7_7800X3D";
  const ryzen = compact.match(/RYZEN([3579])(\d{4})(X3D|XT|X)?/);
  if (ryzen) return `CPU|AMD|RYZEN_${ryzen[1]}_${ryzen[2]}${ryzen[3] ?? ""}`;
  const r7 = compact.match(/R7(\d{4})(X3D|XT|X)?/);
  if (r7) return `CPU|AMD|RYZEN_7_${r7[1]}${r7[2] ?? ""}`;
  const intel = compact.match(/(?:CORE)?I([3579])(\d{4,5}[A-Z]*)/);
  if (intel) return `CPU|INTEL|CORE_I${intel[1]}_${intel[2]}`;
  return null;
}

function PriceBadge({ product }: { product: ProductSearchResult }) {
  if (typeof product.current_recommended_price === "number") {
    return (
      <span className="shrink-0 rounded bg-emerald-50 px-2 py-1 text-xs font-semibold text-signal">
        Rec {money(product.current_recommended_currency, product.current_recommended_price)}
      </span>
    );
  }
  if (typeof product.lowest_market_price === "number") {
    return (
      <span className="shrink-0 rounded bg-amber-50 px-2 py-1 text-xs font-semibold text-caution">
        Low {money(product.lowest_market_currency, product.lowest_market_price)}
      </span>
    );
  }
  return (
    <span className="shrink-0 rounded bg-panel px-2 py-1 text-xs font-medium text-slate-500">
      {product.data_origin === "seed" ? "Seed only" : "No price"}
    </span>
  );
}

function MarketSummary({
  product,
  prices,
  loading,
  regionLabel
}: {
  product?: ProductSearchResult;
  prices: PriceSnapshotView[];
  loading: boolean;
  regionLabel: string;
}) {
  if (loading) return <div className="h-28 animate-pulse rounded-md border border-line bg-panel" />;
  if (!product) {
    return <div className="rounded-md border border-line bg-panel px-3 py-8 text-sm text-slate-600">No market data.</div>;
  }
  const reviewNeeded =
    Boolean(product.lowest_price_warning) ||
    product.flags.includes("price_requires_review") ||
    product.lowest_market_seller_type === "marketplace";
  const noRegionalPrices = prices.length === 0 && product.price_status === "unavailable";
  const hasRecommendation = typeof product.current_recommended_price === "number";
  return (
    <div className="rounded-md border border-line bg-panel p-3">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-base font-semibold text-ink">{product.name}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span>{regionLabel}</span>
            <span>{product.current_recommended_vendor ?? product.lowest_market_vendor ?? "No vendor"}</span>
            <span className="capitalize">{product.price_status.replaceAll("_", " ")}</span>
            {product.recommended_level ? (
              <span className={recommendationTextClass(product.recommended_level)}>
                {product.recommended_level.replaceAll("_", " ")}
              </span>
            ) : null}
            {product.data_origin === "seed" ? <span className="text-caution">seed data</span> : null}
            {product.price_drop_percent ? (
              <span className="inline-flex items-center gap-1 text-signal">
                <TrendingDown size={13} aria-hidden />
                {product.price_drop_percent}% drop
              </span>
            ) : null}
          </div>
        </div>
        {typeof product.current_recommended_price === "number" ? (
          <div className="text-right">
            <div className="text-xl font-semibold text-ink">
              {money(product.current_recommended_currency, product.current_recommended_price)}
            </div>
            <div className="text-xs capitalize text-slate-500">recommended</div>
          </div>
        ) : typeof product.lowest_market_price === "number" ? (
          <div className="text-right">
            <div className="text-xl font-semibold text-caution">{money(product.lowest_market_currency, product.lowest_market_price)}</div>
            <div className="text-xs text-slate-500">lowest, review</div>
          </div>
        ) : null}
      </div>
      <div className="mb-3 rounded border border-line bg-white px-3 py-2">
        <div className="mb-1 flex items-center justify-between gap-3">
          <span className="text-xs font-semibold uppercase text-slate-500">
            {hasRecommendation ? "Recommended Saudi option" : "Saudi recommendation"}
          </span>
          {product.recommended_level ? (
            <span className={`rounded px-2 py-1 text-[11px] font-semibold ${recommendationBadgeClass(product.recommended_level)}`}>
              {product.recommended_level.replaceAll("_", " ")}
            </span>
          ) : null}
        </div>
        {hasRecommendation ? (
          <div className="grid gap-1">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-lg font-semibold text-ink">
                {money(product.current_recommended_currency, product.current_recommended_price as number)}
              </span>
              <span className="text-sm text-slate-600">{product.current_recommended_vendor}</span>
            </div>
            {product.recommended_reason ? (
              <p className="text-xs text-slate-600">{product.recommended_reason}</p>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-slate-600">
            Not enough information to recommend yet. Cheapest listings are still shown, but the platform needs stronger VAT,
            shipping, warranty, condition, or vendor evidence before calling one the safer buy.
          </p>
        )}
      </div>
      {reviewNeeded ? (
        <div className="mb-3 flex items-start gap-2 rounded border border-amber-200 bg-amber-50 px-2 py-2 text-xs text-amber-800">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden />
          <span>{product.lowest_price_warning ?? "Lowest price is marketplace or unknown-condition data. It is shown separately and not treated as trusted automatically."}</span>
        </div>
      ) : null}
      {noRegionalPrices ? (
        <div className="mb-3 flex items-start gap-2 rounded border border-line bg-white px-2 py-2 text-xs text-slate-600">
          <AlertTriangle size={14} className="mt-0.5 shrink-0 text-caution" aria-hidden />
          <span>No live prices yet for this selected market. The product can exist globally without a regional price snapshot.</span>
        </div>
      ) : null}
      <div className="grid gap-2 sm:grid-cols-3">
        <SmallMetric icon={<ShieldCheck size={14} />} label="Trust" value={scoreText(product.current_price_trust_score)} />
        <SmallMetric icon={<Clock3 size={14} />} label="Freshness" value={scoreText(product.current_price_freshness_score)} />
        <SmallMetric icon={<Store size={14} />} label="Vendors" value={String(prices.length)} />
      </div>
      <div className="mt-2 grid gap-2 sm:grid-cols-3">
        <SmallMetric icon={<BadgeDollarSign size={14} />} label="Lowest" value={priceText(product.lowest_market_currency, product.lowest_market_price)} />
        <SmallMetric icon={<ShieldCheck size={14} />} label="Trusted" value={priceText(product.best_trusted_currency, product.best_trusted_price)} />
        <SmallMetric icon={<Store size={14} />} label="Local" value={priceText(product.best_local_currency, product.best_local_price)} />
      </div>
      <div className="mt-2 grid gap-2 sm:grid-cols-3">
        <SmallMetric icon={<BadgeDollarSign size={14} />} label="New" value={priceText(product.best_new_currency, product.best_new_price)} />
        <SmallMetric icon={<ShieldCheck size={14} />} label="Confidence" value={scoreText(product.price_confidence)} />
        <SmallMetric icon={<Store size={14} />} label="Lowest vendor" value={product.lowest_market_vendor ?? "N/A"} />
      </div>
    </div>
  );
}

function VendorComparison({
  prices,
  loading,
  regionLabel
}: {
  prices: PriceSnapshotView[];
  loading: boolean;
  regionLabel: string;
}) {
  if (loading) return <div className="h-32 animate-pulse rounded-md border border-line bg-panel" />;
  if (prices.length === 0) {
    return (
      <div className="rounded-md border border-line bg-panel px-3 py-8 text-sm text-slate-600">
        No vendor snapshots yet for {regionLabel}.
      </div>
    );
  }
  return (
    <div className="rounded-md border border-line bg-panel p-3">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
        <Store size={15} className="text-signal" aria-hidden />
        Vendor comparison
      </div>
      <div className="grid gap-2">
        {prices.slice(0, 5).map((price) => (
          <div key={price.id} className="grid grid-cols-[1fr_auto] gap-3 rounded border border-line bg-white px-3 py-2">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-ink">{price.vendor_name}</div>
              <div className="mt-1 flex flex-wrap gap-1.5 text-xs text-slate-500">
                <span className="capitalize">{price.availability.replaceAll("_", " ")}</span>
                <span className="capitalize">{price.listing_condition.replaceAll("_", " ")}</span>
                <span className="capitalize">{price.seller_type.replaceAll("_", " ")}</span>
                <span className={price.marketplace_risk_score >= 0.65 ? "text-caution" : ""}>
                  risk {Math.round(price.marketplace_risk_score * 100)}%
                </span>
                <span>{price.source}</span>
                <span>{formatStatus(price.vendor_region_type)}</span>
                <span>{formatStatus(price.local_stock_status)}</span>
                <span>{price.is_local_stock ? "local stock" : price.is_imported ? "imported" : "regional unknown"}</span>
                <span className={recommendationTextClass(price.buy_recommendation_level)}>
                  {price.buy_recommendation_level.replaceAll("_", " ")}
                </span>
                <span>{price.trust_tier} trust</span>
                {price.serves_saudi ? <span>serves Saudi</span> : null}
                <span className={price.vat_status === "vat_unknown" ? "text-caution" : ""}>
                  {formatStatus(price.vat_status)}
                </span>
                <span className={price.shipping_status === "unknown_shipping" ? "text-caution" : ""}>
                  {formatStatus(price.shipping_status)}
                </span>
                <span className={price.warranty_status === "unknown_warranty" ? "text-caution" : ""}>
                  {formatStatus(price.warranty_status)}
                </span>
                {price.recommended_saudi_price_candidate ? <span className="text-signal">SA candidate</span> : null}
                {price.warnings.slice(0, 3).map((warning) => (
                  <span key={warning} className="text-caution">
                    {warning}
                  </span>
                ))}
                {price.flags.length && price.warnings.length === 0 ? <span className="text-caution">{price.flags[0].replaceAll("_", " ")}</span> : null}
              </div>
              {price.recommendation_reason ? (
                <div className="mt-1 text-xs text-slate-600">{price.recommendation_reason}</div>
              ) : null}
            </div>
            <div className="text-right text-sm font-semibold text-ink">
              {money(
                price.final_landed_currency ?? price.currency,
                price.final_landed_price_sar ?? price.final_landed_price ?? price.price + price.shipping_cost
              )}
              {price.final_landed_price_sar ? (
                <div className="text-[11px] font-medium text-slate-500">final landed</div>
              ) : null}
              <div className="text-[11px] font-medium text-slate-500">
                confidence {scoreText(price.confidence_score ?? price.final_landed_price_confidence ?? undefined)}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function money(currency: string | undefined, value: number) {
  return `${currency ?? "USD"} ${value.toFixed(0)}`;
}

function priceText(currency: string | undefined, value: number | undefined) {
  return typeof value === "number" ? money(currency, value) : "N/A";
}

function formatStatus(value: string | null | undefined) {
  return (value ?? "unknown").replaceAll("_", " ");
}

function recommendationBadgeClass(level: PriceSnapshotView["buy_recommendation_level"]) {
  if (level === "recommended") return "bg-emerald-50 text-signal";
  if (level === "good_if_price_matters") return "bg-blue-50 text-blue-700";
  if (level === "acceptable_with_risk") return "bg-amber-50 text-caution";
  if (level === "not_recommended") return "bg-red-50 text-danger";
  return "bg-slate-100 text-slate-600";
}

function recommendationTextClass(level: PriceSnapshotView["buy_recommendation_level"] | ProductSearchResult["recommended_level"]) {
  if (level === "recommended") return "text-signal";
  if (level === "good_if_price_matters") return "text-blue-700";
  if (level === "acceptable_with_risk") return "text-caution";
  if (level === "not_recommended") return "text-danger";
  return "text-slate-500";
}

function HardwareIntelligenceCard({
  intelligence,
  reasoning,
  loading,
  product
}: {
  intelligence: HardwareIntelligence | null;
  reasoning: TelemetryReasoningReport | null;
  loading: boolean;
  product?: ProductSearchResult;
}) {
  if (loading) return <div className="h-56 animate-pulse rounded-md border border-line bg-panel" />;
  if (!product) {
    return <div className="rounded-md border border-line bg-panel px-3 py-8 text-sm text-slate-600">No intelligence target.</div>;
  }
  if (!intelligence) {
    return (
      <div className="rounded-md border border-line bg-panel px-3 py-8 text-sm text-slate-600">
        Intelligence enrichment has not been generated for this product yet.
      </div>
    );
  }
  const topWorkloads = [...intelligence.workloads].sort((a, b) => b.score - a.score).slice(0, 4);
  const bars = [
    ["Gaming", intelligence.benchmark.gaming],
    ["Productivity", intelligence.benchmark.productivity],
    ["AI/ML", intelligence.benchmark.ai_ml],
    ["Rendering", intelligence.benchmark.rendering],
    ["Simulation", intelligence.benchmark.simulation]
  ] as const;
  return (
    <div className="rounded-md border border-line bg-panel p-3">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-ink">
            <BrainCircuit size={15} className="text-signal" aria-hidden />
            Hardware intelligence
          </div>
          <div className="flex flex-wrap gap-1.5 text-xs">
            <Badge text={`${intelligence.confidence} confidence`} tone="neutral" />
            <Badge text={`value ${intelligence.market.value_score.toFixed(0)}`} tone="signal" />
            <Badge text={`future ${intelligence.longevity.future_proof_score.toFixed(0)}`} tone="violet" />
            {intelligence.market.best_value_badge ? <Badge text="best value" tone="signal" /> : null}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs sm:w-56">
          <SmallMetric
            icon={<Flame size={14} />}
            label="Thermal"
            value={`${intelligence.power_thermal.thermal_efficiency.toFixed(0)}/100`}
          />
          <SmallMetric
            icon={<Zap size={14} />}
            label="Spike"
            value={intelligence.power_thermal.power_spike_risk}
          />
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-[1fr_0.9fr]">
        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Benchmark model</div>
          <div className="grid gap-2">
            {bars.map(([label, value]) => (
              <div key={label} className="grid grid-cols-[92px_1fr_42px] items-center gap-2 text-xs">
                <span className="text-slate-600">{label}</span>
                <div className="h-2 overflow-hidden rounded bg-slate-100">
                  <div className="h-full rounded bg-signal" style={{ width: `${Math.max(4, value)}%` }} />
                </div>
                <span className="text-right font-semibold text-ink">{value.toFixed(0)}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Workload suitability</div>
          <div className="grid grid-cols-2 gap-2">
            {topWorkloads.map((workload) => (
              <div key={workload.workload} className="rounded bg-panel px-2 py-2">
                <div className="truncate text-xs font-semibold capitalize text-ink">
                  {workload.workload.replaceAll("_", " ")}
                </div>
                <div className="mt-1 text-xs text-slate-600">
                  {workload.score.toFixed(0)} / {workload.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <TelemetryEvidenceCard telemetry={intelligence.telemetry ?? null} />
      <TelemetryReasoningCard reasoning={reasoning} />

      <div className="mt-3 grid gap-2 text-xs leading-5 text-slate-600">
        {intelligence.recommendation_summary.slice(0, 3).map((reason) => (
          <div key={reason} className="rounded border border-line bg-white px-3 py-2">
            {reason}
          </div>
        ))}
      </div>

      {intelligence.warnings.length ? (
        <div className="mt-3 grid gap-2">
          {intelligence.warnings.slice(0, 2).map((warning) => (
            <div key={warning.message} className="rounded border border-caution/30 bg-amber-50 px-3 py-2 text-xs text-caution">
              {warning.message}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function TelemetryEvidenceCard({ telemetry }: { telemetry: TelemetrySummary | null }) {
  if (!telemetry || telemetry.sample_count === 0) {
    return (
      <div className="mt-3 rounded border border-line bg-white px-3 py-3 text-xs text-slate-600">
        No validated telemetry snapshots yet. Spec, market, and compatibility models are active.
      </div>
    );
  }
  const bottleneckRows = [
    ["CPU", telemetry.bottleneck.cpu_percent],
    ["GPU", telemetry.bottleneck.gpu_percent],
    ["VRAM", telemetry.bottleneck.vram_percent],
    ["Thermal", telemetry.bottleneck.thermal_percent],
    ["Driver", telemetry.bottleneck.driver_percent],
    ["Bandwidth", telemetry.bottleneck.bandwidth_percent]
  ] as const;
  return (
    <div className="mt-3 rounded border border-line bg-white px-3 py-3">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase text-slate-500">
            <Activity size={14} className="text-signal" aria-hidden />
            Telemetry evidence
          </div>
          <div className="flex flex-wrap gap-1.5 text-xs">
            <Badge text={`${telemetry.sample_count} samples`} tone="neutral" />
            <Badge text={`${telemetry.confidence} confidence`} tone="signal" />
            <Badge text={`${telemetry.primary_limiter.toUpperCase()} limited`} tone="violet" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs sm:w-64">
          <SmallMetric icon={<Flame size={14} />} label="FPS" value={metricText(telemetry.average_fps)} />
          <SmallMetric icon={<Thermometer size={14} />} label="Thermal" value={telemetry.thermal_throttling_risk} />
        </div>
      </div>
      <div className="grid gap-3 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="grid gap-2 text-xs">
          <SmallMetric icon={<Activity size={14} />} label="1% low" value={metricText(telemetry.one_percent_low_fps)} />
          <SmallMetric
            icon={<Clock3 size={14} />}
            label="Pacing"
            value={metricText(telemetry.frame_time_instability_score, "/100")}
          />
          <SmallMetric icon={<Cpu size={14} />} label="Power" value={metricText(telemetry.peak_power_w, " W")} />
        </div>
        <div className="rounded border border-line bg-panel px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Observed bottleneck</div>
          <div className="grid gap-2">
            {bottleneckRows.map(([label, value]) => (
              <div key={label} className="grid grid-cols-[64px_1fr_42px] items-center gap-2 text-xs">
                <span className="text-slate-600">{label}</span>
                <div className="h-2 overflow-hidden rounded bg-white">
                  <div className="h-full rounded bg-signal" style={{ width: `${Math.max(3, value)}%` }} />
                </div>
                <span className="text-right font-semibold text-ink">{value.toFixed(0)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5 text-xs">
        {telemetry.covered_resolutions.map((resolution) => (
          <Badge key={resolution} text={resolution} tone="neutral" />
        ))}
        {telemetry.latest_driver_versions.slice(0, 2).map((driver) => (
          <Badge key={driver} text={driver} tone="neutral" />
        ))}
      </div>
    </div>
  );
}

function TelemetryReasoningCard({ reasoning }: { reasoning: TelemetryReasoningReport | null }) {
  if (!reasoning || reasoning.sample_size === 0) {
    return (
      <div className="mt-3 rounded border border-line bg-white px-3 py-3 text-xs text-slate-600">
        Behavior reasoning will activate after validated telemetry is attached to this product.
      </div>
    );
  }
  const primaryAnomalies = reasoning.anomalies.slice(0, 3);
  const primaryBottlenecks = reasoning.bottleneck_explanations.slice(0, 3);
  return (
    <div className="mt-3 rounded border border-line bg-white px-3 py-3">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase text-slate-500">
            <AlertTriangle size={14} className="text-caution" aria-hidden />
            Behavior reasoning
          </div>
          <div className="flex flex-wrap gap-1.5 text-xs">
            <Badge text={`${Math.round(reasoning.confidence_score * 100)}% confidence`} tone="signal" />
            <Badge text={`${reasoning.sample_size} samples`} tone="neutral" />
            {reasoning.predictions[0] ? (
              <Badge text={`${reasoning.predictions[0].predicted_limitation.toUpperCase()} risk`} tone="violet" />
            ) : null}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs sm:w-60">
          <SmallMetric icon={<AlertTriangle size={14} />} label="Anomalies" value={String(reasoning.anomalies.length)} />
          <SmallMetric icon={<Activity size={14} />} label="Patterns" value={String(reasoning.patterns.length)} />
        </div>
      </div>

      {primaryAnomalies.length ? (
        <div className="grid gap-2">
          {primaryAnomalies.map((anomaly) => (
            <div
              key={anomaly.id}
              className={`rounded border px-3 py-2 text-xs ${severityClasses(anomaly.severity)}`}
            >
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <span className="font-semibold">{anomaly.title}</span>
                <span className="rounded bg-white/70 px-1.5 py-0.5 uppercase">{anomaly.severity}</span>
                <span>{Math.round(anomaly.confidence_score * 100)}%</span>
              </div>
              <div>{anomaly.explanation}</div>
              {anomaly.likely_causes.length ? (
                <div className="mt-1 text-slate-600">Likely: {anomaly.likely_causes.slice(0, 2).join(", ")}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded border border-line bg-panel px-3 py-2 text-xs text-slate-600">
          No anomaly threshold is currently crossed.
        </div>
      )}

      {reasoning.ai_explanation ? (
        <div className="mt-3 rounded border border-line bg-panel px-3 py-2 text-xs leading-5 text-slate-700 whitespace-pre-line">
          {reasoning.ai_explanation}
        </div>
      ) : null}

      {primaryBottlenecks.length ? (
        <div className="mt-3 rounded border border-line bg-panel px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Bottleneck explanation</div>
          <div className="grid gap-2">
            {primaryBottlenecks.map((item) => (
              <div key={`${item.kind}-${item.percent}`} className="grid grid-cols-[76px_1fr] gap-2 text-xs">
                <span className="font-semibold uppercase text-ink">{item.kind}</span>
                <span className="text-slate-600">{item.reason}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {reasoning.workload_reasoning.length ? (
        <div className="mt-3 rounded border border-line bg-panel px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Workload reasoning</div>
          <div className="grid gap-1.5 text-xs text-slate-600">
            {reasoning.workload_reasoning.slice(0, 4).map((line) => (
              <div key={line}>{line}</div>
            ))}
          </div>
        </div>
      ) : null}

      {reasoning.driver_regressions.length || reasoning.predictions.length ? (
        <div className="mt-3 grid gap-2 lg:grid-cols-2">
          {reasoning.driver_regressions[0] ? (
            <div className="rounded border border-line bg-panel px-3 py-2 text-xs text-slate-600">
              <div className="mb-1 font-semibold text-ink">Driver regression</div>
              {reasoning.driver_regressions[0].explanation}
            </div>
          ) : null}
          {reasoning.predictions[0] ? (
            <div className="rounded border border-line bg-panel px-3 py-2 text-xs text-slate-600">
              <div className="mb-1 font-semibold text-ink">Predictive risk</div>
              {reasoning.predictions[0].explanation}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function CognitionCard({
  cognition,
  loading,
  product
}: {
  cognition: HardwareCognitionReport | null;
  loading: boolean;
  product?: ProductSearchResult;
}) {
  if (loading) return <div className="h-52 animate-pulse rounded-md border border-line bg-panel" />;
  if (!product) {
    return <div className="rounded-md border border-line bg-panel px-3 py-8 text-sm text-slate-600">No cognition target.</div>;
  }
  if (!cognition) {
    return (
      <div className="rounded-md border border-line bg-panel px-3 py-8 text-sm text-slate-600">
        Adaptive cognition is waiting for telemetry, predictions, or validation outcomes for this product.
      </div>
    );
  }
  const confidence = cognition.confidence;
  const metaSignals = [
    ...cognition.meta_reasoning.weak_evidence,
    ...cognition.meta_reasoning.telemetry_gaps,
    ...cognition.meta_reasoning.self_corrections
  ].slice(0, 5);
  return (
    <div className="rounded-md border border-line bg-panel p-3">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-ink">
            <BrainCircuit size={15} className="text-signal" aria-hidden />
            Adaptive cognition
          </div>
          <div className="flex flex-wrap gap-1.5 text-xs">
            <Badge text={`${scoreText(confidence.confidence_score)} confidence`} tone="signal" />
            <Badge text={`${scoreText(confidence.uncertainty_score)} uncertainty`} tone="violet" />
            <Badge text={`${cognition.reliability.validation_count} validations`} tone="neutral" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs sm:w-64">
          <SmallMetric icon={<ShieldCheck size={14} />} label="Evidence" value={scoreText(confidence.evidence_strength)} />
          <SmallMetric icon={<Activity size={14} />} label="Stability" value={scoreText(confidence.telemetry_stability)} />
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Confidence propagation</div>
          <div className="grid gap-2">
            {[
              ["Reliability", cognition.reliability.reliability_score],
              ["Calibration error", cognition.reliability.calibration_error],
              ["Contradiction rate", cognition.reliability.contradiction_rate],
              ["Workload consistency", confidence.workload_consistency]
            ].map(([label, value]) => (
              <div key={label} className="grid grid-cols-[116px_1fr_44px] items-center gap-2 text-xs">
                <span className="text-slate-600">{label}</span>
                <div className="h-2 overflow-hidden rounded bg-slate-100">
                  <div className="h-full rounded bg-signal" style={{ width: `${Math.max(3, Number(value) * 100)}%` }} />
                </div>
                <span className="text-right font-semibold text-ink">{scoreText(Number(value))}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Meta-reasoning</div>
          {metaSignals.length ? (
            <div className="grid gap-1.5 text-xs text-slate-600">
              {metaSignals.map((signal) => (
                <div key={signal}>{signal}</div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-slate-600">No weak evidence path is currently above threshold.</div>
          )}
        </div>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Active predictions</div>
          {cognition.active_predictions.length ? (
            <div className="grid gap-2">
              {cognition.active_predictions.slice(0, 4).map((prediction) => (
                <div key={prediction.id} className="rounded bg-panel px-2 py-2 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold uppercase text-ink">{prediction.kind.replaceAll("_", " ")}</span>
                    <span className="font-semibold text-signal">{scoreText(prediction.confidence.confidence_score)}</span>
                  </div>
                  <div className="mt-1 text-slate-600">{predictionValue(prediction)}</div>
                  <div className="mt-1 truncate text-slate-500">
                    {[prediction.workload, prediction.resolution, prediction.horizon].filter(Boolean).join(" / ")}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-slate-600">No prediction has enough telemetry signal yet.</div>
          )}
        </div>

        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Validation memory</div>
          {cognition.recent_validations.length ? (
            <div className="grid gap-2">
              {cognition.recent_validations.slice(0, 3).map((validation) => (
                <div key={validation.id} className={`rounded border px-2 py-2 text-xs ${severityClasses(validation.severity)}`}>
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="font-semibold uppercase">{validation.status.replaceAll("_", " ")}</span>
                    <span>{scoreText(validation.correctness_score)} correct</span>
                  </div>
                  <div>{validation.explanation}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-slate-600">Outcome validation has not been observed yet.</div>
          )}
        </div>
      </div>

      {cognition.contradictions.length ? (
        <div className="mt-3 grid gap-2">
          {cognition.contradictions.slice(0, 2).map((contradiction) => (
            <div key={contradiction.id} className={`rounded border px-3 py-2 text-xs ${severityClasses(contradiction.severity)}`}>
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <span className="font-semibold">{contradiction.kind.replaceAll("_", " ")}</span>
                <span>{scoreText(contradiction.confidence_score)} confidence</span>
              </div>
              <div>{contradiction.explanation}</div>
            </div>
          ))}
        </div>
      ) : null}

      {cognition.learning_summary.length ? (
        <div className="mt-3 grid gap-1.5 text-xs text-slate-600">
          {cognition.learning_summary.slice(0, 3).map((line) => (
            <div key={line} className="rounded border border-line bg-white px-3 py-2">
              {line}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function GovernanceCard({
  governance,
  loading,
  product
}: {
  governance: ReasoningGovernanceReport | null;
  loading: boolean;
  product?: ProductSearchResult;
}) {
  if (loading) return <div className="h-56 animate-pulse rounded-md border border-line bg-panel" />;
  if (!product) {
    return <div className="rounded-md border border-line bg-panel px-3 py-8 text-sm text-slate-600">No governance target.</div>;
  }
  if (!governance) {
    return (
      <div className="rounded-md border border-line bg-panel px-3 py-8 text-sm text-slate-600">
        Reasoning governance is waiting for cognition state, telemetry evidence, or validation history.
      </div>
    );
  }
  const metrics = governance.metrics;
  const stability = governance.stability;
  const primarySignals = governance.graph_hygiene.slice(0, 3);
  const primaryActions = governance.stabilization_actions.slice(0, 4);
  return (
    <div className="rounded-md border border-line bg-panel p-3">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-ink">
            <ShieldCheck size={15} className="text-signal" aria-hidden />
            Reasoning governance
          </div>
          <div className="flex flex-wrap gap-1.5 text-xs">
            <span className={`rounded px-2 py-1 font-medium ${governanceStatusClasses(governance.status)}`}>
              {governance.status}
            </span>
            <Badge text={`${scoreText(metrics.overall_health)} health`} tone="signal" />
            <Badge text={`${scoreText(stability.governed_confidence)} governed confidence`} tone="violet" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs sm:w-64">
          <SmallMetric icon={<Activity size={14} />} label="Drift" value={scoreText(metrics.confidence_drift)} />
          <SmallMetric icon={<AlertTriangle size={14} />} label="Recursive" value={scoreText(metrics.recursive_feedback_risk)} />
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[1fr_0.95fr]">
        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Cognitive health monitor</div>
          <div className="grid gap-2">
            {[
              ["Reasoning quality", metrics.reasoning_quality],
              ["Calibration risk", metrics.calibration_risk],
              ["Contradiction density", metrics.contradiction_density],
              ["Evidence decay", metrics.evidence_decay_pressure],
              ["Graph integrity", metrics.graph_integrity]
            ].map(([label, value]) => (
              <div key={label} className="grid grid-cols-[118px_1fr_44px] items-center gap-2 text-xs">
                <span className="text-slate-600">{label}</span>
                <div className="h-2 overflow-hidden rounded bg-slate-100">
                  <div
                    className={`h-full rounded ${label === "Graph integrity" || label === "Reasoning quality" ? "bg-signal" : "bg-caution"}`}
                    style={{ width: `${Math.max(3, Number(value) * 100)}%` }}
                  />
                </div>
                <span className="text-right font-semibold text-ink">{scoreText(Number(value))}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Stability controls</div>
          <div className="grid gap-2 text-xs">
            <SmallMetric icon={<ShieldCheck size={14} />} label="Ceiling" value={scoreText(stability.confidence_ceiling)} />
            <SmallMetric icon={<Activity size={14} />} label="Dampening" value={scoreText(stability.dampening_factor)} />
            <SmallMetric icon={<Clock3 size={14} />} label="Decay rate" value={scoreText(stability.decay_rate)} />
          </div>
          {stability.downgrade_reasons.length ? (
            <div className="mt-2 grid gap-1.5 text-xs text-slate-600">
              {stability.downgrade_reasons.slice(0, 3).map((reason) => (
                <div key={reason}>{reason}</div>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Consensus strategies</div>
          <div className="grid gap-2">
            {governance.consensus.map((score) => (
              <div key={score.strategy} className="rounded bg-panel px-2 py-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold uppercase text-ink">{score.strategy.replaceAll("_", " ")}</span>
                  <span className="font-semibold text-signal">{scoreText(score.confidence_score)}</span>
                </div>
                <div className="mt-1 text-slate-600">{score.rationale}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Evidence hygiene</div>
          {governance.evidence_decay.length ? (
            <div className="grid gap-2">
              {governance.evidence_decay.slice(0, 4).map((record) => (
                <div key={record.id} className="rounded bg-panel px-2 py-2 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-semibold text-ink">{record.source}</span>
                    <span className="uppercase text-slate-500">{record.status}</span>
                  </div>
                  <div className="mt-1 text-slate-600">
                    {scoreText(record.decayed_weight)} weight / {Math.round(record.age_days)} days
                  </div>
                  <div className="mt-1 text-slate-500">{record.reason}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-slate-600">No telemetry evidence has entered decay evaluation yet.</div>
          )}
        </div>
      </div>

      {primarySignals.length ? (
        <div className="mt-3 grid gap-2">
          {primarySignals.map((signal) => (
            <div key={signal.id} className={`rounded border px-3 py-2 text-xs ${severityClasses(signal.severity)}`}>
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <span className="font-semibold">{signal.kind.replaceAll("_", " ")}</span>
                <span>{scoreText(signal.confidence_score)} confidence</span>
              </div>
              <div>{signal.explanation}</div>
              {signal.mitigation.length ? (
                <div className="mt-1 text-slate-600">Mitigation: {signal.mitigation.slice(0, 2).join(", ")}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {primaryActions.length ? (
        <div className="mt-3 rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Self-stabilization actions</div>
          <div className="grid gap-2">
            {primaryActions.map((action) => (
              <div key={action.id} className={`rounded border px-2 py-2 text-xs ${severityClasses(action.severity)}`}>
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="font-semibold uppercase">{action.kind.replaceAll("_", " ")}</span>
                  <span>{action.status}</span>
                </div>
                <div>{action.reason}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {governance.governance_summary.length ? (
        <div className="mt-3 grid gap-1.5 text-xs text-slate-600">
          {governance.governance_summary.slice(0, 3).map((line) => (
            <div key={line} className="rounded border border-line bg-white px-3 py-2">
              {line}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function EvolutionCard({
  evolution,
  loading,
  product
}: {
  evolution: EvolutionOrchestrationReport | null;
  loading: boolean;
  product?: ProductSearchResult;
}) {
  if (loading) return <div className="h-56 animate-pulse rounded-md border border-line bg-panel" />;
  if (!product) {
    return <div className="rounded-md border border-line bg-panel px-3 py-8 text-sm text-slate-600">No evolution target.</div>;
  }
  if (!evolution) {
    return (
      <div className="rounded-md border border-line bg-panel px-3 py-8 text-sm text-slate-600">
        Evolution orchestration is waiting for governed cognition state and active policy context.
      </div>
    );
  }
  const metrics = evolution.metrics;
  const health = evolution.health_index;
  const blockingRules = evolution.enforcement.filter((item) => item.status !== "allow").slice(0, 4);
  const promotion = evolution.promotion_decisions.slice(0, 3);
  const rollback = evolution.rollback_events[0];
  return (
    <div className="rounded-md border border-line bg-panel p-3">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-ink">
            <BrainCircuit size={15} className="text-signal" aria-hidden />
            Evolution orchestration
          </div>
          <div className="flex flex-wrap gap-1.5 text-xs">
            <span className={`rounded px-2 py-1 font-medium ${governanceStatusClasses(evolution.status)}`}>
              {evolution.status}
            </span>
            <Badge text={`policy ${evolution.active_policy.version}`} tone="neutral" />
            <Badge text={`${scoreText(health.index)} health index`} tone="signal" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs sm:w-64">
          <SmallMetric icon={<Activity size={14} />} label="Velocity" value={scoreText(metrics.evolution_velocity)} />
          <SmallMetric icon={<ShieldCheck size={14} />} label="Policy drift" value={scoreText(metrics.policy_drift)} />
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[1fr_0.95fr]">
        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Cognitive health index</div>
          <div className="grid gap-2">
            {[
              ["Reasoning stability", health.reasoning_stability],
              ["Graph health", health.graph_health],
              ["Evidence freshness", health.evidence_freshness],
              ["Contradiction resilience", health.contradiction_resilience],
              ["Adaptation volatility", health.adaptation_volatility]
            ].map(([label, value]) => (
              <div key={label} className="grid grid-cols-[134px_1fr_44px] items-center gap-2 text-xs">
                <span className="text-slate-600">{label}</span>
                <div className="h-2 overflow-hidden rounded bg-slate-100">
                  <div className="h-full rounded bg-signal" style={{ width: `${Math.max(3, Number(value) * 100)}%` }} />
                </div>
                <span className="text-right font-semibold text-ink">{scoreText(Number(value))}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Policy envelope</div>
          <div className="grid gap-2 text-xs">
            <SmallMetric icon={<ShieldCheck size={14} />} label="Confidence max" value={scoreText(evolution.active_policy.confidence_ceiling_max)} />
            <SmallMetric icon={<Clock3 size={14} />} label="Freshness min" value={scoreText(evolution.active_policy.evidence_freshness_min)} />
            <SmallMetric icon={<AlertTriangle size={14} />} label="Contradictions" value={scoreText(evolution.active_policy.contradiction_tolerance)} />
          </div>
          <div className="mt-2 text-xs text-slate-600">{evolution.active_policy.change_reason}</div>
        </div>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Policy enforcement</div>
          {blockingRules.length ? (
            <div className="grid gap-2">
              {blockingRules.map((decision) => (
                <div key={decision.id} className={`rounded border px-2 py-2 text-xs ${severityClasses(decision.severity)}`}>
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="font-semibold uppercase">{decision.rule.replaceAll("_", " ")}</span>
                    <span>{decision.status}</span>
                  </div>
                  <div>
                    {scoreText(decision.observed_value)} observed / {scoreText(decision.threshold)} threshold
                  </div>
                  <div className="mt-1 text-slate-600">{decision.action}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-slate-600">All policy rules are inside the current envelope.</div>
          )}
        </div>

        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Sandbox promotion</div>
          {promotion.length ? (
            <div className="grid gap-2">
              {promotion.map((decision) => (
                <div key={decision.id} className="rounded bg-panel px-2 py-2 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-semibold text-ink">{decision.model_id.replace("strategy:", "")}</span>
                    <span className="uppercase text-slate-500">{decision.status}</span>
                  </div>
                  <div className="mt-1 text-slate-600">{scoreText(decision.prediction_accuracy)} predicted accuracy</div>
                  <div className="mt-1 text-slate-500">{decision.reason}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-slate-600">No sandboxed reasoning strategy is available for promotion.</div>
          )}
        </div>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Rollback readiness</div>
          {rollback ? (
            <div className={`rounded border px-2 py-2 text-xs ${rollback.status === "not_required" ? "border-line bg-panel text-slate-600" : "border-caution/30 bg-amber-50 text-caution"}`}>
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="font-semibold uppercase">{rollback.status.replaceAll("_", " ")}</span>
                <span>{rollback.from_policy_id}</span>
              </div>
              <div>{rollback.reason}</div>
            </div>
          ) : (
            <div className="text-xs text-slate-600">No rollback event has been emitted.</div>
          )}
        </div>

        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Long-term memory</div>
          <div className="grid gap-2">
            {evolution.memory_decisions.slice(0, 3).map((decision) => (
              <div key={decision.id} className="rounded bg-panel px-2 py-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-semibold text-ink">{decision.target}</span>
                  <span className="uppercase text-slate-500">{decision.status}</span>
                </div>
                <div className="mt-1 text-slate-600">{scoreText(decision.support_score)} support</div>
                <div className="mt-1 text-slate-500">{decision.reason}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {evolution.orchestration_summary.length ? (
        <div className="mt-3 grid gap-1.5 text-xs text-slate-600">
          {evolution.orchestration_summary.slice(0, 3).map((line) => (
            <div key={line} className="rounded border border-line bg-white px-3 py-2">
              {line}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function AlignmentCard({
  alignment,
  loading,
  product
}: {
  alignment: AlignmentInspectionReport | null;
  loading: boolean;
  product?: ProductSearchResult;
}) {
  if (loading) return <div className="h-56 animate-pulse rounded-md border border-line bg-panel" />;
  if (!product) {
    return <div className="rounded-md border border-line bg-panel px-3 py-8 text-sm text-slate-600">No alignment target.</div>;
  }
  if (!alignment) {
    return (
      <div className="rounded-md border border-line bg-panel px-3 py-8 text-sm text-slate-600">
        Cognitive alignment is waiting for system identity and evolution orchestration state.
      </div>
    );
  }
  const health = alignment.health;
  const objectives = [...alignment.identity.optimization_priorities].sort((a, b) => a.rank - b.rank).slice(0, 6);
  const primaryViolations = alignment.violations.slice(0, 3);
  return (
    <div className="rounded-md border border-line bg-panel p-3">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-ink">
            <ShieldCheck size={15} className="text-signal" aria-hidden />
            Cognitive alignment
          </div>
          <div className="flex flex-wrap gap-1.5 text-xs">
            <span className={`rounded px-2 py-1 font-medium ${alignmentStatusClasses(alignment.status)}`}>
              {alignment.status}
            </span>
            <Badge text={`identity ${alignment.identity.version}`} tone="neutral" />
            <Badge text={`${scoreText(health.overall_alignment)} aligned`} tone="signal" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs sm:w-64">
          <SmallMetric icon={<ShieldCheck size={14} />} label="Integrity" value={scoreText(health.confidence_integrity)} />
          <SmallMetric icon={<AlertTriangle size={14} />} label="Safety" value={scoreText(health.safety_priority_score)} />
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[1fr_0.95fr]">
        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Objective hierarchy</div>
          <div className="grid gap-2">
            {objectives.map((objective) => (
              <div key={objective.name} className="grid grid-cols-[24px_1fr_42px] items-center gap-2 text-xs">
                <span className="font-semibold text-ink">{objective.rank}</span>
                <span className="truncate text-slate-600">{objective.name.replaceAll("_", " ")}</span>
                <span className="text-right font-semibold text-ink">{scoreText(objective.weight)}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Alignment health</div>
          <div className="grid gap-2">
            {[
              ["Identity", health.identity_stability],
              ["Objectives", health.objective_coherence],
              ["Governance", health.governance_alignment],
              ["Transparency", health.transparency_score],
              ["Optimization", health.optimization_consistency]
            ].map(([label, value]) => (
              <div key={label} className="grid grid-cols-[88px_1fr_44px] items-center gap-2 text-xs">
                <span className="text-slate-600">{label}</span>
                <div className="h-2 overflow-hidden rounded bg-slate-100">
                  <div className="h-full rounded bg-signal" style={{ width: `${Math.max(3, Number(value) * 100)}%` }} />
                </div>
                <span className="text-right font-semibold text-ink">{scoreText(Number(value))}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Recommendation ethics</div>
          <div className="grid gap-2">
            {[
              ["Misleading confidence", alignment.ethics.misleading_confidence_risk],
              ["Unsafe recommendation", alignment.ethics.unsafe_recommendation_risk],
              ["Unstable config", alignment.ethics.unstable_configuration_risk],
              ["Biased optimization", alignment.ethics.biased_optimization_risk]
            ].map(([label, value]) => (
              <div key={label} className="grid grid-cols-[132px_1fr_44px] items-center gap-2 text-xs">
                <span className="text-slate-600">{label}</span>
                <div className="h-2 overflow-hidden rounded bg-slate-100">
                  <div className="h-full rounded bg-caution" style={{ width: `${Math.max(3, Number(value) * 100)}%` }} />
                </div>
                <span className="text-right font-semibold text-ink">{scoreText(Number(value))}</span>
              </div>
            ))}
          </div>
          {alignment.ethics.notes.length ? (
            <div className="mt-2 grid gap-1.5 text-xs text-slate-600">
              {alignment.ethics.notes.slice(0, 3).map((note) => (
                <div key={note}>{note}</div>
              ))}
            </div>
          ) : null}
        </div>

        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Constitution</div>
          <div className="grid gap-1.5 text-xs text-slate-600">
            {alignment.identity.constitution.non_overridable_constraints.slice(0, 4).map((constraint) => (
              <div key={constraint}>{constraint}</div>
            ))}
          </div>
        </div>
      </div>

      {primaryViolations.length ? (
        <div className="mt-3 grid gap-2">
          {primaryViolations.map((violation) => (
            <div key={violation.id} className={`rounded border px-3 py-2 text-xs ${severityClasses(violation.severity)}`}>
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <span className="font-semibold">{violation.kind.replaceAll("_", " ")}</span>
                <span>{scoreText(violation.confidence_score)} confidence</span>
              </div>
              <div>{violation.explanation}</div>
              {violation.mitigation.length ? (
                <div className="mt-1 text-slate-600">Mitigation: {violation.mitigation.slice(0, 2).join(", ")}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Explicit tradeoffs</div>
          <div className="grid gap-2">
            {alignment.tradeoffs.slice(0, 3).map((tradeoff) => (
              <div key={tradeoff.id} className="rounded bg-panel px-2 py-2 text-xs">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="font-semibold text-ink">
                    {tradeoff.primary_objective.replaceAll("_", " ")}
                  </span>
                  <span className={tradeoff.acceptable ? "text-signal" : "text-caution"}>
                    {tradeoff.acceptable ? "accepted" : "blocked"}
                  </span>
                </div>
                <div className="text-slate-600">{tradeoff.resolution}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Rollback support</div>
          {alignment.rollback[0] ? (
            <div className={`rounded border px-2 py-2 text-xs ${alignment.rollback[0].status === "not_required" ? "border-line bg-panel text-slate-600" : "border-caution/30 bg-amber-50 text-caution"}`}>
              <div className="mb-1 font-semibold uppercase">{alignment.rollback[0].status.replaceAll("_", " ")}</div>
              <div>{alignment.rollback[0].reason}</div>
            </div>
          ) : (
            <div className="text-xs text-slate-600">No alignment rollback path has been emitted.</div>
          )}
        </div>
      </div>

      {alignment.alignment_summary.length ? (
        <div className="mt-3 grid gap-1.5 text-xs text-slate-600">
          {alignment.alignment_summary.slice(0, 3).map((line) => (
            <div key={line} className="rounded border border-line bg-white px-3 py-2">
              {line}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function AutonomyCard({
  autonomy,
  loading,
  product
}: {
  autonomy: AutonomousCognitionReport | null;
  loading: boolean;
  product?: ProductSearchResult;
}) {
  if (loading) return <div className="h-56 animate-pulse rounded-md border border-line bg-panel" />;
  if (!product) {
    return <div className="rounded-md border border-line bg-panel px-3 py-8 text-sm text-slate-600">No autonomous target.</div>;
  }
  if (!autonomy) {
    return (
      <div className="rounded-md border border-line bg-panel px-3 py-8 text-sm text-slate-600">
        Autonomous cognition is waiting for alignment, governance, and telemetry state.
      </div>
    );
  }
  const health = autonomy.health;
  const priorityTasks = [...autonomy.tasks].sort((a, b) => b.priority_score - a.priority_score).slice(0, 4);
  const priorityEvents = [...autonomy.events].sort((a, b) => b.priority_score - a.priority_score).slice(0, 4);
  const activeAgents = autonomy.agents.filter((agent) => agent.status === "active").length;
  const approvals = autonomy.oversight.filter((action) => action.status === "required");
  return (
    <div className="rounded-md border border-line bg-panel p-3">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-ink">
            <Activity size={15} className="text-signal" aria-hidden />
            Autonomous cognition
          </div>
          <div className="flex flex-wrap gap-1.5 text-xs">
            <span className={`rounded px-2 py-1 font-medium ${autonomyStatusClasses(autonomy.status)}`}>
              {autonomy.status}
            </span>
            <Badge text={`${activeAgents}/${autonomy.agents.length} agents active`} tone="neutral" />
            <Badge text={`${scoreText(health.overall_autonomy_health)} health`} tone="signal" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs sm:w-64">
          <SmallMetric icon={<ShieldCheck size={14} />} label="Safety" value={scoreText(health.safety_stability_score)} />
          <SmallMetric icon={<Clock3 size={14} />} label="Queue" value={scoreText(health.queue_pressure)} />
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[1fr_0.95fr]">
        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Active agents</div>
          <div className="grid gap-2 sm:grid-cols-2">
            {autonomy.agents.slice(0, 8).map((agent) => (
              <div key={agent.id} className="rounded bg-panel px-2 py-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-semibold text-ink">{agent.name}</span>
                  <span className={agent.status === "degraded" ? "text-caution" : "text-slate-500"}>
                    {agent.status}
                  </span>
                </div>
                <div className="mt-1 text-slate-600">{scoreText(agent.priority_weight)} priority</div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Cognitive health</div>
          <div className="grid gap-2">
            {[
              ["Contradictions", health.contradiction_resolution_score],
              ["Telemetry", health.telemetry_freshness_score],
              ["Governance", health.governance_compliance_score],
              ["Interventions", health.intervention_effectiveness],
              ["Agents", health.agent_availability]
            ].map(([label, value]) => (
              <div key={label} className="grid grid-cols-[96px_1fr_44px] items-center gap-2 text-xs">
                <span className="text-slate-600">{label}</span>
                <div className="h-2 overflow-hidden rounded bg-slate-100">
                  <div className="h-full rounded bg-signal" style={{ width: `${Math.max(3, Number(value) * 100)}%` }} />
                </div>
                <span className="text-right font-semibold text-ink">{scoreText(Number(value))}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Event-driven queue</div>
          {priorityEvents.length ? (
            <div className="grid gap-2">
              {priorityEvents.map((event) => (
                <div key={event.id} className={`rounded border px-2 py-2 text-xs ${severityClasses(event.severity)}`}>
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="font-semibold uppercase">{event.kind.replaceAll("_", " ")}</span>
                    <span>{scoreText(event.priority_score)}</span>
                  </div>
                  <div>{event.message}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-slate-600">No cognition events are waiting in the queue.</div>
          )}
        </div>

        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Agent tasks</div>
          {priorityTasks.length ? (
            <div className="grid gap-2">
              {priorityTasks.map((task) => (
                <div key={task.id} className="rounded bg-panel px-2 py-2 text-xs">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="truncate font-semibold text-ink">{task.kind.replaceAll("_", " ")}</span>
                    <span className={task.requires_human_approval ? "text-caution" : "text-slate-500"}>
                      {task.status.replaceAll("_", " ")}
                    </span>
                  </div>
                  <div className="text-slate-600">{task.reason}</div>
                  {task.expected_actions[0] ? <div className="mt-1 text-slate-500">{task.expected_actions[0]}</div> : null}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-slate-600">No autonomous tasks are queued.</div>
          )}
        </div>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Interventions</div>
          {autonomy.interventions.length ? (
            <div className="grid gap-2">
              {autonomy.interventions.slice(0, 4).map((intervention) => (
                <div key={intervention.id} className={`rounded border px-2 py-2 text-xs ${severityClasses(intervention.severity)}`}>
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="font-semibold uppercase">{intervention.kind.replaceAll("_", " ")}</span>
                    <span>{intervention.status.replaceAll("_", " ")}</span>
                  </div>
                  <div>{intervention.reason}</div>
                  {intervention.confidence_delta ? (
                    <div className="mt-1 text-slate-600">Confidence delta {Math.round(intervention.confidence_delta * 100)}%</div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-slate-600">No autonomous intervention has been emitted.</div>
          )}
        </div>

        <div className="rounded border border-line bg-white px-3 py-2">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Human oversight</div>
          {approvals.length ? (
            <div className="grid gap-2">
              {approvals.map((action) => (
                <div key={action.id} className="rounded border border-caution/30 bg-amber-50 px-2 py-2 text-xs text-caution">
                  <div className="mb-1 font-semibold uppercase">{action.action_type.replaceAll("_", " ")}</div>
                  <div>{action.reason}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-slate-600">
              Oversight hooks are available; no approval gate is blocking this product.
            </div>
          )}
        </div>
      </div>

      {autonomy.investigations.length || autonomy.signals.length ? (
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <div className="rounded border border-line bg-white px-3 py-2">
            <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Investigations</div>
            <div className="grid gap-2">
              {autonomy.investigations.slice(0, 3).map((investigation) => (
                <div key={investigation.id} className="rounded bg-panel px-2 py-2 text-xs">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="font-semibold text-ink">{investigation.status}</span>
                    <span>{scoreText(investigation.confidence_score)}</span>
                  </div>
                  <div className="text-slate-600">{investigation.hypothesis}</div>
                </div>
              ))}
              {!autonomy.investigations.length ? <div className="text-xs text-slate-600">No open investigation.</div> : null}
            </div>
          </div>

          <div className="rounded border border-line bg-white px-3 py-2">
            <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Inter-agent signals</div>
            <div className="grid gap-2">
              {autonomy.signals.slice(0, 3).map((signal) => (
                <div key={signal.id} className="rounded bg-panel px-2 py-2 text-xs">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="truncate font-semibold text-ink">
                      {signal.from_agent.replaceAll("_", " ")} to {signal.to_agent.replaceAll("_", " ")}
                    </span>
                    <span className="text-slate-500">{signal.channel.replaceAll("_", " ")}</span>
                  </div>
                  <div className="text-slate-600">{signal.message}</div>
                </div>
              ))}
              {!autonomy.signals.length ? <div className="text-xs text-slate-600">No inter-agent signal emitted.</div> : null}
            </div>
          </div>
        </div>
      ) : null}

      {autonomy.autonomy_summary.length ? (
        <div className="mt-3 grid gap-1.5 text-xs text-slate-600">
          {autonomy.autonomy_summary.slice(0, 3).map((line) => (
            <div key={line} className="rounded border border-line bg-white px-3 py-2">
              {line}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function HistoryChart({ history, loading }: { history: PriceHistoryPoint[]; loading: boolean }) {
  if (loading) return <div className="h-32 animate-pulse rounded-md border border-line bg-panel" />;
  if (history.length === 0) {
    return (
      <div className="rounded-md border border-line bg-panel px-3 py-8 text-sm text-slate-600">
        Historical snapshots will appear after refresh jobs complete.
      </div>
    );
  }
  const points = history.slice(-18);
  const max = Math.max(...points.map((point) => point.price));
  const min = Math.min(...points.map((point) => point.price));
  return (
    <div className="rounded-md border border-line bg-panel p-3">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
        <LineChart size={15} className="text-signal" aria-hidden />
        Price history
      </div>
      <div className="flex h-28 items-end gap-1" aria-label="Price history chart">
        {points.map((point) => {
          const height = max === min ? 55 : 20 + ((point.price - min) / (max - min)) * 78;
          return (
            <div
              key={`${point.vendor_name}-${point.timestamp}-${point.price}`}
              className="min-w-2 flex-1 rounded-t bg-signal"
              style={{ height: `${height}%` }}
              title={`${point.vendor_name}: ${point.currency} ${point.price.toFixed(2)}`}
            />
          );
        })}
      </div>
    </div>
  );
}

function SmallMetric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded border border-line bg-white px-2 py-2">
      <div className="mb-1 flex items-center gap-1 text-[11px] font-semibold uppercase text-slate-500">
        {icon}
        {label}
      </div>
      <div className="text-sm font-semibold text-ink">{value}</div>
    </div>
  );
}

function metricText(value?: number, suffix = "") {
  return typeof value === "number" ? `${Math.round(value)}${suffix}` : "Pending";
}

function scoreText(score?: number) {
  return typeof score === "number" ? `${Math.round(score * 100)}%` : "Pending";
}

function predictionValue(prediction: HardwareCognitionReport["active_predictions"][number]) {
  if (prediction.predicted_limiter) {
    return `Limiter: ${prediction.predicted_limiter.toUpperCase()}`;
  }
  if (typeof prediction.predicted_value === "number") {
    const unit = prediction.predicted_unit ? ` ${prediction.predicted_unit}` : "";
    return `Expected: ${Math.round(prediction.predicted_value)}${unit}`;
  }
  return "Expected outcome remains uncertain.";
}

function governanceStatusClasses(status: ReasoningGovernanceReport["status"]) {
  if (status === "quarantined" || status === "unstable") {
    return "bg-red-50 text-danger";
  }
  if (status === "degraded" || status === "watch") {
    return "bg-amber-50 text-caution";
  }
  return "bg-emerald-50 text-signal";
}

function alignmentStatusClasses(status: AlignmentInspectionReport["status"]) {
  if (status === "violated" || status === "misaligned") {
    return "bg-red-50 text-danger";
  }
  if (status === "watch") {
    return "bg-amber-50 text-caution";
  }
  return "bg-emerald-50 text-signal";
}

function autonomyStatusClasses(status: AutonomousCognitionReport["status"]) {
  if (status === "blocked" || status === "degraded") {
    return "bg-red-50 text-danger";
  }
  if (status === "watch") {
    return "bg-amber-50 text-caution";
  }
  return "bg-emerald-50 text-signal";
}

function severityClasses(severity: TelemetrySeverity) {
  if (severity === "critical") {
    return "border-danger/30 bg-red-50 text-danger";
  }
  if (severity === "warning") {
    return "border-caution/30 bg-amber-50 text-caution";
  }
  return "border-line bg-panel text-slate-600";
}

function Badge({ text, tone }: { text: string; tone: "signal" | "violet" | "neutral" }) {
  const classes =
    tone === "signal"
      ? "bg-emerald-50 text-signal"
      : tone === "violet"
        ? "bg-violet-50 text-violet"
        : "bg-white text-slate-600";
  return <span className={`rounded px-2 py-1 font-medium ${classes}`}>{text}</span>;
}
