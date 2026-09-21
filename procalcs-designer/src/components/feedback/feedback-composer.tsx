// Shared "start a feedback/ask thread" dialog. Used by the global
// Feedback page ("New") and by the embedded "Flag this" button on the
// BOM result page (pre-linked to a run + page). One agent nudge, then
// it's captured — no back-and-forth here; follow-ups happen in-thread.

import { useRef, useState } from "react";
import { ImagePlus, X, Loader2, MessageSquarePlus } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  useCreateFeedbackThread, type FeedbackKind, type FeedbackThreadDetail,
} from "@/lib/api-hooks";

const MAX_FILES = 5;
const MAX_BYTES = 8 * 1024 * 1024;

export function FeedbackComposerDialog({
  open, onOpenChange, defaultKind = "report", pageContext, runId, clientId,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  defaultKind?: FeedbackKind;
  pageContext?: string;
  runId?: number | null;
  clientId?: string;
  onCreated?: (thread: FeedbackThreadDetail) => void;
}) {
  const [kind, setKind] = useState<FeedbackKind>(defaultKind);
  const [body, setBody] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const create = useCreateFeedbackThread();

  const reset = () => {
    setKind(defaultKind); setBody(""); setFiles([]); setErr(null);
  };

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    const next = [...files];
    for (const f of Array.from(list)) {
      if (next.length >= MAX_FILES) break;
      if (f.size > MAX_BYTES) { setErr(`${f.name} is over 8 MB — skipped.`); continue; }
      next.push(f);
    }
    setFiles(next);
    if (fileRef.current) fileRef.current.value = "";
  };

  const submit = async () => {
    setErr(null);
    if (!body.trim()) { setErr("Add a short description first."); return; }
    try {
      const thread = await create.mutateAsync({
        kind, body: body.trim(), page_context: pageContext,
        run_id: runId ?? undefined, client_id: clientId, files,
      });
      onCreated?.(thread);
      reset();
      onOpenChange(false);
    } catch (e: any) {
      setErr(e?.error ?? "Could not submit — please try again.");
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) reset(); onOpenChange(o); }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <MessageSquarePlus className="w-4 h-4" />
            {kind === "report" ? "Report something" : "Ask the team"}
          </DialogTitle>
          <DialogDescription>
            {runId
              ? "Linked to this BOM so the team has the context automatically."
              : "Goes to the team in-app — no email or file transfer needed."}
          </DialogDescription>
        </DialogHeader>

        {/* Kind toggle */}
        <div className="flex gap-1 rounded-lg bg-muted p-1 text-sm">
          {(["report", "question"] as FeedbackKind[]).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setKind(k)}
              className={cn(
                "flex-1 rounded-md px-3 py-1.5 font-medium transition-colors",
                kind === k ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {k === "report" ? "Report / feedback" : "Question for the team"}
            </button>
          ))}
        </div>

        <Textarea
          autoFocus
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder={
            kind === "report"
              ? "What did you expect, and what happened? A screenshot helps."
              : "What do you need answered? Anyone on the team can reply."
          }
          rows={5}
        />

        {/* Attachments */}
        <div className="space-y-2">
          <input
            ref={fileRef}
            type="file"
            multiple
            accept="image/*,.pdf,.xls,.xlsx,.csv"
            className="hidden"
            onChange={(e) => addFiles(e.target.files)}
          />
          <Button type="button" variant="outline" size="sm"
                  onClick={() => fileRef.current?.click()}
                  disabled={files.length >= MAX_FILES}>
            <ImagePlus className="w-3.5 h-3.5 mr-1.5" />
            Attach screenshot{files.length ? ` (${files.length}/${MAX_FILES})` : ""}
          </Button>
          {files.length > 0 && (
            <ul className="flex flex-wrap gap-2">
              {files.map((f, i) => (
                <li key={i}
                    className="flex items-center gap-1.5 rounded border bg-muted/40 px-2 py-1 text-xs">
                  {f.type.startsWith("image/") && (
                    <img src={URL.createObjectURL(f)} alt=""
                         className="h-6 w-6 rounded object-cover" />
                  )}
                  <span className="max-w-[140px] truncate">{f.name}</span>
                  <button type="button"
                          onClick={() => setFiles(files.filter((_, j) => j !== i))}
                          className="text-muted-foreground hover:text-foreground">
                    <X className="w-3 h-3" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {err && <p className="text-sm text-destructive">{err}</p>}

        <DialogFooter>
          <Button variant="ghost" onClick={() => { reset(); onOpenChange(false); }}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={create.isPending || !body.trim()}>
            {create.isPending && <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />}
            Submit
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
