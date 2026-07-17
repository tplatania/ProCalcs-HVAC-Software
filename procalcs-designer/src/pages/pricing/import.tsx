// Pricing Import — bulk-upload contractor pricing sheets.
//
// Day-16. Round-trip from "contractor emails Excel" to "future BOMs
// price correctly" in one upload. POSTs to
// /api/v1/contractor-overrides/import via the bom proxy.

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Loader2, Upload, Download, CheckCircle2, AlertTriangle } from "lucide-react";
import { useListClientProfiles } from "@/lib/api-hooks";

const TEMPLATE_CSV = `supplier,sku,unit_price,corrected_sku,corrected_supplier,notes
GOOD,AHVE24BP1300A,2875.00,,,Q1 2026 pricing
CARR,25HBC518AP0300,4150.50,,,
`;

const DEFAULT_CLIENT_ID = "procalcs-direct";

interface ImportResult {
  client_id: string;
  inserted: number;
  updated: number;
  skipped: number;
  total_seen: number;
  errors: { row: number; reason: string }[];
}

export default function PricingImportPage() {
  const profiles = useListClientProfiles();
  const [clientId, setClientId] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Default to ProCalcs Direct when the list lands.
  useEffect(() => {
    if (clientId) return;
    const list = profiles.data ?? [];
    if (list.length === 0) return;
    const match = list.find((p) => p.id === DEFAULT_CLIENT_ID);
    setClientId(match ? DEFAULT_CLIENT_ID : list[0].id);
  }, [profiles.data, clientId]);

  const downloadTemplate = () => {
    const blob = new Blob([TEMPLATE_CSV], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "pricing-template.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const submit = async () => {
    if (!file || !clientId) return;
    setRunning(true); setError(null); setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("client_id", clientId);
      const res = await fetch("/api/contractor-overrides/import", {
        method: "POST", body: fd,
      });
      let body: any = null;
      try { body = await res.json(); } catch { /* ignore */ }
      if (!res.ok || !body?.success) {
        throw new Error(body?.error ?? `Request failed (${res.status})`);
      }
      setResult(body.data as ImportResult);
    } catch (e: any) {
      setError(e?.message ?? "Unknown error");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Pricing Import</h1>
        <p className="text-muted-foreground mt-2">
          Bulk-upload a contractor's pricing sheet. Each row becomes a per-contractor
          override that future BOMs apply automatically.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Upload pricing sheet</CardTitle>
          <CardDescription>
            CSV or XLSX. Required columns: <code className="text-xs">supplier</code>,{" "}
            <code className="text-xs">sku</code>, and at least one of{" "}
            <code className="text-xs">unit_price</code> / <code className="text-xs">corrected_sku</code> /{" "}
            <code className="text-xs">corrected_supplier</code> / <code className="text-xs">notes</code>.
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
              <Label>File</Label>
              <input
                type="file"
                accept=".csv,.xls,.xlsx"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="block w-full text-sm file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:bg-primary file:text-primary-foreground hover:file:bg-primary/90"
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={submit} disabled={!file || !clientId || running}>
              {running ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Upload className="w-4 h-4 mr-2" />}
              Import pricing
            </Button>
            <Button variant="outline" onClick={downloadTemplate}>
              <Download className="w-4 h-4 mr-2" />
              Download template
            </Button>
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertTriangle className="w-4 h-4" />
              <AlertTitle>Upload failed</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {result && (
            <Alert>
              <CheckCircle2 className="w-4 h-4" />
              <AlertTitle>
                Import complete — {result.inserted} added, {result.updated} updated, {result.skipped} skipped
              </AlertTitle>
              <AlertDescription className="mt-2 space-y-2">
                <div className="text-xs text-muted-foreground">
                  Contractor: <code>{result.client_id}</code> · {result.total_seen} rows seen
                </div>
                {result.errors.length > 0 && (
                  <div>
                    <div className="text-xs font-medium mt-2">Skipped rows:</div>
                    <ul className="text-xs space-y-0.5 mt-1 max-h-48 overflow-y-auto">
                      {result.errors.map((e, i) => (
                        <li key={i}>
                          Row {e.row}: <span className="text-muted-foreground">{e.reason}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
