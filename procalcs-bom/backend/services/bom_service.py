"""
bom_service.py — AI-powered BOM generation engine
Reads completed HVAC design data, calls Claude AI,
applies client profile, returns structured BOM.
Follows ProCalcs Design Standards v2.0

CRITICAL RULE (from design standards):
AI reads text and reasons. Python does math.
Never let AI calculate totals — AI estimates quantities,
Python multiplies by price and applies markup.
"""

import logging
import json
import anthropic
from flask import current_app
from services.profile_service import get_profile_by_id
from services import sku_catalog
from services.materials_rules import generate_rule_lines
from services.catalog_match import (
    match_equipment_to_catalog,
    coalesce_matched_lines,
)
from models.client_profile import ClientProfile


# Phase 5 (May 2026) — Map the AI-prompt category vocabulary
# (duct/fitting/equipment/register/consumable) into the contractor
# section structure (Equipment / Duct System Equipment / Rheia Duct
# System Equipment / Labor) per the sample BOM target shape.
#
# Rules-engine lines and catalog-match lines already carry a section
# field from the SKU Catalog; this fallback only kicks in for AI lines
# that the catalog couldn't pre-claim. Rheia routing requires explicit
# catalog signal — we don't try to AI-detect Rheia from a generic
# "duct" category since Rheia is small-diameter high-velocity and
# distinguishing it needs the HVDALL category match (Phase 2).
_AI_CATEGORY_TO_SECTION: dict[str, str] = {
    "equipment":  "Equipment",
    "duct":       "Duct System Equipment",
    "fitting":    "Duct System Equipment",
    "register":   "Duct System Equipment",
    "consumable": "Duct System Equipment",
}


def _section_for_line(item: dict) -> str:
    """Best section guess for a line item. Honors any pre-computed
    section (catalog or rules-engine emitted), then falls back to the
    AI-category map. Defaults to 'Duct System Equipment' so unknown
    AI items still group somewhere visible rather than disappearing
    into an unbucketed bottom-of-PDF section."""
    explicit = (item.get("section") or "").strip()
    if explicit:
        return explicit
    cat = (item.get("category") or "").lower().strip()
    return _AI_CATEGORY_TO_SECTION.get(cat, "Duct System Equipment")

logger = logging.getLogger('procalcs_bom')


# ===============================
# Output Modes
# ===============================

OUTPUT_MODES = {
    'full':             'All items — drawn parts and AI-estimated consumables',
    'materials_only':   'Field materials and consumables only — no equipment',
    'labor_materials':  'Full job cost including labor at client rates',
    'client_proposal':  'Client-facing — price shown, no cost exposure',
    'cost_estimate':    'Internal cost only — no markup shown',
}


# ===============================
# Main Entry Point
# ===============================

