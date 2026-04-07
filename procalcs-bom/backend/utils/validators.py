"""
validators.py — Input validation helpers
All incoming API data is validated here before hitting services.
Follows ProCalcs Design Standards v2.0
"""

import logging

logger = logging.getLogger('procalcs_bom')


# ===============================
# Profile Validators
# ===============================

def validate_profile_payload(data: dict) -> list:
    """
    Validate a client profile create/update payload.
    Returns a list of error strings.
    Empty list means valid.
    """
    errors = []

    if not data:
        return ["Request body is missing or not valid JSON."]

    # Required fields
    client_id = data.get('client_id', '').strip()
    if not client_id:
        errors.append("client_id is required.")
    elif len(client_id) > 100:
        errors.append("client_id must be 100 characters or fewer.")

    client_name = data.get('client_name', '').strip()
    if not client_name:
        errors.append("client_name is required.")
    elif len(client_name) > 200:
        errors.append("client_name must be 200 characters or fewer.")

    return errors


def validate_markup_tiers(markup: dict) -> list:
    """Validate markup tier percentages — must be numeric and non-negative."""
    errors = []
    if not markup:
        return errors  # Markup is optional

    fields = ['equipment_pct', 'materials_pct', 'consumables_pct', 'labor_pct']
    for field in fields:
        val = markup.get(field)
        if val is not None:
            try:
                float_val = float(val)
                if float_val < 0:
                    errors.append("%s must be 0 or greater." % field)
                if float_val > 1000:
                    errors.append("%s seems unreasonably high — check the value." % field)
            except (TypeError, ValueError):
                errors.append("%s must be a number." % field)
    return errors


def validate_supplier_costs(supplier: dict) -> list:
    """Validate supplier cost fields — must be numeric and non-negative."""
    errors = []
    if not supplier:
        return errors  # Supplier costs are optional on create

    cost_fields = [
        'mastic_cost_per_gallon',
        'tape_cost_per_roll',
        'strapping_cost_per_roll',
        'screws_cost_per_box',
        'brush_cost_each',
        'flex_duct_cost_per_foot',
        'rect_duct_cost_per_sqft',
    ]
    for field in cost_fields:
        val = supplier.get(field)
        if val is not None:
            try:
                float_val = float(val)
                if float_val < 0:
                    errors.append("%s must be 0 or greater." % field)
            except (TypeError, ValueError):
                errors.append("%s must be a number." % field)
    return errors


# ===============================
# BOM Request Validators
# ===============================

def validate_bom_request(data: dict) -> list:
    """
    Validate a BOM generation request from Designer Desktop.
    Returns a list of error strings. Empty = valid.
    """
    errors = []

    if not data:
        return ["Request body is missing or not valid JSON."]

    if not data.get('client_id', '').strip():
        errors.append("client_id is required.")

    if not data.get('job_id', '').strip():
        errors.append("job_id is required.")

    design_data = data.get('design_data')
    if not design_data:
        errors.append("design_data is required.")
    elif not isinstance(design_data, dict):
        errors.append("design_data must be an object.")
    else:
        errors.extend(_validate_design_data(design_data))

    return errors


def _validate_design_data(design: dict) -> list:
    """Validate the design_data block from Designer Desktop."""
    errors = []

    # At minimum we need some design content to work with
    has_content = any([
        design.get('duct_runs'),
        design.get('equipment'),
        design.get('fittings'),
        design.get('registers'),
    ])
    if not has_content:
        errors.append(
            "design_data must contain at least one of: "
            "duct_runs, equipment, fittings, registers."
        )

    # Validate building block if present
    building = design.get('building', {})
    if building:
        valid_types = ['single_level', 'two_story', 'multi_level', 'other']
        bldg_type = building.get('type', '')
        if bldg_type and bldg_type not in valid_types:
            errors.append(
                "building.type must be one of: %s" % ', '.join(valid_types)
            )

        valid_duct_locs = ['attic', 'crawlspace', 'conditioned', 'basement', 'other']
        duct_loc = building.get('duct_location', '')
        if duct_loc and duct_loc not in valid_duct_locs:
            errors.append(
                "building.duct_location must be one of: %s" % ', '.join(valid_duct_locs)
            )

    return errors
