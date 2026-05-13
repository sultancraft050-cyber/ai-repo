import { readFileSync } from "node:fs";

const checks = [
  {
    file: "components/BuildRecommendationCard.tsx",
    snippets: [
      "Build Summary",
      "Savings Suggestions",
      "Confidence Breakdown",
      "Recommended Purchase Order",
      "Export"
    ]
  },
  {
    file: "components/DataCompletenessPanel.tsx",
    snippets: ["Ready", "Usable", "Not ready", "Next:"]
  },
  {
    file: "components/SaudiBuildWizard.tsx",
    snippets: ["Build comparison", "No valid build fits this strict budget yet", "Budget discovery suggestions"]
  },
  {
    file: "components/BuilderShell.tsx",
    snippets: ["Advanced graph builder tools", "Founder operations and market data tools"]
  },
  {
    file: "components/ProductUrlImportPanel.tsx",
    snippets: ["Preview", "Approve ingest"]
  }
];

const failures = [];

for (const check of checks) {
  const source = readFileSync(new URL(`../${check.file}`, import.meta.url), "utf8");
  for (const snippet of check.snippets) {
    if (!source.includes(snippet)) {
      failures.push(`${check.file} is missing "${snippet}"`);
    }
  }
}

if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}

console.log(`UI contract checks passed (${checks.length} files).`);
