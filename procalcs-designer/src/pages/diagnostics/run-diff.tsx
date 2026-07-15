// Run Diff — side-by-side comparison of two BOM runs from the
// bom_runs persistence layer (procalcs-bom Phase 3 + 4 endpoints,
// designer Phase 5 hooks). Built for Richard's testing harness loop:
// after running the same RUP through a Phase-2-prompt build and a
// post-Phase-2-prompt build, open both in this page to see exactly
// which lines moved.
//
// URL-driven: ?left=<id>&right=<id>. Defaults to {regenerated_from_id,
// id} when arriving via the "Diff with parent" button on run-history,
// otherwise empty until the user picks both sides.

import { useEffect, useMemo, useState } from "react";
import { useLocation, useSearchParams } from "wouter";
import {
  GitCompareArrows,
  ArrowRight,
  Plus,
  Minus,
  Equal,
  ArrowUpRight,
  ArrowDownRight,
  Loader2,
  ListChecks,
  Copy,
  Download,
  Check,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { formatDiffAsMarkdown } from "@/lib/bom-diff-export";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { UserChip } from "@/components/user-chip";
import {
  useGetBomRun,
  useListBomRuns,
  type BomRunDetail,
  type BomRunSummary,
} from "@/lib/api-hooks";
import { diffBoms, type DiffChange, type DiffRow, type DiffSummary } from "@/lib/bom-diff";

// ─── Page ──────────────────────────────────────────────────────────────

export default function RunDiffPage() {
  const [, setLocation] = useLocation();
  const [params, setSearchParams] = useSearchParams();
  const leftId = parseIntOrNull(params.get("left"));
  const rightId = parseIntOrNull(params.get("right"));

  const left = useGetBomRun(leftId);
  const right = useGetBomRun(rightId);
  // Recent-runs picker — top 100 newest, no filter. Plenty for staging.
  const recent = useListBomRuns({ limit: 100 });

  const setSide = (side: "left" | "right", id: number | null) => {
    const next = new URLSearchParams(params);
    if (id == null) next.delete(side);
    else next.set(side, String(id));
    setSearchParams(next);
  };

  const diff = useMemo(() => {
    return diffBoms(left.data?.generated_bom ?? null, right.data?.generated_bom ?? null);
  }, [left.data?.generated_bom, right.data?.generated_bom]);

  const bothLoaded = !!left.data && !!right.data;

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <GitCompareArrows className="w-5 h-5 text-primary" />
          Run Diff
        </h1>
        <p className="text-muted-foreground text-sm mt-1 max-w-2xl">
          Side-by-side comparison of two BOM runs. Lines pair on{" "}
          <span className="font-mono text-xs">sku</span> when present, otherwise on{" "}
          <span className="font-mono text-xs">description+section+source</span>. Sub-cent
          totals jitter is treated as no change.
        </p>
      </div>

      {/* Pickers */}
      <Card>
        <CardContent className="p-4 grid grid-cols-1 md:grid-cols-[1fr,auto,1fr] gap-4 items-end">
          <RunPicker
            label="Left (baseline)"
            value={leftId}
            onChange={(id) => setSide("left", id)}
            options={recent.data?.runs ?? []}
            loading={recent.isPending}
            currentDetail={left.data}
            currentLoading={left.isPending}
            currentError={(left.error as any)?.error}
          />
          <ArrowRight className="w-5 h-5 text-muted-foreground self-center hidden md:block" />
          <RunPicker
            label="Right (compared)"
            value={rightId}
            onChange={(id) => setSide("right", id)}
            options={recent.data?.runs ?? []}
            loading={recent.isPending}
            currentDetail={right.data}
            currentLoading={right.isPending}
            currentError={(right.error as any)?.error}
          />
        </CardContent>
      </Card>

      {(leftId == null || rightId == null) && (
        <Card>
          <CardContent className="p-8 text-center space-y-2 text-sm text-muted-foreground">
            <ListChecks className="w-8 h-8 mx-auto text-muted-foreground/40" />
            <p>Pick both sides above to compute a diff.</p>
            <p className="text-xs">
              Tip — open a regenerated run from{" "}
              <button
                className="underline"
                onClick={() => setLocation("/diagnostics/run-history")}
              >
                Run History
              </button>{" "}
              and click "Diff with parent" to land here pre-filled.
            </p>
          </CardContent>
        </Card>
      )}

      {bothLoaded && (
        <div className="flex items-end justify-between gap-3 flex-wrap">
          <SummaryStrip summary={diff.summary} />
          <ExportDiffButtons
            diff={diff}
            leftRun={left.data}
            rightRun={right.data}
          />
        </div>
      )}
      {bothLoaded && (
        <DiffTable rows={diff.rows} leftLabel={left.data!.job_id} rightLabel={right.data!.job_id} />
      )}
    </div>
  );
}

