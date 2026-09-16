// Pricing Overrides — bulk review of one contractor's manual price corrections.
//
// Day-16. Pairs with the Pricing Import page so Richard can verify what
// actually landed without running a full BOM.

import { useState, useEffect, useMemo } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Trash2, Search } from "lucide-react";
import { Link } from "wouter";
import { useListClientProfiles, apiFetchEnvelope } from "@/lib/api-hooks";
import { useToast } from "@/hooks/use-toast";

const DEFAULT_CLIENT_ID = "procalcs-direct";

interface Override {
  id: number;
  contractor_id: string;
  supplier: string;
  sku: string;
  corrected_sku: string | null;
  corrected_supplier: string | null;
  unit_price: number | null;
  notes: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

interface OverrideListResponse {
  items: Override[];
  count: number;
}

export default function PricingOverridesPage() {
  const profiles = useListClientProfiles();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [clientId, setClientId] = useState<string>("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (clientId) return;
    const list = profiles.data ?? [];
    if (list.length === 0) return;
    const match = list.find((p) => p.id === DEFAULT_CLIENT_ID);
    setClientId(match ? DEFAULT_CLIENT_ID : list[0].id);
  }, [profiles.data, clientId]);

  const overrides = useQuery({
    queryKey: ["contractor-overrides", clientId],
    queryFn: () =>
      apiFetchEnvelope<OverrideListResponse>(
        `/api/contractor-overrides?client_id=${encodeURIComponent(clientId)}`
      ),
    enabled: !!clientId,
  });

  const deleteOne = useMutation({
    mutationFn: (id: number) =>
      apiFetchEnvelope<{ deleted_id: number }>(
        `/api/contractor-overrides/${id}`,
        { method: "DELETE" }
      ),
    onSuccess: () => {
      toast({ title: "Override deleted" });
      queryClient.invalidateQueries({ queryKey: ["contractor-overrides", clientId] });
    },
    onError: (e: any) => {
      toast({ title: "Delete failed", description: e?.message ?? "", variant: "destructive" });
    },
  });

  const filtered = useMemo(() => {
    const items = overrides.data?.items ?? [];
    if (!query.trim()) return items;
    const q = query.toLowerCase();
    return items.filter((o) =>
      o.sku.toLowerCase().includes(q) ||
      o.supplier.toLowerCase().includes(q) ||
      (o.corrected_sku ?? "").toLowerCase().includes(q) ||
      (o.notes ?? "").toLowerCase().includes(q)
    );
  }, [overrides.data, query]);

  return (
    <div className="max-w-6xl mx-auto space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Pricing Overrides</h1>
          <p className="text-muted-foreground mt-2">
            Every manual price/SKU correction for the selected contractor. These apply
            automatically on future BOM runs.
          </p>
        </div>
        <Link href="/pricing/import">
          <Button variant="outline">Import pricing →</Button>
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Browse overrides</CardTitle>
          <CardDescription>
            Pick a contractor, search by SKU / supplier / notes, delete individual rows.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Contractor</Label>
              <Select value={clientId} onValueChange={setClientId} disabled={profiles.isPending}>
                <SelectTrigger>
                  <SelectValue placeholder="Pick a contractor profile" />
                </SelectTrigger>
                <SelectContent>
                  {(profiles.data ?? []).map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name || p.id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Search</Label>
              <div className="relative">
                <Search className="w-4 h-4 absolute left-2 top-2.5 text-muted-foreground" />
                <Input
                  className="pl-8"
                  placeholder="SKU, supplier, or notes…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
            </div>
          </div>

          {overrides.isLoading ? (
            <Skeleton className="h-64 w-full rounded-md" />
          ) : !overrides.data?.count ? (
            <div className="text-sm text-muted-foreground italic py-8 text-center">
              No overrides for this contractor yet.{" "}
              <Link href="/pricing/import" className="underline">Import a pricing sheet</Link>{" "}
              to get started.
            </div>
          ) : (
            <div className="border rounded-md overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="text-left px-3 py-2 font-medium">Supplier</th>
                    <th className="text-left px-3 py-2 font-medium">SKU</th>
                    <th className="text-left px-3 py-2 font-medium">Corrected SKU</th>
                    <th className="text-left px-3 py-2 font-medium">Corrected Supplier</th>
                    <th className="text-right px-3 py-2 font-medium">Unit price</th>
                    <th className="text-left px-3 py-2 font-medium">Notes</th>
                    <th className="text-left px-3 py-2 font-medium">Updated</th>
                    <th className="px-3 py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((o) => (
                    <tr key={o.id} className="border-t hover:bg-muted/20">
                      <td className="px-3 py-2 font-mono text-[11px]">
                        <Badge variant="outline">{o.supplier}</Badge>
                      </td>
                      <td className="px-3 py-2 font-mono text-[11px]">{o.sku}</td>
                      <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground">{o.corrected_sku ?? "—"}</td>
                      <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground">{o.corrected_supplier ?? "—"}</td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {o.unit_price != null ? `$${o.unit_price.toFixed(2)}` : "—"}
                      </td>
                      <td className="px-3 py-2 max-w-[240px] truncate text-muted-foreground">{o.notes ?? "—"}</td>
                      <td className="px-3 py-2 text-xs text-muted-foreground">
                        {o.updated_at ? new Date(o.updated_at).toLocaleDateString() : "—"}
                        {o.updated_by && <div className="italic">{o.updated_by}</div>}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            if (confirm(`Delete override for ${o.supplier} / ${o.sku}?`)) {
                              deleteOne.mutate(o.id);
                            }
                          }}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filtered.length === 0 && (
                <div className="px-3 py-6 text-xs text-muted-foreground italic text-center">
                  No rows match "{query}".
                </div>
              )}
            </div>
          )}

          {overrides.data?.count != null && (
            <div className="text-xs text-muted-foreground">
              Showing {filtered.length} of {overrides.data.count} overrides for{" "}
              <code>{clientId}</code>.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
