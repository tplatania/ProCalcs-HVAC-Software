// bom-diff.ts — pure helpers for diffing two BOM responses.
//
// Used by the Run-Diff diagnostic page (/diagnostics/run-diff). Kept
// out of the page module so we can unit-test the diff math without
// spinning up React + jsdom — same pattern as bom-mapping.ts.
//
// Diff strategy: pair lines by SKU when both sides have one, otherwise
// fall back to a (description|section|source) tuple so AI-only lines
// (which have no SKU) still align across two runs of the same RUP.
// Inside each key we coalesce duplicates by summing quantity + cost +
// price — multiple "Hanger straps" rows in one BOM merge to a single
// diff row before being matched against the other side.

import type { BomLineItem, BomResponse } from "./api-hooks";

export type DiffChange =
  | "unchanged"
  | "added"        // present on right, absent on left
  | "removed"      // present on left, absent on right
  | "qty_changed" // same key, qty differs (cost/price may also differ)
  | "price_changed" // same key + qty, only money fields differ
  | "changed";     // catch-all if multiple fields drift in odd combos

export interface DiffRow {
  key: string;
  label: string;          // human-friendly identifier (sku or description)
  section: string | null; // best-guess section to group rows in the UI
  source: string | null;
  left: AggregatedLine | null;
  right: AggregatedLine | null;
  change: DiffChange;
  // Per-row deltas — null on add/remove rows since one side is absent.
  qtyDelta: number | null;
  totalCostDelta: number | null;
  totalPriceDelta: number | null;
}

export interface AggregatedLine {
  key: string;
  label: string;
  section: string | null;
  source: string | null;
  unit: string | null;
  quantity: number;
  total_cost: number;
  total_price: number;
  // Original line items that fed this aggregation (for tooltips / drill-in).
  originals: BomLineItem[];
}

export interface DiffSummary {
  leftItemCount: number;
  rightItemCount: number;
  itemCountDelta: number;        // right - left
  leftTotalCost: number;
  rightTotalCost: number;
  totalCostDelta: number;
  leftTotalPrice: number;
  rightTotalPrice: number;
  totalPriceDelta: number;
  addedCount: number;
  removedCount: number;
  changedCount: number;          // qty_changed + price_changed + changed
  unchangedCount: number;
}

export interface DiffResult {
  rows: DiffRow[];
  summary: DiffSummary;
}

// ─── Internals ─────────────────────────────────────────────────────────

function lineKey(li: BomLineItem): string {
  const sku = (li.sku ?? "").trim();
  if (sku) return `sku:${sku.toUpperCase()}`;
  // Fallback: description + section + source. Lowercased so casing
  // jitter from the AI doesn't break the pairing.
  const desc = (li.description ?? "").trim().toLowerCase();
  const section = (li.section ?? "").trim().toLowerCase();
  const source = (li.source ?? "").trim().toLowerCase();
  return `desc:${desc}|${section}|${source}`;
}

function bestLabel(li: BomLineItem): string {
  const sku = (li.sku ?? "").trim();
  if (sku) return sku;
  return (li.description ?? "(unlabeled)").trim();
}

// Aggregate a side into a key→row map. Duplicate keys (same SKU emitted
// twice in one BOM) get their quantity / totals summed and original
// rows preserved on `.originals`.
export function aggregateBom(bom: BomResponse | null | undefined): Map<string, AggregatedLine> {
  const out = new Map<string, AggregatedLine>();
  if (!bom?.line_items) return out;

  for (const li of bom.line_items) {
    const key = lineKey(li);
    const existing = out.get(key);
    const qty = Number(li.quantity ?? 0) || 0;
    const tc = Number(li.total_cost ?? 0) || 0;
    const tp = Number(li.total_price ?? 0) || 0;

    if (existing) {
      existing.quantity += qty;
      existing.total_cost += tc;
      existing.total_price += tp;
      existing.originals.push(li);
    } else {
      out.set(key, {
        key,
        label:    bestLabel(li),
        section:  li.section ?? null,
        source:   li.source ?? null,
        unit:     li.unit ?? null,
        quantity: qty,
        total_cost: tc,
        total_price: tp,
        originals: [li],
      });
    }
  }
  return out;
}

