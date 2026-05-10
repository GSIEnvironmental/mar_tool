"""
Stable storage for per-technology cost totals (capital / maintenance).

Storing raw pandas ``Series`` or unlabeled lists in ``dash_storage`` is fragile: indices
can become positional (0,1,2), so lookups by calculator column name fail and UIs show $0.
Prefer :func:`totals_series_to_storage_dict` when saving; use :func:`coerce_storage_cost_totals`
when reading.
"""

from __future__ import annotations

import pandas as pd

# Calculator column names — must match CostCalculator DataFrame columns.
CAPITAL_COST_TOTAL_KEYS = (
    "Spreading Pond Cost ($)",
    "Injection Wells Cost ($)",
    "Dry Wells Cost ($)",
)
MAINTENANCE_COST_TOTAL_KEYS = (
    "Spreading Pond Maintenance Cost ($)",
    "Injection Wells Maintenance Cost ($)",
    "Dry Wells Maintenance Cost ($)",
)


def coerce_storage_cost_totals(raw, ordered_columns):
    """Coerce stored payloads to a Series indexed by ``ordered_columns``."""
    cols = list(ordered_columns)
    n = len(cols)
    if raw is None:
        return None

    def _names_present(series):
        return all(c in series.index for c in cols)

    if isinstance(raw, pd.Series):
        if not _names_present(raw):
            try:
                if len(raw) == n:
                    return pd.Series(
                        raw.to_numpy(dtype=float, copy=True)[:n],
                        index=cols,
                    )
                if len(raw) >= n:
                    return pd.Series(
                        raw.iloc[:n].to_numpy(dtype=float, copy=True),
                        index=cols,
                    )
            except (TypeError, ValueError):
                pass
        return raw

    if isinstance(raw, dict):
        out = {c: raw.get(c) for c in cols}
        for i, c in enumerate(cols):
            v = out[c]
            if v is None or (isinstance(v, float) and pd.isna(v)):
                if i in raw:
                    out[c] = raw[i]
                elif str(i) in raw:
                    out[c] = raw[str(i)]
        return pd.Series(out)

    if isinstance(raw, (list, tuple)):
        vals = list(raw)
        if len(vals) == n:
            return pd.Series(vals, index=cols)
        return None
    try:
        arr = getattr(raw, "flatten", lambda: raw)()
        size = getattr(arr, "size", len(arr) if hasattr(arr, "__len__") else 0)
        if size == n:
            flat = arr.tolist() if hasattr(arr, "tolist") else list(arr)
            return pd.Series(flat, index=cols)
    except (TypeError, ValueError):
        pass
    return None


def totals_series_to_storage_dict(series, ordered_columns):
    """Convert calculator totals row to a plain dict suitable for ``dash_storage.set_data``."""
    cols = list(ordered_columns)
    s = coerce_storage_cost_totals(series, cols)
    if s is None:
        return None
    out = {}
    for c in cols:
        if c not in s.index:
            out[c] = None
            continue
        v = s[c]
        try:
            out[c] = float(v) if pd.notna(v) else None
        except (TypeError, ValueError):
            out[c] = None
    return out
