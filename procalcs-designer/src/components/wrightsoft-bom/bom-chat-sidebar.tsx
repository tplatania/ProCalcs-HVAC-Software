// BOM chat sidebar — the human-in-the-loop review agent (Day-22).
//
// Collapsible right-hand panel on the Wrightsoft BOM pages. The
// reviewer chats about the generated draft; the server-side agent
// (/api/bom-chat) can search the Wrightsoft catalog and propose
// line updates. Proposals render as cards with an Apply button —
// applying a price runs the SAME contractor-override path as the
// inline edit drawer, so every answer is learned once and reused
// on all future BOMs for the client.

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  MessageSquareText, Send, X, Loader2, Check, Sparkles, Paperclip, FileText,
} from "lucide-react";

interface ChatAttachment {
  id: string;
  name: string;
  kind: string;
  summary?: string;
  extracted?: string;
  image_b64?: string;
  media_type?: string;
}

interface ChatTurn {
  role: "user" | "assistant";
  text: string;
  actions?: ProposedAction[];
  attachments?: ChatAttachment[];
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

interface PendingQuestion {
  id: string;
  status: string;
  ask: string;
}

export function BomChatSidebar({ bom, onApplyPrice, clientId }: {
  /** The BOM response object — sent as context to the agent. */
  bom: unknown;
  /** Persist a price for a SKU via contractor overrides. Returns
   * true when the SKU was found and the save was kicked off. */
  onApplyPrice: (sku: string, price: number) => boolean;
  /** Contractor id — drives the pending-questions ledger lookup. */
  clientId?: string;
}) {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingQuestion[]>([]);
  const [closedCount, setClosedCount] = useState(0);
  const [showQuestions, setShowQuestions] = useState(true);
  const [staged, setStaged] = useState<ChatAttachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const stageFiles = async (list: FileList | null) => {
    if (!list?.length) return;
    setUploading(true);
    setError(null);
    try {
      const form = new FormData();
      for (const f of Array.from(list).slice(0, 5)) form.append("files", f);
      const res = await fetch("/api/bom-chat/attachments", {
        method: "POST", credentials: "same-origin", body: form,
      });
      const body = await res.json();
      if (!res.ok || !body.success) throw new Error(body.error || `HTTP ${res.status}`);
      setStaged((prev) => [...prev, ...(body.data.attachments as ChatAttachment[])].slice(0, 5));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  // Day-23 — surface the learning loop's surviving asks in-app so
  // nothing needs a Slack round-trip. Read-only ledger; answers go
  // through the chat (→ Apply → remembered forever).
  useEffect(() => {
    if (!open || !clientId) return;
    fetch(`/api/questions/${encodeURIComponent(clientId)}`, {
      credentials: "same-origin",
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => {
        if (body?.success) {
          setPending(body.data.pending ?? []);
          setClosedCount(body.data.closed ?? 0);
        }
      })
      .catch(() => { /* ledger optional */ });
  }, [open, clientId]);

  const send = async () => {
    const text = input.trim();
    if ((!text && staged.length === 0) || busy) return;
    const outgoing = staged;
    setStaged([]);
    setInput("");
    setError(null);
    const nextTurns: ChatTurn[] = [...turns, {
      role: "user",
      text: text || `(sent ${outgoing.length} attachment${outgoing.length === 1 ? "" : "s"})`,
      attachments: outgoing.length ? outgoing : undefined,
    }];
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
          attachments: outgoing,
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

  // Portal to <body>: a transformed ancestor in the page layout was
  // capturing position:fixed, dropping the launcher mid-page instead
  // of the viewport corner (Gerald, 2026-07-16 screenshot).
  // Inline-style positioning on plain wrappers: the Button's
  // hover-elevate class sets position:relative, which overrode the
  // `fixed` utility and left the launcher in-flow (and 24px off the
  // LEFT edge via right-6-on-relative). Inline styles can't lose.
  if (!open) {
    return createPortal(
      <div style={{ position: "fixed", bottom: 24, right: 24, zIndex: 40 }}>
        <Button
          className="shadow-lg gap-2"
          onClick={() => setOpen(true)}
          data-testid="bom-chat-open"
        >
          <MessageSquareText className="w-4 h-4" />
          Ask about this BOM
        </Button>
      </div>,
      document.body,
    );
  }

  return createPortal(
    <div style={{ position: "fixed", top: 0, right: 0, zIndex: 40, height: "100%" }}
         className="w-[380px] border-l bg-background shadow-xl flex flex-col"
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

      {pending.length > 0 && showQuestions && (
        <div className="border-b bg-amber-50/60 dark:bg-amber-950/20 px-4 py-2"
             data-testid="pending-questions">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold">
              Open questions for your team ({pending.length})
              <span className="ml-1 font-normal text-muted-foreground">
                — {closedCount} already answered from your project history
              </span>
            </span>
            <Button variant="ghost" size="sm" className="h-5 px-1 text-[10px]"
                    onClick={() => setShowQuestions(false)}>hide</Button>
          </div>
          <ul className="mt-1 space-y-1">
            {pending.map((q) => (
              <li key={q.id} className="text-[11px] leading-snug flex items-start gap-1.5">
                <span className="mt-0.5">•</span>
                <span className="flex-1">{q.ask}</span>
                <Button variant="outline" size="sm" className="h-5 px-1.5 text-[10px] shrink-0"
                        onClick={() => { setInput(""); setShowQuestions(true);
                          setInput(`Re: ${q.ask.slice(0, 60)}… — `); }}>
                  answer
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

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
              {(t.attachments ?? []).map((a) => (
                <span key={a.id}
                      className="mt-1 flex items-center gap-1 text-[10px] opacity-80">
                  <FileText className="w-3 h-3" /> {a.name}
                </span>
              ))}
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

      {(staged.length > 0 || uploading) && (
        <div className="border-t px-3 py-1.5 flex flex-wrap gap-1.5 items-center"
             data-testid="staged-attachments">
          {staged.map((a, i) => (
            <span key={a.id}
                  className={"inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] " +
                             (a.kind === "unsupported" || a.kind === "error"
                              ? "border-destructive text-destructive" : "bg-muted")}>
              <FileText className="w-3 h-3" /> {a.name}
              <button onClick={() => setStaged((p) => p.filter((_, j) => j !== i))}
                      className="ml-0.5 opacity-60 hover:opacity-100">
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
          {uploading && <Loader2 className="w-3 h-3 animate-spin" />}
        </div>
      )}
      <div className="border-t p-3 flex gap-2">
        <input ref={fileRef} type="file" multiple className="hidden"
               accept=".rup,.xls,.xlsx,.csv,.pdf,.docx,.txt,.md,.json,.png,.jpg,.jpeg,.webp,.gif"
               onChange={(e) => stageFiles(e.target.files)}
               data-testid="bom-chat-file-input" />
        <Button variant="outline" size="icon" disabled={uploading || busy}
                onClick={() => fileRef.current?.click()}
                title="Attach files (rup, xls, pdf, images…)">
          <Paperclip className="w-4 h-4" />
        </Button>
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
        <Button size="icon" onClick={send}
                disabled={busy || uploading || (!input.trim() && staged.length === 0)}>
          <Send className="w-4 h-4" />
        </Button>
      </div>
    </div>,
    document.body,
  );
}
