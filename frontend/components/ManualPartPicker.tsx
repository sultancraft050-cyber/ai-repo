"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
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
import { CalmNotice, IconButton, StateBadge, cx, focusRing, interactiveButton, motionSafeSpin } from "@/components/ui/PublicUi";
import { searchProducts, validateAndMeasure } from "@/lib/api";
import { summarizeBuyerNotes } from "@/lib/uiText";
import { ProductImage } from "@/components/ProductImage";
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
type CategoryLoading = Partial<Record<ComponentKind, boolean>>;
type CategoryHasMore = Partial<Record<ComponentKind, boolean>>;
type SortMode = "recommended" | "cheapest" | "newest" | "name";
const PRODUCT_PAGE_SIZE = 24;

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
  const [categoryLoading, setCategoryLoading] = useState<CategoryLoading>(() =>
    componentOrder.reduce((state, kind) => ({ ...state, [kind]: true }), {} as CategoryLoading)
  );
  const [loadingMore, setLoadingMore] = useState<CategoryLoading>({});
  const [hasMore, setHasMore] = useState<CategoryHasMore>({});
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<SelectionMap>({});
  const [activeKind, setActiveKind] = useState<ComponentKind | null>(null);
  const [resolution, setResolution] = useState<Resolution>("1440p");
  const [refreshRate, setRefreshRate] = useState<(typeof refreshOptions)[number]>(144);
  const [compatibility, setCompatibility] = useState<CompatibilityResponse | null>(null);
  const [performance, setPerformance] = useState<PerformanceResponse | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);
  const openerRef = useRef<HTMLButtonElement | null>(null);
  const openerKindRef = useRef<ComponentKind | null>(null);

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
    ...Object.entries(failures).filter((entry): entry is [string, string] => Boolean(entry[1])).map(([kind, message]) => `${kind}: ${message}`),
    ...missingPrices.map((category) => `${category}: price not listed yet.`),
    ...(compatibility?.checks.filter((check) => check.status !== "pass").map((check) => check.details) ?? [])
  ];
  const buyerNotes = summarizeBuyerNotes(visibleWarnings, {
    fallback: "Pick all required parts to see price, wattage, and FPS estimates.",
    summary: "Some build details need review."
  });
  const missingSpecCount = selectedRows.filter((product) => hasSpecGap(product)).length;
  const exactReadyCount = selectedRows.filter((product) => product.compatibility_ready_exact).length;
  const familyReadyCount = selectedRows.filter((product) => product.compatibility_ready_family && !product.compatibility_ready_exact).length;
  const pricedCount = selectedRows.filter((product) => bestSarPrice(product)).length;
  const manualOnlyWarning =
    selectedCount === componentOrder.length &&
    (missingSpecCount > 0 || Boolean(compatibility && !compatibility.valid) || missingPrices.length > 0);

  useEffect(() => {
    let cancelled = false;
    async function loadProducts() {
      setLoading(true);
      setFailures({});
      setCategoryLoading(
        componentOrder.reduce((state, kind) => ({ ...state, [kind]: true }), {} as CategoryLoading)
      );

      await Promise.all(
        componentOrder.map(async (kind) => {
          try {
            const nextProducts = await searchProducts({
              category: kind,
              region: "SA",
              limit: PRODUCT_PAGE_SIZE,
              offset: 0
            });
            if (cancelled) return;
            setProducts((current) => ({ ...current, [kind]: nextProducts }));
            setHasMore((current) => ({ ...current, [kind]: nextProducts.length === PRODUCT_PAGE_SIZE }));
          } catch (error) {
            if (cancelled) return;
            setFailures((current) => ({
              ...current,
              [kind]: error instanceof Error ? error.message : "Unable to load this category."
            }));
            setHasMore((current) => ({ ...current, [kind]: false }));
          } finally {
            if (!cancelled) {
              setCategoryLoading((current) => ({ ...current, [kind]: false }));
            }
          }
        })
      );
      if (!cancelled) setLoading(false);
    }
    loadProducts();
    return () => {
      cancelled = true;
    };
  }, []);

  async function loadMoreProducts(kind: ComponentKind) {
    if (loadingMore[kind] || !hasMore[kind]) return;
    setLoadingMore((current) => ({ ...current, [kind]: true }));
    setFailures((current) => ({ ...current, [kind]: undefined }));
    try {
      const nextPage = await searchProducts({
        category: kind,
        region: "SA",
        limit: PRODUCT_PAGE_SIZE,
        offset: products[kind].length
      });
      setProducts((current) => ({
        ...current,
        [kind]: dedupeProducts([...current[kind], ...nextPage])
      }));
      setHasMore((current) => ({ ...current, [kind]: nextPage.length === PRODUCT_PAGE_SIZE }));
    } catch (error) {
      setFailures((current) => ({
        ...current,
        [kind]: error instanceof Error ? error.message : "Unable to load more products."
      }));
    } finally {
      setLoadingMore((current) => ({ ...current, [kind]: false }));
    }
  }

  async function retryProducts(kind: ComponentKind) {
    setCategoryLoading((current) => ({ ...current, [kind]: true }));
    setFailures((current) => ({ ...current, [kind]: undefined }));
    try {
      const nextProducts = await searchProducts({ category: kind, region: "SA", limit: PRODUCT_PAGE_SIZE, offset: 0 });
      setProducts((current) => ({ ...current, [kind]: nextProducts }));
      setHasMore((current) => ({ ...current, [kind]: nextProducts.length === PRODUCT_PAGE_SIZE }));
    } catch (error) {
      setFailures((current) => ({ ...current, [kind]: error instanceof Error ? error.message : "Unable to load this category." }));
    } finally {
      setCategoryLoading((current) => ({ ...current, [kind]: false }));
    }
  }

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
    closePicker();
  }

  function openPicker(kind: ComponentKind, opener: HTMLButtonElement) {
    openerRef.current = opener;
    openerKindRef.current = kind;
    setActiveKind(kind);
  }

  function closePicker() {
    setActiveKind(null);
    restorePickerFocus();
  }

  function restorePickerFocus() {
    const restore = () => {
      const opener =
        openerRef.current?.isConnected
          ? openerRef.current
          : openerKindRef.current
            ? document.querySelector<HTMLButtonElement>(`[data-picker-trigger="${openerKindRef.current}"]`)
            : null;
      opener?.focus({ preventScroll: true });
    };
    window.requestAnimationFrame(() => {
      restore();
      window.setTimeout(restore, 0);
    });
  }

  function removeProduct(kind: ComponentKind) {
    setSelected((current) => {
      const next = { ...current };
      delete next[kind];
      return next;
    });
  }

  return (
    <section id="manual-builder" className="scroll-mt-20 overflow-hidden rounded-lg border border-slate-800 bg-[#070b14] shadow-[0_24px_80px_rgba(0,0,0,0.36)]">
      <div className="border-b border-slate-800 bg-[#080d18] p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="mb-1 text-xs font-semibold uppercase text-signal">Manual builder</div>
            <h2 className="text-xl font-semibold text-white">Pick every part yourself</h2>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-400">
              Browse the Saudi catalog by category, pick one product per row, and keep the build summary visible as price,
              wattage, FPS, and compatibility evidence change.
            </p>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="text-xs font-semibold uppercase text-slate-500">
              Resolution
              <select
                value={resolution}
                onChange={(event) => setResolution(event.target.value as Resolution)}
                className={cx(
                  "mt-1 h-10 w-full cursor-pointer rounded-md border border-slate-700 bg-[#111827] px-3 text-sm font-semibold normal-case text-white hover:border-signal/60",
                  interactiveButton,
                  focusRing
                )}
              >
                <option value="1080p">1080p</option>
                <option value="1440p">1440p</option>
                <option value="4K">4K</option>
              </select>
            </label>
            <label className="text-xs font-semibold uppercase text-slate-500">
              Refresh
              <select
                value={refreshRate}
                onChange={(event) => setRefreshRate(Number(event.target.value) as (typeof refreshOptions)[number])}
                className={cx(
                  "mt-1 h-10 w-full cursor-pointer rounded-md border border-slate-700 bg-[#111827] px-3 text-sm font-semibold normal-case text-white hover:border-signal/60",
                  interactiveButton,
                  focusRing
                )}
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

      <div className="grid gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 overflow-hidden rounded-lg border border-slate-800 bg-[#0c1220]">
          <div className="flex items-center gap-2 border-b border-slate-800 bg-[#0a0f1b] px-3 py-3 text-sm font-semibold text-white">
            <span className="border-b-2 border-white pb-2">Parts List</span>
            <span className="pb-2 text-slate-500">Saudi Market</span>
          </div>
          <div className="border-b border-slate-800 bg-[#111827] px-3 py-2 text-sm font-semibold text-slate-300">
            One product per category, with state badges for price and spec readiness.
          </div>
          {componentOrder.map((kind) => (
            <PartRow
              key={kind}
              kind={kind}
              count={products[kind].length}
              selected={selected[kind]}
              loading={Boolean(categoryLoading[kind])}
              failure={failures[kind]}
              onAdd={(opener) => openPicker(kind, opener)}
              onRemove={() => removeProduct(kind)}
              onRetry={() => void retryProducts(kind)}
            />
          ))}
        </div>

        <aside className="grid content-start gap-3 xl:sticky xl:top-4">
          <div className="rounded-lg border border-slate-800 bg-[#111827] p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-base font-semibold text-white">Build summary</h3>
              {validating ? <Loader2 size={18} className={cx(motionSafeSpin, "text-signal")} aria-label="Calculating build" /> : null}
            </div>
            <div className="grid gap-2">
              <SummaryMetric label="Selected" value={`${selectedCount}/8 parts`} />
              <SummaryMetric label="Known SAR total" value={knownPriceTotal ? formatSar(knownPriceTotal) : "No prices yet"} />
              <SummaryMetric label="Missing prices" value={`${missingPrices.length} part${missingPrices.length === 1 ? "" : "s"}`} />
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
            <div className="mt-3 flex flex-wrap gap-2">
              <BuildStatePill label="Saudi priced" value={pricedCount} />
              <BuildStatePill label="Exact ready" value={exactReadyCount} />
              <BuildStatePill label="Family ready" value={familyReadyCount} />
              <BuildStatePill label="Needs specs" value={missingSpecCount} tone={missingSpecCount ? "warn" : "muted"} />
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-[#111827] p-4">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-white">
              {selectedCount === 8 && compatibility?.valid && !manualOnlyWarning ? (
                <CheckCircle2 size={16} className="text-signal" aria-hidden />
              ) : (
                <AlertTriangle size={16} className="text-caution" aria-hidden />
              )}
              Final check
            </div>
            {selectedCount < 8 ? (
              <p className="text-sm leading-6 text-slate-400">
                Missing: {missingCategories.join(", ")}. Pick every required part to finish the manual build.
              </p>
            ) : compatibility?.valid && !manualOnlyWarning ? (
              <p className="text-sm leading-6 text-slate-400">
                Can be used for build generation: all core parts are selected, compatibility checks passed, and required pricing/spec evidence is present.
              </p>
            ) : (
              <p className="text-sm leading-6 text-slate-400">
                Review before relying on automation: a few prices or specs still need confirmation.
              </p>
            )}
            {validationError ? <p className="mt-2 text-sm leading-6 text-danger">{validationError}</p> : null}
          </div>

          <CalmNotice
            title={buyerNotes.summary}
            tone={buyerNotes.count ? "caution" : "info"}
            className="border-slate-800 bg-[#111827]"
            details={
              buyerNotes.hasDetails ? (
                <ul className="grid gap-1">
                  {buyerNotes.details.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              ) : null
            }
          >
            {buyerNotes.visible.length ? buyerNotes.visible.join(" ") : "Pick parts to see the build summary."}
          </CalmNotice>
        </aside>
      </div>

      {activeKind ? (
        <ProductPickerModal
          kind={activeKind}
          products={products[activeKind]}
          selected={selected[activeKind]}
          buildPrice={knownPriceTotal}
          buildWattage={compatibility?.total_power_draw_w ?? 0}
          loading={Boolean(categoryLoading[activeKind])}
          failure={failures[activeKind]}
          onClose={closePicker}
          onSelect={(product) => chooseProduct(activeKind, product)}
          onLoadMore={() => loadMoreProducts(activeKind)}
          loadingMore={Boolean(loadingMore[activeKind])}
          hasMore={Boolean(hasMore[activeKind])}
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
  onRemove,
  onRetry
}: {
  kind: ComponentKind;
  count: number;
  selected?: ProductSearchResult;
  loading: boolean;
  failure?: string;
  onAdd: (opener: HTMLButtonElement) => void;
  onRemove: () => void;
  onRetry: () => void;
}) {
  const price = selected ? bestSarPrice(selected) : null;
  const state = selected ? productCatalogState(selected) : null;

  return (
    <div className="grid min-h-[70px] grid-cols-1 items-center gap-3 border-b border-slate-800 px-3 py-3 last:border-b-0 sm:grid-cols-[150px_minmax(0,1fr)_auto]">
      <div>
        <span className="inline-flex rounded-full border border-slate-700 bg-[#171d2c] px-2 py-1 text-sm font-semibold text-slate-300">
          {categoryCopy[kind]}
        </span>
      </div>

      <div className="min-w-0">
        {selected ? (
          <div className="flex min-w-0 items-center gap-3">
            <ProductImage
              imageUrl={selected?.processed_image_url || selected?.image_url}
              productName={displayProductName(selected)}
              category={kind}
              width={64}
              height={48}
              variant="build-summary"
              className="hidden shrink-0 border border-slate-700 sm:grid"
            />
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-white">{displayProductName(selected)}</div>
              <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted">
                <span>{price ? formatSar(price.amount) : "Price not listed yet"}</span>
                <span>{displayStoreName(price?.vendor ?? selected.current_recommended_vendor ?? selected.lowest_market_vendor)}</span>
                {state ? <StateBadge tone={state.tone}>{state.label}</StateBadge> : null}
              </div>
            </div>
          </div>
        ) : (
          <div className="text-sm text-slate-400">
            {failure ?? (loading ? "Loading market products..." : `${count} market product${count === 1 ? "" : "s"} available`)}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 sm:justify-end">
        {failure ? (
          <button type="button" onClick={onRetry} className={cx("inline-flex h-8 items-center rounded-md border border-caution/50 px-3 text-sm font-semibold text-caution", interactiveButton, focusRing)}>
            Retry {kind}
          </button>
        ) : null}
        {selected ? (
          <button
            type="button"
            onClick={onRemove}
            className={cx(
              "grid h-8 w-8 place-items-center rounded-md border border-slate-700 bg-[#111827] text-slate-400 hover:border-danger/50 hover:text-danger active:bg-[#0b101d]",
              interactiveButton,
              focusRing
            )}
            aria-label={`Remove ${kind}`}
            title={`Remove ${kind}`}
          >
            <Trash2 size={15} aria-hidden />
          </button>
        ) : null}
        <button
          type="button"
          data-picker-trigger={kind}
          onClick={(event) => onAdd(event.currentTarget)}
          disabled={loading || Boolean(failure)}
          className={cx(
            "inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-700 bg-[#202633] px-3 text-sm font-semibold text-white hover:border-signal hover:bg-[#263041] active:bg-[#111827]",
            interactiveButton,
            focusRing
          )}
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
  onSelect,
  onLoadMore,
  loadingMore,
  hasMore
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
  onLoadMore: () => void;
  loadingMore: boolean;
  hasMore: boolean;
}) {
  const headingId = useId();
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortMode>("recommended");
  const [brand, setBrand] = useState<string>("all");
  const [socket, setSocket] = useState<string>("all");
  const [memoryType, setMemoryType] = useState<string>("all");
  const [chipset, setChipset] = useState<string>("all");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [onlyPriced, setOnlyPriced] = useState(false);
  const [browserProducts, setBrowserProducts] = useState<ProductSearchResult[]>(products);
  const [browserLoading, setBrowserLoading] = useState(false);
  const [browserLoadingMore, setBrowserLoadingMore] = useState(false);
  const [browserHasMore, setBrowserHasMore] = useState(hasMore);
  const [browserError, setBrowserError] = useState<string | null>(null);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
      if (event.key === "Tab" && dialogRef.current) {
        const focusable = Array.from(
          dialogRef.current.querySelectorAll<HTMLElement>(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), details summary, [tabindex]:not([tabindex="-1"])'
          )
        ).filter((element) => !element.hasAttribute("disabled") && !element.getAttribute("aria-hidden"));
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    window.setTimeout(() => searchInputRef.current?.focus(), 0);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose]);

  useEffect(() => {
    setBrowserProducts(products);
    setBrowserHasMore(hasMore);
  }, [hasMore, products]);

  useEffect(() => {
    let cancelled = false;
    const timeout = window.setTimeout(async () => {
      setBrowserLoading(true);
      setBrowserError(null);
      try {
        const nextProducts = await searchProducts({
          query,
          category: kind,
          region: "SA",
          limit: PRODUCT_PAGE_SIZE,
          offset: 0,
          brand: brand === "all" ? undefined : brand,
          socket: socket === "all" ? undefined : socket,
          chipset: chipset === "all" ? undefined : chipset,
          memoryType: memoryType === "all" ? undefined : memoryType,
          minPriceSar: minPrice ? Number(minPrice) : undefined,
          maxPriceSar: maxPrice ? Number(maxPrice) : undefined,
          inStockPricedOnly: onlyPriced,
          sort
        });
        if (cancelled) return;
        setBrowserProducts(nextProducts);
        setBrowserHasMore(nextProducts.length === PRODUCT_PAGE_SIZE);
      } catch (error) {
        if (!cancelled) setBrowserError(error instanceof Error ? error.message : "Unable to search products.");
      } finally {
        if (!cancelled) setBrowserLoading(false);
      }
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [brand, chipset, kind, maxPrice, memoryType, minPrice, onlyPriced, query, socket, sort]);

  async function loadMoreFilteredProducts() {
    if (browserLoadingMore || !browserHasMore) return;
    setBrowserLoadingMore(true);
    setBrowserError(null);
    try {
      const nextPage = await searchProducts({
        query,
        category: kind,
        region: "SA",
        limit: PRODUCT_PAGE_SIZE,
        offset: browserProducts.length,
        brand: brand === "all" ? undefined : brand,
        socket: socket === "all" ? undefined : socket,
        chipset: chipset === "all" ? undefined : chipset,
        memoryType: memoryType === "all" ? undefined : memoryType,
        minPriceSar: minPrice ? Number(minPrice) : undefined,
        maxPriceSar: maxPrice ? Number(maxPrice) : undefined,
        inStockPricedOnly: onlyPriced,
        sort
      });
      setBrowserProducts((current) => dedupeProducts([...current, ...nextPage]));
      setBrowserHasMore(nextPage.length === PRODUCT_PAGE_SIZE);
      if (!nextPage.length) onLoadMore();
    } catch (error) {
      setBrowserError(error instanceof Error ? error.message : "Unable to load more products.");
    } finally {
      setBrowserLoadingMore(false);
    }
  }

  const groupedProducts = useMemo(() => cheapestProducts(browserProducts), [browserProducts]);
  const brands = useMemo(
    () =>
      Array.from(new Set(groupedProducts.map((product) => product.brand).filter(Boolean) as string[]))
        .sort((a, b) => a.localeCompare(b))
        .slice(0, 10),
    [groupedProducts]
  );
  const sockets = useMemo(() => facetValues(groupedProducts, "socket").slice(0, 10), [groupedProducts]);
  const memoryTypes = useMemo(() => facetValues(groupedProducts, "memory_type").slice(0, 10), [groupedProducts]);
  const chipsets = useMemo(() => facetValues(groupedProducts, "chipset").slice(0, 10), [groupedProducts]);
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
    return groupedProducts
      .filter((product) => {
        const normalizedQuery = query.trim().toLowerCase();
        return !normalizedQuery || `${product.name} ${product.brand ?? ""} ${product.model ?? ""}`.toLowerCase().includes(normalizedQuery);
      })
      .sort((left, right) => productSort(left, right, sort));
  }, [groupedProducts, query, sort]);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/76 p-2 backdrop-blur-sm sm:p-5"
      role="dialog"
      aria-modal="true"
      aria-labelledby={headingId}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div ref={dialogRef} className="mx-auto grid h-full min-h-0 max-w-7xl overflow-hidden rounded-lg border border-line bg-[#0b101d] shadow-tight lg:grid-cols-[250px_1fr]">
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
          <label className="mt-3 flex cursor-pointer items-center gap-2 rounded-md border border-line bg-panel px-3 py-2 text-sm text-ink transition-colors hover:border-signal/60 focus-within:border-signal focus-within:ring-2 focus-within:ring-signal/60 motion-reduce:transition-none">
            <input className={cx("cursor-pointer", focusRing)} type="checkbox" checked={onlyPriced} onChange={(event) => setOnlyPriced(event.target.checked)} />
            In-stock/priced
          </label>

          <div className="mt-4 border-t border-line pt-4">
            <div className="mb-2 text-xs font-semibold uppercase text-muted">Price range</div>
            <div className="flex justify-between text-sm text-muted">
              <span>{priceBounds.min ? formatSar(priceBounds.min) : "N/A"}</span>
              <span>{priceBounds.max ? formatSar(priceBounds.max) : "N/A"}</span>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <input
                inputMode="numeric"
                value={minPrice}
                onChange={(event) => setMinPrice(event.target.value.replace(/[^\d]/g, ""))}
                placeholder="Min SAR"
                className={cx("h-9 rounded-md border border-line bg-[#050915] px-2 text-sm text-ink placeholder:text-muted hover:border-signal/60", focusRing)}
              />
              <input
                inputMode="numeric"
                value={maxPrice}
                onChange={(event) => setMaxPrice(event.target.value.replace(/[^\d]/g, ""))}
                placeholder="Max SAR"
                className={cx("h-9 rounded-md border border-line bg-[#050915] px-2 text-sm text-ink placeholder:text-muted hover:border-signal/60", focusRing)}
              />
            </div>
          </div>

          <div className="mt-4 border-t border-line pt-4">
            <div className="mb-2 text-xs font-semibold uppercase text-muted">Manufacturer</div>
            <div className="grid gap-2">
              <button
                type="button"
                onClick={() => setBrand("all")}
                className={cx(
                  "rounded-md border px-3 py-2 text-left text-sm hover:border-signal/60 hover:text-ink active:bg-[#111827]",
                  interactiveButton,
                  focusRing,
                  brand === "all" ? "border-signal text-signal" : "border-line text-muted"
                )}
              >
                All brands
              </button>
              {brands.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setBrand(item)}
                  className={cx(
                    "rounded-md border px-3 py-2 text-left text-sm hover:border-signal/60 hover:text-ink active:bg-[#111827]",
                    interactiveButton,
                    focusRing,
                    brand === item ? "border-signal text-signal" : "border-line text-muted"
                  )}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>

          {sockets.length ? (
            <FacetFilter title="Socket" value={socket} options={sockets} onChange={setSocket} />
          ) : null}
          {memoryTypes.length ? (
            <FacetFilter title="Memory" value={memoryType} options={memoryTypes} onChange={setMemoryType} />
          ) : null}
          {chipsets.length ? (
            <FacetFilter title="Chipset" value={chipset} options={chipsets} onChange={setChipset} />
          ) : null}
        </aside>

        <div className="flex min-h-0 min-w-0 flex-col overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
            <div>
              <h3 id={headingId} className="text-lg font-semibold text-ink">Showing {visible.length} market products</h3>
              <p className="text-sm text-muted">
                one card per product, cheapest seller price shown from {browserProducts.length} loaded listings
              </p>
            </div>
            <IconButton label="Close product picker" onClick={onClose}>
              <X size={18} aria-hidden />
            </IconButton>
          </div>

          <div className="grid gap-3 border-b border-line p-4 md:grid-cols-[180px_1fr]">
            <label className={cx("flex h-10 items-center gap-2 rounded-md border border-line bg-panel px-3 text-sm text-muted hover:border-signal/60", focusRing)}>
              <ArrowUpDown size={16} aria-hidden />
              <select value={sort} onChange={(event) => setSort(event.target.value as SortMode)} className="w-full cursor-pointer bg-transparent text-ink outline-none">
                <option value="recommended">Recommended</option>
                <option value="cheapest">Cheapest</option>
                <option value="newest">Newest</option>
                <option value="name">Name</option>
              </select>
            </label>
            <label className={cx("flex h-10 items-center gap-2 rounded-md border border-line bg-panel px-3 text-sm text-muted hover:border-signal/60", focusRing)}>
              <Search size={16} aria-hidden />
              <input
                ref={searchInputRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={`Search ${categoryCopy[kind]}...`}
                className="w-full bg-transparent text-ink outline-none placeholder:text-muted"
              />
            </label>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">
            {failure || browserError ? (
              <CalmNotice title="Products could not load" tone="danger">
                {failure ?? browserError}
              </CalmNotice>
            ) : loading || browserLoading ? (
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
            {!failure && !loading && !browserLoading && browserHasMore ? (
              <div className="mt-4 grid place-items-center">
                <button
                  type="button"
                  onClick={loadMoreFilteredProducts}
                  disabled={loadingMore || browserLoadingMore}
                  className={cx(
                    "inline-flex h-10 items-center justify-center rounded-md border border-line bg-[#2d2d30] px-4 text-sm font-bold text-white hover:border-signal hover:bg-[#36363a] active:bg-[#242428] disabled:cursor-wait",
                    interactiveButton,
                    focusRing
                  )}
                >
                  {loadingMore || browserLoadingMore ? "Loading more..." : "Load more products"}
                </button>
              </div>
            ) : null}
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
  const state = productCatalogState(product);
  const missingExactFields = product.missing_exact_card_fields ?? [];
  return (
    <article
      className={cx(
        "flex min-h-[430px] flex-col overflow-hidden rounded-md border bg-[#1c1c1e] shadow-[0_18px_40px_rgba(0,0,0,0.22)] transition-colors duration-150 hover:border-signal/70 motion-reduce:transition-none",
        selected ? "border-signal" : "border-[#2f3137]"
      )}
    >
      <div className="grid h-48 place-items-center bg-white p-4">
        <ProductArtwork product={product} productName={productName} />
      </div>
      <div className="grid flex-1 grid-rows-[minmax(80px,auto)_minmax(42px,auto)_minmax(96px,auto)_minmax(48px,auto)_auto] gap-3 bg-[#1c1c1e] p-3.5">
        <div className="min-h-20">
          <h4 className="line-clamp-2 min-h-10 text-sm font-bold leading-5 text-white" title={productName}>
            {productName}
          </h4>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-[#a1a1aa]">
            {product.brand ? <span>{product.brand}</span> : null}
            <span>{product.region}</span>
            <StateBadge tone={state.tone}>{state.label}</StateBadge>
          </div>
        </div>
        <div className="flex min-h-10 items-start justify-between gap-3">
          <div className="text-base font-bold text-[#4ade80]">{price ? formatSar(price.amount) : "Price not listed yet"}</div>
          <div className="max-w-[45%] truncate text-right text-xs font-semibold text-[#b8beca]">
            {displayStoreName(price?.vendor ?? product.current_recommended_vendor ?? product.lowest_market_vendor)}
          </div>
        </div>
        {specs.length ? (
          <dl className="grid min-h-24 grid-cols-2 gap-x-5 gap-y-2.5 text-xs">
            {specs.map((spec) => (
              <div key={spec.label}>
                <dt className="text-[11px] font-medium text-[#8d929f]">{spec.label}</dt>
                <dd className="mt-0.5 text-[13px] font-semibold text-[#e4e7ee]">{spec.value}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <div className="min-h-24 text-xs leading-5 text-[#a1a1aa]">Specs will appear as confirmed evidence is added.</div>
        )}
        {missingExactFields.length ? (
          <p className="rounded-md border border-amber-300/20 bg-amber-300/10 px-2.5 py-2 text-xs leading-5 text-amber-100">
            Specs needed: {missingExactFields.slice(0, 3).join(", ")}
          </p>
        ) : (
          <div className="min-h-12" aria-hidden />
        )}
        <button
          type="button"
          onClick={onSelect}
          aria-pressed={selected}
          className={cx(
            "mt-auto inline-flex h-9 items-center justify-center gap-2 rounded-md border border-[#3a3d45] bg-[#2d2d30] text-sm font-bold text-white hover:border-signal hover:bg-[#36363a] active:bg-[#242428]",
            interactiveButton,
            focusRing
          )}
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
  return (
    <ProductImage
      imageUrl={product.processed_image_url || product.image_url}
      productName={productName}
      category={category}
      width={320}
      height={160}
      variant="card"
      className="max-w-full"
    />
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

function FacetFilter({
  title,
  value,
  options,
  onChange
}: {
  title: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="mt-4 border-t border-line pt-4">
      <div className="mb-2 text-xs font-semibold uppercase text-muted">{title}</div>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={cx(
          "h-10 w-full cursor-pointer rounded-md border border-line bg-[#050915] px-3 text-sm font-semibold text-ink hover:border-signal/60",
          interactiveButton,
          focusRing
        )}
      >
        <option value="all">All {title.toLowerCase()}</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
}

function SummaryMetric({ label, value, icon }: { label: string; value: string; icon?: ReactNode }) {
  return (
    <div className="rounded-md border border-slate-700 bg-[#070b14] px-3 py-2">
      <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase text-slate-500">
        {icon}
        {label}
      </div>
      <div className="text-sm font-semibold text-white">{value}</div>
    </div>
  );
}

function BuildStatePill({ label, value, tone = "default" }: { label: string; value: number; tone?: "default" | "warn" | "muted" }) {
  const toneClass =
    tone === "warn"
      ? "border-amber-300/30 bg-amber-300/10 text-amber-100"
      : tone === "muted"
        ? "border-slate-700 bg-slate-900/80 text-slate-400"
        : "border-teal-300/30 bg-teal-300/10 text-teal-100";
  return (
    <span className={`rounded-full border px-2 py-1 text-xs font-semibold ${toneClass}`}>
      {value} {label}
    </span>
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
    const cheapest = productSort(product, current, "cheapest") < 0 ? product : current;
    const cheapestImage = cheapest.processed_image_url || cheapest.image_url;
    const productImage = product.processed_image_url || product.image_url;
    const currentImage = current.processed_image_url || current.image_url;
    const imageCarrier = cheapestImage ? cheapest : productImage ? product : current;
    if (cheapest !== current || (!currentImage && (imageCarrier.processed_image_url || imageCarrier.image_url))) {
      grouped.set(key, {
        ...cheapest,
        processed_image_url: cheapest.processed_image_url ?? imageCarrier.processed_image_url,
        image_url: cheapest.image_url ?? imageCarrier.image_url
      });
    }
  });
  return Array.from(grouped.values());
}

function dedupeProducts(products: ProductSearchResult[]): ProductSearchResult[] {
  const seen = new Set<string>();
  return products.filter((product) => {
    const key = product.id || product.canonical_key || productIdentityKey(product);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
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
  const specs = product.summary_specs ?? {};
  const category = String(product.category);
  const common = [
    { label: "Socket", value: stringSpec(specs.socket) },
    { label: "Chipset", value: stringSpec(specs.chipset) },
    { label: "Memory", value: stringSpec(specs.memory_type) },
    { label: "Form factor", value: stringSpec(specs.form_factor) }
  ];
  const byCategory: Record<string, Array<{ label: string; value: string }>> = {
    CPU: [
      { label: "Socket", value: stringSpec(specs.socket) },
      { label: "Cores", value: stringSpec(specs.cores) },
      { label: "Threads", value: stringSpec(specs.threads) },
      { label: "Boost", value: clockSpec(specs.boost_clock_ghz) || stringSpec(specs.boost_clock) },
      { label: "TDP", value: wattSpec(specs.tdp_w) }
    ],
    GPU: [
      { label: "VRAM", value: gbSpec(specs.vram_gb) },
      { label: "Length", value: mmSpec(specs.length_mm) },
      { label: "Board power", value: wattSpec(specs.board_power_w ?? specs.tdp_w) },
      { label: "Family power", value: wattSpec(specs.reference_tdp_w) },
      { label: "PCIe", value: stringSpec(specs.pcie_generation) }
    ],
    RAM: [
      { label: "Type", value: stringSpec(specs.memory_type) },
      { label: "Capacity", value: gbSpec(specs.capacity_gb) },
      { label: "Speed", value: mhzSpec(specs.speed_mhz ?? specs.speed_mt_s) },
      { label: "Kit", value: stringSpec(specs.kit_config) }
    ],
    Storage: [
      { label: "Capacity", value: tbOrGbSpec(specs.capacity_tb, specs.capacity_gb) },
      { label: "Interface", value: stringSpec(specs.interface) },
      { label: "Protocol", value: stringSpec(specs.protocol) }
    ],
    PSU: [
      { label: "Wattage", value: wattSpec(specs.wattage_w) },
      { label: "Efficiency", value: stringSpec(specs.efficiency_rating) }
    ],
    Motherboard: common,
    Case: common,
    Cooler: [
      { label: "Type", value: stringSpec(specs.cooler_type) },
      { label: "Radiator", value: mmSpec(specs.radiator_size_mm) },
      { label: "Height", value: mmSpec(specs.height_mm) }
    ]
  };
  return (byCategory[category] ?? common).filter((item): item is { label: string; value: string } => Boolean(item.value)).slice(0, 6);
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

function wattSpec(value: unknown): string {
  const raw = stringSpec(value);
  return raw ? (raw.toLowerCase().includes("w") ? raw : `${raw}W`) : "";
}

function gbSpec(value: unknown): string {
  const raw = stringSpec(value);
  return raw ? (raw.toLowerCase().includes("gb") ? raw : `${raw}GB`) : "";
}

function mmSpec(value: unknown): string {
  const raw = stringSpec(value);
  return raw ? (raw.toLowerCase().includes("mm") ? raw : `${raw}mm`) : "";
}

function mhzSpec(value: unknown): string {
  const raw = stringSpec(value);
  return raw ? (raw.toLowerCase().includes("hz") || raw.toLowerCase().includes("mt") ? raw : `${raw}MT/s`) : "";
}

function tbOrGbSpec(tb: unknown, gb: unknown): string {
  const tbValue = stringSpec(tb);
  if (tbValue) return tbValue.toLowerCase().includes("tb") ? tbValue : `${tbValue}TB`;
  return gbSpec(gb);
}

function productModelKey(name: string): string {
  const match =
    name.match(/\bRyzen\s+\d\s+\d{4}[A-Z0-9]*\b/i) ??
    name.match(/\bCore\s+i[3579][-\s]?\d{4,5}[A-Z]*\b/i) ??
    name.match(/\bRTX\s+\d{4}(?:\s+SUPER|\s+Ti)?\b/i) ??
    name.match(/\bRX\s+\d{4}\s?XT\b/i);
  return match?.[0]?.replace(/\s+/g, "_").toUpperCase() ?? "";
}

function bestSarPrice(product: ProductSearchResult): { amount: number; vendor?: string } | null {
  const candidates = [
    {
      amount: product.cheapest_price_sar,
      currency: product.cheapest_price_sar ? "SAR" : undefined,
      vendor: product.cheapest_vendor
    },
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
      ? [{ amount: candidate.amount, vendor: candidate.vendor ?? undefined }]
      : []
  );
  const cheapest = matches.sort((left, right) => left.amount - right.amount)[0];
  return cheapest ? { amount: cheapest.amount, vendor: cheapest.vendor } : null;
}

function productSort(left: ProductSearchResult, right: ProductSearchResult, sort: SortMode) {
  const leftPrice = bestSarPrice(left)?.amount;
  const rightPrice = bestSarPrice(right)?.amount;
  if (sort === "cheapest") return (leftPrice ?? Number.POSITIVE_INFINITY) - (rightPrice ?? Number.POSITIVE_INFINITY);
  if (sort === "newest") {
    const leftTime = left.current_price_timestamp ? Date.parse(left.current_price_timestamp) : 0;
    const rightTime = right.current_price_timestamp ? Date.parse(right.current_price_timestamp) : 0;
    return rightTime - leftTime || displayProductName(left).localeCompare(displayProductName(right));
  }
  if (sort === "name") return displayProductName(left).localeCompare(displayProductName(right));
  const leftScore = (left.price_confidence ?? 0) + (left.current_price_trust_score ?? 0) + (left.best_local_price ? 1 : 0);
  const rightScore = (right.price_confidence ?? 0) + (right.current_price_trust_score ?? 0) + (right.best_local_price ? 1 : 0);
  return rightScore - leftScore || (leftPrice ?? Number.POSITIVE_INFINITY) - (rightPrice ?? Number.POSITIVE_INFINITY);
}

function facetValues(products: ProductSearchResult[], field: string): string[] {
  return Array.from(
    new Set(
      products
        .map((product) => product.summary_specs?.[field])
        .flatMap((value) => (Array.isArray(value) ? value : [value]))
        .filter((value): value is string | number => typeof value === "string" || typeof value === "number")
        .map((value) => String(value).trim())
        .filter(Boolean)
    )
  ).sort((left, right) => left.localeCompare(right));
}

function productCatalogState(product: ProductSearchResult): { label: string; tone: "neutral" | "success" | "info" | "caution" } {
  if (product.catalog_state === "saudi_priced" || bestSarPrice(product)) {
    return { label: "Saudi priced", tone: "success" };
  }
  if (product.readiness_state === "compatibility_ready_exact" || product.compatibility_ready_exact) {
    return { label: "Exact ready", tone: "success" };
  }
  if (product.readiness_state === "compatibility_ready_family" || product.compatibility_ready_family) {
    return { label: "Family ready", tone: "info" };
  }
  if (product.catalog_state === "needs_spec_confirmation" || product.compatibility_ready === false) {
    return { label: "Needs specs", tone: "caution" };
  }
  return { label: "Catalog only", tone: "neutral" };
}

function hasSpecGap(product: ProductSearchResult): boolean {
  return (
    product.readiness_state === "metadata_only" ||
    product.catalog_state === "needs_spec_confirmation" ||
    product.compatibility_ready === false ||
    Boolean(product.missing_exact_card_fields?.length) ||
    Boolean(product.missing_compatibility_fields?.length)
  );
}

function formatSar(value?: number | null) {
  if (typeof value !== "number") return "Price not listed yet";
  return `${Math.round(value).toLocaleString("en-US")} SAR`;
}
