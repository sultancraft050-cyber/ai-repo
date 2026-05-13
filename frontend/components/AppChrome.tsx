import type { ReactNode } from "react";
import { LandingSidebar } from "@/components/LandingSidebar";
import { LandingTopBar } from "@/components/LandingTopBar";

export function AppChrome({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen lg:flex">
      <LandingSidebar />
      <div className="min-w-0 flex-1">
        <LandingTopBar />
        {children}
      </div>
    </div>
  );
}
