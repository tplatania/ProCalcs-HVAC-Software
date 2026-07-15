// BOM chat sidebar — the human-in-the-loop review agent (Day-22).
//
// Collapsible right-hand panel on the Wrightsoft BOM pages. The
// reviewer chats about the generated draft; the server-side agent
// (/api/bom-chat) can search the Wrightsoft catalog and propose
// line updates. Proposals render as cards with an Apply button —
// applying a price runs the SAME contractor-override path as the
// inline edit drawer, so every answer is learned once and reused
// on all future BOMs for the client.

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  MessageSquareText, Send, X, Loader2, Check, Sparkles,
} from "lucide-react";

interface ChatTurn {
  role: "user" | "assistant";
  text: string;
  actions?: ProposedAction[];
}

export interface ProposedAction {
  kind: "propose_line_update" | "propose_add_line";
  sku: string;
  description?: string;
  quantity?: number;
  unit_price?: number;
  source?: string;
  reason: string;
  applied?: boolean;
}

export function BomChatSidebar({ bom, onApplyPrice }: {
  /** The BOM response object — sent as context to the agent. */
  bom: unknown;
  /** Persist a price for a SKU via contractor overrides. Returns
   * true when the SKU was found and the save was kicked off. */
  onApplyPrice: (sku: string, price: number) => boolean;
}) {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setError(null);
    const nextTurns: ChatTurn[] = [...turns, { role: "user", text }];
    setTurns(nextTurns);
    setBusy(true);
    try {
      const res = await fetch("/api/bom-chat", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: nextTurns.map((t) => ({ role: t.role, content: t.text })),
          bom_context: bom,
        }),
      });
      const body = await res.json();
      if (!res.ok || !body.success) {
        throw new Error(body.error || `HTTP ${res.status}`);
      }
      setTurns((prev) => [...prev, {
        role: "assistant",
        text: body.data.reply || "(no reply)",
        actions: (body.data.actions || []) as ProposedAction[],
      }]);
      requestAnimationFrame(() => {
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const applyAction = (turnIdx: number, actionIdx: number) => {
    const action = turns[turnIdx]?.actions?.[actionIdx];
    if (!action || action.applied) return;
    if (action.kind === "propose_line_update" && action.unit_price != null) {
      const ok = onApplyPrice(action.sku, action.unit_price);
      if (!ok) {
        setError(`SKU ${action.sku} not found in the current draft.`);
        return;
      }
      setTurns((prev) => {
        const next = prev.slice();
        const actions = next[turnIdx].actions!.slice();
        actions[actionIdx] = { ...actions[actionIdx], applied: true };
        next[turnIdx] = { ...next[turnIdx], actions };
        return next;
      });
    }
  };

  if (!open) {
    return (
      <Button
        className="fixed bottom-6 right-6 z-40 shadow-lg gap-2"
        onClick={() => setOpen(true)}
        data-testid="bom-chat-open"
      >
        <MessageSquareText className="w-4 h-4" />
        Ask about this BOM
      </Button>
    );
  }

  return (
    <div className="fixed top-0 right-0 z-40 h-full w-[380px] border-l bg-background shadow-xl flex flex-col"
         data-testid="bom-chat-sidebar">
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles className="w-4 h-4 text-amber-500" />
          BOM Review Assistant
        </div>
        <Button variant="ghost" size="icon" onClick={() => setOpen(false)}>
          <X className="w-4 h-4" />
        </Button>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {turns.length === 0 && (
          <div className="text-xs text-muted-foreground space-y-2 pt-2">
            <p>Ask about gaps in this draft — for example:</p>
            <ul className="list-disc pl-4 space-y-1">
              <li>"Why do the Rheia lines have no price?"</li>
              <li>"The 3-in duct is $1.42/ft" — I'll propose the update
                  and you apply it with one click.</li>
              <li>"What is SKU 10-01-041?"</li>
            </ul>
            <p>Applied prices are remembered for all future BOMs.</p>
          </div>
        )}
        {turns.map((t, ti) => (
          <div key={ti} className={t.role === "user" ? "text-right" : ""}>
            <div className={
              "inline-block max-w-[92%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap text-left " +
              (t.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted")
            }>
              {t.text}
            </div>
            {(t.actions ?? []).map((a, ai) => (
              <div key={ai}
                   className="mt-2 rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/30 px-3 py-2 text-xs text-left">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="font-mono font-medium">{a.sku}</div>
                    <div className="text-muted-foreground">
                      {a.kind === "propose_line_update"
                        ? <>Set price to <b>${a.unit_price?.toFixed(2)}</b>
                            {a.quantity != null && <> · qty {a.quantity}</>}</>
                        : <>Add line: {a.description} · qty {a.quantity}
                            {a.unit_price != null && <> · ${a.unit_price.toFixed(2)}</>}</>}
                    </div>
                    <div className="italic mt-0.5">{a.reason}</div>
                  </div>
                  {a.kind === "propose_line_update" ? (
                    a.applied ? (
                      <Badge variant="outline" className="gap-1 text-emerald-700 border-emerald-300">
                        <Check className="w-3 h-3" /> Applied
                      </Badge>
                    ) : (
                      <Button size="sm" className="h-7"
                              onClick={() => applyAction(ti, ai)}
                              data-testid={`apply-${a.sku}`}>
                        Apply
                      </Button>
                    )
                  ) : (
                    <Badge variant="outline">manual add</Badge>
                  )}
                </div>
              </div>
            ))}
          </div>
        ))}
        {busy && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="w-3 h-3 animate-spin" /> thinking…
          </div>
        )}
        {error && <div className="text-xs text-destructive">{error}</div>}
      </div>

      <div className="border-t p-3 flex gap-2">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
          }}
          placeholder="Ask, or paste a price…"
          className="min-h-[38px] max-h-28 text-sm resize-none"
          data-testid="bom-chat-input"
        />
        <Button size="icon" onClick={send} disabled={busy || !input.trim()}>
          <Send className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
}
