import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
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
} from "lucide-react";
import { cn } from "@/lib/utils";

interface BomLine {
  id: string;
  category: "duct" | "fitting" | "equipment" | "consumable";
  standardName: string;
  clientName: string;
  qty: number;
  unit: string;
  unitCost: number;
  markupPct: number;
  total: number;
}

const MOCK_BOM: BomLine[] = [
  { id: "1",  category: "equipment",   standardName: "Roof Top Unit 3-Ton",       clientName: "RTU 3T Carrier 50XCQ",   qty: 1,  unit: "EA", unitCost: 2840.00, markupPct: 18, total: 3351.20 },
  { id: "2",  category: "equipment",   standardName: "Air Handler Unit",           clientName: "AHU Fan Coil 2.5T",      qty: 1,  unit: "EA", unitCost: 1240.00, markupPct: 18, total: 1463.20 },
  { id: "3",  category: "duct",        standardName: "Round Duct 6in",             clientName: "6in Spiral Duct",        qty: 68, unit: "LF", unitCost: 4.80,    markupPct: 15, total: 375.36  },
  { id: "4",  category: "duct",        standardName: "Round Duct 8in",             clientName: "8in Spiral Duct",        qty: 42, unit: "LF", unitCost: 6.20,    markupPct: 15, total: 299.49  },
  { id: "5",  category: "duct",        standardName: "Rectangular Duct 12x8",      clientName: "Rect Duct 12x8",         qty: 24, unit: "LF", unitCost: 9.40,    markupPct: 15, total: 258.84  },
  { id: "6",  category: "fitting",     standardName: "Wye 6in",                    clientName: "6in Sheet Metal Wye",    qty: 9,  unit: "EA", unitCost: 18.50,   markupPct: 18, total: 196.83  },
  { id: "7",  category: "fitting",     standardName: "Elbow 90° 6in",              clientName: "6in Elbow 90",           qty: 14, unit: "EA", unitCost: 12.00,   markupPct: 18, total: 199.92  },
  { id: "8",  category: "fitting",     standardName: "Reducer 8x6in",              clientName: "8x6 Reducing Collar",    qty: 6,  unit: "EA", unitCost: 14.20,   markupPct: 18, total: 100.70  },
  { id: "9",  category: "fitting",     standardName: "Supply Grille 10in",         clientName: "10in Supply Diffuser",   qty: 14, unit: "EA", unitCost: 22.00,   markupPct: 18, total: 364.76  },
  { id: "10", category: "fitting",     standardName: "Return Grille 12in",         clientName: "12in Return Air Grille", qty: 8,  unit: "EA", unitCost: 28.00,   markupPct: 18, total: 264.96  },
  { id: "11", category: "fitting",     standardName: "Flex Connector 6in",         clientName: "6in Flex Connector",     qty: 12, unit: "EA", unitCost: 8.20,    markupPct: 18, total: 116.21  },
  { id: "12", category: "consumable",  standardName: "Mastic Duct Sealant",        clientName: "Duct Seal Compound",     qty: 2,  unit: "GAL",unitCost: 14.00,   markupPct: 15, total: 32.20   },
  { id: "13", category: "consumable",  standardName: "Foil Tape 2in",              clientName: "UL Foil Tape",           qty: 3,  unit: "RL", unitCost: 22.00,   markupPct: 15, total: 75.90   },
  { id: "14", category: "consumable",  standardName: "Sheet Metal Screws",         clientName: "SM Screws #8x1/2",       qty: 2,  unit: "BX", unitCost: 8.50,    markupPct: 15, total: 19.55   },
  { id: "15", category: "consumable",  standardName: "20x25x1 Air Filter",         clientName: "MERV8 Filter 20x25",     qty: 2,  unit: "EA", unitCost: 4.50,    markupPct: 15, total: 10.35   },
];

const CATEGORY_META = {
  equipment:  { label: "Equipment",   icon: Thermometer, color: "text-purple-500",  bg: "bg-purple-500/10" },
  duct:       { label: "Duct",        icon: Wind,        color: "text-blue-500",    bg: "bg-blue-500/10"   },
  fitting:    { label: "Fittings",    icon: Wrench,      color: "text-amber-500",   bg: "bg-amber-500/10"  },
  consumable: { label: "Consumables", icon: Package,     color: "text-green-500",   bg: "bg-green-500/10"  },
};

type Category = keyof typeof CATEGORY_META;

