// modelConfig.ts — single source of truth for which Anthropic model
// the chat agent runs on. Env-driven so the model can change with a
// Cloud Run env update (new revision) instead of a code change, and
// roll back the same way.
//
// Resolution order:
//   1. CHAT_MODEL           — exact model id, wins if set
//   2. CHAT_MODEL_TIER      — premium | standard | fast
//   3. default              — premium (claude-opus-4-8), i.e. today's
//                             behavior, so this layer is a no-op until
//                             an env value is set.
//
// The tier ids below are the ones this codebase already runs on:
// premium = the chat's current hardcoded Opus; standard = the Sonnet
// the BOM service uses (ANTHROPIC_MODEL default); fast = Haiku.

export type ModelTier = "premium" | "standard" | "fast";

export const TIER_MODELS: Record<ModelTier, string> = {
  premium: "claude-opus-4-8",
  standard: "claude-sonnet-4-20250514",
  fast: "claude-haiku-4-5-20251001",
};

const DEFAULT_TIER: ModelTier = "premium";

function isTier(v: string | undefined): v is ModelTier {
  return v === "premium" || v === "standard" || v === "fast";
}

/** Resolve the model id for a given tier, honoring env overrides. When
 * a tier is passed (from a routing policy, phase B) it is used unless
 * CHAT_MODEL forces an exact id. With no argument, resolves the default
 * chat model from env (CHAT_MODEL / CHAT_MODEL_TIER) or the premium
 * default. */
export function resolveModel(tier?: ModelTier): string {
  const exact = process.env.CHAT_MODEL?.trim();
  if (exact) return exact;
  if (tier) return TIER_MODELS[tier];
  const envTier = process.env.CHAT_MODEL_TIER?.trim();
  if (isTier(envTier)) return TIER_MODELS[envTier];
  return TIER_MODELS[DEFAULT_TIER];
}
