// modelRouting.ts — task-based model tier policy for the chat agent.
//
// A pure function from request signals to a model tier. It is OPT-IN
// and conservative:
//   - CHAT_ROUTING_POLICY unset / "all-premium" (default) → returns
//     undefined, i.e. "no opinion" — the model layer falls back to
//     CHAT_MODEL / CHAT_MODEL_TIER / premium. So this file is a no-op
//     until the policy env is flipped to "tiered".
//   - "tiered" → only clearly-simple lookups are routed down to
//     `standard` (Sonnet); anything that edits the BOM, reasons, or
//     carries rich context stays `premium` (Opus). Ambiguous → premium.
//
// The model is chosen before the response, so routing keys off the
// incoming user message + context signals only, never on which tools
// end up being called.

import type { ModelTier } from "./modelConfig.js";

export type ChatSignals = {
  userText: string;
  hasAttachments: boolean;
  hasSnipes: boolean;
};

// Cues that keep a turn on the premium model: edits, corrections, and
// anything that needs real reasoning about the BOM.
const PREMIUM_CUES = [
  "regenerate", "fix", "wrong", "incorrect", "should be", "instead",
  "remove", "replace", "combine", "split", "missing", "why", "explain",
  "price", "cost", "quantity", "qty", "$", "markup", "overrid",
];

// Cues that a turn is a simple catalog lookup / factual question.
const SIMPLE_CUES = [
  "what is", "what's", "search", "find ", "look up", "lookup",
  "does the catalog", "is there", "how many", "list ", "show me",
];

export function routeTier(signals: ChatSignals): ModelTier | undefined {
  const policy = (process.env.CHAT_ROUTING_POLICY ?? "all-premium").trim();
  if (policy !== "tiered") return undefined; // defer to the model layer

  // Rich context (sniped tables/rows, uploaded files) → premium.
  if (signals.hasAttachments || signals.hasSnipes) return "premium";

  const t = signals.userText.toLowerCase();
  if (PREMIUM_CUES.some((c) => t.includes(c))) return "premium";

  // Short, lookup-shaped question with no edit cues → standard.
  if (t.length <= 240 && SIMPLE_CUES.some((c) => t.includes(c))) {
    return "standard";
  }
  return "premium"; // conservative default within the tiered policy
}
