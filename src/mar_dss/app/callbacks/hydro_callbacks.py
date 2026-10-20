"""
Hydrogeology tab callbacks for MAR DSS dashboard.
"""

import copy
import math

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback_context, dcc, html, State
import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.utils.excel_table import input_cell_style, label_cell_style
from mar_dss.app.components.hydro_tab import (
    GROUNDWATER_MONTH_NAMES,
    RULE_DEFAULT_SCALAR_ROWS,
    SOIL_PROPERTIES,
    _build_initial_feasibility_traffic_placeholder,
    _rule_def_input_id,
    initial_feasibility_option_label,
    normalize_groundwater_data,
    normalize_stratigraphy_list_from_raw,
    normalize_stratigraphy_recharge_target,
    soil_property_defaults,
)

from mar_dss.rules.geohydro_rules import (
    DEFAULT_AQUITARD_K_MAX_FT_DAY,
    build_confined_theis_xy_plot_dict,
    build_unconfined_mounding_xy_plot_dict,
    infer_dashboard_aquifer_type,
)
from mar_dss.rules.defaults import (
    RULE_DEFAULTS_OVERRIDES_STORAGE_KEY,
    defaults as RULE_DEFAULTS_BASE,
    get_default as rule_defaults_get,
)
from mar_dss.mar import hard_constraints as hc_module
from mar_dss.mar import soft_constraints as sc_module
from mar_dss.mar.options import mar_options
from mar_dss.mar.forward_run import evaluate_and_store_decision_graph
from mar_dss.app.callbacks.analysis_callbacks import get_session_graph, get_graph_inputs
from mar_dss.app.utils.initial_hydro_feasibility import (
    HYDROGEOLOGIC_CONSTRAINT_TYPES,
    evaluate_option_traffic_light,
)
from mar_dss.app.utils.plotly_contour_grid import rectilinear_grid_for_plotly_contour

DEFAULT_MAX_DRY_WELL_DEPTH_FT = 120.0


def _coerce_aquitard_k_ft_day(val):
    """Positive finite K threshold (ft/day) for aquitard classification; else default."""
    if val is not None and str(val).strip() != "":
        try:
            v = float(str(val).strip())
            if math.isfinite(v) and v > 0.0:
                return v
        except (TypeError, ValueError):
            pass
    raw = dash_storage.get_data("aquitard_conductivity_ft_day")
    if raw is not None:
        try:
            v = float(raw)
            if math.isfinite(v) and v > 0.0:
                return v
        except (TypeError, ValueError):
            pass
    return DEFAULT_AQUITARD_K_MAX_FT_DAY


def _render_initial_feasibility_status(status_line: str):
    """Bold green 'Pass' / bold red 'Fail' for Initial Hydrogeologic Feasibility rows."""
    if not status_line:
        return ""
    if status_line == "Pass":
        return html.Span("Pass", className="fw-bold text-success fs-6")
    prefix_pw = "Pass with Warnings - "
    if status_line.startswith(prefix_pw):
        rest = status_line[len(prefix_pw):]
        return html.Span(
            [
                html.Span("Pass", className="fw-bold text-success"),
                html.Span(f" with Warnings - {rest}", className="text-muted"),
            ],
            className="fs-6",
        )
    prefix_fail = "Fail - "
    if status_line.startswith(prefix_fail):
        rest = status_line[len(prefix_fail):]
        return html.Span(
            [
                html.Span("Fail", className="fw-bold text-danger"),
                html.Span(f" - {rest}", className="text-muted"),
            ],
            className="fs-6",
        )
    return html.Span(status_line, className="fs-6 text-muted")


def _initial_feasibility_error_alert(err: BaseException):
    """User-facing alert when feasibility evaluation fails (missing/invalid inputs)."""
    detail = str(err).strip() or type(err).__name__
    return dbc.Alert(
        [
            html.Div(
                "Some input information is not correct or missing.",
                className="fw-semibold mb-2",
            ),
            html.Div(
                [
                    html.Strong("Error: "),
                    html.Code(detail, className="small"),
                ],
                className="mb-0",
            ),
        ],
        color="danger",
        className="mb-0",
    )


def _aquitard_k_input_str(k: float) -> str:
    """Plain-text field display for aquitard K (no scientific spinners); trim trailing zeros."""
    if k is None or not math.isfinite(k) or k <= 0.0:
        k = DEFAULT_AQUITARD_K_MAX_FT_DAY
    text = f"{k:.12f}".rstrip("0").rstrip(".")
    return text if text else str(k)


def _xy_view_empty_figure():
    """No geometry or contours until the user clicks *Show Contour Lines*."""
    fig = go.Figure()
    fig.update_layout(
        title=dict(text="Plan View", x=0.5, xanchor="center", font=dict(size=16)),
        template="plotly_white",
        height=500,
        margin=dict(l=50, r=50, t=60, b=50),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        annotations=[
            dict(
                x=0.5,
                y=0.5,
                xref="paper",
                yref="paper",
                text='Click "Show Contour Lines" to display the plan view with head contours.',
                showarrow=False,
                font=dict(size=14, color="#000"),
                xanchor="center",
                yanchor="middle",
            )
        ],
    )
    return fig


def _extent_for_radial_contour_z(z, x1d, y1d, *, rel_floor=0.01, pad_ratio=0.06):
    """
    Symmetric axis limits centered on the well: zoom to where Z differs from far-field.

    Cells with (Z − Z_min) / (Z_max − Z_min) >= rel_floor set the radial extent; padding is
    added; half-width is clamped between ~2% of the grid radius and the grid edge.
    """
    import numpy as np

    z = np.asarray(z, dtype=float)
    x1d = np.asarray(x1d, dtype=float)
    y1d = np.asarray(y1d, dtype=float)
    grid_half = float(max(np.max(np.abs(x1d)), np.max(np.abs(y1d)), 1e-9))
    zmin = float(np.nanmin(z))
    zmax = float(np.nanmax(z))
    span = zmax - zmin
    if not np.isfinite(span) or span <= 1e-15:
        h = grid_half * (1.0 + pad_ratio)
        return (-h, h), (-h, h)

    Xg, Yg = np.meshgrid(x1d, y1d, indexing="xy")
    rel = (z - zmin) / span
    mask = rel >= rel_floor
    if not np.any(mask):
        h = grid_half * (1.0 + pad_ratio)
        return (-h, h), (-h, h)

    r_mask = float(np.nanmax(np.sqrt(Xg[mask] ** 2 + Yg[mask] ** 2)))
    pad = pad_ratio * max(r_mask, 1e-9)
    half = r_mask + pad
    half_min = max(0.02 * grid_half, 1.0)
    half = float(np.clip(half, half_min, grid_half * (1.0 + pad_ratio)))
    return (-half, half), (-half, half)


def _extent_padded_square_from_axes(xi, yi, *, pad_ratio=0.04):
    """
    Axis limits framing the full 1‑D coordinate span (square view with equal scale).

    Use for plots where `_extent_for_radial_contour_z` is misleading — e.g. unconfined
    mound + regional gradient: the tilt breaks radial symmetry so the radial mask can
    collapse to roughly one quadrant.
    """
    import numpy as np

    x1 = np.asarray(xi, dtype=float).ravel()
    y1 = np.asarray(yi, dtype=float).ravel()
    xm = float(np.min(x1))
    xM = float(np.max(x1))
    ym = float(np.min(y1))
    yM = float(np.max(y1))
    span = float(max(xM - xm, yM - ym, 1.0))
    pad = float(pad_ratio) * span
    cx = 0.5 * (xm + xM)
    cy = 0.5 * (ym + yM)
    half = max(xM - xm, yM - ym) * 0.5 + pad
    return (cx - half, cx + half), (cy - half, cy + half)


# Regional saturated-zone slope (dh/ds) along XY local +x: downstream is +x; head falls downstream.
XY_VIEW_BACKGROUND_HYDRAULIC_GRADIENT = 0.02  # 2% (ft/ft)


def _footprint_corners(half_length, half_width, rotation_deg):
    """Closed polygon for the horizontal-extension footprint (local x = length, y = width)."""
    import numpy as np

    hl = float(half_length)
    hw = float(half_width)
    local = np.array(
        [
            [-hl, -hw],
            [hl, -hw],
            [hl, hw],
            [-hl, hw],
            [-hl, -hw],
        ],
        dtype=float,
    )
    ang = np.radians(float(rotation_deg))
    cos_a, sin_a = np.cos(ang), np.sin(ang)
    x_w = cos_a * local[:, 0] - sin_a * local[:, 1]
    y_w = sin_a * local[:, 0] + cos_a * local[:, 1]
    return x_w, y_w


def _axis_ranges_for_footprint(half_length, half_width, rotation_deg, *, pad_ratio=0.06):
    """Axis limits that frame the rotated length × width footprint."""
    import numpy as np

    x_c, y_c = _footprint_corners(half_length, half_width, rotation_deg)
    x_min, x_max = float(np.min(x_c)), float(np.max(x_c))
    y_min, y_max = float(np.min(y_c)), float(np.max(y_c))
    pad_x = pad_ratio * max(x_max - x_min, 1.0)
    pad_y = pad_ratio * max(y_max - y_min, 1.0)
    return (x_min - pad_x, x_max + pad_x), (y_min - pad_y, y_max + pad_y)


