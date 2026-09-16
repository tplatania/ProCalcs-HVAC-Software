// EditLineDrawer — Day-13 inline correction drawer for the Wrightsoft
// BOM result page.
//
// Click a line → drawer opens with the line's current values. Three
// editable fields by default (the Tom-aligned set): SKU, supplier,
// unit price. Notes is optional. Wrightsoft-sourced fields (qty,
// description, section) are disabled with a tooltip explaining why —
// Tom's "we use what Wrightsoft produced, we don't recreate it"
// stance means those values must not be overridden through this
// drawer.
//
// Save → upserts to contractor_overrides via useUpsertContractorOverride
// → triggers a re-render of the parent BOM list (parent re-fetches
// or applies the override locally; this component is purely the form).

import { useEffect, useMemo, useState } from "react";
import { Loader2, ShieldCheck, Trash2 } from "lucide-react";

import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetFooter,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  useUpsertContractorOverride,
  useDeleteContractorOverride,
  type ContractorOverride,
} from "@/lib/api-hooks";

// Wrightsoft-sourced lines have a 4-char supplier code (Src) in the
// `manufacturer` field and the part identifier (Name) in `sku`. We
// key the override on those two strings + the contractor_id.
export interface EditableLine {
  // Identity for the override
  manufacturer: string | null;   // Wrightsoft Src
  sku:          string | null;   // Wrightsoft Name (== generic_id on passthrough)
  // Display-only fields (Wrightsoft-sourced, not editable)
  description:  string | null;
  quantity:     number | null;
  unit:         string | null;
  section:      string | null;
  // Current pricing (so the form pre-fills with the active values)
  unit_cost:    number | null;
  // Source tag — used to decide if a Wrightsoft line is being edited
  // (locks the qty/description fields) vs an AI line (would unlock
  // them in a future iteration).
  source:       string | null;
  // Existing override audit fields if the line already has one
  override_id?:         number | null;
  override_updated_by?: string | null;
  override_updated_at?: string | null;
}


