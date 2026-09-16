// Mapping Browser — Day-12. Search mapped_parts.csv directly without
// having to run a BOM. Lets Richard's team verify "given generic X,
// what supplier/part does the deterministic pipeline pick?" and
// answer questions like "which generics does WSF actually cover?"
//
// Backed by GET /api/bom/mappings. Read-only; the CSV ships with the
// app. For editing the contractor-side catalog (the proprietary
// SKUItem table) see /sku-catalog.

import { useMemo, useState } from "react";
import {
  GitBranch,
  Loader2,
  RefreshCw,
  Search,
  PackagePlus,
} from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useMappingsBrowse, type MappingFilters } from "@/lib/api-hooks";


export default function MappingBrowserPage() {
  const [q,        setQ]        = useState<string>("");
  const [supplier, setSupplier] = useState<string>("");
  const [category, setCategory] = useState<string>("");

  const filters: MappingFilters = useMemo(() => ({
    q:        q.trim() || undefined,
    supplier: supplier || undefined,
    category: category || undefined,
    limit:    1000,
  }), [q, supplier, category]);

  const browse = useMappingsBrowse(filters);
  const data = browse.data;

  const resetAll = () => { setQ(""); setSupplier(""); setCategory(""); };

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <GitBranch className="w-5 h-5 text-primary" />
            Mapping Browser
          </h1>
          <p className="text-muted-foreground text-sm mt-1 max-w-3xl">
            Search Wrightsoft's bundled{" "}
            <span className="font-mono text-xs">mapped_parts.csv</span> —
            the source of truth for generic → manufacturer SKU
            translation in the deterministic pipeline. Answer "what
            does the engine pick for generic X?" and "which generics
            does supplier Y cover?" without running a full BOM.
          </p>
        </div>
        <Button
          variant="outline" size="sm"
          onClick={() => browse.refetch()}
          disabled={browse.isFetching}
        >
          {browse.isFetching
            ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
            : <RefreshCw className="w-3.5 h-3.5 mr-1.5" />}
          Refresh
        </Button>
      </div>

      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
            <div className="md:col-span-3">
              <Label className="text-xs">Search generic / SKU / description</Label>
              <div className="relative mt-1">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="e.g. PEX, DSRND, 38MARB"
                  className="h-9 pl-7"
                />
              </div>
            </div>
            <div>
              <Label className="text-xs">Supplier</Label>
              <Select value={supplier || "_any"} onValueChange={(v) => setSupplier(v === "_any" ? "" : v)}>
                <SelectTrigger className="mt-1 h-9"><SelectValue placeholder="Any" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_any">Any</SelectItem>
                  {(data?.facets.suppliers ?? []).map((s) => (
                    <SelectItem key={s} value={s}>{s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Category</Label>
              <Select value={category || "_any"} onValueChange={(v) => setCategory(v === "_any" ? "" : v)}>
                <SelectTrigger className="mt-1 h-9"><SelectValue placeholder="Any" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_any">Any</SelectItem>
                  {(data?.facets.categories ?? []).map((c) => (
                    <SelectItem key={c} value={c}>{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end gap-2">
              <Button variant="ghost" size="sm" onClick={resetAll}>Clear</Button>
            </div>
          </div>
          <div className="text-xs text-muted-foreground text-right">
            {data
              ? <>Showing <span className="font-medium text-foreground">{data.returned}</span> of {data.total.toLocaleString()} mappings</>
              : "—"}
          </div>
        </CardContent>
      </Card>

      {browse.error && (
        <Card><CardContent className="p-4 text-sm text-destructive">
          Failed to load mappings: {(browse.error as any)?.error ?? "unknown error"}
        </CardContent></Card>
      )}

      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-sm">Mappings</CardTitle>
          <CardDescription className="text-xs">
            One row per (generic, supplier, quantity variant). Multiple
            rows per generic when the part comes in different package
            sizes (e.g. PEX0750 as 100 ft / 500 ft / 1000 ft rolls).
          </CardDescription>
        </CardHeader>
        <Separator />
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b bg-muted/30 text-muted-foreground">
                <th className="text-left  px-3 py-2 font-medium">Generic</th>
                <th className="text-left  px-3 py-2 font-medium">Category</th>
                <th className="text-left  px-3 py-2 font-medium">Description</th>
                <th className="text-left  px-3 py-2 font-medium">Supplier</th>
                <th className="text-left  px-3 py-2 font-medium">Manufacturer SKU</th>
                <th className="text-right px-3 py-2 font-medium">Qty variant</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {browse.isPending && (
                <tr><td colSpan={6} className="px-3 py-8 text-center">
                  <Loader2 className="w-4 h-4 animate-spin inline mr-1 text-muted-foreground" />
                  <span className="text-muted-foreground">Loading…</span>
                </td></tr>
              )}
              {data?.items.map((it, i) => (
                <tr key={`${it.generic_id}-${it.supplier}-${it.quantity_variant}-${i}`} className="hover:bg-muted/20">
                  <td className="px-3 py-1.5 font-mono text-[11px] font-medium">{it.generic_id}</td>
                  <td className="px-3 py-1.5">
                    {it.category
                      ? <Badge variant="outline" className="text-[10px] font-mono">{it.category}</Badge>
                      : <span className="text-muted-foreground italic">—</span>}
                  </td>
                  <td className="px-3 py-1.5 max-w-[340px] truncate">{it.description ?? <span className="italic text-muted-foreground">no description</span>}</td>
                  <td className="px-3 py-1.5">
                    <Badge variant="outline" className="text-[10px] font-mono">{it.supplier}</Badge>
                  </td>
                  <td className="px-3 py-1.5 font-mono text-[11px]">
                    <PackagePlus className="w-3 h-3 inline mr-1 text-muted-foreground" />
                    {it.manufacturer_partnum}
                  </td>
                  <td className="px-3 py-1.5 text-right text-muted-foreground tabular-nums">
                    {it.quantity_variant ?? "—"}
                  </td>
                </tr>
              ))}
              {data && data.items.length === 0 && (
                <tr><td colSpan={6} className="text-center py-8 text-muted-foreground italic">
                  No mappings match the current filters.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
