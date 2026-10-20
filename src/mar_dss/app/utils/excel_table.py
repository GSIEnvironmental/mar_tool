"""Excel-like Parameter/Value tables: borderless inputs that commit on blur."""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

import dash_bootstrap_components as dbc
from dash import html

INPUT_CELL_BG = "#fff8e1"
COMPUTED_CELL_BG = "#e3f2fd"
TABLE_HEADER_BG = "#2c5aa0"


def input_cell_style() -> dict[str, str]:
    return {"backgroundColor": INPUT_CELL_BG}


def computed_cell_style() -> dict[str, str]:
    return {"backgroundColor": COMPUTED_CELL_BG}


def label_cell_style(row_index: int = 0) -> dict[str, str]:
    return {"backgroundColor": "#f8f9fa" if row_index % 2 else "white"}


def build_table_legend(
    *, compact: bool = False, include_calculated: bool = True
) -> html.Div:
    """Legend for amber = enter value, and optionally blue = calculated."""
    gap = "gap-1" if compact else "gap-1"
    items: list = [
        html.Span(className="excel-legend-swatch excel-legend-input me-1"),
        html.Span(
            "Enter value",
            className="small me-3" if include_calculated else "small",
        ),
    ]
    if include_calculated:
        items.extend(
            [
                html.Span(className="excel-legend-swatch excel-legend-computed me-1"),
                html.Span("Calculated", className="small"),
            ]
        )
    return html.Div(
        items,
        className=f"d-flex align-items-center mt-2 mb-0 text-muted {gap}",
    )


def datatable_base_style_cell(**overrides: Any) -> dict[str, Any]:
    style = {
        "textAlign": "left",
        "padding": "10px",
        "fontFamily": "Arial, sans-serif",
        "fontSize": "14px",
        "border": "1px solid #ddd",
    }
    style.update(overrides)
    return style


def datatable_base_style_header(**overrides: Any) -> dict[str, Any]:
    style = {
        "backgroundColor": TABLE_HEADER_BG,
        "color": "white",
        "fontWeight": "bold",
        "border": "1px solid #ddd",
        "textAlign": "center",
    }
    style.update(overrides)
    return style


def datatable_computed_data_style(**overrides: Any) -> dict[str, Any]:
    style = {
        "backgroundColor": COMPUTED_CELL_BG,
        "border": "1px solid #ddd",
        "color": "#0d47a1",
    }
    style.update(overrides)
    return style


def datatable_column_styles(
    *,
    computed_columns: Optional[Iterable[str]] = None,
    input_columns: Optional[Iterable[str]] = None,
    label_columns: Optional[Iterable[str]] = None,
) -> list[dict[str, Any]]:
    """Conditional column backgrounds for dash_table.DataTable."""
    styles: list[dict[str, Any]] = []
    for col in computed_columns or ():
        styles.append(
            {"if": {"column_id": col}, "backgroundColor": COMPUTED_CELL_BG, "color": "#0d47a1"}
        )
    for col in input_columns or ():
        styles.append({"if": {"column_id": col}, "backgroundColor": INPUT_CELL_BG})
    for col in label_columns or ():
        styles.append(
            {
                "if": {"column_id": col},
                "backgroundColor": "#ffffff",
                "fontWeight": "600",
            }
        )
    return styles


def wrap_table_with_legend(table_component, *, show_legend: bool = True):
    """Wrap a table component with the standard color legend."""
    if not show_legend:
        return table_component
    return html.Div([table_component, build_table_legend()])


def _as_float(raw: Any, default: float = 0.0) -> float:
    try:
        if raw is None or raw == "":
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def _cell_background(
    param: str,
    row_index: int,
    *,
    readonly: set[str],
    input_highlight: set[str],
    computed_highlight: set[str],
    legacy_highlight: set[str],
) -> str:
    if param in computed_highlight or (param in readonly and param not in input_highlight):
        return COMPUTED_CELL_BG
    if param in input_highlight:
        return INPUT_CELL_BG
    if param in legacy_highlight:
        return COMPUTED_CELL_BG
    return "#f8f9fa" if row_index % 2 else "white"


def build_param_value_table(
    rows: Sequence[dict],
    *,
    input_type: str,
    readonly_params: Optional[Iterable[str]] = None,
    highlight_params: Optional[Iterable[str]] = None,
    input_highlight_params: Optional[Iterable[str]] = None,
    computed_highlight_params: Optional[Iterable[str]] = None,
    table_class: str = "table table-sm table-bordered mb-0 excel-cell-table",
    min_value: Optional[float] = None,
) -> html.Table:
    """Build a two-column Parameter / Value table with borderless number inputs.

    ``rows`` items: ``{"Parameter": str, "Value": number}``.
    ``input_type`` is the Dash pattern-matching id ``type`` for value inputs
    (``{"type": input_type, "param": <Parameter>}``).
    ``min_value`` sets the HTML ``min`` attribute on editable number inputs when given.
    """
    readonly = set(readonly_params or [])
    input_highlight = set(input_highlight_params or [])
    computed_highlight = set(computed_highlight_params or [])
    legacy_highlight = set(highlight_params or [])

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
        bg = _cell_background(
            param,
            i,
            readonly=readonly,
            input_highlight=input_highlight,
            computed_highlight=computed_highlight,
            legacy_highlight=legacy_highlight,
        )
        is_computed = param in computed_highlight or (
            is_ro and param not in input_highlight
        )

        if is_ro:
            value_cell = html.Td(
                html.Span(
                    f"{_as_float(value):g}",
                    className=(
                        "d-block text-center fw-semibold py-1 "
                        + ("excel-cell-computed" if is_computed else "")
                    ),
                ),
                className="align-middle py-0 px-1",
            )
        else:
            input_kwargs = {}
            if min_value is not None:
                input_kwargs["min"] = min_value
            value_cell = html.Td(
                dbc.Input(
                    id={"type": input_type, "param": param},
                    type="number",
                    value=_as_float(value),
                    debounce=True,
                    size="sm",
                    className="text-center table-cell-input-borderless excel-cell-input",
                    **input_kwargs,
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
