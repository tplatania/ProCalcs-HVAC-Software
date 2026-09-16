// Browse BOMs — BREAD "Browse". Lists previously generated BOMs; each
// opens the hydrated canvas (tables + edits + sniping + chat + regen).
// Day-28.

import { useState } from "react";
import { useLocation } from "wouter";
import { useQueryClient } from "@tanstack/react-query";
import { useListBomRuns } from "@/lib/api-hooks";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ListChecks, PackagePlus, Trash2, Loader2, ChevronRight } from "lucide-react";

const STATUS_STYLE: Record<string, string> = {
  good:      "text-emerald-700 border-emerald-300 bg-emerald-50",
  needs_fix: "text-amber-700 border-amber-300 bg-amber-50",
  blocked:   "text-rose-700 border-rose-300 bg-rose-50",
  unset:     "text-muted-foreground",
};

export default function BrowseBomsPage() {
  const [, setLocation] = useLocation();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const list = useListBomRuns({ q: q.trim() || undefined, limit: 100 });
  const runs = list.data?.runs ?? [];

  const del = async (id: number) => {
    if (!window.confirm("Delete this BOM and its chat history? This cannot be undone.")) return;
    setDeletingId(id);
    try {
      const res = await fetch(`/api/bom-runs/${id}`, {
        method: "DELETE", credentials: "same-origin",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await qc.invalidateQueries({ queryKey: ["bom-runs"] });
    } catch {
      /* surfaced by the row staying; keep it simple */
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-6 max-w-[1100px] mx-auto">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <ListChecks className="w-5 h-5 text-primary" /> Browse BOMs
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Every BOM you've generated. Open one to review, edit, chat, and
            regenerate — your conversation and corrections are restored.
          </p>
        </div>
        <Button onClick={() => setLocation("/bom-tool/new")} className="gap-2">
          <PackagePlus className="w-4 h-4" /> Generate New BOM
        </Button>
      </div>

      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-sm flex items-center justify-between gap-3">
            <span>BOMs {list.data ? `(${list.data.total})` : ""}</span>
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Filter by job id or email…"
              className="h-8 max-w-xs text-xs"
            />
          </CardTitle>
          <CardDescription className="text-xs">
            Showing {runs.length} most recent. Click a row to open the canvas.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {list.isLoading && (
            <div className="flex items-center gap-2 px-4 py-8 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading…
            </div>
          )}
          {!list.isLoading && runs.length === 0 && (
            <div className="px-4 py-10 text-center text-sm text-muted-foreground">
              No BOMs yet. <button className="underline"
                onClick={() => setLocation("/bom-tool/new")}>Generate your first one</button>.
            </div>
          )}
          <ul className="divide-y divide-border/60">
            {runs.map((r) => (
              <li key={r.id}
                  className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/30 cursor-pointer group"
                  onClick={() => setLocation(`/bom-tool/bom/${r.id}`)}>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">
                    {r.job_id || `BOM #${r.id}`}
                  </div>
                  <div className="text-[11px] text-muted-foreground flex items-center gap-2 flex-wrap">
                    <span>{new Date(r.created_at).toLocaleString()}</span>
                    <span>·</span>
                    <span>{r.created_by_email ?? "—"}</span>
                    {r.item_count != null && <><span>·</span><span>{r.item_count} items</span></>}
                    {r.total_price != null && <><span>·</span><span>${r.total_price.toFixed(2)}</span></>}
                    {r.regenerated_from_id != null && (
                      <Badge variant="outline" className="text-[9px] py-0">regenerated</Badge>
                    )}
                  </div>
                </div>
                <Badge variant="outline"
                       className={`text-[10px] shrink-0 ${STATUS_STYLE[r.reviewer_status] ?? ""}`}>
                  {r.reviewer_status}
                </Badge>
                <Button variant="ghost" size="icon"
                        className="h-7 w-7 shrink-0 opacity-0 group-hover:opacity-100 text-destructive"
                        onClick={(e) => { e.stopPropagation(); del(r.id); }}
                        disabled={deletingId === r.id}
                        title="Delete BOM">
                  {deletingId === r.id
                    ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    : <Trash2 className="w-3.5 h-3.5" />}
                </Button>
                <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
