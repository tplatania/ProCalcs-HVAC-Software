"""
sku_catalog_routes.py — CRUD for the SKU catalog.

Mounted under /api/v1/sku-catalog. Same shared-secret auth as the rest
of /api/v1/*. Edited via the Designer Desktop SPA so Richard's team can
maintain SKUs without a code deploy.

Endpoints:
    GET     /api/v1/sku-catalog?section=&supplier=&include_disabled=
    GET     /api/v1/sku-catalog/<sku>
    POST    /api/v1/sku-catalog                  → create (409 on dup)
    PUT     /api/v1/sku-catalog/<sku>            → partial update
    POST    /api/v1/sku-catalog/<sku>/disable    → set disabled=true
    POST    /api/v1/sku-catalog/<sku>/enable     → set disabled=false
    DELETE  /api/v1/sku-catalog/<sku>            → hard delete
    GET     /api/v1/sku-catalog/_meta            → enums for the SPA form
"""
import logging
from flask import Blueprint, jsonify, request
from services import sku_catalog
from services.sku_catalog import (
    CatalogError,
    VALID_SECTIONS,
    VALID_TRIGGERS,
    VALID_QUANTITY_MODES,
    VALID_PHASES,
)


logger = logging.getLogger('procalcs_bom')
sku_catalog_bp = Blueprint('sku_catalog', __name__)


def _actor() -> str | None:
    """Pull the calling client identity from the X-Client-Id header
    forwarded by the BFF (designer-desktop, designer-dashboard, etc.).
    Used purely for audit trail; not for authorization (the shared
    secret already gates the request)."""
    return request.headers.get('X-Actor-Email') or request.headers.get('X-Client-Id')


def _serialize(item: sku_catalog.SKUItem) -> dict:
    return item.to_dict()


def _err(exc: CatalogError):
    return jsonify({"success": False, "data": None, "error": str(exc)}), exc.status_code


# ===============================
# GET — List
# ===============================

@sku_catalog_bp.route('/', methods=['GET'])
@sku_catalog_bp.route('', methods=['GET'])
def list_items():
    """List catalog items. Query params:
        section            — filter by section (exact match)
        supplier           — filter by supplier (case-insensitive)
        include_disabled   — '1'/'true' to include soft-hidden items (default true)
    """
    section = request.args.get('section')
    supplier = request.args.get('supplier')
    include_disabled = request.args.get('include_disabled', 'true').lower() in ('1', 'true', 'yes')

    items = sku_catalog.all_items(include_disabled=include_disabled)
    if section:
        items = [it for it in items if it.section == section]
    if supplier:
        s = supplier.lower()
        items = [it for it in items if it.supplier.lower() == s]

    return jsonify({
        "success": True,
        "data": [_serialize(it) for it in items],
        "error": None,
        "meta": {"source": sku_catalog.source(), "count": len(items)},
    }), 200


# ===============================
# GET — Meta (enums for the form)
# ===============================

@sku_catalog_bp.route('/_meta', methods=['GET'])
def get_meta():
    """Static reference data for the SPA form — sections, triggers,
    quantity modes, phases. Returned as sorted lists."""
    return jsonify({
        "success": True,
        "data": {
            "sections": sorted(VALID_SECTIONS),
            "triggers": sorted(VALID_TRIGGERS),
            "quantity_modes": sorted(VALID_QUANTITY_MODES),
            "phases": sorted(p for p in VALID_PHASES if p),
            "suppliers_seen": sorted({it.supplier for it in sku_catalog.all_items()}),
        },
        "error": None,
    }), 200


# ===============================
# GET — One
# ===============================

@sku_catalog_bp.route('/<string:sku>', methods=['GET'])
def get_item(sku: str):
    item = sku_catalog.get(sku)
    if not item:
        return jsonify({"success": False, "data": None, "error": "Not found."}), 404
    return jsonify({"success": True, "data": _serialize(item), "error": None}), 200


