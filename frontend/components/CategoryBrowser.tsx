"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { Cpu, Search, ChevronLeft, ChevronRight, BarChart3 } from "lucide-react";
import { listCatalogProducts, CatalogProduct } from "@/lib/api";
import { ProductImage } from "@/components/ProductImage";

interface CategoryBrowserProps {
  category?: string;
  title?: string;
}

const CATEGORIES = ["CPU", "GPU", "MOTHERBOARD", "RAM", "STORAGE", "PSU", "CASE", "COOLER"];

const CATEGORY_COUNTS: Record<string, number> = {
  ALL: 280,
  CPU: 40,
  GPU: 40,
  MOTHERBOARD: 40,
  RAM: 40,
  STORAGE: 40,
  PSU: 30,
  CASE: 30,
  COOLER: 20
};

function CategoryBrowserImpl({ category: initialCategory, title }: CategoryBrowserProps) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const limit = 20;

  // Derived URL params
  const category = searchParams.get("category") || initialCategory || "";
  const search = searchParams.get("search") || "";
  const page = Number(searchParams.get("page") || "1");
  const offset = (page - 1) * limit;

  const [products, setProducts] = useState<CatalogProduct[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedBrand, setSelectedBrand] = useState("");
  const [sortBy, setSortBy] = useState("name_asc");
  const [compareIds, setCompareIds] = useState<number[]>([]);

  // Search input state
  const [inputSearch, setInputSearch] = useState(search);

  // Sync inputSearch with url search when url search changes (e.g. back/forward navigation)
  useEffect(() => {
    setInputSearch(search);
  }, [search]);

  // Debounce search input changes (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      if (inputSearch !== search) {
        const params = new URLSearchParams(searchParams.toString());
        if (inputSearch.trim()) {
          params.set("search", inputSearch.trim());
        } else {
          params.delete("search");
        }
        params.set("page", "1");
        router.push(`${pathname}?${params.toString()}` as any);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [inputSearch, search, searchParams, pathname, router]);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError("");
      try {
        const data = await listCatalogProducts(offset, limit, category || undefined, search || undefined);
        setProducts(data);
      } catch (err: any) {
        setError(err.message || "Failed to load components.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [category, search, offset]);

  // Handle category change
  const handleCategoryChange = (cat: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (cat) {
      params.set("category", cat);
    } else {
      params.delete("category");
    }
    params.delete("search");
    params.set("page", "1");
    router.push(`${pathname}?${params.toString()}` as any);
    setSelectedBrand("");
  };

  // Handle page change
  const handlePageChange = (newPage: number) => {
    const params = new URLSearchParams(searchParams.toString());
    if (newPage > 1) {
      params.set("page", String(newPage));
    } else {
      params.delete("page");
    }
    router.push(`${pathname}?${params.toString()}` as any);
  };

  // Clear all filters
  const handleClearFilters = () => {
    router.push(pathname as any);
    setInputSearch("");
    setSelectedBrand("");
  };

  // Get unique brands for filtering
  const brands = Array.from(new Set(products.map((p) => p.brand))).filter(Boolean);

  // Filter and sort products
  let filteredProducts = products;
  if (selectedBrand) {
    filteredProducts = products.filter((p) => p.brand === selectedBrand);
  }

  const sortedProducts = [...filteredProducts].sort((a, b) => {
    if (sortBy === "name_asc") {
      return a.canonical_name.localeCompare(b.canonical_name);
    }
    if (sortBy === "name_desc") {
      return b.canonical_name.localeCompare(b.canonical_name);
    }
    return 0;
  });

  const toggleCompare = (id: number) => {
    if (compareIds.includes(id)) {
      setCompareIds(compareIds.filter((x) => x !== id));
    } else {
      if (compareIds.length >= 4) {
        alert("You can compare up to 4 components at a time.");
        return;
      }
      setCompareIds([...compareIds, id]);
    }
  };

  return (
    <main className="p-6 max-w-7xl mx-auto">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-extrabold text-ink tracking-tight">
            {title || (category ? `${category} Catalog` : "PC Components browser")}
          </h1>
          <p className="text-sm text-muted mt-1">
            Browse engineering-grade components with verified compatibility specifications.
          </p>
        </div>

        {compareIds.length > 0 && (
          <a
            href={`/compare?category=${category || products[0]?.category}&ids=${compareIds.join(",")}`}
            className="flex items-center gap-2 px-4 py-2.5 bg-signal hover:bg-signal/80 text-slate-950 font-bold rounded-lg transition-all shadow-lg shadow-teal-500/10"
          >
            <BarChart3 size={18} />
            Compare Selected ({compareIds.length})
          </a>
        )}
      </div>

      {/* Category selector tags */}
      {!initialCategory && (
        <div className="flex flex-wrap gap-2 mb-6">
          <button
            onClick={() => handleCategoryChange("")}
            className={`px-4 py-1.5 rounded-full text-xs font-bold transition-all ${
              category === ""
                ? "bg-signal text-slate-950"
                : "bg-panel border border-line text-muted hover:text-ink"
            }`}
          >
            ALL ({CATEGORY_COUNTS.ALL})
          </button>
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              onClick={() => handleCategoryChange(cat)}
              className={`px-4 py-1.5 rounded-full text-xs font-bold transition-all ${
                category === cat
                  ? "bg-signal text-slate-950"
                  : "bg-panel border border-line text-muted hover:text-ink"
              }`}
            >
              {cat} ({CATEGORY_COUNTS[cat] || 0})
            </button>
          ))}
        </div>
      )}

      {/* Active filter summary */}
      {(category || search || selectedBrand) && (
        <div className="mb-6 flex flex-wrap items-center gap-3 bg-panel/30 border border-line rounded-lg p-3 text-sm">
          <span className="text-muted font-semibold">Active filters:</span>
          {category && (
            <span className="bg-panel border border-line px-2.5 py-1 rounded text-xs font-bold text-ink">
              Category: {category}
            </span>
          )}
          {search && (
            <span className="bg-panel border border-line px-2.5 py-1 rounded text-xs font-bold text-ink">
              Search: "{search}"
            </span>
          )}
          {selectedBrand && (
            <span className="bg-panel border border-line px-2.5 py-1 rounded text-xs font-bold text-ink">
              Brand: {selectedBrand}
            </span>
          )}
          <button
            onClick={handleClearFilters}
            className="text-xs font-black text-signal hover:underline ml-auto"
          >
            Clear all filters
          </button>
        </div>
      )}

      {/* Search and filter toolbar */}
      <div className="grid grid-cols-1 sm:grid-cols-12 gap-4 mb-6">
        <div className="sm:col-span-6 relative">
          <Search className="absolute left-3 top-3.5 text-muted" size={17} />
          <input
            type="text"
            placeholder="Search by manufacturer, model, MPN..."
            value={inputSearch}
            onChange={(e) => {
              setInputSearch(e.target.value);
            }}
            className="w-full bg-[#0d1527] border border-line rounded-lg py-2.5 pl-10 pr-4 text-ink text-sm focus:border-signal focus:outline-none"
          />
        </div>

        <div className="sm:col-span-3">
          <select
            value={selectedBrand}
            onChange={(e) => setSelectedBrand(e.target.value)}
            className="w-full bg-[#0d1527] border border-line rounded-lg py-2.5 px-3 text-ink text-sm focus:border-signal focus:outline-none"
          >
            <option value="">All Brands</option>
            {brands.map((brand) => (
              <option key={brand} value={brand}>
                {brand}
              </option>
            ))}
          </select>
        </div>

        <div className="sm:col-span-3">
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="w-full bg-[#0d1527] border border-line rounded-lg py-2.5 px-3 text-ink text-sm focus:border-signal focus:outline-none"
          >
            <option value="name_asc">Name (A-Z)</option>
            <option value="name_desc">Name (Z-A)</option>
          </select>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="grid place-items-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-signal border-t-transparent"></div>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-4 rounded-lg text-sm mb-6">
          {error}
        </div>
      )}

      {/* No products found */}
      {!loading && sortedProducts.length === 0 && (
        <div className="text-center py-16 bg-panel border border-line rounded-lg">
          <BoxesIcon className="mx-auto text-muted mb-3" size={40} />
          <p className="text-ink font-semibold">No components found</p>
          <p className="text-sm text-muted mt-1">Try expanding your search or selecting another category.</p>
        </div>
      )}

      {/* Products Grid */}
      {!loading && sortedProducts.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {sortedProducts.map((product) => (
            <div
              key={product.id}
              className="bg-[#0b1220]/60 border border-line hover:border-signal/40 rounded-xl p-5 flex flex-col justify-between transition-all"
            >
              <div>
                <div className="flex justify-between items-start gap-2 mb-3">
                  <span className="px-2.5 py-0.5 rounded text-[10px] font-extrabold uppercase bg-panel text-ink border border-line">
                    {product.category}
                  </span>
                  <span className="text-[11px] text-muted font-semibold">
                    MPN: {product.manufacturer_part_number || "Unavailable"}
                  </span>
                </div>

                <h3 className="text-base font-bold text-ink hover:text-signal transition-colors mb-1 line-clamp-1">
                  <a href={`/components/${product.id}`}>{product.canonical_name}</a>
                </h3>
                <p className="text-xs text-muted font-semibold mb-4">By {product.brand}</p>
                
                {/* Category Placeholder Image */}
                <div className="aspect-video w-full rounded-lg mb-4 overflow-hidden border border-line bg-gradient-to-br from-[#101a2d] to-[#0c1424]">
                  <ProductImage
                    imageUrl={null}
                    productName={product.canonical_name}
                    category={product.category}
                    width={320}
                    height={160}
                    variant="card"
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between items-center gap-4 mt-2">
                  <div className="flex flex-col">
                    <span className="text-xs text-muted font-semibold">Local Price</span>
                    <span className="text-sm font-extrabold text-amber-500">No current offer</span>
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={() => toggleCompare(product.id)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
                        compareIds.includes(product.id)
                          ? "bg-signal text-slate-950"
                          : "bg-panel border border-line text-muted hover:text-ink"
                      }`}
                    >
                      <BarChart3 size={13} />
                      {compareIds.includes(product.id) ? "Selected" : "Compare"}
                    </button>
                    <a
                      href={`/components/${product.id}`}
                      className="px-3 py-1.5 bg-panel border border-line hover:border-signal/40 text-ink rounded-lg text-xs font-bold transition-all"
                    >
                      View details
                    </a>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination controls */}
      {!loading && sortedProducts.length > 0 && (
        <div className="flex justify-between items-center mt-10 pt-6 border-t border-line">
          <button
            onClick={() => handlePageChange(page - 1)}
            disabled={page <= 1}
            className="flex items-center gap-1.5 px-4 py-2 bg-panel border border-line hover:border-signal/40 text-ink disabled:text-muted disabled:border-line rounded-lg text-xs font-bold transition-all"
          >
            <ChevronLeft size={16} />
            Previous Page
          </button>

          <span className="text-xs text-muted font-semibold">
            Showing page {page}
          </span>

          <button
            onClick={() => handlePageChange(page + 1)}
            disabled={sortedProducts.length < limit}
            className="flex items-center gap-1.5 px-4 py-2 bg-panel border border-line hover:border-signal/40 text-ink disabled:text-muted disabled:border-line rounded-lg text-xs font-bold transition-all"
          >
            Next Page
            <ChevronRight size={16} />
          </button>
        </div>
      )}

      {/* Public data source attribution notice */}
      <footer className="mt-16 text-center py-6 border-t border-line">
        <p className="text-xs text-muted leading-relaxed">
          Product specification data includes information from{" "}
          <a
            href="https://github.com/buildcores/buildcores-open-db"
            target="_blank"
            rel="noopener noreferrer"
            className="text-signal hover:underline"
          >
            BuildCores OpenDB
          </a>
          , licensed under{" "}
          <a
            href="https://opendatacommons.org/licenses/by/1-0/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-signal hover:underline"
          >
            ODC-By 1.0
          </a>
          .
        </p>
        <p className="text-[10px] text-muted/65 mt-1.5">
          This project is not affiliated with or endorsed by BuildCores.
        </p>
      </footer>
    </main>
  );
}

export function CategoryBrowser(props: CategoryBrowserProps) {
  return (
    <Suspense fallback={
      <div className="grid place-items-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-signal border-t-transparent"></div>
      </div>
    }>
      <CategoryBrowserImpl {...props} />
    </Suspense>
  );
}

function BoxesIcon({ className, size }: { className?: string; size?: number }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size || 24}
      height={size || 24}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l-7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
      <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
      <line x1="12" y1="22.08" x2="12" y2="12"></line>
    </svg>
  );
}