def _mask_z_outside_footprint(x_plot, y_plot, z_plot, half_length, half_width, rotation_deg):
    """NaN-out contour samples outside the rotated MAR footprint box."""
    import numpy as np

    z = np.asarray(z_plot, dtype=float).copy()
    x1d = np.asarray(x_plot, dtype=float).ravel()
    y1d = np.asarray(y_plot, dtype=float).ravel()
    if z.ndim == 1:
        if z.size != x1d.size * y1d.size:
            return z
        z = z.reshape(len(y1d), len(x1d))
    X, Y = np.meshgrid(x1d, y1d, indexing="xy")
    ang = np.radians(float(rotation_deg))
    cos_a, sin_a = np.cos(ang), np.sin(ang)
    x_loc = cos_a * X + sin_a * Y
    y_loc = -sin_a * X + cos_a * Y
    hl = float(half_length)
    hw = float(half_width)
    outside = (np.abs(x_loc) > hl + 1e-9) | (np.abs(y_loc) > hw + 1e-9)
    z[outside] = np.nan
    return z


def _add_footprint_outline(fig, half_length, half_width, rotation_deg):
    """Draw the rotated horizontal-extension rectangle on the XY plan view."""
    x_c, y_c = _footprint_corners(half_length, half_width, rotation_deg)
    fig.add_trace(
        go.Scatter(
            x=x_c,
            y=y_c,
            mode="lines",
            line=dict(color="#212529", width=2),
            name="MAR footprint",
            hoverinfo="skip",
        )
    )


def _prepare_contour_axes(
    x1d,
    y1d,
    z,
    rotation_deg,
    *,
    half_length,
    half_width,
    n_boost=96,
):
    """
    Rotate a rectilinear contour grid, resample for Plotly, and clip to the footprint.
    """
    import numpy as np

    z = np.asarray(z, dtype=float)
    x1d = np.asarray(x1d, dtype=float)
    y1d = np.asarray(y1d, dtype=float)
    if abs(float(rotation_deg)) < 1e-9:
        xp, yp, zp = x1d, y1d, z
    else:
        Xg, Yg = np.meshgrid(x1d, y1d, indexing="xy")
        ang = np.radians(float(rotation_deg))
        cos_a, sin_a = np.cos(ang), np.sin(ang)
        Xr = cos_a * Xg - sin_a * Yg
        Yr = sin_a * Xg + cos_a * Yg
        xp, yp, zp = rectilinear_grid_for_plotly_contour(Xr, Yr, z, n_boost=n_boost)

    zp = _mask_z_outside_footprint(xp, yp, zp, half_length, half_width, rotation_deg)
    return xp, yp, zp


def _prepare_contour_from_mesh(
    x_mesh,
    y_mesh,
    z,
    rotation_deg,
    *,
    half_length,
    half_width,
    n_boost=96,
):
    """Rotate a 2-D mesh grid, resample for Plotly, and clip to the footprint."""
    import numpy as np

    z = np.asarray(z, dtype=float)
    xm = np.asarray(x_mesh, dtype=float)
    ym = np.asarray(y_mesh, dtype=float)
    if abs(float(rotation_deg)) < 1e-9:
        Xg, Yg = xm, ym
    else:
        ang = np.radians(float(rotation_deg))
        cos_a, sin_a = np.cos(ang), np.sin(ang)
        Xg = cos_a * xm - sin_a * ym
        Yg = sin_a * xm + cos_a * ym
    xi, yi, zi = rectilinear_grid_for_plotly_contour(Xg, Yg, z, n_boost=n_boost)
    zi = _mask_z_outside_footprint(xi, yi, zi, half_length, half_width, rotation_deg)
    return xi, yi, zi


def _xy_view_contour_error_alert(detail):
    """User-facing alert when Plan View contour generation fails."""
    msg = str(detail).strip() if detail is not None else ""
    if not msg:
        msg = "unknown error"
    return dbc.Alert(
        [
            html.Div(
                "Could not show contour lines. Some input information may be "
                "incorrect or missing.",
                className="fw-semibold mb-2",
            ),
            html.Div(
                [
                    html.Strong("Error: "),
                    html.Code(msg, className="small"),
                ],
                className="mb-0",
            ),
        ],
        color="danger",
        className="mb-0",
    )


def _xy_view_contour_warning_alert(detail):
    """Non-fatal notice (e.g. fallback contour method)."""
    msg = str(detail).strip() if detail is not None else ""
    if not msg:
        return html.Div()
    return dbc.Alert(
        [
            html.Div(msg, className="mb-0 small"),
        ],
        color="warning",
        className="mb-0",
    )


def _add_confined_theis_contour_to_figure(
    fig,
    strat_in,
    half_length,
    half_width,
    *,
    rotation_deg=0.0,
    n_clicks=0,
):
    """Add confined Theis + regional-gradient contour clipped to the footprint.

    Returns ``(fig, ok, error_message)``.
    """
    import numpy as np

    theis_pack = build_confined_theis_xy_plot_dict(
        strat_in,
        half_length,
        half_width,
    )
    if not theis_pack.get("ok"):
        err = theis_pack.get("error", "Could not build confined Theis contours.")
        return fig, False, err

    Z = np.asarray(theis_pack["drawdown_ft"], dtype=float)
    x1d = np.asarray(theis_pack["x"], dtype=float)
    y1d = np.asarray(theis_pack["y"], dtype=float)
    Xg, _Yg = np.meshgrid(x1d, y1d, indexing="xy")
    Z_background = -XY_VIEW_BACKGROUND_HYDRAULIC_GRADIENT * Xg
    Z = Z + Z_background
    xp, yp, zp = _prepare_contour_axes(
        x1d,
        y1d,
        Z,
        rotation_deg,
        half_length=half_length,
        half_width=half_width,
    )
    fig.add_trace(
        go.Contour(
            x=xp,
            y=yp,
            z=zp,
            colorscale="Jet",
            name="Mound + 2% regional gradient",
            colorbar=dict(title="Mound + gradient (ft)"),
            opacity=0.82,
            contours=dict(showlines=True, coloring="fill"),
            hovertemplate=(
                "<b>Theis + regional gradient</b><br>%{z:.2f} ft<br>"
                "x=%{x:.1f} ft, y=%{y:.1f} ft<extra></extra>"
            ),
            uirevision=str(n_clicks or 0),
        )
    )
    return fig, True, None