export function EditLineDrawer({
  open,
  onOpenChange,
  clientId,
  line,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  clientId: string;
  line: EditableLine | null;
  onSaved: (saved: ContractorOverride) => void;
}) {
  const upsert = useUpsertContractorOverride();
  const remove = useDeleteContractorOverride();

  const [correctedSku,      setCorrectedSku]      = useState<string>("");
  const [correctedSupplier, setCorrectedSupplier] = useState<string>("");
  const [unitPrice,         setUnitPrice]         = useState<string>("");
  const [notes,             setNotes]             = useState<string>("");
  const [error,             setError]             = useState<string | null>(null);

  // Pre-fill the form when the drawer opens on a new line. We treat
  // an empty "corrected SKU/supplier" as 'no change'; the unit price
  // pre-fills with the current cost so the user can adjust from
  // there rather than re-typing from zero.
  useEffect(() => {
    if (!open || !line) return;
    setCorrectedSku("");
    setCorrectedSupplier("");
    setUnitPrice(line.unit_cost != null ? String(line.unit_cost) : "");
    setNotes("");
    setError(null);
  }, [open, line?.sku, line?.manufacturer]); // eslint-disable-line react-hooks/exhaustive-deps

  const isWrightsoftSourced = useMemo(() => {
    const s = line?.source ?? "";
    return s.startsWith("wrightsoft_");
  }, [line?.source]);

  // Effective key for the override = original line value OR the
  // user-typed correction when the line has none (AI-pipeline case
  // where the AI emitted no supplier/sku — the user is filling them
  // in for the first time, which IS the catalog-building moment).
  const effectiveSupplier = (line?.manufacturer || correctedSupplier).trim();
  const effectiveSku      = (line?.sku          || correctedSku).trim();

  const canSave = useMemo(() => {
    if (!clientId) return false;
    if (!effectiveSupplier || !effectiveSku) return false;
    // At least one of corrected_sku / corrected_supplier / unit_price
    // must be touched — otherwise the save is a no-op. For AI lines
    // where the user is filling in supplier/sku for the first time,
    // the typed values count as "touched".
    const priceTouched =
      unitPrice.trim() !== "" &&
      String(line?.unit_cost ?? "") !== unitPrice.trim();
    return (
      correctedSku.trim() !== "" ||
      correctedSupplier.trim() !== "" ||
      priceTouched
    );
  }, [clientId, effectiveSupplier, effectiveSku, correctedSku,
      correctedSupplier, unitPrice, line?.unit_cost]);

  const onSave = () => {
    if (!effectiveSupplier || !effectiveSku) return;
    setError(null);
    upsert.mutate({
      client_id: clientId,
      supplier:  effectiveSupplier,
      sku:       effectiveSku,
      // Pass undefined for untouched fields so the backend leaves
      // existing values alone (None-means-leave-alone contract on
      // the upsert helper).
      corrected_sku:      correctedSku.trim()      || undefined,
      corrected_supplier: correctedSupplier.trim() || undefined,
      unit_price: unitPrice.trim() === "" ? undefined : Number(unitPrice),
      notes:      notes.trim() || undefined,
    }, {
      onSuccess: (saved) => {
        onSaved(saved);
        onOpenChange(false);
      },
      onError: (err) => setError(err?.error ?? "Save failed"),
    });
  };

  const onRemoveOverride = () => {
    if (!line?.override_id) return;
    if (!confirm("Remove this contractor override? Future BOMs for this contractor will revert to the catalog/Wrightsoft value.")) return;
    remove.mutate({ id: line.override_id, client_id: clientId }, {
      onSuccess: () => {
        onSaved({} as ContractorOverride);  // signal refresh
        onOpenChange(false);
      },
      onError: (err) => setError(err?.error ?? "Delete failed"),
    });
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[420px] sm:max-w-[420px] flex flex-col">
        <SheetHeader>
          <SheetTitle className="text-base flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            Edit line
          </SheetTitle>
          <SheetDescription className="text-xs">
            Correct the SKU translation or enter the contractor's price
            for this part. Saves apply to every future BOM for{" "}
            <span className="font-medium text-foreground">{clientId}</span>.
          </SheetDescription>
        </SheetHeader>

        {line && (
          <div className="flex-1 overflow-y-auto py-4 space-y-4 text-sm">
            {/* Identity (read-only) */}
            <div className="bg-muted/30 border rounded-md p-3 space-y-1.5">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-semibold">
                {isWrightsoftSourced ? "Wrightsoft says" : "Current values"}
              </div>
              <Row label="Supplier" value={line.manufacturer ?? "—"} mono />
              <Row label="Part #"   value={line.sku ?? "—"}          mono />
              <Row label="Description" value={line.description ?? "—"} />
              <Row label="Qty"      value={`${line.quantity ?? "—"} ${line.unit ?? ""}`} />
              <Row label="Section"  value={line.section ?? "—"} />
            </div>

            {/* Editable corrections. When the line came in with a
                null sku/supplier (typical for AI-pipeline lines that
                couldn't be verified), the corresponding field becomes
                required — the user is filling it in for the first
                time, which IS the catalog-building moment. */}
            <div className="space-y-3">
              <div>
                <Label className="text-xs">
                  {line.sku ? "Corrected SKU" : "SKU"}
                  <span className="text-muted-foreground font-normal ml-1">
                    {line.sku ? "(optional)" : "(required)"}
                  </span>
                </Label>
                <Input
                  value={correctedSku}
                  onChange={(e) => setCorrectedSku(e.target.value)}
                  placeholder={line.sku ?? "e.g. AHVE24BP1300A"}
                  className="mt-1 h-9 font-mono text-xs"
                  disabled={upsert.isPending}
                />
                <p className="text-[10px] text-muted-foreground mt-1">
                  {line.sku
                    ? `Leave blank if "${line.sku}" is right.`
                    : "AI didn't emit a SKU. Fill in the real part number to teach the catalog."}
                </p>
              </div>

              <div>
                <Label className="text-xs">
                  {line.manufacturer ? "Corrected supplier" : "Supplier"}
                  <span className="text-muted-foreground font-normal ml-1">
                    {line.manufacturer ? "(optional)" : "(required)"}
                  </span>
                </Label>
                <Input
                  value={correctedSupplier}
                  onChange={(e) => setCorrectedSupplier(e.target.value.toUpperCase())}
                  placeholder={line.manufacturer ?? "e.g. GOOD"}
                  className="mt-1 h-9 font-mono text-xs"
                  maxLength={16}
                  disabled={upsert.isPending}
                />
              </div>

              <div>
                <Label className="text-xs">Unit cost
                  <span className="text-muted-foreground font-normal ml-1">(what {clientId} pays)</span>
                </Label>
                <div className="relative mt-1">
                  <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
                  <Input
                    type="number"
                    inputMode="decimal"
                    step="0.01"
                    min="0"
                    value={unitPrice}
                    onChange={(e) => setUnitPrice(e.target.value)}
                    className="h-9 pl-6"
                    disabled={upsert.isPending}
                  />
                </div>
                <p className="text-[10px] text-muted-foreground mt-1">
                  Profile markup is applied automatically to derive the customer price.
                </p>
              </div>

              <div>
                <Label className="text-xs">Notes
                  <span className="text-muted-foreground font-normal ml-1">(optional)</span>
                </Label>
                <Textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="e.g. confirmed price with Goodman rep 5/27"
                  className="mt-1 text-xs min-h-[60px]"
                  disabled={upsert.isPending}
                />
              </div>
            </div>

            {/* Tom-aligned guardrail */}
            {isWrightsoftSourced && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <p className="text-[10px] text-muted-foreground italic cursor-help border-t pt-2">
                    Why are qty and description locked?
                  </p>
                </TooltipTrigger>
                <TooltipContent side="top" className="max-w-[260px] text-xs">
                  Wrightsoft computes these from the drawn project.
                  Per Tom's direction we use those values as-is —
                  to change them, edit the project in Wrightsoft
                  and re-export the BOM.
                </TooltipContent>
              </Tooltip>
            )}

            {line.override_id && (
              <div className="border-t pt-3">
                <p className="text-[10px] text-muted-foreground mb-1.5">
                  Existing override · last updated{" "}
                  {line.override_updated_at?.slice(0, 10) ?? "—"}
                  {line.override_updated_by ? ` by ${line.override_updated_by}` : ""}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-xs text-destructive border-destructive/30 hover:bg-destructive/10"
                  onClick={onRemoveOverride}
                  disabled={remove.isPending}
                >
                  {remove.isPending
                    ? <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                    : <Trash2 className="w-3 h-3 mr-1" />}
                  Remove override
                </Button>
              </div>
            )}

            {error && (
              <p className="text-xs text-destructive">{error}</p>
            )}
          </div>
        )}

        <SheetFooter className="border-t pt-3">
          <Button variant="ghost" size="sm"
                  onClick={() => onOpenChange(false)}
                  disabled={upsert.isPending}>
            Cancel
          </Button>
          <Button size="sm" onClick={onSave}
                  disabled={!canSave || upsert.isPending}>
            {upsert.isPending
              ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              : null}
            Save correction
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}


function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline gap-2 text-xs">
      <span className="w-[80px] text-muted-foreground shrink-0">{label}</span>
      <span className={mono ? "font-mono text-[11px]" : ""}>{value}</span>
    </div>
  );
}