// ─── Export controls ────────────────────────────────────────────────────
//
// Markdown export tuned for pasting into a Claude Code conversation:
// tables with right-aligned numeric columns, changes grouped by kind
// (Added / Removed / Qty / Price), unchanged rows collapsed to a single
// summary line. See lib/bom-diff-export.ts for the formatter.

function ExportDiffButtons({
  diff,
  leftRun,
  rightRun,
}: {
  diff: ReturnType<typeof diffBoms>;
  leftRun: BomRunDetail;
  rightRun: BomRunDetail;
}) {
  const { toast } = useToast();
  const [copied, setCopied] = useState(false);

  const markdown = useMemo(
    () => formatDiffAsMarkdown(diff, leftRun, rightRun),
    [diff, leftRun, rightRun]
  );

  const filename = `bom-diff-${leftRun.id}-vs-${rightRun.id}.md`;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
      toast({
        title: "Diff copied for Claude Code",
        description: `${diff.summary.addedCount + diff.summary.removedCount + diff.summary.changedCount} changed rows · paste into a conversation`,
      });
    } catch (err: any) {
      toast({
        title: "Copy failed",
        description: err?.message ?? "Clipboard unavailable — use Download instead.",
        variant: "destructive",
      });
    }
  };

  const handleDownload = () => {
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex items-center gap-2">
      <Button size="sm" variant="outline" onClick={handleCopy}
              title="Copy the diff as markdown, formatted for pasting into a Claude Code conversation">
        {copied ? (
          <Check className="w-3.5 h-3.5 mr-1.5 text-emerald-600" />
        ) : (
          <Copy className="w-3.5 h-3.5 mr-1.5" />
        )}
        {copied ? "Copied" : "Copy for Claude Code"}
      </Button>
      <Button size="sm" variant="outline" onClick={handleDownload}
              title="Download the diff as a .md file">
        <Download className="w-3.5 h-3.5 mr-1.5" />
        Download .md
      </Button>
    </div>
  );
}

// ─── Pickers ───────────────────────────────────────────────────────────

