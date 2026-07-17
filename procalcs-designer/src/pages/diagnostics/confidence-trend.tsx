// Confidence Trend — read-only sparkline view of how the testing
// harness has been doing over time. Pulls the most recent N runs
// from /api/bom-runs and plots:
//
//   1. Items per run (total) coloured by reviewer_status — quick eye
//      check for "did the prompt regress and start emitting fewer
//      lines?".
//   2. Stacked catalog / rules / AI breakdown per run — shows whether
//      the catalog is taking on more of the load over time as
//      Richard's team encodes more SKUs.
//
// Static, read-only diagnostic. No interaction beyond the limit
// selector + filter inputs. Bigger queries fall back to the
// list endpoint's 200-row cap, which is plenty for staging.

import { useMemo, useState } from "react";
import { useLocation } from "wouter";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Activity, AlertTriangle, Loader2, RefreshCw } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useListBomRuns } from "@/lib/api-hooks";
import { UserChip } from "@/components/user-chip";

// ─── Page ──────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  unset:     "#94a3b8", // slate-400
  good:      "#10b981", // emerald-500
  needs_fix: "#f59e0b", // amber-500
  blocked:   "#ef4444", // rose-500
};

export default function ConfidenceTrendPage() {
  const [, setLocation] = useLocation();
  const [limit, setLimit] = useState<number>(50);
  const [clientFilter, setClientFilter] = useState("");

  const list = useListBomRuns({
    limit,
    client_id: clientFilter.trim() || undefined,
  });

  // Recharts wants oldest-first so the X axis reads left → right.
  const chartData = useMemo(() => {
    const rows = (list.data?.runs ?? []).slice().reverse();
    // We can't reach into the BOM payload from the summary endpoint
    // (it deliberately drops the heavy JSONB), so the catalog/rules/AI
    // breakdown isn't available here yet — we'll surface it when the
    // list endpoint grows those projections. For now the items chart
    // shows total + reviewer-status colour, which is enough to spot
    // a regression in line count or a wave of "needs_fix" rows.
    return rows.map((r) => ({
      x:               `#${r.id}`,
      label:           r.job_id,
      created_at:      r.created_at,
      items:           r.item_count ?? 0,
      total_price:     r.total_price ?? 0,
      reviewer_status: r.reviewer_status,
      created_by:      r.created_by_email ?? "—",
    }));
  }, [list.data?.runs]);

  // Roll-up stats above the charts — gives a single number for "is
  // the suite healthier than yesterday" without scrolling.
  const stats = useMemo(() => computeStats(chartData), [chartData]);

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Activity className="w-5 h-5 text-primary" />
            Confidence Trend
          </h1>
          <p className="text-muted-foreground text-sm mt-1 max-w-2xl">
            Item count + total-price trend over the most recent BOM runs,
            coloured by reviewer status. Spot regressions at a glance —
            a sudden dip in items, a spike in <span className="font-mono text-xs">needs_fix</span>{" "}
            rows, or a runaway price jump.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => list.refetch()} disabled={list.isFetching}>
          {list.isFetching ? (
            <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
          ) : (
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
          )}
          Refresh
        </Button>
      </div>

      <Card>
        <CardContent className="p-4 flex flex-wrap gap-3 items-end">
          <div className="min-w-[160px]">
            <Label className="text-xs uppercase tracking-wide text-muted-foreground">Last N runs</Label>
            <Select value={String(limit)} onValueChange={(v) => setLimit(Number(v))}>
              <SelectTrigger className="mt-1 h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[20, 50, 100, 200].map((n) => (
                  <SelectItem key={n} value={String(n)}>{n}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-[200px]">
            <Label className="text-xs uppercase tracking-wide text-muted-foreground">Client ID</Label>
            <Input
              value={clientFilter}
              onChange={(e) => setClientFilter(e.target.value)}
              placeholder="exact match"
              className="h-9 mt-1"
            />
          </div>
        </CardContent>
      </Card>

      {list.error && (
        <Card>
          <CardContent className="p-4 text-sm text-destructive flex gap-2 items-start">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            Failed to load runs: {(list.error as any)?.error ?? "unknown error"}
          </CardContent>
        </Card>
      )}

      {/* Roll-up stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatBlock label="Runs" value={String(stats.runs)} />
        <StatBlock label="Avg items" value={stats.avgItems.toFixed(1)} />
        <StatBlock label="Avg price" value={`$${stats.avgPrice.toFixed(2)}`} />
        <StatBlock
          label="Reviewer mix"
          value={
            <span className="flex gap-1.5 text-xs">
              {Object.entries(stats.statusCounts).map(([k, v]) => (
                <span key={k} className="inline-flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full" style={{ background: STATUS_COLORS[k] || "#888" }} />
                  {v}
                </span>
              ))}
            </span>
          }
        />
        <StatBlock
          label="Top contributors"
          value={
            <span className="flex flex-wrap gap-1.5 text-xs">
              {Object.entries(stats.userCounts)
                .sort(([, a], [, b]) => b - a)
                .slice(0, 5)
                .map(([email, n]) => (
                  <span key={email} className="inline-flex items-center gap-1">
                    <UserChip
                      email={email === "—" ? null : email}
                      showText={false}
                    />
                    <span className="text-muted-foreground">{n}</span>
                  </span>
                ))}
            </span>
          }
        />
      </div>

      {chartData.length === 0 && !list.isPending && (
        <Card>
          <CardContent className="p-8 text-center text-sm text-muted-foreground space-y-2">
            <Activity className="w-8 h-8 mx-auto text-muted-foreground/40" />
            <p>No runs yet to chart.</p>
            <p className="text-xs">
              Generate a BOM via the{" "}
              <button className="underline" onClick={() => setLocation("/bom-engine")}>BOM Engine</button>{" "}
              page or use the{" "}
              <button className="underline" onClick={() => setLocation("/diagnostics/eval-batch")}>Eval Batch</button>{" "}
              runner to seed history.
            </p>
          </CardContent>
        </Card>
      )}

      {chartData.length > 0 && (
        <>
          <Card>
            <CardHeader className="py-3">
              <CardTitle className="text-sm">Items per run</CardTitle>
              <CardDescription className="text-xs">
                Bar colour = reviewer status. Sudden drop = parser or rules-engine regression.
              </CardDescription>
            </CardHeader>
            <CardContent className="h-[280px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 10, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                  <XAxis dataKey="x" fontSize={10} stroke="hsl(var(--muted-foreground))" />
                  <YAxis fontSize={10} stroke="hsl(var(--muted-foreground))" />
                  <Tooltip
                    contentStyle={{
                      background: "hsl(var(--popover))",
                      border: "1px solid hsl(var(--border))",
                      fontSize: 11,
                      borderRadius: 6,
                    }}
                    formatter={(v: any, _k: any, p: any) => [v, p?.payload?.label]}
                    labelFormatter={(_l, payload) => {
                      const p: any = payload?.[0]?.payload;
                      if (!p) return "";
                      return `${p.x} · ${formatDate(p.created_at)} · ${p.reviewer_status} · by ${p.created_by}`;
                    }}
                  />
                  <Bar dataKey="items" name="Items">
                    {chartData.map((d, i) => (
                      <Cell
                        key={i}
                        fill={STATUS_COLORS[d.reviewer_status] || STATUS_COLORS.unset}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="py-3">
              <CardTitle className="text-sm">Total price per run</CardTitle>
              <CardDescription className="text-xs">
                Watch for unexplained jumps — usually indicates a markup or
                catalog-default change.
              </CardDescription>
            </CardHeader>
            <CardContent className="h-[260px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 10, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                  <XAxis dataKey="x" fontSize={10} stroke="hsl(var(--muted-foreground))" />
                  <YAxis fontSize={10} stroke="hsl(var(--muted-foreground))" tickFormatter={(v) => `$${v}`} />
                  <Tooltip
                    contentStyle={{
                      background: "hsl(var(--popover))",
                      border: "1px solid hsl(var(--border))",
                      fontSize: 11,
                      borderRadius: 6,
                    }}
                    formatter={(v: any) => [`$${Number(v).toFixed(2)}`, "Total"]}
                  />
                  <Legend wrapperStyle={{ fontSize: 10 }} />
                  <Line
                    type="monotone"
                    dataKey="total_price"
                    name="Total price"
                    stroke="hsl(var(--primary))"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

// ─── Helpers ───────────────────────────────────────────────────────────

function StatBlock({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="p-3 space-y-0.5">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
        <div className="text-lg font-bold leading-tight">{value}</div>
      </CardContent>
    </Card>
  );
}

function computeStats(rows: {
  items: number;
  total_price: number;
  reviewer_status: string;
  created_by: string;
}[]) {
  if (rows.length === 0) {
    return {
      runs: 0, avgItems: 0, avgPrice: 0,
      statusCounts: {} as Record<string, number>,
      userCounts:   {} as Record<string, number>,
    };
  }
  const items = rows.reduce((s, r) => s + r.items, 0) / rows.length;
  const price = rows.reduce((s, r) => s + r.total_price, 0) / rows.length;
  const statusCounts: Record<string, number> = {};
  const userCounts:   Record<string, number> = {};
  for (const r of rows) {
    statusCounts[r.reviewer_status] = (statusCounts[r.reviewer_status] ?? 0) + 1;
    userCounts[r.created_by]        = (userCounts[r.created_by] ?? 0) + 1;
  }
  return { runs: rows.length, avgItems: items, avgPrice: price, statusCounts, userCounts };
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
