"""
Main dashboard callbacks for MAR DSS.
"""
import copy
import json
import os
from datetime import datetime
import pandas as pd


import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, html, dependencies, ALL
from dash.dependencies import ClientsideFunction
import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.utils.native_file_dialog import ask_save_project_path
from mar_dss.app.utils.project_file_path import format_project_path, split_project_path
from mar_dss.app.utils.project_storage import (
    apply_project_storage_defaults,
    is_missing_storage_value,
    normalize_stored_string,
    prepare_project_storage_for_export,
    _parse_literal_if_needed,
)

# Import content creation functions
try:
    from mar_dss.app.components.ai_generated_decision_tab import (
        create_ai_generated_decision_content,
    )
    from mar_dss.app.components.dashboard_tab import create_dashboard_content
    from mar_dss.app.components.data_export_tab import (
        create_data_export_content,
    )
    from mar_dss.app.components.decision_interpretation_tab import (
        create_decision_interpretation_content,
    )
    from mar_dss.app.components.hydro_tab import (
        create_hydro_tab_content,
        default_stratigraphy_layers,
        normalize_groundwater_data,
        normalize_stratigraphy_recharge_target,
        stratigraphy_store_payload_from_storage,
    )
    from mar_dss.app.components.scenarios_comparison_tab import (
        create_scenarios_comparison_content,
    )
    from mar_dss.app.components.water_source_tab import (
        create_general_tab_content,
    )
    from mar_dss.app.components.overview_tab import (
        create_overview_content,
        DEFAULT_OVERVIEW_MAP_LAT,
        DEFAULT_OVERVIEW_MAP_LON,
        DEFAULT_OVERVIEW_MAP_ZOOM,
        DEFAULT_OVERVIEW_MAP_BASEMAP,
    )
    from mar_dss.app.components.layout import MAIN_TAB_IDS, main_tab_panel_id
except ImportError:
    from .components.ai_generated_decision_tab import (
        create_ai_generated_decision_content,
    )
    from .components.dashboard_tab import create_dashboard_content
    from .components.data_export_tab import create_data_export_content
    from .components.decision_interpretation_tab import (
        create_decision_interpretation_content,
    )
    from .components.hydro_tab import (
        create_hydro_tab_content,
        default_stratigraphy_layers,
        normalize_groundwater_data,
        normalize_stratigraphy_recharge_target,
        stratigraphy_store_payload_from_storage,
    )
    from .components.scenarios_comparison_tab import (
        create_scenarios_comparison_content,
    )
    from .components.water_source_tab import create_general_tab_content
    from .components.overview_tab import (
        create_overview_content,
        DEFAULT_OVERVIEW_MAP_LAT,
        DEFAULT_OVERVIEW_MAP_LON,
        DEFAULT_OVERVIEW_MAP_ZOOM,
        DEFAULT_OVERVIEW_MAP_BASEMAP,
    )
    from ..components.layout import MAIN_TAB_IDS, main_tab_panel_id


_SKIP_PROJECT_EXPORT_KEYS = frozenset({
    "decision_graph",
    "feasibility_analysis_hash",
    "graph_computation_log",
    "graph_computation_log_text",
})


def _project_export_rows():
    """Build key/value rows for CSV export from current storage."""
    prepare_project_storage_for_export()
    last_saved = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dash_storage.set_data("last_saved", last_saved)

    rows = []
    for key, value in (dash_storage.get_data_storage() or {}).items():
        if key in _SKIP_PROJECT_EXPORT_KEYS:
            continue
        rows.append([key, value])
    return rows


def _project_export_dict():
    """Build a JSON-serializable project dict from current storage."""
    prepare_project_storage_for_export()
    last_saved = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dash_storage.set_data("last_saved", last_saved)

    clean_data = {}
    for key, value in (dash_storage.get_data_storage() or {}).items():
        if key in _SKIP_PROJECT_EXPORT_KEYS:
            continue
        try:
            json.dumps(value)
            clean_data[key] = value
        except (TypeError, ValueError):
            continue
    return clean_data


def _save_project_to_path(fn: str) -> None:
    """Write the current project to ``fn`` as CSV or JSON based on extension."""
    suffix = os.path.splitext(fn)[1].lower()
    if suffix == ".json":
        with open(fn, "w", encoding="utf-8") as f:
            json.dump(_project_export_dict(), f, indent=2)
        return

    df = pd.DataFrame(_project_export_rows(), columns=["key", "value"])
    df.to_csv(fn, index=False)


