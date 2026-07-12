"use client";

import { Menu, Search, ShieldCheck, Sun, SunDim, X } from "lucide-react";
import { useState } from "react";
import Link from "next/link";
import { useTheme } from "@/components/ThemeProvider";

const mobileLinks = [
  ["Home", "/"],
  ["Generate", "/build/generate"],
  ["Pick parts", "/build/manual"],
  ["Saved", "/build/generate#saved-builds"],
  ["Feedback", "/#feedback"]
] as const;

export function LandingTopBar() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();
  const dark = theme === "dark";
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-[#070b13]/88 px-4 py-3 backdrop-blur sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-7xl items-center gap-3">
        <Link href="/" className="flex items-center gap-2 font-bold text-ink lg:hidden">
          <span className="grid h-8 w-8 place-items-center rounded-md bg-signal text-slate-950">SB</span>
          SaudiBuild
        </Link>

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
            onClick={toggleTheme}
            className="grid h-9 w-9 place-items-center rounded-md border border-line bg-white text-muted"
            aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
            title={dark ? "Switch to light mode" : "Switch to dark mode"}
          >
            {dark ? <SunDim size={16} aria-hidden /> : <Sun size={16} aria-hidden />}
          </button>
          <button
            type="button"
            onClick={() => setMobileOpen((open) => !open)}
            className="grid h-9 w-9 place-items-center rounded-md border border-line bg-panel text-muted lg:hidden"
            aria-label={mobileOpen ? "Close navigation menu" : "Open navigation menu"}
            aria-expanded={mobileOpen}
            aria-controls="mobile-navigation"
          >
            {mobileOpen ? <X size={18} aria-hidden /> : <Menu size={18} aria-hidden />}
          </button>
        </div>
      </div>
      {mobileOpen ? (
        <nav id="mobile-navigation" aria-label="Mobile navigation" className="mx-auto mt-3 grid max-w-7xl gap-1 border-t border-line pt-3 lg:hidden">
          {mobileLinks.map(([label, href]) => (
            <Link key={label} href={href} onClick={() => setMobileOpen(false)} className="rounded-md px-3 py-2 text-sm font-semibold text-muted hover:bg-panel hover:text-ink">
              {label}
            </Link>
          ))}
        </nav>
      ) : null}
    </header>
  );
}
