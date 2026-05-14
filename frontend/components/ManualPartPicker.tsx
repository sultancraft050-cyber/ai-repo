"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  ArrowUpDown,
  CheckCircle2,
  Gauge,
  Loader2,
  Plus,
  Search,
  SlidersHorizontal,
  Trash2,
  X,
  Zap
} from "lucide-react";
import { searchProducts, validateAndMeasure } from "@/lib/api";
import {
  componentOrder,
  selectionKeyByKind,
  type BuildPreferences,
  type ComponentKind,
  type CompatibilityResponse,
  type PerformanceResponse,
  type ProductSearchResult,
  type Resolution,
  type SelectedComponents
} from "@/types/builder";

type ProductMap = Record<ComponentKind, ProductSearchResult[]>;
type SelectionMap = Partial<Record<ComponentKind, ProductSearchResult>>;
type CategoryFailures = Partial<Record<ComponentKind, string>>;
type SortMode = "recommended" | "price_low" | "price_high" | "name";

const categoryCopy: Record<ComponentKind, string> = {
  CPU: "Processor",
  GPU: "Graphics card",
  Motherboard: "Motherboard",
  RAM: "Memory",
  Storage: "Storage",
  Cooler: "CPU Cooler",
  Case: "Case",
  PSU: "Power Supply"
};

const refreshOptions = [60, 120, 144, 165, 240] as const;

function emptyProducts(): ProductMap {
  return componentOrder.reduce(
    (accumulator, kind) => ({
      ...accumulator,
      [kind]: []
    }),
    {} as ProductMap
  );
}

