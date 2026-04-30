// Pure data-shaping helpers for the BOM output page.
//
// Extracted from src/pages/bom-output.tsx so they can be unit-tested
// without spinning up React. Keep these pure: no DOM, no React, no
// network. Anything that touches Blob/anchor/URL.createObjectURL stays
// in bom-output.tsx (downloadCsv wraps buildCsvRows for that reason).

import type { BomLineItem, BomResponse } from "./api-hooks";

// ─── Display shapes ──────────────────────────────────────────────────────

export type Source = "rules" | "ai";

export const CATEGORIES = ["equipment", "duct", "fitting", "consumable"] as const;
export type Category = (typeof CATEGORIES)[number];

export interface BomLine {
  id: string;
  category: Category;
  clientName: string;
  standardName: string;
  qty: number;
  unit: string;
  unitCost: number;
  markupPct: number;
  total: number;
  sku?: string;
  source: Source;
}

// ─── Mappers ─────────────────────────────────────────────────────────────

// Normalize unknown categories from the Flask backend into the 4 buckets
// the UI can render. Any unrecognized category falls back to consumable.
// "register" is folded into "fitting" since registers visually live under
// fittings in the SPA.
export function normalizeCategory(raw: string | undefined): Category {
  if (!raw) return "consumable";
  const key = raw.toLowerCase().trim();
  if (key === "equipment") return "equipment";
  if (key === "duct") return "duct";
  if (key === "fitting") return "fitting";
  if (key === "register") return "fitting";
  if (key === "consumable") return "consumable";
  return "consumable";
}

// Collapse provenance to a 2-state enum. Anything explicit-rules is
// "rules"; everything else (absent source, "ai", unknown future values)
// is treated as "ai" so it gets the review-me styling. Defaulting to
// "ai" is the safe choice — false-positive review costs a glance,
// false-negative review could ship hallucinated quantities.
export function normalizeSource(raw: string | undefined): Source {
  return raw === "rules" ? "rules" : "ai";
}

// Map a Flask-shaped line_item into the BomLine display shape. Prices
// are shown when available (full/materials_only/client_proposal modes),
// otherwise unit_cost + total_cost are used (cost_estimate mode).
export function mapLineItem(item: BomLineItem, index: number): BomLine {
  const cat = normalizeCategory(item.category);
  const unitCost = item.unit_price ?? item.unit_cost ?? 0;
  const total = item.total_price ?? item.total_cost ?? 0;
  return {
    id: `${cat}-${index}`,
    category: cat,
    clientName: item.description || "(unnamed)",
    standardName: item.description || "(unnamed)",
    qty: item.quantity ?? 0,
    unit: item.unit || "EA",
    unitCost,
    markupPct: item.markup_pct ?? 0,
    total,
    sku: item.sku || undefined,
    source: normalizeSource(item.source),
  };
}

// ─── Provenance counts ───────────────────────────────────────────────────

export interface ProvenanceCounts {
  rules: number;
  ai: number;
  hasProvenance: boolean;
}

// Prefer the backend-reported counts (post-rules-engine merge in
// procalcs-bom) and fall back to deriving from line_items for older
// response shapes that don't carry the totals.
export function computeProvenanceCounts(
  bom: Pick<BomResponse, "line_items" | "rules_engine_item_count" | "ai_item_count">
): ProvenanceCounts {
  const items = bom.line_items ?? [];
  const rules = bom.rules_engine_item_count ?? items.filter((l) => l.source === "rules").length;
  const ai = bom.ai_item_count ?? items.filter((l) => l.source !== "rules").length;
  return { rules, ai, hasProvenance: rules > 0 || ai > 0 };
}

// ─── CSV row builder ─────────────────────────────────────────────────────

export const CSV_HEADER = [
  "Category",
  "Source",
  "SKU",
  "Description",
  "Qty",
  "Unit",
  "Unit Cost",
  "Unit Price",
  "Markup %",
  "Total",
] as const;

// Returns a 2D string matrix: header row, one row per line item, blank
// row, then totals. The caller is responsible for serialization (so we
// can unit-test the structure without Blob/quoting concerns).
export function buildCsvRows(bom: BomResponse): string[][] {
  const rows: string[][] = [Array.from(CSV_HEADER)];
  for (const item of bom.line_items ?? []) {
    rows.push([
      item.category ?? "",
      normalizeSource(item.source),
      item.sku ?? "",
      item.description ?? "",
      String(item.quantity ?? 0),
      item.unit ?? "",
      String(item.unit_cost ?? ""),
      String(item.unit_price ?? ""),
      String(item.markup_pct ?? ""),
      String(item.total_price ?? item.total_cost ?? 0),
    ]);
  }
  rows.push([]);
  // Pad totals to the header width so column alignment survives in
  // spreadsheet apps. The 9 empty leading cells push totals into the
  // rightmost column under "Total".
  const pad = (label: string, value: string) => [label, "", "", "", "", "", "", "", "", value];
  rows.push(pad("Total Cost", String(bom.totals?.total_cost ?? "")));
  rows.push(pad("Total Price", String(bom.totals?.total_price ?? "")));
  return rows;
}

// CSV-escape: wrap every cell in double quotes and double-up any
// literal quotes inside. RFC 4180.
export function serializeCsv(rows: string[][]): string {
  return rows
    .map((r) => r.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
    .join("\r\n");
}
