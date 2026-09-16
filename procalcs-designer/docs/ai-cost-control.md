# AI cost control & observability (branch: feature/ai-cost-control)

A self-contained bundle to measure and reduce the Anthropic spend that
comes from the **chat agent** (the BOM draft-review assistant). The
deterministic Wrightsoft `.rup` → BOM path uses no AI and is untouched.

**Everything defaults to today's behavior** (Opus, no routing), so
merging this branch changes nothing until an env var is set. All
switches are Cloud Run env vars → activate and roll back without a code
deploy.

## What's in it

| Phase | What | Files |
|---|---|---|
| C | **Observability** — capture chat token usage + model; a cost endpoint | `bomChat.ts`, `usage.ts`, `services/model_pricing.py`, `usage_events_routes.py` |
| A | **Model config layer** — env-driven chat model with named tiers | `server/modelConfig.ts` |
| D | **Prompt caching** — cache the full system prefix (incl. the ~120KB BOM context) | `bomChat.ts` |
| B | **Routing policy** — opt-in, route simple lookups to a cheaper model | `server/modelRouting.ts` |

## The env switches

| Env var | Values | Default | Effect |
|---|---|---|---|
| `CHAT_MODEL` | exact model id | unset | Forces the chat to that exact model (wins over everything). |
| `CHAT_MODEL_TIER` | `premium` / `standard` / `fast` | `premium` | Sets the chat model by tier (Opus / Sonnet / Haiku). |
| `CHAT_ROUTING_POLICY` | `all-premium` / `tiered` | `all-premium` | `tiered` routes clearly-simple catalog lookups to `standard`, keeps edits/reasoning on `premium`. |

Tier → model: premium=`claude-opus-4-8`, standard=`claude-sonnet-4-20250514`,
fast=`claude-haiku-4-5-20251001` (edit `modelConfig.ts` to change).

## Reading the spend

`GET /api/usage/cost?days=30` (proxied to the BOM backend) returns
estimated USD by model and by day, from the token counts now logged on
every `chat_message`. Prices live in `services/model_pricing.py`
(server-side, so history re-prices if rates change). Note: only chats
**after this ships** carry token detail; earlier ones read as $0.

Caveat: it's an in-app estimate for trend/relative comparison, not a
substitute for the Anthropic console bill.

## Recommended activation sequence

1. **Ship C + D only, change nothing else.** D (prompt caching) is a
   pure win — no quality change — and often cuts chat input-token cost
   by >50% on multi-turn conversations. C makes the effect visible.
   Watch `/api/usage/cost` for a week.
2. **Then try routing:** set `CHAT_ROUTING_POLICY=tiered`. Simple
   lookups drop to Sonnet (~5× cheaper/token); everything else stays
   Opus. Compare cost + spot-check chat quality.
3. **Optional, aggressive:** `CHAT_MODEL_TIER=standard` runs the whole
   chat on Sonnet. Only if quality holds on the pilot's real tasks.

Roll back any step by clearing the env var (new revision, instant).

## Safety

- Default behavior unchanged until an env var is set.
- The Wrightsoft BOM generation path (the pilot's core flow) is not
  touched.
- The routing policy is conservative: ambiguous or edit-shaped turns
  stay premium; only short lookup-shaped questions route down.
