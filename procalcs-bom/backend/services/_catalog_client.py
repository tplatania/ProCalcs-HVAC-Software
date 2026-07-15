"""_catalog_client.py — VENDORED from
procalcs-catalog/clients/python/procalcs_catalog_client/client.py.

Keep in sync until we have a private artifact registry. Bug fixes go
upstream then come back. Do NOT diverge the public API locally.

Thin REST wrapper around procalcs-catalog + lightweight TTL cache.
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Any, Optional
from urllib.parse import urljoin

import requests


logger = logging.getLogger("procalcs_catalog_client")


def _looks_like_mfr_code(s: str) -> bool:
    """A 4-char alphanumeric all-caps string is assumed to already BE
    a Wrightsoft manufacturer code (TRAN, BRYA, CARR). Anything else
    is treated as a display name that needs server-side resolution."""
    return bool(s) and len(s) == 4 and s.isupper() and s.isalnum()


class CatalogError(Exception):
    """Raised when the catalog service returns a non-2xx OR a Flask
    envelope with success=false. .status_code + .error_text on the
    instance for diagnostics."""

    def __init__(self, message: str, status_code: int | None = None,
                 error_text: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_text = error_text


class CatalogClient:
    """Thread-safe client. Reuses a single requests.Session under the
    hood for connection pooling."""

    def __init__(
        self,
        base_url: str,
        *,
        service_token: str | None = None,
        client_id: str = "procalcs-client",
        timeout_seconds: float = 10.0,
        cache_ttl_seconds: float = 300.0,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout_seconds
        self.cache_ttl = cache_ttl_seconds
        self._service_token = service_token
        self._client_id = client_id
        self._session = session or requests.Session()
        self._cache: dict[str, tuple[float, Any]] = {}
        self._cache_lock = Lock()

    # ─── Public methods ────────────────────────────────────────────

    def manufacturers(self, *, as_of: str | None = None) -> list[dict]:
        return self._get_items("api/v1/catalog/manufacturers", {}, as_of)

    def categories(self, *, as_of: str | None = None) -> list[dict]:
        return self._get_items("api/v1/catalog/categories", {}, as_of)

    def generics(self, *, category: str | None = None,
                 item: str | None = None, limit: int | None = None,
                 as_of: str | None = None) -> list[dict]:
        params: dict[str, Any] = {}
        if category: params["category"] = category
        if item:     params["item"] = item
        if limit:    params["limit"] = limit
        return self._get_items("api/v1/catalog/generics", params, as_of)

    def mappings(self, *, generic_item: str | None = None,
                 manufacturer_partnum: str | None = None,
                 limit: int = 5000,
                 as_of: str | None = None) -> list[dict]:
        """Bulk list mapped_parts. Used by procalcs-bom to warm its
        local cache on startup. Paginates through offsets when total
        exceeds the per-call ceiling."""
        params_base: dict[str, Any] = {}
        if generic_item: params_base["generic_item"] = generic_item
        if manufacturer_partnum: params_base["manufacturer_partnum"] = manufacturer_partnum
        out: list[dict] = []
        offset = 0
        while True:
            params = {**params_base, "limit": limit, "offset": offset}
            data = self._get_envelope("api/v1/catalog/mappings",
                                      params, as_of)
            if not isinstance(data, dict):
                break
            items = data.get("items") or []
            out.extend(items)
            total = int(data.get("count") or 0)
            offset += len(items)
            if not items or offset >= total:
                break
        return out

    def mappings_by_generic(self, generic_item: str, *,
                            as_of: str | None = None) -> list[dict]:
        """Hot path — translation of one Wrightsoft generic to all its
        supplier variants. Cached."""
        body = self._get_cached(
            f"api/v1/catalog/mappings/by-generic/{generic_item}",
            {}, as_of,
        )
        return body.get("items") or []

    def mappings_by_sku(self, sku: str, *,
                        as_of: str | None = None) -> list[dict]:
        body = self._get_cached(
            f"api/v1/catalog/mappings/by-sku/{sku}", {}, as_of,
        )
        return body.get("items") or []

    def mapping_by_sku_first(self, sku: str, *,
                             as_of: str | None = None) -> dict | None:
        """Convenience — first mapping row for a SKU, or None."""
        rows = self.mappings_by_sku(sku, as_of=as_of)
        return rows[0] if rows else None

    def dfunit(self, *, manufacturer: str | None = None,
               model: str | None = None,
               sys_type: str | None = None,
               unit_type: str | None = None,
               min_clg_btu: int | None = None,
               max_clg_btu: int | None = None,
               min_htg_btu: int | None = None,
               max_htg_btu: int | None = None,
               limit: int | None = None,
               as_of: str | None = None) -> list[dict]:
        params = {k: v for k, v in {
            "manufacturer": manufacturer, "model": model,
            "sys_type": sys_type, "unit_type": unit_type,
            "min_clg_btu": min_clg_btu, "max_clg_btu": max_clg_btu,
            "min_htg_btu": min_htg_btu, "max_htg_btu": max_htg_btu,
            "limit": limit,
        }.items() if v is not None}
        return self._get_items("api/v1/catalog/dfunit", params, as_of)

    def ahri(self, product_type: str, *,
             manufacturer: str | None = None,
             condenser_model: str | None = None,
             min_capacity: int | None = None,
             max_capacity: int | None = None,
             min_seer: float | None = None,
             min_hspf: float | None = None,
             min_afue: float | None = None,
             min_eer95: float | None = None,
             limit: int | None = None,
             as_of: str | None = None) -> list[dict]:
        params = {k: v for k, v in {
            "manufacturer": manufacturer,
            "condenser_model": condenser_model,
            "min_capacity": min_capacity, "max_capacity": max_capacity,
            "min_seer": min_seer, "min_hspf": min_hspf,
            "min_afue": min_afue, "min_eer95": min_eer95,
            "limit": limit,
        }.items() if v is not None}
        return self._get_items(f"api/v1/catalog/ahri/{product_type}",
                               params, as_of)

    def fitting_template(self, *,
                         category: str | None = None,
                         direction: str | None = None,
                         shape: str | None = None,
                         fitting_code: str | None = None,
                         as_of: str | None = None) -> list[dict]:
        """List Tom's canonical fitting-code template rows."""
        params = {k: v for k, v in {
            "category": category, "direction": direction,
            "shape": shape, "fitting_code": fitting_code,
        }.items() if v is not None}
        return self._get_items("api/v1/catalog/fitting-template",
                               params, as_of)

    def fitting_template_by_code(self, code: str, *,
                                 as_of: str | None = None) -> dict:
        """Reverse lookup — returns {fitting_code, in_template (bool),
        count, items: [...]}. `in_template == False` is the BOM
        Generator's 'flag as non-standard' signal."""
        return self._get_cached(
            f"api/v1/catalog/fitting-template/by-code/{code}",
            {}, as_of,
        ) or {"fitting_code": code, "in_template": False,
              "count": 0, "items": []}

    # ─── Wrightsoft binary catalog (RPRUWSF.mdb + follow-ons) ──────
    # Day-20+ — new endpoints backed by wrightsoft_actitem /
    # wrightsoft_actcateg / wrightsoft_dfunit_full tables. Ingested
    # directly from Wrightsoft's binary catalogs via
    # scripts/import_wrightsoft_mdb.py on procalcs-catalog. Only called
    # when a contractor profile opts in via
    # ClientProfile.use_wrightsoft_hosted_catalog=True; the legacy
    # /mappings + /dfunit paths remain the default until we flip the
    # fleet.

    def wrightsoft_actitem_by_pn(self, part_no: str, *,
                                  psrc: str | None = None,
                                  source_mdb: str | None = None,
                                  as_of: str | None = None) -> list[dict]:
        """Lookup Wrightsoft parts-master rows for a given PN. Returns
        a list because the same PN can exist across multiple suppliers
        (psrc) or multiple manufacturer catalogs (source_mdb) — narrow
        with the filters when the caller knows which one they want."""
        params = {k: v for k, v in {
            "psrc": psrc, "source_mdb": source_mdb,
        }.items() if v is not None}
        body = self._get_cached(
            f"api/v1/catalog/wrightsoft/actitem/{part_no}",
            params, as_of,
        )
        if not body:
            return []
        return body.get("items") or []

    def wrightsoft_pricing_for_part(self, *, category: str, psrc: str,
                                     pn: str, source_mdb: str | None = None,
                                     as_of: str | None = None
                                     ) -> dict | None:
        """One-shot part + rule join. Returns:
            {
              "part": {...ActItem row...},
              "rule": {...ActCateg row for (category, psrc)...} | None
            }
        or None when the part isn't in the catalog. The caller applies
        the rule to the part's raw price to compute the final line
        price — same math Wrightsoft's own UI does at BOM assembly."""
        params: dict[str, Any] = {"category": category, "psrc": psrc, "pn": pn}
        if source_mdb is not None:
            params["source_mdb"] = source_mdb
        return self._get_cached(
            "api/v1/catalog/wrightsoft/pricing-for-part",
            params, as_of,
        )

    def arigama2_manufacturer_by_code(self, code: str, *,
                                       domain: str | None = None,
                                       as_of: str | None = None
                                       ) -> dict | None:
        """Resolve a 4-char Wrightsoft manufacturer code (TRAN, BRYA,
        CARR, DAIK...) to its display name. Optional domain narrows
        to cooling|heating|wshp when the caller knows the equipment
        type; otherwise walks all three in that priority."""
        params = {"domain": domain} if domain else {}
        return self._get_cached(
            f"api/v1/catalog/arigama2/manufacturer/{code}",
            params, as_of,
        )

    def arigama2_manufacturer_batch(self, codes: list[str], *,
                                     domain: str | None = None,
                                     as_of: str | None = None
                                     ) -> dict[str, dict]:
        """Resolve multiple manufacturer codes in one round-trip.
        Returns {code: {mfrcode, mfr, ...}} — includes only codes
        that were found. Callers should fall back to the raw code
        for anything missing."""
        if not codes:
            return {}
        params: dict[str, Any] = {"codes": ",".join(codes[:200])}
        if domain:
            params["domain"] = domain
        body = self._get_cached(
            "api/v1/catalog/arigama2/manufacturer",
            params, as_of,
        )
        if not body:
            return {}
        return body.get("items") or {}

    def arigama2_ac_by_model(self, *, manufacturer: str,
                              condenser_model: str | None = None,
                              coil_model: str | None = None,
                              as_of: str | None = None) -> list[dict]:
        """Look up cooling equipment by manufacturer + condenser or coil
        model. `manufacturer` may be either a 4-char code (TRAN) or a
        display name ("Trane"). Provide at least one of condenser_model
        or coil_model. Returns rows sorted by capacity desc."""
        if not manufacturer or not (condenser_model or coil_model):
            return []
        param_key = ("manufacturer" if _looks_like_mfr_code(manufacturer)
                      else "manufacturer_name")
        params: dict[str, Any] = {param_key: manufacturer}
        if condenser_model:
            params["condenser_model"] = condenser_model
        if coil_model:
            params["coil_model"] = coil_model
        body = self._get_cached(
            "api/v1/catalog/arigama2/ac/by-model",
            params, as_of,
        )
        if not body:
            return []
        return body.get("items") or []

    def arigama2_hp_by_model(self, *, manufacturer: str,
                              condenser_model: str | None = None,
                              coil_model: str | None = None,
                              as_of: str | None = None) -> list[dict]:
        """Same shape as arigama2_ac_by_model but for heat pumps —
        includes HSPF, high_capacity, low_capacity, high_cop, low_cop
        alongside the AC-shared fields."""
        if not manufacturer or not (condenser_model or coil_model):
            return []
        param_key = ("manufacturer" if _looks_like_mfr_code(manufacturer)
                      else "manufacturer_name")
        params: dict[str, Any] = {param_key: manufacturer}
        if condenser_model:
            params["condenser_model"] = condenser_model
        if coil_model:
            params["coil_model"] = coil_model
        body = self._get_cached(
            "api/v1/catalog/arigama2/hp/by-model",
            params, as_of,
        )
        if not body:
            return []
        return body.get("items") or []

    def arigama2_furnace_by_model(self, *, manufacturer: str,
                                    model: str,
                                    as_of: str | None = None) -> list[dict]:
        """Furnace lookup — returns input/output/AFUE/fuel/stages
        plus dimensions."""
        if not (manufacturer and model):
            return []
        param_key = ("manufacturer" if _looks_like_mfr_code(manufacturer)
                      else "manufacturer_name")
        body = self._get_cached(
            "api/v1/catalog/arigama2/furnace/by-model",
            {param_key: manufacturer, "model": model},
            as_of,
        )
        if not body:
            return []
        return body.get("items") or []

    def wrightsoft_dfunit_full(self, model: str, *,
                                as_of: str | None = None) -> dict | None:
        """Authoritative DFUnit lookup from RPRUWSF.mdb (supersedes
        the CSV-sourced /dfunit endpoint for callers that want the
        .mdb-ingested version)."""
        return self._get_cached(
            f"api/v1/catalog/wrightsoft/dfunit-full/{model}",
            {}, as_of,
        )

    def latest_batch(self) -> dict | None:
        body = self._get_envelope("api/v1/catalog/batches/latest", {}, None)
        return body if isinstance(body, dict) else None

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()

    # ─── Internals ─────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {
            "Accept": "application/json",
            "X-Client-Id": self._client_id,
        }
        if self._service_token:
            h["X-Procalcs-Service-Token"] = self._service_token
        return h

    def _cache_key(self, path: str, params: dict, as_of: str | None) -> str:
        items = sorted((str(k), str(v)) for k, v in params.items())
        return f"{path}?{items}|as_of={as_of or '_'}"

    def _get_envelope(self, path: str, params: dict, as_of: str | None) -> Any:
        """Issue the GET, validate the envelope, return the `data` field."""
        if as_of:
            params = {**params, "as_of": as_of}
        url = urljoin(self.base_url, path)
        try:
            r = self._session.get(url, params=params,
                                  headers=self._headers(),
                                  timeout=self.timeout)
        except requests.RequestException as e:
            raise CatalogError(f"Network error: {e}") from e
        if r.status_code >= 500:
            raise CatalogError(
                f"Server error {r.status_code} from {path}",
                status_code=r.status_code, error_text=r.text[:200],
            )
        try:
            body = r.json()
        except ValueError as e:
            raise CatalogError(
                f"Non-JSON response from {path}: {r.text[:200]}",
                status_code=r.status_code,
            ) from e
        if not isinstance(body, dict) or "success" not in body:
            raise CatalogError(
                f"Unexpected response shape from {path}",
                status_code=r.status_code, error_text=str(body)[:200],
            )
        if not body.get("success"):
            raise CatalogError(
                body.get("error") or "Unknown catalog error",
                status_code=r.status_code,
                error_text=body.get("error"),
            )
        return body.get("data")

    def _get_cached(self, path: str, params: dict, as_of: str | None) -> Any:
        key = self._cache_key(path, params, as_of)
        now = time.monotonic()
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry and entry[0] > now:
                return entry[1]
        data = self._get_envelope(path, params, as_of)
        with self._cache_lock:
            self._cache[key] = (now + self.cache_ttl, data)
        return data

    def _get_items(self, path: str, params: dict, as_of: str | None) -> list[dict]:
        """Endpoints that wrap a list in {count, items}. Drop the
        wrapper for the caller's convenience."""
        data = self._get_cached(path, params, as_of)
        if not isinstance(data, dict):
            return []
        items = data.get("items")
        return items if isinstance(items, list) else []
