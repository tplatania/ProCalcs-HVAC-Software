// Rules-engine preview — a diagnostic surface for the deterministic
// materials_rules layer in procalcs-bom. Designers and Richard can run
// any parsed .rup through the catalog-driven rules ALONE, with no AI
// estimation and no contractor pricing, to see exactly which lines the
// rules engine produces. This is the spot-check tool the eval-2026-04-29
// post-mortem identified as missing.
//
// Re-uses the same parsed-rup sessionStorage as the BOM Output page —
// the user uploads their .rup on the BOM Engine page once, then can
// switch between /bom-output and /diagnostics/rules-preview to compare
// the rules-only baseline with the merged AI+rules output.

import { useState, useMemo } from "react";
import { useLocation } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  ArrowLeft,
  Beaker,
  ShieldCheck,
  XCircle,
  FileText,
  AlertTriangle,
  Building2,
} from "lucide-react";
import {
  useRulesPreview,
  loadParsedRup,
  type RulesPreviewResponse,
  type StoredParseResult,
} from "@/lib/api-hooks";

// ─── Page ───────────────────────────────────────────────────────────────

type PageState = "needs-input" | "ready" | "running" | "done" | "error";

export default function RulesPreviewPage() {
  const [, setLocation] = useLocation();
  const [stored] = useState<StoredParseResult | null>(() => loadParsedRup());
  const [result, setResult] = useState<RulesPreviewResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const preview = useRulesPreview();

  const pageState: PageState = !stored
    ? "needs-input"
    : errorMsg
    ? "error"
    : result
    ? "done"
    : preview.isPending
    ? "running"
    : "ready";

  const handleRun = () => {
    if (!stored) return;
    setErrorMsg(null);
    setResult(null);
    preview.mutate(
      { design_data: stored.designData, output_mode: "full" },
      {
        onSuccess: (data) => setResult(data),
        onError: (err) => setErrorMsg(err?.error ?? "Rules preview failed"),
      }
    );
  };

  // ─── Empty state ───────────────────────────────────────────────────────

  if (pageState === "needs-input") {
    return (
      <div className="max-w-2xl mx-auto">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-muted-foreground" />
              No parsed .rup file yet
            </CardTitle>
            <CardDescription>
              The Rules-Engine Preview runs against an already-parsed RUP. Upload one on
              the BOM Engine page first, then come back here to see the catalog-driven
              baseline.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => setLocation("/bom-engine")}>
              <ArrowLeft className="w-4 h-4 mr-1.5" />
              Go to BOM Engine
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ─── Header + run controls (always rendered when we have a parse) ─────

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Beaker className="w-5 h-5 text-primary" />
            Rules-Engine Preview
          </h1>
          <p className="text-muted-foreground text-sm mt-1 max-w-2xl">
            Runs the deterministic <span className="font-medium">materials_rules</span> engine
            in procalcs-bom against the parsed .rup —{" "}
            <span className="font-medium">no AI, no profile, no markup</span>. Shows
            exactly which SKU lines the catalog produces from the design alone. Use
            this to spot-check what the rules layer is contributing to a /generate run.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setLocation("/bom-engine")}>
          <ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
          Back to BOM Engine
        </Button>
      </div>

      <ParsedSummary stored={stored!} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            Run preview
          </CardTitle>
          <CardDescription>
            No Claude call. Output is fully deterministic — running this twice on the
            same RUP returns identical SKUs and quantities.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {pageState === "error" && (
            <div className="flex items-start gap-3 p-4 bg-destructive/5 border border-destructive/30 rounded-lg">
              <XCircle className="w-5 h-5 text-destructive mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-medium text-destructive">Preview failed</p>
                <p className="text-xs text-muted-foreground mt-0.5">{errorMsg}</p>
              </div>
            </div>
          )}

          <Button
            className="w-full"
            size="lg"
            onClick={handleRun}
            disabled={pageState === "running"}
          >
            <Beaker className="w-4 h-4 mr-2" />
            {pageState === "running" ? "Running rules engine..." : "Run preview"}
          </Button>
        </CardContent>
      </Card>

      {result && <ResultView result={result} />}
    </div>
  );
}

// ─── Parsed summary banner (mirrors BOM Output) ────────────────────────

