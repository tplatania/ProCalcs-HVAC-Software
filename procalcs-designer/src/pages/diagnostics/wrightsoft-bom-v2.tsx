// Wrightsoft BOM v2 — bundle-driven equipment enrichment (Day-19).
//
// Same UX as v1 (/diagnostics/wrightsoft-bom) with one addition:
// an "equipment_bundle" file input for the JSON produced by the
// Windows extraction station's COM ValidateProject call. When a
// bundle is attached, the SPA calls POST /api/v1/bom/from-wrightsoft-
// bundle (v2 endpoint) instead of /from-wrightsoft (v1). The bundle
// path retires the reactive .rup byte-parsing for equipment — any
// manufacturer Wrightsoft names surfaces cleanly (Mitsubishi, LG,
// Bosch, etc.), per-zone attribution is preserved, and SEER/HSPF/
// AFUE/capacity come straight from Wrightsoft without an AHRI
// catalog round-trip.
//
// v1 stays live at /diagnostics/wrightsoft-bom for the .rup-only
// path (contractors whose extraction station isn't wired yet).

import React, { useEffect, useState } from "react";
import { useLocation, Link, useSearch } from "wouter";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  FileSpreadsheet,
  Download,
  Loader2,
  Cpu,
  PackagePlus,
  Pencil,
  Upload,
  Sparkles,
  XCircle,
  GitCompareArrows,
  ShieldCheck,
  Crosshair,
} from "lucide-react";
import { EditLineDrawer, type EditableLine } from "@/components/wrightsoft-bom/edit-line-drawer";
import { BomChatSidebar, type Snipe } from "@/components/wrightsoft-bom/bom-chat-sidebar";
import { useUpsertContractorOverride } from "@/lib/api-hooks";
import { useToast } from "@/hooks/use-toast";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useListClientProfiles,
  useListBomRuns,
  useGetBomRun,
  useRenderBomPdf,
  useRenderBomXls,
  getListClientProfilesQueryKey,
  type BomResponse,
} from "@/lib/api-hooks";
import { useCurrentUser } from "@/lib/auth-hooks";
import { UserChip } from "@/components/user-chip";
import { cn } from "@/lib/utils";


// ─── Page ──────────────────────────────────────────────────────────

// Default contractor — applied on first load when this profile exists
// in the list. Lets reviewers click "Build BOM" without first hunting
// the dropdown for the contractor 99% of staging runs use anyway.
// Day-26 — Richard's team is the pilot user group, so their profile
// is the default. Falls back to the first profile if it's absent.
const DEFAULT_CLIENT_ID = "reliable-heating-and-cooling";

// Cross-tab signal — the profile-detail page posts a "profiles-updated"
// message after a successful save. Other open tabs (like this one)
// listen and refresh the client-profiles cache so the dropdown reflects
// edits without a manual reload.
const PROFILES_CHANNEL = "procalcs-profiles";

/** Day-26 — replay run-scoped patch ops (chat corrections) over a
 * stored generated_bom so a reloaded permalink shows the corrected
 * BOM, not the original. Mirrors the optimistic in-session logic. */
function applyPatchOps(bom: any, ops: any[] | null | undefined): any {
  if (!Array.isArray(ops) || ops.length === 0) return bom;
  const items = ((bom?.line_items as any[]) ?? []).map((li) => ({ ...li }));
  for (const op of ops) {
    const idx = items.findIndex(
      (li) => (li.sku ?? li.generic_id) === op.sku);
    if (op.op === "remove_line") {
      if (idx >= 0) items.splice(idx, 1);
    } else if (op.op === "add_line") {
      const f = op.fields ?? {};
      const qty = f.quantity ?? 1;
      const price = f.unit_price ?? 0;
      items.push({
        generic_id: op.sku, sku: op.sku,
        description: f.description ?? op.sku,
        quantity: qty, unit: "ea",
        unit_cost: price, unit_price: price,
        total_price: Math.round(price * qty * 100) / 100,
        source: "wrightsoft_manual", section: f.section ?? "Other",
        patched: true,
      });
    } else if (op.op === "update_line" && idx >= 0) {
      const f = op.fields ?? {};
      const li = { ...items[idx], patched: true };
      if (f.quantity != null) {
        li.quantity = f.quantity;
        const unit = li.unit_price ?? li.unit_cost ?? 0;
        li.total_price = Math.round(unit * f.quantity * 100) / 100;
      }
      if (f.description != null) li.description = f.description;
      items[idx] = li;
    }
  }
  return { ...bom, line_items: items, item_count: items.length };
}

