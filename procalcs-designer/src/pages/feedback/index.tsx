// /feedback — the global Feedback & Questions inbox.
//
// Left: thread list (filter by kind + status). Right: the selected
// thread with its messages, attachments, a reply box, and resolve.
// Threads are created here ("New") or from the "Flag this" button on a
// BOM result (which deep-links via ?thread=<id>). All-team, in-app.

import { useEffect, useMemo, useState } from "react";
import { useLocation, useSearch } from "wouter";
import {
  MessageSquarePlus, Bot, CheckCircle2, RotateCcw, ImagePlus, Loader2,
  Paperclip, Send, Inbox,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { FeedbackComposerDialog } from "@/components/feedback/feedback-composer";
import {
  useFeedbackThreads, useFeedbackThread, useAddFeedbackMessage,
  useResolveFeedbackThread, feedbackAttachmentUrl,
  type FeedbackKind, type FeedbackStatus, type FeedbackThreadSummary,
  type FeedbackMessage, type FeedbackAttachmentMeta,
} from "@/lib/api-hooks";

function statusTone(s: FeedbackStatus) {
  return s === "open" ? "bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
    : s === "answered" ? "bg-sky-100 text-sky-800 dark:bg-sky-950/40 dark:text-sky-200"
    : "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200";
}

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso).getTime();
  const s = Math.max(0, (Date.now() - d) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function AttachmentChip({ a }: { a: FeedbackAttachmentMeta }) {
  const url = feedbackAttachmentUrl(a.id);
  if (a.is_image) {
    return (
      <a href={url} target="_blank" rel="noreferrer" className="block">
        <img src={url} alt={a.filename}
             className="h-24 w-auto max-w-[200px] rounded border object-cover" />
      </a>
    );
  }
  return (
    <a href={url} target="_blank" rel="noreferrer"
       className="inline-flex items-center gap-1.5 rounded border bg-muted/40 px-2 py-1 text-xs hover:bg-muted">
      <Paperclip className="w-3 h-3" /> {a.filename}
    </a>
  );
}

function MessageRow({ m, atts }:
  { m: FeedbackMessage; atts: FeedbackAttachmentMeta[] }) {
  const mine = atts.filter((a) => a.message_id === m.id);
  if (m.role === "agent") {
    return (
      <div className="flex items-start gap-2 text-sm text-muted-foreground">
        <Bot className="mt-0.5 h-4 w-4 shrink-0" />
        <p className="italic">{m.body}</p>
      </div>
    );
  }
  const isTeam = m.role === "team";
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 text-xs">
        <span className="font-medium">{m.author_email ?? "unknown"}</span>
        <Badge variant="outline" className={cn("text-[10px]",
          isTeam ? "border-violet-400 text-violet-700 dark:text-violet-300" : "")}>
          {isTeam ? "Team" : "Tester"}
        </Badge>
        <span className="text-muted-foreground">{timeAgo(m.created_at)}</span>
      </div>
      {m.body && <p className="whitespace-pre-wrap text-sm">{m.body}</p>}
      {mine.length > 0 && (
        <div className="flex flex-wrap gap-2 pt-1">
          {mine.map((a) => <AttachmentChip key={a.id} a={a} />)}
        </div>
      )}
    </div>
  );
}

