// Pure data-shaping helpers for the BOM output page.
//
// Extracted from src/pages/bom-output.tsx so they can be unit-tested
// without spinning up React. Keep these pure: no DOM, no React, no
// network. Anything that touches Blob/anchor/URL.createObjectURL stays
// in bom-output.tsx (downloadCsv wraps buildCsvRows for that reason).

import type { BomLineItem, BomResponse } from "./api-hooks";

// ─── Display shapes ──────────────────────────────────────────────────────

// Three-state provenance:
//   "rules"    — the deterministic rules engine OR a catalog_match
//                emitted this line straight from Tom's catalog.
//   "verified" — AI proposed this line, BUT its SKU was verified after
//                the fact against the Wrightsoft catalog (Day-12
//                cross-pollination pass). Almost as trustworthy as
//                rules; just a different code path.
//   "ai"       — pure AI inference, no catalog backing. Spot-check
//                before sending to a customer.
export type Source = "rules" | "verified" | "ai";

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

// Collapse provenance to a 3-state enum. The Flask backend emits
// detailed sources (rules_engine, catalog_match, catalog_verified_*,
// wrightsoft_*, ai_inferred, ai_with_catalog_sku, etc.) — this folds
// them into the three categories the UI actually renders.
//
// Default is "ai" because false-positive review costs a glance,
// false-negative review could ship hallucinated quantities — when in
// doubt, force a human look.
export function normalizeSource(raw: string | undefined): Source {
  if (!raw) return "ai";
  const r = raw.toLowerCase();
  // Catalog-emitted lines (rules engine OR per-equipment catalog match)
  if (r === "rules" || r === "rules_engine" || r === "catalog_match") {
    return "rules";
  }
  // Wrightsoft deterministic pipeline (mapped/dfunit/passthrough have
  // real SKUs) + AI-then-verified-by-catalog. wrightsoft_unmapped is
  // intentionally NOT verified — those lines have no SKU resolution,
  // they're the SKU Backlog candidates and need a human look.
  if (
    r === "wrightsoft_mapped" ||
    r === "wrightsoft_dfunit" ||
    r === "wrightsoft_passthrough" ||
    r.startsWith("catalog_verified")
  ) {
    return "verified";
  }
  return "ai";
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
  verified: number;
  ai: number;
  hasProvenance: boolean;
}

// Compute provenance counts by normalizing each line's raw source
// through the same 3-state classifier the badge renderer uses. Pure
// derivation from line_items so the totals always match what's on
// screen — earlier versions used backend-reported counts which
// drifted from line_items once the verifier started promoting lines.
export function computeProvenanceCounts(
  bom: Pick<BomResponse, "line_items">
): ProvenanceCounts {
  const items = bom.line_items ?? [];
  let rules = 0, verified = 0, ai = 0;
  for (const l of items) {
    const s = normalizeSource(l.source);
    if (s === "rules") rules++;
    else if (s === "verified") verified++;
    else ai++;
  }
  return { rules, verified, ai, hasProvenance: items.length > 0 };
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
