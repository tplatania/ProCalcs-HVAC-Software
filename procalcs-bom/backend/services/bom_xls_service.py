"""
bom_xls_service.py — render a BOM dict to an .xlsx workbook.

Takes the same BOM dict shape that /api/v1/bom/generate and
/api/v1/bom/from-wrightsoft return and emits an Excel workbook with:

  - One header block (job_id, profile, generated_at, totals)
  - Line items grouped by section (Equipment / Duct System Equipment /
    Rheia Duct System Equipment / Labor / Other) with a subtotal row
    at the bottom of each section
  - A grand-total row at the bottom

This is the supplier-handoff format Richard's team uses — they paste
SKU + qty columns into supplier ordering portals. Designed to match
the section grouping the SPA renders so the on-screen view and the
downloaded sheet line up cell-for-cell.

No AI, no pricing math — pure presentation. Called by
POST /api/v1/bom/render-xls.
"""

from __future__ import annotations

import io
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


# Section ordering — matches services.wrightsoft_catalog ordering and
# the SPA's group order so the spreadsheet, the web view, and the PDF
# all read top-to-bottom in the same sequence.
_SECTION_ORDER = [
    "Equipment",
    "Duct System Equipment",
    "Rheia Duct System Equipment",
    "Labor",
    "Other",
]

_HEADER_FILL    = PatternFill("solid", fgColor="1F2937")  # slate-800
_SECTION_FILL   = PatternFill("solid", fgColor="E5E7EB")  # gray-200
_SUBTOTAL_FILL  = PatternFill("solid", fgColor="F3F4F6")  # gray-100
_GRAND_FILL     = PatternFill("solid", fgColor="DBEAFE")  # blue-100
_UNMAPPED_FILL  = PatternFill("solid", fgColor="FEF3C7")  # amber-100

_WHITE_BOLD     = Font(color="FFFFFF", bold=True)
_BOLD           = Font(bold=True)

_THIN = Side(style="thin", color="D1D5DB")
_CELL_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_COLUMNS = [
    ("#",            6),
    ("Generic",      14),
    ("Description",  48),
    ("Mfr",          8),
    ("SKU",          22),
    ("Qty",          10),
    ("Unit",         8),
    ("Unit $",       12),
    ("Total $",      14),
    ("Source",       22),
]


