"""
pdf_service.py — branded BOM PDF renderer.

Takes the already-formatted BOM dict that bom_service.generate()
produces and renders it through a Jinja2 template + WeasyPrint into
PDF bytes. No AI calls here, no pricing math — this is the final
presentation step only.

Called by the /api/v1/bom/render-pdf route. The SPA POSTs a BOM dict
that was generated on a prior /generate call, so Downloading a PDF is
cheap (~200ms) and deterministic — doesn't re-invoke Claude.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

# Category metadata — color + label. Matches the SPA's category chip
# styling in procalcs-designer/src/pages/bom-output.tsx so the PDF
# and the web view look like the same product.
_CATEGORY_META: Dict[str, Dict[str, str]] = {
    "equipment":  {"label": "Equipment",   "color": "#a855f7", "bg": "#faf5ff"},
    "duct":       {"label": "Duct",        "color": "#3b82f6", "bg": "#eff6ff"},
    "fitting":    {"label": "Fittings",    "color": "#f59e0b", "bg": "#fffbeb"},
    "consumable": {"label": "Consumables", "color": "#10b981", "bg": "#ecfdf5"},
}
_CATEGORY_ORDER = ["equipment", "duct", "fitting", "consumable"]


def _normalize_category(raw: str) -> str:
    """Flask returns any string as the category; clamp to the 4 UI
    buckets so the template doesn't need defensive logic."""
    key = (raw or "").strip().lower()
    if key in _CATEGORY_META:
        return key
    # "register" items (from the AI prompt) get shown under fittings
    # in the SPA; do the same here.
    if key == "register":
        return "fitting"
    return "consumable"


def _group_lines(line_items):
    """Group line_items by normalized category, preserving order."""
    groups: Dict[str, list] = {cat: [] for cat in _CATEGORY_ORDER}
    for item in line_items or []:
        cat = _normalize_category(item.get("category", ""))
        groups[cat].append(item)
    # Drop empty categories so the template doesn't render blank sections.
    return [
        {
            "key":      cat,
            "meta":     _CATEGORY_META[cat],
            "lines":    groups.get(cat, []),
            "subtotal": sum(
                (it.get("total_price") or it.get("total_cost") or 0)
                for it in groups.get(cat, [])
            ),
        }
        for cat in _CATEGORY_ORDER
        if groups.get(cat, [])
    ]


# Lazy-built Jinja environment. Template lives next to the services
# directory at backend/templates/.
_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _format_currency(value: Any) -> str:
    """Jinja filter — format a number as $1,234.56, or '—' when
    None/missing (cost-suppressed output modes)."""
    if value is None:
        return "—"
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _format_quantity(value: Any) -> str:
    """Trim trailing .0 on whole-number quantities."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f == int(f):
        return str(int(f))
    return f"{f:.2f}".rstrip("0").rstrip(".")


_jinja_env.filters["currency"] = _format_currency
_jinja_env.filters["qty"]      = _format_quantity


def _build_pdf_context(bom: Dict[str, Any]) -> Dict[str, Any]:
    """Build the Jinja render context from a BOM dict.

    Pulled out as a pure dict-in / dict-out helper so the context-shaping
    logic — particularly the rules-engine vs AI provenance counts — can
    be unit-tested without WeasyPrint in the loop.
    """
    totals = bom.get("totals") or {}
    grand_total = totals.get("total_price")
    if grand_total is None:
        grand_total = totals.get("total_cost")

    line_items = bom.get("line_items") or []

    # Provenance counts. Prefer the backend-reported totals (added by
    # the rules-engine merge in commit ae5bd2b — see bom_service.generate
    # where rules_engine_item_count/ai_item_count get attached). Fall
    # back to deriving from line_items[].source for older payloads or
    # ad-hoc renders that don't go through the merge path. Treat any
    # non-"rules" value as AI so the reviewer-attention default matches
    # the SPA's normalizeSource (defaults-to-ai = surfaces line for review).
    rules_count = bom.get("rules_engine_item_count")
    ai_count = bom.get("ai_item_count")
    if rules_count is None:
        rules_count = sum(1 for it in line_items if it.get("source") == "rules")
    if ai_count is None:
        ai_count = sum(1 for it in line_items if it.get("source") != "rules")
    has_provenance = (rules_count or 0) > 0 or (ai_count or 0) > 0

    return {
        "job_id":         bom.get("job_id", ""),
        "client_name":    bom.get("client_name", ""),
        "client_id":      bom.get("client_id", ""),
        "supplier":       bom.get("supplier", ""),
        "output_mode":    bom.get("output_mode", "full"),
        "generated_at":   bom.get("generated_at", ""),
        "item_count":     bom.get("item_count", len(line_items)),
        "grand_total":    grand_total,
        "groups":         _group_lines(line_items),
        # Provenance — wired into the template behind has_provenance so
        # pre-rules-engine payloads render the prior layout untouched.
        "rules_count":    int(rules_count or 0),
        "ai_count":       int(ai_count or 0),
        "has_provenance": has_provenance,
    }


def render_bom_pdf(bom: Dict[str, Any]) -> bytes:
    """Render a BOM dict into PDF bytes.

    The input dict shape is whatever bom_service._format_bom() returns
    (job_id, client_name, supplier, output_mode, generated_at,
    line_items, totals, item_count, plus rules_engine_item_count and
    ai_item_count from the rules-engine merge). Missing fields get
    sensible defaults so partial test fixtures still render without
    raising.

    Returns: the PDF as bytes, ready to hand to Flask's Response.
    """
    ctx = _build_pdf_context(bom)
    template = _jinja_env.get_template("bom.html.j2")
    html_str = template.render(**ctx)

    pdf_bytes = HTML(string=html_str).write_pdf()
    # WeasyPrint 63 returns bytes already, but annotate for safety.
    return bytes(pdf_bytes or b"")
