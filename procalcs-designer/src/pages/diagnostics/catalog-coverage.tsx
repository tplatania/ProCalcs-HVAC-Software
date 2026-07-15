// Catalog Coverage — Day-11. Per-category and per-supplier view of
// Tom's bundled mapped_parts.csv coverage. Tells Richard's team
// which Wrightsoft categories have the worst mapping coverage so
// they can prioritize what to add to mapped_parts.csv next.
//
// Worst-coverage categories surface at the top automatically.

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Loader2,
  PackagePlus,
  RefreshCw,
  XCircle,
} from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { useCatalogCoverage, type CatalogCoverageCategory } from "@/lib/api-hooks";
import { cn } from "@/lib/utils";


export default function CatalogCoveragePage() {
  const report = useCatalogCoverage();
  const [query, setQuery] = useState("");

  const filteredCategories = useMemo(() => {
    const rows = report.data?.categories ?? [];
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((c) =>
      c.category.toLowerCase().includes(q) ||
      c.description.toLowerCase().includes(q),
    );
  }, [report.data?.categories, query]);

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Database className="w-5 h-5 text-primary" />
            Catalog Coverage
          </h1>
          <p className="text-muted-foreground text-sm mt-1 max-w-3xl">
            How much of Wrightsoft's part catalog can the deterministic
            pipeline translate to manufacturer SKUs? Categories with the
            worst coverage are listed first — those are the highest-
            leverage gaps to fill in <span className="font-mono text-xs">mapped_parts.csv</span>.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => report.refetch()}
          disabled={report.isFetching}
        >
          {report.isFetching ? (
            <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
          ) : (
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
          )}
          Refresh
        </Button>
      </div>

      {report.error && (
        <Card>
          <CardContent className="p-4 text-sm text-destructive flex gap-2 items-start">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            Failed to load coverage: {(report.error as any)?.error ?? "unknown error"}
          </CardContent>
        </Card>
      )}

      {report.isPending && (
        <Card><CardContent className="p-8 flex justify-center">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </CardContent></Card>
      )}

      {report.data && (
        <>
          {/* Top-level totals */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard label="Generic parts" value={report.data.totals.generic_parts.toLocaleString()} />
            <StatCard
              label="Mapped"
              value={`${report.data.totals.covered_generics.toLocaleString()} (${report.data.totals.overall_coverage_pct.toFixed(1)}%)`}
              tone={report.data.totals.overall_coverage_pct >= 90 ? "emerald" : "amber"}
            />
            <StatCard label="Supplier variants" value={report.data.totals.mapped_supplier_variants.toLocaleString()} />
            <StatCard label="Suppliers" value={String(report.data.totals.suppliers)} />
            <StatCard label="DFUnit models" value={report.data.totals.dfunit_models.toLocaleString()} />
            <StatCard label="Categories" value={String(report.data.categories.length)} />
          </div>

          {/* Filter */}
          <Card>
            <CardContent className="p-4">
              <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                Filter categories
              </Label>
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="search by category code or description…"
                className="h-9 mt-1 max-w-md"
              />
            </CardContent>
          </Card>

          {/* Per-category table */}
          <Card>
            <CardHeader className="py-3">
              <CardTitle className="text-sm">Per-category coverage</CardTitle>
              <CardDescription className="text-xs">
                Worst coverage first. Click a category to see which suppliers
                contribute to its mapping. Amber rows mean &lt;50% coverage —
                top candidates for SKU encoding work.
              </CardDescription>
            </CardHeader>
            <Separator />
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b bg-muted/30 text-muted-foreground">
                    <th className="text-left  px-3 py-2 font-medium">Category</th>
                    <th className="text-left  px-3 py-2 font-medium">Description</th>
                    <th className="text-right px-3 py-2 font-medium">Generics</th>
                    <th className="text-right px-3 py-2 font-medium">Covered</th>
                    <th className="text-right px-3 py-2 font-medium">Coverage</th>
                    <th className="text-left  px-3 py-2 font-medium">Top suppliers</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {filteredCategories.map((c) => (
                    <CategoryRow key={c.category} c={c} />
                  ))}
                  {filteredCategories.length === 0 && (
                    <tr>
                      <td colSpan={6} className="text-center py-8 text-muted-foreground italic">
                        No categories match "{query}".
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Per-supplier rollup */}
          <Card>
            <CardHeader className="py-3">
              <CardTitle className="text-sm">Suppliers by coverage contribution</CardTitle>
              <CardDescription className="text-xs">
                How many distinct generic parts each supplier covers.
                Top supplier is the deepest catalog; coverage decreases
                from there.
              </CardDescription>
            </CardHeader>
            <Separator />
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b bg-muted/30 text-muted-foreground">
                    <th className="text-left  px-3 py-2 font-medium w-10">#</th>
                    <th className="text-left  px-3 py-2 font-medium">Code</th>
                    <th className="text-left  px-3 py-2 font-medium">Name</th>
                    <th className="text-right px-3 py-2 font-medium">Distinct generics covered</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {report.data.suppliers.map((s, i) => (
                    <tr key={s.supplier_code} className="hover:bg-muted/20">
                      <td className="px-3 py-1.5 text-muted-foreground">{i + 1}</td>
                      <td className="px-3 py-1.5 font-mono text-[11px]">{s.supplier_code}</td>
                      <td className="px-3 py-1.5">{s.name}</td>
                      <td className="px-3 py-1.5 text-right font-semibold">
                        {s.distinct_generics_covered.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}


function CategoryRow({ c }: { c: CatalogCoverageCategory }) {
  const [open, setOpen] = useState(false);
  const lowCoverage = c.coverage_pct < 50;
  return (
    <>
      <tr
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "cursor-pointer hover:bg-muted/30",
          lowCoverage && "bg-amber-500/[0.04]",
          c.coverage_pct === 0 && "bg-rose-500/[0.04]",
        )}
      >
        <td className="px-3 py-1.5 font-mono text-[11px]">{c.category}</td>
        <td className="px-3 py-1.5">{c.description}</td>
        <td className="px-3 py-1.5 text-right">{c.total_generics}</td>
        <td className="px-3 py-1.5 text-right">{c.covered_generics}</td>
        <td className="px-3 py-1.5 text-right">
          <CoverageBadge pct={c.coverage_pct} />
        </td>
        <td className="px-3 py-1.5 text-[10px] text-muted-foreground">
          {c.suppliers.length === 0 ? (
            <span className="italic">none</span>
          ) : (
            c.suppliers.slice(0, 3).map((s) => (
              <span key={s.supplier_code} className="font-mono mr-2">
                {s.supplier_code}×{s.mapped_count}
              </span>
            ))
          )}
          {c.suppliers.length > 3 && (
            <span className="text-muted-foreground">+{c.suppliers.length - 3}</span>
          )}
        </td>
      </tr>
      {open && c.suppliers.length > 0 && (
        <tr className="bg-muted/10">
          <td colSpan={6} className="px-6 py-3 text-xs">
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
              {c.suppliers.map((s) => (
                <div key={s.supplier_code} className="flex items-center gap-2 border rounded px-2 py-1.5 bg-background">
                  <PackagePlus className="w-3 h-3 text-muted-foreground" />
                  <span className="font-mono text-[11px]">{s.supplier_code}</span>
                  <span className="text-muted-foreground truncate">{s.name}</span>
                  <span className="ml-auto font-semibold text-xs">{s.mapped_count}</span>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}


function CoverageBadge({ pct }: { pct: number }) {
  const cls =
    pct >= 90 ? "border-emerald-500/40 text-emerald-700 dark:text-emerald-400" :
    pct >= 50 ? "border-amber-500/40 text-amber-700 dark:text-amber-400" :
                "border-rose-500/40 text-rose-700 dark:text-rose-400";
  const Icon = pct >= 90 ? CheckCircle2 : pct >= 50 ? AlertTriangle : XCircle;
  return (
    <Badge variant="outline" className={cn("gap-1 px-1.5 text-[10px]", cls)}>
      <Icon className="w-3 h-3" />
      {pct.toFixed(0)}%
    </Badge>
  );
}


function StatCard({ label, value, tone }: {
  label: string; value: string; tone?: "emerald" | "amber";
}) {
  const cls = tone === "emerald" ? "border-emerald-500/30" :
              tone === "amber"   ? "border-amber-500/30" : "";
  return (
    <Card className={cn("border", cls)}>
      <CardContent className="p-3">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="text-base font-bold mt-0.5">{value}</p>
      </CardContent>
    </Card>
  );
}