def render_bom_xlsx(bom: Dict[str, Any]) -> bytes:
    """Render a BOM dict to an .xlsx file. Returns the file bytes."""
    if not isinstance(bom, dict):
        raise ValueError("render_bom_xlsx expects a BOM dict")

    line_items: List[Dict[str, Any]] = list(bom.get("line_items") or [])
    totals = bom.get("totals") or {}

    wb = Workbook()
    ws = wb.active
    ws.title = "BOM"

    # ── Title block ────────────────────────────────────────────────
    # Day-15 — contractor branding. When a contractor display name is
    # supplied via bom["branding"], it leads the header; otherwise the
    # ProCalcs default. Logo embedding is left for a follow-up because
    # openpyxl image insert needs binary download outside this hot path.
    branding = bom.get("branding") or {}
    display_name = branding.get("display_name") or "ProCalcs"
    ws["A1"] = f"{display_name} HVAC — Bill of Materials"
    ws["A1"].font = Font(size=14, bold=True)
    ws.merge_cells("A1:J1")

    meta_rows = [
        ("Job ID",        bom.get("job_id") or "—"),
        ("Profile",       bom.get("profile_name") or bom.get("client_id") or "—"),
        ("Source",        bom.get("source_pipeline") or "—"),
        ("Generated",     _format_ts(bom.get("generated_at"))
                          or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
        ("Items",         str(bom.get("item_count") or len(line_items))),
    ]
    for i, (label, value) in enumerate(meta_rows, start=2):
        ws.cell(row=i, column=1, value=label).font = _BOLD
        ws.cell(row=i, column=2, value=str(value))

    # ── Column widths ──────────────────────────────────────────────
    for i, (_, width) in enumerate(_COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    # ── Header row ─────────────────────────────────────────────────
    header_row = 2 + len(meta_rows) + 1
    for i, (label, _) in enumerate(_COLUMNS, start=1):
        cell = ws.cell(row=header_row, column=i, value=label)
        cell.fill = _HEADER_FILL
        cell.font = _WHITE_BOLD
        cell.alignment = Alignment(horizontal="left", vertical="center")
        cell.border = _CELL_BORDER

    # ── Grouped line items ─────────────────────────────────────────
    groups: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict(
        (s, []) for s in _SECTION_ORDER
    )
    for li in line_items:
        sec = str(li.get("section") or "Other")
        groups.setdefault(sec, []).append(li)

    row = header_row + 1
    running_index = 0
    grand_total = 0.0

    for section, items in groups.items():
        if not items:
            continue

        # Section divider row
        sec_cell = ws.cell(row=row, column=1, value=section)
        sec_cell.font = _BOLD
        sec_cell.fill = _SECTION_FILL
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=len(_COLUMNS))
        for col in range(1, len(_COLUMNS) + 1):
            ws.cell(row=row, column=col).fill = _SECTION_FILL
        row += 1

        section_total = 0.0
        for li in items:
            running_index += 1
            line_total = float(li.get("total_price") or li.get("total_cost") or 0.0)
            section_total += line_total

            unmapped = li.get("source") == "wrightsoft_unmapped"
            values = [
                running_index,
                li.get("generic_id") or "",
                li.get("description") or "",
                li.get("manufacturer") or "",
                li.get("sku") or "",
                _num(li.get("quantity")),
                li.get("unit") or "",
                _num(li.get("unit_cost")),
                line_total,
                li.get("source") or "",
            ]
            for col_idx, value in enumerate(values, start=1):
                c = ws.cell(row=row, column=col_idx, value=value)
                c.border = _CELL_BORDER
                if col_idx in (6, 8, 9):
                    c.alignment = Alignment(horizontal="right")
                    if col_idx in (8, 9):
                        c.number_format = '"$"#,##0.00'
                if unmapped:
                    c.fill = _UNMAPPED_FILL
            row += 1

        # Subtotal row for this section
        sub_label = ws.cell(row=row, column=1, value=f"Subtotal — {section}")
        sub_label.font = _BOLD
        sub_label.fill = _SUBTOTAL_FILL
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
        sub_val = ws.cell(row=row, column=9, value=section_total)
        sub_val.font = _BOLD
        sub_val.fill = _SUBTOTAL_FILL
        sub_val.alignment = Alignment(horizontal="right")
        sub_val.number_format = '"$"#,##0.00'
        sub_val.border = _CELL_BORDER
        # Fill the trailing cells too so the row looks complete
        for col in range(1, len(_COLUMNS) + 1):
            ws.cell(row=row, column=col).fill = _SUBTOTAL_FILL
        ws.cell(row=row, column=10).border = _CELL_BORDER
        row += 1
        # Spacer row between sections
        row += 1

        grand_total += section_total

    # ── Grand total ────────────────────────────────────────────────
    declared_total = totals.get("total_price")
    if declared_total is None:
        declared_total = totals.get("total_cost")
    final_total = float(declared_total) if declared_total is not None else grand_total

    g_label = ws.cell(row=row, column=1, value="GRAND TOTAL")
    g_label.font = Font(bold=True, size=12)
    g_label.fill = _GRAND_FILL
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
    g_val = ws.cell(row=row, column=9, value=final_total)
    g_val.font = Font(bold=True, size=12)
    g_val.fill = _GRAND_FILL
    g_val.alignment = Alignment(horizontal="right")
    g_val.number_format = '"$"#,##0.00'
    g_val.border = _CELL_BORDER
    for col in range(1, len(_COLUMNS) + 1):
        ws.cell(row=row, column=col).fill = _GRAND_FILL

    # Freeze header row so the column titles stick when scrolling
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    # ── Quick Order Summary (Day-17) ─────────────────────────────
    qo_rows = bom.get("quick_order_summary") or []
    if qo_rows:
        ws3 = wb.create_sheet(title="Quick Order")
        ws3.cell(row=1, column=1, value="QUICK ORDER SUMMARY").font = Font(size=14, bold=True)
        ws3.merge_cells("A1:E1")
        ws3.cell(row=2, column=1,
                 value="Buy at these quantities — detailed runs on the BOM sheet."
                 ).font = Font(italic=True, color="64748B")
        ws3.merge_cells("A2:E2")
        headers = ["Category", "Size", "Item", "Total", "Order As"]
        for col_idx, label in enumerate(headers, start=1):
            cell = ws3.cell(row=4, column=col_idx, value=label)
            cell.fill = _HEADER_FILL
            cell.font = _WHITE_BOLD
        prev_cat = ""
        for idx, r in enumerate(qo_rows, start=5):
            cat = r.get("category", "")
            cat_display = cat if cat != prev_cat else ""
            prev_cat = cat
            ws3.cell(row=idx, column=1, value=cat_display).font = Font(bold=(cat_display != ""))
            ws3.cell(row=idx, column=2, value=r.get("size") or "")
            ws3.cell(row=idx, column=3, value=r.get("label", ""))
            total = r.get("total") or 0
            unit  = r.get("unit", "ea")
            ws3.cell(row=idx, column=4, value=f"{total:.2f} {unit}").alignment = Alignment(horizontal="right")
            containers = r.get("containers") or 0
            container  = r.get("container", "ea")
            per_container = r.get("per_container") or 0
            # Day-17 — shared pluralization rule: ea → never pluralizes;
            # box → "boxes"; everything else → +s. Applied uniformly
            # whether per_container > 1 or == 1 so consumable rows
            # (gallons / rolls / boxes) and duct rows (boxes / sticks)
            # both render correctly.
            if containers == 1:
                suffix = ""
            elif container == "ea":
                suffix = ""
            elif container == "box":
                suffix = "es"
            else:
                suffix = "s"
            if per_container > 1:
                order_label = f"{containers} {container}{suffix} ({int(per_container)} {unit} each)"
            else:
                order_label = f"{containers} {container}{suffix}"
            ws3.cell(row=idx, column=5, value=order_label).font = Font(bold=True)
        widths = {1: 22, 2: 10, 3: 50, 4: 14, 5: 28}
        for i, w in widths.items():
            ws3.column_dimensions[get_column_letter(i)].width = w
        ws3.freeze_panes = ws3.cell(row=5, column=1)

    # ── Duct Cuts (per piece) — Day-17 / Richard Jun 30 ───────────
    cuts_groups = bom.get("duct_cuts_summary") or []
    if cuts_groups:
        ws4 = wb.create_sheet(title="Duct Cuts")
        ws4.cell(row=1, column=1, value="DUCT CUTS (PER PIECE)").font = Font(size=14, bold=True)
        ws4.merge_cells("A1:E1")
        ws4.cell(row=2, column=1,
                 value="Each end of every run is a sealed joint — fastener + mastic + tape."
                 ).font = Font(italic=True, color="64748B")
        ws4.merge_cells("A2:E2")
        for col_idx, label in enumerate(["Family", "Size", "Cut", "Length (ft)", "Joints"], start=1):
            cell = ws4.cell(row=4, column=col_idx, value=label)
            cell.fill = _HEADER_FILL
            cell.font = _WHITE_BOLD
        row = 5
        for g in cuts_groups:
            ws4.cell(row=row, column=1, value=g.get("family", "")).font = _BOLD
            ws4.cell(row=row, column=2, value=g.get("size", "")).font = _BOLD
            ws4.cell(row=row, column=3, value=f"{g.get('cut_count', 0)} cuts").font = _BOLD
            ws4.cell(row=row, column=4, value=float(g.get("total_length") or 0)).font = _BOLD
            ws4.cell(row=row, column=5, value=int(g.get("total_joints") or 0)).font = _BOLD
            row += 1
            for i, c in enumerate(g.get("cuts", []), start=1):
                ws4.cell(row=row, column=3, value=f"#{i}")
                ws4.cell(row=row, column=4, value=float(c.get("length") or 0))
                ws4.cell(row=row, column=5, value=int(c.get("joints") or 0))
                row += 1
        widths4 = {1: 28, 2: 10, 3: 14, 4: 14, 5: 12}
        for i, w in widths4.items():
            ws4.column_dimensions[get_column_letter(i)].width = w
        ws4.freeze_panes = ws4.cell(row=5, column=1)

    # ── Equipment Specifications (AHRI) — Day-15 ──────────────────
    # Collect any line carrying an ahri_spec and drop them into a
    # dedicated sheet so contractors can hand the spec sheet to the
    # AHJ / building inspector without re-keying anything.
    ahri_rows = []
    for li in line_items:
        spec = li.get("ahri_spec") or {}
        if spec:
            ahri_rows.append({
                "Model":         spec.get("condenser_model") or li.get("generic_id") or "",
                "Description":   spec.get("trade_name") or li.get("description") or "",
                "Manufacturer":  spec.get("manufacturer") or "",
                "Type":          spec.get("product_type") or "",
                "Capacity (BTU)": spec.get("capacity_btu"),
                "SEER":          spec.get("seer"),
                "HSPF":          spec.get("hspf"),
                "EER95":         spec.get("eer95"),
                "AFUE":          spec.get("afue"),
                "AHRI Ref":      spec.get("ari_refno") if spec.get("ari_refno") not in (None, "0") else "",
                "Coil Model":    spec.get("coil_model") or "",
                "Qty":           li.get("quantity"),
            })
    if ahri_rows:
        ws2 = wb.create_sheet(title="Equipment Specs")
        headers = list(ahri_rows[0].keys())
        for col_idx, label in enumerate(headers, start=1):
            cell = ws2.cell(row=1, column=col_idx, value=label)
            cell.fill = _HEADER_FILL
            cell.font = _WHITE_BOLD
        for row_idx, row in enumerate(ahri_rows, start=2):
            for col_idx, key in enumerate(headers, start=1):
                v = row[key]
                if key in ("Capacity (BTU)", "SEER", "HSPF", "EER95", "AFUE", "Qty"):
                    v = _num(v)
                ws2.cell(row=row_idx, column=col_idx, value=v)
        # Column widths — Model + Description are the wide ones
        widths = {1: 22, 2: 38, 3: 16, 4: 8, 5: 14, 6: 8, 7: 8, 8: 8, 9: 8, 10: 14, 11: 18, 12: 6}
        for i, w in widths.items():
            ws2.column_dimensions[get_column_letter(i)].width = w
        ws2.freeze_panes = ws2.cell(row=2, column=1)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _num(value: Any) -> Any:
    """Coerce a value to a numeric where possible so Excel treats it
    as a number rather than a string."""
    if value is None or value == "":
        return None
    try:
        f = float(value)
        # Keep ints as ints to avoid trailing .0 in the cell
        if f.is_integer():
            return int(f)
        return f
    except (TypeError, ValueError):
        return value


def _format_ts(ts: Any) -> str:
    """Format an ISO-ish timestamp string for display. Return '' if
    unparseable so the caller can fall back to 'now'."""
    if not ts:
        return ""
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M UTC")
    s = str(ts)
    # The shapes we typically see: "2025-05-26T14:33:21Z" or with offset.
    try:
        # Try a few likely shapes without bringing in dateutil.
        cleaned = s.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return s
