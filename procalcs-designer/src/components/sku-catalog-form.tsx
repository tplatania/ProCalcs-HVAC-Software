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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import {
  useGetSkuCatalogMeta,
  useCreateSku,
  useUpdateSku,
  type SKUItem,
} from "@/lib/api-hooks";

type SaveKind = "created" | "updated";

interface Props {
  mode: "create" | "edit";
  initial?: SKUItem;
  onClose: () => void;
  onSaved: (item: SKUItem, kind: SaveKind) => void;
}

const PHASE_NULL = "__none__";

// Quantity-mode → which extra fields the form should expose.
// Anything beyond `mode` lives under `quantity` as free key/value pairs.
const QTY_MODE_FIELDS: Record<string, Array<{ key: string; label: string; placeholder?: string; numeric?: boolean }>> = {
  fixed:               [{ key: "value",   label: "Value",   numeric: true }],
  per_unit:            [{ key: "source",  label: "Source",  placeholder: "equipment.ahu" }],
  per_lf:              [{ key: "source",  label: "Source",  placeholder: "duct_runs.rectangular" }],
  per_register:        [{ key: "source",  label: "Source",  placeholder: "registers.ceiling_round" }],
  rheia_per_lf:        [{ key: "divisor", label: "Divisor (1 per N LF; blank = total LF)", numeric: true }],
  rheia_per_takeoff:   [{ key: "side",    label: "Side",    placeholder: "inside | outside" }],
  rheia_per_endpoint:  [{ key: "endpoint", label: "Endpoint", placeholder: "high_sidewall | ceiling" }],
  fitting_count:       [{ key: "source",  label: "Source",  placeholder: "fittings.elbow" }],
};

function blankItem(): Partial<SKUItem> {
  return {
    sku: "",
    supplier: "",
    section: "",
    phase: null,
    description: "",
    trigger: "always",
    quantity: { mode: "fixed", value: 1 },
    default_unit_price: 0,
    notes: "",
    disabled: false,
    // Phase 3.5 additions — all optional, default to empty/null so the
    // form's basic shape stays unchanged when designers ignore them.
    wrightsoft_codes: [],
    capacity_btu: null,
    capacity_min_btu: null,
    capacity_max_btu: null,
    manufacturer: null,
    contractor_id: null,
  };
}

// Comma-separated string ↔ string[]. Used by the Wrightsoft codes input
// because the schema field is a list but the form field is one text box.
// Trims, drops blanks. Empty input → empty array (not [""]).
function parseCsvList(s: string): string[] {
  return s.split(",").map((v) => v.trim()).filter(Boolean);
}

