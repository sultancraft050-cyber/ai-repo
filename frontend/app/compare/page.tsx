"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Cpu, ArrowLeft, Trash2, Plus, BarChart3 } from "lucide-react";
import { AppChrome } from "@/components/AppChrome";
import { getCatalogProduct, listCatalogProducts, CatalogProductDetail, CatalogProduct } from "@/lib/api";

function CompareContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const category = searchParams.get("category") || "CPU";
  const idsParam = searchParams.get("ids") || "";

  const [comparedProducts, setComparedProducts] = useState<CatalogProductDetail[]>([]);
  const [availableProducts, setAvailableProducts] = useState<CatalogProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showAddSelector, setShowAddSelector] = useState(false);

  const compareIds = idsParam
    ? idsParam.split(",").map(Number).filter((x) => !isNaN(x))
    : [];

  useEffect(() => {
    async function load() {
      if (compareIds.length === 0) {
        setComparedProducts([]);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError("");
      try {
        const promises = compareIds.map((id) => getCatalogProduct(id));
        const results = await Promise.all(promises);
        setComparedProducts(results);
      } catch (err: any) {
        setError(err.message || "Failed to load components for comparison.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [idsParam]);

  // Load other products of same category for the "Add to Compare" dropdown
  useEffect(() => {
    async function loadAvailable() {
      try {
        const data = await listCatalogProducts(0, 100, category);
        // filter out already compared
        setAvailableProducts(data.filter((p) => !compareIds.includes(p.id)));
      } catch {
        // ignore background load errors
      }
    }
    if (category) {
      loadAvailable();
    }
  }, [category, idsParam]);

  const handleCategoryChange = (newCat: string) => {
    const params = new URLSearchParams();
    params.set("category", newCat);
    router.push(`/compare?${params.toString()}`);
  };

  const removeProduct = (id: number) => {
    const remaining = compareIds.filter((x) => x !== id);
    const params = new URLSearchParams();
    params.set("category", category);
    if (remaining.length > 0) {
      params.set("ids", remaining.join(","));
    }
    router.push(`/compare?${params.toString()}`);
  };

  const addProduct = (id: number) => {
    if (compareIds.length >= 4) {
      alert("You can compare up to 4 components.");
      return;
    }
    const updated = [...compareIds, id];
    const params = new URLSearchParams();
    params.set("category", category);
    params.set("ids", updated.join(","));
    router.push(`/compare?${params.toString()}`);
    setShowAddSelector(false);
  };

  // Get union of all specification keys
  const specKeys = Array.from(
    new Set(
      comparedProducts.flatMap((p) =>
        p.specifications.map((s) => s.specification_key)
      )
    )
  );

  return (
    <main className="p-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-extrabold text-ink tracking-tight flex items-center gap-2">
            <BarChart3 size={28} className="text-signal" />
            Component Comparison
          </h1>
          <p className="text-sm text-muted mt-1">
            Compare technical specifications, capabilities, and local pricing side-by-side.
          </p>
        </div>

        <a href="/components" className="flex items-center gap-1.5 text-xs font-bold text-signal hover:underline">
          <ArrowLeft size={14} /> Back to Catalog
        </a>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap gap-4 items-center justify-between bg-[#0b1220]/60 border border-line rounded-xl p-4 mb-8">
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted font-bold uppercase">Category</span>
          <select
            value={category}
            onChange={(e) => handleCategoryChange(e.target.value)}
            className="bg-panel border border-line rounded-lg px-3 py-1.5 text-ink text-xs font-bold focus:border-signal focus:outline-none"
          >
            {["CPU", "GPU", "MOTHERBOARD", "RAM", "STORAGE", "PSU", "CASE", "COOLER"].map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        </div>

        {compareIds.length < 4 && (
          <div className="relative">
            <button
              onClick={() => setShowAddSelector(!showAddSelector)}
              className="flex items-center gap-1.5 px-4 py-2 bg-signal hover:bg-signal/80 text-slate-950 text-xs font-extrabold rounded-lg transition-all"
            >
              <Plus size={14} /> Add Component
            </button>

            {showAddSelector && (
              <div className="absolute right-0 mt-2 w-64 max-h-60 overflow-y-auto bg-panel border border-line rounded-lg shadow-xl z-10 py-1">
                {availableProducts.length === 0 ? (
                  <span className="block px-4 py-2 text-xs text-muted">No components available</span>
                ) : (
                  availableProducts.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => addProduct(p.id)}
                      className="w-full text-left px-4 py-2 text-xs text-muted hover:text-ink hover:bg-slate-900 transition-colors"
                    >
                      {p.canonical_name}
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {loading && (
        <div className="grid place-items-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-signal border-t-transparent"></div>
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-4 rounded-lg text-sm mb-6">
          {error}
        </div>
      )}

      {!loading && comparedProducts.length === 0 && (
        <div className="text-center py-20 bg-panel border border-line rounded-2xl">
          <BarChart3 className="mx-auto text-muted mb-4" size={48} />
          <h2 className="text-lg font-bold text-ink">No components selected for comparison</h2>
          <p className="text-sm text-muted mt-1 max-w-md mx-auto">
            Choose up to 4 components of the same category to inspect and contrast their configurations.
          </p>
          <a
            href={`/components/${category.toLowerCase()}`}
            className="inline-block mt-6 px-4 py-2 bg-signal hover:bg-signal/80 text-slate-950 text-xs font-extrabold rounded-lg transition-all"
          >
            Browse {category}s
          </a>
        </div>
      )}

      {!loading && comparedProducts.length > 0 && (
        <div className="overflow-x-auto bg-[#0b1220]/60 border border-line rounded-2xl">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-line">
                <th className="p-4 w-60 text-left text-xs font-bold uppercase text-muted tracking-wider bg-panel/20">
                  Feature
                </th>
                {comparedProducts.map((product) => (
                  <th key={product.id} className="p-4 text-left min-w-[200px] border-l border-line relative align-top">
                    <button
                      onClick={() => removeProduct(product.id)}
                      className="absolute top-4 right-4 text-muted hover:text-red-400 transition-colors p-1"
                      aria-label="Remove from comparison"
                    >
                      <Trash2 size={15} />
                    </button>

                    <div className="aspect-video w-full rounded-lg mb-4 bg-gradient-to-br from-[#101a2d] to-[#0c1424] border border-line flex items-center justify-center text-muted">
                      <Cpu size={24} className="text-teal-500/35" />
                    </div>

                    <h3 className="text-sm font-bold text-ink hover:underline">
                      <a href={`/components/${product.id}`}>{product.canonical_name}</a>
                    </h3>
                    <p className="text-xs text-muted font-semibold mt-1">By {product.brand}</p>
                    <p className="text-[10px] text-muted/80 mt-0.5">MPN: {product.manufacturer_part_number}</p>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {/* Price row */}
              <tr className="border-b border-line hover:bg-panel/10 transition-colors">
                <td className="p-4 text-xs font-extrabold uppercase text-muted bg-panel/10">
                  Cheapest Local Offer
                </td>
                {comparedProducts.map((product) => (
                  <td key={product.id} className="p-4 text-sm font-black text-amber-500 border-l border-line">
                    {product.cheapest_sar_offer
                      ? `${product.cheapest_sar_offer.sale_price || product.cheapest_sar_offer.regular_price} SAR`
                      : "Price unavailable"}
                  </td>
                ))}
              </tr>

              {/* Specifications rows */}
              {specKeys.map((key) => (
                <tr key={key} className="border-b border-line hover:bg-panel/10 transition-colors">
                  <td className="p-4 text-xs font-bold uppercase text-muted capitalize bg-panel/10">
                    {key.replace(/_/g, " ")}
                  </td>
                  {comparedProducts.map((product) => {
                    const spec = product.specifications.find(
                      (s) => s.specification_key === key
                    );
                    return (
                      <td key={product.id} className="p-4 text-sm text-ink font-semibold border-l border-line">
                        {spec ? spec.display_value : "-"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Public data source attribution notice */}
      <footer className="mt-16 text-center py-6 border-t border-line">
        <p className="text-xs text-muted leading-relaxed">
          Product specifications and database schema derived from{" "}
          <a
            href="https://github.com/buildcores/buildcores-open-db"
            target="_blank"
            rel="noopener noreferrer"
            className="text-signal hover:underline"
          >
            BuildCores OpenDB
          </a>{" "}
          are used under the{" "}
          <a
            href="https://opendatacommons.org/licenses/by/1-0/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-signal hover:underline"
          >
            Open Data Commons Attribution License (ODC-By 1.0)
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

export default function ComparePage() {
  return (
    <AppChrome>
      <Suspense fallback={<div className="grid place-items-center py-20"><div className="h-8 w-8 animate-spin rounded-full border-4 border-signal border-t-transparent"></div></div>}>
        <CompareContent />
      </Suspense>
    </AppChrome>
  );
}