def setup_main_callbacks(app, dashboard_instance):
    """Set up all main dashboard callbacks."""
    
    # Import and set up overview callbacks
    try:
        from mar_dss.app.callbacks.overview_callbacks import setup_overview_callbacks
    except ImportError:
        from .overview_callbacks import setup_overview_callbacks

    def _create_main_tab_content(active_tab_id: str):
        """Build children for one top-level tab (lazy, once per panel)."""
        if active_tab_id == "overview":
            return create_overview_content()
        if active_tab_id == "water-source":
            return create_general_tab_content()
        if active_tab_id == "hydrogeology":
            return create_hydro_tab_content()
        if active_tab_id == "environmental":
            try:
                from mar_dss.app.components.environmental_impact_tab import (
                    create_environmental_impact_content,
                )
            except ImportError:
                from ..components.environmental_impact_tab import (
                    create_environmental_impact_content,
                )
            return create_environmental_impact_content()
        if active_tab_id == "legal":
            try:
                from mar_dss.app.components.legal_constraints_tab import (
                    create_legal_constraints_content,
                )
            except ImportError:
                from ..components.legal_constraints_tab import (
                    create_legal_constraints_content,
                )
            return create_legal_constraints_content()
        if active_tab_id == "engineering-options":
            try:
                from mar_dss.app.components.engineering_options_tab import (
                    create_engineering_options_content,
                )
            except ImportError:
                from ..components.engineering_options_tab import (
                    create_engineering_options_content,
                )
            return create_engineering_options_content()
        if active_tab_id == "analysis":
            try:
                from mar_dss.app.components.analysis_tab import create_analysis_tab_content
            except ImportError:
                from ..components.analysis_tab import create_analysis_tab_content
            return create_analysis_tab_content()
        return create_overview_content()

    app.clientside_callback(
        """
        function(active_tab) {
            var tabs = ["overview", "water-source", "hydrogeology", "environmental",
                "legal", "engineering-options", "analysis"];
            tabs.forEach(function(t) {
                var el = document.getElementById("main-tab-panel-" + t);
                if (el) {
                    el.style.display = (active_tab === t) ? "block" : "none";
                }
            });
            return 0;
        }
        """,
        Output("main-tab-clientside-sync", "data"),
        Input("top-tabs", "active_tab"),
        prevent_initial_call=False,
    )

    # Bump analysis-rerun-count on every click of the (7) Analysis tab (including re-click).
    app.clientside_callback(
        """
        function(active_tab) {
            if (!window.__marAnalysisTopTabClickHook) {
                window.__marAnalysisTopTabClickHook = true;
                var root = document.getElementById("top-tabs");
                if (root) {
                    root.addEventListener("click", function(ev) {
                        var tab = ev.target && ev.target.closest && ev.target.closest('[role="tab"]');
                        if (!tab || !root.contains(tab)) return;
                        var txt = (tab.textContent || "").trim();
                        if (txt.indexOf("(7)") === -1) return;
                        window.__marRC = (window.__marRC || 0) + 1;
                        try {
                            if (typeof dash_clientside !== "undefined" && dash_clientside.set_props) {
                                dash_clientside.set_props(
                                    "analysis-rerun-count",
                                    {data: window.__marRC}
                                );
                            }
                        } catch (e) {}
                    }, true);
                }
            }
            return dash_clientside.no_update;
        }
        """,
        Output("analysis-rerun-count", "data"),
        Input("top-tabs", "active_tab"),
        prevent_initial_call=False,
    )

    @app.callback(
        [Output(main_tab_panel_id(t), "children") for t in MAIN_TAB_IDS],
        Input("top-tabs", "active_tab"),
        [State(main_tab_panel_id(t), "children") for t in MAIN_TAB_IDS],
        prevent_initial_call=False,
    )
    def lazy_load_main_tab(active_tab, *existing_children):
        """Mount each tab body once; switching tabs only toggles visibility (clientside)."""
        try:
            idx = MAIN_TAB_IDS.index(active_tab)
        except ValueError:
            raise dash.exceptions.PreventUpdate
        if existing_children[idx]:
            raise dash.exceptions.PreventUpdate
        patch = [dash.no_update] * len(MAIN_TAB_IDS)
        patch[idx] = _create_main_tab_content(active_tab)
        return patch

    @app.callback(
        [
            Output("theme-selector", "value"),
            Output("theme-css", "href"),
            Output("app-container", "className"),
        ],
        [Input("theme-selector", "value")],
    )
    def update_theme(selected_theme):
        """Update theme based on selection."""
        theme_urls = {
            "CERULEAN": "https://cdn.jsdelivr.net/npm/bootswatch@5.3.2/dist/cerulean/bootstrap.min.css",
            "DARKLY": "https://cdn.jsdelivr.net/npm/bootswatch@5.3.2/dist/darkly/bootstrap.min.css",
            "FLATLY": "https://cdn.jsdelivr.net/npm/bootswatch@5.3.2/dist/flatly/bootstrap.min.css",
            "CYBORG": "https://cdn.jsdelivr.net/npm/bootswatch@5.3.2/dist/cyborg/bootstrap.min.css",
            "SLATE": "https://cdn.jsdelivr.net/npm/bootswatch@5.3.2/dist/slate/bootstrap.min.css",
        }
        theme = selected_theme or "CERULEAN"
        dashboard_instance.current_theme = theme
        theme_url = theme_urls.get(theme, theme_urls["CERULEAN"])
        # Dark themes need light text; light themes force muted greys → black
        body_theme_class = (
            "mar-theme-dark"
            if theme in ("DARKLY", "CYBORG", "SLATE")
            else "mar-theme-light"
        )
        return theme, theme_url, body_theme_class

    @app.callback(
        [
            Output("nav-dashboard", "active"),
            Output("nav-water-levels", "active"),
            Output("nav-recharge", "active"),
            Output("nav-quality", "active"),
            Output("nav-scenarios", "active"),
            Output("nav-ai-decision", "active"),
            Output("nav-export", "active"),
        ],
        [
            Input("nav-dashboard", "n_clicks"),
            Input("nav-water-levels", "n_clicks"),
            Input("nav-recharge", "n_clicks"),
            Input("nav-quality", "n_clicks"),
            Input("nav-scenarios", "n_clicks"),
            Input("nav-ai-decision", "n_clicks"),
            Input("nav-export", "n_clicks"),
        ],
    )
    def update_sidebar_active_states(
        dash_clicks,
        water_clicks,
        recharge_clicks,
        quality_clicks,
        scenarios_clicks,
        ai_clicks,
        export_clicks,
    ):
        """Update sidebar navigation active states."""
        ctx = dash.callback_context

        if not ctx.triggered:
            return True, False, False, False, False, False, False

        button_id = ctx.triggered[0]["prop_id"].split(".")[0]

        return (
            button_id == "nav-dashboard",
            button_id == "nav-water-levels",
            button_id == "nav-recharge",
            button_id == "nav-quality",
            button_id == "nav-scenarios",
            button_id == "nav-ai-decision",
            button_id == "nav-export",
        )


    # Sync flow-data-store from dash_storage when Water Source tab is shown
    @app.callback(
        Output("flow-data-store", "data"),
        Input("top-tabs", "active_tab"),
        State("flow-data-store", "data"),
        prevent_initial_call=False,
    )
    def sync_flow_data_store(active_tab, current_store):
        """Refresh flow store from project storage when opening Water Source."""
        if active_tab != "water-source":
            return dash.no_update

        try:
            from mar_dss.app.components.water_source_tab import (
                flow_dict_from_list,
                flow_dicts_equal,
            )
        except ImportError:
            from .components.water_source_tab import (
                flow_dict_from_list,
                flow_dicts_equal,
            )

        flow_data = flow_dict_from_list(dash_storage.get_data("monthly_flow"))
        if flow_dicts_equal(current_store, flow_data):
            return dash.no_update
        return flow_data

    # When checked, copy January into every month and lock Feb–Dec.
    @app.callback(
        Output({"type": "monthly-flow-input", "month": ALL}, "disabled"),
        Input("constant-monthly-flow-check", "value"),
        State({"type": "monthly-flow-input", "month": ALL}, "id"),
        prevent_initial_call=False,
    )
    def toggle_constant_monthly_flow_inputs(use_constant, input_ids):
        if not input_ids:
            return []
        return [
            bool(use_constant) and id_dict.get("month") != "Jan"
            for id_dict in input_ids
        ]

    _WATER_SOURCE_NEGATIVE_INPUT_ALERT = dbc.Alert(
        "Water Source: negative values are not allowed. "
        "All table input values must be zero or greater.",
        color="danger",
        className="py-2 small mb-0",
    )

    @app.callback(
        Output({"type": "monthly-flow-input", "month": ALL}, "value", allow_duplicate=True),
        Output("flow-data-store", "data", allow_duplicate=True),
        Output("monthly-flow-input-error", "children", allow_duplicate=True),
        Input("constant-monthly-flow-check", "value"),
        Input({"type": "monthly-flow-input", "month": "Jan"}, "value"),
        State({"type": "monthly-flow-input", "month": ALL}, "id"),
        State({"type": "monthly-flow-input", "month": ALL}, "value"),
        prevent_initial_call=True,
    )
    def apply_constant_monthly_flow(use_constant, jan_value, input_ids, values):
        """Propagate January to all months while the constant-flow checkbox is on."""
        if not input_ids:
            return [], dash.no_update, dash.no_update
        if not use_constant:
            return [dash.no_update] * len(input_ids), dash.no_update, dash.no_update

        try:
            from mar_dss.app.components.water_source_tab import (
                FLOW_MONTHS,
                flow_dict_from_list,
                flow_dicts_equal,
            )
        except ImportError:
            from .components.water_source_tab import (
                FLOW_MONTHS,
                flow_dict_from_list,
                flow_dicts_equal,
            )

        try:
            if jan_value is None or (
                isinstance(jan_value, str) and str(jan_value).strip() == ""
            ):
                stored = flow_dict_from_list(dash_storage.get_data("monthly_flow"))
                jan_val = float(stored.get("Jan", 0) or 0)
            else:
                jan_val = float(jan_value)
        except (TypeError, ValueError):
            return [dash.no_update] * len(input_ids), dash.no_update, dash.no_update

        out = []
        needs_update = False
        for i, id_dict in enumerate(input_ids):
            month = id_dict.get("month") if isinstance(id_dict, dict) else None
            if month == "Jan":
                out.append(dash.no_update)
                continue
            raw = values[i] if values and i < len(values) else None
            try:
                cur = (
                    float(raw)
                    if raw is not None
                    and not (isinstance(raw, str) and str(raw).strip() == "")
                    else None
                )
            except (TypeError, ValueError):
                cur = None
            if cur is None or abs(cur - jan_val) > 1e-9:
                out.append(jan_val)
                needs_update = True
            else:
                out.append(dash.no_update)

        error = (
            _WATER_SOURCE_NEGATIVE_INPUT_ALERT if jan_val < 0 else None
        )
        flow_data = {month: jan_val for month in FLOW_MONTHS}
        stored = flow_dict_from_list(dash_storage.get_data("monthly_flow"))
        if needs_update or not flow_dicts_equal(flow_data, stored):
            dash_storage.set_data(
                "monthly_flow", [flow_data[month] for month in FLOW_MONTHS]
            )
            return out, flow_data, error
        if not needs_update:
            return [dash.no_update] * len(input_ids), dash.no_update, error
        return out, dash.no_update, error

    # Push store → month inputs only for external updates (runoff / tab sync).
    @app.callback(
        Output({"type": "monthly-flow-input", "month": ALL}, "value", allow_duplicate=True),
        Input("flow-data-store", "data"),
        State({"type": "monthly-flow-input", "month": ALL}, "id"),
        State({"type": "monthly-flow-input", "month": ALL}, "value"),
        prevent_initial_call=True,
    )
    def apply_flow_store_to_table(flow_data, input_ids, current_values):
        """Update monthly flow inputs when the store changes (e.g. runoff sync)."""
        if not input_ids:
            return []

        try:
            from mar_dss.app.components.water_source_tab import flow_dicts_equal
        except ImportError:
            from .components.water_source_tab import flow_dicts_equal

        flow_data = flow_data or {}
        new_values = []
        new_dict = {}
        cur_dict = {}
        for i, id_dict in enumerate(input_ids):
            month = id_dict.get("month")
            try:
                nv = float(flow_data.get(month, 0) or 0)
            except (TypeError, ValueError):
                nv = 0.0
            new_values.append(nv)
            new_dict[month] = nv
            raw = current_values[i] if current_values and i < len(current_values) else None
            try:
                cur_dict[month] = float(raw) if raw is not None else 0.0
            except (TypeError, ValueError):
                cur_dict[month] = 0.0

        # ALL outputs require a list; a single no_update is invalid
        if flow_dicts_equal(cur_dict, new_dict):
            return [dash.no_update] * len(input_ids)
        return new_values

    # If a cell is cleared by click/focus/blur without a new number, restore stored value.
    # Negatives are allowed to remain but trigger an error message.
    @app.callback(
        Output({"type": "monthly-flow-input", "month": ALL}, "value", allow_duplicate=True),
        Output("monthly-flow-input-error", "children"),
        Input({"type": "monthly-flow-input", "month": ALL}, "value"),
        State({"type": "monthly-flow-input", "month": ALL}, "id"),
        prevent_initial_call=True,
    )
    def restore_blank_monthly_flow_inputs(values, input_ids):
        """Restore blank cells; warn (do not block) when any monthly flow is negative."""
        if not input_ids or values is None:
            return [], dash.no_update

        try:
            from mar_dss.app.components.water_source_tab import (
                flow_dict_from_list,
            )
        except ImportError:
            from .components.water_source_tab import flow_dict_from_list

        stored = flow_dict_from_list(dash_storage.get_data("monthly_flow"))
        out = []
        needs_restore = False
        has_negative = False
        for id_dict, raw in zip(input_ids, values):
            month = id_dict.get("month") if isinstance(id_dict, dict) else None
            stored_val = stored.get(month, 0.0) if month else 0.0
            blank = raw is None or (isinstance(raw, str) and str(raw).strip() == "")
            if blank:
                out.append(stored_val)
                needs_restore = True
                continue
            try:
                parsed = float(raw)
            except (TypeError, ValueError):
                out.append(stored_val)
                needs_restore = True
                continue
            if parsed < 0:
                has_negative = True
            out.append(parsed)

        error = _WATER_SOURCE_NEGATIVE_INPUT_ALERT if has_negative else None
        # ALL outputs require a list; a single no_update is invalid
        if not needs_restore:
            return [dash.no_update] * len(input_ids), error
        return out, error

    # Keep chart in sync with the table and with flow-data-store (tab open / runoff)
    @app.callback(
        Output("monthly-flow-chart", "figure"),
        [
            Input({"type": "monthly-flow-input", "month": ALL}, "value"),
            Input("flow-data-store", "data"),
        ],
        State({"type": "monthly-flow-input", "month": ALL}, "id"),
        prevent_initial_call=False,
    )
    def update_monthly_flow_chart_from_table(values, flow_store, input_ids):
        """Update the monthly flow chart; persist only real edits (not blank clicks)."""
        try:
            from mar_dss.app.components.water_source_tab import (
                FLOW_MONTHS,
                create_monthly_flow_chart,
                flow_dict_from_input_values,
                flow_dict_from_list,
                flow_dicts_equal,
            )
        except ImportError:
            from .components.water_source_tab import (
                FLOW_MONTHS,
                create_monthly_flow_chart,
                flow_dict_from_input_values,
                flow_dict_from_list,
                flow_dicts_equal,
            )

        stored = flow_dict_from_list(dash_storage.get_data("monthly_flow"))
        store_data = (
            flow_store
            if isinstance(flow_store, dict) and flow_store
            else stored
        )

        ctx = dash.callback_context
        trigger = ctx.triggered[0]["prop_id"] if ctx.triggered else ""

        # Store-driven update (tab open, runoff sync) — do not rewrite from inputs
        if "flow-data-store" in trigger or not input_ids:
            return create_monthly_flow_chart(store_data)

        # Merge table into stored values; blank/None cells keep stored month values
        flow_data = flow_dict_from_input_values(
            values, input_ids, fallback=stored
        )

        # Persist only when the user actually changed a numeric value
        if not flow_dicts_equal(flow_data, stored):
            dash_storage.set_data(
                "monthly_flow", [flow_data[month] for month in FLOW_MONTHS]
            )

        return create_monthly_flow_chart(flow_data)

    # Add callback to sync stratigraphy-data-store with dash_storage when hydrogeology tab is accessed
    @app.callback(
        Output("stratigraphy-data-store", "data", allow_duplicate=True),
        [
            Input("top-tabs", "active_tab"),
        ],
        prevent_initial_call=True
    )
    def sync_stratigraphy_data_store(active_tab):
        """When hydrogeology tab opens, seed the stratigraphy store from dash_storage."""
        if active_tab == "hydrogeology":
            return stratigraphy_store_payload_from_storage()
        return dash.no_update

    # Add callback to sync groundwater-data-store with dash_storage when hydrogeology tab is accessed
    @app.callback(
        Output("groundwater-data-store", "data", allow_duplicate=True),
        [
            Input("top-tabs", "active_tab"),
        ],
        prevent_initial_call=True
    )
    def sync_groundwater_data_store(active_tab):
        """Sync groundwater-data-store with dash_storage when hydrogeology tab is accessed."""
        if active_tab == "hydrogeology":
            stored_data = dash_storage.get_data("groundwater_data")
            return normalize_groundwater_data(stored_data if stored_data else [])
        return dash.no_update

    def manage_stratigraphy_layers(
        add_clicks,
        delete_clicks,
        thickness,
        layer_type,
        conductivity,
        porosity,
        current_data,
        local_data,
    ):
        """Manage adding and deleting stratigraphy layers."""
        ctx = dash.callback_context

        # Use whichever data store has data
        layers_data = current_data or local_data or []

        if not ctx.triggered:
            # Initial state - preserve existing data
            if not layers_data:
                return (
                    [
                        html.Div(
                            [
                                html.P(
                                    "No layers added yet. Use the form on the left to add layers",
                                    className="text-muted text-center p-3",
                                )
                            ]
                        )
                    ],
                    [
                        html.P("Total Depth: 0 m", className="mb-1"),
                        html.P("Aquifer Layers: 0", className="mb-1"),
                        html.P("Aquitard Layers: 0", className="mb-0"),
                    ],
                    layers_data,
                    layers_data,
                )

        # Check if this is an add operation
        if "add-layer-btn" in ctx.triggered[0]["prop_id"]:
            if thickness and layer_type:
                import time

                new_layer_data = {
                    "id": len(layers_data),
                    "timestamp": time.time(),
                    "thickness": float(thickness),
                    "layer_type": layer_type,
                    "conductivity": conductivity or 0,
                    "porosity": porosity or 0,
                }
                layers_data.append(new_layer_data)

        # Check if this is a delete operation
        elif "delete-layer" in ctx.triggered[0]["prop_id"]:
            try:
                import json

                triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
                component_id = json.loads(triggered_id)
                delete_index = component_id["index"]

                if 0 <= delete_index < len(layers_data):
                    layers_data = [
                        layer
                        for i, layer in enumerate(layers_data)
                        if i != delete_index
                    ]
            except (ValueError, KeyError, IndexError):
                pass

        # Render the profile
        if not layers_data:
            return (
                [
                    html.Div(
                        [
                            html.P(
                                "No layers added yet. Use the form on the left to add layers",
                                className="text-muted text-center p-3",
                            )
                        ]
                    )
                ],
                [
                    html.P("Total Depth: 0 m", className="mb-1"),
                    html.P("Aquifer Layers: 0", className="mb-1"),
                    html.P("Aquitard Layers: 0", className="mb-0"),
                ],
                layers_data,
                layers_data,
            )

        # Create layer cards
        layer_cards = []
        layer_type_colors = {
            "aquifer": "#28a745",
            "aquitard": "#ffc107",
            "confining": "#dc3545",
            "bedrock": "#6c757d",
            "topsoil": "#8b4513",
            "clay": "#8b4513",
            "silt": "#a0522d",
        }

        layer_display_names = {
            "aquifer": "Aquifer (High Permeability)",
            "aquitard": "Aquitard (Low Permeability)",
            "confining": "Confining Layer",
            "bedrock": "Bedrock",
            "topsoil": "Topsoil",
            "clay": "Clay Lens",
            "silt": "Silt Layer",
        }

        total_depth = 0
        aquifer_count = 0
        aquitard_count = 0

        for i, layer_data in enumerate(layers_data):
            layer_type = layer_data.get("layer_type", "aquifer")
            thickness = layer_data.get("thickness", 0)
            color = layer_type_colors.get(layer_type, "#6c757d")
            display_name = layer_display_names.get(
                layer_type, layer_type.title()
            )

            # Create layer card
            layer_card = dbc.Card(
                [
                    dbc.CardBody(
                        [
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            html.H6(
                                                display_name,
                                                className="mb-0 fw-bold",
                                                style={
                                                    "font-size": "0.9rem"
                                                },
                                            ),
                                            html.P(
                                                f"Thickness: {thickness} m",
                                                className="mb-0 small",
                                                style={
                                                    "font-size": "0.75rem"
                                                },
                                            ),
                                            html.P(
                                                f"Type: {layer_type.title()}",
                                                className="mb-0 small text-muted",
                                                style={
                                                    "font-size": "0.7rem"
                                                },
                                            ),
                                        ],
                                        width=8,
                                    ),
                                    dbc.Col(
                                        [
                                            dbc.Button(
                                                html.I(
                                                    className="fas fa-trash"
                                                ),
                                                id={
                                                    "type": "delete-layer",
                                                    "index": i,
                                                },
                                                color="outline-danger",
                                                size="sm",
                                                className="float-end",
                                                style={
                                                    "padding": "2px 6px",
                                                    "font-size": "0.7rem",
                                                },
                                            )
                                        ],
                                        width=4,
                                    ),
                                ]
                            )
                        ],
                        style={"padding": "8px 12px"},
                    )
                ],
                className="mb-1",
                style={
                    "border-left": f"4px solid {color}",
                    "border-radius": "4px",
                },
            )

            layer_cards.append(layer_card)

            # Update summary
            total_depth += thickness
            if layer_type == "aquifer":
                aquifer_count += 1
            elif layer_type in ["aquitard", "confining"]:
                aquitard_count += 1

        # Create summary
        summary = [
            html.P(f"Total Depth: {total_depth:.1f} m", className="mb-1"),
            html.P(f"Aquifer Layers: {aquifer_count}", className="mb-1"),
            html.P(f"Aquitard Layers: {aquitard_count}", className="mb-0"),
        ]

        return layer_cards, summary, layers_data, layers_data


    def _default_project_filename():
        data = dash_storage.get_data_storage() or {}
        return data.get("filename") or (
            f"mar_dss_project_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )

    def _current_project_path():
        data = dash_storage.get_data_storage() or {}
        return format_project_path(data.get("workspace"), data.get("filename"))

    def _save_project_via_picker(default_name=None):
        """Native save dialog; returns (picked_path, path_out) or raises/returns cancel sentinels."""
        default_name = default_name or _default_project_filename()
        picked = ask_save_project_path(default_name)

        if picked == "":
            return None, dash.no_update

        if picked is None:
            manual_path = _current_project_path()
            if not (manual_path or "").strip():
                raise ValueError(
                    "Native save dialog is unavailable here. Enter a full project "
                    "file path above, then use Save."
                )
            picked = os.path.normpath(manual_path.strip())

        parent = os.path.dirname(os.path.abspath(picked))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)

        _save_project_to_path(picked)
        workspace_dir, base_name = split_project_path(picked)
        dash_storage.set_data("workspace", workspace_dir)
        dash_storage.set_data("filename", base_name)
        path_out = format_project_path(workspace_dir, base_name)
        return picked, path_out

    # Callback for Save button - save current project
    @app.callback(
        Output("main-content-flash", "children"),
        Output(main_tab_panel_id("overview"), "children", allow_duplicate=True),
        Output("project-path-input", "value", allow_duplicate=True),
        Output("top-tabs", "active_tab", allow_duplicate=True),
        [Input("btn-save", "n_clicks")],
        prevent_initial_call=True,
    )
    def handle_save_project(n_clicks):
        """Handle saving the current project."""
        noop = (dash.no_update, dash.no_update, dash.no_update, dash.no_update)
        if not n_clicks:
            return noop

        try:
            current_path = _current_project_path()
            if not (current_path or "").strip():
                result = _save_project_via_picker()
                if result[0] is None:
                    return noop
                picked, path_out = result
                return (
                    [
                        dbc.Alert(
                            f"Project saved successfully at {picked}",
                            color="success",
                            className="mb-3",
                        )
                    ],
                    create_overview_content(),
                    path_out,
                    "overview",
                )

            fn = os.path.normpath(current_path.strip())
            _save_project_to_path(fn)
            workspace_dir, base_name = split_project_path(fn)
            dash_storage.set_data("workspace", workspace_dir)
            dash_storage.set_data("filename", base_name)
            path_out = format_project_path(workspace_dir, base_name)

            return (
                [
                    dbc.Alert(
                        f"Project saved successfully at {fn}",
                        color="success",
                        className="mb-3",
                    )
                ],
                create_overview_content(),
                path_out,
                "overview",
            )
        except Exception as e:
            return (
                [
                    dbc.Alert(
                        f"Error saving project: {str(e)}",
                        color="danger",
                        className="mb-3",
                    )
                ],
                create_overview_content(),
                dash.no_update,
                "overview",
            )

    # Callback for New button - create new project (clear lazy-mounted tabs so they reload)
    @app.callback(
        [
            Output("main-content-flash", "children", allow_duplicate=True),
            *[Output(main_tab_panel_id(t), "children", allow_duplicate=True) for t in MAIN_TAB_IDS],
            Output("top-tabs", "active_tab", allow_duplicate=True),
            Output("stratigraphy-data-store", "data", allow_duplicate=True),
            Output("groundwater-data-store", "data", allow_duplicate=True),
            Output("project-location-store", "data", allow_duplicate=True),
            Output("project-path-input", "value", allow_duplicate=True),
        ],
        [Input("btn-new", "n_clicks")],
        prevent_initial_call=True,
    )
    def handle_new_project(n_clicks):
        """Handle creating a new project."""
        noop = (dash.no_update,) * (len(MAIN_TAB_IDS) + 6)
        if n_clicks:
            # Clear all data storage (includes rule_defaults_overrides from rules.defaults).
            dash_storage.clear_data()
            
            # Reset to default values
            dash_storage.set_data("project_name", "")
            dash_storage.set_data("workspace", "")
            dash_storage.set_data("filename", "")
            dash_storage.set_data("analysis_date", "")
            dash_storage.set_data("mar_purpose", ["secure_water_supply"])
            dash_storage.set_data("ground_surface_slope", 0.5)
            dash_storage.set_data("max_available_area", 1.0)
            dash_storage.set_data("land_use", "Residential")
            dash_storage.set_data("water_source", "surface_water_sources")
            dash_storage.set_data("proximity_distance", 1.0)
            dash_storage.set_data("water_conveyance", "open_canals_ditches")
            dash_storage.set_data("water_ownership", "legal_rights")
            dash_storage.set_data("pumping_needed", "no")
            dash_storage.set_data("monthly_flow", [0.0] * 12)
            dash_storage.set_data("view_runoff_calculator", False)
            dash_storage.set_data("view_recharge_mound_outputs", False)
            dash_storage.set_data("view_treatment_cost_guidance", False)
            dash_storage.set_data("physical_parameters", [])
            dash_storage.set_data("chemical_parameters", [])
            dash_storage.set_data("biological_indicators", [])
            dash_storage.set_data("emerging_contaminants", [])
            # Reset water quality screening
            dash_storage.set_data("wq_source_contaminants", "Unknown")
            dash_storage.set_data("wq_source_turbidity", "Unknown")
            dash_storage.set_data("wq_vadose_impacted", "Unknown")
            dash_storage.set_data("wq_aquifer_anthropogenic", "Unknown")
            dash_storage.set_data("wq_aquifer_natural", "Unknown")
            dash_storage.set_data("vadose_zone_pollution", "None")
            # Reset hydrogeology data
            dash_storage.set_data("aq_type", "unconfined")
            dash_storage.set_data("confined_aquifer_head_ft", None)
            dash_storage.set_data("max_dry_well_depth_ft", 120.0)
            dash_storage.set_data("aquitard_conductivity_ft_day", 1e-3)
            _strat_new = default_stratigraphy_layers()
            normalize_stratigraphy_recharge_target(_strat_new)
            dash_storage.set_data("stratigraphy_data", _strat_new)
            dash_storage.set_data(
                "groundwater_data", normalize_groundwater_data([])
            )
            dash_storage.set_data("ground_surface_elevation", 120.0)
            dash_storage.set_data("max_mar_storage_depth", 20.0)
            dash_storage.set_data("extension_length", 100.0)
            dash_storage.set_data("extension_width", 50.0)
            dash_storage.set_data("extension_rotation", 0.0)
            dash_storage.set_data("upstream_head", 10.0)
            dash_storage.set_data("downstream_head", 5.0)
            dash_storage.set_data("overview_map_lat", DEFAULT_OVERVIEW_MAP_LAT)
            dash_storage.set_data("overview_map_lon", DEFAULT_OVERVIEW_MAP_LON)
            dash_storage.set_data("overview_map_zoom", DEFAULT_OVERVIEW_MAP_ZOOM)
            dash_storage.set_data("overview_map_location_label", "")
            dash_storage.set_data("overview_map_basemap", DEFAULT_OVERVIEW_MAP_BASEMAP)

            import dash_bootstrap_components as dbc
            empty_rest = [[] for _ in range(len(MAIN_TAB_IDS) - 1)]
            return (
                [
                    dbc.Alert(
                        "New project created! All data has been reset to defaults.",
                        color="info",
                        className="mb-3",
                    )
                ],
                create_overview_content(),
                *empty_rest,
                "overview",
                stratigraphy_store_payload_from_storage(),
                normalize_groundwater_data(dash_storage.get_data("groundwater_data") or []),
                "",
                "",
            )
        return noop

    @app.callback(
        Output("close-project-modal", "is_open"),
        [
            Input("btn-close", "n_clicks"),
            Input("btn-close-cancel", "n_clicks"),
        ],
        prevent_initial_call=True,
    )
    def toggle_close_project_modal(close_clicks, cancel_clicks):
        """Open or dismiss the close-project confirmation dialog."""
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update
        triggered = ctx.triggered[0]["prop_id"].split(".")[0]
        if triggered == "btn-close" and close_clicks:
            return True
        if triggered == "btn-close-cancel" and cancel_clicks:
            return False
        return dash.no_update

    @app.callback(
        Output("about-modal", "is_open"),
        [
            Input("btn-about", "n_clicks"),
            Input("btn-about-close", "n_clicks"),
        ],
        prevent_initial_call=True,
    )
    def toggle_about_modal(about_clicks, close_clicks):
        """Open or dismiss the About MAR-Tool dialog."""
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update
        triggered = ctx.triggered[0]["prop_id"].split(".")[0]
        if triggered == "btn-about" and about_clicks:
            return True
        if triggered == "btn-about-close" and close_clicks:
            return False
        return dash.no_update

    @app.callback(
        Output("close-project-modal", "is_open", allow_duplicate=True),
        Output("main-content-flash", "children", allow_duplicate=True),
        Output(main_tab_panel_id("overview"), "children", allow_duplicate=True),
        Output("top-tabs", "active_tab", allow_duplicate=True),
        Input("btn-close-confirm", "n_clicks"),
        prevent_initial_call=True,
    )
    def confirm_close_project(confirm_clicks):
        """Clear the project file association after user confirms."""
        if not confirm_clicks:
            return (dash.no_update,) * 4

        dash_storage.set_data("workspace", "")
        dash_storage.set_data("filename", "")

        return (
            False,
            [
                dbc.Alert(
                    "Closing MAR DSS… If this tab remains open, you may close it manually.",
                    color="info",
                    className="mb-3",
                )
            ],
            create_overview_content(),
            "overview",
        )

    app.clientside_callback(
        ClientsideFunction(
            namespace="clientside",
            function_name="attemptCloseBrowserTab",
        ),
        Output("close-browser-hook", "children"),
        Input("btn-close-confirm", "n_clicks"),
        prevent_initial_call=True,
    )

    # Callback for Save As button - native browse dialog (same pattern as Open)
    @app.callback(
        Output("main-content-flash", "children", allow_duplicate=True),
        Output(main_tab_panel_id("overview"), "children", allow_duplicate=True),
        Output("project-path-input", "value", allow_duplicate=True),
        Output("top-tabs", "active_tab", allow_duplicate=True),
        [Input("btn-save-as", "n_clicks")],
        prevent_initial_call=True,
    )
    def handle_save_as_project(n_clicks):
        """Pick a save location (Tk dialog) and write the current project there."""
        noop_as = (dash.no_update, dash.no_update, dash.no_update, dash.no_update)
        if not n_clicks:
            return noop_as

        try:
            result = _save_project_via_picker(_default_project_filename())
            if result[0] is None:
                return noop_as
            picked, path_out = result
            return (
                [
                    dbc.Alert(
                        f"Project saved successfully at {picked}",
                        color="success",
                        className="mb-3",
                    ),
                ],
                create_overview_content(),
                path_out,
                "overview",
            )
        except Exception as e:
            return (
                [
                    dbc.Alert(
                        f"Error saving project: {str(e)}",
                        color="danger",
                        className="mb-3",
                    ),
                ],
                create_overview_content(),
                dash.no_update,
                "overview",
            )

    setup_overview_callbacks(app)
    # Client-side resize to force Leaflet/Mapbox to re-render when tab becomes visible
    app.clientside_callback(
        ClientsideFunction(namespace="clientside", function_name="resizeMapOnTab"),
        Output("runoff-map", "id", allow_duplicate=True),  # dummy output; will always return no_update
        [
            Input("top-tabs", "active_tab"),
            Input("optional-runoff-tabs", "active_tab"),
        ],
        prevent_initial_call=True,
    )

    @app.callback(
        Output("water-source-config-help-modal", "is_open"),
        [
            Input("water-source-config-help-btn", "n_clicks"),
            Input("water-source-config-help-close-btn", "n_clicks"),
        ],
        State("water-source-config-help-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_water_source_configuration_help_modal(open_clicks, close_clicks, is_open):
        """Open or close the Water Source Configuration help popup."""
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger == "water-source-config-help-btn":
            return True
        if trigger == "water-source-config-help-close-btn":
            return False
        return bool(is_open)

    @app.callback(
        Output("volume-estimates-help-modal", "is_open"),
        [
            Input("volume-estimates-help-btn", "n_clicks"),
            Input("volume-estimates-help-close-btn", "n_clicks"),
        ],
        State("volume-estimates-help-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_volume_estimates_help_modal(open_clicks, close_clicks, is_open):
        """Open or close the Flow Estimates help popup."""
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger == "volume-estimates-help-btn":
            return True
        if trigger == "volume-estimates-help-close-btn":
            return False
        return bool(is_open)

    @app.callback(
        Output("optional-runoff-help-modal", "is_open"),
        [
            Input("optional-runoff-help-btn", "n_clicks"),
            Input("optional-runoff-help-close-btn", "n_clicks"),
        ],
        State("optional-runoff-help-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_optional_runoff_help_modal(open_clicks, close_clicks, is_open):
        """Open or close the Optional Runoff Calculations help popup."""
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger == "optional-runoff-help-btn":
            return True
        if trigger == "optional-runoff-help-close-btn":
            return False
        return bool(is_open)

    @app.callback(
        Output("optional-runoff-calculations-collapse", "is_open"),
        Input("view-runoff-calculator-check", "value"),
        prevent_initial_call=True,
    )
    def toggle_optional_runoff_calculations(view_runoff):
        """Show or hide Optional Runoff Calculations when the view checkbox changes."""
        checked = bool(view_runoff)
        dash_storage.set_data("view_runoff_calculator", checked)
        return checked

    # Callback for water source dropdown - saves to data storage
    @app.callback(
        Output("water-source-dropdown", "value"),
        [
            Input("water-source-dropdown", "value"),
            Input("water-source-dropdown", "id")
        ],
        prevent_initial_call=False
    )
    def handle_water_source_selection(value, component_id):
        """Handle water source selection and save to data storage."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved water source or use default, and save it
            water_source = dash_storage.get_data("water_source") or "surface_water_sources"
            dash_storage.set_data("water_source", water_source)
            return water_source
        
        # Get the current selection
        current_selection = value if value else "surface_water_sources"
        
        # Save water source selection to data storage
        dash_storage.set_data("water_source", current_selection)
        
        return current_selection

    @app.callback(
        Output("optional-runoff-water-source-warning", "children"),
        Input("water-source-dropdown", "value"),
        prevent_initial_call=False,
    )
    def update_optional_runoff_water_source_warning(water_source):
        """Warn when runoff calculator is used with a non-surface-runoff water source."""
        try:
            from mar_dss.app.components.water_source_tab import (
                RUNOFF_CALCULATOR_SOURCE_WARNING,
                RUNOFF_RELEVANT_WATER_SOURCES,
            )
        except ImportError:
            from .components.water_source_tab import (
                RUNOFF_CALCULATOR_SOURCE_WARNING,
                RUNOFF_RELEVANT_WATER_SOURCES,
            )

        source = water_source or dash_storage.get_data("water_source") or "surface_water_sources"
        if source in RUNOFF_RELEVANT_WATER_SOURCES:
            return []
        return dbc.Alert(
            RUNOFF_CALCULATOR_SOURCE_WARNING,
            color="warning",
            className="mb-3",
        )

    @app.callback(
        Output("water-source-map-site-radio", "value"),
        [
            Input("water-source-map-site-radio", "value"),
            Input("water-source-map-site-radio", "id"),
        ],
        prevent_initial_call=False,
    )
    def handle_water_source_map_site_selection(value, component_id):
        """Persist Source vs Recharge site choice for the Water Source map card."""
        ctx = dash.callback_context
        valid = frozenset({"source_site", "recharge_site"})

        if not ctx.triggered:
            site = dash_storage.get_data("water_source_map_site") or "source_site"
            if site not in valid:
                site = "source_site"
            dash_storage.set_data("water_source_map_site", site)
            return site

        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1]
        if trigger_prop == "id":
            site = dash_storage.get_data("water_source_map_site") or "source_site"
            return site if site in valid else "source_site"

        current = value if value in valid else "source_site"
        dash_storage.set_data("water_source_map_site", current)
        return current

    # Note: The Water Source tab no longer shows the "Proximity Distance" control, so
    # the callback for `proximity-distance-input` was removed. The storage key remains
    # initialized for backward compatibility / reporting.

    # Note: The Water Source tab no longer shows the "Water Conveyance" dropdown, so the
    # callback for `water-conveyance-dropdown` was removed. `water_conveyance` remains
    # initialized on new project for backward compatibility / reporting.

    # Note: The Water Source tab no longer shows the "Water Ownership" and "Pumping Needed"
    # radio controls, so the callbacks for those component ids were removed. The storage
    # keys remain initialized for backward compatibility / reporting.

    # Note: The "Water Quality Parameters" card was removed from the UI, so the
    # checklist callbacks for those controls were removed as well. The underlying
    # storage keys (physical_parameters, chemical_parameters, etc.) are still
    # initialized elsewhere for backward compatibility.

