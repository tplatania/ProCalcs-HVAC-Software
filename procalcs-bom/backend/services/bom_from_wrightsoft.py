"""
bom_from_wrightsoft.py — Build a contractor BOM from Wrightsoft's
generic-part output (Day-9 / Tom's "use the produced information" path).

This is the consumer Tom asked about in his Slack message: instead of
re-deriving a BOM from raw RUP design data + AI, we take Wrightsoft's
own generated BOM (a list of generic-part IDs + quantities) and
translate each entry through the mapping infrastructure that's been
sitting unused since Phase 3.

Input contract:
    [{"generic_id": "PEX0750", "quantity": 250.0,
      "description": "1/2-in PEX Tubing"},
     ...]
    plus a ClientProfile (for supplier preference + markup).

Output: a BOM dict matching the existing /api/v1/bom/generate response
shape so downstream consumers (PDF renderer, comparator, run-history
SPA) don't need to special-case it.

Strategy per line:
  1. Look up the generic_id in Wrightsoft's catalog
     (services.wrightsoft_catalog.lookup_skus_for_generic) honoring
     the contractor's supplier preference when one is set
  2. If a manufacturer SKU exists → emit a "wrightsoft_mapped" line
     with that SKU, the Wrightsoft category-derived section, and
     description from generic_parts.csv (more authoritative than
     whatever the caller passed)
  3. If no mapping (generic_id not in mapped_parts.csv) → emit a line
     flagged "unmapped" so reviewers can see what catalog gaps exist
     (feeds the existing SKU-Backlog page)
  4. Apply markup + estimated cost via the same _get_unit_cost /
     _get_markup_pct helpers bom_service uses — keeps pricing logic
     centralized
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from models.client_profile import ClientProfile
from services import wrightsoft_catalog as wsc

logger = logging.getLogger("procalcs_bom.bom_from_wrightsoft")


# ─── Public API ─────────────────────────────────────────────────────

def build_bom_from_wrightsoft_lines(
    *,
    lines: list[dict[str, Any]],
    profile: ClientProfile,
    job_id: str,
    output_mode: str = "full",
) -> dict[str, Any]:
    """Build a complete BOM from a Wrightsoft generic-part listing.

    Returns the same dict shape /api/v1/bom/generate emits so the BOM
    flows through the existing persistence + diff + PDF pipeline
    unchanged.

    Args:
        lines: list of {"generic_id": str, "quantity": float|str,
                        "description": str | optional}
        profile: contractor profile (supplier preference + markup)
        job_id: identifier echoed in the response + bom_runs.job_id
        output_mode: profile output mode (full / cost_estimate / etc.)

    Provenance fields per line:
        source            = "wrightsoft_mapped" | "wrightsoft_unmapped"
        sku               = manufacturer part number (or None when unmapped)
        manufacturer      = 4-char source code from Wrightsoft (QST, GOOD, etc.)
        generic_id        = the original Wrightsoft generic ID — preserved
                            so the SKU Backlog can group unmapped lines
        cost_is_estimate  = True when fell back to estimated cost
    """
    # Lazy import — pulling from services.bom_service at module load
    # creates an import cycle (bom_service imports things that import
    # this file once it's registered as a sibling).
    from services.bom_service import _get_unit_cost, _get_markup_pct

    # Make sure the catalog is warm before the loop — avoids per-line
    # cache thrash when hundreds of lines arrive.
    wsc.load_mapped_parts()
    generic_parts = wsc.load_generic_parts()

    # Contractor's preferred supplier — read from the brands block.
    # Fall back to the AC brand when no explicit supplier code is set
    # so Goodman-preferring contractors still get filtered output.
    supplier_pref = _supplier_pref_for(profile)

    line_items: list[dict[str, Any]] = []
    mapped_count = 0
    unmapped_count = 0
    dfunit_count = 0
    passthrough_count = 0
    # Day-15 — Wrightsoft fittings whose code is NOT in Tom's
    # standard template (designer used a non-canonical fitting).
    non_standard_count = 0
    # Day-15 — Equipment lines whose model number matched a row in the
    # 1.4M-row AHRI library, so we attached SEER/HSPF/AFUE/AHRI ref.
    ahri_count = 0
    # Day-12 — collected for the discovered_mappings auto-learn write.
    # Each entry is the minimum needed for upsert_many. Populated
    # only on the passthrough branch (the catalog branches are already
    # in the bundled mapping).
    discovered_seen: list[dict[str, Any]] = []
    discovered_count = 0
    # Day-13 — count of lines that hit a manual contractor override.
    # Manual edits beat auto-discovery beat raw passthrough.
    manual_count = 0

    for raw in lines:
        gen_id = (raw.get("generic_id") or "").strip()
        if not gen_id:
            continue
        try:
            quantity = float(raw.get("quantity") or 0)
        except (TypeError, ValueError):
            quantity = 0.0
        if quantity <= 0:
            # Skip zero-quantity rows. Wrightsoft sometimes outputs
            # placeholder rows; emitting them as $0 BOM lines is noise.
            continue

        # Day-11 — DFUnit equipment-spec lookup. Wrightsoft BOMs
        # sometimes reference DFUnit model numbers directly (ductless
        # / heat-pump units don't go through the parts catalog —
        # they're listed by Manufacturer + Model). If the generic_id
        # IS a DFUnit Model, we get the full unit spec for free:
        # manufacturer, capacity (BTU), dimensions, weight.
        dfunit_row = wsc.lookup_dfunit_by_model(gen_id)
        dfunit_spec = wsc.dfunit_line_spec(dfunit_row) if dfunit_row else None

        # Look up the contractor's manufacturer SKU
        sku_matches = wsc.lookup_skus_for_generic(gen_id, supplier_pref)
        catalog_row = generic_parts.get(gen_id) or {}
        # Wrightsoft's description is the source of truth (matches
        # the contractor's expectations); caller-provided description
        # is the fallback for items not in the catalog.
        description = (
            catalog_row.get("Description")
            or raw.get("description")
            or gen_id
        )
        unit = catalog_row.get("Units") or raw.get("unit") or "EA"
        # Section resolution: catalog first (most precise), then
        # Wrightsoft's section-divider hint preserved by the parser,
        # then "Other" as last resort. section_for_generic returns
        # SECTION_OTHER (a string, not None) for unknown generics —
        # so we explicitly treat that as 'no answer' and fall through
        # to the file's own section hint. This lets unmapped lines
        # from the real BOM (Goodman/Broan equipment, Rheia parts)
        # land in the right section instead of all piling into Other.
        catalog_section = wsc.section_for_generic(gen_id)
        if catalog_section and catalog_section != wsc.SECTION_OTHER:
            section = catalog_section
        else:
            section = raw.get("section_hint") or wsc.SECTION_OTHER
        category = _category_to_line_category(catalog_row.get("Category"))
        # Wrightsoft's Src column is the supplier-of-record when the
        # bundled catalog doesn't cover this part. Used by the
        # passthrough branch below.
        wsf_src = (raw.get("src") or "").strip().upper() or None

        # Day-13 — check for a contractor-level manual override BEFORE
        # any source branching. The override applies regardless of
        # whether the line ends up mapped, dfunit, discovered, or
        # passthrough: Tom's "we collect prices per contractor" workflow
        # means the price-side override has to win on every code path.
        # The SKU+supplier side of the override only takes effect on
        # the passthrough branch (where Wrightsoft didn't already give
        # us a verified catalog answer).
        override_row = None
        if wsf_src:
            try:
                from models.contractor_override import ContractorOverride
                override_row = ContractorOverride.lookup(
                    contractor_id=profile.client_id,
                    supplier=wsf_src,
                    sku=gen_id,
                )
            except Exception:
                # DB unavailable — fall through. Best-effort, never
                # poison the BOM response.
                override_row = None

        if dfunit_spec:
            # DFUnit direct match — authoritative manufacturer + model.
            # This path is used for ductless / heat-pump units that
            # Wrightsoft lists by model number rather than generic ID.
            # Equipment category is implied; section is Equipment.
            mapped_count += 1
            dfunit_count += 1
            # Description prefers a more informative composed string
            # over the raw catalog description when we have spec data.
            desc_with_spec = _compose_dfunit_description(description, dfunit_spec)
            line = _priced_line(
                generic_id=gen_id,
                description=desc_with_spec,
                quantity=quantity,
                unit=unit or "EA",
                section=wsc.SECTION_EQUIPMENT,
                category="equipment",
                profile=profile,
                sku=dfunit_spec["model"],
                manufacturer=dfunit_spec["manufacturer"],
                source="wrightsoft_dfunit",
                get_unit_cost=_get_unit_cost,
                get_markup_pct=_get_markup_pct,
                wrightsoft_price=raw.get("wrightsoft_price"),
            )
            # Attach the spec dict so PDF / SPA can display capacity,
            # dimensions, weight without re-looking up DFUnit downstream.
            line["dfunit_spec"] = dfunit_spec
        elif sku_matches:
            mapped_count += 1
            supplier_code, mfr_partnum = sku_matches[0]
            line = _priced_line(
                generic_id=gen_id,
                description=description,
                quantity=quantity,
                unit=unit,
                section=section,
                category=category,
                profile=profile,
                sku=mfr_partnum,
                manufacturer=supplier_code,
                source="wrightsoft_mapped",
                get_unit_cost=_get_unit_cost,
                get_markup_pct=_get_markup_pct,
                wrightsoft_price=raw.get("wrightsoft_price"),
            )
        elif wsf_src:
            # Wrightsoft told us who supplies this part (Src column) and
            # what the part number is (Name column). Trust it — the
            # contractor's actual procurement uses this exact SKU.
            #
            # Precedence on the passthrough branch:
            #   1. ContractorOverride — a human said this is right
            #      (Day-13). Overrides SKU / supplier / unit price.
            #   2. DiscoveredMapping — we've seen this combo before
            #      (Day-12). Verified description.
            #   3. Raw Wrightsoft passthrough — first time we've seen it.
            from models.discovered_mapping import DiscoveredMapping

            try:
                existing_row = DiscoveredMapping.lookup(supplier=wsf_src, sku=gen_id)
            except Exception:
                # DB unavailable (e.g. tests with no app context) — fall
                # through to passthrough. The upsert at the end is also
                # wrapped in a try/except so we never poison a BOM
                # response with a DB hiccup.
                existing_row = None

            if override_row is not None:
                # Highest precedence — Richard already corrected this
                # (Src, Name) for this contractor. Use the corrections.
                manual_count += 1
                emitted_source = "wrightsoft_manual"
                emitted_sku = override_row.corrected_sku or gen_id
                emitted_supplier = override_row.corrected_supplier or wsf_src
                if existing_row is not None and existing_row.description:
                    description = existing_row.description
                # Still record the upsert so discovered_mappings keeps
                # tracking that we saw this combo today (without
                # promoting the un-corrected version over the manual).
                discovered_seen.append({
                    "supplier":     wsf_src,
                    "sku":          gen_id,
                    "description":  description,
                    "section_hint": section,
                    "quantity":     quantity,
                })
            elif existing_row is not None:
                discovered_count += 1
                emitted_source = "wrightsoft_discovered"
                emitted_sku = gen_id
                emitted_supplier = wsf_src
                # Prefer the verified description we've seen before
                # over whatever this run's row carried (Wrightsoft
                # occasionally truncates descriptions on smaller exports).
                description = existing_row.description or description
                discovered_seen.append({
                    "supplier":     wsf_src,
                    "sku":          gen_id,
                    "description":  description,
                    "section_hint": section,
                    "quantity":     quantity,
                })
            else:
                passthrough_count += 1
                emitted_source = "wrightsoft_passthrough"
                emitted_sku = gen_id
                emitted_supplier = wsf_src
                discovered_seen.append({
                    "supplier":     wsf_src,
                    "sku":          gen_id,
                    "description":  description,
                    "section_hint": section,
                    "quantity":     quantity,
                })

            line = _priced_line(
                generic_id=gen_id,
                description=description,
                quantity=quantity,
                unit=unit,
                section=section,
                category=category,
                profile=profile,
                sku=emitted_sku,
                manufacturer=emitted_supplier,
                source=emitted_source,
                get_unit_cost=_get_unit_cost,
                get_markup_pct=_get_markup_pct,
                wrightsoft_price=raw.get("wrightsoft_price"),
            )
        else:
            # No catalog match AND no Src column — genuinely unmapped.
            # These are the lines worth investigating; everything else
            # had a real answer in the file itself.
            unmapped_count += 1
            line = _priced_line(
                generic_id=gen_id,
                description=description,
                quantity=quantity,
                unit=unit,
                section=section,
                category=category,
                profile=profile,
                sku=None,
                manufacturer=None,
                source="wrightsoft_unmapped",
                get_unit_cost=_get_unit_cost,
                get_markup_pct=_get_markup_pct,
                wrightsoft_price=raw.get("wrightsoft_price"),
            )

        # Day-13 — apply contractor-level overrides on every line that
        # got emitted, regardless of which branch (mapped / dfunit /
        # discovered / passthrough) picked it up. The override's
        # unit_price IS Tom's per-contractor pricing workflow — it has
        # to win on every code path, not just passthrough.
        #
        # The source-tagging promotion to 'wrightsoft_manual' is handled
        # in the passthrough branch above (where we don't already have
        # a verified catalog source). For mapped/dfunit/discovered
        # lines, the override applies silently — the trustworthy
        # provenance stays, the price is the only thing that changes.
        if override_row is not None:
            if override_row.unit_price is not None:
                new_cost = float(override_row.unit_price)
                markup_pct = float(line.get("markup_pct") or 0.0)
                line["unit_cost"]  = new_cost
                line["total_cost"] = round(new_cost * quantity, 2)
                if "unit_price" in line:
                    new_unit_price = round(new_cost * (1 + markup_pct / 100), 2)
                    line["unit_price"]  = new_unit_price
                    line["total_price"] = round(new_unit_price * quantity, 2)
                line["cost_is_estimate"] = False
            line["override_id"] = override_row.id
            line["override_updated_at"] = (
                override_row.updated_at.isoformat() + "Z"
                if override_row.updated_at else None
            )
            line["override_updated_by"] = override_row.updated_by

        # Day-15 — non-standard fitting flag.
        # Use the Wrightsoft Name column (gen_id) as the fitting-code
        # observation. Classifier returns:
        #   True  → standard (do nothing)
        #   False → flag the line so reviewers can audit
        #   None  → classifier disabled (no template loaded; skip)
        #
        # Day-16: skip lines that obviously aren't fittings — Equipment
        # section, synthetic .rup-pipeline IDs (DUCT-*, REGISTERS,
        # FITTINGS placeholders), and DFUnit-matched equipment lines.
        # The non-standard classifier is meant for the per-fitting code
        # lines (8E / 11H / etc.) that come out of the .xls export,
        # not for model numbers or duct-system rollups.
        # Day-16 hotfix: only fire on lines that look like Tom's standard
        # fitting CODES (e.g. 8E, 11H — short alphanumeric tokens from
        # the 30-row standard template), NOT Wrightsoft-canonical SKUs
        # (FBTI-0804-4, DDVn07MI, etc.). Wrightsoft .xls SKUs always
        # have a `src` column populated; raw fitting codes don't. Also
        # exclude long SKUs (>=7 chars) and SKUs containing dashes —
        # both are tell-tale signs of Wrightsoft's canonical naming.
        _is_fitting_candidate = (
            line.get("section") in (None, "", wsc.SECTION_OTHER,
                                    "Duct System Equipment",
                                    "Rheia Duct System Equipment")
            and not dfunit_spec
            and not gen_id.startswith(("DUCT-", "REGISTERS", "FITTINGS"))
            and not wsf_src        # Wrightsoft-sourced lines are SKUs, not codes
            and "-" not in gen_id  # Wrightsoft SKUs like FBTI-0804-4 use dashes
            and len(gen_id) <= 6   # template codes are short (8E, 11H, 8AF)
        )
        if _is_fitting_candidate:
            std = wsc.is_standard_fitting_code(gen_id)
            if std is False:
                line["non_standard_fitting"] = True
                non_standard_count += 1

        # Day-15 — AHRI equipment enrichment. For lines that DIDN'T
        # resolve via DFUnit (DFUnit hits already carry full spec data),
        # ask the AHRI library whether the gen_id looks like a known
        # condenser model. AHRI gives us SEER/HSPF/AFUE/capacity +
        # AHRI cert number — the data contractors care about for spec
        # sheets.
        #
        # Day-16 hotfix: gate STRICTLY on section=Equipment. The earlier
        # gen-id-shape heuristic fired on fitting SKUs (DDVn07MI,
        # FBTI-0804-4, FCLR-7) and turned an 81-line Wrightsoft BOM
        # export into a 240-AHRI-call request that hit Cloud Run's
        # request timeout. Fittings will never match the AHRI library
        # (which only catalogs AC/HP/FURNACE units) so the lookup is
        # pure cost with zero hit rate on those lines.
        if (line.get("section") == "Equipment"
                and not dfunit_spec
                and gen_id and len(gen_id) >= 6
                and any(c.isdigit() for c in gen_id)
                and any(c.isalpha() for c in gen_id)):
            ahri_row = wsc.lookup_ahri_by_model(gen_id)
            if ahri_row:
                line["ahri_spec"] = wsc.ahri_line_spec(ahri_row)
                ahri_count += 1

        line_items.append(line)

    totals = _compute_totals(line_items)
    bom = {
        "job_id":      job_id,
        "client_id":   profile.client_id,
        "client_name": profile.client_name,
        "output_mode": output_mode,
        "generated_at": _utcnow_iso(),
        "supplier":    profile.supplier.supplier_name or "",
        # Day-15 — contractor branding for PDF/XLS exports. Empty values
        # let the renderer fall back to ProCalcs defaults.
        "branding": {
            "display_name": profile.client_name or "",
            "logo_url":     getattr(profile, "logo_url", "") or "",
            "brand_color":  getattr(profile, "brand_color", "") or "",
        },
        "line_items":  line_items,
        "totals":      totals,
        "item_count":  len(line_items),
        # Provenance counts in the same vocabulary the existing BOM
        # response uses (catalog_match_item_count, etc.) so the SPA
        # surfaces them without special casing.
        "wrightsoft_mapped_item_count":   mapped_count,
        "wrightsoft_unmapped_item_count": unmapped_count,
        # Day-12 — lines where Wrightsoft's own Src+Name combo gave us
        # the answer directly (no catalog round-trip needed). Tom's
        # 'use what Wrightsoft produced' path made explicit.
        "wrightsoft_passthrough_item_count": passthrough_count,
        # Day-12 — lines whose (Src, SKU) combo we've seen on a previous
        # run (rows in discovered_mappings). Functionally the same as
        # passthrough but with the assurance that we've cataloged the
        # combo. Counts split so we can see how the auto-learn catalog
        # is filling in over time.
        "wrightsoft_discovered_item_count":  discovered_count,
        # Day-15 — count of fittings on this BOM whose code isn't in
        # Tom's standard template. Surfaced for the SPA so reviewers
        # see a "Non-standard fittings detected" banner. Individual
        # lines carry non_standard_fitting=True.
        "wrightsoft_non_standard_fitting_count": non_standard_count,
        # Day-15 — Equipment lines whose model matched the AHRI
        # certified-equipment library. Each such line carries an
        # ahri_spec dict with SEER/HSPF/AFUE/AHRI ref + capacity.
        "wrightsoft_ahri_enriched_count": ahri_count,
        # Day-13 — lines a human has manually corrected for this
        # contractor (rows in contractor_overrides). Highest precedence
        # in the source hierarchy; also where Tom's per-contractor
        # pricing flow lives.
        "wrightsoft_manual_item_count":      manual_count,
        # Day-11 — how many of the mapped lines came from DFUnit
        # (authoritative equipment-library hits with full spec data)
        # vs the generic-parts mapping. Lets the SPA show e.g.
        # "12 mapped (3 from equipment library)".
        "wrightsoft_dfunit_item_count":   dfunit_count,
        "catalog_match_item_count":       0,
        "rules_engine_item_count":        0,
        "ai_item_count":                  0,
        # Day-9 marker so the SPA + comparator know this BOM came from
        # Wrightsoft's own output rather than the AI pipeline.
        "source_pipeline": "wrightsoft_bom",
    }
    # Day-12 — auto-learn upsert. Wrapped so any DB issue (e.g. test
    # context with no session) doesn't poison the BOM response. The
    # caller (bom_routes.from_wrightsoft) does a separate commit after
    # persisting the bom_runs row; this work is queued onto the same
    # session and rides along with that commit.
    if discovered_seen:
        try:
            from extensions import db
            from models.discovered_mapping import DiscoveredMapping
            DiscoveredMapping.upsert_many(discovered_seen)
            db.session.flush()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "discovered_mappings upsert skipped for job %s — %s",
                job_id, exc,
            )

    # Day-17 — Quick Order Summary: group identical SKUs by family +
    # size, sum quantities, apply standard packaging (flex = 25ft
    # boxes, rect fiberglass = 10ft sticks). Tom's #1 ask: contractors
    # see at a glance what to purchase without scanning the detailed
    # row-per-run table below.
    try:
        from services.bom_quick_order import build_quick_order, build_duct_cuts_summary
        # Day-17 — per-piece duct cuts summary (Richard Jun 30).
        # Each cut creates two end joints needing fastener + mastic
        # + tape. Surfaces alongside the aggregated Quick Order so
        # the crew can count joints off the BOM directly.
        bom["duct_cuts_summary"] = build_duct_cuts_summary(line_items)
    except Exception as exc:  # noqa: BLE001
        logger.warning("duct_cuts_summary build skipped: %s", exc)
    try:
        from services.bom_quick_order import build_quick_order
        # Day-17 — pass contractor's consumables rules + supplier prices
        # so mastic/tape/screws roll up with the contractor's actual
        # multipliers, falling back to system defaults when unset.
        cr = profile.consumables_rules
        consumables_rules = {
            "items": [
                {
                    "key":           it.key,
                    "name":          it.name,
                    "description":   it.description,
                    "basis":         it.basis,
                    "per_container": it.per_container,
                    "qty_per_job":   it.qty_per_job,
                    "container":     it.container,
                    "unit_price":    it.unit_price,
                    "enabled":       it.enabled,
                }
                for it in cr.items
            ],
        }
        bom["quick_order_summary"] = build_quick_order(
            line_items,
            consumables_rules=consumables_rules,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort enrichment
        logger.warning("quick_order build skipped: %s", exc)

    logger.info(
        "Wrightsoft BOM built for job %s — %d lines "
        "(%d manual / %d mapped / %d discovered / %d passthrough / %d unmapped)",
        job_id, len(line_items), manual_count, mapped_count,
        discovered_count, passthrough_count, unmapped_count,
    )
    return bom


# ─── Internals ──────────────────────────────────────────────────────

def _supplier_pref_for(profile: ClientProfile) -> Optional[str]:
    """Read the contractor's preferred Wrightsoft supplier code from
    the profile's brand prefs. Returns None when no preference is set,
    which makes lookup_skus_for_generic return all suppliers in file
    order (caller picks the first)."""
    # The 4-char Wrightsoft source code may live in supplier_name
    # (some contractors save 'QST' or 'GOOD' there) or in the brand
    # fields. Best-effort match against the known manufacturer list.
    candidates: list[str] = []
    if profile.supplier and profile.supplier.supplier_name:
        candidates.append(profile.supplier.supplier_name)
    if profile.brands:
        for attr in ("ac_brand", "furnace_brand", "air_handler_brand"):
            v = getattr(profile.brands, attr, "")
            if v: candidates.append(v)
    known = set(wsc.load_manufacturers().keys())
    mfrs = wsc.load_manufacturers()
    for c in candidates:
        if not c: continue
        c_up = c.upper().strip()
        # Direct 4-char code match
        if c_up in known:
            return c_up
        # Substring match against manufacturer Name. Wrightsoft Names
        # have suffixes like "Goodman Mfg.", "LG Electronics" — match
        # the leading word against the candidate so "Goodman" → "GOOD".
        c_low = c.lower().strip()
        for code, row in mfrs.items():
            name = (row.get("Name") or "").lower().strip()
            if not name:
                continue
            # Match: name starts with candidate ("goodman mfg." starts with "goodman")
            # OR candidate starts with name (less common but tolerant)
            if name.startswith(c_low) or c_low.startswith(name):
                return code
    return None


def _category_to_line_category(wrightsoft_cat: Optional[str]) -> str:
    """Map a Wrightsoft category code to one of the line-item
    `category` vocabulary the rest of the BOM pipeline understands
    (equipment / duct / fitting / register / consumable / other)."""
    if not wrightsoft_cat:
        return "other"
    # Equipment-adjacent
    if wrightsoft_cat in ("EACCESSY", "HVACCTLS", "MSRP"):
        return "equipment"
    if wrightsoft_cat == "RHALL":
        return "equipment"  # radiant — closest bucket
    # Duct system
    if wrightsoft_cat in ("DSRCT", "DSRND"):
        return "duct"
    if wrightsoft_cat in ("DFRELB", "DFRPLN", "DFRTKO", "DFRTEE", "DFRTRS"):
        return "fitting"
    if wrightsoft_cat == "DFRBTR":
        return "register"
    if wrightsoft_cat == "HVDALL":
        return "duct"  # Rheia is high-velocity duct
    return "other"


def _priced_line(
    *,
    generic_id: str,
    description: str,
    quantity: float,
    unit: str,
    section: str,
    category: str,
    profile: ClientProfile,
    sku: Optional[str],
    manufacturer: Optional[str],
    source: str,
    get_unit_cost,
    get_markup_pct,
    wrightsoft_price: Optional[float] = None,
) -> dict[str, Any]:
    """Apply markup + estimated-cost fallback to a single line. Shared
    between the mapped and unmapped paths so the cost math is consistent.

    Day-16: when our bundled catalog has no price for the SKU AND
    Wrightsoft itself wrote a per-unit price in the source .xls, fall
    back to that. Without this fallback, Richard's 81-line oracle BOM
    came out as $12.75 vs Wrightsoft's $2,149.81."""
    unit_cost = float(get_unit_cost(description, category, profile) or 0.0)
    if unit_cost == 0.0 and wrightsoft_price and wrightsoft_price > 0:
        unit_cost = float(wrightsoft_price)
    is_estimate = False
    # Equipment-category items with no mapped catalog cost still get
    # the estimated-cost fallback from bom_service so they don't emit
    # as $0 (Day-7 fix — same rule applies here).
    if unit_cost == 0.0 and category == "equipment":
        # _get_unit_cost already checks the estimated table when
        # category is equipment; the > 0 result above already includes
        # that fallback. If still 0, leave as 0.
        pass
    elif unit_cost > 0 and category == "equipment":
        # Mark estimated when the cost came from the hardcoded table
        # rather than a real catalog row. We can't tell from here
        # whether _get_unit_cost hit the estimate path or the supplier
        # cost map, so we conservatively flag only AI-style estimates
        # (no SKU) as such.
        is_estimate = sku is None

    markup_pct = float(get_markup_pct(category, profile) or 0.0)
    unit_price = round(unit_cost * (1 + markup_pct / 100), 2)
    total_cost = round(unit_cost * quantity, 2)
    total_price = round(unit_cost * (1 + markup_pct / 100) * quantity, 2)

    line: dict[str, Any] = {
        "category":    category,
        "description": description,
        "quantity":    quantity,
        "unit":        unit,
        "unit_cost":   unit_cost,
        "unit_price":  unit_price,
        "total_cost":  total_cost,
        "total_price": total_price,
        "markup_pct":  markup_pct,
        "section":     section,
        "source":      source,
        # Always preserve the generic_id — lets the SKU-Backlog page
        # aggregate unmapped IDs into a "what to add to mapped_parts.csv
        # next" prioritized list.
        "generic_id":  generic_id,
    }
    if sku:
        line["sku"] = sku
    if manufacturer:
        line["manufacturer"] = manufacturer
    if is_estimate:
        line["cost_is_estimate"] = True
    return line


