"""test_quick_order_grouping.py — Day-29 (Richard, Irvine Rd).

Unknown-family parts must group by their real SKU prefix, not a shared
'_misc' bucket keyed on size token — which merged a rect tee with an
end cap (both token '2018'), inflating the tee to x2 and dropping the
20x18 end cap from the Quick Order Summary."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from services.bom_quick_order import build_quick_order


def _li(sku, desc, qty=1.0, unit="EA"):
    return {"generic_id": sku, "sku": sku, "description": desc,
            "quantity": qty, "unit": unit, "section": "Duct System Equipment"}


def test_tee_and_endcap_with_same_size_token_stay_separate():
    rows = build_quick_order([
        _li("FRTE-2018-2012", "Rect tee, size 2018-2012"),
        _li("FMEC-2018", "End cap for Rectangular metal duct, 20\" x 18\""),
    ])
    other = [r for r in rows if r["category"] == "Other items"]
    assert len(other) == 2, f"expected 2 distinct groups, got {other}"
    assert all(r["total"] == 1.0 for r in other)


def test_true_same_part_rows_still_roll_up():
    rows = build_quick_order([
        _li("FMEC-0808", "End cap 8x8", qty=1.0),
        _li("FMEC-0808", "End cap 8x8", qty=2.0),
    ])
    other = [r for r in rows if r["category"] == "Other items"]
    assert len(other) == 1
    assert other[0]["total"] == 3.0


def test_irvine_endcap_totals_match_detail():
    detail = [
        _li("FMEC-1210", 'End cap for rectangular metal duct, 12"x10"'),
        _li("FMEC-0808", 'End cap for rectangular metal duct, 8"x8"'),
        _li("FMEC-1212", 'End cap for rectangular metal duct, 12"x12"'),
        _li("FRTE-2018-2012", "Rect tee, size 2018-2012"),
        _li("FMEC-2018", 'End cap for Rectangular metal duct, 20" x 18"'),
    ]
    rows = build_quick_order(detail)
    qo_total = sum(r["total"] for r in rows if r["category"] == "Other items")
    assert qo_total == 5.0, f"summary must equal detail (5), got {qo_total}"
