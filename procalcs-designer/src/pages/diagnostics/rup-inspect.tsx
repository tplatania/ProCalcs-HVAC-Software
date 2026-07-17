// RUP Inspector — diagnostic page that opens a .rup file and shows
// what our parser can and CANNOT see in the binary.
//
// Day-10 reframing: the headline finding is that the .rup binary
// does NOT contain the project's BOM — Wrightsoft computes that at
// output time. The inspector now leads with that fact and points to
// the deterministic pipeline (Wrightsoft BOM upload), with the
// ZEQUIP ↔ ECDUCTSYS pairing kept below as backing diagnostic
// detail. AI-as-fallback framing was deliberately removed: the
// source of truth is /Users/geraldvillaran/Procalcs/Catalogs/
// (mapped_parts.csv) reached via the Wrightsoft BOM upload, not
// AI estimation.
//
// No persistence, no AI, no costs — just upload → diagnosis.

import { useState } from "react";
import { useLocation } from "wouter";
import {
  AlertTriangle,
  CheckCircle2,
  FileSearch,
  Loader2,
  PackagePlus,
  Upload,
  XCircle,
} from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { useRupInspect, type RupInspectResponse } from "@/lib/api-hooks";
import { useCurrentUser } from "@/lib/auth-hooks";
import { UserChip } from "@/components/user-chip";

export default function RupInspectPage() {
  const [result, setResult] = useState<RupInspectResponse | null>(null);
  const inspect = useRupInspect();
  const { data: currentUser } = useCurrentUser();
  const [, setLocation] = useLocation();

  const onPickFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";  // reset so picking the same file twice still fires
    if (!file) return;
    if (!/\.rup$/i.test(file.name)) {
      alert("Pick a .rup file.");
      return;
    }
    setResult(null);
    inspect.mutate(file, { onSuccess: setResult });
  };

  return (
    <div className="space-y-6 max-w-[1200px] mx-auto">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <FileSearch className="w-5 h-5 text-primary" />
            RUP Inspector
          </h1>
          <p className="text-muted-foreground text-sm mt-1 max-w-3xl">
            Upload a Wrightsoft <span className="font-mono text-xs">.rup</span> file
            and see what our parser CAN and CANNOT extract from it. The
            headline finding for every Wrightsoft file we've examined: the
            project BOM is not stored in the binary — Wrightsoft computes it
            at output time. This inspector tells you whether a given file
            breaks that pattern (it never has, so far) and what to do instead
            for a deterministic BOM.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/30 border rounded-md px-2.5 py-1.5">
          Inspecting as
          <UserChip email={currentUser?.email} size="md" />
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Pick a .rup file</CardTitle>
          <CardDescription className="text-xs">
            Nothing is persisted; the file is parsed in-memory and the result
            is shown below.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <label className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium border rounded-md hover:bg-muted cursor-pointer w-fit">
            {inspect.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Upload className="w-4 h-4" />
            )}
            {inspect.isPending ? "Inspecting…" : "Choose .rup"}
            <input
              type="file"
              accept=".rup"
              className="hidden"
              onChange={onPickFile}
              disabled={inspect.isPending}
            />
          </label>
          {inspect.error && (
            <div className="mt-3 text-sm text-destructive flex gap-2 items-start">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              {(inspect.error as any)?.error ?? "Inspection failed"}
            </div>
          )}
        </CardContent>
      </Card>

      {result && (
        <ResultView
          result={result}
          onOpenWrightsoftBom={() => setLocation("/diagnostics/wrightsoft-bom")}
        />
      )}
    </div>
  );
}

// Silence the unused-import lint if XCircle isn't used in the current
// layout — it's intentionally imported in case future statuses need it.
void XCircle;

