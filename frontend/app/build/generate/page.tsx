import type { Metadata } from "next";
import { AppChrome } from "@/components/AppChrome";
import { BuilderShell } from "@/components/BuilderShell";

export const metadata: Metadata = {
  title: "Generate a Saudi PC Build | Saudi PC Build Assistant",
  description: "Enter your Saudi budget and target resolution to generate compatible PC build options with SAR pricing and warnings."
};

export default function GenerateBuildPage() {
  return (
    <AppChrome>
      <BuilderShell />
    </AppChrome>
  );
}
