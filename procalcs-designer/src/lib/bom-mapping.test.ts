import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  normalizeCategory,
  normalizeSource,
  mapLineItem,
  computeProvenanceCounts,
  buildCsvRows,
  serializeCsv,
  CSV_HEADER,
} from "./bom-mapping.js";
import type { BomLineItem, BomResponse } from "./api-hooks.js";

// Minimal builder so each test only declares the fields it cares about.
function makeBom(overrides: Partial<BomResponse> = {}): BomResponse {
  return {
    job_id: "test-job",
    client_id: "client-1",
    client_name: "Test Client",
    output_mode: "full",
    generated_at: "2026-04-30T00:00:00Z",
    supplier: "Test Supplier",
    line_items: [],
    totals: { total_cost: null, total_price: null },
    item_count: 0,
    ...overrides,
  };
}

function makeItem(overrides: Partial<BomLineItem> = {}): BomLineItem {
  return {
    category: "equipment",
    description: "Default item",
    quantity: 1,
    unit: "EA",
    ...overrides,
  };
}

describe("normalizeCategory", () => {
  it("recognizes the four canonical categories", () => {
    assert.equal(normalizeCategory("equipment"), "equipment");
    assert.equal(normalizeCategory("duct"), "duct");
    assert.equal(normalizeCategory("fitting"), "fitting");
    assert.equal(normalizeCategory("consumable"), "consumable");
  });

  it("folds 'register' into 'fitting' (registers live under fittings in UI)", () => {
    assert.equal(normalizeCategory("register"), "fitting");
  });

  it("is case-insensitive and trims whitespace", () => {
    assert.equal(normalizeCategory("EQUIPMENT"), "equipment");
    assert.equal(normalizeCategory("  Duct  "), "duct");
  });

  it("falls back to 'consumable' for unknown or missing categories", () => {
    assert.equal(normalizeCategory(undefined), "consumable");
    assert.equal(normalizeCategory(""), "consumable");
    assert.equal(normalizeCategory("supplies"), "consumable");
    assert.equal(normalizeCategory("Hardware"), "consumable");
  });
});

describe("normalizeSource", () => {
  it("returns 'rules' only for the explicit string", () => {
    assert.equal(normalizeSource("rules"), "rules");
  });

  it("treats absent or unknown source as 'ai' (safer default — surfaces line for review)", () => {
    assert.equal(normalizeSource(undefined), "ai");
    assert.equal(normalizeSource(""), "ai");
    assert.equal(normalizeSource("ai"), "ai");
    assert.equal(normalizeSource("manual"), "ai");
    assert.equal(normalizeSource("RULES"), "ai"); // case-sensitive on purpose
  });
});

describe("mapLineItem", () => {
  it("prefers unit_price over unit_cost; total_price over total_cost (full/proposal modes)", () => {
    const line = mapLineItem(
      makeItem({
        unit_cost: 10,
        unit_price: 12,
        total_cost: 100,
        total_price: 120,
        quantity: 10,
      }),
      0
    );
    assert.equal(line.unitCost, 12);
    assert.equal(line.total, 120);
  });

  it("falls back to unit_cost / total_cost when prices missing (cost_estimate mode)", () => {
    const line = mapLineItem(
      makeItem({ unit_cost: 7, total_cost: 21, quantity: 3 }),
      0
    );
    assert.equal(line.unitCost, 7);
    assert.equal(line.total, 21);
  });

  it("propagates SKU + source provenance from the rules engine", () => {
    const line = mapLineItem(
      makeItem({ sku: "AHU-001", source: "rules" }),
      0
    );
    assert.equal(line.sku, "AHU-001");
    assert.equal(line.source, "rules");
  });

  it("defaults source to 'ai' and sku to undefined when absent", () => {
    const line = mapLineItem(makeItem(), 0);
    assert.equal(line.source, "ai");
    assert.equal(line.sku, undefined);
  });

  it("substitutes '(unnamed)' when description missing", () => {
    const line = mapLineItem(makeItem({ description: "" }), 0);
    assert.equal(line.clientName, "(unnamed)");
    assert.equal(line.standardName, "(unnamed)");
  });

  it("generates a stable id from category + index", () => {
    const a = mapLineItem(makeItem({ category: "duct" }), 5);
    const b = mapLineItem(makeItem({ category: "register" }), 5); // register → fitting
    assert.equal(a.id, "duct-5");
    assert.equal(b.id, "fitting-5");
  });
});