function ResultView({ result, onOpenWrightsoftBom }: {
  result: RupInspectResponse;
  onOpenWrightsoftBom: () => void;
}) {
  const entries = Object.entries(result.summary.label_distribution).sort(
    ([, a], [, b]) => b - a,
  );
  const xref = result.catalog_xref;
  return (
    <div className="space-y-4">
      {/* Day-10 headline — deterministic-pipeline verdict */}
      {xref && (
        <Card className={xref.bom_is_in_binary
          ? "border-emerald-500/40"
          : "border-amber-500/40 bg-amber-500/[0.03]"}>
          <CardHeader className="py-3">
            <CardTitle className="text-sm flex items-center gap-2">
              {xref.bom_is_in_binary ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              ) : (
                <AlertTriangle className="w-4 h-4 text-amber-600" />
              )}
              {xref.bom_is_in_binary
                ? "BOM reachable from this binary"
                : "BOM is NOT in this binary"}
            </CardTitle>
            <CardDescription className="text-xs mt-1">
              {xref.generic_ids_found} of {xref.generic_ids_in_catalog.toLocaleString()}{" "}
              Wrightsoft catalog generic-part IDs appear in this file
              {xref.found_sample.length > 0 && (
                <> ({xref.found_sample.slice(0, 5).map((s, i) => (
                  <span key={i}>
                    {i > 0 ? ", " : ""}<span className="font-mono">{s}</span>
                  </span>
                ))}{xref.found_sample.length > 5 ? "..." : ""})</>
              )}.
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-0 text-xs">
            <p className="text-muted-foreground mb-3">{xref.recommendation}</p>
            {!xref.bom_is_in_binary && (
              <Button size="sm" variant="default" onClick={onOpenWrightsoftBom}>
                <PackagePlus className="w-3.5 h-3.5 mr-1.5" />
                Open Wrightsoft BOM upload
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-sm">{result.source_file}</CardTitle>
          <CardDescription className="text-xs">
            Backing diagnostic — what the binary DOES carry, for
            cross-referencing against the Wrightsoft equipment screen.
          </CardDescription>
        </CardHeader>
        <Separator />
        <CardContent className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 text-xs">
          <Stat label="ZEQUIP records" value={String(result.summary.zequip_total)} />
          <Stat label="ECDUCTSYS records" value={String(result.summary.ecductsys_total)} />
          <Stat label="Labeled" value={`${result.summary.labeled_count} / ${result.summary.ecductsys_total}`} />
          <Stat
            label="Distinct labels"
            value={String(entries.length)}
            sub={entries.length === 0
              ? "(no labels — system structure can't be inferred from this binary alone)"
              : undefined}
          />
        </CardContent>
      </Card>

      {entries.length > 0 && (
        <Card>
          <CardHeader className="py-3">
            <CardTitle className="text-sm">Label distribution</CardTitle>
            <CardDescription className="text-xs">
              Each label is the name of a system / piece of equipment Wrightsoft
              attached to one or more zones. The total count of labeled records
              is usually less than the zone count — unlabeled zones inherit
              from the most recently labeled record above them in the file.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {entries.map(([label, count]) => (
              <Badge key={label} variant="secondary" className="text-xs">
                <span className="font-mono">{label}</span>
                <span className="ml-1.5 text-muted-foreground">×{count}</span>
              </Badge>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-sm">
            Per-zone records ({result.rows.length})
          </CardTitle>
          <CardDescription className="text-xs">
            One row per zone with equipment placed. Use the ECDUCTSYS label
            column to cross-reference the equipment screen in Wrightsoft.
          </CardDescription>
        </CardHeader>
        <Separator />
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b bg-muted/30 text-muted-foreground">
                <th className="text-left  px-3 py-2 font-medium w-16">Index</th>
                <th className="text-right px-3 py-2 font-medium">ZEQUIP record id</th>
                <th className="text-left  px-3 py-2 font-medium">ECDUCTSYS label</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {result.rows.map((r) => (
                <tr
                  key={r.index}
                  className={cn(
                    "hover:bg-muted/20",
                    r.ecductsys_label && "bg-emerald-500/[0.04]",
                  )}
                >
                  <td className="px-3 py-1.5 font-mono text-[11px] text-muted-foreground">
                    {r.index}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-[11px] text-right">
                    {r.zequip_record_id ?? "—"}
                  </td>
                  <td className="px-3 py-1.5">
                    {r.ecductsys_label ? (
                      <span className="font-mono text-[11px]">{r.ecductsys_label}</span>
                    ) : (
                      <span className="text-muted-foreground italic text-[11px]">
                        (unlabeled — inherits)
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      <p className="font-bold text-lg leading-tight">{value}</p>
      {sub && <p className="text-[10px] text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}
