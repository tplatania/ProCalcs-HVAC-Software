// Bulk-import dialog for the SKU Catalog page.
//
// Designed for two flows:
//   1. Tom (or Richard) pastes a CSV from Excel / Google Sheets / a
//      vendor catalog (Goodman / Rheia / contractor-brand) — header
//      row maps to SKU schema fields, body rows become items.
//   2. Engineering pastes a JSON array directly (less common; useful
//      when migrating from another catalog).
//
// Submit POSTs to /api/sku-catalog/bulk-import (proxied to procalcs-bom
// Phase 3.6 endpoint). The endpoint is idempotent — re-importing the
// same SKUs updates rather than duplicates. Response summary is shown
// in-place; per-row errors are itemized so the user can fix and retry.
//
// Phase 3.5 schema fields are accepted in CSV: wrightsoft_codes
// (semicolon-separated inside the cell since comma is the CSV separator),
// capacity_btu, capacity_min_btu, capacity_max_btu, manufacturer,
// contractor_id.

import { useEffect, useMemo, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import {
  useBulkImportSku,
  type SkuBulkImportSummary,
  type SKUItem,
} from "@/lib/api-hooks";

interface Props {
  onClose: () => void;
  onImported: (summary: SkuBulkImportSummary) => void;
}

// Minimal RFC 4180-ish CSV parser. Handles quoted fields with embedded
// commas + double-quote-escaping. Doesn't handle multi-line values
// (acceptable for SKU rows — descriptions are one-liners).
function parseCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let i = 0;
  let inQ = false;
  while (i < line.length) {
    const c = line[i];
    if (inQ) {
      if (c === '"') {
        if (line[i + 1] === '"') {  // escaped quote
          cur += '"';
          i += 2;
          continue;
        }
        inQ = false;
        i += 1;
        continue;
      }
      cur += c;
      i += 1;
      continue;
    }
    if (c === '"') { inQ = true; i += 1; continue; }
    if (c === ",") { out.push(cur); cur = ""; i += 1; continue; }
    cur += c;
    i += 1;
  }
  out.push(cur);
  return out;
}

// Parse the whole text. Returns {headers, rows}.
function parseCsv(text: string): { headers: string[]; rows: string[][] } {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trimEnd())
    .filter((l) => l.length > 0);
  if (lines.length === 0) return { headers: [], rows: [] };
  const headers = parseCsvLine(lines[0]).map((h) => h.trim());
  const rows = lines.slice(1).map(parseCsvLine);
  return { headers, rows };
}

// Map a CSV header label to the SKU schema field. Tolerates a couple
// common label variants designers might use.
const HEADER_ALIASES: Record<string, keyof SKUItem | "quantity_mode" | "quantity_value"> = {
  // Required
  "sku":                 "sku",
  "supplier":            "supplier",
  "section":             "section",
  "description":         "description",
  "trigger":             "trigger",

  // Optional core
  "phase":               "phase",
  "default_unit_price":  "default_unit_price",
  "unit_price":          "default_unit_price",
  "price":               "default_unit_price",
  "notes":               "notes",
  "disabled":            "disabled",

  // Quantity (split into two CSV columns since CSV can't carry nested objects)
  "quantity_mode":       "quantity_mode",
  "quantity_value":      "quantity_value",

  // Phase 3.5 additions
  "wrightsoft_codes":    "wrightsoft_codes",
  "capacity_btu":        "capacity_btu",
  "capacity_min_btu":    "capacity_min_btu",
  "capacity_max_btu":    "capacity_max_btu",
  "manufacturer":        "manufacturer",
  "contractor_id":       "contractor_id",
};

function rowToItem(headers: string[], row: string[]): Partial<SKUItem> {
  const item: Record<string, unknown> = {};
  let qtyMode: string | undefined;
  let qtyValue: unknown;
  for (let i = 0; i < headers.length; i++) {
    const h = headers[i].toLowerCase().trim();
    const target = HEADER_ALIASES[h];
    const raw = (row[i] ?? "").trim();
    if (!target || raw === "") continue;

    switch (target) {
      case "wrightsoft_codes":
        // Inside a CSV cell, codes are semicolon-separated (commas
        // would collide with the CSV separator). Split + trim + drop blanks.
        item.wrightsoft_codes = raw.split(/[;,]/).map((s) => s.trim()).filter(Boolean);
        break;
      case "capacity_btu":
      case "capacity_min_btu":
      case "capacity_max_btu":
      case "default_unit_price":
        item[target] = Number(raw);
        break;
      case "disabled":
        item[target] = ["1", "true", "yes", "y"].includes(raw.toLowerCase());
        break;
      case "phase":
        item[target] = raw.toLowerCase() === "none" || raw === "" ? null : raw;
        break;
      case "quantity_mode":
        qtyMode = raw;
        break;
      case "quantity_value":
        // Numeric if it parses, else string (mode-specific extras like 'inside')
        qtyValue = Number.isFinite(Number(raw)) && raw !== "" ? Number(raw) : raw;
        break;
      default:
        item[target] = raw;
    }
  }
  if (qtyMode) {
    const q: Record<string, unknown> = { mode: qtyMode };
    if (qtyValue !== undefined) {
      // 'fixed' mode uses 'value'; 'rheia_per_lf' uses 'divisor'; etc.
      // Just stash under 'value' as the most common case — designers can
      // refine via the form UI for non-fixed modes.
      q.value = qtyValue;
    }
    item.quantity = q;
  }
  return item as Partial<SKUItem>;
}

