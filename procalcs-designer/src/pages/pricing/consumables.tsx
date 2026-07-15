// Pricing → Consumables — edit any contractor's install-consumables
// multipliers + unit costs.
//
// Day-17. The editor body itself lives in <ConsumablesEditor /> so the
// same UI also embeds inside /profiles/<id>. This page exists as a
// quick-access shortcut with a contractor picker on top.

import { useEffect, useState } from "react";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useListClientProfiles } from "@/lib/api-hooks";
import { ConsumablesEditor } from "@/components/consumables-editor";

const DEFAULT_CLIENT_ID = "procalcs-direct";

export default function PricingConsumablesPage() {
  const profiles = useListClientProfiles();
  const [clientId, setClientId] = useState<string>("");

  useEffect(() => {
    if (clientId) return;
    const list = profiles.data ?? [];
    if (list.length === 0) return;
    const match = list.find((p) => p.id === DEFAULT_CLIENT_ID);
    setClientId(match ? DEFAULT_CLIENT_ID : list[0].id);
  }, [profiles.data, clientId]);

  return (
    <div className="max-w-5xl mx-auto space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Install Consumables</h1>
          <p className="text-muted-foreground mt-2">
            Per-contractor multipliers and unit prices for mastic, tape, and screws.
            These drive the <strong>Install consumables</strong> rows on every Quick Order Summary
            for this contractor.
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/pricing/overrides"><Button variant="outline">← Overrides</Button></Link>
          <Link href="/pricing/import"><Button variant="outline">Import →</Button></Link>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Contractor</CardTitle>
          <CardDescription>
            Pick the contractor whose consumables config you want to edit. Or open the contractor
            directly from <Link href="/profiles" className="underline">Profiles</Link> — the same editor lives there.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Select value={clientId} onValueChange={setClientId} disabled={profiles.isPending}>
            <SelectTrigger className="max-w-md">
              <SelectValue placeholder="Pick a contractor profile" />
            </SelectTrigger>
            <SelectContent>
              {(profiles.data ?? []).map((p) => (
                <SelectItem key={p.id} value={p.id}>{p.name || p.id}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      {clientId && <ConsumablesEditor clientId={clientId} />}
    </div>
  );
}
