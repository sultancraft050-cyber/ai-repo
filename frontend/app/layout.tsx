import type { Metadata } from "next";
import type { ReactNode } from "react";
import { cookies } from "next/headers";
import { RegionProvider } from "@/components/RegionProvider";
import { REGION_COOKIE, normalizeRegion } from "@/lib/region";
import "./globals.css";

export const metadata: Metadata = {
  title: "PC Compatibility Intelligence",
  description: "Constraint-driven custom PC builder backed by Neo4j, FastAPI, NumPy, and XState."
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
