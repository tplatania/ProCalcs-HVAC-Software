"""Server-enforced contractor/client isolation.

The browser is not a security boundary.  These helpers derive the allowed
client IDs from the service-authenticated user email and apply that scope to
database queries and write targets inside the BOM backend.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

from flask import current_app, request


def _normalized_rules() -> dict[str, set[str]]:
    raw = current_app.config.get("CLIENT_SCOPE_RULES") or {}
    if not isinstance(raw, dict):
        return {}
    result: dict[str, set[str]] = {}
    for identity, client_ids in raw.items():
        key = str(identity or "").strip().lower().lstrip("@")
        if not key:
            continue
        if isinstance(client_ids, str):
            values: Iterable[object] = [client_ids]
        elif isinstance(client_ids, (list, tuple, set)):
            values = client_ids
        else:
            continue
        result[key] = {
            str(value).strip()
            for value in values
            if str(value or "").strip()
        }
    return result


def allowed_client_ids() -> set[str] | None:
    """Return permitted clients, or ``None`` for unrestricted internal users.

    In local/test mode, the explicit insecure-auth opt-out stays unrestricted.
    In authenticated environments, a missing identity or an unmapped external
    identity gets an empty set and therefore no client access.
    """
    if os.environ.get("ALLOW_INSECURE_NO_AUTH") == "1" and not current_app.config.get(
        "SERVICE_SHARED_SECRET"
    ):
        return None

    email = (request.headers.get("X-Procalcs-User-Email") or "").strip().lower()
    if not email or "@" not in email:
        return set()

    domain = email.rsplit("@", 1)[1]
    internal_domain = str(current_app.config.get("INTERNAL_DOMAIN") or "").strip().lower()
    if internal_domain and domain == internal_domain:
        return None

    rules = _normalized_rules()
    if email in rules:
        return rules[email]
    return rules.get(domain, set())


def can_access_client(client_id: str | None) -> bool:
    allowed = allowed_client_ids()
    if allowed is None:
        return True
    return bool(client_id and client_id in allowed)


def scope_query(query, client_column):
    """Apply the current identity's scope to a SQLAlchemy query."""
    allowed = allowed_client_ids()
    if allowed is None:
        return query
    if not allowed:
        return query.filter(False)
    return query.filter(client_column.in_(sorted(allowed)))