export function ManualPartPicker() {
  const [products, setProducts] = useState<ProductMap>(emptyProducts);
  const [failures, setFailures] = useState<CategoryFailures>({});
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<SelectionMap>({});
  const [activeKind, setActiveKind] = useState<ComponentKind | null>(null);
  const [resolution, setResolution] = useState<Resolution>("1440p");
  const [refreshRate, setRefreshRate] = useState<(typeof refreshOptions)[number]>(144);
  const [compatibility, setCompatibility] = useState<CompatibilityResponse | null>(null);
  const [performance, setPerformance] = useState<PerformanceResponse | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);

  const selectedCount = Object.keys(selected).length;
  const missingCategories = componentOrder.filter((kind) => !selected[kind]);
  const selection = useMemo(() => toSelectedComponents(selected), [selected]);
  const preferences = useMemo<BuildPreferences>(
    () => ({
      purpose: "gaming",
      resolution,
      display_refresh_hz: refreshRate,
      region: "SA",
      brand_bias: [],
      size: "ATX",
      noise_preference: "balanced",
      upgrade_path_priority: 0.65
    }),
    [refreshRate, resolution]
  );

  const selectedRows = componentOrder
    .map((kind) => selected[kind])
    .filter(Boolean) as ProductSearchResult[];
  const priceRows = selectedRows.map((product) => ({ product, price: bestSarPrice(product) }));
  const knownPriceTotal = priceRows.reduce((total, row) => total + (row.price?.amount ?? 0), 0);
  const missingPrices = priceRows.filter((row) => !row.price).map((row) => row.product.category);
  const visibleWarnings = [
    ...Object.entries(failures).map(([kind, message]) => `${kind}: ${message}`),
    ...missingPrices.map((category) => `${category}: no SAR price available, so it is not included in the total.`),
    ...(compatibility?.checks.filter((check) => check.status !== "pass").map((check) => check.details) ?? [])
  ];

  useEffect(() => {
    let cancelled = false;
    async function loadProducts() {
      setLoading(true);
      setFailures({});
      const results = await Promise.allSettled(
        componentOrder.map(async (kind) => ({
          kind,
          products: await searchProducts({ category: kind, region: "SA", limit: 100 })
        }))
      );
      if (cancelled) return;
      const next = emptyProducts();
      const nextFailures: CategoryFailures = {};
      results.forEach((result, index) => {
        const kind = componentOrder[index];
        if (result.status === "fulfilled") {
          next[result.value.kind] = result.value.products;
        } else {
          const message = result.reason instanceof Error ? result.reason.message : "Unable to load this category.";
          nextFailures[kind] = message;
        }
      });
      setProducts(next);
      setFailures(nextFailures);
      setLoading(false);
    }
    loadProducts();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function validateSelection() {
      if (selectedCount === 0) {
        setCompatibility(null);
        setPerformance(null);
        setValidationError(null);
        return;
      }
      setValidating(true);
      setValidationError(null);
      try {
        const result = await validateAndMeasure(selection, preferences);
        if (cancelled) return;
        setCompatibility(result.compatibility);
        setPerformance(result.performance);
      } catch (error) {
        if (cancelled) return;
        setValidationError(error instanceof Error ? error.message : "Unable to validate this manual build.");
        setCompatibility(null);
        setPerformance(null);
      } finally {
        if (!cancelled) setValidating(false);
      }
    }
    validateSelection();
    return () => {
      cancelled = true;
    };
  }, [preferences, selectedCount, selection]);

  function chooseProduct(kind: ComponentKind, product: ProductSearchResult) {
    setSelected((current) => ({ ...current, [kind]: product }));
    setActiveKind(null);
  }

  function removeProduct(kind: ComponentKind) {
    setSelected((current) => {
      const next = { ...current };
      delete next[kind];
      return next;
    });
  }

  return (
    <section id="manual-builder" className="scroll-mt-20 rounded-lg border border-line bg-white shadow-tight">
      <div className="border-b border-line p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="mb-1 text-xs font-semibold uppercase text-signal">Manual builder</div>
            <h2 className="text-xl font-semibold text-ink">Pick every part yourself</h2>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted">
              Click Add on any row to open the market browser. It shows the Saudi catalog for that part type with search,
              sorting, filters, and Saudi prices.
            </p>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="text-xs font-semibold uppercase text-muted">
              Resolution
              <select
                value={resolution}
                onChange={(event) => setResolution(event.target.value as Resolution)}
                className="mt-1 h-10 w-full rounded-md border border-line bg-panel px-3 text-sm font-semibold normal-case text-ink"
              >
                <option value="1080p">1080p</option>
                <option value="1440p">1440p</option>
                <option value="4K">4K</option>
              </select>
            </label>
            <label className="text-xs font-semibold uppercase text-muted">
              Refresh
              <select
                value={refreshRate}
                onChange={(event) => setRefreshRate(Number(event.target.value) as (typeof refreshOptions)[number])}
                className="mt-1 h-10 w-full rounded-md border border-line bg-panel px-3 text-sm font-semibold normal-case text-ink"
              >
                {refreshOptions.map((rate) => (
                  <option key={rate} value={rate}>
                    {rate} Hz
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
      </div>

      <div className="grid gap-4 p-4 xl:grid-cols-[1fr_340px]">
        <div className="overflow-hidden rounded-lg border border-line">
          <div className="flex items-center gap-2 border-b border-line bg-[#0b101d] px-3 py-3 text-sm font-semibold text-ink">
            <span className="border-b-2 border-ink pb-2">Parts List</span>
            <span className="pb-2 text-muted">Price History</span>
          </div>
          <div className="border-b border-line bg-panel px-3 py-2 text-sm font-semibold text-ink">
            Saudi market catalog, compatible checks after selection
          </div>
          {componentOrder.map((kind) => (
            <PartRow
              key={kind}
              kind={kind}
              count={products[kind].length}
              selected={selected[kind]}
              loading={loading}
              failure={failures[kind]}
              onAdd={() => setActiveKind(kind)}
              onRemove={() => removeProduct(kind)}
            />
          ))}
        </div>

        <aside className="grid content-start gap-3">
          <div className="rounded-lg border border-line bg-panel p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-base font-semibold text-ink">Build summary</h3>
              {validating ? <Loader2 size={18} className="animate-spin text-signal" aria-label="Calculating build" /> : null}
            </div>
            <div className="grid gap-2">
              <SummaryMetric label="Selected" value={`${selectedCount}/8 parts`} />
              <SummaryMetric label="Known SAR total" value={knownPriceTotal ? formatSar(knownPriceTotal) : "No prices yet"} />
              <SummaryMetric
                label="Estimated wattage"
                value={
                  compatibility?.total_power_draw_w
                    ? `${Math.round(compatibility.total_power_draw_w)}W draw`
                    : "Select more parts"
                }
                icon={<Zap size={15} />}
              />
              <SummaryMetric
                label="Recommended PSU"
                value={
                  compatibility?.required_psu_w
                    ? `${Math.round(compatibility.required_psu_w)}W or higher`
                    : "Waiting for power data"
                }
              />
              <SummaryMetric
                label="Estimated FPS"
                value={performance ? `${Math.round(performance.expected_fps)} FPS avg` : "CPU + GPU required"}
                icon={<Gauge size={15} />}
              />
              <SummaryMetric label="1% low" value={performance ? `${Math.round(performance.one_percent_low_fps)} FPS` : "Not ready"} />
            </div>
          </div>

          <div className="rounded-lg border border-line bg-panel p-4">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
              {selectedCount === 8 && compatibility?.valid ? (
                <CheckCircle2 size={16} className="text-signal" aria-hidden />
              ) : (
                <AlertTriangle size={16} className="text-caution" aria-hidden />
              )}
              Final check
            </div>
            {selectedCount < 8 ? (
              <p className="text-sm leading-6 text-muted">
                Missing: {missingCategories.join(", ")}. Pick every required part to finish the manual build.
              </p>
            ) : compatibility?.valid ? (
              <p className="text-sm leading-6 text-muted">
                All core parts are selected and compatibility checks passed. Verify store pages before buying.
              </p>
            ) : (
              <p className="text-sm leading-6 text-muted">
                All parts are selected, but compatibility or data warnings still need review.
              </p>
            )}
            {validationError ? <p className="mt-2 text-sm leading-6 text-danger">{validationError}</p> : null}
          </div>

          <div className="rounded-lg border border-line bg-panel p-4">
            <div className="mb-2 text-sm font-semibold text-ink">Build notes</div>
            {visibleWarnings.length ? (
              <ul className="grid gap-2 text-sm leading-5 text-muted">
                {visibleWarnings.slice(0, 6).map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : (
              <p className="text-sm leading-6 text-muted">
                Pick all required parts to see compatibility, wattage, and FPS estimates.
              </p>
            )}
          </div>
        </aside>
      </div>

      {activeKind ? (
        <ProductPickerModal
          kind={activeKind}
          products={products[activeKind]}
          selected={selected[activeKind]}
          buildPrice={knownPriceTotal}
          buildWattage={compatibility?.total_power_draw_w ?? 0}
          loading={loading}
          failure={failures[activeKind]}
          onClose={() => setActiveKind(null)}
          onSelect={(product) => chooseProduct(activeKind, product)}
        />
      ) : null}
    </section>
  );
}

function PartRow({
  kind,
  count,
  selected,
  loading,
  failure,
  onAdd,
  onRemove
}: {
  kind: ComponentKind;
  count: number;
  selected?: ProductSearchResult;
  loading: boolean;
  failure?: string;
  onAdd: () => void;
  onRemove: () => void;
}) {
  const price = selected ? bestSarPrice(selected) : null;

  return (
    <div className="grid min-h-[64px] grid-cols-[128px_1fr_auto] items-center gap-3 border-b border-line px-3 py-3 last:border-b-0">
      <div>
        <span className="inline-flex rounded-full border border-line bg-panel px-2 py-1 text-sm font-semibold text-muted">
          {categoryCopy[kind]}
        </span>
      </div>

      <div className="min-w-0">
        {selected ? (
          <div className="flex min-w-0 items-center gap-3">
            {selected.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={selected.image_url} alt="" className="hidden h-11 w-14 rounded border border-line bg-white object-contain sm:block" />
            ) : null}
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-ink">{displayProductName(selected)}</div>
              <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted">
                <span>{price ? formatSar(price.amount) : "No SAR price"}</span>
                <span>{displayStoreName(price?.vendor ?? selected.current_recommended_vendor ?? selected.lowest_market_vendor)}</span>
                <span className="text-signal">Selected</span>
              </div>
            </div>
          </div>
        ) : (
          <div className="text-sm text-muted">
            {failure ?? (loading ? "Loading market products..." : `${count} market product${count === 1 ? "" : "s"} available`)}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        {selected ? (
          <button
            type="button"
            onClick={onRemove}
            className="grid h-8 w-8 place-items-center rounded-md border border-line bg-panel text-muted hover:text-danger"
            aria-label={`Remove ${kind}`}
            title={`Remove ${kind}`}
          >
            <Trash2 size={15} aria-hidden />
          </button>
        ) : null}
        <button
          type="button"
          onClick={onAdd}
          disabled={loading || Boolean(failure)}
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line bg-panel px-3 text-sm font-semibold text-ink hover:border-signal disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Plus size={15} aria-hidden />
          {selected ? `Change ${kind}` : `Add ${kind}`}
        </button>
      </div>
    </div>
  );
}

function ProductPickerModal({
  kind,
  products,
  selected,
  buildPrice,
  buildWattage,
  loading,
  failure,
  onClose,
  onSelect
}: {
  kind: ComponentKind;
  products: ProductSearchResult[];
  selected?: ProductSearchResult;
  buildPrice: number;
  buildWattage: number;
  loading: boolean;
  failure?: string;
  onClose: () => void;
  onSelect: (product: ProductSearchResult) => void;
}) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortMode>("recommended");
  const [brand, setBrand] = useState<string>("all");
  const [onlyPriced, setOnlyPriced] = useState(false);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose]);

  const groupedProducts = useMemo(() => cheapestProducts(products), [products]);
  const brands = useMemo(
    () =>
      Array.from(new Set(groupedProducts.map((product) => product.brand).filter(Boolean) as string[]))
        .sort((a, b) => a.localeCompare(b))
        .slice(0, 10),
    [groupedProducts]
  );
  const priceBounds = useMemo(() => {
    const prices = groupedProducts
      .map((product) => bestSarPrice(product)?.amount)
      .filter((value): value is number => typeof value === "number");
    return {
      min: prices.length ? Math.min(...prices) : null,
      max: prices.length ? Math.max(...prices) : null
    };
  }, [groupedProducts]);
  const visible = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return groupedProducts
      .filter((product) => {
        if (normalizedQuery) {
          const haystack = `${displayProductName(product)} ${product.brand ?? ""} ${product.model ?? ""}`.toLowerCase();
          if (!haystack.includes(normalizedQuery)) return false;
        }
        if (brand !== "all" && product.brand !== brand) return false;
        if (onlyPriced && !bestSarPrice(product)) return false;
        return true;
      })
      .sort((left, right) => productSort(left, right, sort));
  }, [brand, groupedProducts, onlyPriced, query, sort]);

  return (
    <div className="fixed inset-0 z-50 bg-black/76 p-2 backdrop-blur-sm sm:p-5" role="dialog" aria-modal="true" aria-label={`Add ${kind}`}>
      <div className="mx-auto grid h-full max-w-7xl overflow-hidden rounded-lg border border-line bg-[#0b101d] shadow-tight lg:grid-cols-[250px_1fr]">
        <aside className="hidden overflow-y-auto border-r border-line bg-[#080d18] p-4 lg:block">
          <div className="mb-5 flex items-center gap-2">
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-signal text-slate-950">
              <Plus size={18} aria-hidden />
            </span>
            <div>
              <div className="text-sm font-bold text-ink">Quick Add</div>
              <div className="text-xs text-muted">{categoryCopy[kind]}</div>
            </div>
          </div>

          <div className="rounded-lg border border-line bg-panel p-3">
            <div className="text-xs font-semibold uppercase text-muted">Part list</div>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <MetricMini label="Parts" value={selected ? "1" : "0"} />
              <MetricMini label="Build Price" value={buildPrice ? formatSar(buildPrice) : "0 SAR"} />
              <MetricMini label="Wattage" value={`${Math.round(buildWattage)}W`} />
              <MetricMini label="Showing" value={String(visible.length)} />
            </div>
          </div>

          <div className="mt-5 flex items-center gap-2 text-sm font-semibold text-ink">
            <SlidersHorizontal size={16} aria-hidden />
            Filters
          </div>
          <label className="mt-3 flex items-center gap-2 rounded-md border border-line bg-panel px-3 py-2 text-sm text-ink">
            <input type="checkbox" checked={onlyPriced} onChange={(event) => setOnlyPriced(event.target.checked)} />
            In-stock/priced
          </label>

          <div className="mt-4 border-t border-line pt-4">
            <div className="mb-2 text-xs font-semibold uppercase text-muted">Price range</div>
            <div className="flex justify-between text-sm text-muted">
              <span>{priceBounds.min ? formatSar(priceBounds.min) : "N/A"}</span>
              <span>{priceBounds.max ? formatSar(priceBounds.max) : "N/A"}</span>
            </div>
          </div>

          <div className="mt-4 border-t border-line pt-4">
            <div className="mb-2 text-xs font-semibold uppercase text-muted">Manufacturer</div>
            <div className="grid gap-2">
              <button
                type="button"
                onClick={() => setBrand("all")}
                className={`rounded-md border px-3 py-2 text-left text-sm ${brand === "all" ? "border-signal text-signal" : "border-line text-muted"}`}
              >
                All brands
              </button>
              {brands.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setBrand(item)}
                  className={`rounded-md border px-3 py-2 text-left text-sm ${brand === item ? "border-signal text-signal" : "border-line text-muted"}`}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-col">
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
            <div>
              <h3 className="text-lg font-semibold text-ink">Showing {visible.length} market products</h3>
              <p className="text-sm text-muted">
                one card per product, cheapest seller price shown from {products.length} loaded listings
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="grid h-9 w-9 place-items-center rounded-md border border-line bg-panel text-muted hover:text-ink"
              aria-label="Close product picker"
            >
              <X size={18} aria-hidden />
            </button>
          </div>

          <div className="grid gap-3 border-b border-line p-4 md:grid-cols-[180px_1fr]">
            <label className="flex h-10 items-center gap-2 rounded-md border border-line bg-panel px-3 text-sm text-muted">
              <ArrowUpDown size={16} aria-hidden />
              <select value={sort} onChange={(event) => setSort(event.target.value as SortMode)} className="w-full bg-transparent text-ink outline-none">
                <option value="recommended">Recommended</option>
                <option value="price_low">Price low</option>
                <option value="price_high">Price high</option>
                <option value="name">Name</option>
              </select>
            </label>
            <label className="flex h-10 items-center gap-2 rounded-md border border-line bg-panel px-3 text-sm text-muted">
              <Search size={16} aria-hidden />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={`Search ${categoryCopy[kind]}...`}
                className="w-full bg-transparent text-ink outline-none placeholder:text-muted"
                autoFocus
              />
            </label>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {failure ? (
              <div className="rounded-md border border-danger/30 bg-red-50 px-3 py-2 text-sm text-danger">{failure}</div>
            ) : loading ? (
              <div className="grid place-items-center rounded-lg border border-line bg-panel px-3 py-16 text-sm text-muted">
                Loading Saudi market products...
              </div>
            ) : visible.length === 0 ? (
              <div className="grid place-items-center rounded-lg border border-line bg-panel px-3 py-16 text-center text-sm text-muted">
                No products match these filters. Clear search or select all brands.
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {visible.map((product) => (
                  <ProductCard
                    key={product.id}
                    product={product}
                    selected={selected?.id === product.id}
                    onSelect={() => onSelect(product)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ProductCard({ product, selected, onSelect }: { product: ProductSearchResult; selected: boolean; onSelect: () => void }) {
  const price = bestSarPrice(product);
  const productName = displayProductName(product);
  const specs = productSummarySpecs(product);
  return (
    <article className={`flex min-h-[380px] flex-col overflow-hidden rounded-md border bg-[#1c1c1e] shadow-[0_18px_40px_rgba(0,0,0,0.22)] transition hover:-translate-y-0.5 hover:border-signal/70 ${selected ? "border-signal" : "border-[#2f3137]"}`}>
      <div className="grid aspect-[4/3] place-items-center bg-white p-4">
        <ProductArtwork product={product} productName={productName} />
      </div>
      <div className="grid flex-1 gap-3 bg-[#1c1c1e] p-3.5">
        <div>
          <h4 className="line-clamp-2 min-h-10 text-sm font-bold leading-5 text-white" title={productName}>
            {productName}
          </h4>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-[#a1a1aa]">
            {product.brand ? <span>{product.brand}</span> : null}
            <span>{product.region}</span>
          </div>
        </div>
        <div className="flex items-start justify-between gap-3">
          <div className="text-base font-bold text-[#4ade80]">{price ? formatSar(price.amount) : "No SAR price"}</div>
          <div className="max-w-[45%] truncate text-right text-xs font-semibold text-[#b8beca]">
            {displayStoreName(price?.vendor ?? product.current_recommended_vendor ?? product.lowest_market_vendor)}
          </div>
        </div>
        {specs.length ? (
          <dl className="grid grid-cols-2 gap-x-5 gap-y-2.5 text-xs">
            {specs.map((spec) => (
              <div key={spec.label}>
                <dt className="text-[11px] font-medium text-[#8d929f]">{spec.label}</dt>
                <dd className="mt-0.5 text-[13px] font-semibold text-[#e4e7ee]">{spec.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        <button
          type="button"
          onClick={onSelect}
          className="mt-auto inline-flex h-9 items-center justify-center gap-2 rounded-md border border-[#3a3d45] bg-[#2d2d30] text-sm font-bold text-white transition hover:border-signal hover:bg-[#36363a] focus:outline-none focus:ring-2 focus:ring-signal/70"
        >
          <Plus size={15} aria-hidden />
          {selected ? "Selected" : "Add to build"}
        </button>
      </div>
    </article>
  );
}

function ProductArtwork({ product, productName }: { product: ProductSearchResult; productName: string }) {
  const category = String(product.category);
  const imageUrl = product.processed_image_url || product.image_url;
  if (imageUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={imageUrl} alt={productName} className="h-full max-h-full w-full max-w-full object-contain" />
    );
  }

  const brand = englishText(product.brand) || brandFromName(productName) || "Product";
  const model = shortModelName(productName, category);
  return (
    <div className="grid h-full w-full place-items-center rounded-md bg-slate-50 p-4 text-center">
      <div>
        <div className="mx-auto mb-3 grid h-16 w-16 place-items-center rounded-lg border border-slate-200 bg-white text-sm font-black uppercase text-slate-700 shadow-sm">
          {category.slice(0, 3)}
        </div>
        <div className="text-xs font-bold uppercase tracking-wide text-slate-900">{brand}</div>
        <div className="mt-1 line-clamp-2 text-[11px] font-semibold leading-4 text-slate-500">{model}</div>
      </div>
    </div>
  );
}

function MetricMini({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase text-muted">{label}</div>
      <div className="text-sm font-semibold text-ink">{value}</div>
    </div>
  );
}

function SummaryMetric({ label, value, icon }: { label: string; value: string; icon?: ReactNode }) {
  return (
    <div className="rounded-md border border-line bg-white px-3 py-2">
      <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted">
        {icon}
        {label}
      </div>
      <div className="text-sm font-semibold text-ink">{value}</div>
    </div>
  );
}

function toSelectedComponents(selected: SelectionMap): SelectedComponents {
  return componentOrder.reduce((accumulator, kind) => {
    const product = selected[kind];
    if (product) {
      accumulator[selectionKeyByKind[kind]] = product.id;
    }
    return accumulator;
  }, {} as SelectedComponents);
}

function cheapestProducts(products: ProductSearchResult[]): ProductSearchResult[] {
  const grouped = new Map<string, ProductSearchResult>();
  products.forEach((product) => {
    const key = productIdentityKey(product);
    const current = grouped.get(key);
    if (!current) {
      grouped.set(key, product);
      return;
    }
    const cheapest = productSort(product, current, "price_low") < 0 ? product : current;
    const imageCarrier = cheapest.image_url ? cheapest : product.image_url ? product : current;
    if (cheapest !== current || (!current.image_url && imageCarrier.image_url)) {
      grouped.set(key, {
        ...cheapest,
        image_url: cheapest.image_url ?? imageCarrier.image_url
      });
    }
  });
  return Array.from(grouped.values());
}

function productIdentityKey(product: ProductSearchResult): string {
  const displayName = displayProductName(product);
  const detectedModel = productModelKey(displayName);
  if (detectedModel) return [product.category, detectedModel].join("|").toUpperCase();
  return product.canonical_key || [product.category, product.brand, product.model || displayName].filter(Boolean).join("|").toUpperCase();
}

function displayProductName(product: ProductSearchResult): string {
  const cleaned = englishText(product.name);
  const patternMatch =
    cleaned.match(/\b(?:AMD\s+)?Ryzen\s+\d\s+\d{4}[A-Z0-9]*\b/i) ??
    cleaned.match(/\b\d-?(\d{4}[A-Z0-9]*)\b/i) ??
    cleaned.match(/\b(?:Intel\s+)?Core\s+i[3579][-\s]?\d{4,5}[A-Z]*\b/i) ??
    cleaned.match(/\b(?:NVIDIA\s+)?(?:GeForce\s+)?RTX\s+\d{4}(?:\s+SUPER|\s+Ti)?\b/i) ??
    cleaned.match(/\b(?:AMD\s+)?Radeon\s+RX\s+\d{4}\s?XT\b/i);
  if (patternMatch?.[0]) {
    const normalized = (patternMatch[1] ? `Ryzen ${patternMatch[0].replace("-", " ")}` : patternMatch[0]).replace(/\s+/g, " ").trim();
    if (/^Ryzen/i.test(normalized)) return `AMD ${normalized}`;
    if (/^Core/i.test(normalized)) return `Intel ${normalized}`;
    return normalized;
  }
  if (cleaned.length >= 8) return cleaned;
  const fallback = englishText([product.brand, product.model, product.category].filter(Boolean).join(" "));
  return fallback || "Product";
}

function englishText(value?: string | null): string {
  return (value ?? "")
    .replace(/[^\x20-\x7E]+/g, " ")
    .replace(/\b(?:unknown|null|undefined)\b/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function displayStoreName(value?: string | null): string {
  const cleaned = englishText(value);
  if (cleaned) return cleaned;
  const raw = value ?? "";
  if (/قصر\s*الحاسبات/.test(raw)) return "Computer Palace";
  if (/الحاسبات/.test(raw)) return "Local computer store";
  return "Store unknown";
}

function productSummarySpecs(product: ProductSearchResult): Array<{ label: string; value: string }> {
  if (product.category !== "CPU") return [];
  const specs = product.summary_specs ?? {};
  return [
    { label: "Socket", value: stringSpec(specs.socket) },
    {
      label: "Cores",
      value: stringSpec(specs.cores)
    },
    {
      label: "Threads",
      value: stringSpec(specs.threads)
    },
    {
      label: "Boost",
      value: clockSpec(specs.boost_clock_ghz)
    }
  ].filter((item): item is { label: string; value: string } => Boolean(item.value));
}

function stringSpec(value: unknown): string {
  if (typeof value === "number") return String(value);
  if (typeof value === "string" && value.trim()) return value.trim();
  return "";
}

function clockSpec(value: unknown): string {
  if (typeof value === "number") return `${value} GHz`;
  if (typeof value === "string" && value.trim()) {
    return value.toLowerCase().includes("ghz") ? value.trim() : `${value.trim()} GHz`;
  }
  return "";
}

function brandFromName(name: string): string {
  const match = name.match(/\b(AMD|Intel|NVIDIA|ASUS|MSI|Gigabyte|Corsair|Kingston|Samsung|WD|Crucial|DeepCool|NZXT|Seasonic)\b/i);
  return match?.[1] ?? "";
}

function productModelKey(name: string): string {
  const match =
    name.match(/\bRyzen\s+\d\s+\d{4}[A-Z0-9]*\b/i) ??
    name.match(/\bCore\s+i[3579][-\s]?\d{4,5}[A-Z]*\b/i) ??
    name.match(/\bRTX\s+\d{4}(?:\s+SUPER|\s+Ti)?\b/i) ??
    name.match(/\bRX\s+\d{4}\s?XT\b/i);
  return match?.[0]?.replace(/\s+/g, "_").toUpperCase() ?? "";
}

function shortModelName(name: string, category: string): string {
  const cleaned = englishText(name);
  const words = cleaned.split(" ").filter(Boolean);
  if (category === "CPU") {
    const match = cleaned.match(/\b(?:Ryzen|Core)\s+\d?\s*[A-Za-z0-9-]+\b/i);
    if (match?.[0]) return match[0].replace(/\s+/g, " ");
  }
  if (category === "GPU") {
    const match = cleaned.match(/\b(?:RTX|RX)\s+\d{4}(?:\s+SUPER|\s+Ti|\s+XT)?\b/i);
    if (match?.[0]) return match[0].replace(/\s+/g, " ");
  }
  return words.slice(0, 4).join(" ") || category;
}

function bestSarPrice(product: ProductSearchResult): { amount: number; vendor?: string } | null {
  const candidates = [
    {
      amount: product.current_recommended_price,
      currency: product.current_recommended_currency,
      vendor: product.current_recommended_vendor
    },
    { amount: product.best_local_price, currency: product.best_local_currency, vendor: product.best_local_vendor },
    { amount: product.best_trusted_price, currency: product.best_trusted_currency, vendor: product.best_trusted_vendor },
    { amount: product.current_best_price, currency: product.current_best_currency, vendor: product.current_best_vendor },
    { amount: product.lowest_market_price, currency: product.lowest_market_currency, vendor: product.lowest_market_vendor }
  ];
  const matches = candidates.flatMap((candidate) =>
    typeof candidate.amount === "number" && candidate.amount > 0 && candidate.currency === "SAR"
      ? [{ amount: candidate.amount, vendor: candidate.vendor }]
      : []
  );
  const cheapest = matches.sort((left, right) => left.amount - right.amount)[0];
  return cheapest ? { amount: cheapest.amount, vendor: cheapest.vendor } : null;
}

function productSort(left: ProductSearchResult, right: ProductSearchResult, sort: SortMode) {
  const leftPrice = bestSarPrice(left)?.amount;
  const rightPrice = bestSarPrice(right)?.amount;
  if (sort === "price_low") return (leftPrice ?? Number.POSITIVE_INFINITY) - (rightPrice ?? Number.POSITIVE_INFINITY);
  if (sort === "price_high") return (rightPrice ?? -1) - (leftPrice ?? -1);
  if (sort === "name") return displayProductName(left).localeCompare(displayProductName(right));
  const leftScore = (left.price_confidence ?? 0) + (left.current_price_trust_score ?? 0) + (left.best_local_price ? 1 : 0);
  const rightScore = (right.price_confidence ?? 0) + (right.current_price_trust_score ?? 0) + (right.best_local_price ? 1 : 0);
  return rightScore - leftScore || (leftPrice ?? Number.POSITIVE_INFINITY) - (rightPrice ?? Number.POSITIVE_INFINITY);
}

function formatSar(value?: number | null) {
  if (typeof value !== "number") return "Price unknown";
  return `${Math.round(value).toLocaleString("en-US")} SAR`;
}