def generate(client_id: str, job_id: str, design_data: dict,
             output_mode: str = None) -> dict:
    """
    Generate a complete BOM for a finished HVAC design job.

    Steps:
    1. Load client profile from Firestore
    2. Build AI prompt from design data + profile context
    3. Call Claude — get raw material quantities back as JSON
    4. Apply pricing and markup in Python (never in AI)
    5. Format and return structured BOM

    Returns a dict with the complete BOM ready to render.
    Raises ValueError for missing profile.
    Raises RuntimeError for AI or processing failures.
    """
    logger.info("Starting BOM generation for client %s job %s", client_id, job_id)

    # Step 1 — Load profile
    profile_data = get_profile_by_id(client_id)
    if not profile_data:
        raise ValueError("No profile found for client_id '%s'. "
                         "Create a profile before generating a BOM." % client_id)

    profile = ClientProfile.from_dict(profile_data)
    effective_mode = output_mode or profile.default_output_mode

    # Step 2a — Deterministic rules engine first. Emits SKU-level lines
    # for everything the catalog can express (AHU/condenser/heat-kit
    # equipment, Rheia duct system, plenum take-offs, etc.). Catalog
    # default_unit_price is the cost; Python applies profile markup.
    rule_lines = generate_rule_lines(design_data, output_mode=effective_mode)
    rules_priced = _format_rule_lines_for_bom(rule_lines, profile)

    # Step 2a' — Catalog-augmented per-equipment match (Phase 3.7,
    # May 2026). The rules engine fires SKUs by trigger flags but
    # doesn't pick by capacity — if a project has 5 AHUs at 24 kBTU
    # and 3 at 36 kBTU, the rules engine emits 8x of one SKU. This
    # step looks up each parsed equipment item's capacity in the SKU
    # Catalog (filtered by contractor_id + capacity tolerance band)
    # and emits per-instance matches with confidence flags.
    # Coalesces same-SKU matches so output stays compact.
    equipment = (design_data or {}).get("equipment") or []
    matched_per_instance = match_equipment_to_catalog(equipment, client_id)
    catalog_matched = _format_catalog_matches_for_bom(
        coalesce_matched_lines(matched_per_instance), profile,
    )

    # Step 2b — AI fills the gaps the catalog doesn't cover yet
    # (consumables, miscellaneous fittings, brand-specific items).
    # Phase 7: pass already-claimed lines so Claude knows what NOT to
    # duplicate. Reduces hallucination + saves output tokens.
    already_claimed = catalog_matched + rules_priced
    raw_quantities = _call_ai_for_quantities(
        design_data, profile, claimed_lines=already_claimed,
    )

    # Step 3 — Apply pricing for AI-estimated items (Python does all math)
    ai_priced = _apply_pricing(raw_quantities, profile, effective_mode)

    # Source precedence: catalog_match > rules_engine > AI.
    #
    # Two collision rules — order matters:
    #
    # 1. SKU-level dedupe: rules engine fires every catalog SKU whose
    #    trigger flag is true (e.g. trigger=ahu_present matches ALL AHU
    #    SKUs without capacity discrimination). If catalog_match already
    #    emitted a per-equipment line for SKU X, don't let the rules
    #    engine re-emit X. Same for AI.
    # 2. Trigger-level suppression: if catalog_match emitted ANY line for
    #    trigger T (e.g. ahu_present via per-equipment capacity match),
    #    suppress all OTHER rules-engine SKUs that would fire on T.
    #    Otherwise we get phantom lines: a 60K AHU SKU fires because
    #    trigger=ahu_present is true, even though no 60K equipment
    #    exists in the design. Real money problem if not suppressed.
    # 3. Description-substring dedupe: catches AI items whose generic
    #    description matches something the catalog or rules already
    #    covered (e.g. AI emits "Air handler 24000 BTU" while catalog
    #    emitted GOOD-AHU-24K).

    catalog_skus = {li.get("sku") for li in catalog_matched if li.get("sku")}
    # Pull the trigger keys claimed by catalog_match. Sourced from the
    # original rule_lines vocabulary (ahu_present, condenser_present,
    # erv_present, heat_kit_present) — see services/catalog_match.py.
    claimed_triggers = {
        sku_catalog.get(li.get("sku")).trigger
        for li in catalog_matched
        if li.get("sku") and sku_catalog.get(li.get("sku"))
    }
    deduped_rules = [
        li for li in rules_priced
        if li.get("sku") not in catalog_skus
        and (
            sku_catalog.get(li.get("sku")) is None
            or sku_catalog.get(li.get("sku")).trigger not in claimed_triggers
        )
    ]

    claimed_descs: set[str] = set()
    for li in catalog_matched + deduped_rules:
        d = (li.get("description") or "").lower()
        if d:
            claimed_descs.add(d)
    deduped_ai = [
        li for li in ai_priced
        if not any(c and c in (li.get("description") or "").lower() for c in claimed_descs)
    ]

    priced_items = catalog_matched + deduped_rules + deduped_ai

    # Step 4 — Format final BOM
    bom = _format_bom(priced_items, profile, job_id, effective_mode)
    bom["catalog_match_item_count"] = len(catalog_matched)
    bom["rules_engine_item_count"] = len(deduped_rules)
    bom["ai_item_count"] = len(deduped_ai)

    logger.info("BOM generated successfully for job %s — %s line items",
                job_id, len(bom.get('line_items', [])))

    # Phase 3 (May 2026) — persist the run for Richard's testing-harness
    # history page. Best-effort: a DB hiccup must NOT fail an otherwise
    # successful BOM generation, since that's what the user is paying
    # to wait 15 seconds for. Caller can still recover the BOM from the
    # response even if persistence failed.
    try:
        _record_bom_run(
            client_id=client_id,
            job_id=job_id,
            output_mode=effective_mode,
            design_data=design_data,
            generated_bom=bom,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("BOM persistence failed for job %s — %s", job_id, exc)

    return bom


def _record_bom_run(
    *,
    client_id: str,
    job_id: str,
    output_mode: str,
    design_data: dict,
    generated_bom: dict,
) -> None:
    """Insert one bom_runs row + commit. Pulled out so the try/except
    around it stays narrow — DB failures shouldn't poison the BOM
    response. See models/bom_run.py for the full schema."""
    from models import BomRun
    from extensions import db
    from flask import g, has_request_context

    # Created-by attribution from the user-identity-forwarding middleware
    # (see app.py register_user_middleware). Optional — if the request
    # didn't carry X-Procalcs-User-Email (shared-secret-only call), we
    # still record the run but with no email.
    created_by_email = None
    if has_request_context():
        user = getattr(g, "current_user", None)
        if user is not None:
            created_by_email = getattr(user, "email", None)

    BomRun.record(
        client_id=client_id,
        job_id=job_id,
        output_mode=output_mode,
        parsed_design_data=design_data,
        generated_bom=generated_bom,
        created_by_email=created_by_email,
    )
    db.session.commit()


# ===============================
# AI Prompt + API Call
# ===============================

def _build_available_catalog_block(
    profile: ClientProfile,
    claimed_lines: list,
) -> str:
    """List the SKU Catalog entries available for the AI to reference,
    filtered to ones not already claimed by catalog_match + rules_engine.

    Phase 2 of Path B (May 2026). Closes the AI's previous gap of
    inventing SKU codes that look plausible but don't exist. By listing
    every callable catalog SKU + its key fields (manufacturer, capacity,
    description), Claude can output the EXACT sku string and the
    downstream pipeline picks up the catalog metadata (cost, supplier,
    section) deterministically.

    Filtering rules:
      - Exclude SKUs already in `claimed_lines` (catalog_match or
        rules_engine emitted them — no point listing for AI dup)
      - Include both contractor-scoped (matching profile.client_id)
        and globally-scoped (contractor_id None) SKUs
      - Exclude disabled SKUs

    Token budget: ~80 chars per SKU. With the 21 starter SKUs this is
    ~1.7 KB. Even at 200 SKUs it's ~16 KB — well within Anthropic's
    200K context window.

    Returns "" when the catalog is empty or all entries are claimed.
    """
    try:
        all_skus = sku_catalog.all_items(include_disabled=False)
    except Exception:
        # Catalog unavailable (Firestore creds missing in tests) — skip
        # the block entirely so the prompt stays valid.
        return ""

    claimed = {li.get("sku") for li in (claimed_lines or []) if li.get("sku")}
    contractor_id = getattr(profile, "client_id", None)

    in_scope = [
        s for s in all_skus
        if s.sku not in claimed
        and (s.contractor_id is None or s.contractor_id == contractor_id)
    ]
    if not in_scope:
        return ""

    rows: list[str] = []
    for s in in_scope:
        # One line per SKU: sku, capacity hint, description.
        cap_hint = ""
        if s.capacity_btu is not None:
            cap_hint = f" [{s.capacity_btu} BTU]"
        elif s.capacity_min_btu is not None and s.capacity_max_btu is not None:
            cap_hint = f" [{s.capacity_min_btu}-{s.capacity_max_btu} BTU]"
        mfr = f" ({s.manufacturer})" if s.manufacturer else ""
        rows.append(f"  - {s.sku}{cap_hint}{mfr} — {s.description}")

    return (
        "\n\nAVAILABLE CATALOG SKUs (you may reference any of these by "
        "exact `sku` code in the lines you output — the system will look "
        "up cost/supplier/section automatically. Prefer matching by "
        "capacity when an equipment item has BTU/tonnage. Set the `sku` "
        "field on lines where you pick a catalog entry; leave `sku` "
        "blank when no catalog entry fits and the line is genuinely "
        "novel):\n"
        + "\n".join(rows)
        + "\n"
    )


def _build_catalog_context_block(claimed_lines: list) -> str:
    """Build the 'ALREADY COVERED' prompt block so Claude doesn't
    re-emit lines the catalog_match + rules_engine layers already
    handled. Each entry is one line: source · sku · description.
    Returns empty string when nothing's claimed (early in adoption,
    before contractors encode SKUs)."""
    if not claimed_lines:
        return ""
    rows = []
    for li in claimed_lines:
        src   = li.get("source", "?")
        sku   = li.get("sku", "(no-sku)")
        desc  = (li.get("description") or "").strip()
        rows.append(f"  - [{src}] sku={sku} — {desc}")
    return (
        "\n\nALREADY COVERED (these SKUs are already in the BOM via "
        "the deterministic catalog/rules layers — do NOT emit "
        "duplicate lines for these). If you generate a line that "
        "describes the same physical item, the system will drop it "
        "via description-substring dedupe, so save us tokens by "
        "skipping them entirely:\n"
        + "\n".join(rows)
        + "\n"
    )


def _build_ai_prompt(
    design_data: dict,
    profile: ClientProfile,
    *,
    claimed_lines: list | None = None,
) -> str:
    """
    Build the prompt sent to Claude.
    Instructs AI to return ONLY quantities — no pricing, no math.
    Pricing is applied by Python after the AI responds.

    Phase 7 (May 2026): now accepts claimed_lines — the lines already
    emitted by catalog_match + rules_engine. We pass these to Claude
    as an "ALREADY COVERED" block so it doesn't duplicate equipment
    SKUs the deterministic layers already handled. Optional —
    pre-Phase-7 callers (tests, legacy) still work.
    """
    building  = design_data.get('building', {})
    duct_runs = design_data.get('duct_runs', [])
    fittings  = design_data.get('fittings', [])
    equipment = design_data.get('equipment', [])
    registers = design_data.get('registers', [])
    rooms     = design_data.get('rooms', [])
    raw_ctx   = design_data.get('raw_rup_context', '')

    # Phase 7 — context block listing what catalog_match + rules_engine
    # already claimed. Empty when both layers emitted nothing.
    catalog_context_block = _build_catalog_context_block(claimed_lines or [])

    # Phase 2 of Path B (May 2026) — list AVAILABLE catalog SKUs the AI
    # can reference. Closes the SKU-hallucination gap for Easy + Avg
    # RUPs whose parser leaves equipment[] empty (no catalog_match
    # candidates). When Claude picks a catalog SKU, _apply_pricing
    # preserves the sku field through to BOM output.
    available_catalog_block = _build_available_catalog_block(profile, claimed_lines or [])

    # Hybrid fallback section — included when raw_rup_context is present
    # (i.e. the design_data came from the .rup parser in procalcs-bom/
    # backend/utils/rup_parser.py, which leaves duct_runs/fittings/registers
    # empty and dumps the narrative text here). The AI is instructed to
    # read this text to estimate quantities that couldn't be extracted
    # structurally. Harmless when empty — the section is skipped entirely.
    if raw_ctx:
        fallback_block = (
            "\n\nRUP FILE CONTEXT (structured extraction was partial — "
            "read this to infer duct linear footage by size, fitting "
            "quantities by type, and register counts per room when the "
            "structured arrays above are empty or sparse):\n"
            "---\n"
            f"{raw_ctx}\n"
            "---\n"
        )
    else:
        fallback_block = ""

    rooms_block = ""
    if rooms:
        room_lines = "\n".join(
            f"  - {r.get('name', '?')} (assigned to {r.get('ahu', '?')})"
            for r in rooms[:60]
        )
        rooms_block = f"\n\nRooms ({len(rooms)} total):\n{room_lines}"

    prompt = """You are an expert HVAC materials estimator for ProCalcs LLC.
Analyze this completed HVAC design and return a precise materials list.

DESIGN DATA:
Building Type: {bldg_type}
Duct Location: {duct_loc}

Duct Runs: {duct_runs}

Fittings: {fittings}

Equipment: {equipment}

Registers/Grilles: {registers}{rooms_block}{fallback_block}{available_catalog_block}{catalog_context_block}

CLIENT PREFERENCES:
Preferred mastic brand: {mastic_brand}
Preferred tape brand: {tape_brand}
Preferred flex duct brand: {flex_brand}

YOUR TASK:
Return ONLY a JSON object with material quantities. Do NOT calculate prices.
Do NOT include any explanation, preamble, or markdown. Return raw JSON only.

Estimate quantities for ALL of the following — drawn items AND field consumables:

{{
  "drawn_items": [
    {{"category": "duct", "description": "...", "quantity": 0.0, "unit": "LF", "sku": "<optional catalog sku>"}},
    {{"category": "fitting", "description": "...", "quantity": 0.0, "unit": "EA", "sku": "<optional catalog sku>"}},
    {{"category": "equipment", "description": "...", "quantity": 0.0, "unit": "EA", "sku": "<optional catalog sku>"}},
    {{"category": "register", "description": "...", "quantity": 0.0, "unit": "EA", "sku": "<optional catalog sku>"}}
  ],
  "consumables": [
    {{"category": "consumable", "description": "Duct mastic ({mastic_brand})", "quantity": 0.0, "unit": "GAL"}},
    {{"category": "consumable", "description": "Foil tape ({tape_brand})", "quantity": 0.0, "unit": "ROLL"}},
    {{"category": "consumable", "description": "Hanger straps", "quantity": 0.0, "unit": "EA"}},
    {{"category": "consumable", "description": "Sheet metal screws", "quantity": 0.0, "unit": "BOX"}},
    {{"category": "consumable", "description": "Mastic brushes", "quantity": 0.0, "unit": "EA"}}
  ],
  "estimator_notes": "Any important notes about this job"
}}

Use industry-standard installation rates for consumables.
For mastic: approximately 1 gallon per 150 sq ft of duct surface area.
For foil tape: approximately 1 roll per 75 LF of duct.
For hanger straps: approximately 1 per 4-5 LF of horizontal duct run.
""".format(
        bldg_type=building.get('type', 'single_level'),
        duct_loc=building.get('duct_location', 'attic'),
        duct_runs=json.dumps(duct_runs, indent=2),
        fittings=json.dumps(fittings, indent=2),
        equipment=json.dumps(equipment, indent=2),
        registers=json.dumps(registers, indent=2),
        rooms_block=rooms_block,
        fallback_block=fallback_block,
        available_catalog_block=available_catalog_block,
        catalog_context_block=catalog_context_block,
        mastic_brand=profile.brands.mastic_brand or 'standard',
        tape_brand=profile.brands.tape_brand or 'standard',
        flex_brand=profile.brands.flex_duct_brand or 'standard',
    )
    return prompt


def _call_ai_for_quantities(
    design_data: dict,
    profile: ClientProfile,
    *,
    claimed_lines: list | None = None,
) -> dict:
    """
    Send design data to Claude and get raw material quantities back.
    Returns parsed JSON dict. Raises RuntimeError on failure.

    Phase 7 (May 2026): claimed_lines is the list of catalog_match +
    rules_engine lines already emitted. Threaded into _build_ai_prompt
    as an "ALREADY COVERED" block so Claude doesn't duplicate them.
    Optional kwarg — pre-Phase-7 callers (tests, legacy) still work.
    """
    try:
        api_key = current_app.config.get('ANTHROPIC_API_KEY', '')
        model   = current_app.config.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')
        max_tokens = current_app.config.get('ANTHROPIC_MAX_TOKENS', 4096)

        client = anthropic.Anthropic(api_key=api_key)
        prompt = _build_ai_prompt(design_data, profile, claimed_lines=claimed_lines)

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )

        raw_text = response.content[0].text.strip() if response.content else ''
        if not raw_text:
            raise RuntimeError("AI returned an empty response.")

        # Strip markdown fences if AI added them despite instructions
        if raw_text.startswith('```'):
            raw_text = raw_text.split('\n', 1)[-1]
            raw_text = raw_text.rsplit('```', 1)[0].strip()

        quantities = json.loads(raw_text)
        logger.info("AI returned %s drawn items and %s consumables",
                    len(quantities.get('drawn_items', [])),
                    len(quantities.get('consumables', [])))
        return quantities

    except json.JSONDecodeError as e:
        logger.error("AI returned non-JSON response: %s", e)
        raise RuntimeError("AI response could not be parsed. Please try again.")
    except Exception as e:
        logger.error("AI call failed: %s", e)
        raise RuntimeError("BOM generation failed: %s" % str(e))


