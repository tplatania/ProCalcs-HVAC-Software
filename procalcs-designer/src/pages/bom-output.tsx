import { useState, useMemo, useEffect } from "react";
import { useLocation } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  FileText,
  Download,
  Printer,
  Search,
  Filter,
  Building2,
  CheckCircle2,
  Clock,
  DollarSign,
  Package,
  Wrench,
  Wind,
  Thermometer,
  ChevronDown,
  ChevronUp,
  ArrowLeft,
  Cpu,
  XCircle,
  Sparkles,
  ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  useListClientProfiles,
  useGenerateBom,
  useRenderBomPdf,
  loadParsedRup,
  clearParsedRup,
  type BomResponse,
  type BomLineItem,
  type StoredParseResult,
} from "@/lib/api-hooks";

// ─── Display shapes ──────────────────────────────────────────────────────

type Source = "rules" | "ai";

interface BomLine {
  id: string;
  category: Category;
  clientName: string;
  standardName: string;
  qty: number;
  unit: string;
  unitCost: number;
  markupPct: number;
  total: number;
  // Provenance — populated when the upstream rules engine fills these in.
  sku?: string;
  source: Source; // narrowed: lines without explicit source are treated as "ai"
}

const CATEGORY_META = {
  equipment:  { label: "Equipment",   icon: Thermometer, color: "text-purple-500",  bg: "bg-purple-500/10" },
  duct:       { label: "Duct",        icon: Wind,        color: "text-blue-500",    bg: "bg-blue-500/10"   },
  fitting:    { label: "Fittings",    icon: Wrench,      color: "text-amber-500",   bg: "bg-amber-500/10"  },
  consumable: { label: "Consumables", icon: Package,     color: "text-green-500",   bg: "bg-green-500/10"  },
} as const;

type Category = keyof typeof CATEGORY_META;

// Normalize unknown categories from the Flask backend into the 4 buckets
// the UI can render. Any unrecognized category falls back to consumable.
function normalizeCategory(raw: string | undefined): Category {
  if (!raw) return "consumable";
  const key = raw.toLowerCase().trim();
  if (key === "equipment") return "equipment";
  if (key === "duct") return "duct";
  if (key === "fitting") return "fitting";
  if (key === "register") return "fitting"; // registers visually live under fittings
  if (key === "consumable") return "consumable";
  return "consumable";
}

// Map a Flask-shaped line_item into the BomLine display shape. Prices
// are shown when available (full/materials_only/client_proposal modes),
// otherwise unit_cost + total_cost are used (cost_estimate mode).
function mapLineItem(item: BomLineItem, index: number): BomLine {
  const cat = normalizeCategory(item.category);
  const unitCost = item.unit_price ?? item.unit_cost ?? 0;
  const total = item.total_price ?? item.total_cost ?? 0;
  // Treat any non-"rules" source (or absent source) as AI. The rules engine
  // explicitly emits source="rules" for deterministic SKU lines; anything
  // else originated from the Claude estimator and should be flagged for review.
  const source: Source = item.source === "rules" ? "rules" : "ai";
  return {
    id: `${cat}-${index}`,
    category: cat,
    clientName: item.description || "(unnamed)",
    standardName: item.description || "(unnamed)",
    qty: item.quantity ?? 0,
    unit: item.unit || "EA",
    unitCost,
    markupPct: item.markup_pct ?? 0,
    total,
    sku: item.sku || undefined,
    source,
  };
}

// ─── CSV export helper ───────────────────────────────────────────────────

