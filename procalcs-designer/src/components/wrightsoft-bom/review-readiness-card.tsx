// Review-readiness card — surfaces the confidence & materiality review
// summary the engine computes (services/review_confidence.py). Shows the
// reviewer exactly which flagged lines to check first: low-confidence or
// high-dollar, riskiest first — the 2026 professional-takeoff pattern.

import { useState } from "react";
import { ShieldAlert, ChevronDown, ChevronRight } from "lucide-react";

interface PriorityLine {
  sku?: string;
  description?: string;
  confidence: "low" | "medium" | "high";
  materiality: number;
  high_dollar: boolean;
  reason?: string;
}
export interface ReviewSummary {
  flagged_count: number;
  by_confidence: { low: number; medium: number; high: number };
  flagged_value: number;
  bom_total: number;
  high_dollar_threshold: number;
  priority_count: number;
  priority_lines: PriorityLine[];
}

const CONF_CLS: Record<string, string> = {
  low:    "text-rose-700 dark:text-rose-300",
  medium: "text-amber-700 dark:text-amber-300",
  high:   "text-emerald-700 dark:text-emerald-300",
};
const money = (n: number) =>
  n >= 0 ? `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "—";

export function ReviewReadinessCard({ summary }: { summary?: ReviewSummary }) {
  const [open, setOpen] = useState(false);
  if (!summary || summary.flagged_count === 0) return null;

  const { by_confidence: bc, priority_count, priority_lines } = summary;

  return (
    <div className="rounded-md border border-amber-400 bg-amber-50 dark:bg-amber-950/30 px-3 py-2 text-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 w-full text-left text-amber-900 dark:text-amber-200"
      >
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        <ShieldAlert className="w-4 h-4" />
        <span className="font-semibold">
          {priority_count} line{priority_count === 1 ? "" : "s"} to review
        </span>
        <span className="text-amber-800/80 dark:text-amber-200/70">
          {bc.low ? `${bc.low} low-confidence` : ""}
          {bc.low && summary.flagged_value ? " · " : ""}
          {summary.flagged_value ? `${money(summary.flagged_value)} flagged` : ""}
        </span>
      </button>

      {open && (
        <div className="mt-2 space-y-1.5">
          <div className="text-xs text-amber-800/80 dark:text-amber-200/70">
            Priority = low-confidence or high-dollar (≥ {money(summary.high_dollar_threshold)}),
            riskiest first. Confidence is the engine's certainty the line is right;
            you own the final number.
          </div>
          <ul className="space-y-1 border-l-2 border-amber-300 pl-3">
            {priority_lines.map((p, i) => (
              <li key={i} className="text-xs">
                <span className={`font-semibold ${CONF_CLS[p.confidence] ?? ""}`}>
                  {p.confidence}
                </span>
                {p.high_dollar && (
                  <span className="text-amber-900 dark:text-amber-200"> · {money(p.materiality)}</span>
                )}
                {" — "}
                <span className="font-mono">{p.sku ?? "(line)"}</span>
                {p.description ? <span className="text-muted-foreground"> {p.description}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