function ThreadDetail({ id }: { id: number }) {
  const { data: thread, isLoading } = useFeedbackThread(id);
  const addMsg = useAddFeedbackMessage();
  const resolve = useResolveFeedbackThread();
  const [reply, setReply] = useState("");
  const [files, setFiles] = useState<File[]>([]);

  useEffect(() => { setReply(""); setFiles([]); }, [id]);

  if (isLoading || !thread) {
    return <div className="p-8 text-sm text-muted-foreground">Loading thread…</div>;
  }
  // Attachments not tied to a specific message (e.g. first submit) render
  // under the opening message; group by message_id, with null → first msg.
  const firstMsgId = thread.messages[0]?.id ?? null;
  const attByMsg = thread.attachments.map((a) => ({
    ...a, message_id: a.message_id ?? firstMsgId,
  }));

  const send = async () => {
    if (!reply.trim() && files.length === 0) return;
    await addMsg.mutateAsync({ threadId: id, body: reply.trim(), files });
    setReply(""); setFiles([]);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-3 border-b p-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Badge className={statusTone(thread.status)}>{thread.status}</Badge>
            <Badge variant="outline">{thread.kind === "question" ? "Question" : "Report"}</Badge>
            {thread.run_id && (
              <span className="text-xs text-muted-foreground">BOM run #{thread.run_id}</span>
            )}
          </div>
          <h2 className="mt-1 truncate text-base font-semibold">{thread.title}</h2>
        </div>
        {thread.status !== "resolved" ? (
          <Button size="sm" variant="outline"
                  onClick={() => resolve.mutate({ threadId: id, status: "resolved" })}>
            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" /> Mark resolved
          </Button>
        ) : (
          <Button size="sm" variant="ghost"
                  onClick={() => resolve.mutate({ threadId: id, status: "open" })}>
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" /> Reopen
          </Button>
        )}
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {thread.messages.map((m) => (
          <MessageRow key={m.id} m={m} atts={attByMsg} />
        ))}
      </div>

      <div className="border-t p-3">
        <Textarea value={reply} onChange={(e) => setReply(e.target.value)}
                  placeholder="Reply…" rows={2} className="mb-2" />
        <div className="flex items-center justify-between">
          <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
            <ImagePlus className="h-3.5 w-3.5" />
            {files.length ? `${files.length} file(s)` : "Attach"}
            <input type="file" multiple accept="image/*,.pdf,.xls,.xlsx,.csv"
                   className="hidden"
                   onChange={(e) => setFiles(Array.from(e.target.files ?? []).slice(0, 5))} />
          </label>
          <Button size="sm" onClick={send}
                  disabled={addMsg.isPending || (!reply.trim() && !files.length)}>
            {addMsg.isPending
              ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              : <Send className="mr-1.5 h-3.5 w-3.5" />}
            Send
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function FeedbackPage() {
  const [, navigate] = useLocation();
  const searchStr = useSearch();
  const [kindFilter, setKindFilter] = useState<FeedbackKind | "all">("all");
  const [statusFilter, setStatusFilter] = useState<FeedbackStatus | "all">("all");
  const [composerOpen, setComposerOpen] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);

  // Deep link from "Flag this": /feedback?thread=<id>
  useEffect(() => {
    const t = new URLSearchParams(searchStr).get("thread");
    if (t) setSelected(Number(t));
  }, [searchStr]);

  const { data, isLoading } = useFeedbackThreads({
    kind: kindFilter === "all" ? undefined : kindFilter,
    status: statusFilter === "all" ? undefined : statusFilter,
  });
  const threads = data?.threads ?? [];

  const list = useMemo(() => threads, [threads]);

  return (
    <div className="mx-auto max-w-[1200px] p-4 sm:p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Feedback &amp; Questions</h1>
          <p className="text-sm text-muted-foreground">
            Report issues or ask the team — screenshots welcome, all in-app.
          </p>
        </div>
        <Button onClick={() => setComposerOpen(true)}>
          <MessageSquarePlus className="mr-1.5 h-4 w-4" /> New
        </Button>
      </div>

      <div className="mb-3 flex flex-wrap gap-2 text-sm">
        {(["all", "report", "question"] as const).map((k) => (
          <button key={k} onClick={() => setKindFilter(k)}
                  className={cn("rounded-full border px-3 py-1",
                    kindFilter === k ? "bg-foreground text-background" : "hover:bg-muted")}>
            {k === "all" ? "All" : k === "report" ? "Reports" : "Questions"}
          </button>
        ))}
        <span className="mx-1 w-px bg-border" />
        {(["all", "open", "answered", "resolved"] as const).map((s) => (
          <button key={s} onClick={() => setStatusFilter(s)}
                  className={cn("rounded-full border px-3 py-1 capitalize",
                    statusFilter === s ? "bg-foreground text-background" : "hover:bg-muted")}>
            {s}
          </button>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-[minmax(280px,360px)_1fr]">
        {/* List */}
        <div className="space-y-2">
          {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {!isLoading && list.length === 0 && (
            <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-10 text-center text-sm text-muted-foreground">
              <Inbox className="h-6 w-6" />
              Nothing here yet.
            </div>
          )}
          {list.map((t: FeedbackThreadSummary) => (
            <button key={t.id} onClick={() => setSelected(t.id)}
                    className={cn("w-full rounded-lg border p-3 text-left transition-colors",
                      selected === t.id ? "border-foreground bg-muted/50" : "hover:bg-muted/30")}>
              <div className="flex items-center gap-2">
                <Badge className={cn("text-[10px]", statusTone(t.status))}>{t.status}</Badge>
                <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  {t.kind}
                </span>
                <span className="ml-auto text-[11px] text-muted-foreground">
                  {timeAgo(t.last_message_at ?? t.created_at)}
                </span>
              </div>
              <p className="mt-1 line-clamp-2 text-sm font-medium">{t.title}</p>
              <div className="mt-1 flex items-center gap-3 text-[11px] text-muted-foreground">
                <span>{t.created_by_email ?? "—"}</span>
                {t.attachment_count > 0 && (
                  <span className="inline-flex items-center gap-0.5">
                    <Paperclip className="h-3 w-3" />{t.attachment_count}
                  </span>
                )}
                {t.run_id && <span>run #{t.run_id}</span>}
              </div>
            </button>
          ))}
        </div>

        {/* Detail */}
        <Card className="min-h-[420px] overflow-hidden">
          {selected
            ? <ThreadDetail id={selected} />
            : <div className="flex h-full min-h-[420px] items-center justify-center p-8 text-center text-sm text-muted-foreground">
                Select a thread, or start a new one.
              </div>}
        </Card>
      </div>

      <FeedbackComposerDialog
        open={composerOpen}
        onOpenChange={setComposerOpen}
        onCreated={(t) => { setSelected(t.id); navigate(`/feedback?thread=${t.id}`); }}
      />
    </div>
  );
}
