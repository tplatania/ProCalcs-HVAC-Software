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
    raw_quantities = _call_ai_for_quantities(design_data, profile)

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
    return bom


# ===============================
# AI Prompt + API Call
# ===============================

def _build_ai_prompt(design_data: dict, profile: ClientProfile) -> str:
    """
    Build the prompt sent to Claude.
    Instructs AI to return ONLY quantities — no pricing, no math.
    Pricing is applied by Python after the AI responds.
    """
    building  = design_data.get('building', {})
    duct_runs = design_data.get('duct_runs', [])
    fittings  = design_data.get('fittings', [])
    equipment = design_data.get('equipment', [])
    registers = design_data.get('registers', [])
    rooms     = design_data.get('rooms', [])
    raw_ctx   = design_data.get('raw_rup_context', '')

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

Registers/Grilles: {registers}{rooms_block}{fallback_block}

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
    {{"category": "duct", "description": "...", "quantity": 0.0, "unit": "LF"}},
    {{"category": "fitting", "description": "...", "quantity": 0.0, "unit": "EA"}},
    {{"category": "equipment", "description": "...", "quantity": 0.0, "unit": "EA"}},
    {{"category": "register", "description": "...", "quantity": 0.0, "unit": "EA"}}
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
        mastic_brand=profile.brands.mastic_brand or 'standard',
        tape_brand=profile.brands.tape_brand or 'standard',
        flex_brand=profile.brands.flex_duct_brand or 'standard',
    )
    return prompt


def _call_ai_for_quantities(design_data: dict, profile: ClientProfile) -> dict:
    """
    Send design data to Claude and get raw material quantities back.
    Returns parsed JSON dict. Raises RuntimeError on failure.
    """
    try:
        api_key = current_app.config.get('ANTHROPIC_API_KEY', '')
        model   = current_app.config.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')
        max_tokens = current_app.config.get('ANTHROPIC_MAX_TOKENS', 4096)

        client = anthropic.Anthropic(api_key=api_key)
        prompt = _build_ai_prompt(design_data, profile)

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

        unit_cost   = _get_unit_cost(description, category, profile)
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

        line_items.append({
            "category":    category,
            "description": display_name,
            "quantity":    quantity,
            "unit":        unit,
            "unit_cost":   unit_cost,
            "unit_price":  unit_price,
            "total_cost":  total_cost,
            "total_price": total_price,
            "markup_pct":  markup_pct,
        })

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

        # Preserve provenance fields for SPA labeling, when set.
        # Phase 3.7 added 'manufacturer' and 'confidence' for catalog-
        # match lines (catalog_exact / catalog_band / catalog_default).
        for key in ('sku', 'supplier', 'section', 'phase', 'source',
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
