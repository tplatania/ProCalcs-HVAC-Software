// SKU Backlog — prioritized list of catalog SKUs to encode next,
// driven by every sample-BOM comparison Richard's team has ever
// uploaded. Each row aggregates one "missing SKU" across all runs,
// sorted by demand (occurrence count, then total quantity).
//
// Think of it as the catalog-encoding queue: top row = the SKU that
// most often shows up missing on contractor reference BOMs, with
// run IDs you can click into to see the original context.

import { useState } from "react";
import { useLocation } from "wouter";
import {
  AlertTriangle,
  ExternalLink,
  Loader2,
  PackagePlus,
  RefreshCw,
} from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { useMissingSkuBacklog, type MissingSkuBacklogItem } from "@/lib/api-hooks";
import { UserChip } from "@/components/user-chip";

export default function SkuBacklogPage() {
  const [, setLocation] = useLocation();
  const [clientFilter, setClientFilter] = useState("");

  const backlog = useMissingSkuBacklog({
    client_id: clientFilter.trim() || undefined,
  });

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <PackagePlus className="w-5 h-5 text-primary" />
            SKU Backlog
          </h1>
          <p className="text-muted-foreground text-sm mt-1 max-w-3xl">
            Every SKU that showed up missing on a sample-BOM comparison,
            grouped and sorted by demand. Top rows are the catalog entries
            most worth encoding next. Each row links to the original runs
            so you can confirm context before adding the SKU.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => backlog.refetch()}
          disabled={backlog.isFetching}
        >
          {backlog.isFetching ? (
            <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
          ) : (
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
          )}
          Refresh
        </Button>
      </div>

      <Card>
        <CardContent className="p-4 flex flex-wrap gap-3 items-end">
          <div className="min-w-[220px]">
            <Label className="text-xs uppercase tracking-wide text-muted-foreground">
              Client ID
            </Label>
            <Input
              value={clientFilter}
              onChange={(e) => setClientFilter(e.target.value)}
              placeholder="exact match (e.g. procalcs-direct)"
              className="h-9 mt-1"
            />
          </div>
          {backlog.data && (
            <div className="flex gap-3 text-xs text-muted-foreground self-center">
              <span>
                <strong className="text-foreground">{backlog.data.total_missing_skus_unique}</strong>{" "}
                distinct SKUs across{" "}
                <strong className="text-foreground">{backlog.data.total_comparisons}</strong>{" "}
                comparisons
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      {backlog.error && (
        <Card>
          <CardContent className="p-4 text-sm text-destructive flex gap-2 items-start">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            Failed to load backlog: {(backlog.error as any)?.error ?? "unknown error"}
          </CardContent>
        </Card>
      )}

      {backlog.data && backlog.data.items.length === 0 && !backlog.isPending && (
        <Card>
          <CardContent className="p-8 text-center space-y-3">
            <PackagePlus className="w-8 h-8 mx-auto text-muted-foreground/40" />
            <div>
              <p className="text-sm font-medium">No missing-SKU backlog yet.</p>
              <p className="text-xs text-muted-foreground mt-1">
                Upload a contractor sample BOM via the{" "}
                <button className="underline" onClick={() => setLocation("/diagnostics/run-history")}>
                  Run History
                </button>{" "}
                page's Compare card. Every comparison's missing SKUs land here.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {backlog.data && backlog.data.items.length > 0 && (
        <Card>
          <CardHeader className="py-3">
            <CardTitle className="text-sm">Top-priority SKUs to encode</CardTitle>
            <CardDescription className="text-xs">
              Sorted by how often the SKU has been missing, then by total quantity demanded.
            </CardDescription>
          </CardHeader>
          <Separator />
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b bg-muted/30 text-muted-foreground">
                  <th className="text-left  px-3 py-2 font-medium w-12">#</th>
                  <th className="text-left  px-3 py-2 font-medium">SKU</th>
                  <th className="text-left  px-3 py-2 font-medium">Description</th>
                  <th className="text-right px-3 py-2 font-medium">Missing in</th>
                  <th className="text-right px-3 py-2 font-medium">Total qty</th>
                  <th className="text-left  px-3 py-2 font-medium">Last seen</th>
                  <th className="text-left  px-3 py-2 font-medium">Flagged by</th>
                  <th className="text-left  px-3 py-2 font-medium">Runs</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {backlog.data.items.map((item, idx) => (
                  <BacklogRow
                    key={item.sku ?? item.description ?? String(idx)}
                    rank={idx + 1}
                    item={item}
                    onOpenSkuEditor={() =>
                      setLocation(`/sku-catalog?prefill=${encodeURIComponent(item.sku_display ?? item.sku ?? "")}`)
                    }
                    onOpenRun={(runId) =>
                      setLocation(`/diagnostics/run-history?run=${runId}`)
                    }
                  />
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function BacklogRow({
  rank,
  item,
  onOpenSkuEditor,
  onOpenRun,
}: {
  rank: number;
  item: MissingSkuBacklogItem;
  onOpenSkuEditor: () => void;
  onOpenRun: (runId: number) => void;
}) {
  const isTop = rank <= 3;
  return (
    <tr className="hover:bg-muted/20">
      <td className="px-3 py-1.5 text-muted-foreground">
        {isTop ? (
          <Badge variant="default" className="text-[10px] px-1.5">{rank}</Badge>
        ) : (
          rank
        )}
      </td>
      <td className="px-3 py-1.5">
        <span className="font-mono text-[11px]">
          {item.sku_display ?? item.sku ?? <span className="text-muted-foreground italic">(no SKU)</span>}
        </span>
      </td>
      <td className="px-3 py-1.5 max-w-[320px]">
        <span className="truncate block" title={item.description ?? ""}>
          {item.description ?? <span className="text-muted-foreground italic">—</span>}
        </span>
      </td>
      <td className="px-3 py-1.5 text-right font-semibold">
        {item.occurrence_count}{" "}
        <span className="text-muted-foreground font-normal text-[10px]">
          compare{item.occurrence_count === 1 ? "" : "s"}
        </span>
      </td>
      <td className="px-3 py-1.5 text-right">{item.total_qty.toFixed(1)}</td>
      <td className="px-3 py-1.5 text-muted-foreground text-[10px]">
        {item.last_seen ? formatDate(item.last_seen) : "—"}
      </td>
      <td className="px-3 py-1.5">
        <div className="flex flex-wrap gap-1 max-w-[160px]">
          {(item.contributors ?? []).length === 0 ? (
            <span className="text-muted-foreground italic text-[10px]">—</span>
          ) : (
            (item.contributors ?? []).slice(0, 4).map((email) => (
              <UserChip key={email} email={email} showText={false} />
            ))
          )}
          {(item.contributors?.length ?? 0) > 4 && (
            <span className="text-muted-foreground text-[10px]">
              +{(item.contributors!.length) - 4}
            </span>
          )}
        </div>
      </td>
      <td className="px-3 py-1.5 text-[10px]">
        <div className="flex flex-wrap gap-1 max-w-[220px]">
          {item.run_ids.slice(0, 5).map((rid) => (
            <button
              key={rid}
              onClick={() => onOpenRun(rid)}
              className="text-primary hover:underline font-mono"
              title={`Open run #${rid}`}
            >
              #{rid}
            </button>
          ))}
          {item.run_ids.length > 5 && (
            <span className="text-muted-foreground">+{item.run_ids.length - 5}</span>
          )}
        </div>
      </td>
      <td className="px-3 py-1.5 text-right">
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-[11px]"
          onClick={onOpenSkuEditor}
          title="Pre-fill the SKU Catalog editor with this SKU"
        >
          <PackagePlus className="w-3 h-3 mr-1" />
          Encode
          <ExternalLink className="w-2.5 h-2.5 ml-1" />
        </Button>
      </td>
    </tr>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day:   "numeric",
      hour:  "2-digit",
      minute:"2-digit",
    });
  } catch {
    return iso;
  }
}