def _compute_totals(line_items: list[dict[str, Any]]) -> dict[str, float]:
    total_cost = round(sum(li.get("total_cost") or 0 for li in line_items), 2)
    total_price = round(sum(li.get("total_price") or 0 for li in line_items), 2)
    return {"total_cost": total_cost, "total_price": total_price}


def _utcnow_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _compose_dfunit_description(fallback: str, spec: dict[str, Any]) -> str:
    """Build a human-readable description that incorporates the unit
    capacity + type when DFUnit spec data is available. Keeps the
    caller-provided description as a fallback when the spec is sparse.

    Examples:
        "Carrier 38MARBQ24AA3 — Heat Pump, Outdoor Split, 24,000 BTU"
        "Mitsubishi MUZ-GL18NA-U1 — Heat Pump, Outdoor Multi, 18,000 BTU"
    """
    mfr = spec.get("manufacturer") or ""
    model = spec.get("model") or ""
    parts: list[str] = []
    if mfr and model:
        parts.append(f"{_pretty_manufacturer(mfr)} {model}")
    elif model:
        parts.append(model)
    bits: list[str] = []
    sys_type = spec.get("sys_type")
    if sys_type == "H": bits.append("Heat Pump")
    elif sys_type == "A": bits.append("AC")
    unit_type_label = _UNIT_TYPE_LABEL.get(spec.get("unit_type") or "")
    if unit_type_label: bits.append(unit_type_label)
    cap = spec.get("cooling_btu") or spec.get("heating_btu")
    if cap: bits.append(f"{int(cap):,} BTU")
    if bits and parts:
        return f"{parts[0]} — {', '.join(bits)}"
    if parts:
        return parts[0]
    return fallback