export default function WrightsoftBomV2Page() {
  const [, setLocation] = useLocation();
  const profiles = useListClientProfiles();
  const { data: currentUser } = useCurrentUser();
  const queryClient = useQueryClient();

  const [clientId, setClientId] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  // Day-16 follow-up — optional second .rup file co-uploaded alongside
  // the canonical .xls to add room/duct-system context the .xls strips.
  const [rupContextFile, setRupContextFile] = useState<File | null>(null);
  // Day-19 — v2: equipment bundle from the Windows extraction station
  // (ValidateProject JSON). When present, switches to /from-wrightsoft-
  // bundle so equipment lines come from Wrightsoft's COM output rather
  // than the .rup byte-parser. Optional project_name for multi-project
  // bundles.
  const [equipmentBundleFile, setEquipmentBundleFile] = useState<File | null>(null);
  const [bundleProjectName, setBundleProjectName] = useState<string>("");
  const [jobId, setJobId] = useState<string>("");

  // Day-15 — the selected profile's brand color drives the contractor-
  // specific accent in the result view (badge edges, banner stripe).
  // Falls back to the default ProCalcs orange when the profile has no
  // override set.
  const selectedProfile = (profiles.data ?? []).find((p) => p.id === clientId);
  const brandColor = selectedProfile?.brandColor || "#f97316";

  // Pre-select the default contractor once the profiles list lands,
  // but only if the user hasn't picked something else yet.
  useEffect(() => {
    if (clientId) return;
    const list = profiles.data ?? [];
    if (list.length === 0) return;
    const match = list.find((p) => p.id === DEFAULT_CLIENT_ID);
    setClientId(match ? DEFAULT_CLIENT_ID : list[0].id);
  }, [profiles.data, clientId]);

  // Listen for cross-tab edits so the dropdown reflects profile changes
  // made in another tab without forcing a page reload here.
  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const ch = new BroadcastChannel(PROFILES_CHANNEL);
    ch.onmessage = (msg) => {
      if (msg?.data?.type === "profiles-updated") {
        queryClient.invalidateQueries({ queryKey: getListClientProfilesQueryKey() });
      }
    };
    return () => ch.close();
  }, [queryClient]);

  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BomResponse | null>(null);
  // Chat-panel width handoff — content reflows instead of being covered.
  const [chatOpen, setChatOpen] = useState(false);

  // Day-17 — refresh-survivability via ?run=<id> URL param.
  // On mount (or whenever the URL changes), if ?run= is present we
  // hydrate the result from the persisted bom_runs row. After every
  // successful build we push the new id to the URL so refresh
  // restores the same result, browser-back works, and the URL is
  // shareable in Slack/email.
  const searchString = useSearch();
  const urlRunId = (() => {
    try {
      const sp = new URLSearchParams(searchString);
      const raw = sp.get("run");
      const n = raw ? parseInt(raw, 10) : NaN;
      return Number.isFinite(n) && n > 0 ? n : null;
    } catch { return null; }
  })();
  const persistedRun = useGetBomRun(urlRunId);
  // Hydrate `result` once the bom_run query lands (only when there's
  // no in-flight build result and the run_id in URL changed). Lets
  // the existing edit drawer + inline-price + run-diff flows work
  // unchanged on a permalinked result.
  useEffect(() => {
    if (!urlRunId) return;
    const data: any = persistedRun.data;
    const gen = data?.generated_bom;
    if (gen && (result === null || (result as any).run_id !== urlRunId)) {
      // Day-26 — re-apply run-scoped patches on rehydrate, otherwise a
      // reload silently shows the pre-correction BOM.
      const patched = applyPatchOps(gen, data?.patch_ops);
      setResult({ ...patched, run_id: data.id ?? urlRunId } as any);
      if (data?.client_id && !clientId) setClientId(data.client_id);
      if (data?.job_id && !jobId)       setJobId(data.job_id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlRunId, persistedRun.data]);

  const onPickFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    e.target.value = "";
    setFile(f);
    setResult(null);
    setError(null);
    // Day-17 — drop ?run=<old> so picking a new file doesn't rehydrate
    // the previous result mid-edit.
    if (typeof window !== "undefined") {
      try {
        const url = new URL(window.location.href);
        if (url.searchParams.has("run")) {
          url.searchParams.delete("run");
          window.history.replaceState({}, "", url.toString());
        }
      } catch { /* ignore */ }
    }
    if (f && !jobId) {
      // Default job_id from filename + timestamp so the run is
      // self-identifying in Run History without forcing manual entry
      const stem = f.name.replace(/\.[^.]+$/, "")
                          .toLowerCase()
                          .replace(/[^a-z0-9-]+/g, "-")
                          .replace(/^-+|-+$/g, "");
      setJobId(`wrightsoft-${stem}-${Date.now()}`);
    }
  };

  const submit = async () => {
    if (!file)     { setError("Pick a BOM file first."); return; }
    if (!clientId) { setError("Pick a contractor profile."); return; }
    if (!jobId)    { setError("Job ID is required."); return; }
    setRunning(true); setError(null); setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("client_id", clientId);
      fd.append("job_id", jobId);
      // Day-16 follow-up — co-upload the source .rup when provided so
      // the response carries room/branch context the .xls doesn't have.
      if (rupContextFile) {
        fd.append("rup_context", rupContextFile);
      }
      // Day-19 — v2: when an equipment_bundle is attached, switch to
      // the /from-wrightsoft-bundle endpoint so equipment comes from
      // COM ValidateProject output instead of the .rup byte-parser.
      const useBundlePath = !!equipmentBundleFile;
      if (useBundlePath) {
        fd.append("equipment_bundle", equipmentBundleFile!);
        if (bundleProjectName) fd.append("project_name", bundleProjectName);
      }
      const res = await fetch(
        useBundlePath ? "/api/bom/from-wrightsoft-bundle" : "/api/bom/from-wrightsoft",
        { method: "POST", body: fd },
      );
      let body: any = null;
      try { body = await res.json(); } catch { /* ignore */ }
      if (!res.ok || !body?.success) {
        throw new Error(body?.error ?? `Request failed (${res.status})`);
      }
      const bomData = body.data as BomResponse;
      setResult(bomData);
      // Day-17 — push ?run=<id> onto the URL so refresh survives.
      // history.replaceState avoids polluting the back stack with a
      // pre-build empty page; user can still hit back to leave the
      // result view entirely.
      const newRunId = (bomData as any)?.run_id;
      if (newRunId && typeof window !== "undefined") {
        try {
          const url = new URL(window.location.href);
          url.searchParams.set("run", String(newRunId));
          window.history.replaceState({}, "", url.toString());
        } catch { /* ignore */ }
      }
    } catch (e: any) {
      setError(e?.message ?? "Unknown error");
    } finally {
      setRunning(false);
    }
  };

  return (
    // Chat open → drop the centered 1200px cap and use the full main
    // column minus the 380px panel (+16px gutter). No dead margins.
    <div className={cn(
      "space-y-6 transition-all duration-200",
      chatOpen ? "max-w-none pr-[396px]" : "max-w-[1200px] mx-auto",
    )}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <PackagePlus className="w-5 h-5 text-primary" />
            Wrightsoft BOM v2
            <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-primary/10 text-primary">
              beta
            </span>
          </h1>
          <p className="text-muted-foreground text-sm mt-1 max-w-3xl">
            Upload Wrightsoft's own BOM output (CSV / XLS / XLSX) plus the
            optional <strong>equipment bundle</strong> from the Windows
            extraction station (COM ValidateProject JSON). Equipment lines
            come from Wrightsoft's own COM output when the bundle is present —
            richer per-zone data and covers any manufacturer, no
            reverse-engineered .rup parsing. When no bundle is attached, v2
            falls back to the v1 .xls-only behavior for line items. The
            server translates each generic part ID through{" "}
            <span className="font-mono text-xs">mapped_parts.csv</span> into
            the contractor's actual manufacturer SKU. No AI, no guessing —
            when the mapping has the part, the answer is exact; when it
            doesn't, the line is flagged so the SKU Backlog can prioritize
            what to encode next.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/30 border rounded-md px-2.5 py-1.5">
          Running as
          <UserChip email={currentUser?.email} size="md" />
        </div>
      </div>

      {/* Why-this-page banner */}
      <Card className="border-primary/30 bg-primary/[0.03]">
        <CardContent className="p-4 flex items-start gap-3 text-sm">
          <Sparkles className="w-5 h-5 text-primary mt-0.5 shrink-0" />
          <div className="space-y-1">
            <p className="font-medium">This is the recommended path for projects where you have a Wrightsoft BOM export.</p>
            <p className="text-muted-foreground text-xs">
              The alternative — the AI-driven{" "}
              <button className="underline" onClick={() => setLocation("/bom-engine")}>
                BOM Engine
              </button>{" "}
              path that takes a raw <span className="font-mono">.rup</span>{" "}
              file — is kept as a fallback for projects without a Wrightsoft
              BOM in hand, but it estimates quantities and prices. This page
              produces deterministic output.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Setup form */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Setup</CardTitle>
          <CardDescription className="text-xs">
            Pick the contractor profile (drives supplier preference +
            markup), upload the BOM file, optionally adjust the job ID.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-[1fr,1fr] gap-3">
            <div>
              <Label className="text-xs">Contractor profile</Label>
              <div className="flex gap-2 mt-1">
                <Select value={clientId} onValueChange={setClientId} disabled={profiles.isPending}>
                  <SelectTrigger className="flex-1">
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
                {/* Edit-in-new-tab. Disabled until a profile is picked
                    so we don't open a 404. Cross-tab BroadcastChannel
                    listener above refreshes the dropdown on save. */}
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  disabled={!clientId}
                  title={clientId
                    ? `Open “${clientId}” in a new tab to view or edit`
                    : "Pick a profile first"}
                  onClick={() => {
                    if (!clientId) return;
                    window.open(`/profiles/${encodeURIComponent(clientId)}`, "_blank", "noopener");
                  }}
                >
                  <Pencil className="w-4 h-4" />
                </Button>
              </div>
            </div>
            <div>
              <Label className="text-xs">Job ID</Label>
              <input
                value={jobId}
                onChange={(e) => setJobId(e.target.value)}
                placeholder="auto-filled from filename when you pick a file"
                className="mt-1 h-10 w-full px-3 rounded-md border bg-background text-sm"
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-3 items-center">
            <label className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium border rounded-md hover:bg-muted cursor-pointer">
              <Upload className="w-4 h-4" />
              {file ? "Replace file" : "Pick file (.rup / .csv / .xls / .xlsx)"}
              <input
                type="file"
                accept=".rup,.csv,.xls,.xlsx"
                className="hidden"
                onChange={onPickFile}
                disabled={running}
              />
            </label>
            {file && (
              <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
                <FileSpreadsheet className="w-3.5 h-3.5" />
                <span className="font-mono">{file.name}</span>
                <span>{(file.size / 1024).toFixed(0)} KB</span>
              </span>
            )}
          </div>

          {/* Day-16 follow-up — optional second .rup co-upload to add
              room/branch context the .xls export strips. Only useful
              when the main upload is a .xls/.csv (Wrightsoft's BOM
              export); skipped silently when the main upload is itself
              a .rup since that path already has the context. */}
          {file && !file.name.toLowerCase().endsWith(".rup") && (
            <div className="flex flex-wrap gap-3 items-center pt-1">
              <label className="inline-flex items-center gap-2 px-3 py-2 text-xs font-medium border border-dashed rounded-md hover:bg-muted cursor-pointer text-muted-foreground">
                <Upload className="w-3.5 h-3.5" />
                {rupContextFile ? "Replace .rup" : "Also add source .rup (optional)"}
                <input
                  type="file"
                  accept=".rup"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0] ?? null;
                    e.target.value = "";
                    setRupContextFile(f);
                  }}
                  disabled={running}
                />
              </label>
              {rupContextFile && (
                <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
                  <FileSpreadsheet className="w-3.5 h-3.5" />
                  <span className="font-mono">{rupContextFile.name}</span>
                  <span>{(rupContextFile.size / 1024).toFixed(0)} KB</span>
                  <button
                    type="button"
                    onClick={() => setRupContextFile(null)}
                    className="text-muted-foreground hover:text-foreground"
                    aria-label="Remove .rup"
                  >
                    <XCircle className="w-3.5 h-3.5" />
                  </button>
                </span>
              )}
              <span className="text-[11px] text-muted-foreground italic">
                Adds room/branch context to the BOM result. Doesn't change line items.
              </span>
            </div>
          )}

          {/* Day-19 — v2: equipment bundle from the Windows extraction
              station. When present, replaces the .rup equipment
              extraction with COM ValidateProject output. */}
          {file && !file.name.toLowerCase().endsWith(".rup") && (
            <div className="flex flex-wrap gap-3 items-center pt-1 border-t pt-3">
              <label className="inline-flex items-center gap-2 px-3 py-2 text-xs font-medium border border-dashed border-primary/40 rounded-md hover:bg-primary/5 cursor-pointer text-primary">
                <Sparkles className="w-3.5 h-3.5" />
                {equipmentBundleFile
                  ? "Replace equipment bundle"
                  : "Add equipment bundle (from Wrightsoft Extraction Station)"}
                <input
                  type="file"
                  accept=".json,application/json"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0] ?? null;
                    e.target.value = "";
                    setEquipmentBundleFile(f);
                  }}
                  disabled={running}
                />
              </label>
              {equipmentBundleFile && (
                <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
                  <FileSpreadsheet className="w-3.5 h-3.5" />
                  <span className="font-mono">{equipmentBundleFile.name}</span>
                  <span>{(equipmentBundleFile.size / 1024).toFixed(0)} KB</span>
                  <button
                    type="button"
                    onClick={() => {
                      setEquipmentBundleFile(null);
                      setBundleProjectName("");
                    }}
                    className="text-muted-foreground hover:text-foreground"
                    aria-label="Remove bundle"
                  >
                    <XCircle className="w-3.5 h-3.5" />
                  </button>
                </span>
              )}
              {equipmentBundleFile && (
                <div className="w-full flex items-center gap-2 pt-1">
                  <label className="text-[11px] text-muted-foreground shrink-0">
                    Project name (leave blank if bundle has one project):
                  </label>
                  <input
                    type="text"
                    value={bundleProjectName}
                    onChange={(e) => setBundleProjectName(e.target.value)}
                    placeholder="e.g. 79th Ct Residence"
                    className="text-xs font-mono px-2 py-1 border rounded flex-1 max-w-md"
                    disabled={running}
                  />
                </div>
              )}
              <span className="w-full text-[11px] text-muted-foreground italic">
                COM ValidateProject JSON from the Windows extraction station. When
                present, equipment lines (AHU / condenser / heat kit) come from
                Wrightsoft's own COM output — richer and covers any manufacturer.
              </span>
            </div>
          )}

          <div className="flex gap-2 pt-2">
            <Button size="sm" onClick={submit}
                    disabled={running || !file || !clientId || !jobId}>
              {running ? (
                <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              ) : (
                <PackagePlus className="w-3.5 h-3.5 mr-1.5" />
              )}
              {equipmentBundleFile ? "Build BOM (v2 bundle)" : "Build BOM"}
            </Button>
            {result?.run_id != null && (
              <Button variant="outline" size="sm"
                      onClick={() => setLocation(`/diagnostics/run-history`)}>
                Open in Run History
                <ExternalLink className="w-3 h-3 ml-1.5" />
              </Button>
            )}
          </div>

          {error && (
            <div className="text-sm text-destructive flex gap-2 items-start mt-2">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              {error}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Day-17 — rehydration spinner while ?run= is being fetched */}
      {urlRunId && !result && persistedRun.isLoading && (
        <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />
          Restoring run #{urlRunId}…
        </div>
      )}
      {urlRunId && !result && persistedRun.isError && (
        <div className="rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-900">
          <span className="font-medium">Couldn't restore run #{urlRunId}.</span>{" "}
          It may have been deleted. Pick a file above to build a fresh BOM.
        </div>
      )}

      {/* Result */}
      {result && (
        <BomResultView
          bom={result}
          clientId={clientId}
          brandColor={brandColor}
          onChatOpenChange={setChatOpen}
          onApplyPatch={async (action) => {
            // Day-25 — surgical corrections from the chat. Persist as
            // a run-scoped patch (fixes THIS run only), then mirror
            // the edit locally so the tables update immediately.
            const runId = (result as any)?.run_id;
            if (!runId) return false;
            const op = action.kind === "propose_remove_line" ? "remove_line"
                     : action.kind === "propose_add_line"    ? "add_line"
                     : "update_line";
            const fields: Record<string, unknown> = {};
            if (action.quantity != null)    fields.quantity    = action.quantity;
            if (action.description != null) fields.description = action.description;
            if (op === "add_line" && action.unit_price != null) fields.unit_price = action.unit_price;
            if (action.source) fields.source = action.source;
            try {
              const res = await fetch(`/api/bom-runs/${runId}/patches`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({
                  op, sku: action.sku, fields, reason: action.reason,
                  rule_candidate: !!action.rule_candidate,
                }),
              });
              const body = await res.json();
              if (!res.ok || !body.success) return false;
            } catch { return false; }
            setResult((prev) => {
              if (!prev) return prev;
              const items = (prev.line_items as any[]).slice();
              const idx = items.findIndex(
                (li: any) => (li.sku ?? li.generic_id) === action.sku);
              if (op === "remove_line") {
                if (idx >= 0) items.splice(idx, 1);
              } else if (op === "add_line") {
                items.push({
                  generic_id: action.sku, sku: action.sku,
                  description: action.description ?? action.sku,
                  quantity: action.quantity ?? 1, unit: "ea",
                  unit_cost: action.unit_price ?? 0,
                  unit_price: action.unit_price ?? 0,
                  total_price: (action.unit_price ?? 0) * (action.quantity ?? 1),
                  source: "wrightsoft_manual", section: "Other",
                  patched: true,
                });
              } else if (idx >= 0) {
                const li = { ...items[idx], patched: true };
                if (action.quantity != null) {
                  li.quantity = action.quantity;
                  const unit = li.unit_price ?? li.unit_cost ?? 0;
                  li.total_price = Math.round(unit * action.quantity * 100) / 100;
                }
                if (action.description != null) li.description = action.description;
                items[idx] = li;
              }
              return { ...prev, line_items: items,
                       item_count: items.length } as any;
            });
            return true;
          }}
          onRegenerate={async () => {
            // Day-25 — full re-run from stored design data. Result is
            // swapped in place; the chat sidebar stays mounted, so the
            // conversation survives.
            const runId = (result as any)?.run_id;
            if (!runId) return false;
            try {
              const res = await fetch(`/api/bom-runs/${runId}/regenerate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({}),
              });
              const body = await res.json();
              if (!res.ok || !body.success) return false;
              const fresh = body.data as BomResponse;
              setResult(fresh);
              const newRunId = (fresh as any)?.run_id;
              if (newRunId && typeof window !== "undefined") {
                try {
                  const url = new URL(window.location.href);
                  url.searchParams.set("run", String(newRunId));
                  window.history.replaceState({}, "", url.toString());
                } catch { /* ignore */ }
              }
              return true;
            } catch { return false; }
          }}
          onLineUpdated={(idx, patch) => {
            // Optimistic in-place update so the edit drawer's save is
            // reflected immediately without a full BOM re-run.
            setResult((prev) => {
              if (!prev) return prev;
              const items = prev.line_items.slice();
              items[idx] = { ...items[idx], ...patch } as any;
              return { ...prev, line_items: items };
            });
          }}
        />
      )}
    </div>
  );
}

// ─── Result view ───────────────────────────────────────────────────

function BomResultView({ bom, clientId, brandColor, onLineUpdated, onChatOpenChange, onApplyPatch, onRegenerate }: {
  bom: BomResponse & {
    source_pipeline?: string;
    wrightsoft_mapped_item_count?: number;
    wrightsoft_unmapped_item_count?: number;
    wrightsoft_dfunit_item_count?: number;
    wrightsoft_passthrough_item_count?: number;
    wrightsoft_discovered_item_count?: number;
    wrightsoft_manual_item_count?: number;
  };
  clientId: string;
  brandColor: string;
  onLineUpdated: (lineIndex: number, patch: Record<string, any>) => void;
  /** Page-level hook: reflow the content column while the chat is open. */
  onChatOpenChange?: (open: boolean) => void;
  /** Day-25 — surgical patch + full regenerate, owned by the page
   * because both mutate the result object in place. */
  onApplyPatch?: (a: import("@/components/wrightsoft-bom/bom-chat-sidebar").ProposedAction) => Promise<boolean>;
  onRegenerate?: () => Promise<boolean>;
}) {
  // Edit drawer state lives here because we own the in-place line
  // mutation that runs after a save. The line index is preserved so
  // the optimistic update knows which row to patch.
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const editingLine: EditableLine | null = editingIndex == null
    ? null
    : ((bom.line_items as any[])[editingIndex] as EditableLine);
  const [, setLocation] = useLocation();
  const renderPdf = useRenderBomPdf();
  // Day-24 — "sniping": surgical table/row references for the chat.
  // Lives here because both the crosshair buttons and the sidebar
  // render inside this view.
  const [snipes, setSnipes] = useState<Snipe[]>([]);
  // Sniping auto-opens the chat (bumping the signal); the page-level
  // container reflows to full-width-minus-panel while it's open.
  const [chatOpenSignal, setChatOpenSignal] = useState(0);
  const onSnipe = (s: Snipe) => {
    setSnipes((prev) =>
      prev.some((x) => x.ref === s.ref) ? prev : [...prev, s].slice(0, 6));
    setChatOpenSignal((n) => n + 1);
  };
  /** Row-level crosshair cell — consistent width so columns stay
   * aligned with the matching empty <th className="w-10" />. */
  const snipeTd = (s: Snipe) => (
    <td className="w-10 px-0 py-1.5 text-center align-middle">
      <button className="opacity-30 hover:opacity-100 transition-opacity align-middle"
              title={`Reference "${s.label}" in the chat`}
              onClick={(e) => { e.stopPropagation(); onSnipe(s); }}>
        <Crosshair className="w-3.5 h-3.5" />
      </button>
    </td>
  );
  /** Card-header crosshair for whole-table snipes. */
  const snipeHeaderBtn = (s: Snipe) => (
    /* -mr-3: CardHeader px-6 (24px) vs body cell w-10 (icon center
     * 20px from card edge) — pull 12px right so header + row
     * crosshairs share one vertical line. */
    <button className="ml-auto self-center -mr-3 opacity-70 hover:opacity-100"
            title={`Reference the whole ${s.label} table in the chat`}
            onClick={() => onSnipe(s)}>
      <Crosshair className="w-4 h-4" />
    </button>
  );
  const renderXls = useRenderBomXls();
  // Day-16 — inline price-only editor support
  const upsertOverride = useUpsertContractorOverride();
  const { toast: pricingToast } = useToast();
  const [bulkOpen, setBulkOpen] = useState(false);

  /** Save a single line's unit price to contractor_overrides, then
   * optimistically update the line locally so the BOM totals reflect
   * the new price without a full re-run. Falls back to a toast error
   * when the upsert fails.
   *
   * When called with price === 0, also tags the override with a
   * "$0 confirmed" note so the row renders as 'confirmed $0' (gray
   * check) instead of 'needs price' (rose pill). Lets the user
   * explicitly say "this is intentionally free, not forgotten." */
  const savePriceForLine = (absIdx: number, price: number) => {
    const li = (bom.line_items as any[])[absIdx];
    if (!li) return;
    const supplier = (li.manufacturer || li.src || "WSF").toString().toUpperCase();
    const sku = li.sku || li.generic_id;
    if (!sku) {
      pricingToast({
        title: "Cannot save price",
        description: "Line has no SKU to key the override on.",
        variant: "destructive",
      });
      return;
    }
    const isZeroConfirm = price === 0;
    upsertOverride.mutate(
      {
        client_id: clientId,
        supplier,
        sku,
        unit_price: price,
        notes: isZeroConfirm ? "$0 confirmed" : undefined,
      },
      {
        onSuccess: (saved: any) => {
          const qty = li.quantity ?? 0;
          const markupPct = li.markup_pct ?? 0;
          const newUnitPrice = Math.round(price * (1 + markupPct / 100) * 100) / 100;
          onLineUpdated(absIdx, {
            unit_cost:  price,
            total_cost: Math.round(price * qty * 100) / 100,
            unit_price: newUnitPrice,
            total_price: Math.round(newUnitPrice * qty * 100) / 100,
            override_id: saved?.id ?? null,
            override_updated_at: saved?.updated_at ?? null,
            override_updated_by: saved?.updated_by ?? null,
            source: (li.source === "wrightsoft_passthrough"
                     || li.source === "wrightsoft_discovered")
              ? "wrightsoft_manual"
              : li.source,
          } as any);
          pricingToast({
            title: isZeroConfirm
              ? `${supplier}/${sku} confirmed as $0`
              : `$${price.toFixed(2)} saved for ${supplier}/${sku}`,
            description: `Applies to all future BOMs for ${clientId}.`,
          });
        },
        onError: (err: any) => {
          pricingToast({
            title: "Save failed",
            description: err?.error ?? "Could not save price",
            variant: "destructive",
          });
        },
      },
    );
  };

  // For "Compare to previous run": pull the 5 most recent runs for
  // this client and pick the newest one that isn't the current run.
  // 5 is plenty — anything older that would interest a reviewer they
  // can pick by hand in the Run Diff page. The hook auto-skips when
  // run_id isn't set yet.
  const recent = useListBomRuns(
    bom.run_id != null && clientId
      ? { client_id: clientId, limit: 5 }
      : undefined,
  );
  const previousRunId = (recent.data?.runs ?? [])
    .map((r) => r.id)
    .find((id) => id !== bom.run_id);
  const mapped      = bom.wrightsoft_mapped_item_count      ?? 0;
  const unmapped    = bom.wrightsoft_unmapped_item_count    ?? 0;
  const dfunit      = bom.wrightsoft_dfunit_item_count      ?? 0;
  const passthrough = bom.wrightsoft_passthrough_item_count ?? 0;
  // Day-16 — auto-learn (discovered) lines should count toward "From
  // Wrightsoft directly" + "Resolved with SKU". They came from a prior
  // run that auto-recorded the (Src, SKU) combo; functionally
  // indistinguishable from passthrough for the contractor.
  const discovered  = bom.wrightsoft_discovered_item_count  ?? 0;
  const nonStandard = (bom as any).wrightsoft_non_standard_fitting_count ?? 0;
  const ahriEnriched = (bom as any).wrightsoft_ahri_enriched_count ?? 0;
  const total       = bom.item_count;
  // "Resolved" = the line has a real answer (catalog match, DFUnit hit,
  // or Wrightsoft told us the Src+Name combo directly). Only the
  // genuinely-unmapped lines belong in the SKU Backlog.
  const resolved    = mapped + passthrough + discovered;
  const resolvedPct = total > 0 ? (resolved / total) * 100 : 0;

  // Group line items by section so the table mirrors a real Wrightsoft
  // BOM (Equipment / Duct System Equipment / Rheia / Labor) with a
  // subtotal row at the end of each block. Order is intentional —
  // Equipment first because that's what reviewers scan first.
  const SECTION_ORDER = [
    "Equipment",
    "Duct System Equipment",
    "Rheia Duct System Equipment",
    "Labor",
    "Other",
  ];
  const groups = (() => {
    const buckets = new Map<string, any[]>();
    for (const sec of SECTION_ORDER) buckets.set(sec, []);
    for (const li of (bom.line_items as any[])) {
      const sec = (li.section as string) || "Other";
      if (!buckets.has(sec)) buckets.set(sec, []);
      buckets.get(sec)!.push(li);
    }
    return Array.from(buckets.entries())
      .filter(([, items]) => items.length > 0)
      .map(([section, items]) => ({
        section,
        items,
        subtotal: items.reduce(
          (acc, li) => acc + (li.total_price ?? li.total_cost ?? 0),
          0,
        ),
      }));
  })();
  return (
    <div className="space-y-6">
      {/* Brand stripe — matches the contractor color on the PDF/XLS */}
      <div
        className="h-1 rounded-full"
        style={{ background: brandColor }}
        aria-hidden
      />

      {/* Day-16 — .rup best-effort notice */}
      {(bom as any).source_pipeline === "wrightsoft_rup" && (
        <div className="rounded-md border border-sky-300 bg-sky-50 px-3 py-2 text-sm text-sky-900">
          <span className="font-medium">.rup parsed (best-effort).</span>{" "}
          Equipment + duct system extracted directly from the binary. For the
          canonical fitting rollup (codes like 8E / 11H), upload the Wrightsoft
          BOM export (<code className="text-xs">File → Bill of Materials</code>) as{" "}
          <code className="text-xs">.xls</code> instead.
        </div>
      )}

      {/* Day-16 follow-up — ducts-only / Manual D file-type hint */}
      {(bom as any).rup_file_type_hint && (
        <div className="rounded-md border border-blue-300 bg-blue-50 px-3 py-2 text-sm text-blue-900">
          <span className="font-medium">Ducts-only file detected:</span>{" "}
          {(bom as any).rup_file_type_hint}
        </div>
      )}

      {/* Day-16 follow-up — room/branch context from co-uploaded .rup.
          Surfaces the rooms served + duct system shape pulled from the
          design file when both .xls and .rup arrive together. */}
      {(bom as any).rup_context && (
        <div className="rounded-md border border-indigo-200 bg-indigo-50/60 px-3 py-2 text-sm text-indigo-900 space-y-1.5">
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="w-3.5 h-3.5" />
            <span className="font-medium">Design context</span>
            <span className="text-xs text-indigo-700/70">
              from {(bom as any).rup_context.filename}
            </span>
          </div>
          {(bom as any).rup_context.room_count > 0 && (
            <div className="flex flex-wrap gap-1 items-baseline">
              <span className="text-xs font-medium mr-1">
                Rooms ({(bom as any).rup_context.room_count}):
              </span>
              {((bom as any).rup_context.rooms as string[]).map((r, i) => (
                <span
                  key={i}
                  className="inline-block px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-800 text-[10px]"
                >
                  {r}
                </span>
              ))}
            </div>
          )}
          {Object.keys((bom as any).rup_context.duct_type_counts || {}).length > 0 && (
            <div className="text-xs">
              <span className="font-medium">Duct mix:</span>{" "}
              {Object.entries((bom as any).rup_context.duct_type_counts as Record<string, number>)
                .map(([k, v]) => `${v} ${k}`).join(" · ")}
            </div>
          )}
          {(((bom as any).rup_context.round_diameters?.length ?? 0)
            + ((bom as any).rup_context.rect_sizes?.length ?? 0)) > 0 && (
            <div className="text-xs">
              <span className="font-medium">Sizes used:</span>{" "}
              {[
                ...((bom as any).rup_context.round_diameters as number[] || []).map((d) => `${d}"`),
                ...((bom as any).rup_context.rect_sizes as string[] || []),
              ].join(", ")}
            </div>
          )}
        </div>
      )}

      {/* Day-17 — empty Equipment section banner. Wrightsoft's BOM.xls
          export doesn't include equipment (AHU / condenser / furnace /
          ERV / heat kit) — those live in the source .rup. When the
          user uploads only the .xls and the Equipment section comes
          back empty, point them at the workaround so they don't
          assume the BOM is broken. Suppress once a .rup has been
          attached (rup_context present) or once equipment lines exist. */}
      {(() => {
        const items = (bom.line_items as any[]) ?? [];
        const equipCount = items.filter((li) => li.section === "Equipment").length;
        const hasRupContext = !!(bom as any).rup_context;
        if (equipCount > 0 || hasRupContext) return null;
        return (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2.5 text-sm text-amber-900">
            <div className="font-medium mb-1 flex items-center gap-2">
              <PackagePlus className="w-4 h-4" />
              Equipment section empty
            </div>
            <p className="text-xs leading-relaxed">
              Wrightsoft's <code className="font-mono text-[11px]">BOM.xls</code> export doesn't
              include named equipment (AHU, condenser, furnace, ERV, heat kit). To populate the
              Equipment section, also attach the source{" "}
              <code className="font-mono text-[11px]">.rup</code> file under{" "}
              <strong>Also add source .rup (optional)</strong> above — we'll extract equipment
              from its <code className="font-mono text-[11px]">EQUIP</code> block and merge it
              into this BOM on the next build.
            </p>
          </div>
        );
      })()}

      {/* Day-16 — auto sanity-check banner. Flags obvious red flags
          (low total, all-$0 equipment, no AHRI when equipment present)
          so the operator doesn't have to eyeball every BOM. */}
      {(() => {
        const items = (bom.line_items as any[]) ?? [];
        const equip = items.filter((li) => li.section === "Equipment");
        const grandTotal = bom.totals?.total_price ?? 0;
        const issues: string[] = [];
        if (items.length >= 5 && grandTotal > 0 && grandTotal < 1000) {
          issues.push(
            `Grand total is only $${grandTotal.toFixed(2)} across ${items.length} lines — pricing likely incomplete.`,
          );
        }
        if (equip.length > 0 && equip.every((li) =>
              (li.unit_price ?? li.unit_cost ?? 0) === 0 && !li.override_id)) {
          issues.push(
            `${equip.length} equipment line${equip.length === 1 ? "" : "s"} at $0 — contractor pricing not loaded for these SKUs.`,
          );
        }
        if (equip.length > 0 && ahriEnriched === 0) {
          issues.push(
            `${equip.length} equipment line${equip.length === 1 ? "" : "s"} with no AHRI spec match — model numbers may not be in the certified-equipment library.`,
          );
        }
        if (issues.length === 0) return null;
        return (
          <div className="rounded-md border border-orange-300 bg-orange-50 px-3 py-2 text-sm text-orange-900">
            <div className="font-medium mb-1">Sanity check — review before forwarding to QA:</div>
            <ul className="list-disc list-inside space-y-0.5 text-xs">
              {issues.map((msg, idx) => (
                <li key={idx}>{msg}</li>
              ))}
            </ul>
          </div>
        );
      })()}

      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <StatCard label="Items emitted" value={String(total)} />
        <StatCard
          label="Resolved (with SKU)"
          value={`${resolved} (${resolvedPct.toFixed(0)}%)`}
          tone="emerald"
        />
        <StatCard
          label="Via catalog mapping"
          value={String(mapped)}
          tone={mapped > 0 ? "emerald" : undefined}
        />
        <StatCard
          label="From Wrightsoft directly"
          value={String(passthrough + discovered)}
          tone={passthrough + discovered > 0 ? "emerald" : undefined}
        />
        <StatCard label="Unmapped (SKU Backlog)"
                  value={String(unmapped)}
                  tone={unmapped > 0 ? "amber" : undefined} />
      </div>
      {dfunit > 0 && (
        <p className="text-xs text-muted-foreground -mt-2 ml-1">
          {dfunit} of the catalog-mapped lines came from the equipment library (DFUnit).
        </p>
      )}
      {ahriEnriched > 0 && (
        <p className="text-xs text-muted-foreground -mt-2 ml-1">
          {ahriEnriched} equipment line{ahriEnriched === 1 ? "" : "s"} matched the
          AHRI certified-equipment library — hover the{" "}
          <span className="inline-block px-1.5 py-0.5 rounded bg-sky-100 text-sky-800 text-[10px] font-medium">
            AHRI
          </span>{" "}
          badge to see SEER / HSPF / AHRI cert number.
        </p>
      )}
      {nonStandard > 0 && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <span className="font-medium">Non-standard fittings detected:</span>{" "}
          {nonStandard} line{nonStandard === 1 ? "" : "s"} use a fitting code
          outside Tom's standard template. Look for the{" "}
          <span className="inline-block px-1.5 py-0.5 rounded bg-amber-200 text-amber-900 text-xs font-medium">
            non-standard
          </span>{" "}
          tag in the line items below.
        </div>
      )}

      {/* Day-16 — pricing coverage signal. Fires whenever ANY line is
          unpriced — even one $0 line is worth offering the upload
          shortcut. The banner copy adapts to the severity (most-
          missing / mostly-priced / a few missing). */}
      {(() => {
        const items = (bom.line_items as any[]) ?? [];
        // Day-17 — confirmed-$0 lines (override exists with price 0)
        // don't count as 'unpriced' — they're explicitly handled.
        const unpriced = items.filter(
          (li) => (li.unit_price ?? li.unit_cost ?? 0) === 0 && !li.override_id,
        ).length;
        if (items.length === 0 || unpriced === 0) return null;
        const priced = items.length - unpriced;
        const severe = unpriced / items.length >= 0.5;
        return (
          <div className={cn(
            "rounded-md border px-3 py-2 text-sm flex items-center justify-between gap-3",
            severe
              ? "border-amber-300 bg-amber-50 text-amber-900"
              : "border-amber-200 bg-amber-50/60 text-amber-800",
          )}>
            <div>
              <span className="font-medium">
                {severe ? "Partial pricing — " : "Some lines at $0 — "}
              </span>
              {severe
                ? `only ${priced} of ${items.length} lines have a unit price. The grand total below reflects that subset and is not the full project cost.`
                : `${unpriced} of ${items.length} lines have no contractor price loaded yet. Their cost shows as $0 and they're not contributing to the grand total.`}
            </div>
            <Link href="/pricing/import">
              <Button size="sm" variant="outline">Upload pricing →</Button>
            </Link>
          </div>
        );
      })()}

      {/* Download row */}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-muted-foreground">
          {(() => {
            const items = (bom.line_items as any[]) ?? [];
            const priced = items.filter(
              (li) => (li.unit_price ?? li.unit_cost ?? 0) > 0,
            ).length;
            const partial = items.length > 0 && priced < items.length;
            return partial ? "Partial total: " : "Totals: ";
          })()}
          <span
            className="font-semibold px-2 py-0.5 rounded text-white"
            style={{ background: brandColor }}
          >
            {bom.totals.total_price != null
              ? `$${bom.totals.total_price.toFixed(2)}`
              : "—"}
          </span>
        </span>
        <div className="flex-1" />
        {(() => {
          const items = (bom.line_items as any[]) ?? [];
          // Day-17 — confirmed-$0 lines (override exists) don't count
          // toward 'unpriced' since the user already handled them.
          const unpriced = items.filter(
            (li) => (li.unit_price ?? li.unit_cost ?? 0) === 0 && !li.override_id,
          ).length;
          if (unpriced === 0) return null;
          return (
            <Button
              size="sm"
              variant="outline"
              className="border-rose-500/40 text-rose-700 hover:bg-rose-50 dark:text-rose-300"
              onClick={() => setBulkOpen(true)}
            >
              <Pencil className="w-3.5 h-3.5 mr-1.5" />
              Price {unpriced} unpriced line{unpriced === 1 ? "" : "s"}
            </Button>
          );
        })()}
        <Button
          size="sm"
          variant="outline"
          onClick={() => renderXls.mutate({ bom })}
          disabled={renderXls.isPending}
        >
          {renderXls.isPending
            ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
            : <FileSpreadsheet className="w-3.5 h-3.5 mr-1.5" />}
          Download XLS
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => renderPdf.mutate({ bom })}
          disabled={renderPdf.isPending}
        >
          {renderPdf.isPending
            ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
            : <Download className="w-3.5 h-3.5 mr-1.5" />}
          Download PDF
        </Button>
        {bom.run_id != null && previousRunId != null && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => setLocation(
              `/diagnostics/run-diff?left=${previousRunId}&right=${bom.run_id}`,
            )}
            title={`Compare against the previous run for ${clientId}`}
          >
            <GitCompareArrows className="w-3.5 h-3.5 mr-1.5" />
            Compare to previous
          </Button>
        )}
      </div>

      {/* Day-17 — Quick Order Summary (Tom's #1). Groups identical
          SKUs by family + size, sums quantities, applies standard
          packaging conversion (flex = 25ft boxes, rect fiberglass
          = 10ft sticks). Contractor sees at a glance what to buy. */}
      {((bom as any).quick_order_summary?.length ?? 0) > 0 && (
        <Card>
          <CardHeader className="py-3 bg-slate-900 text-white rounded-t-lg">
            <CardTitle className="text-sm flex items-center gap-2">
              <PackagePlus className="w-4 h-4" />
              Quick Order Summary
              {snipeHeaderBtn({
                ref: "table:quick-order", label: "Quick Order", kind: "table",
                data: (bom as any).quick_order_summary,
              })}
            </CardTitle>
            <CardDescription className="text-xs text-slate-300">
              Buy at these quantities — detailed runs below.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 text-[10px] uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">Category</th>
                  <th className="text-left px-3 py-2 font-medium">Size</th>
                  <th className="text-left px-3 py-2 font-medium">Item</th>
                  <th className="text-right px-3 py-2 font-medium">Total</th>
                  <th className="text-left px-3 py-2 font-medium">Order as</th>
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody>
                {(() => {
                  const qo = (bom as any).quick_order_summary as any[];
                  let prevCat = "";
                  return qo.map((r: any, idx: number) => {
                    const showCat = r.category !== prevCat;
                    if (showCat) prevCat = r.category;
                    // Day-17 — shared pluralization rule: ea → never
                    // pluralizes; box → "boxes"; everything else → +s.
                    const _suffix = r.containers === 1
                      ? ""
                      : r.container === "ea" ? ""
                      : r.container === "box" ? "es"
                      : "s";
                    const orderLabel = `${r.containers} ${r.container}${_suffix}`;
                    return (
                      <tr key={idx} className="border-t hover:bg-muted/10">
                        <td className={cn(
                          "px-3 py-1.5 text-xs",
                          showCat ? "font-semibold" : "text-muted-foreground/50",
                        )}>
                          {showCat ? r.category : ""}
                        </td>
                        <td className="px-3 py-1.5 font-mono text-[11px]">{r.size || "—"}</td>
                        <td className="px-3 py-1.5 text-xs text-muted-foreground max-w-[320px] truncate">{r.label}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums font-semibold text-xs">
                          {r.total.toFixed(2)} {r.unit}
                        </td>
                        <td className="px-3 py-1.5 text-xs">
                          <span className="font-semibold">{orderLabel}</span>
                          {r.per_container > 1 && (
                            <span className="text-muted-foreground text-[10px] ml-1">
                              ({Math.round(r.per_container)} {r.unit} each)
                            </span>
                          )}
                        </td>
                        {snipeTd({
                          ref: `row:qo:${r.size || r.label}`,
                          label: (r.size || r.label || "row").slice(0, 24),
                          kind: "row", data: r,
                        })}
                      </tr>
                    );
                  });
                })()}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* Day-21 — Register Air Balance (from .rup BALDUCT records).
          Each drawn register maps to its Manual-D design CFM. Decoded
          directly from the .rup binary via structural walk — no .xls
          sidecar required. Renders above the Duct Cuts card so the
          crew can cross-check register CFMs against cut lengths on
          the same page. */}
      {((bom as any).rup_balduct?.length ?? 0) > 0 && (
        <Card>
          <CardHeader className="py-3 bg-slate-700 text-white rounded-t-lg">
            <CardTitle className="text-sm flex items-center gap-2">
              <GitCompareArrows className="w-4 h-4" />
              Register Air Balance (Manual-D design CFM)
              {snipeHeaderBtn({ ref: "table:registers", label: "Registers",
                kind: "table", data: (bom as any).rup_balduct })}
            </CardTitle>
            <CardDescription className="text-xs text-slate-300">
              {(bom as any).rup_balduct.length} registers · design
              airflow per register decoded directly from the Wrightsoft
              .rup file.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 text-[10px] uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="text-left  px-3 py-2 font-medium">Register</th>
                  <th className="text-right px-3 py-2 font-medium">Design CFM</th>
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {((bom as any).rup_balduct as Array<{
                  label: string; cfm: number; id: number;
                }>).map((r, i) => (
                  <tr key={`bd-${r.id}-${i}`} className="hover:bg-muted/10">
                    <td className="px-3 py-1.5 text-xs">{r.label}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-xs">
                      {r.cfm.toFixed(1)}
                    </td>
                    {snipeTd({ ref: `row:reg:${r.label}-${i}`,
                      label: r.label.slice(0, 24), kind: "row", data: r })}
                  </tr>
                ))}
                {/* Summary footer — total design airflow */}
                <tr className="bg-muted/20 font-semibold">
                  <td className="px-3 py-1.5 text-xs">Total design airflow</td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-xs">
                    {((bom as any).rup_balduct as Array<{ cfm: number }>)
                      .reduce((s, r) => s + r.cfm, 0)
                      .toFixed(1)}
                  </td>
                  <td className="w-10"></td>
                </tr>
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* Day-21 — Per-segment Duct Cuts (from .rup drawing objects,
          Increment 2b). Decodes CSDuctOb/CRDuctOb instances in the
          .rup binary to produce per-piece cut list with real
          diameter/size + length. Works on BOTH built AND un-built
          .rup files — no "Bill of Materials → save" step required.
          Complements the older duct_cuts_summary path below (from
          the .xls export). When both are present, this one is more
          comprehensive because it decodes drawing objects directly. */}
      {((bom as any).rup_duct_geometry?.length ?? 0) > 0 && (
        <Card>
          <CardHeader className="py-3 bg-slate-700 text-white rounded-t-lg">
            <CardTitle className="text-sm flex items-center gap-2">
              <GitCompareArrows className="w-4 h-4" />
              Per-piece Duct Cuts (from .rup drawing)
              {snipeHeaderBtn({ ref: "table:duct-cuts-geom", label: "Duct Cuts",
                kind: "table", data: (bom as any).rup_duct_geometry })}
            </CardTitle>
            <CardDescription className="text-xs text-slate-300">
              {(bom as any).rup_duct_geometry.length} drawn segments ·{" "}
              {((bom as any).rup_duct_geometry as Array<{
                cut_length_ft: number;
              }>).reduce((s, r) => s + r.cut_length_ft, 0).toFixed(1)}{" "}
              ft total · decoded directly from the .rup binary's
              CSDuctOb/CRDuctOb drawing objects.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 text-[10px] uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="text-left  px-3 py-2 font-medium">Run</th>
                  <th className="text-left  px-3 py-2 font-medium">Side</th>
                  <th className="text-left  px-3 py-2 font-medium">Shape</th>
                  <th className="text-left  px-3 py-2 font-medium">Size</th>
                  <th className="text-right px-3 py-2 font-medium">Cut length</th>
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {((bom as any).rup_duct_geometry as Array<{
                  run_id: string; side: string; shape: string;
                  diameter_in?: number; width_in?: number; height_in?: number;
                  cut_length_ft: number;
                }>).map((r, i) => {
                  const size = r.shape === "round"
                    ? `${r.diameter_in}" round`
                    : `${r.width_in}" × ${r.height_in}"`;
                  return (
                    <tr key={`geom-${r.run_id}-${i}`} className="hover:bg-muted/10">
                      <td className="px-3 py-1.5 text-xs font-mono">{r.run_id}</td>
                      <td className="px-3 py-1.5 text-xs text-muted-foreground">{r.side}</td>
                      <td className="px-3 py-1.5 text-xs">{r.shape}</td>
                      <td className="px-3 py-1.5 text-xs font-mono">{size}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-xs">
                        {r.cut_length_ft.toFixed(2)} ft
                      </td>
                      {snipeTd({ ref: `row:cut:${r.run_id}-${i}`,
                        label: `${r.run_id}`.slice(0, 24), kind: "row", data: r })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* Day-17 — Per-piece Duct Cuts (Richard Jun 30). Every flex /
          rigid duct cut listed with length + joints. Each cut = 2 end
          joints needing fastener + mastic + tape, so the crew can
          read joint counts straight off the BOM. Complements the
          aggregated Quick Order Summary above. */}
      {((bom as any).duct_cuts_summary?.length ?? 0) > 0 && (
        <Card>
          <CardHeader className="py-3 bg-slate-700 text-white rounded-t-lg">
            <CardTitle className="text-sm flex items-center gap-2">
              <GitCompareArrows className="w-4 h-4" />
              Duct Cuts (per piece)
              {snipeHeaderBtn({ ref: "table:duct-cuts", label: "Cuts Summary",
                kind: "table", data: (bom as any).duct_cuts_summary })}
            </CardTitle>
            <CardDescription className="text-xs text-slate-300">
              Every individual cut — each end of every run is a sealed joint (fastener + mastic + tape).
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 text-[10px] uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="text-left  px-3 py-2 font-medium">Family</th>
                  <th className="text-left  px-3 py-2 font-medium">Size</th>
                  <th className="text-left  px-3 py-2 font-medium">Cut #</th>
                  <th className="text-right px-3 py-2 font-medium">Length</th>
                  <th className="text-right px-3 py-2 font-medium">Joints</th>
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {(() => {
                  const groups = (bom as any).duct_cuts_summary as any[];
                  const rows: React.ReactElement[] = [];
                  groups.forEach((g, gi) => {
                    // Header row (group totals) + one row per cut
                    rows.push(
                      <tr key={`g${gi}`} className="bg-muted/10 font-semibold">
                        <td className="px-3 py-1.5 text-xs">{g.family}</td>
                        <td className="px-3 py-1.5 font-mono text-[11px]">{g.size}</td>
                        <td className="px-3 py-1.5 text-xs text-muted-foreground">
                          {g.cut_count} cut{g.cut_count === 1 ? "" : "s"}
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-xs">
                          {g.total_length.toFixed(2)} ft
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-xs">
                          {g.total_joints}
                        </td>
                        {snipeTd({ ref: `row:cutgrp:${g.family}-${g.size}`,
                          label: `${g.family} ${g.size}`.slice(0, 24),
                          kind: "row", data: g })}
                      </tr>
                    );
                    g.cuts.forEach((c: any, ci: number) => {
                      rows.push(
                        <tr key={`g${gi}-c${ci}`} className="hover:bg-muted/10">
                          <td className="px-3 py-1.5 text-xs text-muted-foreground/50"></td>
                          <td className="px-3 py-1.5 text-xs text-muted-foreground/50"></td>
                          <td className="px-3 py-1.5 text-xs text-muted-foreground">#{ci + 1}</td>
                          <td className="px-3 py-1.5 text-right tabular-nums text-xs">
                            {c.length.toFixed(2)} ft
                          </td>
                          <td className="px-3 py-1.5 text-right tabular-nums text-xs">{c.joints}</td>
                          {snipeTd({ ref: `row:cut:${g.family}-${g.size}-${ci + 1}`,
                            label: `${g.size} #${ci + 1}`.slice(0, 24),
                            kind: "row", data: { family: g.family, size: g.size, ...c } })}
                        </tr>
                      );
                    });
                  });
                  return rows;
                })()}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* Line-item table */}
      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-sm flex items-center gap-2">
            Line items ({total})
            {snipeHeaderBtn({ ref: "table:line-items", label: "Line Items",
              kind: "table", data: bom.line_items })}
          </CardTitle>
          <CardDescription className="text-xs">
            <span className="inline-flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3 text-emerald-600" /> mapped
            </span>{" "}
            rows have a real manufacturer SKU.{" "}
            <span className="inline-flex items-center gap-1">
              <XCircle className="w-3 h-3 text-amber-600" /> unmapped
            </span>{" "}
            rows surface to the SKU Backlog so Richard's team can
            prioritize what to add to mapped_parts.csv next.
          </CardDescription>
        </CardHeader>
        <Separator />
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b bg-muted/30 text-muted-foreground">
                <th className="text-left  px-3 py-2 font-medium w-10">#</th>
                <th className="text-left  px-3 py-2 font-medium">Generic</th>
                <th className="text-left  px-3 py-2 font-medium">Description</th>
                <th className="text-left  px-3 py-2 font-medium">Source</th>
                <th className="text-left  px-3 py-2 font-medium">Mfr</th>
                <th className="text-left  px-3 py-2 font-medium">SKU</th>
                <th className="text-right px-3 py-2 font-medium">Qty</th>
                <th className="text-right px-3 py-2 font-medium">Unit $</th>
                <th className="text-right px-3 py-2 font-medium">Total</th>
                <th className="w-10"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {(() => {
                let cursor = 0;
                return groups.map(({ section, items, subtotal }) => {
                  const start = cursor;
                  cursor += items.length;
                  return (
                    <SectionBlock
                      key={section}
                      section={section}
                      items={items}
                      subtotal={subtotal}
                      startIndex={start}
                      onEditLine={(absIdx) => setEditingIndex(absIdx)}
                      onInlinePriceSave={(absIdx, price) =>
                        savePriceForLine(absIdx, price)
                      }
                      pricingClientId={clientId}
                      onSnipe={onSnipe}
                    />
                  );
                });
              })()}
            </tbody>
          </table>
        </div>
        <div className="px-3 py-2 text-[11px] text-muted-foreground border-t bg-muted/10">
          Click any line to edit its SKU translation or enter the
          contractor's price.
        </div>
      </Card>

      {/* Day-17 — Equipment Specifications card. Mirrors the AHRI
          specs block in the PDF and the "Equipment Specs" sheet in
          the XLS so the SPA shows the same data, not just inline
          hover popovers. Hidden when no equipment line carries an
          ahri_spec — i.e. duct-only BOMs and equipment with no AHRI
          match. */}
      {(() => {
        const items = (bom.line_items as any[]) ?? [];
        const specs = items
          .filter((li) => li.ahri_spec)
          .map((li) => ({
            generic_id:  li.generic_id,
            description: li.description,
            quantity:    li.quantity,
            ...li.ahri_spec,
          }));
        if (specs.length === 0) return null;
        return (
          <Card>
            <CardHeader className="py-3">
              <CardTitle className="text-sm flex items-center gap-2">
                <Cpu className="w-4 h-4 text-primary" />
                Equipment Specifications
                {snipeHeaderBtn({ ref: "table:equip-specs", label: "Equip Specs",
                  kind: "table", data: specs })}
              </CardTitle>
              <CardDescription className="text-xs">
                AHRI-certified specs for every equipment line on this BOM. Matches the
                Equipment Specs sheet in the .xlsx export and the bottom of the PDF.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-muted/40 text-[10px] uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="text-left  px-3 py-2 font-medium">Model / Description</th>
                    <th className="text-left  px-3 py-2 font-medium">Type</th>
                    <th className="text-right px-3 py-2 font-medium">Capacity (BTU)</th>
                    <th className="text-right px-3 py-2 font-medium">SEER</th>
                    <th className="text-right px-3 py-2 font-medium">HSPF</th>
                    <th className="text-right px-3 py-2 font-medium">EER95</th>
                    <th className="text-right px-3 py-2 font-medium">AFUE</th>
                    <th className="text-left  px-3 py-2 font-medium">AHRI Ref</th>
                    <th className="w-10"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {specs.map((s: any, i: number) => (
                    <tr key={i}>
                      <td className="px-3 py-2">
                        <div className="font-medium font-mono text-[11px]">{s.condenser_model || s.generic_id}</div>
                        <div className="text-muted-foreground text-[10px]">
                          {s.trade_name || s.description} — {s.manufacturer || "—"}
                        </div>
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">{s.product_type || "—"}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{s.capacity_btu != null ? s.capacity_btu.toLocaleString() : "—"}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{s.seer ?? "—"}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{s.hspf ?? "—"}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{s.eer95 ?? "—"}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{s.afue ?? "—"}</td>
                      <td className="px-3 py-2 font-mono text-[10px] text-muted-foreground">{s.ari_refno && s.ari_refno !== "0" ? s.ari_refno : "—"}</td>
                      {snipeTd({ ref: `row:spec:${s.condenser_model || s.generic_id}-${i}`,
                        label: String(s.condenser_model || s.generic_id || "spec").slice(0, 24),
                        kind: "row", data: s })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        );
      })()}

      {/* Edit drawer */}
      <EditLineDrawer
        open={editingIndex !== null}
        onOpenChange={(next) => { if (!next) setEditingIndex(null); }}
        clientId={clientId}
        line={editingLine}
        onSaved={(saved) => {
          if (editingIndex == null) return;
          // Build the optimistic patch from the persisted override row.
          // Empty/null fields on the saved row mean 'don't change',
          // which we represent by skipping that key in the patch.
          const patch: Record<string, any> = {
            override_id:         saved.id ?? null,
            override_updated_at: saved.updated_at ?? null,
            override_updated_by: saved.updated_by ?? null,
          };
          if (saved.corrected_sku) patch.sku = saved.corrected_sku;
          if (saved.corrected_supplier) patch.manufacturer = saved.corrected_supplier;
          if (saved.unit_price != null) {
            const li = (bom.line_items as any[])[editingIndex];
            const qty = li.quantity ?? 0;
            const markupPct = li.markup_pct ?? 0;
            patch.unit_cost  = saved.unit_price;
            patch.total_cost = Math.round(saved.unit_price * qty * 100) / 100;
            const newUnitPrice = Math.round(saved.unit_price * (1 + markupPct / 100) * 100) / 100;
            patch.unit_price  = newUnitPrice;
            patch.total_price = Math.round(newUnitPrice * qty * 100) / 100;
          }
          // Source promotion: passthrough lines become manual once
          // edited. mapped/dfunit/discovered stay tagged where they
          // were (the override applies silently).
          const li = (bom.line_items as any[])[editingIndex];
          if (li.source === "wrightsoft_passthrough"
              || li.source === "wrightsoft_discovered") {
            patch.source = "wrightsoft_manual";
          }
          onLineUpdated(editingIndex, patch);
        }}
      />

      {/* Day-16 — bulk price-only modal for the "fix the $0 lines" flow */}
      <BulkPriceDialog
        open={bulkOpen}
        onOpenChange={setBulkOpen}
        items={(bom.line_items as any[]) ?? []}
        clientId={clientId}
        onSave={(absIdx, price) => savePriceForLine(absIdx, price)}
      />

      {/* Day-22 — chat agent sidebar. Applying a proposed price runs
          the same savePriceForLine → contractor-override path as the
          drawer, so chat answers are learned once and reused. */}
      <BomChatSidebar
        clientId={clientId}
        runId={(bom as any).run_id}
        onApplyPatch={onApplyPatch}
        onRegenerate={onRegenerate}
        openSignal={chatOpenSignal}
        onOpenChange={onChatOpenChange}
        snipes={snipes}
        onRemoveSnipe={(ref) => setSnipes((p) => p.filter((s) => s.ref !== ref))}
        onClearSnipes={() => setSnipes([])}
        bom={{
          line_items: (bom.line_items as any[])?.map((li: any) => ({
            sku: li.sku ?? li.generic_id,
            description: li.description,
            quantity: li.quantity,
            unit_cost: li.unit_cost,
            unit_price: li.unit_price,
            manufacturer: li.manufacturer ?? li.src,
            section: li.section,
            source: li.source,
          })),
          totals: (bom as any).totals,
          source_pipeline: (bom as any).source_pipeline,
        }}
        onApplyPrice={(sku, price) => {
          const idx = (bom.line_items as any[]).findIndex(
            (li: any) => (li.sku ?? li.generic_id) === sku,
          );
          if (idx < 0) return false;
          savePriceForLine(idx, price);
          return true;
        }}
      />
    </div>
  );
}

function SectionBlock({
  section, items, subtotal, startIndex, onEditLine,
  onInlinePriceSave, pricingClientId, onSnipe,
}: {
  section: string;
  items: any[];
  subtotal: number;
  startIndex: number;
  onEditLine: (absoluteIndex: number) => void;
  onInlinePriceSave: (absoluteIndex: number, price: number) => void;
  pricingClientId: string;
  onSnipe: (s: Snipe) => void;
}) {
  return (
    <>
      <tr className="bg-muted/40">
        <td colSpan={9} className="px-3 py-1.5 font-semibold text-[11px] uppercase tracking-wide text-muted-foreground">
          {section}
          <span className="ml-2 text-muted-foreground/70 normal-case font-normal">
            · {items.length} line{items.length === 1 ? "" : "s"}
          </span>
        </td>
        <td className="w-10 px-0 py-1.5 text-center align-middle">
          <button className="opacity-30 hover:opacity-100 transition-opacity align-middle"
                  title={`Reference the "${section}" section in the chat`}
                  onClick={(e) => { e.stopPropagation(); onSnipe({
                    ref: `table:sec:${section}`, label: section.slice(0, 24),
                    kind: "table", data: items,
                  }); }}>
            <Crosshair className="w-3.5 h-3.5" />
          </button>
        </td>
      </tr>
      {items.map((li, i) => {
        const isMapped = li.source === "wrightsoft_mapped"
                      || li.source === "wrightsoft_dfunit"
                      || li.source === "wrightsoft_passthrough"
                      || li.source === "wrightsoft_discovered"
                      || li.source === "wrightsoft_manual";
        const isEdited = !!li.override_id || li.source === "wrightsoft_manual";
        const linePrice = li.unit_price ?? li.unit_cost ?? 0;
        // Day-17 — three pricing states (not two):
        //   confirmedZero : price 0 AND an override row exists → user
        //                   explicitly accepted $0. Render neutral.
        //   needsPrice    : price 0 AND no override row → contractor
        //                   pricing hasn't been entered. Render rose.
        //   priced        : > 0. Normal.
        const confirmedZero = linePrice === 0 && !!li.override_id;
        const needsPrice    = linePrice === 0 && !li.override_id;
        return (
          <tr
            key={i}
            onClick={() => onEditLine(startIndex + i)}
            className={cn(
              "hover:bg-emerald-500/[0.06] cursor-pointer transition-colors",
              !isMapped && "bg-amber-500/[0.04]",
              isEdited && "bg-emerald-500/[0.04]",
              needsPrice && "bg-rose-500/[0.05]",
              confirmedZero && "bg-slate-500/[0.03]",
            )}
            title="Click to edit SKU / supplier / price"
          >
            <td className="px-3 py-1.5 text-muted-foreground">{startIndex + i + 1}</td>
            <td className="px-3 py-1.5 font-mono text-[11px]">
              {li.generic_id ?? "—"}
              {isEdited && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="ml-1 inline-flex items-center text-emerald-600">
                      <ShieldCheck className="w-3 h-3" />
                    </span>
                  </TooltipTrigger>
                  <TooltipContent className="text-xs">
                    Edited{li.override_updated_by ? ` by ${li.override_updated_by}` : ""}
                  </TooltipContent>
                </Tooltip>
              )}
            </td>
            <td className="px-3 py-1.5 max-w-[280px] truncate">
              {li.description}
            </td>
            <td className="px-3 py-1.5">
              <WrightsoftSourceBadge source={li.source} />
              {li.non_standard_fitting && (
                <Badge
                  variant="outline"
                  className="ml-1 text-[10px] border-amber-500/60 bg-amber-50 text-amber-800 dark:bg-amber-950/30 dark:text-amber-300"
                  title="Fitting code is not in Tom's standard template"
                >
                  non-standard
                </Badge>
              )}
              {li.ahri_spec && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Badge
                      variant="outline"
                      className="ml-1 text-[10px] border-sky-500/60 bg-sky-50 text-sky-800 dark:bg-sky-950/30 dark:text-sky-300 cursor-help"
                    >
                      AHRI
                    </Badge>
                  </TooltipTrigger>
                  <TooltipContent className="text-xs space-y-0.5">
                    <div className="font-medium">{li.ahri_spec.trade_name || li.ahri_spec.condenser_model}</div>
                    <div>Mfr: {li.ahri_spec.manufacturer ?? "—"} ({li.ahri_spec.product_type ?? "—"})</div>
                    {li.ahri_spec.capacity_btu != null && <div>Capacity: {li.ahri_spec.capacity_btu} BTU</div>}
                    {li.ahri_spec.seer != null && <div>SEER: {li.ahri_spec.seer}</div>}
                    {li.ahri_spec.hspf != null && <div>HSPF: {li.ahri_spec.hspf}</div>}
                    {li.ahri_spec.eer95 != null && <div>EER95: {li.ahri_spec.eer95}</div>}
                    {li.ahri_spec.afue != null && <div>AFUE: {li.ahri_spec.afue}</div>}
                    {li.ahri_spec.ari_refno && li.ahri_spec.ari_refno !== "0" && (
                      <div>AHRI Ref: {li.ahri_spec.ari_refno}</div>
                    )}
                  </TooltipContent>
                </Tooltip>
              )}
            </td>
            <td className="px-3 py-1.5 font-mono text-[11px]">
              {li.manufacturer ?? (
                <Badge variant="outline" className="text-[10px] border-amber-500/40 text-amber-700 dark:text-amber-400">
                  unmapped
                </Badge>
              )}
            </td>
            <td className="px-3 py-1.5 font-mono text-[11px]">{li.sku ?? "—"}</td>
            <td className="px-3 py-1.5 text-right">{li.quantity} {li.unit}</td>
            <td className="px-3 py-1.5 text-right">
              <InlinePriceCell
                value={li.unit_cost ?? 0}
                needsPrice={needsPrice}
                confirmedZero={confirmedZero}
                onSave={(price) => onInlinePriceSave(startIndex + i, price)}
              />
            </td>
            <td className="px-3 py-1.5 text-right font-semibold">
              ${(li.total_price ?? li.total_cost ?? 0).toFixed(2)}
            </td>
            <td className="w-10 px-0 py-1.5 text-center align-middle">
              <button className="opacity-30 hover:opacity-100 transition-opacity align-middle"
                      title={`Reference "${li.sku ?? li.generic_id ?? li.description}" in the chat`}
                      onClick={(e) => { e.stopPropagation(); onSnipe({
                        ref: `row:li:${li.sku ?? li.generic_id ?? startIndex + i}`,
                        label: String(li.sku ?? li.generic_id ?? "line").slice(0, 24),
                        kind: "row", data: li,
                      }); }}>
                <Crosshair className="w-3.5 h-3.5" />
              </button>
            </td>
          </tr>
        );
      })}
      <tr className="bg-muted/20 border-t border-border/60">
        <td colSpan={8} className="px-3 py-1.5 text-right font-medium text-muted-foreground">
          Subtotal — {section}
        </td>
        <td className="px-3 py-1.5 text-right font-bold">
          ${subtotal.toFixed(2)}
        </td>
        <td className="w-10"></td>
      </tr>
    </>
  );
}

function StatCard({ label, value, tone }: {
  label: string; value: string; tone?: "emerald" | "amber";
}) {
  const ring = tone === "emerald" ? "border-emerald-500/30" :
               tone === "amber"   ? "border-amber-500/30" :
               "";
  return (
    <Card className={cn("border", ring)}>
      <CardContent className="p-3">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="text-lg font-bold mt-0.5">{value}</p>
      </CardContent>
    </Card>
  );
}


// ─── Source badge for the Wrightsoft BOM result table ──────────────
//
// One badge per provenance type emitted by /from-wrightsoft. Hover
// reveals the long-form explanation so reviewers don't have to
// remember what "discovered" vs "passthrough" means.
//
// Single source of truth for these copy strings — if the backend
// renames a source, only this map needs to change.
const WSF_SOURCE_META: Record<string, {
  label: string;
  cls:   string;
  title: string;
  body:  string;
}> = {
  wrightsoft_mapped: {
    label: "Mapped",
    cls:   "border-emerald-600/40 text-emerald-700 dark:text-emerald-400",
    title: "Catalog-mapped",
    body:  "Generic ID matched Tom's bundled mapped_parts.csv. " +
           "Supplier picked by contractor preference; fully deterministic.",
  },
  wrightsoft_dfunit: {
    label: "Equipment",
    cls:   "border-violet-500/40 text-violet-700 dark:text-violet-400",
    title: "Equipment library hit",
    body:  "SKU matches a model in Tom's DFUnit equipment library. " +
           "Carries full spec data (capacity, dimensions, weight).",
  },
  wrightsoft_passthrough: {
    label: "From file",
    cls:   "border-sky-500/40 text-sky-700 dark:text-sky-400",
    title: "Straight from Wrightsoft",
    body:  "Wrightsoft's Src+Name columns gave us supplier and SKU " +
           "directly — first time we've seen this combo. Trust level: " +
           "same as Wrightsoft itself.",
  },
  wrightsoft_discovered: {
    label: "Known",
    cls:   "border-teal-500/40 text-teal-700 dark:text-teal-400",
    title: "Previously seen",
    body:  "This (supplier, SKU) combo has flowed through the pipeline " +
           "before — it's now in our discovered_mappings table and " +
           "auto-recognized on every future run.",
  },
  wrightsoft_manual: {
    label: "Edited",
    cls:   "border-amber-500/40 text-amber-700 dark:text-amber-400",
    title: "Human override",
    body:  "Someone on the team corrected this line (SKU, supplier, " +
           "or unit price). Override is per-contractor and applies to " +
           "every future BOM run for them.",
  },
  wrightsoft_unmapped: {
    label: "Unmapped",
    cls:   "border-rose-500/40 text-rose-700 dark:text-rose-400",
    title: "No SKU info",
    body:  "Generic ID isn't in our catalog AND no Src column was " +
           "provided. Lands in the SKU Backlog — Richard's team can " +
           "encode it manually via the edit drawer.",
  },
};

function WrightsoftSourceBadge({ source }: { source?: string | null }) {
  const meta = WSF_SOURCE_META[source ?? ""] ?? {
    label: source ?? "—",
    cls:   "border-muted-foreground/30 text-muted-foreground",
    title: "Unknown source",
    body:  `Source tag "${source ?? ""}" isn't recognized by the SPA. ` +
           "Probably a backend change that hasn't been reflected here yet.",
  };
  return (
    <Tooltip delayDuration={150}>
      <TooltipTrigger asChild>
        <Badge
          variant="outline"
          className={cn("text-[10px] cursor-help font-normal", meta.cls)}
          onClick={(e) => e.stopPropagation()} // don't open the edit drawer
        >
          {meta.label}
        </Badge>
      </TooltipTrigger>
      <TooltipContent side="right" className="max-w-xs text-xs">
        <div className="font-semibold mb-0.5">{meta.title}</div>
        <div className="text-muted-foreground">{meta.body}</div>
      </TooltipContent>
    </Tooltip>
  );
}


// ─── Inline price-only cell editor (Day-16) ────────────────────────
//
// Click the cell on a $0 line → input appears → enter/blur saves.
// Click on a priced line → does nothing (drawer still opens via row).
// Stops propagation so the row's drawer-open handler doesn't fire.

function InlinePriceCell({
  value, needsPrice, confirmedZero, onSave,
}: {
  value: number;
  needsPrice: boolean;
  confirmedZero?: boolean;
  onSave: (price: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value.toFixed(2));

  useEffect(() => {
    setDraft(value.toFixed(2));
  }, [value]);

  const commit = () => {
    setEditing(false);
    const n = parseFloat(draft);
    if (!Number.isFinite(n) || n < 0 || n === value) return;
    onSave(n);
  };

  if (editing) {
    return (
      <Input
        autoFocus
        type="number"
        step="0.01"
        min="0"
        value={draft}
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") { setEditing(false); setDraft(value.toFixed(2)); }
        }}
        className="h-7 w-24 ml-auto text-right tabular-nums"
      />
    );
  }

  if (confirmedZero) {
    return (
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setEditing(true); }}
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border border-slate-300 bg-slate-50 text-slate-600 hover:bg-slate-100 dark:bg-slate-900/40 dark:text-slate-400 dark:border-slate-700"
        title="$0 confirmed. Click to enter a real price instead."
      >
        <CheckCircle2 className="w-2.5 h-2.5" />
        $0 confirmed
      </button>
    );
  }

  if (needsPrice) {
    return (
      <span className="inline-flex items-center gap-1">
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); setEditing(true); }}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border border-rose-400/60 bg-rose-50 text-rose-700 hover:bg-rose-100 dark:bg-rose-950/30 dark:text-rose-300 dark:border-rose-700/40"
          title="Click to enter contractor's price"
        >
          <Pencil className="w-2.5 h-2.5" />
          needs price
        </button>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onSave(0); }}
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border border-slate-300 text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800"
          title="Confirm this line is intentionally $0 (e.g. supplied free, included in another line)"
        >
          $0 OK
        </button>
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); setEditing(true); }}
      className="hover:underline tabular-nums"
      title="Click to edit price"
    >
      ${value.toFixed(2)}
    </button>
  );
}


