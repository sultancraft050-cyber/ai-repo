type BuyerNotesOptions = {
  maxVisible?: number;
  fallback?: string;
  summary?: string;
};

export type BuyerNotesSummary = {
  summary: string;
  visible: string[];
  details: string[];
  count: number;
  hasDetails: boolean;
};

export function summarizeBuyerNotes(notes: Array<string | null | undefined>, options: BuyerNotesOptions = {}): BuyerNotesSummary {
  const maxVisible = options.maxVisible ?? 2;
  const cleaned = Array.from(
    new Set(
      notes
        .map((note) => calmBuyerNote(note))
        .filter((note): note is string => Boolean(note))
    )
  );
  const visible = cleaned.slice(0, maxVisible);
  const details = cleaned.slice(maxVisible);
  return {
    summary: cleaned.length ? options.summary ?? "Some details need review before buying." : options.fallback ?? "No buyer notes right now.",
    visible,
    details,
    count: cleaned.length,
    hasDetails: details.length > 0
  };
}

function calmBuyerNote(note?: string | null): string | null {
  const text = (note ?? "").replace(/\s+/g, " ").trim();
  if (!text) return null;
  const lower = text.toLowerCase();
  if (lower.includes("no sar price") || lower.includes("price available") || lower.includes("price unknown")) {
    return "Price not listed yet.";
  }
  if (lower.includes("vat") && (lower.includes("unknown") || lower.includes("unclear"))) {
    return "VAT may need a store check.";
  }
  if (lower.includes("shipping") && (lower.includes("unknown") || lower.includes("unclear"))) {
    return "Delivery details may need a store check.";
  }
  if (lower.includes("warranty") && (lower.includes("unknown") || lower.includes("unclear"))) {
    return "Warranty details may need a store check.";
  }
  if (lower.includes("imported listing")) {
    return "This option may ship from outside Saudi stock.";
  }
  if (lower.includes("missing") && lower.includes("spec")) {
    return "Some specs need confirmation.";
  }
  if (text.length > 150) return `${text.slice(0, 147).trim()}...`;
  return text;
}
