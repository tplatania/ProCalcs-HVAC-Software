// /api/questions — the contractor question ledger, exposed read-only.
//
// Surfaces the learning loop's SURVIVING asks (not-in-data pastes +
// provisional one-liners) so contractor-side reviewers see exactly
// what's needed inside the app instead of over Slack/email. Answers
// flow through the existing chat → Apply → contractor-override
// pipeline; this route is visibility only.
//
// Source of truth: contractor-rules/<contractor>/questions.yaml,
// shipped into the image (see Dockerfile). Unknown contractor → 404;
// missing file → empty list (the ledger is optional per contractor).

import { Router, type Request, type Response } from "express";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { load as yamlLoad } from "js-yaml";

const router = Router();
const __dirname = path.dirname(fileURLToPath(import.meta.url));

// dist-server/ at runtime; server/routes/ under tsx. Walk up to repo root.
const CANDIDATES = [
  path.resolve(__dirname, "../../contractor-rules"),
  path.resolve(__dirname, "../contractor-rules"),
  path.resolve(process.cwd(), "contractor-rules"),
];

interface LedgerQuestion {
  id: string;
  question: string;
  status: string;
  for_richard?: string;
  confirmation_line?: string;
  answer?: string;
}

function loadLedger(contractor: string): LedgerQuestion[] | null {
  const safe = contractor.replace(/[^a-z0-9-]/gi, "");
  // ledger dirs use short names (reliable) while client ids are long
  // (reliable-heating-and-cooling) — try both.
  const names = [safe, safe.split("-")[0]];
  for (const base of CANDIDATES) {
    for (const name of names) {
      const p = path.join(base, name, "questions.yaml");
      if (fs.existsSync(p)) {
        const doc = yamlLoad(fs.readFileSync(p, "utf-8")) as {
          questions?: LedgerQuestion[];
        };
        return doc?.questions ?? [];
      }
    }
  }
  return null;
}

// GET /api/questions/:contractor — pending items + closed count.
router.get("/:contractor", (req: Request, res: Response) => {
  const all = loadLedger(req.params.contractor);
  if (all === null) {
    res.status(404).json({ success: false, data: null, error: "no ledger for contractor" });
    return;
  }
  const pending = all
    .filter((q) => q.status === "not-in-data" || q.status === "provisional"
                   || q.status === "open")
    .map((q) => ({
      id: q.id,
      status: q.status,
      // The reviewer-facing ask, not the internal research question.
      ask: q.for_richard || q.confirmation_line || q.question,
    }));
  res.json({
    success: true,
    data: {
      pending,
      closed: all.length - pending.length,
      total: all.length,
    },
    error: null,
  });
});

export default router;