// ─── Bulk price modal (Day-16) ─────────────────────────────────────
//
// One pane listing every $0 line for the current BOM with an editable
// price input. Save all → fires individual upserts via the parent's
// onSave callback (which handles the toast + optimistic line update).
// Lighter than the EditLineDrawer because price is all most reviewers
// care about for these lines.

function BulkPriceDialog({
  open, onOpenChange, items, clientId, onSave,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  items: any[];
  clientId: string;
  onSave: (absIdx: number, price: number) => void;
}) {
  // Day-17 — only show genuinely-unpriced lines (price 0 AND no
  // override). Lines already confirmed as $0 drop out of this dialog
  // so re-opens don't keep showing the same already-handled rows.
  const unpriced = items
    .map((li, idx) => ({ li, idx }))
    .filter(({ li }) =>
      (li.unit_price ?? li.unit_cost ?? 0) === 0 && !li.override_id,
    );
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  // Day-17 — per-row "confirm $0" toggle. When checked, the dialog
  // saves price=0 for that row regardless of what's in the draft.
  const [confirmZero, setConfirmZero] = useState<Record<number, boolean>>({});

  // Reset drafts + confirms when the modal opens
  useEffect(() => {
    if (open) {
      setDrafts({});
      setConfirmZero({});
    }
  }, [open]);

  const saveAll = () => {
    let saved = 0;
    for (const { idx } of unpriced) {
      if (confirmZero[idx]) {
        onSave(idx, 0);
        saved++;
        continue;
      }
      const raw = drafts[idx];
      if (!raw) continue;
      const n = parseFloat(raw);
      if (!Number.isFinite(n) || n <= 0) continue;
      onSave(idx, n);
      saved++;
    }
    if (saved > 0) onOpenChange(false);
  };

  const confirmAllRemaining = () => {
    // Mark every row that has neither a draft nor a confirm-toggle
    // as $0-confirmed. Lets the user clear out commodity stubs in
    // one click after pricing the items that need a real number.
    const next: Record<number, boolean> = { ...confirmZero };
    for (const { idx } of unpriced) {
      const raw = drafts[idx];
      const hasDraft = raw && parseFloat(raw) > 0;
      if (!hasDraft && !next[idx]) next[idx] = true;
    }
    setConfirmZero(next);
  };

  const draftedCount = unpriced.filter(({ idx }) =>
    drafts[idx] && parseFloat(drafts[idx]) > 0
  ).length;
  const confirmedCount = unpriced.filter(({ idx }) => confirmZero[idx]).length;
  const willSaveCount = draftedCount + confirmedCount;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>
            Price {unpriced.length} unpriced line{unpriced.length === 1 ? "" : "s"}
          </DialogTitle>
          <DialogDescription>
            Enter the contractor's price OR mark as "$0 OK" (intentionally free /
            included elsewhere). Saves apply to{" "}
            <code className="text-xs">{clientId}</code> and persist for all future BOMs.
          </DialogDescription>
        </DialogHeader>
        <div className="overflow-y-auto flex-1 border rounded-md">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground sticky top-0">
              <tr>
                <th className="text-left px-3 py-2 font-medium">SKU</th>
                <th className="text-left px-3 py-2 font-medium">Description</th>
                <th className="text-right px-3 py-2 font-medium">Qty</th>
                <th className="text-right px-3 py-2 font-medium">Unit price ($)</th>
                <th className="text-center px-3 py-2 font-medium">$0 OK</th>
              </tr>
            </thead>
            <tbody>
              {unpriced.map(({ li, idx }) => {
                const isConfirmed = !!confirmZero[idx];
                return (
                  <tr key={idx} className={cn("border-t", isConfirmed && "bg-slate-100/60 dark:bg-slate-900/30")}>
                    <td className="px-3 py-1.5 font-mono text-[11px]">
                      {(li.manufacturer || li.src || "WSF")}/{li.sku || li.generic_id}
                    </td>
                    <td className="px-3 py-1.5 max-w-[300px] truncate text-muted-foreground">
                      {li.description || "—"}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {li.quantity} {li.unit}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      <Input
                        type="number"
                        step="0.01"
                        min="0"
                        placeholder="0.00"
                        disabled={isConfirmed}
                        value={drafts[idx] ?? ""}
                        onChange={(e) =>
                          setDrafts((prev) => ({ ...prev, [idx]: e.target.value }))
                        }
                        className="h-7 w-24 ml-auto text-right tabular-nums"
                      />
                    </td>
                    <td className="px-3 py-1.5 text-center">
                      <input
                        type="checkbox"
                        checked={isConfirmed}
                        onChange={(e) =>
                          setConfirmZero((prev) => ({
                            ...prev,
                            [idx]: e.target.checked,
                          }))
                        }
                        className="h-4 w-4 cursor-pointer"
                        title="Mark this line as intentionally $0"
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {unpriced.length === 0 && (
            <div className="px-3 py-8 text-center text-sm italic text-muted-foreground">
              Nothing to price — every line either has a unit price or is already confirmed as $0.
            </div>
          )}
        </div>
        <DialogFooter className="flex items-center justify-between gap-3 sm:flex-row">
          <div className="text-xs text-muted-foreground mr-auto">
            {willSaveCount} of {unpriced.length} will save
            {confirmedCount > 0 && (
              <span className="ml-1 text-slate-600">({confirmedCount} as $0)</span>
            )}
          </div>
          <Button variant="outline" size="sm" onClick={confirmAllRemaining}
                  disabled={unpriced.length === 0}>
            Confirm rest as $0
          </Button>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={saveAll} disabled={willSaveCount === 0}>
            Save {willSaveCount > 0 ? `(${willSaveCount})` : ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
