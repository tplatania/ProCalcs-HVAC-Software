import { useState, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useLocation } from "wouter";
import {
  Upload,
  FileUp,
  CheckCircle2,
  XCircle,
  Cpu,
  FileText,
  Search,
  Eye,
  ArrowRight,
  RotateCcw,
  AlertCircle,
  Building2,
  Home,
  Wind,
  Layers,
  PackagePlus,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  useParseRup,
  useUpsertRupDuctTotals,
  storeParsedRup,
  type RupDesignData,
} from "@/lib/api-hooks";

// Pipeline state machine — drives the 4-step visual at the top of the page
// and the dropzone / preview layout below.
type PipelineStatus = "idle" | "parsing" | "parsed" | "error";

const PIPELINE_STEPS = [
  { key: "upload",  label: "Upload",   icon: Upload,    desc: "Drop a Wrightsoft .rup project file" },
  { key: "parse",   label: "Parse",    icon: Search,    desc: "Extract rooms, equipment, building info" },
  { key: "preview", label: "Preview",  icon: Eye,       desc: "Review parsed data before generating" },
  { key: "generate",label: "Generate", icon: Cpu,       desc: "Pick client profile, compute priced BOM" },
] as const;

type StepKey = (typeof PIPELINE_STEPS)[number]["key"];

function getStepState(step: StepKey, status: PipelineStatus): "idle" | "active" | "done" {
  if (status === "idle" || status === "error") return "idle";
  if (status === "parsing") {
    return step === "upload" ? "done" : step === "parse" ? "active" : "idle";
  }
  if (status === "parsed") {
    // upload + parse + preview all "done"; generate is the next step the
    // user navigates to via the Continue button.
    return step === "generate" ? "active" : "done";
  }
  return "idle";
}

function getProgressValue(status: PipelineStatus): number {
  // Bar represents progress of the work this page does (parsing the
  // .rup). Generate is the next page's job, so reaching "parsed" means
  // BOM Engine itself is done — show 100% to match user mental model
  // ("Parse complete" + a non-100 bar reads as "parse incomplete").
  // The 4-stage breadcrumb at the top still tracks Upload → Parse →
  // Preview → Generate as the workflow indicator.
  const map: Record<PipelineStatus, number> = {
    idle:    0,
    parsing: 45,
    parsed:  100,
    error:   0,
  };
  return map[status];
}