def setup_hydro_callbacks(app):
    """Set up all hydrogeology-related callbacks."""

    @app.callback(
        Output("initial-feasibility-help-modal", "is_open"),
        [
            Input("initial-feasibility-help-btn", "n_clicks"),
            Input("initial-feasibility-help-close-btn", "n_clicks"),
        ],
        State("initial-feasibility-help-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_initial_feasibility_help_modal(open_clicks, close_clicks, is_open):
        """Open or close the Initial Hydrogeologic Feasibility help popup."""
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger == "initial-feasibility-help-btn":
            return True
        if trigger == "initial-feasibility-help-close-btn":
            return False
        return bool(is_open)

    @app.callback(
        Output("horizontal-extension-help-modal", "is_open"),
        [
            Input("horizontal-extension-help-btn", "n_clicks"),
            Input("horizontal-extension-help-close-btn", "n_clicks"),
        ],
        State("horizontal-extension-help-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_horizontal_extension_help_modal(open_clicks, close_clicks, is_open):
        """Open or close the Horizontal Extent Configuration help popup."""
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger == "horizontal-extension-help-btn":
            return True
        if trigger == "horizontal-extension-help-close-btn":
            return False
        return bool(is_open)

    @app.callback(
        Output("recharge-mound-outputs-help-modal", "is_open"),
        [
            Input("recharge-mound-outputs-help-btn", "n_clicks"),
            Input("recharge-mound-outputs-help-close-btn", "n_clicks"),
        ],
        State("recharge-mound-outputs-help-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_recharge_mound_outputs_help_modal(open_clicks, close_clicks, is_open):
        """Open or close the Recharge Mound Outputs help popup."""
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger == "recharge-mound-outputs-help-btn":
            return True
        if trigger == "recharge-mound-outputs-help-close-btn":
            return False
        return bool(is_open)

    @app.callback(
        Output("recharge-mound-outputs-collapse", "is_open"),
        Input("view-recharge-mound-outputs-check", "value"),
        prevent_initial_call=True,
    )
    def toggle_recharge_mound_outputs(view_mound):
        """Show or hide Recharge Mound Outputs when the view checkbox changes."""
        checked = bool(view_mound)
        dash_storage.set_data("view_recharge_mound_outputs", checked)
        return checked

    @app.callback(
        Output("groundwater-level-help-modal", "is_open"),
        [
            Input("groundwater-level-help-btn", "n_clicks"),
            Input("groundwater-level-help-close-btn", "n_clicks"),
        ],
        State("groundwater-level-help-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_groundwater_level_help_modal(open_clicks, close_clicks, is_open):
        """Open or close the Groundwater Level Configuration help popup."""
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger == "groundwater-level-help-btn":
            return True
        if trigger == "groundwater-level-help-close-btn":
            return False
        return bool(is_open)

    @app.callback(
        Output("default-parameters-help-modal", "is_open"),
        [
            Input("default-parameters-help-btn", "n_clicks"),
            Input("default-parameters-help-close-btn", "n_clicks"),
        ],
        State("default-parameters-help-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_default_parameters_help_modal(open_clicks, close_clicks, is_open):
        """Open or close the (3.2) Default Parameters help popup."""
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger == "default-parameters-help-btn":
            return True
        if trigger == "default-parameters-help-close-btn":
            return False
        return bool(is_open)

    # Persist inferred aquifer type (no manual aquifer-type control)
    @app.callback(
        Output("aq-type-inferred-store", "data"),
        [
            Input("stratigraphy-data-store", "data"),
            Input("groundwater-data-store", "data"),
            Input("ground-surface-elevation", "value"),
            Input("aquitard-conductivity-input", "value"),
        ],
        prevent_initial_call=False,
    )
    def refresh_inferred_aquifer_type(strat, gw, gs_elev, aq_k_input):
        """Infer confined vs unconfined from stratigraphy + WT + ground surface."""
        strat = strat if strat is not None else dash_storage.get_data("stratigraphy_data")
        gw = gw if gw is not None else dash_storage.get_data("groundwater_data")
        if gs_elev is None:
            gs_elev = dash_storage.get_data("ground_surface_elevation")
        aq_k = _coerce_aquitard_k_ft_day(aq_k_input)
        inferred = infer_dashboard_aquifer_type(
            strat or [],
            gw or [],
            gs_elev,
            aquitard_k_max_ft_day=aq_k,
        )
        dash_storage.set_data("aq_type", inferred)
        return inferred

    # Callback to synchronize geometry tabs with view tabs
    @app.callback(
        Output("view-tabs", "active_tab"),
        [Input("geometry-tabs", "active_tab")],
        prevent_initial_call=False
    )
    def sync_view_tabs_with_geometry_tabs(active_geometry_tab):
        """Synchronize view tabs based on geometry tab selection."""
        # Map geometry tabs to view tabs
        tab_mapping = {
            "stratigraphy-tab": "stratigraphy-cross-section",
            "groundwater-level-tab": "available-mar-storage",
        }
        
        # Return the corresponding view tab, or default to stratigraphy-cross-section
        return tab_mapping.get(active_geometry_tab, "stratigraphy-cross-section")

    @app.callback(
        Output("confined-aquifer-head-input", "value"),
        [
            Input("confined-aquifer-head-input", "n_blur"),
            Input("confined-aquifer-head-input", "n_submit"),
            Input("confined-aquifer-head-input", "id"),
        ],
        State("confined-aquifer-head-input", "value"),
        prevent_initial_call=False,
    )
    def handle_confined_aquifer_head_input(n_blur, n_submit, component_id, value):
        """Persist confined aquifer head (ft) for dry-well feasibility; empty clears stored value."""
        ctx = dash.callback_context

        if not ctx.triggered:
            stored = dash_storage.get_data("confined_aquifer_head_ft")
            if stored is None:
                return ""
            try:
                return float(stored)
            except (TypeError, ValueError):
                return ""

        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1] if ctx.triggered else ""

        if trigger_prop == "id":
            stored = dash_storage.get_data("confined_aquifer_head_ft")
            if stored is None:
                return ""
            try:
                return float(stored)
            except (TypeError, ValueError):
                return ""

        if value is None or str(value).strip() == "":
            dash_storage.set_data("confined_aquifer_head_ft", None)
            return ""

        try:
            fv = float(str(value).strip())
            if not math.isfinite(fv):
                dash_storage.set_data("confined_aquifer_head_ft", None)
                return ""
        except (ValueError, TypeError):
            dash_storage.set_data("confined_aquifer_head_ft", None)
            return ""

        dash_storage.set_data("confined_aquifer_head_ft", fv)
        return fv

    @app.callback(
        Output("max-dry-well-depth-input", "value"),
        [
            Input("max-dry-well-depth-input", "n_blur"),
            Input("max-dry-well-depth-input", "n_submit"),
            Input("max-dry-well-depth-input", "id"),
        ],
        State("max-dry-well-depth-input", "value"),
        prevent_initial_call=False,
    )
    def handle_max_dry_well_depth_input(n_blur, n_submit, component_id, value):
        """Persist maximum dry well depth (ft); default 120 ft when unset or invalid."""
        ctx = dash.callback_context

        def _load_or_default():
            stored = dash_storage.get_data("max_dry_well_depth_ft")
            if stored is not None:
                try:
                    v = float(stored)
                    if math.isfinite(v) and v > 0:
                        dash_storage.set_data("max_dry_well_depth_ft", v)
                        return v
                except (TypeError, ValueError):
                    pass
            dash_storage.set_data(
                "max_dry_well_depth_ft", DEFAULT_MAX_DRY_WELL_DEPTH_FT
            )
            return DEFAULT_MAX_DRY_WELL_DEPTH_FT

        if not ctx.triggered:
            return _load_or_default()

        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1] if ctx.triggered else ""

        if trigger_prop == "id":
            return _load_or_default()

        if value is None or str(value).strip() == "":
            dash_storage.set_data(
                "max_dry_well_depth_ft", DEFAULT_MAX_DRY_WELL_DEPTH_FT
            )
            return DEFAULT_MAX_DRY_WELL_DEPTH_FT

        try:
            fv = float(str(value).strip())
            if not math.isfinite(fv) or fv <= 0:
                dash_storage.set_data(
                    "max_dry_well_depth_ft", DEFAULT_MAX_DRY_WELL_DEPTH_FT
                )
                return DEFAULT_MAX_DRY_WELL_DEPTH_FT
        except (ValueError, TypeError):
            dash_storage.set_data(
                "max_dry_well_depth_ft", DEFAULT_MAX_DRY_WELL_DEPTH_FT
            )
            return DEFAULT_MAX_DRY_WELL_DEPTH_FT

        dash_storage.set_data("max_dry_well_depth_ft", fv)
        return fv

    @app.callback(
        Output("aquitard-conductivity-input", "value"),
        [
            Input("aquitard-conductivity-input", "n_blur"),
            Input("aquitard-conductivity-input", "n_submit"),
            Input("aquitard-conductivity-input", "id"),
        ],
        State("aquitard-conductivity-input", "value"),
        prevent_initial_call=False,
    )
    def handle_aquitard_conductivity_input(n_blur, n_submit, component_id, value):
        """Persist aquitard K on blur/submit only so the field can be cleared while editing."""
        ctx = dash.callback_context

        if not ctx.triggered:
            aq = dash_storage.get_data("aquitard_conductivity_ft_day")
            if aq is not None:
                try:
                    aq = float(aq)
                    if math.isfinite(aq) and aq > 0.0:
                        dash_storage.set_data("aquitard_conductivity_ft_day", aq)
                        return _aquitard_k_input_str(aq)
                except (TypeError, ValueError):
                    pass
            dash_storage.set_data(
                "aquitard_conductivity_ft_day", DEFAULT_AQUITARD_K_MAX_FT_DAY
            )
            return _aquitard_k_input_str(DEFAULT_AQUITARD_K_MAX_FT_DAY)

        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1] if ctx.triggered else ""

        if trigger_prop == "id":
            aq = dash_storage.get_data("aquitard_conductivity_ft_day")
            if aq is not None:
                try:
                    aq = float(aq)
                    if math.isfinite(aq) and aq > 0.0:
                        dash_storage.set_data("aquitard_conductivity_ft_day", aq)
                        return _aquitard_k_input_str(aq)
                except (TypeError, ValueError):
                    pass
            dash_storage.set_data(
                "aquitard_conductivity_ft_day", DEFAULT_AQUITARD_K_MAX_FT_DAY
            )
            return _aquitard_k_input_str(DEFAULT_AQUITARD_K_MAX_FT_DAY)

        # Blur or Enter: commit current text from State
        if value is not None and str(value).strip() != "":
            try:
                current = float(str(value).strip())
                if math.isfinite(current) and current > 0.0:
                    dash_storage.set_data("aquitard_conductivity_ft_day", current)
                    return _aquitard_k_input_str(current)
            except (TypeError, ValueError):
                pass

        dash_storage.set_data(
            "aquitard_conductivity_ft_day", DEFAULT_AQUITARD_K_MAX_FT_DAY
        )
        return _aquitard_k_input_str(DEFAULT_AQUITARD_K_MAX_FT_DAY)

    # Persist stratigraphy store → dash_storage (do not Output to the same Store as Input;
    # that pattern is unreliable in Dash). Ping store is only for a legal Output target.
    @app.callback(
        Output("stratigraphy-dash-sync-ping", "data"),
        [Input("stratigraphy-data-store", "data")],
        [State("stratigraphy-dash-sync-ping", "data")],
        prevent_initial_call=True,
    )
    def save_stratigraphy_to_storage(data, prev_ping):
        """Save stratigraphy data to dash_storage when store updates."""
        if data:
            rows = copy.deepcopy(data)
            normalize_stratigraphy_recharge_target(rows)
            dash_storage.set_data("stratigraphy_data", rows)
        n = prev_ping if isinstance(prev_ping, int) else 0
        return n + 1

    @app.callback(
        Output("groundwater-dash-sync-ping", "data"),
        [Input("groundwater-data-store", "data")],
        [State("groundwater-dash-sync-ping", "data")],
        prevent_initial_call=True,
    )
    def save_groundwater_to_storage(data, prev_ping):
        """Save groundwater data to dash_storage when store updates."""
        if data:
            dash_storage.set_data("groundwater_data", copy.deepcopy(data))
        n = prev_ping if isinstance(prev_ping, int) else 0
        return n + 1
    
    # Callback to save ground surface elevation to data storage
    @app.callback(
        Output("ground-surface-elevation", "value"),
        [
            Input("ground-surface-elevation", "value"),
            Input("ground-surface-elevation", "n_blur"),
            Input("ground-surface-elevation", "n_submit"),
            Input("ground-surface-elevation", "id")
        ],
        prevent_initial_call=False
    )
    def handle_ground_surface_elevation_input(value, n_blur, n_submit, component_id):
        """Handle ground surface elevation input and save to data storage."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved value and ensure it's a float, then save it
            elevation = dash_storage.get_data("ground_surface_elevation")
            if elevation is not None:
                try:
                    elevation = float(elevation)
                except (ValueError, TypeError):
                    elevation = 120.0
            else:
                elevation = 120.0
            dash_storage.set_data("ground_surface_elevation", elevation)
            return elevation
        
        # Get the current value and convert to float
        if value is not None:
            try:
                current_value = float(value)
            except (ValueError, TypeError):
                current_value = 120.0
        else:
            current_value = 120.0
        
        # Determine which trigger caused the callback
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1] if ctx.triggered else ""
        
        # Save for all triggers except initial load (ensure it's saved as float)
        if trigger_prop != "id":
            dash_storage.set_data("ground_surface_elevation", current_value)
        
        return current_value
    
    # Callback to save max MAR storage depth to data storage
    @app.callback(
        Output("max-mar-storage-depth", "value"),
        Input("max-mar-storage-depth", "id"),
        prevent_initial_call=False,
    )
    def load_max_mar_storage_depth(_component_id):
        """Restore max MAR storage depth from project storage."""
        depth = dash_storage.get_data("max_mar_storage_depth")
        if depth is not None:
            try:
                depth = float(depth)
            except (ValueError, TypeError):
                depth = 20.0
        else:
            depth = 20.0
        if depth < 0:
            depth = 20.0
        dash_storage.set_data("max_mar_storage_depth", depth)
        return depth

    @app.callback(
        [
            Output("max-mar-storage-depth", "value", allow_duplicate=True),
            Output("max-mar-storage-depth", "invalid"),
            Output("max-mar-storage-depth-feedback", "children"),
        ],
        [
            Input("max-mar-storage-depth", "n_blur"),
            Input("max-mar-storage-depth", "n_submit"),
        ],
        State("max-mar-storage-depth", "value"),
        prevent_initial_call=True,
    )
    def commit_max_mar_storage_depth(_n_blur, _n_submit, raw_value):
        """Commit storage depth on blur/Enter; reject negative values."""
        saved = dash_storage.get_data("max_mar_storage_depth")
        try:
            last_valid = float(saved) if saved is not None else 20.0
        except (ValueError, TypeError):
            last_valid = 20.0
        if last_valid < 0:
            last_valid = 20.0

        if raw_value is None or raw_value == "":
            return last_valid, True, "Enter a number."

        try:
            value = float(raw_value)
        except (ValueError, TypeError):
            return last_valid, True, "Enter a valid number."

        if value < 0:
            return last_valid, True, "Maximum MAR Storage Depth cannot be negative."

        dash_storage.set_data("max_mar_storage_depth", value)
        return value, False, ""
    # Callback to save extension length to data storage
    @app.callback(
        Output("extension-length", "value"),
        [
            Input("extension-length", "value"),
            Input("extension-length", "n_blur"),
            Input("extension-length", "n_submit"),
            Input("extension-length", "id")
        ],
        prevent_initial_call=False
    )
    def handle_extension_length_input(value, n_blur, n_submit, component_id):
        """Handle extension length input and save to data storage."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved value or use default, and save it
            length = dash_storage.get_data("extension_length") or 100.0
            dash_storage.set_data("extension_length", length)
            return length
        
        current_value = value if value is not None else 100.0
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1] if ctx.triggered else ""
        
        if trigger_prop != "id":
            dash_storage.set_data("extension_length", current_value)
        
        return current_value
    
    # Callback to save extension width to data storage
    @app.callback(
        Output("extension-width", "value"),
        [
            Input("extension-width", "value"),
            Input("extension-width", "n_blur"),
            Input("extension-width", "n_submit"),
            Input("extension-width", "id")
        ],
        prevent_initial_call=False
    )
    def handle_extension_width_input(value, n_blur, n_submit, component_id):
        """Handle extension width input and save to data storage."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved value or use default, and save it
            width = dash_storage.get_data("extension_width") or 50.0
            dash_storage.set_data("extension_width", width)
            return width
        
        current_value = value if value is not None else 50.0
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1] if ctx.triggered else ""
        
        if trigger_prop != "id":
            dash_storage.set_data("extension_width", current_value)
        
        return current_value
    
    # Callback to save extension rotation to data storage
    @app.callback(
        Output("extension-rotation", "value"),
        [
            Input("extension-rotation", "value"),
            Input("extension-rotation", "n_blur"),
            Input("extension-rotation", "n_submit"),
            Input("extension-rotation", "id")
        ],
        prevent_initial_call=False
    )
    def handle_extension_rotation_input(value, n_blur, n_submit, component_id):
        """Handle extension rotation input and save to data storage."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved value or use default, and save it
            rotation = dash_storage.get_data("extension_rotation") or 0.0
            dash_storage.set_data("extension_rotation", rotation)
            return rotation
        
        current_value = value if value is not None else 0.0
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1] if ctx.triggered else ""
        
        if trigger_prop != "id":
            dash_storage.set_data("extension_rotation", current_value)
        
        return current_value
    
    @app.callback(
        Output("stratigraphy-table-body", "children"),
        [
            Input("stratigraphy-data-store", "data"),
            Input("stratigraphy-validation-tick", "data"),
        ],
        prevent_initial_call=False
    )
    def update_stratigraphy_table(data, validation_tick):
        """Update the stratigraphy table based on stored data."""
        if not data:
            return []

        tick = validation_tick if validation_tick is not None else 0
        rows = []
        for i, row in enumerate(data):
            # Create checkbox for selection
            checkbox = dbc.Checkbox(
                id={"type": "layer-checkbox", "index": i},
                value=row.get("selected", False),
                className="form-check-input"
            )

            recharge_checkbox = dbc.Checkbox(
                id={"type": "recharge-target-checkbox", "index": i},
                value=bool(row.get("recharge_target", False)),
                className="form-check-input",
            )

            # Create layer dropdown
            layer_dropdown = dbc.Select(
                id={"type": "layer-select", "index": i},
                value=row["layer"],
                options=[{"label": lith, "value": lith} for lith in SOIL_PROPERTIES.keys()],
                size="sm",
                className="table-cell-input-borderless",
            )
            
            # key includes validation tick so rejected edits remount with store values
            thickness_input = dbc.Input(
                id={"type": "thickness-input", "index": i},
                value=row["thickness"],
                type="number",
                min=1e-12,
                step="0.1",
                size="sm",
                debounce=True,
                className="table-cell-input-borderless",
                key=f"thickness-{i}-{tick}",
            )
            
            conductivity_input = dbc.Input(
                id={"type": "conductivity-input", "index": i},
                value=row["conductivity"],
                type="number",
                min=1e-12,
                step="0.001",
                size="sm",
                debounce=True,
                className="table-cell-input-borderless",
                key=f"conductivity-{i}-{tick}",
            )
            
            storage_input = dbc.Input(
                id={"type": "storage-input", "index": i},
                value=row["storage"],
                type="number",
                min=1e-12,
                step="0.000001",
                size="sm",
                debounce=True,
                className="table-cell-input-borderless",
                key=f"storage-{i}-{tick}",
            )
            
            yield_input = dbc.Input(
                id={"type": "yield-input", "index": i},
                value=row["yield"],
                type="number",
                min=1e-12,
                step="0.01",
                size="sm",
                debounce=True,
                className="table-cell-input-borderless",
                key=f"yield-{i}-{tick}",
            )
            
            rows.append(html.Tr([
                html.Td(checkbox, style=input_cell_style()),
                html.Td(layer_dropdown, style=input_cell_style()),
                html.Td(
                    html.Div(
                        recharge_checkbox,
                        className="d-flex justify-content-center align-items-center",
                    ),
                    style=input_cell_style(),
                ),
                html.Td(thickness_input, style=input_cell_style()),
                html.Td(conductivity_input, style=input_cell_style()),
                html.Td(storage_input, style=input_cell_style()),
                html.Td(yield_input, style=input_cell_style()),
            ]))
        
        return rows
    
    @app.callback(
        Output("stratigraphy-data-store", "data"),
        [Input("add-layer-btn", "n_clicks"),
         Input("delete-layer-btn", "n_clicks"),
         Input("move-up-btn", "n_clicks"),
         Input("move-down-btn", "n_clicks")],
        [State("stratigraphy-data-store", "data")],
        prevent_initial_call=True
    )
    def handle_table_actions(add_clicks, delete_clicks, move_up_clicks, move_down_clicks, data):
        """Handle table actions (add, delete, move)."""
        ctx = callback_context
        if not ctx.triggered:
            return data

        # Never mutate the Store's list in place — append/move on a shared reference
        # races with other callbacks and can produce phantom default rows.
        current_data = copy.deepcopy(data or [])

        trig_prop = ctx.triggered[0]["prop_id"]
        tid = getattr(ctx, "triggered_id", None)
        if tid is None and isinstance(trig_prop, str) and ".n_clicks" in trig_prop:
            tid = trig_prop.rsplit(".", 1)[0]

        ac = add_clicks if add_clicks is not None else 0
        dc = delete_clicks if delete_clicks is not None else 0
        muc = move_up_clicks if move_up_clicks is not None else 0
        mdc = move_down_clicks if move_down_clicks is not None else 0

        if tid == "add-layer-btn":
            if ac < 1:
                return data
            new_layer = {
                "layer": "Sand",
                "thickness": 60.0,
                **soil_property_defaults("Sand"),
                "selected": False,
                "recharge_target": False,
            }
            current_data.append(new_layer)

        elif tid == "delete-layer-btn":
            if dc < 1:
                return data
            current_data = [row for row in current_data if not row.get("selected", False)]

        elif tid == "move-up-btn":
            if muc < 1:
                return data
            for i in range(1, len(current_data)):
                if current_data[i].get("selected", False) and not current_data[i - 1].get("selected", False):
                    current_data[i], current_data[i - 1] = current_data[i - 1], current_data[i]

        elif tid == "move-down-btn":
            if mdc < 1:
                return data
            for i in range(len(current_data) - 2, -1, -1):
                if current_data[i].get("selected", False) and not current_data[i + 1].get("selected", False):
                    current_data[i], current_data[i + 1] = current_data[i + 1], current_data[i]
        else:
            return data

        normalize_stratigraphy_recharge_target(current_data)
        return current_data

    @app.callback(
        Output("stratigraphy-data-store", "data", allow_duplicate=True),
        [Input({"type": "recharge-target-checkbox", "index": dash.dependencies.ALL}, "value")],
        [State("stratigraphy-data-store", "data")],
        prevent_initial_call=True,
    )
    def apply_recharge_target_exclusive(rt_values, data):
        """Only one recharge target row; checking one row clears the others."""
        if not data or rt_values is None:
            return dash.no_update
        if len(rt_values) != len(data):
            return dash.no_update

        truths = [bool(v) for v in rt_values]
        idx = None
        if callback_context.triggered:
            try:
                import json as _json

                tid = callback_context.triggered[0]["prop_id"].split(".")[0]
                idx = int(_json.loads(tid)["index"])
            except (ValueError, KeyError, TypeError):
                idx = None

        if idx is not None and 0 <= idx < len(data) and truths[idx]:
            for i, row in enumerate(data):
                row["recharge_target"] = i == idx
            return data

        selected = sum(truths)
        if selected == 1:
            k = truths.index(True)
            for i, row in enumerate(data):
                row["recharge_target"] = i == k
            return data
        if selected == 0:
            normalize_stratigraphy_recharge_target(data)
            return data
        k = truths.index(True)
        for i, row in enumerate(data):
            row["recharge_target"] = i == k
        return data

    @app.callback(
        Output("stratigraphy-data-store", "data", allow_duplicate=True),
        Output("stratigraphy-error-message", "children"),
        Output("stratigraphy-validation-tick", "data"),
        [Input({"type": "layer-checkbox", "index": dash.dependencies.ALL}, "value"),
         Input({"type": "layer-select", "index": dash.dependencies.ALL}, "value"),
         Input({"type": "thickness-input", "index": dash.dependencies.ALL}, "value"),
         Input({"type": "conductivity-input", "index": dash.dependencies.ALL}, "value"),
         Input({"type": "storage-input", "index": dash.dependencies.ALL}, "value"),
         Input({"type": "yield-input", "index": dash.dependencies.ALL}, "value")],
        [
            State("stratigraphy-data-store", "data"),
            State("stratigraphy-validation-tick", "data"),
        ],
        prevent_initial_call=True
    )
    def update_table_data(
        checkbox_values,
        layer_values,
        thickness_values,
        conductivity_values,
        storage_values,
        yield_values,
        data,
        validation_tick,
    ):
        """Update table data when inputs change.

        Changing soil type auto-fills K, Ss, and Sy for that row from SOIL_PROPERTIES
        only when the soil type value actually changes. Manual edits to thickness,
        K, Ss, and Sy are kept afterward.

        Thickness, hydraulic conductivity, specific storage, and specific yield must
        all be numbers greater than zero. Invalid or blank entries are rejected, an
        error alert is shown, and the table remounts with the last valid values.
        """
        tick = validation_tick if validation_tick is not None else 0
        if not data:
            return data, [], tick

        original = data
        data = copy.deepcopy(data)
        errors = []

        numeric_types = {
            "thickness-input": ("thickness", "Thickness"),
            "conductivity-input": ("conductivity", "Hydraulic Conductivity"),
            "storage-input": ("storage", "Specific Storage"),
            "yield-input": ("yield", "Specific Yield"),
        }

        triggered_layer_idx = None
        triggered_numeric_type = None
        triggered_numeric_idx = None
        if callback_context.triggered:
            try:
                import json as _json

                tid = callback_context.triggered[0]["prop_id"].split(".")[0]
                parsed = _json.loads(tid)
                t = parsed.get("type")
                idx = int(parsed["index"])
                if t == "layer-select":
                    triggered_layer_idx = idx
                elif t in numeric_types:
                    triggered_numeric_type = t
                    triggered_numeric_idx = idx
            except (ValueError, KeyError, TypeError):
                pass

        def _apply_positive(raw, field_label, row_num, *, strict):
            """Return float if valid and > 0; None to keep prior store value.

            When *strict* (the cell the user just edited), blank / ≤0 / non-numeric
            values append an error. Non-strict cells ignore blanks (remount noise)
            and only apply when a valid positive number is present.
            """
            blank = raw is None or (isinstance(raw, str) and str(raw).strip() == "")
            if blank:
                if strict:
                    errors.append(
                        f"Row {row_num}: {field_label} must be greater than zero."
                    )
                return None
            try:
                value = float(raw)
            except (TypeError, ValueError):
                if strict:
                    errors.append(
                        f"Row {row_num}: {field_label} must be a number "
                        "greater than zero."
                    )
                return None
            if value <= 0:
                if strict:
                    errors.append(
                        f"Row {row_num}: {field_label} must be greater than zero."
                    )
                return None
            return value

        input_lists = {
            "thickness-input": thickness_values,
            "conductivity-input": conductivity_values,
            "storage-input": storage_values,
            "yield-input": yield_values,
        }

        for i, row in enumerate(data):
            row_num = i + 1
            if i < len(checkbox_values):
                row["selected"] = checkbox_values[i] or False

            old_layer = row.get("layer")
            new_layer = (
                layer_values[i]
                if i < len(layer_values) and layer_values[i] is not None
                else old_layer
            )
            soil_type_changed = (
                triggered_layer_idx == i
                and new_layer is not None
                and new_layer != old_layer
            )

            if new_layer is not None:
                row["layer"] = new_layer

            if soil_type_changed:
                # Thickness still comes from the input; K / Ss / Sy from soil defaults.
                if i < len(thickness_values):
                    parsed = _apply_positive(
                        thickness_values[i],
                        "Thickness",
                        row_num,
                        strict=(
                            triggered_numeric_type == "thickness-input"
                            and triggered_numeric_idx == i
                        ),
                    )
                    if parsed is not None:
                        row["thickness"] = parsed
                props = soil_property_defaults(new_layer)
                row["conductivity"] = props["conductivity"]
                row["storage"] = props["storage"]
                row["yield"] = props["yield"]
                continue

            for type_key, (store_key, label) in numeric_types.items():
                values = input_lists[type_key]
                if i >= len(values):
                    continue
                strict = (
                    triggered_numeric_type == type_key
                    and triggered_numeric_idx == i
                )
                parsed = _apply_positive(
                    values[i], label, row_num, strict=strict
                )
                if parsed is not None:
                    row[store_key] = parsed

        if errors:
            seen = set()
            unique_errors = []
            for msg in errors:
                if msg not in seen:
                    seen.add(msg)
                    unique_errors.append(msg)
            alert = dbc.Alert(
                [
                    html.Strong("Invalid stratigraphy values"),
                    html.P(
                        "All thickness, hydraulic conductivity, specific storage, "
                        "and specific yield values must be greater than zero.",
                        className="mb-2 mt-2",
                    ),
                    html.Ul(
                        [html.Li(msg) for msg in unique_errors],
                        className="mb-0",
                    ),
                ],
                color="danger",
                className="mb-0",
                dismissable=True,
            )
            # Keep last valid store values; bump tick so inputs remount cleaned.
            return dash.no_update, alert, tick + 1

        # Avoid store churn (and remount loops) when nothing actually changed.
        if data == original:
            return dash.no_update, [], tick

        return data, [], tick    
    # Groundwater Level Table Callbacks
    @app.callback(
        Output("groundwater-table-body", "children"),
        Input("groundwater-data-store", "data"),
        Input("constant-groundwater-level-check", "value"),
        prevent_initial_call=False,
    )
    def update_groundwater_table(data, use_constant):
        """Update the groundwater level table based on stored data."""
        rows_data = normalize_groundwater_data(data or [])
        rows_out = []
        for i, row in enumerate(rows_data):
            elevation_input = dbc.Input(
                id={"type": "elevation-input", "index": i},
                value=row["elevation"],
                type="number",
                step="0.1",
                size="sm",
                debounce=True,
                disabled=bool(use_constant) and i != 0,
                className="table-cell-input-borderless",
            )
            rows_out.append(
                html.Tr(
                    [
                        html.Td(
                            row["month"],
                            className="align-middle small text-muted fw-semibold",
                            style=label_cell_style(i),
                        ),
                        html.Td(elevation_input, style=input_cell_style()),
                    ]
                )
            )
        return rows_out

    @app.callback(
        Output("groundwater-data-store", "data"),
        Input({"type": "elevation-input", "index": dash.dependencies.ALL}, "value"),
        Input("constant-groundwater-level-check", "value"),
        State("groundwater-data-store", "data"),
        prevent_initial_call=True,
    )
    def update_groundwater_data(elevation_values, use_constant, data):
        """Update groundwater elevations; months are fixed January–December.

        When the constant-level checkbox is on, January's elevation is applied
        to every month.
        """
        base = normalize_groundwater_data(data or [])
        for i, name in enumerate(GROUNDWATER_MONTH_NAMES):
            if i >= len(base):
                break
            if i < len(elevation_values) and elevation_values[i] is not None:
                try:
                    base[i]["elevation"] = float(elevation_values[i])
                except (TypeError, ValueError):
                    pass
            base[i]["month"] = name

        if use_constant:
            try:
                if elevation_values and elevation_values[0] is not None:
                    jan_val = float(elevation_values[0])
                else:
                    jan_val = float(base[0]["elevation"])
            except (TypeError, ValueError, IndexError):
                jan_val = float(base[0]["elevation"])
            for row in base:
                row["elevation"] = jan_val

        return base
    
    # Groundwater Level Plot Callback
    @app.callback(
        Output("groundwater-plot", "figure"),
        [Input("groundwater-data-store", "data"),
         Input("ground-surface-elevation", "value"),
         Input("max-mar-storage-depth", "value")],
        prevent_initial_call=False
    )
    def update_groundwater_plot(data, ground_elevation, max_storage_depth):
        """Update the groundwater level plot based on table data."""
        
        if not data:
            return go.Figure()
        
        # Convert input values to float in case they're strings (from CSV storage)
        ground_elevation_float = None
        max_storage_depth_float = None
        
        if ground_elevation is not None:
            try:
                ground_elevation_float = float(ground_elevation)
            except (ValueError, TypeError):
                ground_elevation_float = None
        
        if max_storage_depth is not None:
            try:
                max_storage_depth_float = float(max_storage_depth)
            except (ValueError, TypeError):
                max_storage_depth_float = None
        
        # Convert data to DataFrame for easier handling
        df = pd.DataFrame(data)
        
        # Sort by month order
        month_order = ['January', 'February', 'March', 'April', 'May', 'June',
                      'July', 'August', 'September', 'October', 'November', 'December']
        df['month_num'] = df['month'].map({month: i for i, month in enumerate(month_order)})
        df = df.sort_values('month_num')
        
        # Create the plot
        fig = go.Figure()
        
        # Add groundwater elevation line plot
        fig.add_trace(go.Scatter(
            x=df['month'],
            y=df['elevation'],
            mode='lines+markers',
            name='Groundwater Elevation',
            line=dict(color='#1f77b4', width=3),
            marker=dict(size=8, color='#1f77b4'),
            hovertemplate='<b>%{x}</b><br>Elevation: %{y:.1f} ft<extra></extra>'
        ))
        
        # Add filled area between MAR storage and groundwater if both values are provided
        if max_storage_depth_float is not None and ground_elevation_float is not None:
            mar_storage_line = ground_elevation - max_storage_depth
            
            # Create filled area between MAR storage line and groundwater elevation
            # We need to create a polygon that fills the area between the two lines
            months = df['month'].tolist()
            groundwater_elevations = df['elevation'].tolist()
            mar_storage_elevations = [mar_storage_line] * len(months)
            
            # Create the filled area by combining the lines
            fig.add_trace(go.Scatter(
                x=months + months[::-1],  # Forward then reverse for closed polygon
                y=groundwater_elevations + mar_storage_elevations[::-1],  # Combine both lines
                fill='toself',
                fillcolor='rgba(255, 165, 0, 0.3)',  # Orange with transparency
                line=dict(color='rgba(255,255,255,0)'),  # Transparent line
                name='Available MAR Storage',
                hovertemplate='<b>Available MAR Storage Area</b><extra></extra>',
                showlegend=True
            ))
            
            # Add the MAR storage line as a reference
            fig.add_trace(go.Scatter(
                x=months,
                y=mar_storage_elevations,
                mode='lines',
                line=dict(color='red', width=2, dash='dot'),
                name='MAR Storage Limit',
                hovertemplate='<b>%{x}</b><br>MAR Storage Limit: %{y:.1f} ft<extra></extra>',
                showlegend=True
            ))
        
        # Add horizontal lines if values are provided
        if ground_elevation_float is not None:
            # Ground surface elevation line
            fig.add_hline(
                y=ground_elevation_float,
                line_dash="dash",
                line_color="green",
                line_width=2,
                annotation_text=f"Ground Surface: {ground_elevation_float:.1f} ft",
                annotation_position="top right"
            )
        
        if max_storage_depth_float is not None and ground_elevation_float is not None:
            # Maximum MAR storage depth line (from ground surface)
            mar_storage_line = ground_elevation_float - max_storage_depth_float
            fig.add_hline(
                y=mar_storage_line,
                line_dash="dot",
                line_color="red",
                line_width=2,
                annotation_text=f"Max MAR Storage: {mar_storage_line:.1f} ft",
                annotation_position="bottom right"
            )
        
        # Update layout
        fig.update_layout(
            title={
                'text': 'Groundwater Elevation Variation by Month',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 16}
            },
            xaxis_title="Month",
            yaxis_title="Elevation (ft)",
            template="plotly_white",
            height=600,
            margin=dict(l=50, r=50, t=60, b=100),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.15,
                xanchor="center",
                x=0.5
            )
        )
        
        # Add grid
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
        
        return fig
    
    # Stratigraphy Cross Section Plot Callback
    @app.callback(
        Output("stratigraphy-cross-section-plot", "figure"),
        [
            Input("stratigraphy-data-store", "data"),
            Input("groundwater-data-store", "data"),
            Input("ground-surface-elevation", "value"),
        ],
        prevent_initial_call=False
    )
    def update_stratigraphy_cross_section(data, gw_data, gs_elevation):
        """Update the stratigraphy cross-section plot based on table data."""
        if not data:
            return go.Figure()

        def _deepest_gw_depth_bgs(gs_val, groundwater_rows):
            """Depth below ground surface (ft) at minimum monthly WT elevation.

            Minimum water-table **elevation** (lowest head) ⇒ **deepest** water ⇒
            **maximum** depth b.g.s. Aligns with other hydro inference using min WT elev.
            """
            if gs_val is None or not groundwater_rows:
                return None
            try:
                gs_f = float(gs_val)
            except (TypeError, ValueError):
                return None
            elevs = []
            for r in groundwater_rows:
                if not isinstance(r, dict) or r.get("elevation") is None:
                    continue
                try:
                    elevs.append(float(r["elevation"]))
                except (TypeError, ValueError):
                    continue
            if not elevs:
                return None
            min_elev = min(elevs)
            return float(gs_f - min_elev)

        strat_rows = data
        gw_rows = (
            gw_data
            if gw_data is not None
            else dash_storage.get_data("groundwater_data")
        )
        gs_use = gs_elevation
        if gs_use is None:
            gs_use = dash_storage.get_data("ground_surface_elevation")

        gw_depth_ft = _deepest_gw_depth_bgs(gs_use, gw_rows or [])

        # Define colors for different layer types
        layer_colors = {
            "Gravel": "#BDBDBD",      # Light gray (distinct from Other)
            "Sand": "#F4A460",        # Sandy brown
            "Silt": "#C4A574",        # Dusty khaki (distinct from Loam)
            "Loam": "#8FBC8F",        # Soft green-brown (organic-rich loam)
            "Clay": "#A0522D",        # Sienna
            "Other": "#6C757D",       # Mid gray (unspecified / average mix)
        }
        
        # Create the plot
        fig = go.Figure()

        try:
            gs_f = float(gs_use) if gs_use is not None and str(gs_use).strip() != "" else None
        except (TypeError, ValueError):
            gs_f = None

        def _elev_at_depth(depth_ft):
            if gs_f is None:
                return None
            return gs_f - float(depth_ft)

        # Calculate cumulative depths for layering
        cumulative_depth = 0
        layer_names = []
        layer_depths = []
        layer_colors_list = []
        recharge_target_mid_depth = None
        recharge_target_layer_name = None

        for i, row in enumerate(strat_rows):
            layer_name = row["layer"]
            thickness = row["thickness"]
            try:
                thick_f = float(thickness)
            except (TypeError, ValueError):
                thick_f = 0.0

            if row.get("recharge_target") and recharge_target_mid_depth is None:
                recharge_target_mid_depth = cumulative_depth + thick_f / 2.0
                recharge_target_layer_name = layer_name

            top_d = cumulative_depth
            bot_d = cumulative_depth + thick_f
            elev_hover = ""
            if gs_f is not None:
                elev_hover = (
                    f"<br>Elevation: {_elev_at_depth(top_d):.1f} - {_elev_at_depth(bot_d):.1f} ft"
                )

            # Add layer rectangle
            fig.add_trace(go.Scatter(
                x=[0, 1, 1, 0, 0],  # Rectangle coordinates
                y=[
                    top_d,
                    top_d,
                    bot_d,
                    bot_d,
                    top_d,
                ],
                fill='toself',
                fillcolor=layer_colors.get(layer_name, "#808080"),  # Default gray if layer not found
                line=dict(color='black', width=1),
                name=layer_name,
                hovertemplate=(
                    f"<b>{layer_name}</b><br>Thickness: {thick_f:.1f} ft<br>"
                    f"Depth: {top_d:.1f} - {bot_d:.1f} ft bgs{elev_hover}<extra></extra>"
                ),
                showlegend=True
            ))
            
            # Add layer label in the middle of the layer
            fig.add_annotation(
                x=0.5,
                y=cumulative_depth + thick_f / 2.0,
                text=layer_name,
                showarrow=False,
                font=dict(size=12, color="black")
            )

            cumulative_depth += thick_f

        if recharge_target_mid_depth is None and strat_rows:
            try:
                t0 = float(strat_rows[0].get("thickness", 0.0))
            except (TypeError, ValueError):
                t0 = 0.0
            recharge_target_mid_depth = t0 / 2.0
            recharge_target_layer_name = strat_rows[0].get("layer", "")

        total_depth = cumulative_depth
        wt_depth_plot = gw_depth_ft if gw_depth_ft is not None else total_depth
        if wt_depth_plot < 0:
            wt_depth_plot = 0.0

        fig.add_trace(
            go.Scatter(
                x=[0, 1],
                y=[wt_depth_plot, wt_depth_plot],
                mode="lines",
                name=(
                    "GW at min WT elev "
                    + (f'({gw_depth_ft:.1f} ft bgs)' if gw_depth_ft is not None else "(profile bottom)")
                ),
                line=dict(color="#0d6efd", width=2, dash="dash"),
                hovertemplate=(
                    "<b>Water table (min monthly elev)</b><br>"
                    f"Depth: {wt_depth_plot:.1f} ft bgs"
                    + (
                        f"<br>Elevation: {_elev_at_depth(wt_depth_plot):.1f} ft"
                        if gs_f is not None
                        else ""
                    )
                    + "<extra></extra>"
                ),
            )
        )

        if recharge_target_mid_depth is not None:
            elev_mid = _elev_at_depth(recharge_target_mid_depth)
            elev_hover = (
                f"<br>Elevation at midpoint: {elev_mid:.1f} ft" if elev_mid is not None else ""
            )
            fig.add_trace(
                go.Scatter(
                    x=[0.18],
                    y=[recharge_target_mid_depth],
                    mode="markers",
                    name="Target Recharge Layer",
                    marker=dict(
                        symbol="circle",
                        size=18,
                        color="#22c55e",
                        line=dict(width=2, color="#15803d"),
                    ),
                    hovertemplate=(
                        "<b>Target Recharge Layer</b><br>"
                        f"{recharge_target_layer_name or ''}<br>"
                        f"Depth at layer midpoint: {recharge_target_mid_depth:.1f} ft bgs"
                        f"{elev_hover}"
                        "<extra></extra>"
                    ),
                    showlegend=True,
                )
            )

        # Depth increases downward (0 at top). Elevation = GS − depth (GS at top).
        y_depth_range = [max(total_depth, 0.0), 0.0]
        layout_kwargs = dict(
            title={
                "text": "Stratigraphy Cross Section",
                "x": 0.5,
                "xanchor": "center",
                "font": {"size": 16},
            },
            xaxis_title="",
            yaxis=dict(
                title="Depth (ft)",
                range=y_depth_range,
                showgrid=True,
                gridwidth=1,
                gridcolor="lightgray",
                zeroline=False,
            ),
            template="plotly_white",
            height=500,
            margin=dict(l=60, r=70, t=60, b=50),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.1,
                xanchor="center",
                x=0.5,
            ),
            xaxis=dict(
                showgrid=False,
                showticklabels=False,
                range=[-0.1, 1.1],
            ),
        )

        if gs_f is not None:
            elev_bottom = gs_f - max(total_depth, 0.0)
            elev_top = gs_f
            # Invisible anchor so Plotly always draws the secondary axis
            fig.add_trace(
                go.Scatter(
                    x=[None],
                    y=[elev_top],
                    yaxis="y2",
                    mode="markers",
                    marker=dict(opacity=0),
                    showlegend=False,
                    hoverinfo="skip",
                )
            )
            layout_kwargs["yaxis2"] = dict(
                title="Elevation (ft)",
                overlaying="y",
                side="right",
                range=[elev_bottom, elev_top],
                showgrid=False,
                zeroline=False,
            )

        fig.update_layout(**layout_kwargs)

        return fig

    @app.callback(
        Output("xy-view-show-contours-btn", "n_clicks"),
        Input("stratigraphy-data-store", "data"),
        prevent_initial_call=True,
    )
    def reset_xy_view_contours_on_stratigraphy_change(_strat):
        """CSV / stratigraphy reload: contours are stale until the user clicks Show Contour Lines again."""
        return 0

    # XY View Plot Callback
    @app.callback(
        [
            Output("xy-view-plot", "figure"),
            Output("xy-view-contour-message", "children"),
        ],
        [
            Input("extension-length", "value"),
            Input("extension-width", "value"),
            Input("extension-rotation", "value"),
            Input("xy-view-show-contours-btn", "n_clicks"),
            Input("stratigraphy-data-store", "data"),
        ],
        prevent_initial_call=False,
    )
    def update_xy_view_plot(length, width, rotation, n_clicks, _strat_data):
        """Update the XY view plot with rectangle and contour lines."""
        # Rely on ``reset_xy_view_contours_on_stratigraphy_change`` zeroing clicks when stratigraphy/
        # CSV reloads matches so we do not wipe a valid redraw on the same tick as the Show button.
        if not n_clicks:
            return _xy_view_empty_figure(), html.Div()

        import traceback

        import numpy as np

        try:
            # Default values if inputs are None, and convert to float
            if length is None:
                length = 100.0
            else:
                try:
                    length = float(length)
                except (ValueError, TypeError):
                    length = 100.0

            if width is None:
                width = 50.0
            else:
                try:
                    width = float(width)
                except (ValueError, TypeError):
                    width = 50.0

            if rotation is None:
                rotation = 0.0
            else:
                try:
                    rotation = float(rotation)
                except (ValueError, TypeError):
                    rotation = 0.0

            if length <= 0 or width <= 0:
                return (
                    _xy_view_empty_figure(),
                    _xy_view_contour_error_alert(
                        "Length and width must be positive values."
                    ),
                )

            aq_type_raw = dash_storage.get_data("aq_type") or "unconfined"
            aq_type_l = str(aq_type_raw).strip().lower()
            is_confined = aq_type_l == "confined"

            # Create the plot
            fig = go.Figure()
            contour_style = "theis" if is_confined else "hantush"
            message = html.Div()

            half_length = length / 2
            half_width = width / 2
            footprint_x_range, footprint_y_range = _axis_ranges_for_footprint(
                half_length, half_width, rotation
            )

            if is_confined:
                strat_in = dash_storage.get_data("stratigraphy_data")
                fig, contour_ok, contour_err = _add_confined_theis_contour_to_figure(
                    fig,
                    strat_in,
                    half_length,
                    half_width,
                    rotation_deg=rotation,
                    n_clicks=n_clicks,
                )
                if not contour_ok:
                    message = _xy_view_contour_error_alert(contour_err)
            else:
                # unconfined aquifer
                strat_in = dash_storage.get_data("stratigraphy_data")
                gw_rows = normalize_groundwater_data(
                    dash_storage.get_data("groundwater_data") or []
                )
                gs_elev = dash_storage.get_data("ground_surface_elevation")

                graph = get_session_graph()
                if graph is None:
                    return (
                        _xy_view_empty_figure(),
                        _xy_view_contour_error_alert(
                            "Decision graph is not available."
                        ),
                    )
                inputs = get_graph_inputs()
                evaluate_and_store_decision_graph(graph, inputs)
                node_values = graph.get_node_values()
                design_sizing = node_values.get("design_sizing")

                if design_sizing is not None:
                    mound_pack = build_unconfined_mounding_xy_plot_dict(
                        strat_in,
                        design_sizing,
                        half_length,
                        half_width,
                        gw_rows,
                        gs_elev,
                    )
                    if mound_pack.get("ok"):
                        Z = np.asarray(mound_pack["drawdown_ft"], dtype=float)
                        Xmesh = np.asarray(mound_pack["x_grid"], dtype=float)
                        Ymesh = np.asarray(mound_pack["y_grid"], dtype=float)
                        Z_background = (
                            -XY_VIEW_BACKGROUND_HYDRAULIC_GRADIENT * Xmesh
                        )
                        Z = Z + Z_background
                        xi, yi, Zi = _prepare_contour_from_mesh(
                            Xmesh,
                            Ymesh,
                            Z,
                            rotation,
                            half_length=half_length,
                            half_width=half_width,
                        )
                        fig.add_trace(
                            go.Contour(
                                x=xi,
                                y=yi,
                                z=Zi,
                                colorscale="Jet",
                                name="Unconfined mound + 2% regional gradient",
                                colorbar=dict(title="Mound + gradient (ft)"),
                                opacity=0.82,
                                contours=dict(showlines=True, coloring="fill"),
                                hovertemplate=(
                                    "<b>Hantush mound + regional gradient</b><br>"
                                    "%{z:.2f} ft<br>"
                                    "x=%{x:.1f} ft, y=%{y:.1f} ft<extra></extra>"
                                ),
                                uirevision=str(n_clicks or 0),
                            )
                        )
                    else:
                        message = _xy_view_contour_error_alert(
                            mound_pack.get(
                                "error",
                                "Could not build unconfined mound contours.",
                            )
                        )
                else:
                    # Surface recharge not possible — fall back to confined Theis contours.
                    contour_style = "theis"
                    fig, contour_ok, contour_err = _add_confined_theis_contour_to_figure(
                        fig,
                        strat_in,
                        half_length,
                        half_width,
                        rotation_deg=rotation,
                        n_clicks=n_clicks,
                    )
                    if contour_ok:
                        message = _xy_view_contour_warning_alert(
                            "Unconfined design sizing is not available "
                            "(surface recharge may not be feasible). "
                            "Showing confined Theis contours instead."
                        )
                    else:
                        message = _xy_view_contour_error_alert(
                            contour_err
                            or (
                                "Unconfined design sizing is not available, and "
                                "confined Theis contours also failed."
                            )
                        )

            _add_footprint_outline(fig, half_length, half_width, rotation)

            # Update layout
            xy_title = (
                "Plan View — confined Theis mound"
                if contour_style == "theis"
                else "Plan View — unconfined Hantush mound"
            )
            xr, yr = footprint_x_range, footprint_y_range
            fig.update_layout(
                title={
                    "text": xy_title,
                    "x": 0.5,
                    "xanchor": "center",
                    "font": {"size": 16},
                },
                xaxis_title="Distance (ft)",
                yaxis_title="Distance (ft)",
                template="plotly_white",
                height=500,
                margin=dict(l=50, r=50, t=60, b=50),
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.1,
                    xanchor="center",
                    x=0.5,
                ),
                xaxis=dict(
                    scaleanchor="y",
                    scaleratio=1,
                    range=list(xr),
                    autorange=False,
                ),
                yaxis=dict(
                    scaleanchor="x",
                    scaleratio=1,
                    range=list(yr),
                    autorange=False,
                ),
            )

            return fig, message

        except Exception as err:
            traceback.print_exc()
            return _xy_view_empty_figure(), _xy_view_contour_error_alert(err)
    _TRAFFIC_DOT = {"green": "#198754", "orange": "#fd7e14", "red": "#dc3545"}

    @app.callback(
        Output("initial-feasibility-traffic-output", "children"),
        [
            Input("check-initial-feasibility-btn", "n_clicks"),
            Input("stratigraphy-data-store", "data"),
        ],
        [
            State("groundwater-data-store", "data"),
            State("ground-surface-elevation", "value"),
            State("aquitard-conductivity-input", "value"),
        ],
        prevent_initial_call=True,
        running=[
            (Output("check-initial-feasibility-btn", "disabled"), True, False),
            (
                Output("check-initial-feasibility-btn", "children"),
                [
                    dbc.Spinner(size="sm", color="light", spinner_class_name="me-2"),
                    "Checking…",
                ],
                "Check Initial Feasibility",
            ),
        ],
    )
    def update_initial_feasibility_traffic(
        _n_clicks,
        strat_store,
        gw_store,
        gs_elev,
        aq_k_input,
    ):
        """Evaluate feasibility on button click; reset to pending when stratigraphy changes (e.g. new CSV)."""
        ctx = callback_context
        tid = getattr(ctx, "triggered_id", None)
        if tid is None and ctx.triggered:
            tid = ctx.triggered[0]["prop_id"].split(".")[0]
        if isinstance(tid, str) and tid == "stratigraphy-data-store":
            return _build_initial_feasibility_traffic_placeholder()

        try:
            if strat_store is not None:
                rows = normalize_stratigraphy_list_from_raw(strat_store)
                if rows is not None:
                    normalize_stratigraphy_recharge_target(rows)
                    dash_storage.set_data("stratigraphy_data", rows)
            if gw_store is not None:
                dash_storage.set_data("groundwater_data", gw_store)
            if gs_elev is not None and str(gs_elev).strip() != "":
                try:
                    dash_storage.set_data(
                        "ground_surface_elevation", float(gs_elev)
                    )
                except (TypeError, ValueError):
                    pass
            aq_k = _coerce_aquitard_k_ft_day(aq_k_input)
            dash_storage.set_data("aquitard_conductivity_ft_day", aq_k)

            inputs = get_graph_inputs()
            graph = get_session_graph()
            if graph is None:
                return _initial_feasibility_error_alert(
                    ValueError("Decision graph is not available.")
                )
            evaluate_and_store_decision_graph(graph, inputs)

            cols_out = []
            for i, option in enumerate(mar_options()):
                color, status_line = evaluate_option_traffic_light(
                    option,
                    hc_module.hard_constraints,
                    sc_module.soft_constraints,
                    allowed_types=HYDROGEOLOGIC_CONSTRAINT_TYPES,
                )
                dot = _TRAFFIC_DOT[color]
                name_cls = (
                    "fw-semibold fs-5 text-success"
                    if color in ("green", "orange")
                    else "fw-semibold fs-5 text-danger"
                )
                col_border = (
                    "mb-2 mb-sm-3 mb-md-0 border-start border-secondary border-opacity-25 ps-md-3"
                    if i
                    else "mb-2 mb-sm-3 mb-md-0"
                )
                cols_out.append(
                    dbc.Col(
                        dbc.Row(
                            [
                                dbc.Col(
                                    html.Span(
                                        className="rounded-circle d-inline-block flex-shrink-0",
                                        style={
                                            "width": "22px",
                                            "height": "22px",
                                            "backgroundColor": dot,
                                            "verticalAlign": "middle",
                                        },
                                    ),
                                    width="auto",
                                    className="d-flex align-items-start pt-2",
                                ),
                                dbc.Col(
                                    [
                                        html.Div(
                                            initial_feasibility_option_label(
                                                option.name
                                            ),
                                            className=name_cls,
                                        ),
                                        html.Div(
                                            _render_initial_feasibility_status(
                                                status_line
                                            ),
                                            className="fs-6",
                                        ),
                                    ],
                                    className="ps-0 min-w-0",
                                ),
                            ],
                            className="g-2 align-items-start mx-0",
                        ),
                        xs=12,
                        sm=6,
                        md=4,
                        className=col_border,
                    )
                )

            return html.Div(
                dbc.Row(
                    cols_out,
                    className="g-2 g-md-3 align-items-start justify-content-lg-between",
                ),
                className="initial-feasibility-traffic initial-feasibility-traffic--evaluated mt-1",
            )
        except Exception as err:
            import traceback

            traceback.print_exc()
            return _initial_feasibility_error_alert(err)

    # --- Dashboard overrides for mar_dss.rules.defaults (geohydro rule parameters) ---
    for _row in RULE_DEFAULT_SCALAR_ROWS:
        _rk = _row[0]

        def _make_rule_scalar_cb(rkey=_rk):
            _inp = _rule_def_input_id(rkey)

            @app.callback(
                Output(_inp, "value"),
                [
                    Input(_inp, "n_blur"),
                    Input(_inp, "n_submit"),
                    Input(_inp, "id"),
                ],
                State(_inp, "value"),
                prevent_initial_call=False,
            )
            def _persist_geohydro_rule_scalar(n_blur, n_submit, _component_id, value):
                ctx = dash.callback_context
                base = RULE_DEFAULTS_BASE[rkey]
                if not ctx.triggered:
                    return rule_defaults_get(rkey)
                trig = ctx.triggered[0]["prop_id"].split(".")[1]
                if trig == "id":
                    return rule_defaults_get(rkey)
                ov0 = dict(dash_storage.get_data(RULE_DEFAULTS_OVERRIDES_STORAGE_KEY) or {})
                if value is None or str(value).strip() == "":
                    ov0.pop(rkey, None)
                    dash_storage.set_data(
                        RULE_DEFAULTS_OVERRIDES_STORAGE_KEY, ov0 if ov0 else None
                    )
                    return rule_defaults_get(rkey)
                try:
                    if isinstance(base, bool):
                        nv = bool(value)
                    elif isinstance(base, int) and not isinstance(base, bool):
                        nv = int(round(float(str(value).strip())))
                    else:
                        nv = float(str(value).strip())
                    if isinstance(nv, float) and not math.isfinite(nv):
                        raise ValueError
                except (ValueError, TypeError):
                    dash_storage.set_data(
                        RULE_DEFAULTS_OVERRIDES_STORAGE_KEY,
                        ov0 if ov0 else None,
                    )
                    return rule_defaults_get(rkey)
                ov0[rkey] = nv
                dash_storage.set_data(RULE_DEFAULTS_OVERRIDES_STORAGE_KEY, ov0)
                return nv

            return _persist_geohydro_rule_scalar

        _make_rule_scalar_cb()

    _lo_ex = "rule-def-excessive-deep-aquifer-0-input"
    _hi_ex = "rule-def-excessive-deep-aquifer-1-input"

    @app.callback(
        Output(_lo_ex, "value"),
        Output(_hi_ex, "value"),
        [
            Input(_lo_ex, "n_blur"),
            Input(_lo_ex, "n_submit"),
            Input(_hi_ex, "n_blur"),
            Input(_hi_ex, "n_submit"),
            Input(_lo_ex, "id"),
        ],
        [State(_lo_ex, "value"), State(_hi_ex, "value")],
        prevent_initial_call=False,
    )
    def _persist_excessive_deep_aquifer_bounds(
        nb0, ns0, nb1, ns1, id0, v0, v1
    ):
        ctx = dash.callback_context
        base = RULE_DEFAULTS_BASE["excessive_deep_aquifer"]
        if not ctx.triggered:
            ed = rule_defaults_get("excessive_deep_aquifer")
            return float(ed[0]), float(ed[1])
        trig = ctx.triggered[0]["prop_id"].split(".")[1]
        if trig == "id":
            ed = rule_defaults_get("excessive_deep_aquifer")
            return float(ed[0]), float(ed[1])

        try:
            lo = float(str(v0).strip()) if v0 is not None and str(v0).strip() != "" else float(base[0])
            hi = float(str(v1).strip()) if v1 is not None and str(v1).strip() != "" else float(base[1])
            if not math.isfinite(lo) or not math.isfinite(hi):
                raise ValueError
            if hi < lo:
                lo, hi = hi, lo
        except (ValueError, TypeError):
            ov = dict(dash_storage.get_data(RULE_DEFAULTS_OVERRIDES_STORAGE_KEY) or {})
            ov.pop("excessive_deep_aquifer", None)
            dash_storage.set_data(
                RULE_DEFAULTS_OVERRIDES_STORAGE_KEY, ov if ov else None
            )
            return float(base[0]), float(base[1])

        ov = dict(dash_storage.get_data(RULE_DEFAULTS_OVERRIDES_STORAGE_KEY) or {})
        ov["excessive_deep_aquifer"] = [lo, hi]
        dash_storage.set_data(RULE_DEFAULTS_OVERRIDES_STORAGE_KEY, ov)
        return lo, hi

    @app.callback(
        [
            Output("aquitard-conductivity-input", "value", allow_duplicate=True),
            Output("confined-aquifer-head-input", "value", allow_duplicate=True),
            Output("max-dry-well-depth-input", "value", allow_duplicate=True),
            *[
                Output(_rule_def_input_id(row[0]), "value", allow_duplicate=True)
                for row in RULE_DEFAULT_SCALAR_ROWS
            ],
            Output("rule-def-excessive-deep-aquifer-0-input", "value", allow_duplicate=True),
            Output("rule-def-excessive-deep-aquifer-1-input", "value", allow_duplicate=True),
        ],
        Input("reset-default-parameters-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_default_parameters_to_builtins(n_clicks):
        """Clear overrides and restore all (3.2) Default Parameters fields."""
        if not n_clicks:
            raise dash.exceptions.PreventUpdate

        dash_storage.set_data(RULE_DEFAULTS_OVERRIDES_STORAGE_KEY, None)
        dash_storage.set_data(
            "aquitard_conductivity_ft_day", DEFAULT_AQUITARD_K_MAX_FT_DAY
        )
        dash_storage.set_data("confined_aquifer_head_ft", None)
        dash_storage.set_data(
            "max_dry_well_depth_ft", DEFAULT_MAX_DRY_WELL_DEPTH_FT
        )

        scalar_values = []
        for key, *_rest in RULE_DEFAULT_SCALAR_ROWS:
            scalar_values.append(RULE_DEFAULTS_BASE[key])

        eda = RULE_DEFAULTS_BASE["excessive_deep_aquifer"]
        return (
            _aquitard_k_input_str(DEFAULT_AQUITARD_K_MAX_FT_DAY),
            "",
            DEFAULT_MAX_DRY_WELL_DEPTH_FT,
            *scalar_values,
            float(eda[0]),
            float(eda[1]),
        )