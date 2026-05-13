"use client";

import { Search, ShieldCheck, SunDim } from "lucide-react";

export function LandingTopBar() {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-[#070b13]/88 px-4 py-3 backdrop-blur sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-7xl items-center gap-3">
        <a href="#" className="flex items-center gap-2 font-bold text-ink lg:hidden">
          <span className="grid h-8 w-8 place-items-center rounded-md bg-signal text-slate-950">SB</span>
          SaudiBuild
        </a>

        <div className="mx-auto hidden h-9 w-full max-w-xl items-center gap-2 rounded-md border border-line bg-white px-3 text-sm text-muted md:flex">
          <Search size={16} aria-hidden />
          <span>Search parts later...</span>
          <span className="ml-auto rounded border border-line bg-panel px-1.5 py-0.5 text-[10px]">Ctrl+K</span>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <span className="hidden items-center gap-1 rounded-md border border-line bg-panel px-2 py-1 text-xs font-semibold text-muted sm:inline-flex">
            <ShieldCheck size={14} aria-hidden />
            Saudi only
          </span>
          <button
            type="button"
            className="grid h-9 w-9 place-items-center rounded-md border border-line bg-white text-muted"
            aria-label="Dark mode active"
            title="Dark mode active"
          >
            <SunDim size={16} aria-hidden />
          </button>
        </div>
      </div>
    </header>
  );
}
