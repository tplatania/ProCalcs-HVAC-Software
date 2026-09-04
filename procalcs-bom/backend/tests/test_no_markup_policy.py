"""
test_no_markup_policy.py — Dana #2 (2026-09-02), confirmed by Gerald.

Policy: contractor-facing BOMs carry NO markup. Contractors get the
BOM to price with their own supplier pricing, so ProCalcs never marks
up on top. This is already the reality (the model default markup is 0
and the Reliable profile is all-zero), and this test LOCKS it so
markup can't be silently reintroduced into the default/contractor path.

Non-contractor profiles (e.g. procalcs-direct, beazer) may still carry
markup for their own contexts — this test only pins the default and a
zero-markup profile.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.client_profile import ClientProfile, MarkupTiers, SupplierInfo  # noqa: E402


def test_default_markup_is_zero():
    """The product default is no markup (Dana #2)."""
    m = MarkupTiers()
    assert m.equipment_pct == 0.0
    assert m.materials_pct == 0.0
    assert m.consumables_pct == 0.0
    assert m.labor_pct == 0.0


def test_get_markup_pct_returns_zero_for_zero_markup_profile():
    from services.bom_service import _get_markup_pct
    profile = ClientProfile(
        client_id="reliable-heating-and-cooling",
        client_name="Reliable Heating and Cooling",
        supplier=SupplierInfo(supplier_name="QST"),
        markup=MarkupTiers(),  # defaults — all zero
    )
    for category in ("equipment", "duct", "fitting", "register", "consumable"):
        assert _get_markup_pct(category, profile) == 0.0, category


def test_zero_markup_means_price_equals_cost():
    """With no markup, a priced line's unit_price must equal its cost —
    the contractor sees true cost, not a marked-up number."""
    from services.bom_service import _get_markup_pct

    class _P:
        markup = MarkupTiers()

    cost = 12.50
    markup_pct = _get_markup_pct("duct", _P())
    price = round(cost * (1 + markup_pct / 100.0), 2)
    assert price == cost