const TEMPLATE_CSV = [
  "sku,supplier,manufacturer,section,description,trigger,quantity_mode,quantity_value,default_unit_price,capacity_btu,capacity_min_btu,capacity_max_btu,wrightsoft_codes,contractor_id",
  "GOOD-AHU-24K,GOOD,Goodman,Equipment,Goodman AHU 24K (AHVE24BP1300A),ahu_present,fixed,1,1850,24000,22000,26000,AHVE24BP1300A,",
  "GOOD-AHU-36K,GOOD,Goodman,Equipment,Goodman AHU 36K (AHVE36BP1300A),ahu_present,fixed,1,2150,36000,34000,38000,AHVE36BP1300A,",
  "GOOD-COND-24K,GOOD,Goodman,Equipment,Goodman Condenser 24K (GZV6S24),condenser_present,fixed,1,1450,24000,22000,26000,GZV6SA24,",
].join("\n");


export function SkuBulkImportDialog({ onClose, onImported }: Props) {
  const [text, setText] = useState("");
  const [parseError, setParseError] = useState<string | null>(null);
  const [summary, setSummary] = useState<SkuBulkImportSummary | null>(null);
  const importMutation = useBulkImportSku();

  // Reset summary when the user edits the text after a previous run.
  useEffect(() => { if (text) setSummary(null); }, [text]);

  const previewItems = useMemo<Partial<SKUItem>[]>(() => {
    if (!text.trim()) return [];
    setParseError(null);
    try {
      // JSON-array path first — useful for engineering pastes.
      const trimmed = text.trim();
      if (trimmed.startsWith("[")) {
        const arr = JSON.parse(trimmed);
        if (!Array.isArray(arr)) throw new Error("JSON must be an array of SKU objects");
        return arr;
      }
      // Otherwise treat as CSV.
      const { headers, rows } = parseCsv(trimmed);
      if (headers.length === 0) return [];
      return rows.map((r) => rowToItem(headers, r));
    } catch (e: any) {
      setParseError(`Couldn't parse: ${e?.message ?? String(e)}`);
      return [];
    }
  }, [text]);

  const handleImport = () => {
    setSummary(null);
    importMutation.mutate(
      { items: previewItems },
      {
        onSuccess: (s) => {
          setSummary(s);
          if (s.created > 0 || s.updated > 0) onImported(s);
        },
      }
    );
  };

  const submitting = importMutation.isPending;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Bulk import SKUs</DialogTitle>
          <DialogDescription>
            Paste a CSV (header row required) or a JSON array of SKU objects.
            Idempotent: existing SKUs with the same code are updated; new ones
            are created. Each row is validated independently — bad rows are
            itemized in the response and don't block the rest of the import.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer select-none">
              CSV format reference (click to expand)
            </summary>
            <div className="mt-2 space-y-2">
              <p>
                Required headers: <code>sku</code>, <code>supplier</code>,{" "}
                <code>section</code>, <code>description</code>, <code>trigger</code>,{" "}
                <code>quantity_mode</code>.
              </p>
              <p>
                Optional: <code>quantity_value</code>, <code>phase</code>,{" "}
                <code>default_unit_price</code>, <code>notes</code>, <code>disabled</code>,{" "}
                <code>wrightsoft_codes</code> (semicolon-separated inside cell),{" "}
                <code>capacity_btu</code>, <code>capacity_min_btu</code>,{" "}
                <code>capacity_max_btu</code>, <code>manufacturer</code>,{" "}
                <code>contractor_id</code>.
              </p>
              <Button
                variant="outline"
                size="sm"
                type="button"
                onClick={() => setText(TEMPLATE_CSV)}
              >
                Load 3-row Goodman template
              </Button>
            </div>
          </details>

          <div className="space-y-1.5">
            <Label htmlFor="bulk-text">Paste CSV or JSON</Label>
            <Textarea
              id="bulk-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="sku,supplier,manufacturer,section,description,trigger,..."
              rows={12}
              className="font-mono text-xs"
            />
          </div>

          {parseError && (
            <div className="text-sm text-destructive border border-destructive/30 bg-destructive/5 rounded p-2">
              {parseError}
            </div>
          )}

          {!parseError && text.trim() && (
            <div className="text-xs text-muted-foreground">
              Parsed {previewItems.length} row{previewItems.length === 1 ? "" : "s"}.
            </div>
          )}

          {summary && (
            <div className="border rounded p-3 space-y-2 bg-muted/30">
              <p className="text-sm font-medium">Import summary</p>
              <div className="flex gap-4 text-sm">
                <span className="text-emerald-600">Created: {summary.created}</span>
                <span className="text-blue-600">Updated: {summary.updated}</span>
                <span className="text-amber-600">Skipped: {summary.skipped}</span>
              </div>
              {summary.errors.length > 0 && (
                <details className="text-xs">
                  <summary className="cursor-pointer text-destructive">
                    {summary.errors.length} row error{summary.errors.length === 1 ? "" : "s"}
                  </summary>
                  <ul className="mt-1 space-y-0.5 pl-3 max-h-40 overflow-y-auto">
                    {summary.errors.map((e, i) => (
                      <li key={i}>
                        Row {e.index + 2}{e.sku ? ` (${e.sku})` : ""}: {e.error}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            {summary ? "Close" : "Cancel"}
          </Button>
          <Button
            onClick={handleImport}
            disabled={submitting || previewItems.length === 0 || !!parseError}
          >
            {submitting ? "Importing…" : `Import ${previewItems.length} row${previewItems.length === 1 ? "" : "s"}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