# ===============================
# Pricing — Python does all math
# ===============================

def _get_unit_cost(description: str, category: str, profile: ClientProfile) -> float:
    """
    Look up the unit cost for an item from the client profile.
    Falls back to 0.0 if not configured — never crashes.
    """
    desc_lower = description.lower()
    s = profile.supplier  # shorthand

    cost_map = {
        'mastic':    s.mastic_cost_per_gallon,
        'foil tape': s.tape_cost_per_roll,
        'tape':      s.tape_cost_per_roll,
        'strap':     s.strapping_cost_per_roll,
        'screw':     s.screws_cost_per_box,
        'brush':     s.brush_cost_each,
        'flex':      s.flex_duct_cost_per_foot,
    }
    for keyword, cost in cost_map.items():
        if keyword in desc_lower:
            return float(cost or 0.0)

    # Rectangular duct by sq ft
    if category == 'duct' and 'rect' in desc_lower:
        return float(s.rect_duct_cost_per_sqft or 0.0)

    return 0.0  # Safe fallback — not all items have profile costs


def _get_markup_pct(category: str, profile: ClientProfile) -> float:
    """Return the markup percentage for a given category."""
    markup_map = {
        'equipment':  profile.markup.equipment_pct,
        'duct':       profile.markup.materials_pct,
        'fitting':    profile.markup.materials_pct,
        'register':   profile.markup.materials_pct,
        'consumable': profile.markup.consumables_pct,
    }
    return float(markup_map.get(category, 0.0))