function downloadCsv(bom: BomResponse): void {
  const rows = [
    [
      "Category",
      "Source",
      "SKU",
      "Description",
      "Qty",
      "Unit",
      "Unit Cost",
      "Unit Price",
      "Markup %",
      "Total",
    ],
  ];
  for (const item of bom.line_items) {
    rows.push([
      item.category ?? "",
      item.source === "rules" ? "rules" : "ai",
      item.sku ?? "",
      (item.description ?? "").replace(/"/g, '""'),
      String(item.quantity ?? 0),
      item.unit ?? "",
      String(item.unit_cost ?? ""),
      String(item.unit_price ?? ""),
      String(item.markup_pct ?? ""),
      String(item.total_price ?? item.total_cost ?? 0),
    ]);
  }
  rows.push([]);
  rows.push(["Total Cost", "", "", "", "", "", "", "", "", String(bom.totals.total_cost ?? "")]);
  rows.push(["Total Price", "", "", "", "", "", "", "", "", String(bom.totals.total_price ?? "")]);

  const csv = rows
    .map((r) => r.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
    .join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${bom.job_id || "bom"}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ─── Page component ─────────────────────────────────────────────────────

type PageState = "needs-input" | "ready-to-generate" | "generating" | "done" | "error";

export default function BomOutput() {
  const [, setLocation] = useLocation();
  const [stored, setStored] = useState<StoredParseResult | null>(() => loadParsedRup());
  const [selectedClientId, setSelectedClientId] = useState<string>("procalcs-direct");
  const [outputMode, setOutputMode] = useState<"full" | "materials_only" | "client_proposal" | "cost_estimate">("full");
  const [bom, setBom] = useState<BomResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const profilesQuery = useListClientProfiles();
  const generate = useGenerateBom();

  // Default the profile picker to the first available profile if the
  // preferred one isn't present in Firestore.
  useEffect(() => {
    if (!profilesQuery.data || profilesQuery.data.length === 0) return;
    const hasPreferred = profilesQuery.data.some((p) => p.id === selectedClientId);
    if (!hasPreferred) {
      setSelectedClientId(profilesQuery.data[0].id);
    }
  }, [profilesQuery.data, selectedClientId]);

  // Derive the page state from local state
  const pageState: PageState = !stored
    ? "needs-input"
    : errorMsg
    ? "error"
    : bom
    ? "done"
    : generate.isPending
    ? "generating"
    : "ready-to-generate";

  const handleGenerate = () => {
    if (!stored) return;
    setErrorMsg(null);
    setBom(null);
    const jobId = `${stored.designData.project?.name || "job"}-${Date.now()}`
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 80);
    generate.mutate(
      {
        client_id: selectedClientId,
        job_id: jobId,
        design_data: stored.designData,
        output_mode: outputMode,
      },
      {
        onSuccess: (data) => setBom(data),
        onError: (err) => setErrorMsg(err?.error ?? "BOM generation failed"),
      }
    );
  };

  const handleBack = () => {
    clearParsedRup();
    setStored(null);
    setBom(null);
    setErrorMsg(null);
    setLocation("/bom-engine");
  };

  const handleRetry = () => {
    setErrorMsg(null);
    setBom(null);
  };

  // ─── Render states ─────────────────────────────────────────────────────

  if (pageState === "needs-input") {
    return (
      <div className="max-w-2xl mx-auto">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-muted-foreground" />
              No parsed .rup file yet
            </CardTitle>
            <CardDescription>
              Start by uploading a Wrightsoft .rup project file on the BOM Engine page.
              The parsed data will then be available here for BOM generation.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => setLocation("/bom-engine")}>
              <ArrowLeft className="w-4 h-4 mr-1.5" />
              Go to BOM Engine
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Summary blob derived from the stored parse — shown in both ready and done states
  const parsedSummary = stored && (
    <Card className="border-primary/20 bg-primary/5 no-print">
      <CardContent className="p-4">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Project
            </p>
            <p className="font-medium truncate">
              {stored.designData.project?.name ?? stored.sourceFile}
            </p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Building
            </p>
            <p className="font-medium">
              {(stored.designData.building?.type ?? "unknown").replace("_", " ")} /{" "}
              {stored.designData.building?.duct_location ?? "—"}
            </p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Equipment
            </p>
            <p className="font-medium">{stored.designData.equipment?.length ?? 0} units</p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Rooms
            </p>
            <p className="font-medium">{stored.designData.rooms?.length ?? 0} rooms</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );

  if (pageState === "ready-to-generate" || pageState === "generating" || pageState === "error") {
    return (
      <div className="space-y-6 max-w-3xl mx-auto">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">BOM Output</h1>
            <p className="text-muted-foreground text-sm mt-1">
              Pick a client profile and generate a priced BOM from the parsed .rup data.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={handleBack}>
            <ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
            Back to BOM Engine
          </Button>
        </div>

        {parsedSummary}

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Cpu className="w-4 h-4 text-muted-foreground" />
              Generate BOM
            </CardTitle>
            <CardDescription>
              The backend calls Claude to estimate material quantities from the parsed data,
              then Python applies the selected profile's pricing and markup.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Client profile picker */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Client Profile
              </label>
              {profilesQuery.isLoading ? (
                <Skeleton className="h-9 w-full" />
              ) : profilesQuery.data && profilesQuery.data.length > 0 ? (
                <Select
                  value={selectedClientId}
                  onValueChange={setSelectedClientId}
                  disabled={pageState === "generating"}
                >
                  <SelectTrigger className="h-9 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {profilesQuery.data.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.name} — {p.supplierName}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No client profiles found. Create one on the Profiles page first.
                </p>
              )}
            </div>

            {/* Output mode picker */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Output Mode
              </label>
              <Select
                value={outputMode}
                onValueChange={(v) => setOutputMode(v as typeof outputMode)}
                disabled={pageState === "generating"}
              >
                <SelectTrigger className="h-9 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="full">Full — all items, cost + price</SelectItem>
                  <SelectItem value="materials_only">Materials Only — no equipment</SelectItem>
                  <SelectItem value="client_proposal">Client Proposal — price only</SelectItem>
                  <SelectItem value="cost_estimate">Cost Estimate — cost only</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {pageState === "generating" && (
              <div className="flex items-center gap-3 p-4 bg-primary/5 border border-primary/20 rounded-lg">
                <Sparkles className="w-5 h-5 text-primary animate-pulse" />
                <div className="flex-1">
                  <p className="text-sm font-medium">AI estimating quantities...</p>
                  <p className="text-xs text-muted-foreground">
                    Usually 10–20 seconds. Cold starts can take up to 45 seconds.
                  </p>
                </div>
              </div>
            )}

            {pageState === "error" && (
              <div className="flex items-start gap-3 p-4 bg-destructive/5 border border-destructive/30 rounded-lg">
                <XCircle className="w-5 h-5 text-destructive mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-destructive">BOM generation failed</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{errorMsg}</p>
                </div>
              </div>
            )}

            <Button
              className="w-full"
              size="lg"
              onClick={pageState === "error" ? handleRetry : handleGenerate}
              disabled={
                pageState === "generating" ||
                !profilesQuery.data ||
                profilesQuery.data.length === 0
              }
            >
              <Cpu className="w-4 h-4 mr-2" />
              {pageState === "generating"
                ? "Generating..."
                : pageState === "error"
                ? "Retry"
                : "Generate BOM"}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // pageState === "done" — render the real BOM
  return <BomResultView bom={bom!} stored={stored!} onBack={handleBack} onRetry={handleRetry} />;
}

// ─── BOM result view (done state) ──────────────────────────────────────

function BomResultView({
  bom,
  stored,
  onBack,
  onRetry,
}: {
  bom: BomResponse;
  stored: StoredParseResult;
  onBack: () => void;
  onRetry: () => void;
}) {
  const [search, setSearch] = useState("");
  const [filterCategory, setFilterCategory] = useState<"all" | Category>("all");
  const [filterSource, setFilterSource] = useState<"all" | Source>("all");
  const [expandedCategories, setExpandedCategories] = useState<Set<Category>>(
    new Set(["equipment", "duct", "fitting", "consumable"])
  );
  const renderPdf = useRenderBomPdf();

  const lines: BomLine[] = useMemo(
    () => (bom.line_items ?? []).map((item, i) => mapLineItem(item, i)),
    [bom]
  );

  // Counts by provenance — prefer the backend-provided counts (from the
  // rules-engine merge in procalcs-bom) and fall back to derivation from
  // line_items for older response shapes.
  const rulesCount = bom.rules_engine_item_count ?? lines.filter((l) => l.source === "rules").length;
  const aiCount = bom.ai_item_count ?? lines.filter((l) => l.source === "ai").length;
  const hasProvenance = rulesCount > 0 || aiCount > 0;

  const byCategory = useMemo(() => {
    return Object.fromEntries(
      (Object.keys(CATEGORY_META) as Category[]).map((cat) => [
        cat,
        lines.filter((l) => l.category === cat),
      ])
    ) as Record<Category, BomLine[]>;
  }, [lines]);

  const toggleCategory = (cat: Category) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const grandTotal =
    bom.totals.total_price ??
    bom.totals.total_cost ??
    lines.reduce((s, l) => s + l.total, 0);

  const generatedDate = useMemo(() => {
    try {
      return new Date(bom.generated_at).toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return bom.generated_at;
    }
  }, [bom.generated_at]);

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap no-print">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">BOM Output</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Generated materials list — formatted with{" "}
            <span className="font-medium text-foreground">{bom.client_name}</span> profile pricing
            and markup.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" size="sm" onClick={onBack}>
            <ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
            Back
          </Button>
          <Button variant="outline" size="sm" onClick={onRetry}>
            <Cpu className="w-3.5 h-3.5 mr-1.5" />
            Regenerate
          </Button>
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            <Printer className="w-3.5 h-3.5 mr-1.5" />
            Print
          </Button>
          <Button variant="outline" size="sm" onClick={() => downloadCsv(bom)}>
            <Download className="w-3.5 h-3.5 mr-1.5" />
            Export CSV
          </Button>
          <Button
            size="sm"
            onClick={() => renderPdf.mutate({ bom })}
            disabled={renderPdf.isPending}
          >
            <Download className="w-3.5 h-3.5 mr-1.5" />
            {renderPdf.isPending ? "Rendering..." : "Download PDF"}
          </Button>
        </div>
      </div>

      {/* Job metadata banner */}
      <Card className="border-primary/20 bg-primary/5">
        <CardContent className="p-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              {
                label: "Job",
                value: stored.designData.project?.name ?? bom.job_id,
                icon: Building2,
              },
              {
                label: "Profile Applied",
                value: `${bom.client_name} (${bom.supplier})`,
                icon: CheckCircle2,
              },
              {
                label: "Generated",
                value: generatedDate,
                icon: Clock,
              },
              {
                label: "Grand Total",
                value: `$${grandTotal.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}`,
                icon: DollarSign,
              },
            ].map(({ label, value, icon: Icon }) => (
              <div key={label} className="flex items-start gap-2">
                <Icon className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <div className="min-w-0">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {label}
                  </p>
                  <p className="text-sm font-medium truncate">{value}</p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Provenance summary — only shown when the upstream rules engine
          has reported per-source counts. Lets designers see at a glance
          which lines are deterministic (rules) vs estimated (AI). */}
      {hasProvenance && (
        <Card className="border-muted">
          <CardContent className="p-4 flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              <span className="text-sm">
                <span className="font-semibold">{rulesCount}</span>{" "}
                <span className="text-muted-foreground">
                  rules-engine line{rulesCount === 1 ? "" : "s"} (deterministic)
                </span>
              </span>
            </div>
            <Separator orientation="vertical" className="h-6 hidden sm:block" />
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-amber-600" />
              <span className="text-sm">
                <span className="font-semibold">{aiCount}</span>{" "}
                <span className="text-muted-foreground">
                  AI-estimated line{aiCount === 1 ? "" : "s"} (review)
                </span>
              </span>
            </div>
            <p className="text-xs text-muted-foreground sm:ml-auto no-print">
              Rules-engine quantities are emitted from the catalog and won't change between runs.
              AI lines may vary — spot-check before sending to the client.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Category summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 no-print">
        {(Object.entries(CATEGORY_META) as [Category, typeof CATEGORY_META[Category]][]).map(
          ([cat, meta]) => {
            const catLines = byCategory[cat];
            const subtotal = catLines.reduce((s, l) => s + l.total, 0);
            return (
              <Card
                key={cat}
                className="cursor-pointer hover:border-primary/30 transition-colors"
                onClick={() => {
                  setFilterCategory(cat === filterCategory ? "all" : cat);
                }}
              >
                <CardContent className="p-4">
                  <div
                    className={cn(
                      "w-8 h-8 rounded flex items-center justify-center mb-2",
                      meta.bg
                    )}
                  >
                    <meta.icon className={cn("w-4 h-4", meta.color)} />
                  </div>
                  <p className="font-semibold text-xs">{meta.label}</p>
                  <p className="text-lg font-bold mt-0.5">
                    {catLines.length}{" "}
                    <span className="text-xs font-normal text-muted-foreground">items</span>
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    $
                    {subtotal.toLocaleString("en-US", {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </p>
                </CardContent>
              </Card>
            );
          }
        )}
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap items-center no-print">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            placeholder="Search items..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 h-9 text-sm"
          />
        </div>
        <Select value={filterCategory} onValueChange={(v) => setFilterCategory(v as any)}>
          <SelectTrigger className="h-9 text-sm w-40">
            <Filter className="w-3.5 h-3.5 mr-1.5 text-muted-foreground" />
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Categories</SelectItem>
            {Object.entries(CATEGORY_META).map(([k, v]) => (
              <SelectItem key={k} value={k}>
                {v.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {hasProvenance && (
          <Select value={filterSource} onValueChange={(v) => setFilterSource(v as any)}>
            <SelectTrigger className="h-9 text-sm w-40">
              <ShieldCheck className="w-3.5 h-3.5 mr-1.5 text-muted-foreground" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Sources</SelectItem>
              <SelectItem value="rules">Rules engine only</SelectItem>
              <SelectItem value="ai">AI-estimated only</SelectItem>
            </SelectContent>
          </Select>
        )}
        {(search || filterCategory !== "all" || filterSource !== "all") && (
          <Button
            variant="ghost"
            size="sm"
            className="h-9"
            onClick={() => {
              setSearch("");
              setFilterCategory("all");
              setFilterSource("all");
            }}
          >
            Clear
          </Button>
        )}
      </div>

      {/* BOM table grouped by category */}
      <div className="space-y-3">
        {(Object.entries(byCategory) as [Category, BomLine[]][])
          .filter(([cat]) => filterCategory === "all" || filterCategory === cat)
          .map(([cat, catLines]) => {
            const meta = CATEGORY_META[cat];
            const visibleLines = catLines.filter((l) => {
              if (filterSource !== "all" && l.source !== filterSource) return false;
              if (!search) return true;
              const needle = search.toLowerCase();
              return (
                l.standardName.toLowerCase().includes(needle) ||
                l.clientName.toLowerCase().includes(needle) ||
                (l.sku ?? "").toLowerCase().includes(needle)
              );
            });
            if (visibleLines.length === 0) return null;
            const subtotal = visibleLines.reduce((s, l) => s + l.total, 0);
            const expanded = expandedCategories.has(cat);

            return (
              <Card key={cat} className="overflow-hidden">
                <button className="w-full" onClick={() => toggleCategory(cat)}>
                  <div className="flex items-center justify-between px-5 py-3 hover:bg-muted/30 transition-colors">
                    <div className="flex items-center gap-3">
                      <div
                        className={cn(
                          "w-7 h-7 rounded flex items-center justify-center",
                          meta.bg
                        )}
                      >
                        <meta.icon className={cn("w-3.5 h-3.5", meta.color)} />
                      </div>
                      <span className="font-semibold text-sm">{meta.label}</span>
                      <Badge variant="secondary" className="text-xs">
                        {visibleLines.length} items
                      </Badge>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="font-semibold text-sm">
                        $
                        {subtotal.toLocaleString("en-US", {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                      </span>
                      {expanded ? (
                        <ChevronUp className="w-4 h-4 text-muted-foreground no-print" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-muted-foreground no-print" />
                      )}
                    </div>
                  </div>
                </button>

                {expanded && (
                  <>
                    <Separator />
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b bg-muted/30 text-muted-foreground">
                            <th className="text-left px-5 py-2.5 font-medium">Description</th>
                            {hasProvenance && (
                              <th className="text-left px-2 py-2.5 font-medium hidden lg:table-cell">
                                Source
                              </th>
                            )}
                            <th className="text-left px-3 py-2.5 font-medium hidden md:table-cell">
                              SKU
                            </th>
                            <th className="text-right px-3 py-2.5 font-medium">Qty</th>
                            <th className="text-right px-3 py-2.5 font-medium hidden sm:table-cell">
                              Unit
                            </th>
                            <th className="text-right px-3 py-2.5 font-medium hidden sm:table-cell">
                              Unit Cost
                            </th>
                            <th className="text-right px-3 py-2.5 font-medium hidden md:table-cell">
                              Markup
                            </th>
                            <th className="text-right px-5 py-2.5 font-medium">Total</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/50">
                          {visibleLines.map((line) => (
                            <tr key={line.id} className="hover:bg-muted/20 transition-colors">
                              <td className="px-5 py-2.5 font-medium">{line.clientName}</td>
                              {hasProvenance && (
                                <td className="px-2 py-2.5 hidden lg:table-cell">
                                  {line.source === "rules" ? (
                                    <Badge
                                      variant="outline"
                                      className="text-[10px] gap-1 border-emerald-600/30 text-emerald-700 dark:text-emerald-400"
                                    >
                                      <ShieldCheck className="w-3 h-3" />
                                      Rules
                                    </Badge>
                                  ) : (
                                    <Badge
                                      variant="outline"
                                      className="text-[10px] gap-1 border-amber-600/30 text-amber-700 dark:text-amber-400"
                                    >
                                      <Sparkles className="w-3 h-3" />
                                      AI
                                    </Badge>
                                  )}
                                </td>
                              )}
                              <td className="px-3 py-2.5 hidden md:table-cell font-mono text-[11px] text-muted-foreground">
                                {line.sku ?? "—"}
                              </td>
                              <td className="px-3 py-2.5 text-right">{line.qty}</td>
                              <td className="px-3 py-2.5 text-right text-muted-foreground hidden sm:table-cell">
                                {line.unit}
                              </td>
                              <td className="px-3 py-2.5 text-right text-muted-foreground hidden sm:table-cell">
                                ${line.unitCost.toFixed(2)}
                              </td>
                              <td className="px-3 py-2.5 text-right text-muted-foreground hidden md:table-cell">
                                {line.markupPct}%
                              </td>
                              <td className="px-5 py-2.5 text-right font-semibold">
                                ${line.total.toFixed(2)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                        <tfoot>
                          <tr className="border-t bg-muted/20">
                            <td
                              colSpan={hasProvenance ? 7 : 6}
                              className="px-5 py-2.5 font-semibold text-right hidden md:table-cell"
                            >
                              {meta.label} Subtotal
                            </td>
                            <td
                              colSpan={3}
                              className="px-5 py-2.5 font-semibold text-right md:hidden"
                            >
                              Subtotal
                            </td>
                            <td className="px-5 py-2.5 text-right font-bold">
                              $
                              {subtotal.toLocaleString("en-US", {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </td>
                          </tr>
                        </tfoot>
                      </table>
                    </div>
                  </>
                )}
              </Card>
            );
          })}
      </div>

      {/* Grand total */}
      <Card className="border-primary/20">
        <CardContent className="p-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-primary" />
            <span className="font-semibold">Grand Total — {bom.output_mode.replace("_", " ")}</span>
            <Badge variant="outline" className="text-xs ml-1">
              {bom.client_name} markup applied
            </Badge>
          </div>
          <span className="text-2xl font-bold text-primary">
            $
            {grandTotal.toLocaleString("en-US", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>
        </CardContent>
      </Card>
    </div>
  );
}
