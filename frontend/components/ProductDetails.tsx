"use client";

import { useState, useEffect } from "react";
import { ArrowLeft, ShieldCheck, ShoppingCart, Info } from "lucide-react";
import { getCatalogProduct, CatalogProductDetail } from "@/lib/api";
import { ProductImage } from "@/components/ProductImage";

export function ProductDetails({ productId }: { productId: number }) {
  const [product, setProduct] = useState<CatalogProductDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      if (!productId) return;
      setLoading(true);
      setError("");
      try {
        const data = await getCatalogProduct(productId);
        setProduct(data);
      } catch (err: any) {
        setError(err.message || "Failed to load component details.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [productId]);

  if (loading) {
    return (
      <div className="grid place-items-center py-32">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-signal border-t-transparent"></div>
      </div>
    );
  }

  if (error || !product) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <a href="/components" className="flex items-center gap-1.5 text-xs font-bold text-signal hover:underline mb-6">
          <ArrowLeft size={14} /> Back to Catalog
        </a>
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-5 rounded-lg text-sm">
          {error || "Component details not found."}
        </div>
      </div>
    );
  }

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <a href="/components" className="flex items-center gap-1.5 text-xs font-bold text-signal hover:underline mb-6">
        <ArrowLeft size={14} /> Back to Catalog
      </a>

      {/* Header and Summary card */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-8 mb-8 bg-[#0b1220]/60 border border-line rounded-2xl p-6 md:p-8">
        {/* Placeholder image */}
        <div className="md:col-span-4 aspect-square rounded-xl overflow-hidden border border-line bg-gradient-to-br from-[#101a2d] to-[#0c1424] flex items-center justify-center">
          <ProductImage
            imageUrl={null}
            productName={product.canonical_name}
            category={product.category}
            width={320}
            height={320}
            variant="detail"
          />
        </div>

        {/* Identity fields */}
        <div className="md:col-span-8 flex flex-col justify-between">
          <div>
            <div className="flex flex-wrap gap-2 mb-3">
              <span className="px-2.5 py-0.5 rounded text-[10px] font-extrabold uppercase bg-panel text-ink border border-line">
                {product.category}
              </span>
              <span className="px-2.5 py-0.5 rounded text-[10px] font-extrabold uppercase bg-teal-500/10 text-teal-400 border border-teal-500/20">
                {product.lifecycle_status}
              </span>
            </div>

            <h1 className="text-2xl md:text-3xl font-extrabold text-ink leading-tight mb-2">
              {product.canonical_name}
            </h1>
            <p className="text-sm font-semibold text-muted mb-4">
              Manufacturer: <span className="text-ink">{product.brand}</span>
            </p>

            <div className="grid grid-cols-2 gap-4 border-t border-b border-line py-4 my-4">
              <div>
                <span className="block text-[10px] uppercase font-bold text-muted">Part Number (MPN)</span>
                <span className="text-sm font-bold text-ink">{product.manufacturer_part_number || "Unavailable"}</span>
              </div>
              <div>
                <span className="block text-[10px] uppercase font-bold text-muted">GTIN (EAN/UPC)</span>
                <span className="text-sm font-bold text-ink">{product.gtin || "Unavailable"}</span>
              </div>
            </div>
          </div>

          <div className="flex justify-between items-center gap-4 bg-panel/30 p-3 rounded-lg border border-line/50">
            <span className="text-xs text-muted font-semibold">Cheapest local offer</span>
            <span className="text-lg font-black text-amber-500">
              {product.cheapest_sar_offer
                ? `${product.cheapest_sar_offer.sale_price || product.cheapest_sar_offer.regular_price} SAR`
                : "No current offer"}
            </span>
          </div>
        </div>
      </div>

      {/* Grid of details */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Specifications */}
        <section className="bg-[#0b1220]/60 border border-line rounded-2xl p-6">
          <h2 className="text-lg font-bold text-ink flex items-center gap-2 mb-4 border-b border-line pb-3">
            <ShieldCheck className="text-signal" size={19} />
            Technical Specifications
          </h2>

          {product.specifications.length === 0 ? (
            <p className="text-sm text-muted">No specifications registered for this component.</p>
          ) : (
            <div className="grid gap-3">
              {product.specifications.map((spec) => (
                <div key={spec.specification_key} className="flex justify-between items-center py-2 border-b border-line/45 last:border-0 text-sm">
                  <span className="text-muted font-medium capitalize">
                    {spec.specification_key.replace(/_/g, " ")}
                  </span>
                  <span className="text-ink font-bold">
                    {spec.display_value}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Offers & Sellers */}
        <section className="bg-[#0b1220]/60 border border-line rounded-2xl p-6">
          <h2 className="text-lg font-bold text-ink flex items-center gap-2 mb-4 border-b border-line pb-3">
            <ShoppingCart className="text-signal" size={19} />
            Seller Offers
          </h2>

          {product.offers.length === 0 ? (
            <div className="text-center py-10">
              <Info className="mx-auto text-muted mb-2" size={24} />
              <p className="text-sm text-ink font-bold">No active offers found</p>
              <p className="text-xs text-muted mt-0.5">No current store offers are available for this product.</p>
            </div>
          ) : (
            <div className="grid gap-4">
              {product.offers.map((offer) => (
                <div
                  key={offer.id}
                  className="bg-panel/40 border border-line rounded-xl p-4 flex justify-between items-center transition-all hover:border-signal/20"
                >
                  <div>
                    <span className="text-xs font-black text-ink">{offer.store?.name || "Local Seller"}</span>
                    <span className="block text-[10px] text-muted font-semibold mt-0.5">SKU: {offer.store_sku}</span>
                  </div>

                  <div className="text-right flex flex-col items-end gap-1">
                    <span className="text-base font-extrabold text-amber-500">
                      {offer.sale_price || offer.regular_price} {offer.currency}
                    </span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                      offer.stock_status === "in_stock"
                        ? "bg-teal-500/10 text-teal-400"
                        : "bg-red-500/10 text-red-400"
                    }`}>
                      {offer.stock_status.replace(/_/g, " ").toUpperCase()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

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