def _format_catalog_matches_for_bom(matched_lines: list, profile: ClientProfile) -> list:
    """Apply contractor pricing/markup to per-equipment catalog matches.

    Mirrors _format_rule_lines_for_bom (same shape downstream) but
    preserves the catalog_match `source` and per-line `confidence`
    flags so the SPA can render confidence badges next to SKUs whose
    capacity match was banded rather than exact.

    Phase 3.7, May 2026.
    """
    out = []
    for ml in matched_lines:
        category    = ml.get("category", "equipment")
        description = ml.get("description", "")
        quantity    = float(ml.get("quantity") or 0.0)
        unit        = ml.get("unit", "EA")
        unit_cost   = float(ml.get("unit_cost") or 0.0)
        markup_pct  = _get_markup_pct(category, profile)

        raw_unit_price = unit_cost * (1 + markup_pct / 100)
        total_cost  = round(quantity * unit_cost, 2)
        unit_price  = round(raw_unit_price, 2)
        total_price = round(quantity * raw_unit_price, 2)

        # Apply client part name override if one matches the catalog
        # description. Lets contractors rename a Goodman AHU into their
        # internal nomenclature without touching the catalog.
        display_name = description
        for override in profile.part_name_overrides:
            if override.standard_name and override.standard_name.lower() in description.lower():
                display_name = override.client_name or description
                break

        out.append({
            "category":     category,
            "description":  display_name,
            "quantity":     quantity,
            "unit":         unit,
            "unit_cost":    unit_cost,
            "unit_price":   unit_price,
            "total_cost":   total_cost,
            "total_price":  total_price,
            "markup_pct":   markup_pct,
            # Provenance — preserved through _format_bom so the SPA can
            # render badges + confidence indicators per line.
            "sku":          ml.get("sku"),
            "supplier":     ml.get("supplier"),
            "section":      ml.get("section"),
            "phase":        ml.get("phase"),
            "manufacturer": ml.get("manufacturer"),
            "source":       "catalog_match",
            "confidence":   ml.get("confidence"),
        })
    return out


