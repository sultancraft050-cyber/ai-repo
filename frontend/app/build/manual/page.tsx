import type { Metadata } from "next";
import Link from "next/link";
import { AppChrome } from "@/components/AppChrome";
import { ManualPartPicker } from "@/components/ManualPartPicker";
import { RegionSelector } from "@/components/RegionSelector";

export const metadata: Metadata = {
  title: "Pick PC Parts Manually | Saudi PC Build Assistant",
  description: "Choose every PC part yourself and review estimated SAR total, wattage, FPS, compatibility, and warnings."
};

export default function ManualBuildPage() {
  return (
    <AppChrome>
      <main className="min-h-screen">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-5 sm:px-6 lg:px-8">
          <div className="flex flex-col gap-3 rounded-lg border border-line bg-white p-4 shadow-tight md:flex-row md:items-center md:justify-between">
            <div>
              <div className="mb-1 text-xs font-semibold uppercase text-signal">Manual path</div>
              <h1 className="text-xl font-semibold text-ink">Pick every part yourself</h1>
              <p className="mt-1 max-w-2xl text-sm leading-6 text-muted">
                Choose each core PC part in its own row, then review estimated wattage, FPS, total SAR price, warnings, and compatibility.
              </p>
              <Link href="/" className="mt-3 inline-flex text-sm font-semibold text-signal">
                Back to home
              </Link>
            </div>
            <RegionSelector />
          </div>
          <ManualPartPicker />
        </div>
      </main>
    </AppChrome>
  );
}