export default function BomEngine() {
  const [dragOver, setDragOver] = useState(false);
  const [status, setStatus] = useState<PipelineStatus>("idle");
  const [droppedFile, setDroppedFile] = useState<File | null>(null);
  const [parsed, setParsed] = useState<RupDesignData | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [, setLocation] = useLocation();

  // Day-14 Phase 4 — user-entered Wrightsoft Supply Actual Ln totals.
  // Key format: "${dir}:${type}:${size}", e.g. "round_supply:4" or
  // "rect_supply:12x10". Stored as strings so empty inputs render
  // correctly; coerced to numbers at submit time.
  const [knownLF, setKnownLF] = useState<Record<string, string>>({});

  const parseRup = useParseRup();
  const upsertDuctTotals = useUpsertRupDuctTotals();

  const runParse = (file: File) => {
    setDroppedFile(file);
    setParsed(null);
    setErrorMsg(null);
    setStatus("parsing");
    parseRup.mutate(file, {
      onSuccess: (data) => {
        setParsed(data);
        // Day-14 Phase 4 — pre-populate the form from cached totals
        // when the same RUP has been processed before. The backend
        // bundles cached totals into duct_summary.known_lengths_ft
        // on /parse-rup so the SPA doesn't need a second round trip.
        const cached = data.duct_summary?.known_lengths_ft;
        if (cached) {
          const pre: Record<string, string> = {};
          for (const dir of ["round_supply", "round_return",
                             "rect_supply", "rect_return"] as const) {
            const bucket = (cached as any)[dir] || {};
            for (const [size, lf] of Object.entries(bucket)) {
              const n = Number(lf);
              if (isFinite(n) && n > 0) pre[`${dir}:${size}`] = String(n);
            }
          }
          setKnownLF(pre);
        } else {
          setKnownLF({});  // reset form on every new parse
        }
        setStatus("parsed");
      },
      onError: (err) => {
        setErrorMsg(err?.error ?? "Failed to parse .rup file");
        setStatus("error");
      },
    });
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) runParse(file);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) runParse(file);
  };

  const reset = () => {
    setStatus("idle");
    setParsed(null);
    setDroppedFile(null);
    setErrorMsg(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const handleContinue = () => {
    if (!parsed || !droppedFile) return;
    // Day-14 Phase 4 — bundle any user-entered known-LF totals into
    // designData.duct_summary.known_lengths_ft so the backend's
    // /generate endpoint can emit deterministic duct lines.
    const buckets: Record<string, Record<string, number>> = {
      round_supply: {}, round_return: {},
      rect_supply: {},  rect_return: {},
    };
    for (const [key, val] of Object.entries(knownLF)) {
      const n = Number(val);
      if (!isFinite(n) || n <= 0) continue;
      const [dir, size] = key.split(":");
      if (!buckets[dir]) continue;
      buckets[dir][size] = n;
    }
    const anyKnown = Object.values(buckets).some(b => Object.keys(b).length > 0);
    const knownLengthsFt = anyKnown
      ? Object.fromEntries(
          Object.entries(buckets).filter(([, v]) => Object.keys(v).length > 0)
        )
      : null;
    const merged: RupDesignData = knownLengthsFt
      ? {
          ...parsed,
          duct_summary: {
            ...(parsed.duct_summary || {}),
            known_lengths_ft: knownLengthsFt as any,
          },
        }
      : parsed;
    storeParsedRup(merged, droppedFile.name);

    // Day-14 Phase 4 — persist the totals so a re-upload of this same
    // RUP pre-fills the form. Fire-and-forget — a save failure is
    // logged but doesn't block navigation (the BOM still generates
    // with the in-session totals).
    if (knownLengthsFt && parsed.rup_hash) {
      upsertDuctTotals.mutate(
        {
          rup_hash: parsed.rup_hash,
          known_lengths_ft: knownLengthsFt as any,
          source_filename: droppedFile.name,
        },
        {
          onError: (err) => {
            console.warn("rup-duct-totals cache save failed:", err?.error);
          },
        },
      );
    }

    setLocation("/bom-output");
  };

  const isRunning = status === "parsing";
  const isParsed = status === "parsed";
  const isError = status === "error";

  // Derived preview stats — computed only when we have parsed data
  const stats = parsed
    ? {
        equipmentCount: parsed.equipment?.length ?? 0,
        roomCount: parsed.rooms?.length ?? 0,
        buildingType: parsed.building?.type ?? "unknown",
        ductLocation: parsed.building?.duct_location ?? "unknown",
        totalCfm: parsed.equipment?.reduce(
          (sum, e) => sum + (e.cfm ?? 0),
          0
        ) ?? 0,
        sectionCount: parsed.metadata?.section_count ?? 0,
      }
    : null;

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">BOM Engine (AI fallback path)</h1>
        <p className="text-muted-foreground text-sm mt-1 max-w-3xl">
          Upload a Wrightsoft Right-Suite Universal{" "}
          <code className="text-xs bg-muted px-1 py-0.5 rounded">.rup</code>{" "}
          project file. The parser extracts rooms, equipment, and building
          info, then the AI estimates quantities and prices. Use this path
          when you don't have Wrightsoft's own BOM export in hand. For a
          deterministic BOM with real manufacturer SKUs, prefer the{" "}
          <a className="underline" href="/diagnostics/wrightsoft-bom">
            Wrightsoft BOM upload
          </a>{" "}
          path.
        </p>
      </div>

      {/* Pipeline overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {PIPELINE_STEPS.map((step) => {
          const state = getStepState(step.key, status);
          return (
            <Card
              key={step.key}
              className={cn(
                "relative overflow-hidden transition-all",
                state === "active" && "ring-2 ring-primary/40 shadow-md",
                state === "done" && "bg-green-500/5 border-green-500/20"
              )}
            >
              <CardContent className="p-4">
                <div className="flex items-start justify-between mb-2">
                  <div
                    className={cn(
                      "w-8 h-8 rounded flex items-center justify-center",
                      state === "done"
                        ? "bg-green-500/15 text-green-500"
                        : state === "active"
                        ? "bg-primary/15 text-primary"
                        : "bg-muted text-muted-foreground"
                    )}
                  >
                    {state === "done" ? (
                      <CheckCircle2 className="w-4 h-4" />
                    ) : (
                      <step.icon className="w-4 h-4" />
                    )}
                  </div>
                </div>
                <p
                  className={cn(
                    "font-semibold text-xs",
                    state === "active"
                      ? "text-primary"
                      : state === "done"
                      ? "text-green-600"
                      : "text-foreground"
                  )}
                >
                  {step.label}
                </p>
                <p className="text-[10px] text-muted-foreground mt-0.5 leading-snug">
                  {step.desc}
                </p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Upload + Preview panel */}
        <div className="lg:col-span-3 space-y-4">
          {/* Drop zone */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <FileUp className="w-4 h-4 text-muted-foreground" />
                File Input
              </CardTitle>
              <CardDescription>
                Drop a <code className="text-xs">.rup</code> file, or click to browse
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => !isRunning && fileRef.current?.click()}
                className={cn(
                  "border-2 border-dashed rounded-lg p-10 text-center transition-all cursor-pointer select-none",
                  dragOver
                    ? "border-primary bg-primary/5 scale-[1.01]"
                    : "border-border hover:border-primary/50 hover:bg-muted/30",
                  isRunning && "pointer-events-none opacity-60"
                )}
              >
                <input
                  ref={fileRef}
                  type="file"
                  accept=".rup"
                  className="hidden"
                  onChange={handleFileChange}
                />
                <Upload
                  className={cn(
                    "w-10 h-10 mx-auto mb-3",
                    dragOver ? "text-primary" : "text-muted-foreground/50"
                  )}
                />
                {droppedFile ? (
                  <p className="font-medium text-sm text-foreground">
                    {droppedFile.name}{" "}
                    <span className="text-muted-foreground text-xs">
                      ({(droppedFile.size / 1024 / 1024).toFixed(1)} MB)
                    </span>
                  </p>
                ) : (
                  <>
                    <p className="font-medium text-sm">Drop .rup here</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Wrightsoft Right-Suite Universal project files
                    </p>
                  </>
                )}
              </div>

              {/* Progress bar */}
              {(isRunning || isParsed) && (
                <div className="mt-4 space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">
                      {isParsed ? "Parse complete — review and continue" : "Parsing .rup binary..."}
                    </span>
                    <span
                      className={cn(
                        "font-medium",
                        isParsed ? "text-green-600" : "text-primary"
                      )}
                    >
                      {getProgressValue(status)}%
                    </span>
                  </div>
                  <Progress value={getProgressValue(status)} className="h-1.5" />
                </div>
              )}

              {(isParsed || isError) && (
                <Button variant="outline" size="sm" className="mt-3 w-full" onClick={reset}>
                  <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
                  {isError ? "Try Another File" : "Process Another File"}
                </Button>
              )}
            </CardContent>
          </Card>

          {/* Error card */}
          {isError && (
            <Card className="border-destructive/30 bg-destructive/5">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2 text-destructive">
                  <XCircle className="w-4 h-4" />
                  Parse Failed
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-destructive">{errorMsg}</p>
                <p className="text-xs text-muted-foreground mt-2">
                  Make sure the file is a valid Wrightsoft Right-Suite Universal .rup export.
                </p>
              </CardContent>
            </Card>
          )}

          {/* Deterministic-pipeline nudge — Day-10. Shows whenever the
              parser confirms the binary doesn't carry a usable BOM
              catalog (which is every Wrightsoft file we've sampled).
              Steers the designer to the deterministic Wrightsoft BOM
              upload BEFORE they kick off AI estimation. The AI path
              stays available right below — user picks. */}
          {isParsed && parsed?.catalog_xref && !parsed.catalog_xref.bom_is_in_binary && (
            <Card className="border-amber-500/40 bg-amber-500/[0.04]">
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2 text-amber-700 dark:text-amber-400">
                  <AlertCircle className="w-4 h-4" />
                  This .rup binary does not carry a BOM
                </CardTitle>
                <CardDescription className="text-xs">
                  {parsed.catalog_xref.generic_ids_found} of{" "}
                  {parsed.catalog_xref.generic_ids_in_catalog.toLocaleString()}{" "}
                  Wrightsoft catalog part IDs found in this file. Wrightsoft
                  computes BOMs at output time — they're not stored in
                  the project file.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="text-xs text-muted-foreground bg-background/60 border rounded p-3 space-y-2">
                  <p className="font-medium text-foreground inline-flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-primary" />
                    Recommended: deterministic Wrightsoft BOM upload
                  </p>
                  <p>
                    In Wrightsoft, export this project's BOM (Reports →
                    Bill of Materials → CSV/XLS), then upload it on the
                    Wrightsoft BOM page. Each part is translated through{" "}
                    <span className="font-mono">mapped_parts.csv</span> into
                    the contractor's actual manufacturer SKU. No AI, no
                    guessing.
                  </p>
                </div>
                <div className="flex gap-2 flex-wrap">
                  <Button
                    size="sm"
                    onClick={() => setLocation("/diagnostics/wrightsoft-bom")}
                  >
                    <PackagePlus className="w-3.5 h-3.5 mr-1.5" />
                    Use deterministic upload
                  </Button>
                  <p className="text-xs text-muted-foreground self-center">
                    — or continue below with the AI-estimated fallback
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Preview card — parsed project data */}
          {isParsed && parsed && stats && (
            <Card className="border-green-500/20 bg-green-500/5">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2 text-green-700">
                    <CheckCircle2 className="w-4 h-4" />
                    Parse Complete
                  </CardTitle>
                  <Badge variant="outline" className="text-green-600 border-green-500/30 text-xs">
                    {stats.sectionCount} sections
                  </Badge>
                </div>
                <CardDescription>
                  {parsed.project?.name ?? droppedFile?.name ?? "Parsed project"}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {/* Stat grid */}
                <div className="grid grid-cols-4 gap-3 mb-4">
                  {[
                    { label: "Equipment", value: stats.equipmentCount, color: "text-purple-600" },
                    { label: "Rooms", value: stats.roomCount, color: "text-blue-600" },
                    { label: "Total CFM", value: stats.totalCfm || "—", color: "text-amber-600" },
                    { label: "Building", value: stats.buildingType.replace("_", " "), color: "text-green-600" },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="text-center">
                      <p className={cn("text-xl font-bold", color)}>{value}</p>
                      <p className="text-[10px] text-muted-foreground mt-0.5">{label}</p>
                    </div>
                  ))}
                </div>

                {/* Project metadata row */}
                {parsed.project && (
                  <div className="grid grid-cols-2 gap-2 mb-4 text-xs">
                    {parsed.project.address && (
                      <div className="flex items-center gap-1.5">
                        <Home className="w-3 h-3 text-muted-foreground" />
                        <span className="text-muted-foreground">Address:</span>
                        <span className="font-medium truncate">
                          {parsed.project.address}
                          {parsed.project.city ? `, ${parsed.project.city}` : ""}
                          {parsed.project.zip ? ` ${parsed.project.zip}` : ""}
                        </span>
                      </div>
                    )}
                    {parsed.project.contractor?.name && (
                      <div className="flex items-center gap-1.5">
                        <Building2 className="w-3 h-3 text-muted-foreground" />
                        <span className="text-muted-foreground">Contractor:</span>
                        <span className="font-medium truncate">
                          {parsed.project.contractor.name}
                        </span>
                      </div>
                    )}
                    <div className="flex items-center gap-1.5">
                      <Wind className="w-3 h-3 text-muted-foreground" />
                      <span className="text-muted-foreground">Ducts:</span>
                      <span className="font-medium">{stats.ductLocation}</span>
                    </div>
                    {parsed.project.date && (
                      <div className="flex items-center gap-1.5">
                        <FileText className="w-3 h-3 text-muted-foreground" />
                        <span className="text-muted-foreground">Date:</span>
                        <span className="font-medium">{parsed.project.date}</span>
                      </div>
                    )}
                  </div>
                )}

                {/* Day-14 Phase 4 — known-duct-LF paste form. Optional.
                    Shows up only when the parser detected duct sizes.
                    When filled, the backend emits deterministic duct
                    lines from these totals — no AI estimation. */}
                <KnownDuctLengthsForm
                  ductSummary={parsed.duct_summary}
                  value={knownLF}
                  onChange={setKnownLF}
                />

                <Button size="sm" className="w-full" onClick={handleContinue}>
                  Continue to BOM Output
                  <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
                </Button>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right panel — Rooms list (idle) or raw_rup_context preview (parsed) */}
        <div className="lg:col-span-2">
          <Card className="h-full">
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Layers className="w-4 h-4 text-muted-foreground" />
                {isParsed ? "Extracted Rooms" : "Ready to Parse"}
              </CardTitle>
              <CardDescription>
                {isParsed
                  ? `${stats?.roomCount ?? 0} rooms extracted from the .rup file`
                  : "Parsed room list appears here after upload"}
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              {isParsed && parsed?.rooms && parsed.rooms.length > 0 ? (
                <ScrollArea className="h-[420px] px-4 pb-4">
                  <div className="space-y-1">
                    {parsed.rooms.map((room, i) => (
                      <div
                        key={`${room.name}-${i}`}
                        className="flex items-center gap-2 rounded-md px-2.5 py-2 text-xs bg-muted/30"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5 text-green-500 shrink-0" />
                        <span className="font-medium truncate flex-1">{room.name}</span>
                        {room.ahu && (
                          <span className="text-muted-foreground text-[10px] font-mono">
                            {room.ahu}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              ) : (
                <div className="flex flex-col items-center justify-center h-[420px] text-center px-6">
                  <Search className="w-10 h-10 text-muted-foreground/25 mb-3" />
                  <p className="text-sm text-muted-foreground">
                    Room list appears here after parsing.
                  </p>
                  <p className="text-xs text-muted-foreground/60 mt-1">
                    Each room in the .rup is mapped to its assigned air handler (AHU).
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Info callout */}
      <Card className="border-blue-500/20 bg-blue-500/5">
        <CardContent className="p-4 flex gap-3">
          <AlertCircle className="w-4 h-4 text-blue-400 mt-0.5 shrink-0" />
          <div className="text-xs text-muted-foreground space-y-1">
            <p>
              <span className="font-semibold text-foreground">
                Hybrid extraction strategy.
              </span>{" "}
              Structured fields (building type, duct location, rooms, equipment) are extracted
              directly from the .rup binary. Duct linear footage, fitting counts, and register
              quantities are left empty — the BOM engine's AI pass infers them from the narrative
              context baked into the parser output.
            </p>
            <p>
              Parser implementation lives in{" "}
              <code className="font-mono bg-muted px-1 rounded">
                procalcs-bom/backend/utils/rup_parser.py
              </code>
              . Wrightsoft Right-Suite Universal v25.x is the tested format.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}


// ─── Known-duct-LF paste form (Day-14 Phase 4) ─────────────────────
//
// Wrightsoft's report has a "Supply Actual Ln(ft)" + "Return Actual Ln(ft)"
// table that's the ground truth for duct linear footage. We can't crack
// it out of the .rup binary deterministically yet, so the simpler win
// is to let Richard's team paste those numbers in here. When filled,
// the backend emits one deterministic duct line per (size, direction)
// and the AI is told to skip all duct lines.

function KnownDuctLengthsForm({
  ductSummary,
  value,
  onChange,
}: {
  ductSummary: RupDesignData["duct_summary"];
  value: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
}) {
  const roundDiams = ductSummary?.round_diameters_present ?? [];
  const rectSizes  = ductSummary?.rect_sizes_present ?? [];

  // Skip rendering entirely on RUPs with no duct system at all
  // (commercial equipment-only projects, equipment swap-outs).
  if (roundDiams.length === 0 && rectSizes.length === 0) {
    return null;
  }

  const setVal = (key: string, v: string) => {
    onChange({ ...value, [key]: v });
  };

  const totalEntered = Object.values(value)
    .map(v => Number(v))
    .filter(n => isFinite(n) && n > 0)
    .reduce((a, b) => a + b, 0);

  return (
    <div className="rounded-md border border-primary/20 bg-primary/[0.03] p-3 mt-3 text-xs space-y-3">
      <div>
        <div className="flex items-baseline justify-between gap-2 flex-wrap">
          <p className="font-semibold text-sm">
            Known duct totals (optional)
          </p>
          {ductSummary?.known_lengths_cached_at && (
            <span className="text-[10px] text-emerald-700 dark:text-emerald-400">
              ✓ pre-filled from earlier upload
              {ductSummary.known_lengths_cached_by
                ? ` by ${ductSummary.known_lengths_cached_by}`
                : ""}
            </span>
          )}
        </div>
        <p className="text-muted-foreground mt-0.5 leading-snug">
          From Wrightsoft's report, two numbers per duct size: how many
          feet of <strong className="text-foreground">supply</strong> duct
          (air going TO rooms) and how many feet of{" "}
          <strong className="text-foreground">return</strong> duct (air
          coming back to the AHU). Wrightsoft labels these{" "}
          <em>Supply Actual Ln(ft)</em> and <em>Return Actual Ln(ft)</em> —
          paste those numbers verbatim. Decimals OK (e.g. 524.1).
          When provided, BOM duct lines come straight from these numbers —
          no AI estimation. Saved per-RUP so re-uploads of the same file
          remember your numbers.
        </p>
      </div>

      {roundDiams.length > 0 && (
        <div>
          <div className="font-medium text-muted-foreground mb-1">
            Round flex duct
          </div>
          {roundDiams.map((d) => (
            <div key={`round-${d}`} className="mb-2 last:mb-0">
              <div className="font-mono text-[11px] mb-0.5">
                {d}″ diameter
              </div>
              <div className="grid grid-cols-[80px,1fr,80px,1fr] gap-1.5 items-center">
                <label
                  className="text-[10px] text-muted-foreground text-right pr-1"
                  htmlFor={`r-sup-${d}`}
                >
                  Supply (ft)
                </label>
                <input
                  id={`r-sup-${d}`}
                  type="number" min="0" step="0.1"
                  className="h-7 px-2 text-right rounded border bg-background text-xs"
                  placeholder="—"
                  value={value[`round_supply:${d}`] ?? ""}
                  onChange={(e) => setVal(`round_supply:${d}`, e.target.value)}
                />
                <label
                  className="text-[10px] text-muted-foreground text-right pr-1"
                  htmlFor={`r-ret-${d}`}
                >
                  Return (ft)
                </label>
                <input
                  id={`r-ret-${d}`}
                  type="number" min="0" step="0.1"
                  className="h-7 px-2 text-right rounded border bg-background text-xs"
                  placeholder="—"
                  value={value[`round_return:${d}`] ?? ""}
                  onChange={(e) => setVal(`round_return:${d}`, e.target.value)}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {rectSizes.length > 0 && (
        <div>
          <div className="font-medium text-muted-foreground mb-1 mt-2">
            Rectangular duct
          </div>
          {rectSizes.map((s) => (
            <div key={`rect-${s}`} className="mb-2 last:mb-0">
              <div className="font-mono text-[11px] mb-0.5">
                {s}″ (W × H)
              </div>
              <div className="grid grid-cols-[80px,1fr,80px,1fr] gap-1.5 items-center">
                <label
                  className="text-[10px] text-muted-foreground text-right pr-1"
                  htmlFor={`x-sup-${s}`}
                >
                  Supply (ft)
                </label>
                <input
                  id={`x-sup-${s}`}
                  type="number" min="0" step="0.1"
                  className="h-7 px-2 text-right rounded border bg-background text-xs"
                  placeholder="—"
                  value={value[`rect_supply:${s}`] ?? ""}
                  onChange={(e) => setVal(`rect_supply:${s}`, e.target.value)}
                />
                <label
                  className="text-[10px] text-muted-foreground text-right pr-1"
                  htmlFor={`x-ret-${s}`}
                >
                  Return (ft)
                </label>
                <input
                  id={`x-ret-${s}`}
                  type="number" min="0" step="0.1"
                  className="h-7 px-2 text-right rounded border bg-background text-xs"
                  placeholder="—"
                  value={value[`rect_return:${s}`] ?? ""}
                  onChange={(e) => setVal(`rect_return:${s}`, e.target.value)}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {totalEntered > 0 && (
        <div className="pt-1 border-t flex items-center justify-between">
          <span className="text-muted-foreground">
            Total linear feet entered
          </span>
          <span className="font-semibold text-foreground">
            {totalEntered.toLocaleString("en-US", { maximumFractionDigits: 1 })} ft
          </span>
        </div>
      )}
    </div>
  );
}
