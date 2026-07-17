// Regression Suites — list every distinct tag across bom_runs and let
// the tester one-click re-run the whole suite. The procalcs-bom Phase
// 9 endpoint walks each member, calls bom_service.generate against
// the parent's stored design_data, and inherits the suite tag onto
// the new child rows so the suite stays self-curating.
//
// Build a suite: open any run on /diagnostics/run-history and add
// a tag in the Tags card.
//
// Run a suite: come here, click "Run suite". Sync-blocking (15s × N
// members); UI shows a single spinner + per-member outcome card when
// done. Background-jobs is a Phase 11 stretch.

import { useState } from "react";
import { useLocation } from "wouter";
import { useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  ExternalLink,
  Loader2,
  Play,
  RefreshCw,
  Tag,
  XCircle,
  ListChecks,
  AlertTriangle,
} from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { UserChip } from "@/components/user-chip";
import {
  useListBomRunTags,
  useRunRegressionSuite,
  type SuiteRunReport,
  type SuiteRunMember,
  type TagCount,
} from "@/lib/api-hooks";

type ResultState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "done"; report: SuiteRunReport }
  | { kind: "error"; message: string };

export default function RegressionSuitesPage() {
  const [, setLocation] = useLocation();
  const tags = useListBomRunTags();
  const run = useRunRegressionSuite();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  // Per-suite result state, keyed by tag — keeps one suite's outcome
  // around while the tester runs another.
  const [results, setResults] = useState<Record<string, ResultState>>({});

  const runSuite = (tag: string) => {
    setResults((cur) => ({ ...cur, [tag]: { kind: "running" } }));
    run.mutate(
      { tag },
      {
        onSuccess: (report) => {
          setResults((cur) => ({ ...cur, [tag]: { kind: "done", report } }));
          toast({
            title: `Suite '${tag}' complete`,
            description: `${report.summary.ok}/${report.summary.total} regenerated successfully.`,
          });
          // The new child runs land on bom_runs — refresh the lists
          // so the user sees them when they navigate over.
          queryClient.invalidateQueries({ queryKey: ["bom-runs"] });
          tags.refetch();
        },
        onError: (err) => {
          const msg = err?.error ?? "unknown error";
          setResults((cur) => ({ ...cur, [tag]: { kind: "error", message: msg } }));
          toast({ title: "Suite run failed", description: msg, variant: "destructive" });
        },
      },
    );
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <ListChecks className="w-5 h-5 text-primary" />
            Regression Suites
          </h1>
          <p className="text-muted-foreground text-sm mt-1 max-w-2xl">
            One row per distinct tag across <span className="font-mono text-xs">bom_runs</span>.
            Click <strong>Run suite</strong> to regenerate every member against the current
            BOM service — children inherit the suite tag, so the suite stays self-curating.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => tags.refetch()} disabled={tags.isFetching}>
          {tags.isFetching ? (
            <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
          ) : (
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
          )}
          Refresh
        </Button>
      </div>

      {tags.isPending && (
        <Card>
          <CardContent className="p-8 flex justify-center">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </CardContent>
        </Card>
      )}

      {tags.error && (
        <Card>
          <CardContent className="p-4 text-sm text-destructive">
            Failed to load tags: {(tags.error as any)?.error ?? "unknown error"}
          </CardContent>
        </Card>
      )}

      {tags.data && tags.data.tags.length === 0 && (
        <Card>
          <CardContent className="p-8 text-center space-y-3">
            <Tag className="w-8 h-8 mx-auto text-muted-foreground/40" />
            <div>
              <p className="text-sm font-medium">No tags yet.</p>
              <p className="text-xs text-muted-foreground mt-1">
                Open any run in{" "}
                <button className="underline" onClick={() => setLocation("/diagnostics/run-history")}>
                  Run History
                </button>{" "}
                and add a tag (e.g. <span className="font-mono">regression-v1</span>) to start a suite.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {tags.data && tags.data.tags.length > 0 && (
        <div className="space-y-3">
          {tags.data.tags.map((t) => (
            <SuiteRow
              key={t.tag}
              tag={t}
              state={results[t.tag] ?? { kind: "idle" }}
              onRun={() => runSuite(t.tag)}
              onOpenList={() =>
                setLocation(`/diagnostics/run-history?tag=${encodeURIComponent(t.tag)}`)
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Per-suite row ─────────────────────────────────────────────────────

function SuiteRow({
  tag,
  state,
  onRun,
  onOpenList,
}: {
  tag: TagCount;
  state: ResultState;
  onRun: () => void;
  onOpenList: () => void;
}) {
  const running = state.kind === "running";
  return (
    <Card>
      <CardHeader className="py-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Tag className="w-4 h-4 text-muted-foreground" />
            <CardTitle className="text-sm font-mono">{tag.tag}</CardTitle>
            <Badge variant="secondary" className="text-[10px]">{tag.count} members</Badge>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={onOpenList}>
              View members
            </Button>
            <Button size="sm" onClick={onRun} disabled={running}>
              {running ? (
                <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              ) : (
                <Play className="w-3.5 h-3.5 mr-1.5" />
              )}
              {running ? "Running…" : "Run suite"}
            </Button>
          </div>
        </div>
      </CardHeader>
      {state.kind !== "idle" && (
        <>
          <Separator />
          <CardContent className="p-4 space-y-3">
            {state.kind === "running" && (
              <p className="text-xs text-muted-foreground">
                Regenerating {tag.count} member{tag.count === 1 ? "" : "s"} —
                ~10–20s per RUP. Don't navigate away.
              </p>
            )}
            {state.kind === "error" && (
              <div className="text-sm text-destructive flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{state.message}</span>
              </div>
            )}
            {state.kind === "done" && <SuiteResult report={state.report} />}
          </CardContent>
        </>
      )}
    </Card>
  );
}

function SuiteResult({ report }: { report: SuiteRunReport }) {
  const [, setLocation] = useLocation();
  const okPct = report.summary.total === 0
    ? 0
    : (report.summary.ok / report.summary.total) * 100;
  const regressions = report.summary.regressions ?? 0;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant="outline" className="border-emerald-500/30 text-emerald-700 dark:text-emerald-400">
          <CheckCircle2 className="w-3 h-3 mr-1" />
          {report.summary.ok} ok
        </Badge>
        {report.summary.errors > 0 && (
          <Badge variant="outline" className="border-rose-500/30 text-rose-700 dark:text-rose-400">
            <XCircle className="w-3 h-3 mr-1" />
            {report.summary.errors} errors
          </Badge>
        )}
        {regressions > 0 && (
          <Badge variant="outline" className="border-amber-500/40 text-amber-700 dark:text-amber-400">
            <AlertTriangle className="w-3 h-3 mr-1" />
            {regressions} regression{regressions === 1 ? "" : "s"}
          </Badge>
        )}
        <span className="text-muted-foreground">{okPct.toFixed(0)}% success</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b bg-muted/30 text-muted-foreground">
              <th className="text-left px-3 py-2 font-medium">Parent</th>
              <th className="text-left px-3 py-2 font-medium">Status</th>
              <th className="text-right px-3 py-2 font-medium">Items</th>
              <th className="text-left px-3 py-2 font-medium">Drift</th>
              <th className="text-right px-3 py-2 font-medium">Δ price</th>
              <th className="text-right px-3 py-2 font-medium">Child</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {report.members.map((m) => (
              <tr
                key={m.parent_id}
                className={cn(
                  "hover:bg-muted/20",
                  m.status === "error" && "bg-rose-500/[0.04]",
                  m.regression_detected && "bg-amber-500/[0.04]",
                )}
              >
                <td className="px-3 py-1.5">
                  <div className="font-mono text-[11px]">#{m.parent_id}</div>
                  <div className="text-muted-foreground text-[10px] truncate max-w-[260px]">{m.parent_job}</div>
                  <div className="mt-0.5">
                    <UserChip email={m.parent_created_by_email} />
                  </div>
                </td>
                <td className="px-3 py-1.5">
                  {m.status === "ok" ? (
                    m.regression_detected ? (
                      <Badge variant="outline" className="border-amber-500/40 text-amber-700 dark:text-amber-400 text-[10px]">
                        <AlertTriangle className="w-3 h-3 mr-1" />
                        regression
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="border-emerald-500/30 text-emerald-700 dark:text-emerald-400 text-[10px]">
                        ok
                      </Badge>
                    )
                  ) : (
                    <Badge variant="outline" className="border-rose-500/30 text-rose-700 dark:text-rose-400 text-[10px]" title={m.error ?? undefined}>
                      error
                    </Badge>
                  )}
                  {m.error && (
                    <div className="text-[10px] text-destructive truncate max-w-[260px]" title={m.error}>
                      {m.error}
                    </div>
                  )}
                </td>
                <td className="px-3 py-1.5 text-right">{m.item_count ?? "—"}</td>
                <td className="px-3 py-1.5 text-[10px] text-muted-foreground">
                  {m.diff ? (
                    <DriftCell d={m.diff} />
                  ) : "—"}
                </td>
                <td className="px-3 py-1.5 text-right text-[10px]">
                  {m.diff ? formatDelta(m.diff.total_price_delta, true) : "—"}
                </td>
                <td className="px-3 py-1.5 text-right">
                  {m.child_id != null ? (
                    <button
                      className="inline-flex items-center gap-1 text-primary hover:underline"
                      onClick={() =>
                        setLocation(
                          `/diagnostics/run-diff?left=${m.parent_id}&right=${m.child_id}`,
                        )
                      }
                      title="Open Run Diff: parent vs child"
                    >
                      #{m.child_id}
                      <ExternalLink className="w-3 h-3" />
                    </button>
                  ) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DriftCell({ d }: { d: NonNullable<SuiteRunMember["diff"]> }) {
  const parts: string[] = [];
  if (d.added)   parts.push(`+${d.added}`);
  if (d.removed) parts.push(`-${d.removed}`);
  if (d.changed) parts.push(`Δ${d.changed}`);
  if (parts.length === 0) return <span className="italic">no drift</span>;
  return (
    <span className="font-mono">
      {parts.join(" · ")}{" "}
      <span className="text-muted-foreground/70">({d.unchanged} same)</span>
    </span>
  );
}

function formatDelta(n: number, isMoney = false): React.ReactNode {
  if (n === 0) return <span className="text-muted-foreground">0</span>;
  const sign = n > 0 ? "+" : "−";
  const v = isMoney ? `$${Math.abs(n).toFixed(2)}` : String(Math.abs(n));
  return (
    <span className={n > 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}>
      {sign}{v}
    </span>
  );
}