// Tolerance for "equal enough" — totals are computed in Python from
// markup math that may round to 2 decimals; treat sub-cent jitter as
// no change.
const EPS = 0.005;
function approxEq(a: number, b: number): boolean {
  return Math.abs(a - b) < EPS;
}

function classifyChange(left: AggregatedLine, right: AggregatedLine): DiffChange {
  const qtyEq = approxEq(left.quantity, right.quantity);
  const costEq = approxEq(left.total_cost, right.total_cost);
  const priceEq = approxEq(left.total_price, right.total_price);

  if (qtyEq && costEq && priceEq) return "unchanged";
  if (!qtyEq && (costEq || priceEq)) return "qty_changed";
  if (qtyEq && (!costEq || !priceEq)) return "price_changed";
  return "changed";
}

// ─── Public API ────────────────────────────────────────────────────────

export function diffBoms(
  leftBom: BomResponse | null | undefined,
  rightBom: BomResponse | null | undefined,
): DiffResult {
  const left = aggregateBom(leftBom);
  const right = aggregateBom(rightBom);

  // Union of keys, deterministically ordered: changed first (drives the
  // eye to deltas), then added, removed, unchanged. Within each bucket,
  // sort by section then label.
  const allKeys = new Set<string>([...left.keys(), ...right.keys()]);
  const rows: DiffRow[] = [];

  for (const key of allKeys) {
    const l = left.get(key) ?? null;
    const r = right.get(key) ?? null;

    let change: DiffChange;
    let qtyDelta: number | null = null;
    let totalCostDelta: number | null = null;
    let totalPriceDelta: number | null = null;

    if (l && !r) {
      change = "removed";
    } else if (!l && r) {
      change = "added";
    } else if (l && r) {
      change = classifyChange(l, r);
      qtyDelta = round(r.quantity - l.quantity);
      totalCostDelta = round(r.total_cost - l.total_cost);
      totalPriceDelta = round(r.total_price - l.total_price);
    } else {
      // Should never happen — key came from the union.
      change = "unchanged";
    }

    const ref = r ?? l!;
    rows.push({
      key,
      label: ref.label,
      section: ref.section,
      source: ref.source,
      left: l,
      right: r,
      change,
      qtyDelta,
      totalCostDelta,
      totalPriceDelta,
    });
  }

  rows.sort((a, b) => {
    const order: Record<DiffChange, number> = {
      qty_changed: 0,
      price_changed: 1,
      changed: 2,
      added: 3,
      removed: 4,
      unchanged: 5,
    };
    if (order[a.change] !== order[b.change]) return order[a.change] - order[b.change];
    const sa = (a.section ?? "").toLowerCase();
    const sb = (b.section ?? "").toLowerCase();
    if (sa !== sb) return sa < sb ? -1 : 1;
    return a.label.localeCompare(b.label);
  });

  // Summary
  const leftItemCount = leftBom?.line_items?.length ?? 0;
  const rightItemCount = rightBom?.line_items?.length ?? 0;
  const leftTotalCost = leftBom?.totals?.total_cost ?? 0;
  const rightTotalCost = rightBom?.totals?.total_cost ?? 0;
  const leftTotalPrice = leftBom?.totals?.total_price ?? 0;
  const rightTotalPrice = rightBom?.totals?.total_price ?? 0;

  let added = 0, removed = 0, changed = 0, unchanged = 0;
  for (const r of rows) {
    if (r.change === "added") added++;
    else if (r.change === "removed") removed++;
    else if (r.change === "unchanged") unchanged++;
    else changed++;
  }

  const summary: DiffSummary = {
    leftItemCount,
    rightItemCount,
    itemCountDelta: rightItemCount - leftItemCount,
    leftTotalCost,
    rightTotalCost,
    totalCostDelta: round(rightTotalCost - leftTotalCost),
    leftTotalPrice,
    rightTotalPrice,
    totalPriceDelta: round(rightTotalPrice - leftTotalPrice),
    addedCount: added,
    removedCount: removed,
    changedCount: changed,
    unchangedCount: unchanged,
  };

  return { rows, summary };
}

function round(n: number): number {
  return Math.round(n * 100) / 100;
}
