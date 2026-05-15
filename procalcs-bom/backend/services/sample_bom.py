"""
sample_bom.py — Parse a contractor's reference BOM (.xls / .xlsx) into
the same line-item shape the BOM comparator expects.

Phase 7 (May 2026, testing-harness rollout). Tom hands Richard a
"Sample BOM" exported from Wrightsoft when reviewing a generated run.
This module turns that workbook into a clean list of:

    [{"sku", "description", "quantity", "unit", "manufacturer", "section"}]

so services/bom_comparator can pair it against a generated_bom dict.

Tolerant of:
  - Both .xls (xlrd) and .xlsx (openpyxl) — the file format Tom uses
    today is the legacy .xls; newer designer exports may be .xlsx.
  - Section-header rows (e.g. "Equipment", "Duct System Equipment") —
    skipped, but section is propagated to following data rows so the
    comparator can group by section without re-keying.
  - Subtotal rows ("Subtotal, Equipment") — skipped.
  - Blank rows — skipped.
  - Header row in any of the first 5 rows — auto-detected by looking
    for the {Name, Qty, Description} column triple (case-insensitive).
"""
from __future__ import annotations

from typing import Any, Iterable
import logging

logger = logging.getLogger("procalcs_bom.sample_bom")


# Header tokens we look for to pin the column layout. Wrightsoft's
# default export uses these exact lowercase strings; we match
# case-insensitively to survive minor edits.
_REQUIRED_HEADERS = {"name", "qty", "description"}


def parse_sample_bom_bytes(
    file_bytes: bytes,
    *,
    filename: str = "",
) -> list[dict[str, Any]]:
    """Top-level entry point. Picks the right parser by file extension
    (or magic bytes when the extension is missing), returns a list of
    line-item dicts. Raises ValueError on unrecognized formats and
    RuntimeError on parse failures."""
    if not file_bytes:
        raise ValueError("Empty file")

    name = (filename or "").lower()
    is_xlsx = name.endswith(".xlsx") or file_bytes[:2] == b"PK"
    is_xls = name.endswith(".xls") or file_bytes[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

    if is_xlsx:
        rows = _read_xlsx_rows(file_bytes)
    elif is_xls:
        rows = _read_xls_rows(file_bytes)
    else:
        # Fall back to .xlsx attempt — sometimes Wrightsoft exports
        # without an extension. If openpyxl rejects, propagate.
        try:
            rows = _read_xlsx_rows(file_bytes)
        except Exception:  # noqa: BLE001
            try:
                rows = _read_xls_rows(file_bytes)
            except Exception as exc2:  # noqa: BLE001
                raise ValueError(
                    f"Unrecognized BOM file format (filename={filename!r})"
                ) from exc2

    return _normalize_rows(rows)


# ─── Format-specific readers ──────────────────────────────────────────

def _read_xlsx_rows(file_bytes: bytes) -> list[list[Any]]:
    from io import BytesIO
    from openpyxl import load_workbook
    wb = load_workbook(BytesIO(file_bytes), data_only=True, read_only=True)
    ws = wb.active
    rows: list[list[Any]] = []
    for r in ws.iter_rows(values_only=True):
        rows.append(list(r))
    return rows


def _read_xls_rows(file_bytes: bytes) -> list[list[Any]]:
    import xlrd
    wb = xlrd.open_workbook(file_contents=file_bytes)
    ws = wb.sheet_by_index(0)
    return [
        [ws.cell_value(r, c) for c in range(ws.ncols)]
        for r in range(ws.nrows)
    ]


# ─── Normalization ────────────────────────────────────────────────────

def _normalize_rows(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """Find the header row, map columns by name, and emit clean dicts."""
    if not rows:
        return []

    header_idx, col_map = _find_header(rows)
    if header_idx is None or col_map is None:
        # No recognizable header — return empty rather than guess.
        logger.warning("sample_bom: no recognizable header row found")
        return []

    out: list[dict[str, Any]] = []
    current_section: str | None = None

    for r in rows[header_idx + 1:]:
        if not _row_has_content(r):
            continue
        # Section header: only the description column is filled.
        desc = _cell_str(r, col_map.get("description"))
        sku  = _cell_str(r, col_map.get("name"))
        src  = _cell_str(r, col_map.get("src"))
        qty  = _cell_num(r, col_map.get("qty"))

        if not sku and not src and desc:
            d_lower = desc.lower().strip()
            if d_lower.startswith("subtotal"):
                continue  # Subtotal row — skip
            # Section header — remember for following rows
            current_section = desc.strip()
            continue

        if not sku:
            continue  # No SKU = no line we can pair on

        out.append({
            "sku":          sku.strip(),
            "description":  desc.strip(),
            "quantity":     qty,
            "unit":         _cell_str(r, col_map.get("un")) or None,
            "manufacturer": src.strip() or None,
            "section":      current_section,
            "unit_price":   _cell_num(r, col_map.get("price")),
            "total_price":  _cell_num(r, col_map.get("ext price")),
        })

    return out


def _find_header(rows: list[list[Any]]) -> tuple[int | None, dict[str, int] | None]:
    """Scan the first 6 rows for one whose lowered-cell-text covers
    REQUIRED_HEADERS. Returns (row_index, {header_name: col_index})."""
    for i, r in enumerate(rows[:6]):
        lowered = {
            (str(v).strip().lower() if v is not None else ""): idx
            for idx, v in enumerate(r)
        }
        non_empty = {k: idx for k, idx in lowered.items() if k}
        if _REQUIRED_HEADERS.issubset(non_empty.keys()):
            return i, non_empty
    return None, None


def _cell_str(row: list[Any], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    v = row[idx]
    if v is None:
        return ""
    return str(v).strip()


def _cell_num(row: list[Any], idx: int | None) -> float:
    if idx is None or idx >= len(row):
        return 0.0
    v = row[idx]
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _row_has_content(row: Iterable[Any]) -> bool:
    for v in row:
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        return True
    return False
