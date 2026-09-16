// Eval Batch — run several .rup fixtures through the BOM pipeline in
// one click. Built for Richard's harness: pick the staging fixture set
// (Easy / Average / Edge), pick a contractor profile, hit Run, watch
// each row land on the run-history page in real time.
//
// Implementation notes:
//   - Files stay client-side. We don't bundle customer RUPs in the
//     SPA build; tester picks them from disk per run.
//   - Sequential execution (one parse-rup + one /generate per file at
//     a time). The BOM service shares one Anthropic key + one Postgres
//     pool — running 3 in parallel would just queue at the upstream.
//     Sequential makes the progress display honest.
//   - Each row's status is owned locally so the UI doesn't depend on
//     react-query mutation lifecycle for ordering.
//   - On completion, the run_id is hyperlinked back into the
//     run-history page so the tester can drill into reviewer state +
//     compare against a sample BOM without leaving the harness.

import { useState } from "react";
import { useLocation } from "wouter";
import {
  CheckCircle2,
  ChevronRight,
  CircleDashed,
  ExternalLink,
  FileText,
  ListChecks,
  Loader2,
  Play,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";

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
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import {
  useListClientProfiles,
  type RupDesignData,
  type BomResponse,
} from "@/lib/api-hooks";
import { useCurrentUser } from "@/lib/auth-hooks";
import { UserChip } from "@/components/user-chip";

// ─── Types ─────────────────────────────────────────────────────────────

type RowStatus = "queued" | "parsing" | "generating" | "done" | "error" | "cancelled";

interface BatchRow {
  id: string;             // local row key — file name + index
  file: File;
  status: RowStatus;
  parseMs?: number;
  generateMs?: number;
  jobId?: string;
  runId?: number;
  itemCount?: number;
  totalPrice?: number | null;
  error?: string;
}

// ─── Page ──────────────────────────────────────────────────────────────

export default function EvalBatchPage() {
  const profiles = useListClientProfiles();
  const { data: currentUser } = useCurrentUser();
  const { toast } = useToast();
  const [, setLocation] = useLocation();

  const [clientId, setClientId] = useState<string>("");
  const [rows, setRows] = useState<BatchRow[]>([]);
  const [running, setRunning] = useState(false);
  // A simple cancel flag the run loop checks between files. We don't
  // try to abort an in-flight Anthropic call (server-side latency is
  // mostly upstream); Cancel just stops the queue from advancing.
  const [cancelFlag, setCancelFlag] = useState(false);

  const addFiles = (files: FileList | null) => {
    if (!files) return;
    const next: BatchRow[] = [];
    Array.from(files).forEach((f, i) => {
      if (!/\.rup$/i.test(f.name)) {
        toast({
          title: "Skipped non-.rup file",
          description: f.name,
          variant: "destructive",
        });
        return;
      }
      next.push({ id: `${f.name}-${Date.now()}-${i}`, file: f, status: "queued" });
    });
    setRows((cur) => [...cur, ...next]);
  };

  const removeRow = (id: string) =>
    setRows((cur) => cur.filter((r) => r.id !== id));
  const clearAll = () => setRows([]);

  const updateRow = (id: string, patch: Partial<BatchRow>) =>
    setRows((cur) => cur.map((r) => (r.id === id ? { ...r, ...patch } : r)));

  const runBatch = async () => {
    if (!clientId) {
      toast({ title: "Pick a contractor profile", variant: "destructive" });
      return;
    }
    if (rows.length === 0) return;

    setRunning(true);
    setCancelFlag(false);

    // Mark everything queued at start of a new pass.
    setRows((cur) => cur.map((r) => ({ ...r, status: "queued" as RowStatus, error: undefined })));

    for (const row of rows) {
      if (cancelFlag) {
        updateRow(row.id, { status: "cancelled" });
        continue;
      }

      const jobId = `eval-${stripExt(row.file.name)}-${Date.now()}`
        .toLowerCase()
        .replace(/[^a-z0-9-]/g, "-");

      try {
        // Parse
        updateRow(row.id, { status: "parsing", jobId });
        const t0 = performance.now();
        const designData = await parseRupRequest(row.file);
        const t1 = performance.now();
        updateRow(row.id, { parseMs: Math.round(t1 - t0), status: "generating" });

        // Generate
        const bom = await generateBomRequest({
          client_id: clientId,
          job_id: jobId,
          design_data: designData,
        });
        const t2 = performance.now();
        updateRow(row.id, {
          status: "done",
          generateMs: Math.round(t2 - t1),
          runId: bom.run_id,
          itemCount: bom.item_count,
          totalPrice: bom.totals?.total_price ?? null,
        });
      } catch (err: any) {
        updateRow(row.id, {
          status: "error",
          error: err?.error ?? String(err) ?? "unknown error",
        });
      }
    }

    setRunning(false);
    toast({
      title: "Batch complete",
      description: `${rows.length} fixture${rows.length === 1 ? "" : "s"} processed.`,
    });
  };

  const summary = useMemo_doneSummary(rows);

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Play className="w-5 h-5 text-primary" />
            Eval Batch
          </h1>
          <p className="text-muted-foreground text-sm mt-1 max-w-2xl">
            Run multiple .rup fixtures through the full pipeline in one click.
            Each file is parsed and BOM-generated against the chosen contractor
            profile; results land in <span className="font-mono text-xs">bom_runs</span>{" "}
            and link straight back to <button className="underline" onClick={() => setLocation("/diagnostics/run-history")}>Run History</button>.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/30 border rounded-md px-2.5 py-1.5">
          Running as
          <UserChip email={currentUser?.email} size="md" />
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Setup</CardTitle>
          <CardDescription className="text-xs">
            Pick the contractor profile to credit each generation against, then
            queue up RUP files from disk.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-[1fr,auto] gap-3 items-end">
            <div>
              <Label className="text-xs">Contractor profile</Label>
              <Select value={clientId} onValueChange={setClientId} disabled={profiles.isPending}>
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder={profiles.isPending ? "Loading…" : "Pick a profile…"} />
                </SelectTrigger>
                <SelectContent>
                  {(profiles.data ?? []).map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name ?? p.id} ({p.id})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <label className="inline-flex items-center gap-2 px-3 py-2 text-xs font-medium border rounded-md hover:bg-muted cursor-pointer w-fit">
              <Upload className="w-3.5 h-3.5" />
              Add .rup files
              <input
                type="file"
                accept=".rup"
                multiple
                className="hidden"
                onChange={(e) => {
                  addFiles(e.target.files);
                  e.target.value = "";
                }}
              />
            </label>
          </div>
        </CardContent>
      </Card>

      {/* Queue */}
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="text-sm">Queue</CardTitle>
            <CardDescription className="text-xs">
              {rows.length === 0 ? "Empty — add at least one .rup file above." :
                `${rows.length} fixture${rows.length === 1 ? "" : "s"} queued. ${summary}`}
            </CardDescription>
          </div>
          <div className="flex gap-2">
            {rows.length > 0 && !running && (
              <Button variant="outline" size="sm" onClick={clearAll}>
                <Trash2 className="w-3.5 h-3.5 mr-1.5" />
                Clear
              </Button>
            )}
            {!running ? (
              <Button size="sm" onClick={runBatch} disabled={rows.length === 0 || !clientId}>
                <Play className="w-3.5 h-3.5 mr-1.5" />
                Run batch
              </Button>
            ) : (
              <Button variant="destructive" size="sm" onClick={() => setCancelFlag(true)}>
                <XCircle className="w-3.5 h-3.5 mr-1.5" />
                Cancel
              </Button>
            )}
          </div>
        </CardHeader>
        <Separator />
        {rows.length === 0 ? (
          <CardContent className="p-8 text-center text-sm text-muted-foreground">
            <FileText className="w-8 h-8 mx-auto text-muted-foreground/40 mb-2" />
            No fixtures queued.
          </CardContent>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b bg-muted/30 text-muted-foreground">
                  <th className="text-left px-3 py-2 font-medium">File</th>
                  <th className="text-left px-3 py-2 font-medium w-32">Status</th>
                  <th className="text-right px-3 py-2 font-medium">Parse</th>
                  <th className="text-right px-3 py-2 font-medium">Generate</th>
                  <th className="text-right px-3 py-2 font-medium">Items</th>
                  <th className="text-right px-3 py-2 font-medium">Total</th>
                  <th className="text-right px-3 py-2 font-medium">Run</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {rows.map((r) => (
                  <BatchRowView
                    key={r.id}
                    row={r}
                    onRemove={() => removeRow(r.id)}
                    canRemove={!running || r.status === "queued" || r.status === "done" || r.status === "error" || r.status === "cancelled"}
                    onOpenRun={(id) => setLocation(`/diagnostics/run-history`)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

// ─── Row view ──────────────────────────────────────────────────────────

function BatchRowView({
  row,
  onRemove,
  canRemove,
  onOpenRun,
}: {
  row: BatchRow;
  onRemove: () => void;
  canRemove: boolean;
  onOpenRun: (runId: number) => void;
}) {
  return (
    <tr className={cn("hover:bg-muted/20")}>
      <td className="px-3 py-1.5">
        <div className="flex items-center gap-2 min-w-0">
          <FileText className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
          <span className="truncate font-medium" title={row.file.name}>{row.file.name}</span>
          <span className="text-[10px] text-muted-foreground shrink-0">
            {(row.file.size / 1024).toFixed(0)} KB
          </span>
        </div>
        {row.error && (
          <p className="text-[10px] text-destructive mt-0.5 truncate" title={row.error}>
            {row.error}
          </p>
        )}
      </td>
      <td className="px-3 py-1.5"><StatusPill status={row.status} /></td>
      <td className="px-3 py-1.5 text-right text-muted-foreground">
        {row.parseMs != null ? `${row.parseMs}ms` : "—"}
      </td>
      <td className="px-3 py-1.5 text-right text-muted-foreground">
        {row.generateMs != null ? `${(row.generateMs / 1000).toFixed(1)}s` : "—"}
      </td>
      <td className="px-3 py-1.5 text-right">{row.itemCount ?? "—"}</td>
      <td className="px-3 py-1.5 text-right">
        {row.totalPrice != null ? `$${row.totalPrice.toFixed(2)}` : "—"}
      </td>
      <td className="px-3 py-1.5 text-right">
        {row.runId != null ? (
          <button
            onClick={() => onOpenRun(row.runId!)}
            className="inline-flex items-center gap-1 text-primary hover:underline"
            title="Open in Run History"
          >
            #{row.runId}
            <ExternalLink className="w-3 h-3" />
          </button>
        ) : (
          "—"
        )}
      </td>
      <td className="px-3 py-1.5 text-right">
        {canRemove && (
          <button
            onClick={onRemove}
            className="text-muted-foreground hover:text-destructive"
            title="Remove from queue"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
      </td>
    </tr>
  );
}

function StatusPill({ status }: { status: RowStatus }) {
  const m: Record<RowStatus, { label: string; cls: string; icon: React.ElementType }> = {
    queued:     { label: "Queued",     cls: "border-border text-muted-foreground", icon: CircleDashed },
    parsing:    { label: "Parsing",    cls: "border-blue-500/30 text-blue-600", icon: Loader2 },
    generating: { label: "Generating", cls: "border-blue-500/30 text-blue-600", icon: Loader2 },
    done:       { label: "Done",       cls: "border-emerald-500/30 text-emerald-600", icon: CheckCircle2 },
    error:      { label: "Error",      cls: "border-rose-500/30 text-rose-600", icon: XCircle },
    cancelled:  { label: "Cancelled",  cls: "border-border text-muted-foreground", icon: XCircle },
  };
  const Icon = m[status].icon;
  const spinning = status === "parsing" || status === "generating";
  return (
    <Badge variant="outline" className={cn("gap-1 px-2 text-[10px]", m[status].cls)}>
      <Icon className={cn("w-3 h-3", spinning && "animate-spin")} />
      {m[status].label}
    </Badge>
  );
}

// ─── Pure request helpers (mirror useParseRup / useGenerateBom but
//     callable from a sequential loop without react-query state churn) ─

async function parseRupRequest(file: File): Promise<RupDesignData> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/bom/parse-rup", { method: "POST", body: fd });
  let body: any = null;
  try { body = await res.json(); } catch { /* ignore */ }
  if (!res.ok || !body?.success) {
    throw { error: body?.error ?? `Parse failed (${res.status})`, status: res.status };
  }
  return body.data as RupDesignData;
}

async function generateBomRequest(payload: {
  client_id: string;
  job_id: string;
  design_data: RupDesignData;
  output_mode?: BomResponse["output_mode"];
}): Promise<BomResponse> {
  const res = await fetch("/api/bom/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  let body: any = null;
  try { body = await res.json(); } catch { /* ignore */ }
  if (!res.ok || !body?.success) {
    throw { error: body?.error ?? `Generate failed (${res.status})`, status: res.status };
  }
  return body.data as BomResponse;
}

function stripExt(name: string): string {
  return name.replace(/\.[^.]+$/, "");
}

// Tiny memo helper for the CardDescription summary — split out so the
// dependency array is obvious.
function useMemo_doneSummary(rows: BatchRow[]): string {
  const done = rows.filter((r) => r.status === "done").length;
  const err  = rows.filter((r) => r.status === "error").length;
  const pending = rows.length - done - err;
  if (pending === 0 && rows.length > 0) {
    return `Done: ${done} · Errors: ${err}`;
  }
  return "";
}

// Silence the linter on the icons we wired in but don't currently render.
void ChevronRight;
void ListChecks;