function RunPicker({
  label,
  value,
  onChange,
  options,
  loading,
  currentDetail,
  currentLoading,
  currentError,
}: {
  label: string;
  value: number | null;
  onChange: (id: number | null) => void;
  options: BomRunSummary[];
  loading: boolean;
  currentDetail: BomRunDetail | undefined;
  currentLoading: boolean;
  currentError: string | undefined;
}) {
  return (
    <div>
      <Label className="text-xs uppercase tracking-wide text-muted-foreground">{label}</Label>
      <Select
        value={value != null ? String(value) : ""}
        onValueChange={(v) => onChange(v ? Number(v) : null)}
        disabled={loading}
      >
        <SelectTrigger className="mt-1">
          <SelectValue placeholder={loading ? "Loading runs…" : "Pick a run…"} />
        </SelectTrigger>
        <SelectContent>
          {options.map((r) => (
            <SelectItem key={r.id} value={String(r.id)}>
              #{r.id} · {r.job_id}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <div className="text-xs text-muted-foreground mt-1.5 min-h-[1.25rem]">
        {currentLoading && (
          <span className="flex items-center gap-1">
            <Loader2 className="w-3 h-3 animate-spin" /> loading…
          </span>
        )}
        {currentError && <span className="text-destructive">Error: {currentError}</span>}
        {currentDetail && (
          <span className="inline-flex items-center gap-1.5 flex-wrap">
            <UserChip email={currentDetail.created_by_email} /> ·{" "}
            {currentDetail.client_id} ·{" "}
            {currentDetail.item_count ?? 0} items ·{" "}
            {currentDetail.total_price != null ? `$${currentDetail.total_price.toFixed(2)}` : "—"}
          </span>
        )}
      </div>
    </div>
  );
}

// ─── Summary strip ─────────────────────────────────────────────────────

function SummaryStrip({ summary }: { summary: DiffSummary }) {
  const itemArrow = summary.itemCountDelta === 0 ? null : summary.itemCountDelta > 0 ? "+" : "";
  const costArrow = summary.totalCostDelta === 0 ? Equal : summary.totalCostDelta > 0 ? ArrowUpRight : ArrowDownRight;
  const priceArrow = summary.totalPriceDelta === 0 ? Equal : summary.totalPriceDelta > 0 ? ArrowUpRight : ArrowDownRight;
  const CostIcon = costArrow;
  const PriceIcon = priceArrow;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      <SummaryCard label="Items" left={summary.leftItemCount} right={summary.rightItemCount}
                   delta={`${itemArrow ?? ""}${summary.itemCountDelta}`} />
      <SummaryCard
        label="Total cost"
        left={`$${summary.leftTotalCost.toFixed(2)}`}
        right={`$${summary.rightTotalCost.toFixed(2)}`}
        delta={
          <span className="inline-flex items-center gap-0.5">
            <CostIcon className="w-3 h-3" />
            ${Math.abs(summary.totalCostDelta).toFixed(2)}
          </span>
        }
        deltaColor={summary.totalCostDelta === 0 ? "neutral" : summary.totalCostDelta > 0 ? "up" : "down"}
      />
      <SummaryCard
        label="Total price"
        left={`$${summary.leftTotalPrice.toFixed(2)}`}
        right={`$${summary.rightTotalPrice.toFixed(2)}`}
        delta={
          <span className="inline-flex items-center gap-0.5">
            <PriceIcon className="w-3 h-3" />
            ${Math.abs(summary.totalPriceDelta).toFixed(2)}
          </span>
        }
        deltaColor={summary.totalPriceDelta === 0 ? "neutral" : summary.totalPriceDelta > 0 ? "up" : "down"}
      />
      <BucketCard label="Added"     value={summary.addedCount}     color="green" Icon={Plus} />
      <BucketCard label="Removed"   value={summary.removedCount}   color="red"   Icon={Minus} />
      <BucketCard label="Changed"   value={summary.changedCount}   color="amber" Icon={GitCompareArrows} />
    </div>
  );
}

function SummaryCard({
  label, left, right, delta, deltaColor,
}: {
  label: string;
  left: string | number;
  right: string | number;
  delta: React.ReactNode;
  deltaColor?: "up" | "down" | "neutral";
}) {
  const color =
    deltaColor === "up" ? "text-emerald-600" :
    deltaColor === "down" ? "text-rose-600" :
    "text-muted-foreground";
  return (
    <Card>
      <CardContent className="p-3 space-y-0.5">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="text-xs">
          <span className="text-muted-foreground">{left}</span>{" "}
          <ArrowRight className="inline w-3 h-3 -mt-0.5 text-muted-foreground/60" />{" "}
          <span className="font-medium">{right}</span>
        </p>
        <p className={cn("text-xs font-semibold", color)}>{delta}</p>
      </CardContent>
    </Card>
  );
}

function BucketCard({
  label, value, color, Icon,
}: {
  label: string;
  value: number;
  color: "green" | "red" | "amber";
  Icon: React.ElementType;
}) {
  const tone = {
    green: "border-emerald-500/30 text-emerald-600",
    red:   "border-rose-500/30 text-rose-600",
    amber: "border-amber-500/30 text-amber-600",
  }[color];
  return (
    <Card className={cn("border", tone)}>
      <CardContent className="p-3 flex items-center gap-2">
        <Icon className="w-4 h-4" />
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
          <p className="text-lg font-bold leading-none">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Diff table ────────────────────────────────────────────────────────

function DiffTable({
  rows,
  leftLabel,
  rightLabel,
}: {
  rows: DiffRow[];
  leftLabel: string;
  rightLabel: string;
}) {
  const [showUnchanged, setShowUnchanged] = useState(false);
  const visible = showUnchanged ? rows : rows.filter((r) => r.change !== "unchanged");

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 py-3">
        <div>
          <CardTitle className="text-sm">Line-item diff</CardTitle>
          <CardDescription className="text-xs">
            <span className="font-mono">{leftLabel}</span>{" "}
            <ArrowRight className="inline w-3 h-3" />{" "}
            <span className="font-mono">{rightLabel}</span>
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={() => setShowUnchanged(v => !v)}>
          {showUnchanged ? "Hide unchanged" : "Show unchanged"}
        </Button>
      </CardHeader>
      <Separator />
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b bg-muted/30 text-muted-foreground">
              <th className="text-left px-3 py-2 font-medium w-24">Change</th>
              <th className="text-left px-3 py-2 font-medium">Item</th>
              <th className="text-right px-3 py-2 font-medium">Left qty</th>
              <th className="text-right px-3 py-2 font-medium">Right qty</th>
              <th className="text-right px-3 py-2 font-medium">Δ qty</th>
              <th className="text-right px-3 py-2 font-medium">Left $</th>
              <th className="text-right px-3 py-2 font-medium">Right $</th>
              <th className="text-right px-3 py-2 font-medium">Δ price</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {visible.map((r) => (
              <DiffRowView key={r.key} row={r} />
            ))}
            {visible.length === 0 && (
              <tr>
                <td colSpan={8} className="text-center py-8 text-muted-foreground italic">
                  No differences. The two runs produced identical line items.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function DiffRowView({ row }: { row: DiffRow }) {
  return (
    <tr className={cn("hover:bg-muted/20", rowTone(row.change))}>
      <td className="px-3 py-1.5">
        <ChangeBadge change={row.change} />
      </td>
      <td className="px-3 py-1.5">
        <div className="flex items-baseline gap-2 min-w-0">
          <span className="font-mono text-[11px] truncate">{row.label}</span>
          {row.section && (
            <span className="text-[10px] text-muted-foreground truncate">· {row.section}</span>
          )}
          {row.source && (
            <span className="text-[10px] uppercase text-muted-foreground/70 truncate">· {row.source}</span>
          )}
        </div>
      </td>
      <td className="px-3 py-1.5 text-right">{row.left ? `${row.left.quantity} ${row.left.unit ?? ""}` : "—"}</td>
      <td className="px-3 py-1.5 text-right">{row.right ? `${row.right.quantity} ${row.right.unit ?? ""}` : "—"}</td>
      <td className="px-3 py-1.5 text-right font-semibold">{deltaCell(row.qtyDelta)}</td>
      <td className="px-3 py-1.5 text-right">{row.left ? `$${row.left.total_price.toFixed(2)}` : "—"}</td>
      <td className="px-3 py-1.5 text-right">{row.right ? `$${row.right.total_price.toFixed(2)}` : "—"}</td>
      <td className="px-3 py-1.5 text-right font-semibold">{deltaCell(row.totalPriceDelta, true)}</td>
    </tr>
  );
}

function ChangeBadge({ change }: { change: DiffChange }) {
  const m: Record<DiffChange, { label: string; cls: string; icon: React.ElementType }> = {
    added:         { label: "Added",     cls: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30", icon: Plus },
    removed:       { label: "Removed",   cls: "bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-500/30", icon: Minus },
    qty_changed:   { label: "Qty",       cls: "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30", icon: GitCompareArrows },
    price_changed: { label: "$",         cls: "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30", icon: GitCompareArrows },
    changed:       { label: "Changed",   cls: "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30", icon: GitCompareArrows },
    unchanged:     { label: "Same",      cls: "bg-muted text-muted-foreground border-border", icon: Equal },
  };
  const Icon = m[change].icon;
  return (
    <Badge variant="outline" className={cn("gap-1 px-1.5 text-[10px]", m[change].cls)}>
      <Icon className="w-3 h-3" />
      {m[change].label}
    </Badge>
  );
}

function rowTone(change: DiffChange): string {
  switch (change) {
    case "added":   return "bg-emerald-500/[0.04]";
    case "removed": return "bg-rose-500/[0.04]";
    case "qty_changed":
    case "price_changed":
    case "changed": return "bg-amber-500/[0.04]";
    default:        return "";
  }
}

function deltaCell(delta: number | null, isMoney = false): React.ReactNode {
  if (delta == null) return <span className="text-muted-foreground">—</span>;
  if (delta === 0) return <span className="text-muted-foreground">0</span>;
  const sign = delta > 0 ? "+" : "−";
  const formatted = isMoney ? `$${Math.abs(delta).toFixed(2)}` : String(Math.abs(delta));
  return (
    <span className={delta > 0 ? "text-emerald-600" : "text-rose-600"}>
      {sign}{formatted}
    </span>
  );
}

// ─── Helpers ───────────────────────────────────────────────────────────

function parseIntOrNull(v: string | null): number | null {
  if (!v) return null;
  const n = parseInt(v, 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

// react-types shim — useEffect is imported but unused in this file's
// current shape; kept in the imports to avoid future churn.
void useEffect;
