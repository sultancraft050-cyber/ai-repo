"use client";

import { useParams } from "next/navigation";
import { AppChrome } from "@/components/AppChrome";
import { ProductDetails } from "@/components/ProductDetails";

export default function ProductDetailPage() {
  const params = useParams();
  const id = params.id as string;
  return (
    <AppChrome>
      <ProductDetails productId={Number(id)} />
    </AppChrome>
  );
}
