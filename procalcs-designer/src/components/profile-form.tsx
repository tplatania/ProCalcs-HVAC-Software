import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { PlusCircle, Trash2, Building2, Palette, Percent, Link as LinkIcon, Save, ArrowLeft } from "lucide-react";
import { Separator } from "@/components/ui/separator";
import { Link } from "wouter";

const markupTierSchema = z.object({
  label: z.string().min(1, "Label required"),
  minAmount: z.coerce.number().min(0),
  maxAmount: z.coerce.number().nullable().optional(),
  markupPercent: z.coerce.number().min(0),
});

const partOverrideSchema = z.object({
  standardName: z.string().min(1, "Standard name required"),
  clientName: z.string().min(1, "Client name required"),
  unitCost: z.coerce.number().nullable().optional(),
  unit: z.string().min(1, "Unit required"),
});

const profileSchema = z.object({
  name: z.string().min(1, "Client name is required"),
  isActive: z.boolean().default(true),
  supplierName: z.string().min(1, "Supplier name is required"),
  supplierContact: z.string().nullable().optional(),
  supplierEmail: z.string().email("Invalid email").nullable().optional().or(z.literal("")),
  brandColor: z.string().nullable().optional(),
  logoUrl: z.string().url("Invalid URL").nullable().optional().or(z.literal("")),
  defaultMarkupPercent: z.coerce.number().min(0).max(1000),
  markupTiers: z.array(markupTierSchema).default([]),
  partOverrides: z.array(partOverrideSchema).default([]),
  notes: z.string().nullable().optional(),
});

type ProfileFormValues = z.infer<typeof profileSchema>;

interface ProfileFormProps {
  initialValues?: Partial<ProfileFormValues>;
  onSubmit: (data: ProfileFormValues) => void;
  isSubmitting?: boolean;
}

