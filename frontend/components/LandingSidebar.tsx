"use client";

import { BarChart3, Boxes, Cpu, MessageSquare, MonitorUp, Save } from "lucide-react";

const navItems = [
  { label: "Home", icon: Boxes, href: "/" },
  { label: "Generate", icon: Cpu, href: "/build/generate" },
  { label: "Pick Parts", icon: Boxes, href: "/build/manual" },
  { label: "Saved", icon: Save, href: "/build/generate#saved-builds" },
  { label: "Compare", icon: BarChart3, href: "/build/generate" },
  { label: "Feedback", icon: MessageSquare, href: "/#feedback" }
];

export function LandingSidebar() {
  return (
    <aside className="hidden min-h-screen w-64 shrink-0 border-r border-line bg-[#070b13]/92 px-4 py-5 lg:block">
      <a href="#" className="mb-6 flex items-center gap-3">
        <span className="grid h-9 w-9 place-items-center rounded-lg bg-signal text-slate-950">
          <Boxes size={19} aria-hidden />
        </span>
        <span>
          <span className="block text-base font-bold text-ink">SaudiBuild</span>
          <span className="text-xs font-semibold uppercase text-muted">MVP</span>
        </span>
      </a>

      <nav className="grid gap-2" aria-label="Main navigation">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <a
              key={item.label}
              href={item.href}
              className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-semibold text-muted hover:bg-panel hover:text-ink"
            >
              <Icon size={17} aria-hidden />
              {item.label}
            </a>
          );
        })}
      </nav>

      <div className="mt-7 rounded-lg border border-line bg-panel p-3">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
          <MonitorUp size={16} aria-hidden />
          Saudi market
        </div>
        <p className="text-xs leading-5 text-muted">
          SAR prices, visible warnings, and compatibility checks stay in the buying flow.
        </p>
      </div>
    </aside>
  );
}