# ===============================
# POST — Create
# ===============================

@sku_catalog_bp.route('/', methods=['POST'])
@sku_catalog_bp.route('', methods=['POST'])
def create_item():
    payload = request.get_json(silent=True) or {}
    try:
        record = sku_catalog.create_item(payload, actor_email=_actor())
    except CatalogError as exc:
        return _err(exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("create_item failed: %s", exc)
        return jsonify({"success": False, "data": None,
                        "error": "Unable to create SKU."}), 500
    return jsonify({"success": True, "data": record, "error": None}), 201


# ===============================
# POST — Bulk import (Phase 3.6, May 2026)
# ===============================
#
# Body shape:
#   {"items": [<sku payload>, <sku payload>, ...]}
#
# Each item is validated and either created (no existing doc with that
# sku) or fully replaced (idempotent upsert). Per-row failures don't
# abort the batch — they're surfaced as a list in the response.
#
# Designed for two callers:
#   1. The SPA's bulk-import UI (paste CSV → POST as JSON)
#   2. Tom uploading vendor catalogs (Goodman / Rheia / contractor-brand)
#      converted from CSV to JSON either by the SPA or by curl one-liner
#
# The SPA handles CSV-to-JSON conversion client-side so this endpoint
# stays JSON-only — keeps the auth/middleware contract simple and the
# response shape predictable.

@sku_catalog_bp.route('/bulk-import', methods=['POST'])
def bulk_import():
    payload = request.get_json(silent=True) or {}
    items = payload.get("items")
    if not isinstance(items, list):
        return jsonify({
            "success": False,
            "data":    None,
            "error":   "Body must be {\"items\": [<sku payload>, ...]}",
        }), 400

    try:
        summary = sku_catalog.bulk_upsert(items, actor_email=_actor())
    except CatalogError as exc:
        return _err(exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("bulk_import failed: %s", exc)
        return jsonify({
            "success": False,
            "data":    None,
            "error":   "Bulk import failed.",
        }), 500

    # 200 even when individual rows failed — the operation as a whole
    # succeeded (some rows landed, some were rejected with reasons).
    # The SPA decides whether to surface per-row errors or treat any
    # error count > 0 as a hard failure.
    return jsonify({"success": True, "data": summary, "error": None}), 200


# ===============================
# PUT — Update
# ===============================

@sku_catalog_bp.route('/<string:sku>', methods=['PUT'])
def update_item(sku: str):
    patch = request.get_json(silent=True) or {}
    try:
        record = sku_catalog.update_item(sku, patch, actor_email=_actor())
    except CatalogError as exc:
        return _err(exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("update_item failed for %s: %s", sku, exc)
        return jsonify({"success": False, "data": None,
                        "error": "Unable to update SKU."}), 500
    return jsonify({"success": True, "data": record, "error": None}), 200


# ===============================
# POST — Disable / Enable
# ===============================

@sku_catalog_bp.route('/<string:sku>/disable', methods=['POST'])
def disable_item(sku: str):
    try:
        record = sku_catalog.set_disabled(sku, True, actor_email=_actor())
    except CatalogError as exc:
        return _err(exc)
    return jsonify({"success": True, "data": record, "error": None}), 200


@sku_catalog_bp.route('/<string:sku>/enable', methods=['POST'])
def enable_item(sku: str):
    try:
        record = sku_catalog.set_disabled(sku, False, actor_email=_actor())
    except CatalogError as exc:
        return _err(exc)
    return jsonify({"success": True, "data": record, "error": None}), 200


# ===============================
# DELETE — Hard delete
# ===============================

@sku_catalog_bp.route('/<string:sku>', methods=['DELETE'])
def delete_item(sku: str):
    try:
        sku_catalog.delete_item(sku, actor_email=_actor())
    except CatalogError as exc:
        return _err(exc)
    return ('', 204)