_UNIT_TYPE_LABEL: dict[str, str] = {
    "OS": "Outdoor Split",
    "OM": "Outdoor Multi",
    "IW": "Indoor Wall",
    "IC": "Indoor Ceiling",
    "ID": "Indoor Duct",
    "IF": "Indoor Floor",
    "IA": "Indoor Air-Handler",
    "IU": "Indoor Universal",
}


# Mirrors the substring-tolerant supplier matching in _supplier_pref_for;
# used here to turn a 4-char code (CARR, MITS, DAIK) into a human name
# for display.
_MFR_DISPLAY: dict[str, str] = {
    "CARR": "Carrier", "MITS": "Mitsubishi", "DAIK": "Daikin",
    "FUJI": "Fujitsu", "GREE": "Gree",        "LGEL": "LG",
    "MRCL": "MrCool",  "WSF":  "Wrightsoft",
}

def _pretty_manufacturer(code: str) -> str:
    return _MFR_DISPLAY.get(code.upper(), code)


# ─── CSV / XLS ingestion (Day-9 endpoint input parser) ──────────────

# Column-name aliases the parser will try when locating the
# generic_id / quantity columns. Lowercased and stripped before match.
# Lets us tolerate variations across Wrightsoft versions without
# requiring Tom to rename columns. Order matters — first match wins.
# 'name' must come BEFORE 'item' — Wrightsoft's actual XLS export uses
# 'Name' as the part-identifier column (the row labelled 'Src | Name |
# Description | Phase | Qty | Un | Tax | Price | Ext price'). Older
# pre-Day-12 fixtures used 'item' or 'generic_id' so those still work
# as fallbacks. 'name' is intentionally NOT in the description alias
# list below — same column can't be both gid and description.
_GENERIC_ID_HEADER_ALIASES = (
    "name", "item", "generic_id", "generic id", "id", "part", "part_id",
    "part id", "generic", "code",
)
_QUANTITY_HEADER_ALIASES = (
    "qty", "quantity", "count", "amount", "number",
)
_DESCRIPTION_HEADER_ALIASES = (
    "description", "desc", "label",
)
# Wrightsoft's BOM exports include a 'Src' column carrying the 4-char
# supplier-of-record (GOOD, BROAN, WSF, PGM, RHEA, …). When the bundled
# catalog has no entry for a part, Src tells us who supplies it — which
# the builder uses to emit a wrightsoft_passthrough line instead of
# stuffing it into the SKU Backlog as 'unmapped'.
_SRC_HEADER_ALIASES = (
    "src", "source", "supplier", "vendor",
)
# Wrightsoft's own per-unit pricing column. Day-16: when our bundled
# catalog has no price for a Wrightsoft SKU, fall back to whatever
# Wrightsoft itself wrote in the Price column. Without this fallback
# Richard's 81-line oracle BOM came out as $12.75 vs Wrightsoft's
# $2,149.81 because most fitting SKUs aren't in our catalog yet.
_PRICE_HEADER_ALIASES = (
    "price", "unit price", "unit_price", "cost", "unit cost", "unit_cost",
)


