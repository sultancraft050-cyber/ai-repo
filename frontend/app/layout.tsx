import type { Metadata } from "next";
import type { ReactNode } from "react";
import { cookies } from "next/headers";
import { RegionProvider } from "@/components/RegionProvider";
import { REGION_COOKIE, normalizeRegion } from "@/lib/region";
import "./globals.css";

export const metadata: Metadata = {
  title: "Saudi PC Build Assistant | Local Prices, Warnings, and Compatibility",
  description: "Build and compare Saudi PC builds with SAR pricing, compatibility checks, confidence scoring, and visible VAT, shipping, warranty, and marketplace warnings.",
  openGraph: {
    title: "Saudi PC Build Assistant",
    description: "Plan Saudi PC builds with local prices, budget fit, warnings, and compatibility confidence.",
    type: "website",
    locale: "en_US"
  },
  robots: {
    index: true,
    follow: true
  }
};

export default async function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  const cookieStore = await cookies();
  const initialRegion = normalizeRegion(cookieStore.get(REGION_COOKIE)?.value);
  return (
    <html lang="en">
      <body>
        <RegionProvider initialRegion={initialRegion}>{children}</RegionProvider>
      </body>
    </html>
  );
}
