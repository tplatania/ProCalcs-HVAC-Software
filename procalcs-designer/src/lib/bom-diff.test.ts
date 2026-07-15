import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { aggregateBom, diffBoms } from "./bom-diff.js";
import type { BomLineItem, BomResponse } from "./api-hooks.js";

function makeBom(items: Partial<BomLineItem>[], totals?: Partial<BomResponse["totals"]>): BomResponse {
  const line_items = items.map((p): BomLineItem => ({
    category: "equipment",
    description: "x",
    quantity: 1,
    unit: "EA",
    ...p,
  }));
  // Auto-derive totals from items if not provided — keeps test fixtures terse.
  const total_cost = totals?.total_cost ?? line_items.reduce((s, li) => s + (li.total_cost ?? 0), 0);
  const total_price = totals?.total_price ?? line_items.reduce((s, li) => s + (li.total_price ?? 0), 0);
  return {
    job_id: "t",
    client_id: "c",
    client_name: "C",
    output_mode: "full",
    generated_at: "2026-05-15T00:00:00Z",
    supplier: "S",
    line_items,
    totals: { total_cost, total_price },
    item_count: line_items.length,
  };
}

// ─── aggregateBom ────────────────────────────────────────────────────

describe("aggregateBom", () => {
  it("returns empty map for null input", () => {
    assert.equal(aggregateBom(null).size, 0);
    assert.equal(aggregateBom(undefined).size, 0);
  });

  it("keys lines by sku when present (case-insensitive)", () => {
    const m = aggregateBom(makeBom([
      { sku: "AHU-24K", description: "Air handler 2T", quantity: 1, total_cost: 100 },
      { sku: "ahu-24k", description: "Air handler again", quantity: 2, total_cost: 200 },
    ]));
    // Same SKU different case → coalesced
    assert.equal(m.size, 1);
    const row = [...m.values()][0];
    assert.equal(row.quantity, 3);
    assert.equal(row.total_cost, 300);
    assert.equal(row.originals.length, 2);
  });

  it("falls back to description+section+source when sku missing", () => {
    const m = aggregateBom(makeBom([
      { description: "Hanger straps", section: "Duct", source: "rules", quantity: 5, total_cost: 100 },
      { description: "Hanger straps", section: "Duct", source: "rules", quantity: 3, total_cost: 60 },
      { description: "Hanger straps", section: "Equipment", source: "rules", quantity: 1, total_cost: 20 }, // diff section
    ]));
    assert.equal(m.size, 2);
  });
});

// ─── diffBoms — adds/removes/unchanged ───────────────────────────────

describe("diffBoms", () => {
  it("flags added rows when right has a SKU left doesn't", () => {
    const left = makeBom([{ sku: "A", quantity: 1, total_cost: 10, total_price: 13 }]);
    const right = makeBom([
      { sku: "A", quantity: 1, total_cost: 10, total_price: 13 },
      { sku: "B", quantity: 2, total_cost: 50, total_price: 65 },
    ]);
    const { rows, summary } = diffBoms(left, right);
    const added = rows.filter(r => r.change === "added");
    assert.equal(added.length, 1);
    assert.equal(added[0].label, "B");
    assert.equal(summary.addedCount, 1);
    assert.equal(summary.removedCount, 0);
    assert.equal(summary.itemCountDelta, 1);
  });

  it("flags removed rows when left has a SKU right doesn't", () => {
    const left = makeBom([
      { sku: "A", quantity: 1, total_cost: 10, total_price: 13 },
      { sku: "B", quantity: 2, total_cost: 50, total_price: 65 },
    ]);
    const right = makeBom([{ sku: "A", quantity: 1, total_cost: 10, total_price: 13 }]);
    const { rows, summary } = diffBoms(left, right);
    assert.equal(summary.removedCount, 1);
    assert.equal(rows.find(r => r.label === "B")?.change, "removed");
  });

  it("treats sub-cent jitter as unchanged", () => {
    const left = makeBom([{ sku: "A", quantity: 1, total_cost: 10.001, total_price: 13.0049 }]);
    const right = makeBom([{ sku: "A", quantity: 1, total_cost: 10.0049, total_price: 13.0001 }]);
    const { summary } = diffBoms(left, right);
    assert.equal(summary.unchangedCount, 1);
    assert.equal(summary.changedCount, 0);
  });

  it("classifies qty_changed when only quantity differs", () => {
    const left = makeBom([{ sku: "A", quantity: 1, total_cost: 10, total_price: 13 }]);
    const right = makeBom([{ sku: "A", quantity: 2, total_cost: 10, total_price: 13 }]);
    const r = diffBoms(left, right).rows[0];
    assert.equal(r.change, "qty_changed");
    assert.equal(r.qtyDelta, 1);
  });

  it("classifies price_changed when only money differs", () => {
    const left = makeBom([{ sku: "A", quantity: 1, total_cost: 10, total_price: 13 }]);
    const right = makeBom([{ sku: "A", quantity: 1, total_cost: 12, total_price: 16 }]);
    const r = diffBoms(left, right).rows[0];
    assert.equal(r.change, "price_changed");
    assert.equal(r.totalCostDelta, 2);
    assert.equal(r.totalPriceDelta, 3);
  });

  it("classifies generic 'changed' when both qty and money drift", () => {
    const left = makeBom([{ sku: "A", quantity: 1, total_cost: 10, total_price: 13 }]);
    const right = makeBom([{ sku: "A", quantity: 2, total_cost: 25, total_price: 33 }]);
    assert.equal(diffBoms(left, right).rows[0].change, "changed");
  });

  it("orders changed first, then added, removed, unchanged", () => {
    const left = makeBom([
      { sku: "UNCH", quantity: 1, total_cost: 1, total_price: 1 },
      { sku: "QTY",  quantity: 1, total_cost: 5, total_price: 5 },
      { sku: "GONE", quantity: 1, total_cost: 9, total_price: 9 },
    ]);
    const right = makeBom([
      { sku: "UNCH", quantity: 1, total_cost: 1, total_price: 1 },
      { sku: "QTY",  quantity: 3, total_cost: 5, total_price: 5 }, // qty changed
      { sku: "NEW",  quantity: 2, total_cost: 4, total_price: 4 }, // added
    ]);
    const order = diffBoms(left, right).rows.map(r => r.change);
    assert.deepEqual(order, ["qty_changed", "added", "removed", "unchanged"]);
  });

  it("returns sane summary when one side is null", () => {
    const right = makeBom([{ sku: "A", quantity: 1, total_cost: 10, total_price: 13 }]);
    const { summary } = diffBoms(null, right);
    assert.equal(summary.addedCount, 1);
    assert.equal(summary.leftItemCount, 0);
    assert.equal(summary.rightItemCount, 1);
    assert.equal(summary.totalCostDelta, 10);
    assert.equal(summary.totalPriceDelta, 13);
  });

  it("uses provided totals over auto-summed ones", () => {
    // Stress test: line items don't carry totals but BOM-level totals do.
    // Many real BOMs zero out per-line cost when output_mode hides money.
    const left: BomResponse = {
      ...makeBom([{ sku: "A", quantity: 1 }]),
      totals: { total_cost: 100, total_price: 130 },
    };
    const right: BomResponse = {
      ...makeBom([{ sku: "A", quantity: 1 }]),
      totals: { total_cost: 110, total_price: 143 },
    };
    const { summary } = diffBoms(left, right);
    assert.equal(summary.totalCostDelta, 10);
    assert.equal(summary.totalPriceDelta, 13);
  });
});