export function ProfileForm({ initialValues, onSubmit, isSubmitting }: ProfileFormProps) {
  const form = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      name: "",
      isActive: true,
      supplierName: "",
      supplierContact: "",
      supplierEmail: "",
      brandColor: "#1e293b",
      logoUrl: "",
      defaultMarkupPercent: 25,
      markupTiers: [],
      partOverrides: [],
      notes: "",
      ...initialValues,
    },
  });

  const { fields: tierFields, append: appendTier, remove: removeTier } = useFieldArray({
    control: form.control,
    name: "markupTiers",
  });

  const { fields: partFields, append: appendPart, remove: removePart } = useFieldArray({
    control: form.control,
    name: "partOverrides",
  });

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-8 pb-20">
        
        <div className="flex items-center justify-between sticky top-0 bg-background/95 backdrop-blur-sm z-10 py-4 border-b border-border/40">
          <div className="flex items-center gap-4">
            <Link href="/profiles">
              <Button variant="outline" size="icon" type="button" className="h-9 w-9">
                <ArrowLeft className="w-4 h-4" />
              </Button>
            </Link>
            <div>
              <h2 className="text-xl font-bold tracking-tight">
                {initialValues?.name ? `Edit ${initialValues.name}` : "New Client Profile"}
              </h2>
            </div>
          </div>
          <Button type="submit" disabled={isSubmitting} className="min-w-[120px]">
            <Save className="w-4 h-4 mr-2" />
            {isSubmitting ? "Saving..." : "Save Profile"}
          </Button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left Column: Basic Info & Supplier */}
          <div className="lg:col-span-1 space-y-8">
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Building2 className="w-4 h-4 text-muted-foreground" />
                  Client Information
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Client Name</FormLabel>
                      <FormControl>
                        <Input placeholder="Acme HVAC Corp" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                
                <FormField
                  control={form.control}
                  name="isActive"
                  render={({ field }) => (
                    <FormItem className="flex flex-row items-start space-x-3 space-y-0 rounded-md border p-4 bg-muted/20">
                      <FormControl>
                        <Checkbox
                          checked={field.value}
                          onCheckedChange={field.onChange}
                        />
                      </FormControl>
                      <div className="space-y-1 leading-none">
                        <FormLabel>Active Profile</FormLabel>
                        <FormDescription>
                          Inactive profiles won't be used in the BOM engine.
                        </FormDescription>
                      </div>
                    </FormItem>
                  )}
                />

                <Separator className="my-4" />
                
                <h4 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-2">
                  <Palette className="w-4 h-4" /> Brand Identity
                </h4>

                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="brandColor"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Brand Color</FormLabel>
                        <FormControl>
                          <div className="flex gap-2">
                            <Input 
                              type="color" 
                              className="w-10 h-10 p-1 cursor-pointer" 
                              {...field} 
                              value={field.value || "#1e293b"} 
                            />
                            <Input 
                              className="flex-1 font-mono text-sm uppercase" 
                              {...field} 
                              value={field.value || ""} 
                              placeholder="#000000"
                            />
                          </div>
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <FormField
                  control={form.control}
                  name="logoUrl"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Logo URL</FormLabel>
                      <FormControl>
                        <div className="relative">
                          <LinkIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                          <Input placeholder="https://..." className="pl-9" {...field} value={field.value || ""} />
                        </div>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Building2 className="w-4 h-4 text-muted-foreground" />
                  Supplier Details
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="supplierName"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Primary Supplier</FormLabel>
                      <FormControl>
                        <Input placeholder="Ferguson Enterprise" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="supplierContact"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Contact Name</FormLabel>
                      <FormControl>
                        <Input placeholder="Jane Doe" {...field} value={field.value || ""} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="supplierEmail"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Contact Email</FormLabel>
                      <FormControl>
                        <Input type="email" placeholder="jane@supplier.com" {...field} value={field.value || ""} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <FileText className="w-4 h-4 text-muted-foreground" />
                  Notes
                </CardTitle>
              </CardHeader>
              <CardContent>
                <FormField
                  control={form.control}
                  name="notes"
                  render={({ field }) => (
                    <FormItem>
                      <FormControl>
                        <Textarea 
                          placeholder="Special instructions, delivery preferences..." 
                          className="min-h-[120px]" 
                          {...field} 
                          value={field.value || ""} 
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>
          </div>

          {/* Right Column: Pricing & Overrides */}
          <div className="lg:col-span-2 space-y-8">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Percent className="w-4 h-4 text-muted-foreground" />
                    Markup Engine Rules
                  </CardTitle>
                  <CardDescription className="mt-1">
                    Define default and tiered pricing markups for BOM generation.
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="p-4 bg-muted/20 border rounded-lg max-w-sm">
                  <FormField
                    control={form.control}
                    name="defaultMarkupPercent"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Default Global Markup (%)</FormLabel>
                        <FormControl>
                          <Input type="number" min="0" step="0.1" {...field} className="text-lg font-semibold h-12 w-32" />
                        </FormControl>
                        <FormDescription>Applied when no tiers match.</FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h4 className="font-medium text-sm">Tiered Markups</h4>
                    <Button 
                      type="button" 
                      variant="outline" 
                      size="sm" 
                      onClick={() => appendTier({ label: "", minAmount: 0, maxAmount: null, markupPercent: 0 })}
                    >
                      <PlusCircle className="w-4 h-4 mr-2" /> Add Tier
                    </Button>
                  </div>
                  
                  {tierFields.length === 0 ? (
                    <div className="text-center p-6 border border-dashed rounded-lg text-muted-foreground text-sm bg-muted/10">
                      No custom tiers defined. The default markup will be used for all items.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div className="grid grid-cols-12 gap-3 px-3 pb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider border-b">
                        <div className="col-span-4">Tier Label</div>
                        <div className="col-span-3">Min Amount ($)</div>
                        <div className="col-span-3">Max Amount ($)</div>
                        <div className="col-span-2">Markup (%)</div>
                      </div>
                      
                      {tierFields.map((field, index) => (
                        <div key={field.id} className="grid grid-cols-12 gap-3 items-start group relative">
                          <div className="col-span-4">
                            <FormField
                              control={form.control}
                              name={`markupTiers.${index}.label`}
                              render={({ field }) => (
                                <FormItem>
                                  <FormControl><Input placeholder="e.g. High Value" {...field} /></FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                          </div>
                          <div className="col-span-3">
                            <FormField
                              control={form.control}
                              name={`markupTiers.${index}.minAmount`}
                              render={({ field }) => (
                                <FormItem>
                                  <FormControl><Input type="number" min="0" {...field} /></FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                          </div>
                          <div className="col-span-3">
                            <FormField
                              control={form.control}
                              name={`markupTiers.${index}.maxAmount`}
                              render={({ field }) => (
                                <FormItem>
                                  <FormControl><Input type="number" min="0" placeholder="Infinity" {...field} value={field.value || ""} /></FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                          </div>
                          <div className="col-span-2 relative">
                            <FormField
                              control={form.control}
                              name={`markupTiers.${index}.markupPercent`}
                              render={({ field }) => (
                                <FormItem>
                                  <FormControl><Input type="number" min="0" step="0.1" {...field} /></FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                            <Button 
                              type="button" 
                              variant="ghost" 
                              size="icon" 
                              className="absolute -right-10 top-0 h-9 w-9 text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-destructive transition-opacity"
                              onClick={() => removeTier(index)}
                            >
                              <Trash2 className="w-4 h-4" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-base flex items-center gap-2">
                    <FileText className="w-4 h-4 text-muted-foreground" />
                    Part Overrides
                  </CardTitle>
                  <CardDescription className="mt-1">
                    Map standard BOM parts to client-specific terminology and locked pricing.
                  </CardDescription>
                </div>
                <Button 
                  type="button" 
                  variant="outline" 
                  size="sm" 
                  onClick={() => appendPart({ standardName: "", clientName: "", unitCost: null, unit: "EA" })}
                >
                  <PlusCircle className="w-4 h-4 mr-2" /> Add Override
                </Button>
              </CardHeader>
              <CardContent>
                {partFields.length === 0 ? (
                  <div className="text-center p-8 border border-dashed rounded-lg text-muted-foreground text-sm bg-muted/10">
                    <FileText className="w-8 h-8 mx-auto mb-3 opacity-20" />
                    No part overrides configured.
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className="grid grid-cols-12 gap-3 px-3 pb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider border-b">
                      <div className="col-span-4">Standard Name</div>
                      <div className="col-span-4">Client Output Name</div>
                      <div className="col-span-2">Unit Cost ($)</div>
                      <div className="col-span-2">Unit</div>
                    </div>
                    
                    {partFields.map((field, index) => (
                      <div key={field.id} className="grid grid-cols-12 gap-3 items-start group relative">
                        <div className="col-span-4">
                          <FormField
                            control={form.control}
                            name={`partOverrides.${index}.standardName`}
                            render={({ field }) => (
                              <FormItem>
                                <FormControl><Input placeholder="e.g. Copper Pipe 1/2" {...field} /></FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </div>
                        <div className="col-span-4">
                          <FormField
                            control={form.control}
                            name={`partOverrides.${index}.clientName`}
                            render={({ field }) => (
                              <FormItem>
                                <FormControl><Input placeholder="e.g. CU-500" {...field} /></FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </div>
                        <div className="col-span-2">
                          <FormField
                            control={form.control}
                            name={`partOverrides.${index}.unitCost`}
                            render={({ field }) => (
                              <FormItem>
                                <FormControl><Input type="number" min="0" step="0.01" placeholder="Auto" {...field} value={field.value || ""} /></FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </div>
                        <div className="col-span-2 relative">
                          <FormField
                            control={form.control}
                            name={`partOverrides.${index}.unit`}
                            render={({ field }) => (
                              <FormItem>
                                <FormControl><Input placeholder="EA" {...field} /></FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          <Button 
                            type="button" 
                            variant="ghost" 
                            size="icon" 
                            className="absolute -right-10 top-0 h-9 w-9 text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-destructive transition-opacity"
                            onClick={() => removePart(index)}
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </form>
    </Form>
  );
}

function FileText(props: any) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
      <path d="M14 2v4a2 2 0 0 0 2 2h4" />
      <path d="M10 9H8" />
      <path d="M16 13H8" />
      <path d="M16 17H8" />
    </svg>
  )
}
