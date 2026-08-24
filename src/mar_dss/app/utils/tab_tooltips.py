"""Helpers for tab nav tooltips with dash-bootstrap-components Tabs."""

import dash_bootstrap_components as dbc
from dash import html

# Global switch for all UI tooltips (Bootstrap, tab nav, sliders, tables, etc.).
TOOLTIPS_ENABLED = False


def tab_nav_id(tab_id: str, *, id_prefix: str = "") -> str:
    """Return the ``id`` for ``dbc.Tab`` so ``dbc.Tooltip`` can target the nav link."""
    return f"{id_prefix}tab-{tab_id}" if id_prefix else f"tab-{tab_id}"


def tab_tooltip(
    tab_id: str,
    text: str,
    *,
    id_prefix: str = "",
    placement: str = "bottom",
):
    """Return a Bootstrap tooltip for a tab nav link."""
    if not TOOLTIPS_ENABLED:
        return html.Div(style={"display": "none"})
    return dbc.Tooltip(
        text,
        target=tab_nav_id(tab_id, id_prefix=id_prefix),
        placement=placement,
    )


def dbc_tooltip(*args, **kwargs):
    """Return ``dbc.Tooltip`` or a hidden placeholder when tooltips are disabled."""
    if not TOOLTIPS_ENABLED:
        return html.Div(style={"display": "none"})
    return dbc.Tooltip(*args, **kwargs)


def slider_tooltip_kwargs():
    """``dcc.Slider`` tooltip config, or ``None`` when tooltips are disabled."""
    if not TOOLTIPS_ENABLED:
        return None
    return {"placement": "bottom", "always_visible": False}


def dash_table_tooltip_kwargs(tooltip_data):
    """Extra ``DataTable`` props for cell tooltips."""
    if not TOOLTIPS_ENABLED:
        return {}
    return {"tooltip_data": tooltip_data, "tooltip_duration": None}
