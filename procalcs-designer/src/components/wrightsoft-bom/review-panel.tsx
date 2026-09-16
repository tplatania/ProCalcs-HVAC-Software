// Reviewer Workspace panel — mark-reviewed control + correction history.
//
// Surfaces two things the backend already tracked but the UI never
// showed: (1) the run's reviewer_status/notes (settable via the
// existing POST /api/bom-runs/:id/review), and (2) the correction
// history (patch_ops) as a readable audit timeline.

import { useState } from "react";
import { CheckCircle2, AlertTriangle, Ban, Circle, History, Loader2 } from "lucide-react";
import {
  useReviewBomRun, type ReviewerStatus, type PatchOp,
} from "@/lib/api-hooks";

const STATUS_META: Record<ReviewerStatus, { label: string; icon: any; cls: string }> = {
  unset:     { label: "Unreviewed", icon: Circle,       cls: "text-muted-foreground border-muted-foreground/30" },
  good:      { label: "Good",       icon: CheckCircle2, cls: "text-emerald-700 border-emerald-500/50 bg-emerald-50 dark:bg-emerald-950/30 dark:text-emerald-300" },
  needs_fix: { label: "Needs fix",  icon: AlertTriangle,cls: "text-amber-700 border-amber-500/50 bg-amber-50 dark:bg-amber-950/30 dark:text-amber-300" },
  blocked:   { label: "Blocked",    icon: Ban,          cls: "text-rose-700 border-rose-500/50 bg-rose-50 dark:bg-rose-950/30 dark:text-rose-300" },
};
const SETTABLE: ReviewerStatus[] = ["good", "needs_fix", "blocked"];

function describeOp(op: PatchOp): string {
  const sku = op.sku ?? "(line)";
  const f = op.fields ?? {};
  if (op.op === "remove_line") return `Removed ${sku}`;
  if (op.op === "add_line") {
    const q = f.quantity != null ? ` ×${f.quantity}` : "";
    return `Added ${sku}${q}`;
  }
  // update_line
  const bits: string[] = [];
  if (f.quantity != null) bits.push(`qty → ${f.quantity}`);
  if (f.unit_price != null) bits.push(`price → $${f.unit_price}`);
  if (f.description != null) bits.push(`description updated`);
  return `Updated ${sku}${bits.length ? " (" + bits.join(", ") + ")" : ""}`;
}

export function ReviewPanel({
  runId, initialStatus, initialNotes, patchOps,
}: {
  runId: number;
  initialStatus?: string;
  initialNotes?: string | null;
  patchOps?: PatchOp[];
}) {
  const review = useReviewBomRun();
  const [status, setStatus] = useState<ReviewerStatus>(
    (initialStatus as ReviewerStatus) || "unset");
  const [notes, setNotes] = useState(initialNotes ?? "");
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  const save = (next: ReviewerStatus) => {
    setStatus(next);
    setSavedMsg(null);
    review.mutate(
      { id: runId, status: next, notes: notes.trim() || undefined },
      {
        onSuccess: () => setSavedMsg("Saved"),
        onError: (e) => setSavedMsg(e.error || "Save failed"),
      },
    );
  };

  const ops = (patchOps ?? []).filter((o) => o && o.op);

  return (
    <div className="rounded-md border bg-card/50 p-3 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          Review
        </span>
        {SETTABLE.map((s) => {
          const m = STATUS_META[s];
          const Icon = m.icon;
          const active = status === s;
          return (
            <button
              key={s}
              type="button"
              onClick={() => save(s)}
              disabled={review.isPending}
              className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium transition
                ${active ? m.cls : "text-muted-foreground border-muted-foreground/20 hover:bg-muted"}`}
            >
              <Icon className="w-3.5 h-3.5" /> {m.label}
            </button>
          );
        })}
        {review.isPending && <Loader2 className="w-3.5 h-3.5 animate-spin text-muted-foreground" />}
        {savedMsg && !review.isPending && (
          <span className="text-xs text-muted-foreground">{savedMsg}</span>
        )}
      </div>

      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        onBlur={() => { if (status !== "unset") save(status); }}
        placeholder="Review notes (optional) — saved with the status"
        rows={2}
        className="w-full text-sm px-2 py-1.5 rounded-md border bg-background resize-y"
      />

      {ops.length > 0 && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
            <History className="w-3.5 h-3.5" />
            Correction history · {ops.length}
          </div>
          <ol className="space-y-1 border-l-2 border-muted pl-3">
            {ops.map((op, i) => (
              <li key={i} className="text-xs">
                <span className="text-foreground">{describeOp(op)}</span>
                {op.reason && (
                  <span className="text-muted-foreground"> — {op.reason}</span>
                )}
                <span className="text-muted-foreground/70">
                  {op.author ? ` · ${op.author}` : ""}
                  {op.at ? ` · ${op.at.slice(0, 16).replace("T", " ")}` : ""}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
