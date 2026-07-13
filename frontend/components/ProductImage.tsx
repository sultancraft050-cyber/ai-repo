"use client";

import { useMemo, useState } from "react";
import type { ComponentKind } from "@/types/builder";

export type ProductImageVariant = "card" | "build-summary" | "detail";
export type ProductImageCategory = ComponentKind | "Unknown" | string;

type ProductImageProps = {
  imageUrl?: string | null;
  productName: string;
  category?: ProductImageCategory | null;
  width: number;
  height: number;
  variant?: ProductImageVariant;
  priority?: boolean;
  className?: string;
};

// Keep this list intentionally narrow. A real production host must be reviewed
// from repository evidence before it is added; local assets remain supported.
const APPROVED_REMOTE_HOSTS = new Set(["cdn.example.test"]);

const categoryLabels: Record<string, string> = {
  CPU: "CPU",
  GPU: "GPU",
  Motherboard: "Motherboard",
  RAM: "RAM",
  Storage: "Storage",
  PSU: "Power supply",
  Case: "Case",
  Cooler: "Cooler"
};

function categoryLabel(category?: ProductImageCategory | null): string {
  const key = String(category ?? "Unknown");
  return categoryLabels[key] ?? (key.trim() ? key : "Unknown category");
}

function usableImageUrl(value?: string | null): string | null {
  const candidate = value?.trim();
  if (!candidate || candidate.startsWith("//")) return null;
  if (candidate.startsWith("/")) return candidate;
  try {
    const parsed = new URL(candidate);
    if (parsed.protocol !== "https:" || !parsed.hostname || !APPROVED_REMOTE_HOSTS.has(parsed.hostname)) return null;
    return parsed.toString();
  } catch {
    return null;
  }
}

function PlaceholderArtwork({ label }: { label: string }) {
  return (
    <svg aria-hidden="true" className="h-16 w-16 text-slate-400" viewBox="0 0 80 80" fill="none">
      <rect x="8" y="8" width="64" height="64" rx="14" className="fill-slate-100 stroke-current dark:fill-slate-800" strokeWidth="2" />
      <path d="M24 50h32M28 44V30h24v14M34 30v-6h12v6M32 56h16" className="stroke-current" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <text x="40" y="66" textAnchor="middle" className="fill-current text-[8px] font-bold" style={{ fontSize: 8 }}>
        {label.slice(0, 10)}
      </text>
    </svg>
  );
}

export function ProductImage({
  imageUrl,
  productName,
  category,
  width,
  height,
  variant = "card",
  priority = false,
  className = ""
}: ProductImageProps) {
  const [failed, setFailed] = useState(false);
  const safeUrl = useMemo(() => usableImageUrl(imageUrl), [imageUrl]);
  const label = categoryLabel(category);
  const alt = `${productName || "Product"} ${label} image`;
  const showImage = Boolean(safeUrl && !failed);

  return (
    <div
      className={`product-image product-image--${variant} relative grid place-items-center overflow-hidden rounded-md bg-white dark:bg-slate-950 ${className}`}
      style={{ width, height, aspectRatio: `${width} / ${height}` }}
      data-testid="product-image"
      data-image-state={showImage ? "image" : "placeholder"}
      data-image-category={label}
    >
      {showImage ? (
        <img
          src={safeUrl ?? undefined}
          alt={alt}
          width={width}
          height={height}
          loading={priority ? "eager" : "lazy"}
          decoding="async"
          className="block h-full w-full object-contain object-center"
          onError={() => setFailed(true)}
        />
      ) : (
        <div className="grid h-full w-full place-items-center bg-slate-50 text-center dark:bg-slate-900" role="img" aria-label={`${productName || "Product"} ${label} placeholder`}>
          <PlaceholderArtwork label={label} />
        </div>
      )}
    </div>
  );
}