def parse_wrightsoft_bom_rows(
    file_bytes: bytes,
    *,
    filename: str = "",
) -> list[dict[str, Any]]:
    """Parse a Wrightsoft BOM export (CSV or XLS/XLSX) into the
    {generic_id, quantity, description} shape build_bom_from_wrightsoft_lines
    expects.

    Tolerant of column-name variation — looks for common aliases
    ("Item" / "generic_id" / "Part"). Returns [] if no rows decode.
    Raises ValueError on a truly unparseable file so the caller can
    return a 400.

    Header detection: scans the first 10 rows for a row containing
    both a generic-id header AND a quantity header. The matched row
    pins the column indices for subsequent data rows.
    """
    if not file_bytes:
        raise ValueError("Empty file")

    name = (filename or "").lower()
    raw_rows: list[list[str]]
    if name.endswith(".csv") or _looks_like_csv(file_bytes):
        raw_rows = _read_csv_rows(file_bytes)
    else:
        # Defer XLS/XLSX parsing to the existing sample_bom helpers —
        # they already handle both formats with xlrd / openpyxl.
        from services.sample_bom import (
            _read_xlsx_rows, _read_xls_rows,  # noqa: PLC0415
        )
        is_xlsx = name.endswith(".xlsx") or file_bytes[:2] == b"PK"
        is_xls  = name.endswith(".xls") or file_bytes[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
        if is_xlsx:
            raw_rows = _read_xlsx_rows(file_bytes)
        elif is_xls:
            raw_rows = _read_xls_rows(file_bytes)
        else:
            raise ValueError(
                "Unrecognized file format — accepts .csv, .xls, .xlsx "
                "(or send rows as a JSON body instead)."
            )

    return _rows_to_generic_lines(raw_rows)


def _looks_like_csv(file_bytes: bytes) -> bool:
    """Heuristic — comma + newline in the first 1KB, no binary signatures."""
    head = file_bytes[:1024]
    if head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":  # XLS magic
        return False
    if head[:2] == b"PK":  # XLSX (ZIP)
        return False
    try:
        sample = head.decode("utf-8", errors="strict")
        return "," in sample and "\n" in sample
    except UnicodeDecodeError:
        return False


def _read_csv_rows(file_bytes: bytes) -> list[list[str]]:
    """Decode CSV bytes into list-of-list-of-strings."""
    import csv
    import io
    # utf-8-sig transparently strips the BOM Wrightsoft writes
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    return [row for row in reader]


def _rows_to_generic_lines(raw_rows: list[list[Any]]) -> list[dict[str, Any]]:
    """Find the header row (scans first 10 rows), then map each data
    row to {generic_id, quantity, description, src, section_hint}.

    Tolerates rows shorter than the header (treats missing cells as
    empty). Section-divider rows (e.g. 'Equipment', 'Duct System
    Equipment', 'Rheia Duct System Equipment' — rows with blank Name
    + a known section label in the description column) become a
    rolling section_hint that gets attached to subsequent data rows,
    so downstream grouping works even on lines that aren't in the
    bundled mapping catalog.

    'src' is Wrightsoft's supplier-of-record column (GOOD, BROAN,
    RHEA, PGM, WSF, etc.) and is preserved verbatim — the builder
    uses it as a pass-through when the catalog has no entry for the
    Name, so real-world BOMs don't get drowned in 'unmapped' lines
    for parts Wrightsoft has already told us who supplies.
    """
    if not raw_rows:
        return []

    header_idx, gid_col, qty_col, desc_col, src_col, price_col = _locate_header(raw_rows)
    if header_idx < 0:
        raise ValueError(
            "Could not find header row — expected columns including one of "
            f"{list(_GENERIC_ID_HEADER_ALIASES)} for generic ID and one of "
            f"{list(_QUANTITY_HEADER_ALIASES)} for quantity."
        )

    out: list[dict[str, Any]] = []
    current_section_hint: Optional[str] = None
    for row in raw_rows[header_idx + 1:]:
        # Tolerant access — pad short rows so indexing doesn't IndexError
        def _at(i: int) -> str:
            if i < 0 or i >= len(row):
                return ""
            v = row[i]
            return str(v).strip() if v is not None else ""

        gid = _at(gid_col)
        desc = _at(desc_col) if desc_col >= 0 else ""

        # Section-divider row detection. In real Wrightsoft exports
        # these look like ['','','Equipment','','',...] — blank Src +
        # blank Name + description matches a known section keyword.
        # 'Subtotal, X' rows look similar but match the SUBTOTAL_RE so
        # they don't overwrite the hint with junk.
        if not gid:
            hint = _section_hint_from_label(desc)
            if hint:
                current_section_hint = hint
            continue

        qty_raw = _at(qty_col)
        try:
            qty = float(qty_raw or 0)
        except ValueError:
            qty = 0.0
        line: dict[str, Any] = {
            "generic_id":   gid,
            "quantity":     qty,
            "description":  desc,
        }
        src = _at(src_col) if src_col >= 0 else ""
        if src:
            line["src"] = src
        # Day-16: pass through Wrightsoft's own per-unit price as a
        # fallback when our catalog has no entry for this SKU. The
        # builder will use it as unit_cost on the passthrough path so
        # the customer-facing total matches Wrightsoft's own BOM.
        if price_col >= 0:
            price_raw = _at(price_col)
            if price_raw:
                try:
                    price = float(price_raw.replace("$", "").replace(",", ""))
                    if price > 0:
                        line["wrightsoft_price"] = price
                except ValueError:
                    pass
        if current_section_hint:
            line["section_hint"] = current_section_hint
        out.append(line)
    return out


def _locate_header(raw_rows: list[list[Any]]) -> tuple[int, int, int, int, int, int]:
    """Scan the first 10 rows for one containing both a generic-id
    header alias AND a quantity header alias. Returns
    (header_row_index, gid_col, qty_col, description_col_or_-1,
     src_col_or_-1, price_col_or_-1). Returns (-1, 0, 0, -1, -1, -1)
    if no header is found.
    """
    for idx, row in enumerate(raw_rows[:10]):
        norm = [str(c or "").strip().lower() for c in row]
        gid_col = _first_alias_index(norm, _GENERIC_ID_HEADER_ALIASES)
        qty_col = _first_alias_index(norm, _QUANTITY_HEADER_ALIASES)
        if gid_col >= 0 and qty_col >= 0:
            desc_col  = _first_alias_index(norm, _DESCRIPTION_HEADER_ALIASES)
            src_col   = _first_alias_index(norm, _SRC_HEADER_ALIASES)
            price_col = _first_alias_index(norm, _PRICE_HEADER_ALIASES)
            return idx, gid_col, qty_col, desc_col, src_col, price_col
    return -1, 0, 0, -1, -1, -1


# Section-divider lookup. Keys are lowercased; matched as substring
# against the description cell (so 'Subtotal, Equipment' still maps
# to Equipment via the 'equipment' suffix — but we filter subtotals
# out below so they don't reset the hint after an empty section).
_SECTION_HINT_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("rheia duct system equipment", "Rheia Duct System Equipment"),
    ("duct system equipment",       "Duct System Equipment"),
    ("equipment",                   "Equipment"),
    ("labor",                       "Labor"),
)


def _section_hint_from_label(label: str) -> Optional[str]:
    """Recognize a Wrightsoft section-divider row's text. Returns the
    canonical section name or None when the label isn't a divider
    (e.g. 'Subtotal, X' rows must not reset the rolling hint —
    they're handled by the subtotal-prefix filter below)."""
    if not label:
        return None
    low = label.strip().lower()
    if low.startswith("subtotal") or low.startswith("overall total"):
        return None
    for needle, canonical in _SECTION_HINT_KEYWORDS:
        if needle in low:
            return canonical
    return None


def _first_alias_index(norm_row: list[str], aliases: tuple[str, ...]) -> int:
    for alias in aliases:
        if alias in norm_row:
            return norm_row.index(alias)
    return -1
