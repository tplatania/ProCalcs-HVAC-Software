// DFUnit Explorer — Day-12. Browse Tom's bundled DFUnit.csv (963
// ductless / mini-split / heat-pump equipment rows) without leaving
// the SPA. Filter by manufacturer / sys-type / unit-type / capacity
// range / free-text. Lets designers confirm a Wrightsoft equipment
// pick has a matching catalog row before running the deterministic
// pipeline.
//
// Backed by GET /api/bom/dfunit. Read-only — the catalog ships with
// the app, not user-editable.

import { useMemo, useState } from "react";
import {
  Cpu,
  Loader2,
  RefreshCw,
  Search,
  Snowflake,
  Flame,
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
import { useDfunitBrowse, type DFUnitFilters } from "@/lib/api-hooks";
import { cn } from "@/lib/utils";

const UNIT_TYPE_LABEL: Record<string, string> = {
  OS: "Outdoor Split",
  IW: "Indoor Wall",
  IC: "Indoor Ceiling",
  OM: "Outdoor Multi",
  ID: "Indoor Duct",
  IA: "Indoor (A)",
  IF: "Indoor (F)",
  IU: "Indoor (U)",
};

const SYS_TYPE_LABEL: Record<string, string> = {
  H: "Heat Pump",
  A: "AC Only",
};

const MFR_LABEL: Record<string, string> = {
  CARR: "Carrier",
  MITS: "Mitsubishi",
  DAIK: "Daikin",
  FUJI: "Fujitsu",
  GREE: "Gree",
  LGEL: "LG",
  MRCL: "Miracool",
  WSF:  "Wrightsoft",
};


export default function DFUnitExplorerPage() {
  const [manufacturer, setManufacturer] = useState<string>("");
  const [sysType,      setSysType]      = useState<string>("");
  const [unitType,     setUnitType]     = useState<string>("");
  const [q,            setQ]            = useState<string>("");
  const [minClg,       setMinClg]       = useState<string>("");
  const [maxClg,       setMaxClg]       = useState<string>("");

  const filters: DFUnitFilters = useMemo(() => ({
    manufacturer: manufacturer || undefined,
    sys_type:     sysType      || undefined,
    unit_type:    unitType     || undefined,
    q:            q.trim()     || undefined,
    min_clg_btu:  minClg ? Number(minClg) : undefined,
    max_clg_btu:  maxClg ? Number(maxClg) : undefined,
    limit:        500,
  }), [manufacturer, sysType, unitType, q, minClg, maxClg]);

  const browse = useDfunitBrowse(filters);
  const data = browse.data;

  const resetAll = () => {
    setManufacturer(""); setSysType(""); setUnitType("");
    setQ(""); setMinClg(""); setMaxClg("");
  };

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Cpu className="w-5 h-5 text-primary" />
            DFUnit Explorer
          </h1>
          <p className="text-muted-foreground text-sm mt-1 max-w-3xl">
            Browse Tom's bundled Wrightsoft equipment library —{" "}
            <span className="font-mono text-xs">DFUnit.csv</span>:
            ductless heads, mini-splits, and heat pumps. Filter by
            manufacturer, system type, or cooling capacity to confirm
            a designer's Wrightsoft pick has a matching catalog row
            before pushing it through the deterministic BOM pipeline.
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

      {/* Filter row */}
      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
            <div className="md:col-span-2">
              <Label className="text-xs">Search model / series</Label>
              <div className="relative mt-1">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="e.g. 38MARB, MUZ-GX"
                  className="h-9 pl-7"
                />
              </div>
            </div>
            <div>
              <Label className="text-xs">Manufacturer</Label>
              <Select value={manufacturer || "_any"} onValueChange={(v) => setManufacturer(v === "_any" ? "" : v)}>
                <SelectTrigger className="mt-1 h-9"><SelectValue placeholder="Any" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_any">Any</SelectItem>
                  {(data?.facets.manufacturers ?? []).map((m) => (
                    <SelectItem key={m} value={m}>{MFR_LABEL[m] ?? m} ({m})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">System type</Label>
              <Select value={sysType || "_any"} onValueChange={(v) => setSysType(v === "_any" ? "" : v)}>
                <SelectTrigger className="mt-1 h-9"><SelectValue placeholder="Any" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_any">Any</SelectItem>
                  {(data?.facets.sys_types ?? []).map((s) => (
                    <SelectItem key={s} value={s}>{SYS_TYPE_LABEL[s] ?? s} ({s})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Unit type</Label>
              <Select value={unitType || "_any"} onValueChange={(v) => setUnitType(v === "_any" ? "" : v)}>
                <SelectTrigger className="mt-1 h-9"><SelectValue placeholder="Any" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_any">Any</SelectItem>
                  {(data?.facets.unit_types ?? []).map((u) => (
                    <SelectItem key={u} value={u}>{UNIT_TYPE_LABEL[u] ?? u} ({u})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Cooling BTU (min)</Label>
              <Input
                type="number" inputMode="numeric"
                value={minClg} onChange={(e) => setMinClg(e.target.value)}
                placeholder="e.g. 18000" className="h-9 mt-1"
              />
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
            <div>
              <Label className="text-xs">Cooling BTU (max)</Label>
              <Input
                type="number" inputMode="numeric"
                value={maxClg} onChange={(e) => setMaxClg(e.target.value)}
                placeholder="e.g. 24000" className="h-9 mt-1"
              />
            </div>
            <div className="md:col-span-5 flex items-end gap-2">
              <Button variant="ghost" size="sm" onClick={resetAll}>
                Clear filters
              </Button>
              <div className="flex-1" />
              <div className="text-xs text-muted-foreground">
                {data
                  ? <>Showing <span className="font-medium text-foreground">{data.returned}</span> of {data.total.toLocaleString()} matches</>
                  : "—"}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {browse.error && (
        <Card><CardContent className="p-4 text-sm text-destructive">
          Failed to load DFUnit catalog: {(browse.error as any)?.error ?? "unknown error"}
        </CardContent></Card>
      )}

      {/* Result table */}
      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-sm">Equipment</CardTitle>
          <CardDescription className="text-xs">
            Cooling + heating BTU come straight from the Wrightsoft
            catalog. Dimensions (W×D×H, weight) are useful for clearance
            checks during install.
          </CardDescription>
        </CardHeader>
        <Separator />
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b bg-muted/30 text-muted-foreground">
                <th className="text-left  px-3 py-2 font-medium">Mfr</th>
                <th className="text-left  px-3 py-2 font-medium">Model</th>
                <th className="text-left  px-3 py-2 font-medium">Type</th>
                <th className="text-left  px-3 py-2 font-medium">Series</th>
                <th className="text-right px-3 py-2 font-medium">Cooling BTU</th>
                <th className="text-right px-3 py-2 font-medium">Heating BTU</th>
                <th className="text-right px-3 py-2 font-medium">W×D×H (in)</th>
                <th className="text-right px-3 py-2 font-medium">Weight</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {browse.isPending && (
                <tr><td colSpan={8} className="px-3 py-8 text-center">
                  <Loader2 className="w-4 h-4 animate-spin inline mr-1 text-muted-foreground" />
                  <span className="text-muted-foreground">Loading…</span>
                </td></tr>
              )}
              {data?.items.map((it, i) => (
                <tr key={`${it.model}-${i}`} className="hover:bg-muted/20">
                  <td className="px-3 py-1.5 font-mono text-[11px]">
                    {it.manufacturer}
                    <span className="ml-1 text-muted-foreground/70">
                      {MFR_LABEL[it.manufacturer ?? ""] ? `· ${MFR_LABEL[it.manufacturer!]}` : ""}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 font-mono text-[11px] font-medium">{it.model}</td>
                  <td className="px-3 py-1.5">
                    <div className="flex items-center gap-1 flex-wrap">
                      <Badge variant="outline" className="text-[10px]">
                        {UNIT_TYPE_LABEL[it.unit_type ?? ""] ?? it.unit_type ?? "—"}
                      </Badge>
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-[10px]",
                          it.sys_type === "H" && "border-orange-500/40 text-orange-700 dark:text-orange-400",
                          it.sys_type === "A" && "border-sky-500/40 text-sky-700 dark:text-sky-400",
                        )}
                      >
                        {it.sys_type === "H" ? <Flame className="w-2.5 h-2.5 mr-0.5" /> :
                         it.sys_type === "A" ? <Snowflake className="w-2.5 h-2.5 mr-0.5" /> : null}
                        {SYS_TYPE_LABEL[it.sys_type ?? ""] ?? it.sys_type ?? "—"}
                      </Badge>
                    </div>
                  </td>
                  <td className="px-3 py-1.5 text-muted-foreground">{it.series ?? "—"}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {it.cooling_btu != null ? it.cooling_btu.toLocaleString() : "—"}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {it.heating_btu != null ? it.heating_btu.toLocaleString() : "—"}
                  </td>
                  <td className="px-3 py-1.5 text-right text-muted-foreground tabular-nums">
                    {fmtDims(it.width_in, it.depth_in, it.height_in)}
                  </td>
                  <td className="px-3 py-1.5 text-right text-muted-foreground tabular-nums">
                    {it.weight_lb != null ? `${it.weight_lb} lb` : "—"}
                  </td>
                </tr>
              ))}
              {data && data.items.length === 0 && (
                <tr><td colSpan={8} className="text-center py-8 text-muted-foreground italic">
                  No equipment matches the current filters.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function fmtDims(w: number | null, d: number | null, h: number | null) {
  if (w == null && d == null && h == null) return "—";
  return [w, d, h].map((v) => v == null ? "?" : v).join("×");
}
