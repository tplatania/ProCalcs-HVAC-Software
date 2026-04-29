import { useMemo, useState } from "react";
import {
  PlusCircle,
  Search,
  Pencil,
  Trash2,
  EyeOff,
  Eye,
  PackageSearch,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  useListSkuCatalog,
  useGetSkuCatalogMeta,
  useDeleteSku,
  useDisableSku,
  getListSkuCatalogQueryKey,
  type SKUItem,
} from "@/lib/api-hooks";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useToast } from "@/hooks/use-toast";

import { SkuCatalogForm } from "@/components/sku-catalog-form";

const ALL = "__all__";

function describeQuantity(q: SKUItem["quantity"]): string {
  if (!q || !q.mode) return "—";
  const extras = Object.entries(q)
    .filter(([k]) => k !== "mode")
    .map(([k, v]) => `${k}=${v}`)
    .join(" ");
  return extras ? `${q.mode} · ${extras}` : String(q.mode);
}

export default function SkuCatalogPage() {
  const [search, setSearch] = useState("");
  const [section, setSection] = useState<string>(ALL);
  const [supplier, setSupplier] = useState<string>(ALL);
  const [includeDisabled, setIncludeDisabled] = useState(true);

  // form state — null = closed, "create" = new, SKUItem = edit
  const [formMode, setFormMode] = useState<null | "create" | { editing: SKUItem }>(null);

  // delete confirm state
  const [pendingDelete, setPendingDelete] = useState<SKUItem | null>(null);

  const filter = {
    section: section === ALL ? undefined : section,
    supplier: supplier === ALL ? undefined : supplier,
    include_disabled: includeDisabled,
  };

  const { data: items, isLoading } = useListSkuCatalog(filter);
  const { data: meta } = useGetSkuCatalogMeta();
  const deleteMutation = useDeleteSku();
  const disableMutation = useDisableSku();

  const queryClient = useQueryClient();
  const { toast } = useToast();

  const filtered = useMemo(() => {
    if (!items) return [] as SKUItem[];
    if (!search.trim()) return items;
    const q = search.toLowerCase();
    return items.filter(
      (it) =>
        it.sku.toLowerCase().includes(q) ||
        it.description.toLowerCase().includes(q) ||
        it.supplier.toLowerCase().includes(q)
    );
  }, [items, search]);

  const sectionsForFilter = meta?.sections ?? [];
  const suppliersForFilter = meta?.suppliers_seen ?? [];

  const invalidate = () => {
    // Invalidate every list-cache variant since filter is part of the key.
    queryClient.invalidateQueries({ queryKey: ["sku-catalog"] });
  };

  const handleDelete = (item: SKUItem) => {
    deleteMutation.mutate(
      { sku: item.sku },
      {
        onSuccess: () => {
          toast({ title: `Deleted ${item.sku}` });
          invalidate();
          setPendingDelete(null);
        },
        onError: (err: any) =>
          toast({
            title: "Delete failed",
            description: err?.error ?? "Unknown error",
            variant: "destructive",
          }),
      }
    );
  };

  const handleToggleDisabled = (item: SKUItem) => {
    disableMutation.mutate(
      { sku: item.sku, disabled: !item.disabled },
      {
        onSuccess: () => {
          toast({ title: `${item.disabled ? "Enabled" : "Disabled"} ${item.sku}` });
          invalidate();
        },
        onError: (err: any) =>
          toast({
            title: "Toggle failed",
            description: err?.error ?? "Unknown error",
            variant: "destructive",
          }),
      }
    );
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">SKU Catalog</h1>
          <p className="text-muted-foreground mt-2">
            Supplier part numbers, sections, and quantity rules. Edits take effect on
            the next BOM generation — no deploy required.
          </p>
        </div>
        <Button onClick={() => setFormMode("create")}>
          <PlusCircle className="w-4 h-4 mr-2" />
          New SKU
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-center">
            <div className="md:col-span-5 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search SKU, description, or supplier…"
                className="pl-10"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="md:col-span-3">
              <Select value={section} onValueChange={setSection}>
                <SelectTrigger><SelectValue placeholder="Section" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>All sections</SelectItem>
                  {sectionsForFilter.map((s) => (
                    <SelectItem key={s} value={s}>{s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="md:col-span-3">
              <Select value={supplier} onValueChange={setSupplier}>
                <SelectTrigger><SelectValue placeholder="Supplier" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>All suppliers</SelectItem>
                  {suppliersForFilter.map((s) => (
                    <SelectItem key={s} value={s}>{s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="md:col-span-1 text-right">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIncludeDisabled((v) => !v)}
                title={includeDisabled ? "Hide disabled" : "Show disabled"}
              >
                {includeDisabled ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
          <CardTitle className="text-lg">
            {isLoading ? "Loading…" : `${filtered.length} item${filtered.length === 1 ? "" : "s"}`}
          </CardTitle>
          <span className="text-xs text-muted-foreground">
            Hard-delete is permanent. Use Disable to keep history.
          </span>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-2">
              {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-10 w-full" />)}
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-12 text-center">
              <PackageSearch className="w-10 h-10 text-muted-foreground mb-3" />
              <h3 className="text-lg font-semibold">No SKUs match</h3>
              <p className="text-muted-foreground mt-1 max-w-md text-sm">
                {search || section !== ALL || supplier !== ALL
                  ? "Try clearing filters."
                  : "Start by adding your first SKU."}
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>SKU</TableHead>
                  <TableHead>Supplier</TableHead>
                  <TableHead>Section</TableHead>
                  <TableHead>Phase</TableHead>
                  <TableHead className="min-w-[260px]">Description</TableHead>
                  <TableHead>Trigger</TableHead>
                  <TableHead>Quantity Rule</TableHead>
                  <TableHead className="text-right">Default Price</TableHead>
                  <TableHead className="text-right pr-6">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((it) => (
                  <TableRow key={it.sku} className={it.disabled ? "opacity-50" : ""}>
                    <TableCell className="font-mono text-sm font-medium">
                      {it.sku}
                      {it.disabled && (
                        <Badge variant="secondary" className="ml-2 text-[10px]">disabled</Badge>
                      )}
                    </TableCell>
                    <TableCell>{it.supplier}</TableCell>
                    <TableCell className="text-xs">{it.section}</TableCell>
                    <TableCell className="text-xs">{it.phase ?? "—"}</TableCell>
                    <TableCell className="text-sm">{it.description}</TableCell>
                    <TableCell className="text-xs font-mono">{it.trigger}</TableCell>
                    <TableCell className="text-xs font-mono whitespace-nowrap">
                      {describeQuantity(it.quantity)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {it.default_unit_price > 0 ? `$${it.default_unit_price.toFixed(2)}` : "—"}
                    </TableCell>
                    <TableCell className="text-right pr-6">
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          title={it.disabled ? "Enable" : "Disable"}
                          onClick={() => handleToggleDisabled(it)}
                        >
                          {it.disabled ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          title="Edit"
                          onClick={() => setFormMode({ editing: it })}
                        >
                          <Pencil className="w-4 h-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive hover:text-destructive"
                          title="Delete (hard)"
                          onClick={() => setPendingDelete(it)}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Form modal */}
      {formMode !== null && (
        <SkuCatalogForm
          mode={formMode === "create" ? "create" : "edit"}
          initial={formMode !== "create" ? formMode.editing : undefined}
          onClose={() => setFormMode(null)}
          onSaved={(item, kind) => {
            toast({
              title: kind === "created" ? `Created ${item.sku}` : `Updated ${item.sku}`,
            });
            invalidate();
            setFormMode(null);
          }}
        />
      )}

      {/* Delete confirm */}
      <AlertDialog open={!!pendingDelete} onOpenChange={(o) => !o && setPendingDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Hard-delete {pendingDelete?.sku}?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes <strong>{pendingDelete?.sku}</strong> from Firestore.
              If you only want to hide it from designers, use <em>Disable</em> instead.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => pendingDelete && handleDelete(pendingDelete)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete permanently
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
