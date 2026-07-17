// Reusable editor for a contractor's install-consumables list.
// Used by /pricing/consumables (full page w/ contractor picker) and
// embedded inside /profiles/<id>.
//
// Day-17 — items list is dynamic: rows can be added, removed,
// renamed, or toggled off. Each row is auto-quantified per BOM run
// from its basis (joints / flex_runs / fittings / duct_lf / per_job).

import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuItem, DropdownMenuSeparator, DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { Save, RotateCcw, Beaker, Trash2, Plus, GripVertical } from "lucide-react";
import {
  useGetContractorConsumables,
  useUpdateContractorConsumables,
  getContractorConsumablesQueryKey,
  type ContractorConsumables,
  type ConsumableItem,
  type ConsumableBasis,
} from "@/lib/api-hooks";
import { useToast } from "@/hooks/use-toast";

const SAMPLE_JOINTS = 30;
const SAMPLE_FLEX_RUNS = 5;
const SAMPLE_FITTINGS = 30;
const SAMPLE_DUCT_LF = 120;

const BASIS_LABELS: Record<ConsumableBasis, string> = {
  joints:    "per joint",
  flex_runs: "per flex run",
  fittings:  "per fitting",
  duct_lf:   "per LF of duct",
  per_job:   "flat per job",
};

const BASIS_HINT: Record<ConsumableBasis, string> = {
  joints:    "Counts every fitting that creates a sealed joint (boots, collars, end caps, etc.).",
  flex_runs: "Counts every flex-duct line item.",
  fittings:  "Counts every fitting line item.",
  duct_lf:   "Sum of linear feet across all duct line items.",
  per_job:   "Fixed quantity per job, regardless of BOM size.",
};

// Quick-pick presets — common install consumables a contractor might
// want to add without filling in every field manually.
const PRESETS: Array<{ label: string; item: Omit<ConsumableItem, "key"> }> = [
  { label: "Mastic",         item: { name: "Mastic",                description: "Brushed onto joints to seal duct connections.",     basis: "joints",    per_container: 75,  container: "gallon", unit_price: 0, enabled: true } },
  { label: "Foil tape",      item: { name: "Foil tape (UL-181A-P)", description: "Seals sheet metal and fiberglass-board seams.",     basis: "joints",    per_container: 30,  container: "roll",   unit_price: 0, enabled: true } },
  { label: "Flex tape",      item: { name: "Flex tape (UL-181B-FX)",description: "Seals flex-duct-to-collar connections.",            basis: "flex_runs", per_container: 40,  container: "roll",   unit_price: 0, enabled: true } },
  { label: "Sheet metal screws", item: { name: "Sheet metal screws",description: "For fastening collars, boots, rectangular joints.",basis: "fittings",  per_container: 150, container: "box",    unit_price: 0, enabled: true } },
  { label: "Hanger strap",   item: { name: "Hanger strap",          description: "Supports duct runs from joists.",                   basis: "duct_lf",   per_container: 50,  container: "roll",   unit_price: 0, enabled: true } },
  { label: "Insulation tape",item: { name: "Insulation tape",       description: "Seals the outer vapor barrier on flex duct.",       basis: "flex_runs", per_container: 30,  container: "roll",   unit_price: 0, enabled: true } },
  { label: "Mesh tape",      item: { name: "Foil-mesh tape",        description: "Reinforces mastic over wider gaps.",                basis: "joints",    per_container: 40,  container: "roll",   unit_price: 0, enabled: true } },
  { label: "Mastic brush",   item: { name: "Mastic brush",          description: "Disposable brush for applying mastic.",             basis: "per_job",   per_container: 1,   container: "each",   unit_price: 0, enabled: true, qty_per_job: 2 } },
];

const SYSTEM_DEFAULT_KEYS = ["mastic", "foil-tape", "flex-tape", "screws"];

function systemDefaultItems(): ConsumableItem[] {
  return [
    { key: "mastic",    name: "Mastic",                 description: "Brushed onto joints to seal duct connections.", basis: "joints",    per_container: 75,  container: "gallon", unit_price: 0, enabled: true },
    { key: "foil-tape", name: "Foil tape (UL-181A-P)",  description: "Seals sheet metal and fiberglass-board seams.", basis: "joints",    per_container: 30,  container: "roll",   unit_price: 0, enabled: true },
    { key: "flex-tape", name: "Flex tape (UL-181B-FX)", description: "Seals flex-duct-to-collar connections.",        basis: "flex_runs", per_container: 40,  container: "roll",   unit_price: 0, enabled: true },
    { key: "screws",    name: "Sheet metal screws",     description: "For fastening collars, boots, rectangular joints.", basis: "fittings", per_container: 150, container: "box", unit_price: 0, enabled: true },
  ];
}

function ceilDiv(n: number, d: number): number {
  const denom = Math.max(1, Math.floor(d || 0));
  return Math.ceil(n / denom);
}

