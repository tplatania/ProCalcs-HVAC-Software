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

    # Step 2 — Call AI for material quantities
    raw_quantities = _call_ai_for_quantities(design_data, profile)

    # Step 3 — Apply pricing (Python does all math)
    priced_items = _apply_pricing(raw_quantities, profile, effective_mode)

    # Step 4 — Format final BOM
    bom = _format_bom(priced_items, profile, job_id, effective_mode)

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
    building = design_data.get('building', {})
    duct_runs = design_data.get('duct_runs', [])
    fittings  = design_data.get('fittings', [])
    equipment = design_data.get('equipment', [])
    registers = design_data.get('registers', [])

    prompt = """You are an expert HVAC materials estimator for ProCalcs LLC.
Analyze this completed HVAC design and return a precise materials list.

DESIGN DATA:
Building Type: {bldg_type}
Duct Location: {duct_loc}

Duct Runs: {duct_runs}

Fittings: {fittings}

Equipment: {equipment}

Registers/Grilles: {registers}

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
        total_cost  = round(quantity * unit_cost, 2)
        unit_price  = round(unit_cost * (1 + markup_pct / 100), 2)
        total_price = round(quantity * unit_price, 2)

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