def _format_rule_lines_for_bom(rule_lines: list, profile: ClientProfile) -> list:
    """
    Shape rules-engine output (SKU-keyed dicts from materials_rules.
    generate_rule_lines) into the same line-item dict shape that
    ``_apply_pricing`` produces for AI quantities. Applies the profile's
    per-category markup so the rules layer respects contractor pricing
    knobs even though it sources unit costs from the SKU catalog.
    """
    out = []
    for rl in rule_lines:
        category    = rl.get("category", "consumable")
        description = rl.get("description", "")
        quantity    = float(rl.get("quantity") or 0.0)
        unit        = rl.get("unit", "EA")
        unit_cost   = float(rl.get("unit_cost") or 0.0)
        markup_pct  = _get_markup_pct(category, profile)

        raw_unit_price = unit_cost * (1 + markup_pct / 100)
        total_cost  = round(quantity * unit_cost, 2)
        unit_price  = round(raw_unit_price, 2)
        total_price = round(quantity * raw_unit_price, 2)

        # Apply client part-name override if one matches
        display_name = description
        for override in profile.part_name_overrides:
            if override.standard_name.lower() in description.lower():
                display_name = override.client_name or description
                break

        out.append({
            "category":    category,
            "description": display_name,
            "quantity":    quantity,
            "unit":        unit,
            "unit_cost":   unit_cost,
            "unit_price":  unit_price,
            "total_cost":  total_cost,
            "total_price": total_price,
            "markup_pct":  markup_pct,
            # Rules-engine provenance — preserved through _format_bom
            # via a side channel so the SPA can label these rows.
            "sku":         rl.get("sku"),
            "supplier":    rl.get("supplier"),
            "section":     rl.get("section"),
            "phase":       rl.get("phase"),
            "source":      "rules_engine",
        })
    return out