describe("computeProvenanceCounts", () => {
  it("prefers backend-reported counts when present", () => {
    const counts = computeProvenanceCounts(
      makeBom({
        rules_engine_item_count: 4,
        ai_item_count: 12,
        line_items: [makeItem(), makeItem()], // mismatched on purpose — backend wins
      })
    );
    assert.equal(counts.rules, 4);
    assert.equal(counts.ai, 12);
    assert.equal(counts.hasProvenance, true);
  });

  it("derives counts from line_items.source when backend totals absent", () => {
    const counts = computeProvenanceCounts(
      makeBom({
        line_items: [
          makeItem({ source: "rules" }),
          makeItem({ source: "rules" }),
          makeItem({ source: "ai" }),
          makeItem({}), // no source → counted as AI
        ],
      })
    );
    assert.equal(counts.rules, 2);
    assert.equal(counts.ai, 2);
    assert.equal(counts.hasProvenance, true);
  });

  it("hasProvenance is false only when both counts are zero", () => {
    const empty = computeProvenanceCounts(makeBom({ line_items: [] }));
    assert.equal(empty.hasProvenance, false);
  });
});

describe("buildCsvRows + serializeCsv", () => {
  it("emits the expected 10-column header", () => {
    const rows = buildCsvRows(makeBom());
    assert.deepEqual(rows[0], Array.from(CSV_HEADER));
    assert.equal(rows[0].length, 10);
  });

  it("includes Source + SKU columns for each line item", () => {
    const bom = makeBom({
      line_items: [
        makeItem({
          category: "equipment",
          source: "rules",
          sku: "AHU-001",
          description: "Air handler 3T",
          quantity: 1,
          unit: "EA",
          unit_cost: 1000,
          unit_price: 1200,
          markup_pct: 20,
          total_price: 1200,
        }),
      ],
    });
    const rows = buildCsvRows(bom);
    // [Category, Source, SKU, Description, Qty, Unit, UnitCost, UnitPrice, Markup, Total]
    assert.deepEqual(rows[1], [
      "equipment",
      "rules",
      "AHU-001",
      "Air handler 3T",
      "1",
      "EA",
      "1000",
      "1200",
      "20",
      "1200",
    ]);
  });

  it("appends totals padded to align with the Total column", () => {
    const bom = makeBom({
      totals: { total_cost: 500, total_price: 600 },
      line_items: [makeItem({ total_price: 600 })],
    });
    const rows = buildCsvRows(bom);
    // header, line, blank, total cost, total price
    assert.equal(rows.length, 5);
    assert.deepEqual(rows[2], []);
    assert.equal(rows[3][0], "Total Cost");
    assert.equal(rows[3][9], "500");
    assert.equal(rows[4][0], "Total Price");
    assert.equal(rows[4][9], "600");
  });

  it("escapes embedded double-quotes per RFC 4180", () => {
    const bom = makeBom({
      line_items: [makeItem({ description: 'Damper 6" round' })],
    });
    const csv = serializeCsv(buildCsvRows(bom));
    // The inner quote must be doubled inside the quoted cell.
    assert.match(csv, /"Damper 6"" round"/);
  });

  it("uses CRLF line endings (Excel-friendly)", () => {
    const csv = serializeCsv([
      ["a", "b"],
      ["c", "d"],
    ]);
    assert.equal(csv, '"a","b"\r\n"c","d"');
  });
});