function genKey(name: string, existing: ConsumableItem[]): string {
  const slug = (name || "item").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "item";
  let candidate = slug;
  let n = 2;
  const taken = new Set(existing.map((i) => i.key));
  while (taken.has(candidate)) candidate = `${slug}-${n++}`;
  return candidate;
}

interface Props {
  clientId: string;
  compact?: boolean;
}

export function ConsumablesEditor({ clientId, compact = false }: Props) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const consumables = useGetContractorConsumables(clientId);
  const updateMutation = useUpdateContractorConsumables();
  const [draft, setDraft] = useState<ContractorConsumables | null>(null);

  useEffect(() => {
    if (consumables.data) setDraft(consumables.data);
  }, [consumables.data, clientId]);

  const dirty = useMemo(() => {
    if (!draft || !consumables.data) return false;
    return JSON.stringify(draft) !== JSON.stringify(consumables.data);
  }, [draft, consumables.data]);

  const preview = useMemo(() => {
    if (!draft) return { rows: [], subtotal: 0 };
    const counts: Record<ConsumableBasis, number> = {
      joints:    SAMPLE_JOINTS,
      flex_runs: SAMPLE_FLEX_RUNS,
      fittings:  SAMPLE_FITTINGS,
      duct_lf:   SAMPLE_DUCT_LF,
      per_job:   0,
    };
    const rows: Array<{ name: string; qty: number; unit: string; unitPrice: number }> = [];
    for (const it of draft.items) {
      if (!it.enabled) continue;
      let qty = 0;
      if (it.basis === "per_job") {
        qty = Math.ceil(it.qty_per_job ?? 0);
      } else {
        const n = counts[it.basis];
        if (!n) continue;
        qty = ceilDiv(n, it.per_container);
      }
      if (qty <= 0) continue;
      // Day-17 — shared pluralization rule: ea → never pluralizes;
      // box → "boxes"; everything else → +s.
      const suffix = qty === 1
        ? ""
        : it.container === "ea" ? ""
        : it.container === "box" ? "es"
        : "s";
      const unit = `${it.container}${suffix}`;
      rows.push({ name: it.name, qty, unit, unitPrice: it.unit_price });
    }
    return { rows, subtotal: rows.reduce((s, r) => s + r.qty * r.unitPrice, 0) };
  }, [draft]);

  if (!draft) {
    return <Skeleton className="h-96 w-full rounded-md" />;
  }

  const setItem = (idx: number, patch: Partial<ConsumableItem>) => {
    const next = [...draft.items];
    next[idx] = { ...next[idx], ...patch };
    setDraft({ ...draft, items: next });
  };
  const removeItem = (idx: number) => {
    const next = draft.items.filter((_, i) => i !== idx);
    setDraft({ ...draft, items: next });
  };
  const addItem = (preset?: Omit<ConsumableItem, "key">) => {
    const seed: Omit<ConsumableItem, "key"> = preset ?? {
      name: "New consumable",
      description: "",
      basis: "joints",
      per_container: 50,
      container: "each",
      unit_price: 0,
      enabled: true,
    };
    const newItem: ConsumableItem = { key: genKey(seed.name, draft.items), ...seed };
    setDraft({ ...draft, items: [...draft.items, newItem] });
  };
  const resetDefaults = () => setDraft({ items: systemDefaultItems() });

  const handleSave = () => {
    if (!draft || !clientId) return;
    updateMutation.mutate(
      { id: clientId, data: draft },
      {
        onSuccess: () => {
          toast({ title: "Consumables config saved" });
          queryClient.invalidateQueries({ queryKey: getContractorConsumablesQueryKey(clientId) });
        },
        onError: (e: any) => {
          toast({ title: "Save failed", description: e?.error ?? "", variant: "destructive" });
        },
      },
    );
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-base">Consumable items</CardTitle>
              {!compact && (
                <CardDescription>
                  Each row is auto-quantified per BOM run based on its basis. Toggle off, edit,
                  remove, or add a new consumable below.
                </CardDescription>
              )}
            </div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" variant="outline"><Plus className="w-3.5 h-3.5 mr-1.5" />Add</Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64">
                <DropdownMenuLabel className="text-xs">Quick-pick presets</DropdownMenuLabel>
                {PRESETS.map((p) => (
                  <DropdownMenuItem key={p.label} onSelect={() => addItem(p.item)}>
                    {p.label}
                  </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => addItem()}>
                  <Plus className="w-3.5 h-3.5 mr-2" /> Custom consumable
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </CardHeader>
          <CardContent className="space-y-3">
            {draft.items.length === 0 && (
              <p className="text-sm text-muted-foreground italic py-6 text-center">
                No consumables for this contractor.{" "}
                <button className="underline" onClick={() => addItem(PRESETS[0].item)}>Add one</button>{" "}
                or <button className="underline" onClick={resetDefaults}>restore the defaults</button>.
              </p>
            )}
            {draft.items.map((it, idx) => (
              <ConsumableRow
                key={it.key + "-" + idx}
                item={it}
                onChange={(p) => setItem(idx, p)}
                onRemove={() => removeItem(idx)}
              />
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Beaker className="w-4 h-4 text-muted-foreground" />
              Live preview
            </CardTitle>
            <CardDescription>
              Sample install: {SAMPLE_JOINTS} joints / {SAMPLE_FLEX_RUNS} flex runs / {SAMPLE_DUCT_LF} LF duct.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {preview.rows.length === 0 ? (
              <p className="text-sm text-muted-foreground italic">All consumables disabled or empty.</p>
            ) : (
              <table className="w-full text-sm">
                <tbody>
                  {preview.rows.map((row, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-2 pr-2">{row.name}</td>
                      <td className="py-2 px-2 text-right tabular-nums font-medium">
                        {row.qty} {row.unit}
                      </td>
                      <td className="py-2 pl-2 text-right tabular-nums text-muted-foreground">
                        ${(row.qty * row.unitPrice).toFixed(2)}
                      </td>
                    </tr>
                  ))}
                  <tr className="font-semibold">
                    <td className="pt-3" colSpan={2}>Subtotal</td>
                    <td className="pt-3 pl-2 text-right tabular-nums">${preview.subtotal.toFixed(2)}</td>
                  </tr>
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="flex items-center justify-between py-3 border-t">
        <Button variant="outline" size="sm" onClick={resetDefaults} disabled={updateMutation.isPending}>
          <RotateCcw className="w-3.5 h-3.5 mr-2" />
          Reset to system defaults
        </Button>
        <div className="flex items-center gap-3">
          {dirty && <span className="text-xs text-amber-600 font-medium">Unsaved changes</span>}
          <Button onClick={handleSave} disabled={!dirty || updateMutation.isPending} size="sm" className="min-w-[140px]">
            <Save className="w-3.5 h-3.5 mr-2" />
            {updateMutation.isPending ? "Saving…" : "Save consumables"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ─── Row ─────────────────────────────────────────────────────────────

interface RowProps {
  item: ConsumableItem;
  onChange: (patch: Partial<ConsumableItem>) => void;
  onRemove: () => void;
}

function ConsumableRow({ item, onChange, onRemove }: RowProps) {
  return (
    <div className="rounded-md border p-3 space-y-3 bg-card">
      <div className="flex items-start gap-3">
        <div className="flex items-center pt-1.5">
          <Checkbox
            checked={item.enabled}
            onCheckedChange={(v) => onChange({ enabled: !!v })}
          />
        </div>
        <div className="flex-1 min-w-0 space-y-2">
          <Input
            value={item.name}
            onChange={(e) => onChange({ name: e.target.value })}
            className="font-medium h-8"
            placeholder="Item name"
          />
          <Input
            value={item.description ?? ""}
            onChange={(e) => onChange({ description: e.target.value })}
            className="h-7 text-xs"
            placeholder="Optional description"
          />
        </div>
        <button
          type="button"
          onClick={onRemove}
          className="text-muted-foreground hover:text-rose-600 transition-colors p-1"
          title="Remove this consumable"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      <div className="grid grid-cols-12 gap-2 items-end pl-7">
        <div className="col-span-4">
          <Label className="text-[10px] uppercase tracking-wide text-muted-foreground">Basis</Label>
          <Select value={item.basis} onValueChange={(v) => onChange({ basis: v as ConsumableBasis })}>
            <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              {(Object.keys(BASIS_LABELS) as ConsumableBasis[]).map((b) => (
                <SelectItem key={b} value={b} className="text-xs">
                  {BASIS_LABELS[b]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {item.basis === "per_job" ? (
          <div className="col-span-3">
            <Label className="text-[10px] uppercase tracking-wide text-muted-foreground">Qty per job</Label>
            <Input
              type="number" min={0} step={1}
              value={item.qty_per_job ?? 0}
              onChange={(e) => onChange({ qty_per_job: Number(e.target.value) || 0 })}
              className="h-8 text-xs"
            />
          </div>
        ) : (
          <div className="col-span-3">
            <Label className="text-[10px] uppercase tracking-wide text-muted-foreground">{BASIS_LABELS[item.basis]} ×N</Label>
            <Input
              type="number" min={1} step={1}
              value={item.per_container}
              onChange={(e) => onChange({ per_container: Number(e.target.value) || 0 })}
              className="h-8 text-xs"
            />
          </div>
        )}
        <div className="col-span-2">
          <Label className="text-[10px] uppercase tracking-wide text-muted-foreground">Container</Label>
          <Input
            value={item.container}
            onChange={(e) => onChange({ container: e.target.value })}
            className="h-8 text-xs"
            placeholder="gallon"
          />
        </div>
        <div className="col-span-3">
          <Label className="text-[10px] uppercase tracking-wide text-muted-foreground">$ per {item.container}</Label>
          <Input
            type="number" min={0} step={0.01}
            value={item.unit_price}
            onChange={(e) => onChange({ unit_price: Number(e.target.value) || 0 })}
            className="h-8 text-xs"
          />
        </div>
      </div>
      <p className="pl-7 text-[10px] text-muted-foreground/70 italic">{BASIS_HINT[item.basis]}</p>
    </div>
  );
}