def _apply_pricing(raw_quantities: dict, profile: ClientProfile,
                   output_mode: str) -> list:
    """
    Apply client pricing and markup to AI-estimated quantities.
    Python handles ALL arithmetic — not the AI.
    Returns a flat list of priced line items.
    """
    line_items = []
    all_items = (
        raw_quantities.get('drawn_items', []) +
        raw_quantities.get('consumables', [])
    )

    for item in all_items:
        category    = item.get('category', 'other')
        description = item.get('description', '')
        quantity    = float(item.get('quantity') or 0.0)
        unit        = item.get('unit', 'EA')

        # Phase 2 of Path B (May 2026): if the AI emitted a `sku` field
        # referencing a real catalog entry, look it up and use the
        # catalog's cost + supplier + section + manufacturer. This is
        # the bridge that makes "AVAILABLE CATALOG SKUs" prompt block
        # actually pay off — Claude picks the SKU, we attach the
        # deterministic catalog metadata.
        ai_sku = (item.get('sku') or '').strip() or None
        catalog_entry = sku_catalog.get(ai_sku) if ai_sku else None

        if catalog_entry is not None:
            # Catalog wins on cost + supplier + section + manufacturer.
            # Description stays as AI emitted (more contextual than
            # the catalog row's generic name).
            unit_cost     = float(catalog_entry.default_unit_price or 0.0)
            sku_resolved  = catalog_entry.sku
            supplier      = catalog_entry.supplier
            section       = catalog_entry.section
            manufacturer  = catalog_entry.manufacturer
        else:
            # No SKU or unknown SKU — fall back to the legacy
            # description-based unit-cost lookup.
            unit_cost     = _get_unit_cost(description, category, profile)
            sku_resolved  = ai_sku  # may be a SKU we just don't know
            supplier      = None
            section       = None
            manufacturer  = None

        markup_pct  = _get_markup_pct(category, profile)
        # Compute totals from the unrounded arithmetic to avoid a
        # compounding banker's-rounding error. Example:
        #   2.0 * 18.50 * 1.25 = 46.25 exactly, but
        #   round(18.50 * 1.25, 2) = 23.12 (banker's rounding to even),
        #   and then round(2.0 * 23.12, 2) = 46.24 — one penny short.
        # Display values get rounded for presentation; the total is
        # rounded last from the full-precision product.
        raw_unit_price = unit_cost * (1 + markup_pct / 100)
        total_cost  = round(quantity * unit_cost, 2)
        unit_price  = round(raw_unit_price, 2)
        total_price = round(quantity * raw_unit_price, 2)

        # Apply client part name override if one exists
        display_name = description
        for override in profile.part_name_overrides:
            if override.standard_name.lower() in description.lower():
                display_name = override.client_name or description
                break

        line = {
            "category":    category,
            "description": display_name,
            "quantity":    quantity,
            "unit":        unit,
            "unit_cost":   unit_cost,
            "unit_price":  unit_price,
            "total_cost":  total_cost,
            "total_price": total_price,
            "markup_pct":  markup_pct,
        }
        # Provenance — only set when AI gave us a sku. _format_bom
        # picks up these fields automatically (Phase 3.7 / Phase 5).
        if sku_resolved:
            line["sku"] = sku_resolved
            line["source"] = (
                "ai_with_catalog_sku" if catalog_entry else "ai_inferred"
            )
        if supplier:
            line["supplier"] = supplier
        if section:
            line["section"] = section
        if manufacturer:
            line["manufacturer"] = manufacturer

        line_items.append(line)

    return line_items