export default function BomOutput() {
  const [search, setSearch] = useState("");
  const [filterCategory, setFilterCategory] = useState<"all" | Category>("all");
  const [expandedCategories, setExpandedCategories] = useState<Set<Category>>(
    new Set(["equipment", "duct", "fitting", "consumable"])
  );

  const toggleCategory = (cat: Category) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const filtered = MOCK_BOM.filter((line) => {
    const matchSearch =
      !search ||
      line.standardName.toLowerCase().includes(search.toLowerCase()) ||
      line.clientName.toLowerCase().includes(search.toLowerCase());
    const matchCat = filterCategory === "all" || line.category === filterCategory;
    return matchSearch && matchCat;
  });

  const grandTotal = MOCK_BOM.reduce((s, l) => s + l.total, 0);
  const byCategory = Object.fromEntries(
    (Object.keys(CATEGORY_META) as Category[]).map((cat) => [
      cat,
      MOCK_BOM.filter((l) => l.category === cat),
    ])
  ) as Record<Category, BomLine[]>;

  return (
    <div className="space-y-6 max-w-5xl mx-auto">

      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">BOM Output</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Generated materials list — formatted with Beazer Homes profile pricing and markup tiers.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" size="sm">
            <Printer className="w-3.5 h-3.5 mr-1.5" />
            Print
          </Button>
          <Button size="sm">
            <Download className="w-3.5 h-3.5 mr-1.5" />
            Export CSV
          </Button>
        </div>
      </div>

      {/* Job metadata banner */}
      <Card className="border-primary/20 bg-primary/5">
        <CardContent className="p-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { label: "Job", value: "Beazer Homes — Lot A7", icon: Building2 },
              { label: "Profile Applied", value: "Beazer Homes (18% std)", icon: CheckCircle2 },
              { label: "Generated", value: "Apr 7, 2026  10:14 AM", icon: Clock },
              { label: "Grand Total", value: `$${grandTotal.toLocaleString("en-US", { minimumFractionDigits: 2 })}`, icon: DollarSign },
            ].map(({ label, value, icon: Icon }) => (
              <div key={label} className="flex items-start gap-2">
                <Icon className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
                  <p className="text-sm font-medium">{value}</p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Category summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {(Object.entries(CATEGORY_META) as [Category, typeof CATEGORY_META[Category]][]).map(([cat, meta]) => {
          const lines = byCategory[cat];
          const subtotal = lines.reduce((s, l) => s + l.total, 0);
          return (
            <Card key={cat} className="cursor-pointer hover:border-primary/30 transition-colors"
              onClick={() => { setFilterCategory(cat === filterCategory ? "all" : cat); }}
            >
              <CardContent className="p-4">
                <div className={cn("w-8 h-8 rounded flex items-center justify-center mb-2", meta.bg)}>
                  <meta.icon className={cn("w-4 h-4", meta.color)} />
                </div>
                <p className="font-semibold text-xs">{meta.label}</p>
                <p className="text-lg font-bold mt-0.5">{lines.length} <span className="text-xs font-normal text-muted-foreground">items</span></p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  ${subtotal.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                </p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap items-center">
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
              <SelectItem key={k} value={k}>{v.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {(search || filterCategory !== "all") && (
          <Button variant="ghost" size="sm" className="h-9" onClick={() => { setSearch(""); setFilterCategory("all"); }}>
            Clear
          </Button>
        )}
      </div>

      {/* BOM table grouped by category */}
      <div className="space-y-3">
        {(Object.entries(byCategory) as [Category, BomLine[]][])
          .filter(([cat]) => filterCategory === "all" || filterCategory === cat)
          .map(([cat, lines]) => {
            const meta = CATEGORY_META[cat];
            const visibleLines = lines.filter((l) =>
              !search ||
              l.standardName.toLowerCase().includes(search.toLowerCase()) ||
              l.clientName.toLowerCase().includes(search.toLowerCase())
            );
            if (visibleLines.length === 0) return null;
            const subtotal = visibleLines.reduce((s, l) => s + l.total, 0);
            const expanded = expandedCategories.has(cat);

            return (
              <Card key={cat} className="overflow-hidden">
                <button
                  className="w-full"
                  onClick={() => toggleCategory(cat)}
                >
                  <div className="flex items-center justify-between px-5 py-3 hover:bg-muted/30 transition-colors">
                    <div className="flex items-center gap-3">
                      <div className={cn("w-7 h-7 rounded flex items-center justify-center", meta.bg)}>
                        <meta.icon className={cn("w-3.5 h-3.5", meta.color)} />
                      </div>
                      <span className="font-semibold text-sm">{meta.label}</span>
                      <Badge variant="secondary" className="text-xs">{visibleLines.length} items</Badge>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="font-semibold text-sm">
                        ${subtotal.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                      </span>
                      {expanded
                        ? <ChevronUp className="w-4 h-4 text-muted-foreground" />
                        : <ChevronDown className="w-4 h-4 text-muted-foreground" />
                      }
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
                            <th className="text-left px-5 py-2.5 font-medium w-[35%]">Client Name</th>
                            <th className="text-left px-3 py-2.5 font-medium hidden md:table-cell w-[30%]">Standard Name</th>
                            <th className="text-right px-3 py-2.5 font-medium">Qty</th>
                            <th className="text-right px-3 py-2.5 font-medium hidden sm:table-cell">Unit</th>
                            <th className="text-right px-3 py-2.5 font-medium hidden sm:table-cell">Unit Cost</th>
                            <th className="text-right px-3 py-2.5 font-medium hidden md:table-cell">Markup</th>
                            <th className="text-right px-5 py-2.5 font-medium">Total</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/50">
                          {visibleLines.map((line) => (
                            <tr key={line.id} className="hover:bg-muted/20 transition-colors">
                              <td className="px-5 py-2.5 font-medium">{line.clientName}</td>
                              <td className="px-3 py-2.5 text-muted-foreground hidden md:table-cell">{line.standardName}</td>
                              <td className="px-3 py-2.5 text-right">{line.qty}</td>
                              <td className="px-3 py-2.5 text-right text-muted-foreground hidden sm:table-cell">{line.unit}</td>
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
                            <td colSpan={6} className="px-5 py-2.5 font-semibold text-right hidden md:table-cell">
                              {meta.label} Subtotal
                            </td>
                            <td colSpan={3} className="px-5 py-2.5 font-semibold text-right md:hidden">
                              Subtotal
                            </td>
                            <td className="px-5 py-2.5 text-right font-bold">
                              ${subtotal.toLocaleString("en-US", { minimumFractionDigits: 2 })}
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
            <span className="font-semibold">Grand Total — All Materials</span>
            <Badge variant="outline" className="text-xs ml-1">Beazer Homes markup applied</Badge>
          </div>
          <span className="text-2xl font-bold text-primary">
            ${grandTotal.toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </span>
        </CardContent>
      </Card>
    </div>
  );
}