function ParsedSummary({ stored }: { stored: StoredParseResult }) {
  return (
    <Card className="border-primary/20 bg-primary/5">
      <CardContent className="p-4">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Project
            </p>
            <p className="font-medium truncate">
              {stored.designData.project?.name ?? stored.sourceFile}
            </p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Building
            </p>
            <p className="font-medium">
              {(stored.designData.building?.type ?? "unknown").replace("_", " ")} /{" "}
              {stored.designData.building?.duct_location ?? "—"}
            </p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Equipment
            </p>
            <p className="font-medium">{stored.designData.equipment?.length ?? 0} units</p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Rooms
            </p>
            <p className="font-medium">{stored.designData.rooms?.length ?? 0} rooms</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Result view ───────────────────────────────────────────────────────

function ResultView({ result }: { result: RulesPreviewResponse }) {
  // Group line items by section (per ae5bd2b: equipment / duct / etc.).
  // Section is the rules-engine's own categorization; we render it
  // verbatim so engineering can match output to materials_rules.py.
  const grouped = useMemo(() => {
    const groups = new Map<string, typeof result.line_items>();
    for (const item of result.line_items) {
      const key = item.section || item.category || "other";
      const arr = groups.get(key) ?? [];
      arr.push(item);
      groups.set(key, arr);
    }
    return Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [result.line_items]);

  const scopeEntries = useMemo(() => {
    return Object.entries(result.scope ?? {}).sort(([a], [b]) => a.localeCompare(b));
  }, [result.scope]);

  const totalCost = result.totals?.total_cost ?? 0;
  const isEmpty = result.item_count === 0;

  return (
    <div className="space-y-6">
      {isEmpty ? (
        <Card className="border-amber-500/40 bg-amber-50 dark:bg-amber-950/20">
          <CardContent className="p-4 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-600 mt-0.5 shrink-0" />
            <div className="text-sm">
              <p className="font-semibold">Rules engine produced 0 lines.</p>
              <p className="text-muted-foreground mt-1">
                The catalog has no rules that match this RUP's scope. Either the parser
                didn't surface fields the triggers look at (check the Scope block below),
                or this RUP shape isn't covered yet — both worth a look at{" "}
                <code className="text-xs">procalcs-bom/backend/services/materials_rules.py</code>.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="border-emerald-500/30">
          <CardContent className="p-4 flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-emerald-600" />
              <span className="text-sm">
                <span className="font-semibold">{result.item_count}</span>{" "}
                <span className="text-muted-foreground">deterministic line item{result.item_count === 1 ? "" : "s"}</span>
              </span>
            </div>
            <Separator orientation="vertical" className="h-6 hidden sm:block" />
            <div className="text-sm">
              <span className="text-muted-foreground">Catalog cost:</span>{" "}
              <span className="font-semibold">
                $
                {totalCost.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </span>
              {totalCost === 0 && (
                <span className="ml-2 text-xs text-muted-foreground">
                  (catalog default_unit_price is $0 for most SKUs — gap to be seeded)
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Scope diagnostic — shows what the rules engine actually saw */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <Building2 className="w-4 h-4 text-muted-foreground" />
            Scope detected
          </CardTitle>
          <CardDescription>
            Triggers the rules engine evaluated against. Useful for diagnosing why a
            rule did or didn't fire.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {scopeEntries.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">No scope flags returned.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-1 text-xs font-mono">
              {scopeEntries.map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 border-b border-border/30 py-1">
                  <span className="text-muted-foreground">{k}</span>
                  <span className="truncate text-right">{formatScopeValue(v)}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Grouped line items */}
      {grouped.map(([section, items]) => (
        <Card key={section} className="overflow-hidden">
          <CardHeader className="py-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">{section}</CardTitle>
              <Badge variant="secondary" className="text-xs">
                {items.length} item{items.length === 1 ? "" : "s"}
              </Badge>
            </div>
          </CardHeader>
          <Separator />
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b bg-muted/30 text-muted-foreground">
                  <th className="text-left px-5 py-2.5 font-medium">SKU</th>
                  <th className="text-left px-3 py-2.5 font-medium">Description</th>
                  <th className="text-right px-3 py-2.5 font-medium">Qty</th>
                  <th className="text-right px-3 py-2.5 font-medium">Unit</th>
                  <th className="text-right px-3 py-2.5 font-medium hidden sm:table-cell">
                    Unit Cost
                  </th>
                  <th className="text-right px-5 py-2.5 font-medium">Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {items.map((item, i) => (
                  <tr key={`${item.sku ?? "-"}-${i}`} className="hover:bg-muted/20">
                    <td className="px-5 py-2.5 font-mono text-[11px]">{item.sku ?? "—"}</td>
                    <td className="px-3 py-2.5 font-medium">{item.description}</td>
                    <td className="px-3 py-2.5 text-right">{item.quantity}</td>
                    <td className="px-3 py-2.5 text-right text-muted-foreground">
                      {item.unit}
                    </td>
                    <td className="px-3 py-2.5 text-right text-muted-foreground hidden sm:table-cell">
                      ${(item.unit_cost ?? 0).toFixed(2)}
                    </td>
                    <td className="px-5 py-2.5 text-right font-semibold">
                      ${(item.total_cost ?? 0).toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ))}
    </div>
  );
}

// Best-effort string rendering for arbitrary JSON values. Booleans become
// ✓/✗ for quick scanning; objects/arrays JSON-stringified compact.
function formatScopeValue(v: unknown): string {
  if (typeof v === "boolean") return v ? "✓" : "✗";
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