# ===============================
# BOM Formatter
# ===============================

def _format_bom(line_items: list, profile: ClientProfile,
                job_id: str, output_mode: str) -> dict:
    """
    Assemble the final BOM response object.
    Output mode controls which cost/price columns are included.
    """
    from datetime import datetime, timezone

    show_cost  = output_mode in ('full', 'materials_only', 'labor_materials', 'cost_estimate')
    show_price = output_mode in ('full', 'materials_only', 'labor_materials', 'client_proposal')

    # Strip cost or price columns based on output mode
    formatted_items = []
    for item in line_items:
        entry = {
            "category":    item['category'],
            "description": item['description'],
            "quantity":    item['quantity'],
            "unit":        item['unit'],
        }
        if show_cost:
            entry['unit_cost']   = item['unit_cost']
            entry['total_cost']  = item['total_cost']
        if show_price:
            entry['unit_price']  = item['unit_price']
            entry['total_price'] = item['total_price']

        # Section is the contractor-facing grouping (Equipment / Duct
        # System Equipment / Rheia Duct System Equipment / Labor) that
        # the SPA + PDF render as collapsible sections. Always populated:
        # catalog/rules lines carry it from the SKU Catalog, AI lines
        # get it from the category fallback map (Phase 5, May 2026).
        entry['section'] = _section_for_line(item)

        # Preserve other provenance fields for SPA labeling, when set.
        # Phase 3.7 added 'manufacturer' and 'confidence' for catalog-
        # match lines (catalog_exact / catalog_band / catalog_default).
        for key in ('sku', 'supplier', 'phase', 'source',
                    'manufacturer', 'confidence'):
            if item.get(key) is not None:
                entry[key] = item[key]

        formatted_items.append(entry)

    # Python calculates all totals
    total_cost  = round(sum(i.get('total_cost', 0.0)  for i in formatted_items), 2)
    total_price = round(sum(i.get('total_price', 0.0) for i in formatted_items), 2)

    return {
        "job_id":        job_id,
        "client_id":     profile.client_id,
        "client_name":   profile.client_name,
        "output_mode":   output_mode,
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "supplier":      profile.supplier.supplier_name,
        "line_items":    formatted_items,
        "totals": {
            "total_cost":  total_cost  if show_cost  else None,
            "total_price": total_price if show_price else None,
        },
        "item_count": len(formatted_items),
    }