// Coerce optional numeric form input to int | null. "" → null,
// non-numeric → null, otherwise parsed int. Mirrors backend's
// _coerce_int_or_none.
function parseOptionalInt(v: unknown): number | null {
  if (v === "" || v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.round(n) : null;
}

export function SkuCatalogForm({ mode, initial, onClose, onSaved }: Props) {
  const { data: meta } = useGetSkuCatalogMeta();
  const createMutation = useCreateSku();
  const updateMutation = useUpdateSku();

  const [draft, setDraft] = useState<Partial<SKUItem>>(() =>
    initial ? { ...initial } : blankItem()
  );
  const [serverError, setServerError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(initial ? { ...initial } : blankItem());
    setServerError(null);
  }, [initial]);

  const set = <K extends keyof SKUItem>(key: K, value: SKUItem[K] | undefined) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const setQty = (patch: Record<string, unknown>) =>
    setDraft((d) => ({ ...d, quantity: { ...(d.quantity as any), ...patch } }));

  const qtyMode = (draft.quantity as any)?.mode ?? "fixed";
  const qtyExtraFields = QTY_MODE_FIELDS[qtyMode] ?? [];

  const submitting = createMutation.isPending || updateMutation.isPending;

  const valid = useMemo(() => {
    return !!(
      (mode === "edit" || draft.sku?.trim()) &&
      draft.supplier?.trim() &&
      draft.section?.trim() &&
      draft.description?.trim() &&
      draft.trigger?.trim() &&
      qtyMode
    );
  }, [draft, mode, qtyMode]);

  const handleSubmit = () => {
    setServerError(null);

    // Strip __none__ sentinel back to null on the way out.
    const phase =
      draft.phase === undefined || draft.phase === PHASE_NULL ? null : draft.phase;

    const payload: Partial<SKUItem> = {
      ...draft,
      phase,
      default_unit_price: Number(draft.default_unit_price ?? 0) || 0,
      // Phase 3.5 — coerce optional numerics + normalize the codes list.
      wrightsoft_codes: draft.wrightsoft_codes ?? [],
      capacity_btu:     parseOptionalInt(draft.capacity_btu),
      capacity_min_btu: parseOptionalInt(draft.capacity_min_btu),
      capacity_max_btu: parseOptionalInt(draft.capacity_max_btu),
      manufacturer:    (draft.manufacturer ?? "").trim() || null,
      contractor_id:   (draft.contractor_id ?? "").trim() || null,
    };

    const onError = (err: any) =>
      setServerError(err?.error || "Save failed. Check the form and try again.");

    if (mode === "create") {
      createMutation.mutate(payload, {
        onSuccess: (item) => onSaved(item, "created"),
        onError,
      });
    } else {
      const sku = initial?.sku ?? draft.sku ?? "";
      updateMutation.mutate(
        { sku, data: payload },
        {
          onSuccess: (item) => onSaved(item, "updated"),
          onError,
        }
      );
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {mode === "create" ? "New SKU" : `Edit ${initial?.sku ?? ""}`}
          </DialogTitle>
          <DialogDescription>
            All fields except <em>Notes</em> are required. Quantity rule controls
            how the rules engine emits this SKU during BOM generation.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="sku">SKU</Label>
            <Input
              id="sku"
              value={draft.sku ?? ""}
              onChange={(e) => set("sku", e.target.value)}
              placeholder="e.g. AHVE24BP1300A or 10-01-010"
              disabled={mode === "edit"}
              autoFocus={mode === "create"}
            />
            {mode === "edit" && (
              <p className="text-[11px] text-muted-foreground">
                SKU is the document key; rename by deleting and re-creating.
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="supplier">Supplier</Label>
            <Input
              id="supplier"
              list="sku-supplier-options"
              value={draft.supplier ?? ""}
              onChange={(e) => set("supplier", e.target.value)}
              placeholder="GOODMAN, PGM, WSF, PRJ, RHEA…"
            />
            <datalist id="sku-supplier-options">
              {(meta?.suppliers_seen ?? []).map((s) => <option key={s} value={s} />)}
            </datalist>
          </div>

          <div className="space-y-1.5">
            <Label>Section</Label>
            <Select
              value={draft.section ?? ""}
              onValueChange={(v) => set("section", v)}
            >
              <SelectTrigger><SelectValue placeholder="Pick a section…" /></SelectTrigger>
              <SelectContent>
                {(meta?.sections ?? []).map((s) => (
                  <SelectItem key={s} value={s}>{s}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label>Phase</Label>
            <Select
              value={draft.phase ?? PHASE_NULL}
              onValueChange={(v) => set("phase", (v === PHASE_NULL ? null : v) as any)}
            >
              <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
              <SelectContent>
                <SelectItem value={PHASE_NULL}>None</SelectItem>
                {(meta?.phases ?? []).map((p) => (
                  <SelectItem key={p} value={p}>{p}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5 md:col-span-2">
            <Label htmlFor="description">Description</Label>
            <Input
              id="description"
              value={draft.description ?? ""}
              onChange={(e) => set("description", e.target.value)}
              placeholder='e.g. Rectangular fiberglass duct, 17" x 12", medium'
            />
          </div>

          <div className="space-y-1.5">
            <Label>Trigger</Label>
            <Select
              value={draft.trigger ?? ""}
              onValueChange={(v) => set("trigger", v)}
            >
              <SelectTrigger><SelectValue placeholder="When to emit…" /></SelectTrigger>
              <SelectContent>
                {(meta?.triggers ?? []).map((t) => (
                  <SelectItem key={t} value={t}>{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="default-price">Default unit price (USD)</Label>
            <Input
              id="default-price"
              type="number"
              step="0.01"
              value={draft.default_unit_price ?? 0}
              onChange={(e) => set("default_unit_price", Number(e.target.value) as any)}
            />
            <p className="text-[11px] text-muted-foreground">
              0 means "use contractor profile or supplier API at generation time".
            </p>
          </div>

          {/* Quantity rule — mode + dynamic extras */}
          <div className="md:col-span-2 border rounded-md p-4 bg-muted/30 space-y-3">
            <Label>Quantity rule</Label>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="qty-mode" className="text-xs uppercase tracking-wide text-muted-foreground">Mode</Label>
                <Select
                  value={qtyMode}
                  onValueChange={(v) => setDraft((d) => ({ ...d, quantity: { mode: v } as any }))}
                >
                  <SelectTrigger id="qty-mode"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {(meta?.quantity_modes ?? Object.keys(QTY_MODE_FIELDS)).map((m) => (
                      <SelectItem key={m} value={m}>{m}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {qtyExtraFields.map((f) => (
                <div className="space-y-1.5" key={f.key}>
                  <Label htmlFor={`qty-${f.key}`} className="text-xs uppercase tracking-wide text-muted-foreground">
                    {f.label}
                  </Label>
                  <Input
                    id={`qty-${f.key}`}
                    type={f.numeric ? "number" : "text"}
                    placeholder={f.placeholder}
                    value={(draft.quantity as any)?.[f.key] ?? ""}
                    onChange={(e) =>
                      setQty({
                        [f.key]: f.numeric
                          ? (e.target.value === "" ? undefined : Number(e.target.value))
                          : e.target.value,
                      })
                    }
                  />
                </div>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">
              Mode <code>fixed</code> emits a constant quantity. Other modes count items
              from <code>design_data</code> (per LF, per register, per take-off…). Rheia
              modes only fire when <code>rheia_in_scope</code> is detected.
            </p>
          </div>

          <div className="md:col-span-2 space-y-1.5">
            <Label htmlFor="notes">Notes (internal)</Label>
            <Textarea
              id="notes"
              value={draft.notes ?? ""}
              onChange={(e) => set("notes", e.target.value)}
              placeholder="Tonnage caveats, sample-BOM anchors, refinement TODOs…"
              rows={3}
            />
          </div>

          {/* Phase 3.5 (May 2026) — Advanced fields for catalog-augmented
              BOM generation. Collapsed by default so designers writing
              simple SKUs aren't overwhelmed; expands when they need
              tonnage matching, contractor scoping, or Wrightsoft code
              bridging. See _repo-docs/SAAS_BILLING_DESIGN.md sibling
              notes + procalcs-bom services/sku_catalog.py SKUItem. */}
          <details className="md:col-span-2 border rounded-md bg-muted/20 group">
            <summary className="cursor-pointer select-none px-4 py-2.5 text-sm font-medium hover:bg-muted/40">
              Advanced — manufacturer, capacity sizing, contractor scope, Wrightsoft codes
              <span className="text-[11px] text-muted-foreground ml-2">
                (optional · enables per-equipment catalog matching)
              </span>
            </summary>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-4 pt-2 border-t">

              <div className="space-y-1.5">
                <Label htmlFor="manufacturer">Manufacturer (display name)</Label>
                <Input
                  id="manufacturer"
                  value={draft.manufacturer ?? ""}
                  onChange={(e) => set("manufacturer", (e.target.value || null) as any)}
                  placeholder="Goodman, Rheia, PGM, Carrier…"
                />
                <p className="text-[11px] text-muted-foreground">
                  Full name shown in the BOM. Separate from <code>Supplier</code>
                  (the 4-char Wrightsoft source code).
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="contractor-id">Contractor scope</Label>
                <Input
                  id="contractor-id"
                  value={draft.contractor_id ?? ""}
                  onChange={(e) => set("contractor_id", (e.target.value || null) as any)}
                  placeholder="(blank = global, e.g. beazer-homes-az)"
                />
                <p className="text-[11px] text-muted-foreground">
                  When set, this SKU only matches BOMs for that contractor.
                  Global SKUs (blank) are the default fallback.
                </p>
              </div>

              <div className="space-y-1.5 md:col-span-2">
                <Label htmlFor="wrightsoft-codes">Wrightsoft generic codes</Label>
                <Input
                  id="wrightsoft-codes"
                  value={(draft.wrightsoft_codes ?? []).join(", ")}
                  onChange={(e) =>
                    set("wrightsoft_codes", parseCsvList(e.target.value) as any)
                  }
                  placeholder="comma-separated, e.g. AHVE24BP1300A, AHVE30BP1300A"
                />
                <p className="text-[11px] text-muted-foreground">
                  Bridge to <code>generic_parts.csv</code>. One catalog SKU can cover
                  multiple Wrightsoft generics (e.g. one Goodman AHU SKU covering
                  AHU-24K, AHU-30K variants).
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="capacity-btu">Capacity (BTU/hr nominal)</Label>
                <Input
                  id="capacity-btu"
                  type="number"
                  step="100"
                  value={draft.capacity_btu ?? ""}
                  onChange={(e) =>
                    set("capacity_btu", parseOptionalInt(e.target.value) as any)
                  }
                  placeholder="24000"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                  Tolerance band (BTU/hr)
                </Label>
                <div className="flex gap-2 items-center">
                  <Input
                    type="number"
                    step="100"
                    value={draft.capacity_min_btu ?? ""}
                    onChange={(e) =>
                      set("capacity_min_btu", parseOptionalInt(e.target.value) as any)
                    }
                    placeholder="min"
                    aria-label="capacity min BTU"
                  />
                  <span className="text-xs text-muted-foreground">–</span>
                  <Input
                    type="number"
                    step="100"
                    value={draft.capacity_max_btu ?? ""}
                    onChange={(e) =>
                      set("capacity_max_btu", parseOptionalInt(e.target.value) as any)
                    }
                    placeholder="max"
                    aria-label="capacity max BTU"
                  />
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Equipment within this band matches this SKU when nominal isn't exact.
                  Both ends required, or both blank.
                </p>
              </div>

            </div>
          </details>

          <div className="md:col-span-2 flex items-center gap-2">
            <Checkbox
              id="disabled"
              checked={!!draft.disabled}
              onCheckedChange={(v) => set("disabled", v as any)}
            />
            <Label htmlFor="disabled" className="cursor-pointer">
              Disabled — keep in catalog for history but hide from rules engine + designer
            </Label>
          </div>
        </div>

        {serverError && (
          <div className="text-sm text-destructive border border-destructive/30 bg-destructive/5 rounded p-2">
            {serverError}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={!valid || submitting}>
            {submitting ? "Saving…" : mode === "create" ? "Create" : "Save changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
