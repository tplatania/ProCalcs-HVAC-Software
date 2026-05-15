"""
bom_comparator.py — Pair a sample (reference) BOM against a generated
BOM, return a per-line match report + roll-up metrics.

Phase 7 of the testing-harness rollout (May 2026). Built so Richard
can answer "how close did we get?" without eyeballing two spreadsheets:

    sample_lines  ─┐
                   │  compare_bom(sample, generated)
    generated_bom ─┘                  │
                                       ▼
                               ComparisonReport

Match strategy:
  1. SKU-level pairing — case-insensitive, whitespace-stripped. Catches
     the high-confidence cases (catalog hits, AI-with-catalog-sku lines).
  2. Description-level pairing for any sample lines without SKU OR
     where the SKU didn't match — falls back to a normalized substring
     check so "AHU" in the sample matches "Air handler — 24K BTU" in
     the generated BOM.

Per-line outcomes:
  - matched:      sample SKU/desc found in generated, qty within tolerance
  - qty_mismatch: same SKU, generated qty differs from sample qty
  - missing:      sample line never found in generated (a gap)
  - extra:        generated line never found in sample (over-production
                  or AI hallucination — both worth flagging)

Metrics:
  - sku_match_rate:         matched / sample_count (the headline number)
  - sku_match_with_qty_rate: matched(within_qty_tol) / sample_count
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ─── Data classes ─────────────────────────────────────────────────────

@dataclass
class LineMatch:
    sample:      Optional[dict[str, Any]]
    generated:   Optional[dict[str, Any]]
    status:      str  # matched | qty_mismatch | missing | extra
    sku:         Optional[str]
    description: Optional[str]
    sample_qty:  Optional[float]
    generated_qty: Optional[float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status":        self.status,
            "sku":           self.sku,
            "description":   self.description,
            "sample_qty":    self.sample_qty,
            "generated_qty": self.generated_qty,
            "sample":        self.sample,
            "generated":     self.generated,
        }


@dataclass
class ComparisonMetrics:
    sample_count:    int = 0
    generated_count: int = 0
    matched:         int = 0
    qty_mismatch:    int = 0
    missing:         int = 0
    extra:           int = 0

    @property
    def sku_match_rate(self) -> float:
        if self.sample_count == 0:
            return 0.0
        return round((self.matched + self.qty_mismatch) / self.sample_count, 4)

    @property
    def sku_match_with_qty_rate(self) -> float:
        if self.sample_count == 0:
            return 0.0
        return round(self.matched / self.sample_count, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_count":            self.sample_count,
            "generated_count":         self.generated_count,
            "matched":                 self.matched,
            "qty_mismatch":            self.qty_mismatch,
            "missing":                 self.missing,
            "extra":                   self.extra,
            "sku_match_rate":          self.sku_match_rate,
            "sku_match_with_qty_rate": self.sku_match_with_qty_rate,
        }


@dataclass
class ComparisonReport:
    metrics: ComparisonMetrics = field(default_factory=ComparisonMetrics)
    lines:   list[LineMatch]   = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics.to_dict(),
            "lines":   [l.to_dict() for l in self.lines],
        }


# ─── Comparator ───────────────────────────────────────────────────────

# Quantity tolerance — sample BOMs are hand-edited, so 5% drift is fine.
# A "5 hangers vs 6 hangers" diff is not a regression; "1 AHU vs 4 AHU"
# is. Configurable via param.
_DEFAULT_QTY_TOL_PCT = 0.05


def compare_bom(
    sample_lines: list[dict[str, Any]],
    generated_bom: dict[str, Any] | None,
    *,
    qty_tolerance_pct: float = _DEFAULT_QTY_TOL_PCT,
) -> ComparisonReport:
    """Pair sample_lines with generated_bom['line_items'] and return a
    full report. Both inputs are tolerant — empty / None just means
    everything on the other side becomes missing/extra."""
    gen_items: list[dict[str, Any]] = list((generated_bom or {}).get("line_items") or [])
    sample_lines = list(sample_lines or [])

    # Normalize both sides — coalesce duplicates by SKU so multiple
    # "Hanger straps" rows don't double-count against the same sample row.
    sample_by_sku, sample_by_desc, sample_no_sku = _index_lines(sample_lines)
    gen_by_sku,    gen_by_desc,    gen_no_sku    = _index_lines(gen_items)

    report = ComparisonReport()
    report.metrics.sample_count    = len(sample_lines)
    report.metrics.generated_count = len(gen_items)

    matched_gen_skus:  set[str] = set()
    matched_gen_descs: set[str] = set()

    # ─── Pass 1: SKU-level pairing
    for sku_norm, s_agg in sample_by_sku.items():
        g_agg = gen_by_sku.get(sku_norm)
        if g_agg is None:
            continue
        matched_gen_skus.add(sku_norm)
        status = _qty_status(s_agg["qty"], g_agg["qty"], qty_tolerance_pct)
        report.lines.append(LineMatch(
            sample      = s_agg["original"],
            generated   = g_agg["original"],
            status      = status,
            sku         = s_agg["original"].get("sku"),
            description = s_agg["original"].get("description"),
            sample_qty    = s_agg["qty"],
            generated_qty = g_agg["qty"],
        ))
        if status == "matched":
            report.metrics.matched += 1
        else:
            report.metrics.qty_mismatch += 1

    # ─── Pass 2: description-level pairing for the remainder
    # Build the pool of generated lines that are still unmatched
    # (i.e. whose SKU wasn't claimed in pass 1, plus all SKU-less lines).
    unmatched_gen_keys = [
        (sku_norm, agg) for sku_norm, agg in gen_by_sku.items()
        if sku_norm not in matched_gen_skus
    ] + [(None, agg) for agg in gen_no_sku]

    # Iterate sample lines that didn't match by SKU, plus all SKU-less
    # sample lines.
    leftover_sample = [
        s_agg for sku_norm, s_agg in sample_by_sku.items()
        if sku_norm not in gen_by_sku
    ] + sample_no_sku

    for s_agg in leftover_sample:
        s_desc = (s_agg["original"].get("description") or "").lower().strip()
        if not s_desc:
            report.lines.append(_missing_line(s_agg))
            report.metrics.missing += 1
            continue

        match_idx = None
        for i, (sku_norm, g_agg) in enumerate(unmatched_gen_keys):
            g_desc = (g_agg["original"].get("description") or "").lower().strip()
            if not g_desc:
                continue
            if _desc_matches(s_desc, g_desc):
                match_idx = i
                break

        if match_idx is None:
            report.lines.append(_missing_line(s_agg))
            report.metrics.missing += 1
            continue

        sku_norm, g_agg = unmatched_gen_keys.pop(match_idx)
        if sku_norm:
            matched_gen_skus.add(sku_norm)
        else:
            matched_gen_descs.add(
                (g_agg["original"].get("description") or "").lower().strip()
            )

        status = _qty_status(s_agg["qty"], g_agg["qty"], qty_tolerance_pct)
        report.lines.append(LineMatch(
            sample      = s_agg["original"],
            generated   = g_agg["original"],
            status      = status,
            sku         = s_agg["original"].get("sku") or g_agg["original"].get("sku"),
            description = s_agg["original"].get("description"),
            sample_qty    = s_agg["qty"],
            generated_qty = g_agg["qty"],
        ))
        if status == "matched":
            report.metrics.matched += 1
        else:
            report.metrics.qty_mismatch += 1

    # ─── Pass 3: extras — generated lines never paired
    for sku_norm, g_agg in gen_by_sku.items():
        if sku_norm in matched_gen_skus:
            continue
        report.lines.append(_extra_line(g_agg))
        report.metrics.extra += 1
    for g_agg in gen_no_sku:
        g_desc = (g_agg["original"].get("description") or "").lower().strip()
        if g_desc in matched_gen_descs:
            continue
        report.lines.append(_extra_line(g_agg))
        report.metrics.extra += 1

    return report


# ─── Helpers ──────────────────────────────────────────────────────────

def _index_lines(
    lines: list[dict[str, Any]],
) -> tuple[dict[str, dict], dict[str, dict], list[dict]]:
    """Bucket lines by normalized SKU. Returns (by_sku, by_desc, no_sku).
    Aggregated dicts carry the summed qty + the first original row
    (used for human-display fields)."""
    by_sku: dict[str, dict[str, Any]] = {}
    by_desc: dict[str, dict[str, Any]] = {}
    no_sku: list[dict[str, Any]] = []

    for li in lines:
        sku = (li.get("sku") or "").strip()
        qty = float(li.get("quantity") or 0)
        if sku:
            key = sku.upper()
            agg = by_sku.get(key)
            if agg:
                agg["qty"] += qty
            else:
                by_sku[key] = {"qty": qty, "original": li}
        else:
            no_sku.append({"qty": qty, "original": li})
            d = (li.get("description") or "").strip().lower()
            if d:
                by_desc.setdefault(d, {"qty": qty, "original": li})

    return by_sku, by_desc, no_sku


def _qty_status(sample_qty: float, gen_qty: float, tol_pct: float) -> str:
    if sample_qty == 0 and gen_qty == 0:
        return "matched"
    base = max(abs(sample_qty), abs(gen_qty), 1.0)
    diff = abs(sample_qty - gen_qty)
    if diff / base <= tol_pct:
        return "matched"
    return "qty_mismatch"


def _desc_matches(a: str, b: str) -> bool:
    """True when description a substring-matches b (or vice versa).
    Both pre-lowered + stripped. Catches "AHU" ↔ "Air handler — 24K BTU"
    and "hanger straps" ↔ "Hanger straps". Skips empties."""
    if not a or not b:
        return False
    return a in b or b in a


def _missing_line(s_agg: dict[str, Any]) -> LineMatch:
    s = s_agg["original"]
    return LineMatch(
        sample        = s,
        generated     = None,
        status        = "missing",
        sku           = s.get("sku"),
        description   = s.get("description"),
        sample_qty    = s_agg["qty"],
        generated_qty = None,
    )


def _extra_line(g_agg: dict[str, Any]) -> LineMatch:
    g = g_agg["original"]
    return LineMatch(
        sample        = None,
        generated     = g,
        status        = "extra",
        sku           = g.get("sku"),
        description   = g.get("description"),
        sample_qty    = None,
        generated_qty = g_agg["qty"],
    )
