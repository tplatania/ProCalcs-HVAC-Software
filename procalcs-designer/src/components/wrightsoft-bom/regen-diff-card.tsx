// "What changed vs the previous run" — a compact diff card shown on a
// regenerated BOM. Uses the existing diffBoms() engine and the run's
// regenerated_from_id to fetch the parent, so a reviewer sees exactly
// what a regenerate moved instead of re-scanning the whole BOM.

import { useState } from "react";
import { GitCompareArrows, ChevronDown, ChevronRight } from "lucide-react";
import { useGetBomRun, type BomResponse } from "@/lib/api-hooks";
import { diffBoms } from "@/lib/bom-diff";

export function RegenDiffCard({
  currentBom, parentRunId,
}: {
  currentBom: BomResponse;
  parentRunId: number;
}) {
  const [open, setOpen] = useState(false);
  const parent = useGetBomRun(parentRunId);
  const parentBom = (parent.data as any)?.generated_bom as BomResponse | undefined;

  if (parent.isLoading || !parentBom) return null;

  const diff = diffBoms(parentBom, currentBom);
  const s = diff.summary;
  const moved = s.addedCount + s.removedCount + s.changedCount;
  if (moved === 0) return null;

  const changedRows = diff.rows.filter((r) => r.change !== "unchanged");

  return (
    <div className="rounded-md border border-sky-300 bg-sky-50 dark:bg-sky-950/30 px-3 py-2 text-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 w-full text-left text-sky-900 dark:text-sky-200"
      >
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        <GitCompareArrows className="w-4 h-4" />
        <span className="font-semibold">Changed from run #{parentRunId}:</span>
        <span>
          {s.addedCount} added · {s.removedCount} removed · {s.changedCount} changed
        </span>
      </button>

      {open && (
        <ul className="mt-2 space-y-0.5 border-l-2 border-sky-300 pl-3">
          {changedRows.slice(0, 40).map((r, i) => {
            const label = r.label ?? r.key;
            const tag =
              r.change === "added" ? "＋ added"
              : r.change === "removed" ? "－ removed"
              : r.qtyDelta != null && r.qtyDelta !== 0
                ? `qty ${r.qtyDelta > 0 ? "+" : ""}${r.qtyDelta}`
                : "changed";
            return (
              <li key={i} className="text-xs text-sky-900/90 dark:text-sky-200/90">
                <span className="font-mono">{tag}</span> — {label}
              </li>
            );
          })}
          {changedRows.length > 40 && (
            <li className="text-xs text-muted-foreground">
              …and {changedRows.length - 40} more
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
