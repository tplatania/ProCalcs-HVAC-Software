"""
ts_format.py — human timestamp formatting for BOM exports.

Dana #10 (2026-09-02): exports showed a raw ISO timestamp with
microseconds in UTC ("2026-09-02T14:05:22.450609+00:00"). ProCalcs
business hours are EST, so render generated-at in US Eastern
(handles EST/EDT automatically) with no microseconds.
"""
from __future__ import annotations

from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    _EASTERN = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover — zoneinfo/tzdata missing
    _EASTERN = None


def format_generated_eastern(ts) -> str:
    """Return e.g. 'Sep 2, 2026 10:05 AM EST'. Accepts an ISO string,
    a datetime, or falsy (→ now). Falls back to a clean UTC string if
    the Eastern zone is unavailable."""
    dt = _coerce(ts)
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if _EASTERN is not None:
        local = dt.astimezone(_EASTERN)
        tzname = local.tzname() or "EST"
        # %-d/%-I are POSIX; guard for portability.
        try:
            return local.strftime(f"%b %-d, %Y %-I:%M %p {tzname}")
        except ValueError:
            return local.strftime(f"%b %d, %Y %I:%M %p {tzname}").replace(" 0", " ")
    return dt.astimezone(timezone.utc).strftime("%b %d, %Y %H:%M UTC")


def _coerce(ts):
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts
    s = str(ts).strip()
    if not s:
        return None
    try:
        # Python's fromisoformat handles microseconds + offset.
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
