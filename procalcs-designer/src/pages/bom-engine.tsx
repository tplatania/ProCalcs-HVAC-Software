import { useState, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Upload,
  FileUp,
  CheckCircle2,
  XCircle,
  Clock,
  Cpu,
  Filter,
  Layers,
  ArrowRight,
  RotateCcw,
  Download,
  AlertCircle,
  FileText,
  Zap,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

type PipelineStatus = "idle" | "uploading" | "converting" | "filtering" | "generating" | "done" | "error";

interface BlockResult {
  name: string;
  action: "kept" | "stripped";
  reason: string;
  count: number;
}

interface ProcessingResult {
  filename: string;
  totalBlocks: number;
  keptBlocks: number;
  strippedBlocks: number;
  lineItems: number;
  duration: string;
  blocks: BlockResult[];
}

const PIPELINE_STEPS = [
  { key: "uploading",   label: "Upload DWG/DXF",    icon: Upload,   desc: "Receiving file from Designer Desktop" },
  { key: "converting",  label: "DWG → DXF",          icon: Layers,   desc: "ODA File Converter extracting geometry" },
  { key: "filtering",   label: "INSERT Filter",       icon: Filter,   desc: "Smart block classifier removing furniture/fixtures" },
  { key: "generating",  label: "BOM Generation",      icon: Zap,      desc: "AI reads duct, fittings, equipment, consumables" },
];

const MOCK_RESULT: ProcessingResult = {
  filename: "Beazer_LotA7_Mech.dwg",
  totalBlocks: 184,
  keptBlocks: 62,
  strippedBlocks: 122,
  lineItems: 47,
  duration: "3.2s",
  blocks: [
    { name: "DUCT_RND_6", action: "kept", reason: "Keyword match: duct", count: 18 },
    { name: "DUCT_RECT_12x8", action: "kept", reason: "Keyword match: duct", count: 9 },
    { name: "RTU_3TON", action: "kept", reason: "Keyword match: equipment", count: 1 },
    { name: "SUPPLY_GRILLE_10", action: "kept", reason: "Keyword match: supply", count: 14 },
    { name: "RETURN_AIR_12", action: "kept", reason: "Keyword match: return", count: 8 },
    { name: "FLEX_CONN_6", action: "kept", reason: "Keyword match: flex", count: 12 },
    { name: "SOFA_L_SHAPE", action: "stripped", reason: "Keyword: furniture", count: 3 },
    { name: "BED_QUEEN", action: "stripped", reason: "Keyword: furniture", count: 4 },
    { name: "DOOR_3068", action: "stripped", reason: "Keyword: door", count: 22 },
    { name: "WINDOW_3040", action: "stripped", reason: "Keyword: window", count: 18 },
    { name: "TOILET_STD", action: "stripped", reason: "Keyword: plumbing", count: 6 },
    { name: "SINK_LAV", action: "stripped", reason: "Keyword: plumbing", count: 8 },
    { name: "STAIR_STRAIGHT", action: "stripped", reason: "Keyword: stair", count: 2 },
    { name: "BLK_A7F2", action: "stripped", reason: "Generic — geometry analysis: arc+line → door signature", count: 59 },
  ],
};

const STEP_ORDER = ["uploading", "converting", "filtering", "generating"] as const;

function getStepState(step: string, currentStatus: PipelineStatus) {
  if (currentStatus === "idle" || currentStatus === "error") return "idle";
  if (currentStatus === "done") return "done";
  const stepIdx = STEP_ORDER.indexOf(step as typeof STEP_ORDER[number]);
  const currentIdx = STEP_ORDER.indexOf(currentStatus as typeof STEP_ORDER[number]);
  if (stepIdx < currentIdx) return "done";
  if (stepIdx === currentIdx) return "active";
  return "pending";
}

function getProgressValue(status: PipelineStatus) {
  const map: Record<PipelineStatus, number> = {
    idle: 0, uploading: 15, converting: 40, filtering: 65, generating: 85, done: 100, error: 0,
  };
  return map[status];
}

export default function BomEngine() {
  const [dragOver, setDragOver] = useState(false);
  const [status, setStatus] = useState<PipelineStatus>("idle");
  const [result, setResult] = useState<ProcessingResult | null>(null);
  const [droppedFile, setDroppedFile] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const runPipeline = (filename: string) => {
    setDroppedFile(filename);
    setResult(null);
    const steps: PipelineStatus[] = ["uploading", "converting", "filtering", "generating", "done"];
    let i = 0;
    const tick = () => {
      setStatus(steps[i]);
      i++;
      if (i < steps.length) {
        setTimeout(tick, i === 1 ? 800 : i === 2 ? 1100 : i === 3 ? 1400 : 600);
      } else {
        setResult(MOCK_RESULT);
      }
    };
    tick();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) runPipeline(file.name);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) runPipeline(file.name);
  };

  const reset = () => {
    setStatus("idle");
    setResult(null);
    setDroppedFile(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const isRunning = status !== "idle" && status !== "done" && status !== "error";
  const isDone = status === "done";

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">BOM Engine</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Upload a DWG or DXF file. The pipeline strips non-HVAC blocks, then the AI generates a full materials list.
        </p>
      </div>

      {/* Pipeline overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {PIPELINE_STEPS.map((step, idx) => {
          const state = getStepState(step.key, status);
          return (
            <Card key={step.key} className={cn(
              "relative overflow-hidden transition-all",
              state === "active" && "ring-2 ring-primary/40 shadow-md",
              state === "done" && "bg-green-500/5 border-green-500/20",
            )}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between mb-2">
                  <div className={cn(
                    "w-8 h-8 rounded flex items-center justify-center",
                    state === "done" ? "bg-green-500/15 text-green-500" :
                    state === "active" ? "bg-primary/15 text-primary" :
                    "bg-muted text-muted-foreground"
                  )}>
                    {state === "done" ? <CheckCircle2 className="w-4 h-4" /> : <step.icon className="w-4 h-4" />}
                  </div>
                  {idx < PIPELINE_STEPS.length - 1 && (
                    <ChevronRight className="w-3.5 h-3.5 text-border absolute right-2 top-1/2 -translate-y-1/2" />
                  )}
                </div>
                <p className={cn(
                  "font-semibold text-xs",
                  state === "active" ? "text-primary" : state === "done" ? "text-green-600" : "text-foreground"
                )}>
                  {step.label}
                </p>
                <p className="text-[10px] text-muted-foreground mt-0.5 leading-snug">{step.desc}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">

        {/* Upload + Progress panel */}
        <div className="lg:col-span-3 space-y-4">

          {/* Drop zone */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <FileUp className="w-4 h-4 text-muted-foreground" />
                File Input
              </CardTitle>
              <CardDescription>Drop a DWG or DXF file, or click to browse</CardDescription>
            </CardHeader>
            <CardContent>
              <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => !isRunning && fileRef.current?.click()}
                className={cn(
                  "border-2 border-dashed rounded-lg p-10 text-center transition-all cursor-pointer select-none",
                  dragOver ? "border-primary bg-primary/5 scale-[1.01]" : "border-border hover:border-primary/50 hover:bg-muted/30",
                  isRunning && "pointer-events-none opacity-60"
                )}
              >
                <input
                  ref={fileRef}
                  type="file"
                  accept=".dwg,.dxf"
                  className="hidden"
                  onChange={handleFileChange}
                />
                <Upload className={cn("w-10 h-10 mx-auto mb-3", dragOver ? "text-primary" : "text-muted-foreground/50")} />
                {droppedFile ? (
                  <p className="font-medium text-sm text-foreground">{droppedFile}</p>
                ) : (
                  <>
                    <p className="font-medium text-sm">Drop DWG or DXF here</p>
                    <p className="text-xs text-muted-foreground mt-1">Supports WrightSoft and AutoCAD exports</p>
                  </>
                )}
              </div>

              {/* Progress bar */}
              {(isRunning || isDone) && (
                <div className="mt-4 space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">
                      {isDone ? "Processing complete" : `Step: ${status.charAt(0).toUpperCase() + status.slice(1)}...`}
                    </span>
                    <span className={cn("font-medium", isDone ? "text-green-600" : "text-primary")}>
                      {getProgressValue(status)}%
                    </span>
                  </div>
                  <Progress value={getProgressValue(status)} className="h-1.5" />
                </div>
              )}

              {isDone && (
                <Button variant="outline" size="sm" className="mt-3 w-full" onClick={reset}>
                  <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
                  Process Another File
                </Button>
              )}
            </CardContent>
          </Card>

          {/* Results stats */}
          {result && (
            <Card className="border-green-500/20 bg-green-500/5">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2 text-green-700">
                    <CheckCircle2 className="w-4 h-4" />
                    Pipeline Complete
                  </CardTitle>
                  <Badge variant="outline" className="text-green-600 border-green-500/30 text-xs">
                    {result.duration}
                  </Badge>
                </div>
                <CardDescription>{result.filename}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-4 gap-3 mb-4">
                  {[
                    { label: "Total Blocks", value: result.totalBlocks, color: "text-foreground" },
                    { label: "Kept (HVAC)", value: result.keptBlocks, color: "text-green-600" },
                    { label: "Stripped", value: result.strippedBlocks, color: "text-orange-500" },
                    { label: "BOM Lines", value: result.lineItems, color: "text-primary" },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="text-center">
                      <p className={cn("text-xl font-bold", color)}>{value}</p>
                      <p className="text-[10px] text-muted-foreground mt-0.5">{label}</p>
                    </div>
                  ))}
                </div>
                <Button size="sm" className="w-full">
                  <Download className="w-3.5 h-3.5 mr-1.5" />
                  View Full BOM Output
                </Button>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Block log panel */}
        <div className="lg:col-span-2">
          <Card className="h-full">
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Layers className="w-4 h-4 text-muted-foreground" />
                Block Filter Log
              </CardTitle>
              <CardDescription>INSERT filter decisions per block type</CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              {result ? (
                <ScrollArea className="h-[420px] px-4 pb-4">
                  <div className="space-y-1">
                    {result.blocks.map((block, i) => (
                      <div
                        key={i}
                        className={cn(
                          "flex items-start gap-2 rounded-md px-2.5 py-2 text-xs",
                          block.action === "kept" ? "bg-green-500/5" : "bg-muted/40"
                        )}
                      >
                        {block.action === "kept"
                          ? <CheckCircle2 className="w-3.5 h-3.5 text-green-500 mt-0.5 shrink-0" />
                          : <XCircle className="w-3.5 h-3.5 text-orange-400 mt-0.5 shrink-0" />
                        }
                        <div className="flex-1 min-w-0">
                          <span className="font-mono font-medium truncate block">{block.name}</span>
                          <span className="text-muted-foreground">{block.reason}</span>
                        </div>
                        <span className="text-muted-foreground shrink-0">×{block.count}</span>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              ) : (
                <div className="flex flex-col items-center justify-center h-[420px] text-center px-6">
                  <Filter className="w-10 h-10 text-muted-foreground/25 mb-3" />
                  <p className="text-sm text-muted-foreground">Block filter log appears here after processing a file.</p>
                  <p className="text-xs text-muted-foreground/60 mt-1">Each INSERT block is classified as HVAC or non-HVAC.</p>
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
            <p><span className="font-semibold text-foreground">ODA File Converter required for DWG input.</span> The pipeline is wired for DXF natively. DWG support requires ODA installed on the server — Gerald wires that subprocess after Designer Desktop integration is confirmed.</p>
            <p>Block keyword lists live in <code className="font-mono bg-muted px-1 rounded">insert_filter.py</code>. After real-world DWG testing, those lists will need tuning — architect naming conventions vary by firm.</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
