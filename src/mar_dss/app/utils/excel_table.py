"""Excel-like Parameter/Value tables: borderless inputs that commit on blur."""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

import dash_bootstrap_components as dbc
from dash import html


def _as_float(raw: Any, default: float = 0.0) -> float:
    try:
        if raw is None or raw == "":
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def build_param_value_table(
    rows: Sequence[dict],
    *,
    input_type: str,
    readonly_params: Optional[Iterable[str]] = None,
    highlight_params: Optional[Iterable[str]] = None,
    table_class: str = "table table-sm table-bordered mb-0 excel-cell-table",
) -> html.Table:
    """Build a two-column Parameter / Value table with borderless number inputs.

    ``rows`` items: ``{"Parameter": str, "Value": number}``.
    ``input_type`` is the Dash pattern-matching id ``type`` for value inputs
    (``{"type": input_type, "param": <Parameter>}``).
    """
    readonly = set(readonly_params or [])
    highlight = set(highlight_params or [])

    body_rows = [
        html.Tr(
            [
                html.Th("Parameter", className="text-center text-white py-2 px-2"),
                html.Th("Value", className="text-center text-white py-2 px-2"),
            ],
            style={"backgroundColor": "#2c5aa0"},
        )
    ]

    for i, row in enumerate(rows):
        param = str(row.get("Parameter", ""))
        value = row.get("Value", 0)
        is_ro = param in readonly
        bg = "#e3f2fd" if param in highlight else ("#f8f9fa" if i % 2 else "white")

        if is_ro:
            value_cell = html.Td(
                html.Span(
                    f"{_as_float(value):g}",
                    className="d-block text-center fw-semibold py-1",
                ),
                className="align-middle py-0 px-1",
            )
        else:
            value_cell = html.Td(
                dbc.Input(
                    id={"type": input_type, "param": param},
                    type="number",
                    value=_as_float(value),
                    debounce=True,
                    size="sm",
                    className="text-center table-cell-input-borderless",
                ),
                className="align-middle py-0 px-1",
            )

        body_rows.append(
            html.Tr(
                [
                    html.Td(
                        param,
                        className="align-middle small fw-semibold py-1 px-2",
                    ),
                    value_cell,
                ],
                style={"backgroundColor": bg},
            )
        )

    return html.Table(body_rows, className=table_class, style={"width": "100%"})


def rows_from_param_inputs(
    values: Sequence[Any],
    ids: Sequence[dict],
    base_rows: Sequence[dict],
) -> list[dict]:
    """Merge pattern-matching input values into Parameter/Value row dicts."""
    by_param = {}
    for id_dict, raw in zip(ids or [], values or []):
        if not isinstance(id_dict, dict):
            continue
        param = id_dict.get("param")
        if param is None:
            continue
        by_param[param] = _as_float(raw)

    out = []
    for row in base_rows:
        param = str(row.get("Parameter", ""))
        new_row = dict(row)
        if param in by_param:
            new_row["Value"] = by_param[param]
        out.append(new_row)
    return out
