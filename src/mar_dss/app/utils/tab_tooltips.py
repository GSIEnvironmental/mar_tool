"""Helpers for tab nav tooltips with dash-bootstrap-components Tabs."""

import dash_bootstrap_components as dbc


def tab_nav_id(tab_id: str, *, id_prefix: str = "") -> str:
    """Return the ``id`` for ``dbc.Tab`` so ``dbc.Tooltip`` can target the nav link."""
    return f"{id_prefix}tab-{tab_id}" if id_prefix else f"tab-{tab_id}"


def tab_tooltip(
    tab_id: str,
    text: str,
    *,
    id_prefix: str = "",
    placement: str = "bottom",
) -> dbc.Tooltip:
    """Return a Bootstrap tooltip for a tab nav link."""
    return dbc.Tooltip(
        text,
        target=tab_nav_id(tab_id, id_prefix=id_prefix),
        placement=placement,
    )
