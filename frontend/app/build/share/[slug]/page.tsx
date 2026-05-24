import type { Metadata } from "next";
import { SharedBuildPageClient } from "@/components/SharedBuildPageClient";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  return {
    title: "Shared Saudi PC Build | Prices, Warnings, and Compatibility",
    description: "Review a shared Saudi PC build with SAR pricing, budget status, compatibility notes, confidence, and visible marketplace warnings.",
    openGraph: {
      title: "Shared Saudi PC Build",
      description: "Saudi PC build summary with SAR prices, budget fit, warnings, and compatibility confidence.",
      type: "article",
      url: `/build/share/${slug}`
    },
    robots: {
      index: true,
      follow: true
    }
  };
}

export default async function SharedBuildPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <SharedBuildPageClient slug={slug} />;
}
