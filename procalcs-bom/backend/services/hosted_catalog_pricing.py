"""hosted_catalog_pricing.py — Path A pricing shim.

Thin wrapper over the catalog client's wrightsoft_pricing_for_part call,
gated by ClientProfile.use_wrightsoft_hosted_catalog. Kept in its own
module so:

  1. The build_bom_from_wrightsoft_lines integration point is a single
     import + one-line call rather than a scattered refactor.
  2. Rollback is trivial — flip the profile flag or disable this module
     with a top-level SHIM_DISABLED = True.
  3. Rate-limit / retry / fallback policy lives here so calling code
     doesn't need to know about catalog transport concerns.

When the flag is off (default across the fleet), get_hosted_price()
returns None immediately — no HTTP call, no cost. When on, we hit the
catalog once per (category, psrc, pn) and apply the ActCateg discount
+ margin to the raw ActItem price.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def is_hosted_catalog_enabled(profile: Any) -> bool:
    """Read the feature flag off the contractor profile. Tolerant of
    older profile dicts that pre-date the flag."""
    if profile is None:
        return False
    # Prefer attribute (ClientProfile dataclass instance)
    val = getattr(profile, "use_wrightsoft_hosted_catalog", None)
    if val is not None:
        return bool(val)
    # Fall back to dict-shaped payloads (Firestore doc, tests)
    if isinstance(profile, dict):
        return bool(profile.get("use_wrightsoft_hosted_catalog", False))
    return False


def get_hosted_price(profile: Any, *,
                    category: Optional[str], psrc: Optional[str], pn: str,
                    source_mdb: Optional[str] = None
                    ) -> Optional[dict[str, Any]]:
    """Return {unit_price, list_price, cost, rule} from the hosted
    catalog for the given part, or None when:
      - The profile's use_wrightsoft_hosted_catalog flag is False
      - The catalog has no entry for pn (with variant-strip fallback)
      - The catalog client raises (best-effort — logged, swallowed)

    Callers treat None as 'no hosted price; fall through to the existing
    pricing path' — Path A wires in additively, doesn't replace v1.

    Category / psrc are optional — when absent, we look up by pn alone,
    read the discovered (category, psrc) off the returned ActItem row,
    then fetch the matching ActCateg rule in a second hop. Wrightsoft's
    .xls emits SKUs like DDVn04MI (with the Medium Insulation variant
    suffix) whose base PN (DDVn04) is what ActItem stores — the
    variant-strip fallback handles that mismatch."""
    if not pn or not is_hosted_catalog_enabled(profile):
        return None

    try:
        from services import wrightsoft_catalog as _wsc  # noqa: WPS433
        client = _wsc._get_client()
        if client is None:
            return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("hosted_catalog_pricing: catalog client unavailable: %s",
                       exc)
        return None

    # ── Two-step discovery: find the ActItem row, then its ActCateg rule.
    def _find_part(_pn: str) -> Optional[dict[str, Any]]:
        """Return the ActItem dict when _pn exists in the catalog.
        Uses the pricing-for-part endpoint when (category, psrc) known,
        else falls back to actitem_by_pn."""
        if category and psrc:
            try:
                r = client.wrightsoft_pricing_for_part(
                    category=category, psrc=psrc, pn=_pn, source_mdb=source_mdb,
                )
                if r and r.get("part"):
                    return r  # already has {part, rule}
            except Exception as exc:  # noqa: BLE001
                logger.warning("hosted_catalog_pricing: pricing-for-part failed: %s", exc)
        # Category-agnostic path. Don't filter by psrc here — the .xls
        # Src column ("PGM" etc.) often differs from ActItem.psrc ("WSF")
        # even for the same PN. Endpoint sorts by price desc so highest-
        # priced match wins; that's the right one when Wrightsoft itself
        # would resolve the SKU.
        try:
            items = client.wrightsoft_actitem_by_pn(
                _pn, psrc=None, source_mdb=source_mdb,
            )
            if not items:
                return None
            part = items[0]  # highest-priced match wins per endpoint sort
            # Look up rule separately if we don't already have it
            rule = None
            if part.get("category") and part.get("psrc"):
                try:
                    rule = client._get_cached(
                        f"api/v1/catalog/wrightsoft/actcateg/"
                        f"{part['category']}/{part['psrc']}",
                        {}, None,
                    )
                except Exception:  # noqa: BLE001
                    rule = None
            return {"part": part, "rule": rule}
        except Exception as exc:  # noqa: BLE001
            logger.warning("hosted_catalog_pricing: actitem_by_pn failed: %s", exc)
            return None

    # 1. Try the exact PN.
    result = _find_part(pn)
    # 2. Insulation-variant fallback. Wrightsoft's .xls emits DDVn08MI
    #    (Medium Insulation) but ActItem has the base DDVn08 SKU only.
    if result is None and len(pn) >= 4 and pn[-2:].upper() in ("MI", "HI", "LI"):
        base_pn = pn[:-2]
        result = _find_part(base_pn)

    if not result or not result.get("part"):
        return None

    part = result["part"]
    rule = result.get("rule") or {}

    # Apply Wrightsoft's own math: discount reduces the list price,
    # margin scales it up on the sell side. Catalog discount is
    # percent (0-100), margin also percent. Costtax is a rate we
    # don't apply here — it's a tax rate, not a markup. Contractor
    # overrides layer already handles taxes on the priced BOM.
    raw_list = float(part.get("listprice") or 0)
    raw_cost = float(part.get("cost") or 0)
    raw_price = float(part.get("price") or 0)

    discount_pct = float(rule.get("discount") or 0) / 100.0
    margin_pct   = float(rule.get("margin") or 0) / 100.0

    # Cost = list × (1 - discount). Common Wrightsoft interpretation.
    computed_cost = raw_list * (1 - discount_pct) if raw_list else raw_cost
    # Sell price = cost × (1 + margin) or raw_price when no margin.
    computed_price = (computed_cost * (1 + margin_pct)
                      if margin_pct else raw_price or computed_cost)

    return {
        "unit_price":  round(computed_price, 4),
        "list_price":  raw_list,
        "cost":        round(computed_cost, 4),
        "raw_price":   raw_price,
        "discount":    discount_pct,
        "margin":      margin_pct,
        "source_mdb":  part.get("source_mdb"),
        "rule_applied": bool(rule),
    }
