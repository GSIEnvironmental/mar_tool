"""
Hydrogeology tab callbacks for MAR DSS dashboard.
"""

import math

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc, html, State, callback_context
import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.components.hydro_tab import (
    RULE_DEFAULT_SCALAR_ROWS,
    _rule_def_input_id,
    normalize_stratigraphy_recharge_target,
)

_FEASIBILITY_RULE_DEFAULT_INPUTS = [
    Input(_rule_def_input_id(k), "value")
    for k, _, _, _ in RULE_DEFAULT_SCALAR_ROWS
] + [
    Input("rule-def-excessive-deep-aquifer-0-input", "value"),
    Input("rule-def-excessive-deep-aquifer-1-input", "value"),
]

from mar_dss.rules.geohydro_rules import (
    DEFAULT_AQUITARD_K_MAX_FT_DAY,
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
from mar_dss.app.utils.initial_hydro_feasibility import evaluate_option_traffic_light

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
    """Bold green 'Pass' / bold red 'Fail' for Initial Hydrologic Feasibility rows."""
    if not status_line:
        return ""
    if status_line == "Pass":
        return html.Span("Pass", className="fw-bold text-success small")
    prefix_pw = "Pass with Warnings - "
    if status_line.startswith(prefix_pw):
        rest = status_line[len(prefix_pw):]
        return html.Span(
            [
                html.Span("Pass", className="fw-bold text-success"),
                html.Span(f" with Warnings - {rest}", className="text-muted"),
            ],
            className="small",
        )
    prefix_fail = "Fail - "
    if status_line.startswith(prefix_fail):
        rest = status_line[len(prefix_fail):]
        return html.Span(
            [
                html.Span("Fail", className="fw-bold text-danger"),
                html.Span(f" - {rest}", className="text-muted"),
            ],
            className="small",
        )
    return html.Span(status_line, className="small text-muted")


def _aquitard_k_input_str(k: float) -> str:
    """Plain-text field display for aquitard K (no scientific spinners); trim trailing zeros."""
    if k is None or not math.isfinite(k) or k <= 0.0:
        k = DEFAULT_AQUITARD_K_MAX_FT_DAY
    text = f"{k:.12f}".rstrip("0").rstrip(".")
    return text if text else str(k)


def setup_hydro_callbacks(app):
    """Set up all hydrogeology-related callbacks."""
    
    # Typical values for different soil types
    SOIL_PROPERTIES = {
        "Gravel": {"conductivity": 100.0, "storage": 0.0001, "yield": 0.30},
        "Sand": {"conductivity": 10.0, "storage": 0.0001, "yield": 0.25},
        "Silt": {"conductivity": 0.01, "storage": 0.0001, "yield": 0.10},
        "Loam": {"conductivity": 0.001, "storage": 0.0001, "yield": 0.05},
        "Clay": {"conductivity": 0.0001, "storage": 0.0001, "yield": 0.01}
    }
    
    # Persist inferred aquifer type (no manual aquifer-type control)
    @app.callback(
        Output("aq-type-inferred-store", "data"),
        Output("aquifer-type-display", "children"),
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
        aq_text = str(inferred).replace("-", " ").title()
        return inferred, f"Aquifer Type: {aq_text}"

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
            "horizontal-extension-tab": "xy-view"
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

    # Callback to save stratigraphy data to dash_storage when store updates
    @app.callback(
        Output("stratigraphy-data-store", "data", allow_duplicate=True),
        [Input("stratigraphy-data-store", "data")],
        prevent_initial_call=True
    )
    def save_stratigraphy_to_storage(data):
        """Save stratigraphy data to dash_storage when store updates."""
        if data:
            normalize_stratigraphy_recharge_target(data)
            dash_storage.set_data("stratigraphy_data", data)
        return dash.no_update
    
    # Callback to save groundwater data to dash_storage when store updates
    @app.callback(
        Output("groundwater-data-store", "data", allow_duplicate=True),
        [Input("groundwater-data-store", "data")],
        prevent_initial_call=True
    )
    def save_groundwater_to_storage(data):
        """Save groundwater data to dash_storage when store updates."""
        if data:
            dash_storage.set_data("groundwater_data", data)
        return dash.no_update
    
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
        [
            Input("max-mar-storage-depth", "value"),
            Input("max-mar-storage-depth", "n_blur"),
            Input("max-mar-storage-depth", "n_submit"),
            Input("max-mar-storage-depth", "id")
        ],
        prevent_initial_call=False
    )
    def handle_max_mar_storage_depth_input(value, n_blur, n_submit, component_id):
        """Handle max MAR storage depth input and save to data storage."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved value and ensure it's a float, then save it
            depth = dash_storage.get_data("max_mar_storage_depth")
            if depth is not None:
                try:
                    depth = float(depth)
                except (ValueError, TypeError):
                    depth = 20.0
            else:
                depth = 20.0
            dash_storage.set_data("max_mar_storage_depth", depth)
            return depth
        
        # Get the current value and convert to float
        if value is not None:
            try:
                current_value = float(value)
            except (ValueError, TypeError):
                current_value = 20.0
        else:
            current_value = 20.0
        
        # Determine which trigger caused the callback
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1] if ctx.triggered else ""
        
        # Save for all triggers except initial load (ensure it's saved as float)
        if trigger_prop != "id":
            dash_storage.set_data("max_mar_storage_depth", current_value)
        
        return current_value
    
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
    
    # Callback to save upstream head to data storage
    @app.callback(
        Output("upstream-head", "value"),
        [
            Input("upstream-head", "value"),
            Input("upstream-head", "n_blur"),
            Input("upstream-head", "n_submit"),
            Input("upstream-head", "id")
        ],
        prevent_initial_call=False
    )
    def handle_upstream_head_input(value, n_blur, n_submit, component_id):
        """Handle upstream head input and save to data storage."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved value or use default, and save it
            head = dash_storage.get_data("upstream_head") or 10.0
            dash_storage.set_data("upstream_head", head)
            return head
        
        current_value = value if value is not None else 10.0
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1] if ctx.triggered else ""
        
        if trigger_prop != "id":
            dash_storage.set_data("upstream_head", current_value)
        
        return current_value
    
    # Callback to save downstream head to data storage
    @app.callback(
        Output("downstream-head", "value"),
        [
            Input("downstream-head", "value"),
            Input("downstream-head", "n_blur"),
            Input("downstream-head", "n_submit"),
            Input("downstream-head", "id")
        ],
        prevent_initial_call=False
    )
    def handle_downstream_head_input(value, n_blur, n_submit, component_id):
        """Handle downstream head input and save to data storage."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved value or use default, and save it
            head = dash_storage.get_data("downstream_head") or 5.0
            dash_storage.set_data("downstream_head", head)
            return head
        
        current_value = value if value is not None else 5.0
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1] if ctx.triggered else ""
        
        if trigger_prop != "id":
            dash_storage.set_data("downstream_head", current_value)
        
        return current_value
    
    @app.callback(
        Output("stratigraphy-table-body", "children"),
        [Input("stratigraphy-data-store", "data")],
        prevent_initial_call=False
    )
    def update_stratigraphy_table(data):
        """Update the stratigraphy table based on stored data."""
        if not data:
            return []
        
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
                size="sm"
            )
            
            # Create thickness input
            thickness_input = dbc.Input(
                id={"type": "thickness-input", "index": i},
                value=row["thickness"],
                type="number",
                step="0.1",
                size="sm"
            )
            
            # Create input fields
            conductivity_input = dbc.Input(
                id={"type": "conductivity-input", "index": i},
                value=row["conductivity"],
                type="number",
                step="0.001",
                size="sm"
            )
            
            storage_input = dbc.Input(
                id={"type": "storage-input", "index": i},
                value=row["storage"],
                type="number",
                step="0.000001",
                size="sm"
            )
            
            yield_input = dbc.Input(
                id={"type": "yield-input", "index": i},
                value=row["yield"],
                type="number",
                step="0.01",
                size="sm"
            )
            
            rows.append(html.Tr([
                html.Td(checkbox),
                html.Td(layer_dropdown),
                html.Td(
                    html.Div(
                        recharge_checkbox,
                        className="d-flex justify-content-center align-items-center",
                    )
                ),
                html.Td(thickness_input),
                html.Td(conductivity_input),
                html.Td(storage_input),
                html.Td(yield_input),
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
        
        current_data = data or []
        
        button_id = ctx.triggered[0]["prop_id"].split(".")[0]
        
        if button_id == "add-layer-btn":
            # Add new layer (default to Sand)
            new_layer = {
                "layer": "Sand",
                "thickness": 60.0,
                "conductivity": SOIL_PROPERTIES["Sand"]["conductivity"],
                "storage": SOIL_PROPERTIES["Sand"]["storage"],
                "yield": SOIL_PROPERTIES["Sand"]["yield"],
                "selected": False,
                "recharge_target": False,
            }
            current_data.append(new_layer)
            
        elif button_id == "delete-layer-btn":
            # Delete selected layers
            current_data = [row for row in current_data if not row.get("selected", False)]
            
        elif button_id == "move-up-btn":
            # Move selected layers up
            for i in range(1, len(current_data)):
                if current_data[i].get("selected", False) and not current_data[i-1].get("selected", False):
                    current_data[i], current_data[i-1] = current_data[i-1], current_data[i]
                    
        elif button_id == "move-down-btn":
            # Move selected layers down
            for i in range(len(current_data)-2, -1, -1):
                if current_data[i].get("selected", False) and not current_data[i+1].get("selected", False):
                    current_data[i], current_data[i+1] = current_data[i+1], current_data[i]

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
        [Input({"type": "layer-checkbox", "index": dash.dependencies.ALL}, "value"),
         Input({"type": "layer-select", "index": dash.dependencies.ALL}, "value"),
         Input({"type": "thickness-input", "index": dash.dependencies.ALL}, "value"),
         Input({"type": "conductivity-input", "index": dash.dependencies.ALL}, "value"),
         Input({"type": "storage-input", "index": dash.dependencies.ALL}, "value"),
         Input({"type": "yield-input", "index": dash.dependencies.ALL}, "value")],
        [State("stratigraphy-data-store", "data")],
        prevent_initial_call=True
    )
    def update_table_data(checkbox_values, layer_values, thickness_values, conductivity_values, storage_values, yield_values, data):
        """Update table data when inputs change."""
        if not data:
            return data
        
        # Update data with new values
        for i, row in enumerate(data):
            if i < len(checkbox_values):
                row["selected"] = checkbox_values[i] or False
            if i < len(layer_values):
                row["layer"] = layer_values[i]
                # Update properties based on selected layer
                if layer_values[i] in SOIL_PROPERTIES:
                    props = SOIL_PROPERTIES[layer_values[i]]
                    row["conductivity"] = props["conductivity"]
                    row["storage"] = props["storage"]
                    row["yield"] = props["yield"]
            if i < len(thickness_values) and thickness_values[i] is not None:
                row["thickness"] = float(thickness_values[i])
            if i < len(conductivity_values) and conductivity_values[i] is not None:
                row["conductivity"] = float(conductivity_values[i])
            if i < len(storage_values) and storage_values[i] is not None:
                row["storage"] = float(storage_values[i])
            if i < len(yield_values) and yield_values[i] is not None:
                row["yield"] = float(yield_values[i])
        
        return data
    
    # Groundwater Level Table Callbacks
    @app.callback(
        Output("groundwater-table-body", "children"),
        [Input("groundwater-data-store", "data")],
        prevent_initial_call=False
    )
    def update_groundwater_table(data):
        """Update the groundwater level table based on stored data."""
        if not data:
            return []
        
        rows = []
        for i, row in enumerate(data):
            # Create checkbox for selection
            checkbox = dbc.Checkbox(
                id={"type": "gw-checkbox", "index": i},
                value=row.get("selected", False),
                className="form-check-input"
            )
            
            # Create month dropdown
            month_dropdown = dbc.Select(
                id={"type": "month-select", "index": i},
                value=row["month"],
                options=[
                    {"label": "January", "value": "January"},
                    {"label": "February", "value": "February"},
                    {"label": "March", "value": "March"},
                    {"label": "April", "value": "April"},
                    {"label": "May", "value": "May"},
                    {"label": "June", "value": "June"},
                    {"label": "July", "value": "July"},
                    {"label": "August", "value": "August"},
                    {"label": "September", "value": "September"},
                    {"label": "October", "value": "October"},
                    {"label": "November", "value": "November"},
                    {"label": "December", "value": "December"}
                ],
                size="sm"
            )
            
            # Create elevation input
            elevation_input = dbc.Input(
                id={"type": "elevation-input", "index": i},
                value=row["elevation"],
                type="number",
                step="0.1",
                size="sm"
            )
            
            rows.append(html.Tr([
                html.Td(checkbox),
                html.Td(month_dropdown),
                html.Td(elevation_input)
            ]))
        
        return rows
    
    @app.callback(
        Output("groundwater-data-store", "data"),
        [Input("add-month-btn", "n_clicks"),
         Input("delete-month-btn", "n_clicks"),
         Input("reset-gw-btn", "n_clicks")],
        [State("groundwater-data-store", "data")],
        prevent_initial_call=True
    )
    def handle_groundwater_actions(add_clicks, delete_clicks, reset_clicks, data):
        """Handle groundwater table actions."""
        ctx = callback_context
        if not ctx.triggered:
            return data
        
        button_id = ctx.triggered[0]["prop_id"].split(".")[0]
        current_data = data or []
        
        if button_id == "add-month-btn":
            # Add new month (default to January)
            new_month = {
                "month": "January",
                "elevation": 75.0,
                "selected": False
            }
            current_data.append(new_month)
            
        elif button_id == "delete-month-btn":
            # Delete selected months
            current_data = [row for row in current_data if not row.get("selected", False)]
            
        elif button_id == "reset-gw-btn":
            # Reset to default values
            current_data = [
                {"month": "January", "elevation": 75.0, "selected": False},
                {"month": "February", "elevation": 72.0, "selected": False},
                {"month": "March", "elevation": 78.0, "selected": False},
                {"month": "April", "elevation": 82.0, "selected": False},
                {"month": "May", "elevation": 85.0, "selected": False},
                {"month": "June", "elevation": 88.0, "selected": False},
                {"month": "July", "elevation": 90.0, "selected": False},
                {"month": "August", "elevation": 89.0, "selected": False},
                {"month": "September", "elevation": 86.0, "selected": False},
                {"month": "October", "elevation": 83.0, "selected": False},
                {"month": "November", "elevation": 79.0, "selected": False},
                {"month": "December", "elevation": 76.0, "selected": False}
            ]
        
        return current_data
    
    @app.callback(
        Output("groundwater-data-store", "data", allow_duplicate=True),
        [Input({"type": "gw-checkbox", "index": dash.dependencies.ALL}, "value"),
         Input({"type": "month-select", "index": dash.dependencies.ALL}, "value"),
         Input({"type": "elevation-input", "index": dash.dependencies.ALL}, "value")],
        [State("groundwater-data-store", "data")],
        prevent_initial_call=True
    )
    def update_groundwater_data(checkbox_values, month_values, elevation_values, data):
        """Update groundwater data when inputs change."""
        if not data:
            return data
        
        # Update data with new values
        for i, row in enumerate(data):
            if i < len(checkbox_values):
                row["selected"] = checkbox_values[i] or False
            if i < len(month_values):
                row["month"] = month_values[i]
            if i < len(elevation_values) and elevation_values[i] is not None:
                row["elevation"] = float(elevation_values[i])
        
        return data
    
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
            "Gravel": "#8B4513",      # Brown
            "Sand": "#F4A460",        # Sandy brown
            "Silt": "#D2B48C",        # Tan
            "Loam": "#DEB887",        # Burlywood
            "Clay": "#A0522D"         # Sienna
        }
        
        # Create the plot
        fig = go.Figure()
        
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

            # Add layer rectangle
            fig.add_trace(go.Scatter(
                x=[0, 1, 1, 0, 0],  # Rectangle coordinates
                y=[
                    cumulative_depth,
                    cumulative_depth,
                    cumulative_depth + thick_f,
                    cumulative_depth + thick_f,
                    cumulative_depth,
                ],
                fill='toself',
                fillcolor=layer_colors.get(layer_name, "#808080"),  # Default gray if layer not found
                line=dict(color='black', width=1),
                name=layer_name,
                hovertemplate=(
                    f'<b>{layer_name}</b><br>Thickness: {thick_f:.1f} ft<br>'
                    f'Depth: {cumulative_depth:.1f} - {cumulative_depth + thick_f:.1f} ft<extra></extra>'
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
                    f"Depth: {wt_depth_plot:.1f} ft bgs<br>"
                    "<extra></extra>"
                ),
            )
        )

        if recharge_target_mid_depth is not None:
            fig.add_trace(
                go.Scatter(
                    x=[0.18],
                    y=[recharge_target_mid_depth],
                    mode="markers",
                    name="Recharge target",
                    marker=dict(
                        symbol="circle",
                        size=18,
                        color="#22c55e",
                        line=dict(width=2, color="#15803d"),
                    ),
                    hovertemplate=(
                        "<b>Recharge target layer</b><br>"
                        f"{recharge_target_layer_name or ''}<br>"
                        f"Depth at layer midpoint: {recharge_target_mid_depth:.1f} ft bgs"
                        "<extra></extra>"
                    ),
                    showlegend=True,
                )
            )

        # Update layout
        fig.update_layout(
            title={
                'text': 'Stratigraphy Cross Section',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 16}
            },
            xaxis_title="",
            yaxis_title="Depth (ft)",
            yaxis=dict(autorange="reversed"),  # Reverse y-axis so surface is at top
            template="plotly_white",
            height=500,
            margin=dict(l=50, r=50, t=60, b=50),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.1,
                xanchor="center",
                x=0.5
            ),
            xaxis=dict(
                showgrid=False,
                showticklabels=False,
                range=[-0.1, 1.1]
            )
        )
        
        # Add grid
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
        
        return fig
    
    # XY View Plot Callback
    @app.callback(
        Output("xy-view-plot", "figure"),
        [Input("extension-length", "value"),
         Input("extension-width", "value"),
         Input("extension-rotation", "value"),
         Input("upstream-head", "value"),
         Input("downstream-head", "value")],
        prevent_initial_call=False
    )
    def update_xy_view_plot(length, width, rotation, upstream_head, downstream_head):
        """Update the XY view plot with rectangle and contour lines."""
        import numpy as np
        
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
        
        if upstream_head is None:
            upstream_head = 10.0
        else:
            try:
                upstream_head = float(upstream_head)
            except (ValueError, TypeError):
                upstream_head = 10.0
        
        if downstream_head is None:
            downstream_head = 5.0
        else:
            try:
                downstream_head = float(downstream_head)
            except (ValueError, TypeError):
                downstream_head = 5.0
        
        # Create the plot
        fig = go.Figure()
        
        # Convert rotation to radians
        rotation_rad = np.radians(rotation)
        
        # Define rectangle corners (centered at origin, then rotated)
        half_length = length / 2
        half_width = width / 2
        
        # Original rectangle corners (before rotation)
        corners = np.array([
            [-half_length, -half_width],
            [half_length, -half_width],
            [half_length, half_width],
            [-half_length, half_width],
            [-half_length, -half_width]  # Close the rectangle
        ])
        
        # Rotation matrix
        cos_rot = np.cos(rotation_rad)
        sin_rot = np.sin(rotation_rad)
        rotation_matrix = np.array([[cos_rot, -sin_rot], [sin_rot, cos_rot]])
        
        # Rotate the rectangle
        rotated_corners = corners @ rotation_matrix.T
        
        # Add rectangle outline
        fig.add_trace(go.Scatter(
            x=rotated_corners[:, 0],
            y=rotated_corners[:, 1],
            mode='lines',
            line=dict(color='black', width=3),
            name='MAR Project Area',
            hovertemplate='<b>MAR Project Area</b><br>Length: %{x:.1f} ft<br>Width: %{y:.1f} ft<extra></extra>',
            showlegend=True
        ))
        
        # Add filled rectangle
        fig.add_trace(go.Scatter(
            x=rotated_corners[:, 0],
            y=rotated_corners[:, 1],
            fill='toself',
            fillcolor='rgba(0, 123, 255, 0.3)',
            line=dict(color='rgba(255,255,255,0)'),
            name='Project Area',
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Create contour lines (10 lines parallel to width, from upstream to downstream)
        n_contours = 10
        head_values = np.linspace(upstream_head, downstream_head, n_contours)
        
        # Define color scale from blue (high head) to red (low head)
        colors = ['#0000FF', '#0080FF', '#00FFFF', '#00FF80', '#00FF00', 
                 '#80FF00', '#FFFF00', '#FF8000', '#FF4000', '#FF0000']
        
        for i, head in enumerate(head_values):
            # Create contour line parallel to the width (perpendicular to length)
            # The contour lines run from one width side to the other
            t = np.linspace(-half_width, half_width, 50)
            
            # Create points along the width at different positions along the length
            # Position varies from -half_length to +half_length
            length_position = (i / (n_contours - 1) - 0.5) * 2 * half_length
            
            # Create points along the width
            contour_x = np.full_like(t, length_position)
            contour_y = t
            
            # Rotate the contour line
            contour_points = np.column_stack([contour_x, contour_y])
            rotated_contour = contour_points @ rotation_matrix.T
            
            # Add contour line with color based on head value
            fig.add_trace(go.Scatter(
                x=rotated_contour[:, 0],
                y=rotated_contour[:, 1],
                mode='lines',
                line=dict(color=colors[i], width=2, dash='dash'),
                name=f'Head: {head:.1f} ft',
                hovertemplate=f'<b>Head: {head:.1f} ft</b><extra></extra>',
                showlegend=False
            ))
            
            # Add label for contour line (at the middle of the line)
            label_position = np.array([length_position, 0]) @ rotation_matrix.T
            fig.add_annotation(
                x=label_position[0],
                y=label_position[1],
                text=f'{head:.1f}',
                showarrow=False,
                font=dict(size=10, color='black', family="Arial Black"),
                bgcolor="rgba(255,255,255,0.8)",
                bordercolor="black",
                borderwidth=1
            )
        
        # Add upstream and downstream labels
        # Upstream (higher head)
        upstream_center = np.array([-half_length, 0]) @ rotation_matrix.T
        fig.add_annotation(
            x=upstream_center[0],
            y=upstream_center[1],
            text=f"Upstream<br>{upstream_head:.1f} ft",
            showarrow=True,
            arrowhead=2,
            arrowcolor="green",
            font=dict(size=10, color="green"),
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="green"
        )
        
        # Downstream (lower head)
        downstream_center = np.array([half_length, 0]) @ rotation_matrix.T
        fig.add_annotation(
            x=downstream_center[0],
            y=downstream_center[1],
            text=f"Downstream<br>{downstream_head:.1f} ft",
            showarrow=True,
            arrowhead=2,
            arrowcolor="red",
            font=dict(size=10, color="red"),
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="red"
        )
        
        # Update layout
        fig.update_layout(
            title={
                'text': 'XY View - MAR Project Area with Head Contours',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 16}
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
                x=0.5
            ),
            xaxis=dict(scaleanchor="y", scaleratio=1),  # Equal aspect ratio
            yaxis=dict(scaleanchor="x", scaleratio=1)
        )
        
        # No grid lines for cleaner appearance
        
        return fig

    _TRAFFIC_DOT = {"green": "#198754", "orange": "#fd7e14", "red": "#dc3545"}

    @app.callback(
        Output("initial-feasibility-traffic-output", "children"),
        Input("check-initial-feasibility-btn", "n_clicks"),
        [
            State("stratigraphy-data-store", "data"),
            State("groundwater-data-store", "data"),
            State("ground-surface-elevation", "value"),
            State("aquitard-conductivity-input", "value"),
        ],
        prevent_initial_call=True,
    )
    def update_initial_feasibility_traffic(
        _n_clicks,
        strat_store,
        gw_store,
        gs_elev,
        aq_k_input,
    ):
        """Evaluate the decision graph and show per-option traffic lights from MAR constraints."""
        try:
            if strat_store is not None:
                rows = list(strat_store)
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
                return dbc.Alert(
                    "Decision graph is not available.",
                    color="warning",
                    className="mb-0 small",
                )
            evaluate_and_store_decision_graph(graph, inputs)

            rows_out = []
            for option in mar_options():
                color, status_line = evaluate_option_traffic_light(
                    option,
                    hc_module.hard_constraints,
                    sc_module.soft_constraints,
                )
                dot = _TRAFFIC_DOT[color]
                name_cls = (
                    "fw-semibold small text-success"
                    if color in ("green", "orange")
                    else "fw-semibold small text-danger"
                )
                rows_out.append(
                    dbc.Row(
                        [
                            dbc.Col(
                                html.Span(
                                    className="rounded-circle d-inline-block flex-shrink-0",
                                    style={
                                        "width": "14px",
                                        "height": "14px",
                                        "backgroundColor": dot,
                                        "verticalAlign": "middle",
                                    },
                                ),
                                width="auto",
                                className="d-flex align-items-start pt-1",
                            ),
                            dbc.Col(
                                [
                                    html.Div(
                                        option.name,
                                        className=name_cls,
                                    ),
                                    html.Div(
                                        _render_initial_feasibility_status(status_line),
                                        className="small",
                                    ),
                                ],
                                className="ps-0",
                            ),
                        ],
                        className="mb-2 align-items-start gx-2",
                    )
                )

            return html.Div(rows_out, className="initial-feasibility-traffic mt-1")
        except ValueError as err:
            return dbc.Alert(
                f"Cannot evaluate feasibility: {err}",
                color="warning",
                className="mb-0 small",
            )
        except Exception as err:
            import traceback

            traceback.print_exc()
            return dbc.Alert(
                f"Error: {err}",
                color="danger",
                className="mb-0 small",
            )

    # Callback to update Hydrogeologic Feasibility content
    @app.callback(
        Output("hydrogeologic-feasibility-content", "children"),
        [
            Input("stratigraphy-data-store", "data"),
            Input("groundwater-data-store", "data"),
            Input("aq-type-inferred-store", "data"),
            Input("aquitard-conductivity-input", "value"),
            Input("hydrogeology-subtabs", "active_tab"),
            *_FEASIBILITY_RULE_DEFAULT_INPUTS,
        ],
        prevent_initial_call=False
    )
    def update_hydrogeologic_feasibility_content(*args):
        """Update the Hydrogeologic Feasibility tab content when data changes."""
        strat_data, gw_data, _aq_inferred, aq_k_input, active_tab = args[:5]
        # args[5:] are rule-default control values (refresh trigger only; rules read via get_default).

        from mar_dss.app.components.hydrogeologic_feasibility_content import (
            create_hydrogeologic_feasibility_content_dynamic,
            create_loading_content
        )
        
        # Only update if we're on the feasibility tab
        if active_tab != "hydrogeologic-feasibility-tab":
            return dash.no_update
        
        try:
            strat = strat_data if strat_data is not None else dash_storage.get_data("stratigraphy_data")
            gw = gw_data if gw_data is not None else dash_storage.get_data("groundwater_data")
            gs_elev = dash_storage.get_data("ground_surface_elevation")
            aq_k = _coerce_aquitard_k_ft_day(aq_k_input)
            inferred = infer_dashboard_aquifer_type(
                strat or [],
                gw or [],
                gs_elev,
                aquitard_k_max_ft_day=aq_k,
            )
            dash_storage.set_data("aq_type", inferred)

            # Generate dynamic content
            content = create_hydrogeologic_feasibility_content_dynamic()
            return content
        except Exception as e:
            import traceback
            traceback.print_exc()
            return create_loading_content(f"Error: {str(e)}")

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