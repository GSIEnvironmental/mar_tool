"""
Overview tab callbacks for MAR DSS dashboard.
"""

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, html, dependencies
from dash.dependencies import ClientsideFunction
import mar_dss.app.utils.data_storage as dash_storage
import mar_dss.app.utils.helpers as helpers
import ast
import json
import os

import pandas as pd

try:
    from mar_dss.app.utils.native_file_dialog import ask_open_project_path
    from mar_dss.app.utils.project_file_path import format_project_path, split_project_path
except ImportError:
    from ..utils.native_file_dialog import ask_open_project_path
    from ..utils.project_file_path import format_project_path, split_project_path

# Import the overview content creation function
try:
    from mar_dss.app.components.overview_tab import (
        create_overview_content,
        get_overview_map_header_text,
        get_overview_map_figure_params,
        ALLOWED_OVERVIEW_BASEMAP_STYLES,
        DEFAULT_OVERVIEW_MAP_BASEMAP,
    )
    from mar_dss.app.components.water_source_tab import (
        create_location_map,
        build_water_source_location_map_figure,
        water_source_site_coordinates_summary_children,
    )
    from mar_dss.app.components.layout import main_tab_panel_id
except ImportError:
    from ..components.overview_tab import (
        create_overview_content,
        get_overview_map_header_text,
        get_overview_map_figure_params,
        ALLOWED_OVERVIEW_BASEMAP_STYLES,
        DEFAULT_OVERVIEW_MAP_BASEMAP,
    )
    from ..components.water_source_tab import (
        create_location_map,
        build_water_source_location_map_figure,
        water_source_site_coordinates_summary_children,
    )
    from ..components.layout import main_tab_panel_id


def _extract_mapbox_view_from_relayout(relayout_data):
    """Parse Plotly mapbox relayout payload for center and zoom."""
    if not relayout_data:
        return None, None, None
    lat = lon = zoom = None
    z = relayout_data.get("mapbox.zoom")
    if z is not None:
        try:
            zoom = float(z)
        except (TypeError, ValueError):
            pass
    center = relayout_data.get("mapbox.center")
    if isinstance(center, dict):
        try:
            lat = float(center["lat"])
            lon = float(center["lon"])
        except (KeyError, TypeError, ValueError):
            pass
    if lat is None and "mapbox.center.lat" in relayout_data:
        try:
            lat = float(relayout_data["mapbox.center.lat"])
        except (TypeError, ValueError):
            pass
    if lon is None and "mapbox.center.lon" in relayout_data:
        try:
            lon = float(relayout_data["mapbox.center.lon"])
        except (TypeError, ValueError):
            pass
    return lat, lon, zoom


def _relayout_has_mapbox_camera(relayout_data):
    """True when relayout reflects user map camera (not autosize/width churn)."""
    if not relayout_data or not isinstance(relayout_data, dict):
        return False
    for key in relayout_data:
        if key == "mapbox.zoom":
            return True
        if key.startswith("mapbox.center"):
            return True
    return False


def _persist_shared_map_view_from_relayout(relayout_data):
    """Write lat/lon/zoom/project_location labels from Plotly ``relayoutData``.

    Returns ``(header_text, project_location_value)`` where *header_text*
    is suitable for both map card headers after storage updates.

    Used by Overview-only and Water Source-only callbacks so each callback
    does not reference graphs that disappear when swapping top-level tabs.
    """
    old_lat = dash_storage.get_data("overview_map_lat")
    old_lon = dash_storage.get_data("overview_map_lon")
    stored_project_location = dash_storage.get_data("project_location") or ""

    lat, lon, zoom = _extract_mapbox_view_from_relayout(relayout_data)
    if lat is not None:
        dash_storage.set_data("overview_map_lat", lat)
    if lon is not None:
        dash_storage.set_data("overview_map_lon", lon)
    if zoom is not None:
        dash_storage.set_data("overview_map_zoom", zoom)

    center_changed = False
    if lat is not None and lon is not None:
        try:
            ola = float(old_lat) if old_lat is not None else None
            olo = float(old_lon) if old_lon is not None else None
            center_changed = (
                ola is None
                or olo is None
                or abs(ola - lat) > 0.002
                or abs(olo - lon) > 0.002
            )
        except (TypeError, ValueError):
            center_changed = True

    location_name = None
    if center_changed and lat is not None and lon is not None:
        try:
            from mar_dss.app.components.water_source_tab import get_location_details
        except ImportError:
            from ..components.water_source_tab import get_location_details

        location_name = get_location_details(lat, lon)
        dash_storage.set_data("project_location", location_name)
        dash_storage.set_data(
            "overview_map_location_label",
            f"Project Location — {location_name}",
        )

    hdr = get_overview_map_header_text()

    if location_name is not None:
        return hdr, location_name

    return hdr, stored_project_location


def setup_overview_callbacks(app):
    """Set up all overview-related callbacks."""
    
    # Combined callback for project name input - handles all triggers
    @app.callback(
        Output("project-name-input", "value"),
        [
            Input("project-name-input", "value"),
            Input("project-name-input", "n_blur"),
            Input("project-name-input", "n_submit"),
            Input("project-name-input", "id")
        ],
        prevent_initial_call=False
    )
    def handle_project_name(value, n_blur, n_submit, component_id):
        """Handle project name input for all triggers: value change, blur, submit, and load."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved project name or use default, and save it
            project_name = dash_storage.get_data("project_name") or ""
            dash_storage.set_data("project_name", project_name)
            return project_name
        
        # Get the current value from the input
        current_value = value if value else ""
        
        # Determine which trigger caused the callback
        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1]
        
        # Save project name for all triggers except initial load
        if trigger_prop != "id" and current_value:
            dash_storage.set_data("project_name", current_value)
        
        return current_value

    # Combined callback for analysis date input - handles all triggers
    @app.callback(
        Output("analysis-date-input", "value"),
        [
            Input("analysis-date-input", "value"),
            Input("analysis-date-input", "n_blur"),
            Input("analysis-date-input", "n_submit"),
            Input("analysis-date-input", "id")
        ],
        prevent_initial_call=False
    )
    def handle_analysis_date(value, n_blur, n_submit, component_id):
        """Handle analysis date input for all triggers: value change, blur, submit, and load."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved analysis date or use default, and save it
            analysis_date = dash_storage.get_data("analysis_date")
            if analysis_date:
                # Ensure date is in YYYY-MM-DD format
                try:
                    if isinstance(analysis_date, str) and len(analysis_date) == 10 and analysis_date[4] == '-' and analysis_date[7] == '-':
                        formatted_date = analysis_date
                    else:
                        # Try to parse and reformat the date
                        from datetime import datetime
                        parsed_date = helpers.parse_unknown_date(analysis_date)
                        formatted_date = parsed_date.strftime("%Y-%m-%d")
                    dash_storage.set_data("analysis_date", formatted_date)
                    return formatted_date
                except:
                    # If parsing fails, use today's date
                    from datetime import datetime
                    default_date = datetime.now().strftime("%Y-%m-%d")
                    dash_storage.set_data("analysis_date", default_date)
                    return default_date
            else:
                # No data in storage, use today's date
                from datetime import datetime
                default_date = datetime.now().strftime("%Y-%m-%d")
                dash_storage.set_data("analysis_date", default_date)
                return default_date
        
        # Get the current value from the input
        current_value = value if value else ""
        
        # Determine which trigger caused the callback
        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1]
        
        # Save analysis date for all triggers except initial load
        if trigger_prop != "id" and current_value:
            # Ensure date is in YYYY-MM-DD format before saving
            try:
                from datetime import datetime
                # If it's already in correct format, use it
                if isinstance(current_value, str) and len(current_value) == 10 and current_value[4] == '-' and current_value[7] == '-':
                    formatted_date = current_value
                else:
                    # Try to parse and reformat
                    parsed_date = datetime.strptime(str(current_value), "%Y-%m-%d")
                    formatted_date = parsed_date.strftime("%Y-%m-%d")
                dash_storage.set_data("analysis_date", formatted_date)
            except:
                # If formatting fails, save as is
                dash_storage.set_data("analysis_date", current_value)
        
        return current_value

    # Callback for MAR purpose checklist - saves selections to data storage
    @app.callback(
        Output("mar-purpose-checklist", "value"),
        [
            Input("mar-purpose-checklist", "value"),
            Input("mar-purpose-checklist", "id")
        ],
        prevent_initial_call=False
    )
    def handle_mar_purpose_selections(value, component_id):
        """Handle MAR purpose checklist selections and save to data storage."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved MAR purpose selections or use default, and save it
            mar_purpose = dash_storage.get_data("mar_purpose") or ["secure_water_supply"]
            dash_storage.set_data("mar_purpose", mar_purpose)
            return mar_purpose
        
        # Get the current selections
        current_selections = value if value else []
        
        # Save MAR purpose selections to data storage
        if current_selections:
            dash_storage.set_data("mar_purpose", current_selections)
        
        return current_selections

    def _overview_map_figure_with_style(
        style_value,
        uirevision="mar-overview-location-map",
        *,
        fill_container=False,
    ):
        """Shared basemap + figure build for Overview and Water Source maps."""
        style = (
            style_value
            if style_value in ALLOWED_OVERVIEW_BASEMAP_STYLES
            else DEFAULT_OVERVIEW_MAP_BASEMAP
        )
        dash_storage.set_data("overview_map_basemap", style)
        lat, lon, zoom, marker_name, _ = get_overview_map_figure_params()
        return create_location_map(
            lat=lat,
            lon=lon,
            location_name=marker_name,
            zoom=float(zoom),
            map_style=style,
            uirevision=uirevision,
            fill_container=fill_container,
        )

    @app.callback(
        Output("location-map", "figure"),
        Input("overview-map-basemap", "value"),
        prevent_initial_call=True,
    )
    def apply_overview_map_basemap_overview(style_overview):
        return _overview_map_figure_with_style(style_overview)

    @app.callback(
        Output("water-source-location-map", "figure"),
        Input("water-source-overview-map-basemap", "value"),
        prevent_initial_call=True,
    )
    def apply_overview_map_basemap_water_source(style_ws):
        style = (
            style_ws
            if style_ws in ALLOWED_OVERVIEW_BASEMAP_STYLES
            else DEFAULT_OVERVIEW_MAP_BASEMAP
        )
        dash_storage.set_data("overview_map_basemap", style)
        return build_water_source_location_map_figure(style)

    app.clientside_callback(
        ClientsideFunction(
            namespace="clientside",
            function_name="installWaterSourceMapClickRelay",
        ),
        Output("water-source-map-click-relay-hook", "children"),
        [
            Input("water-source-location-map", "figure"),
            Input("top-tabs", "active_tab"),
        ],
    )

    @app.callback(
        Output("water-source-location-map", "figure", allow_duplicate=True),
        Input("water-source-map-mapbox-click-store", "data"),
        [
            State("water-source-overview-map-basemap", "value"),
            State("water-source-map-site-radio", "value"),
        ],
        prevent_initial_call=True,
    )
    def place_water_source_site_from_map_click(
        picked,
        basemap_dropdown_value,
        map_site_radio_value,
    ):
        """Place Source / Recharge from map picks (relay fills ``picked`` lat/lon)."""
        if not picked or not isinstance(picked, dict):
            return dash.no_update

        lat = picked.get("lat")
        lon = picked.get("lon")
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (TypeError, ValueError):
            return dash.no_update

        role = map_site_radio_value
        if role not in ("source_site", "recharge_site"):
            role = "source_site"

        if role == "recharge_site":
            dash_storage.set_data("water_map_recharge_lat", lat_f)
            dash_storage.set_data("water_map_recharge_lon", lon_f)
        else:
            dash_storage.set_data("water_map_source_lat", lat_f)
            dash_storage.set_data("water_map_source_lon", lon_f)

        bm = basemap_dropdown_value
        if bm not in ALLOWED_OVERVIEW_BASEMAP_STYLES:
            bm = DEFAULT_OVERVIEW_MAP_BASEMAP

        return build_water_source_location_map_figure(bm)

    @app.callback(
        Output("water-source-site-coordinates-summary", "children"),
        [
            Input("water-source-location-map", "figure"),
            Input("top-tabs", "active_tab"),
        ],
    )
    def update_water_source_site_coordinates_summary(_figure, _active_tab):
        """Refresh lat/lon/distance when map markers move or user switches tabs."""
        return water_source_site_coordinates_summary_children()

    # Overview-map pan/zoom and Project Location (components exist only on Overview tab)
    @app.callback(
        Output("location-card-header", "children"),
        Output("project-location-input", "value"),
        [
            Input("location-map", "relayoutData"),
            Input("project-location-input", "value"),
            Input("project-location-input", "n_blur"),
            Input("project-location-input", "n_submit"),
            Input("project-location-input", "id"),
        ],
        prevent_initial_call=False,
    )
    def update_overview_location_card_and_project_place(
        relayout_overview,
        project_location_value,
        n_blur,
        n_submit,
        component_id,
    ):
        ctx = dash.callback_context
        stored_project_location = dash_storage.get_data("project_location") or ""

        trigger_id = None
        trigger_prop = None
        if ctx.triggered:
            trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
            trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1]

        if trigger_id == "location-map":
            if not _relayout_has_mapbox_camera(relayout_overview):
                return dash.no_update, dash.no_update
            hdr, loc_inp = _persist_shared_map_view_from_relayout(relayout_overview)
            return hdr, loc_inp

        if trigger_id == "project-location-input" and trigger_prop != "id":
            current_value = (project_location_value or "").strip()
            dash_storage.set_data("project_location", current_value)
            if current_value:
                dash_storage.set_data(
                    "overview_map_location_label",
                    f"Project Location — {current_value}",
                )
            return get_overview_map_header_text(), current_value

        return get_overview_map_header_text(), stored_project_location

    @app.callback(
        Output("water-source-location-card-header", "children"),
        Input("water-source-location-map", "relayoutData"),
        prevent_initial_call=True,
    )
    def update_water_source_location_card_only(relayout_water):
        if not _relayout_has_mapbox_camera(relayout_water):
            return dash.no_update
        hdr, _ = _persist_shared_map_view_from_relayout(relayout_water)
        return hdr

    # Combined project path (workspace + file name) — kept as two storage keys for save/load CSV
    @app.callback(
        Output("project-path-input", "value"),
        [
            Input("project-path-input", "value"),
            Input("project-path-input", "n_blur"),
            Input("project-path-input", "n_submit"),
            Input("project-path-input", "id"),
        ],
        prevent_initial_call=False,
    )
    def handle_project_path_input(value, n_blur, n_submit, component_id):
        """Sync workspace + filename storage from one full path string."""
        ctx = dash.callback_context

        if not ctx.triggered:
            display = format_project_path(
                dash_storage.get_data("workspace"),
                dash_storage.get_data("filename"),
            )
            ws, fn = split_project_path(display)
            dash_storage.set_data("workspace", ws)
            dash_storage.set_data("filename", fn)
            return display

        raw = value if isinstance(value, str) else ""
        current_value = raw.strip()
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1]

        if trigger_prop != "id":
            if current_value:
                ws, fn = split_project_path(current_value)
                dash_storage.set_data("workspace", ws)
                dash_storage.set_data("filename", fn)
                return format_project_path(ws, fn)
            dash_storage.set_data("workspace", "")
            dash_storage.set_data("filename", "")
            return ""

        return format_project_path(
            dash_storage.get_data("workspace"),
            dash_storage.get_data("filename"),
        )

    def _load_project_rows_into_storage(df):
        """Populate dash_storage from a key/value CSV export."""
        for _, row in df.iterrows():
            key = row["key"]
            value = row["value"]

            if isinstance(value, str):
                if value.startswith("[") and value.endswith("]"):
                    try:
                        value = ast.literal_eval(value)
                    except (ValueError, SyntaxError):
                        pass
                elif value.startswith("{") and value.endswith("}"):
                    try:
                        value = ast.literal_eval(value)
                    except (ValueError, SyntaxError):
                        pass

            dash_storage.set_data(key, value)

    # Callback for Open button - load project from file (native picker when available)
    @app.callback(
        Output("main-content-flash", "children", allow_duplicate=True),
        Output(main_tab_panel_id("overview"), "children", allow_duplicate=True),
        Output("project-path-input", "value", allow_duplicate=True),
        Output("top-tabs", "active_tab", allow_duplicate=True),
        [Input("btn-open", "n_clicks")],
        prevent_initial_call=True,
    )
    def handle_open_project(n_clicks):
        """Pick a CSV/JSON project file (Tk dialog) then load into storage."""
        noop = (dash.no_update, dash.no_update, dash.no_update, dash.no_update)
        if not n_clicks:
            return noop

        picked = ask_open_project_path()

        # User dismissed the native picker without choosing a path
        if picked == "":
            return noop

        if isinstance(picked, str) and picked:
            fn = picked
            workspace_dir, base_name = split_project_path(fn)
            dash_storage.set_data("workspace", workspace_dir)
            dash_storage.set_data("filename", base_name)
            path_out = format_project_path(workspace_dir, base_name)
        else:
            # Tk unavailable: use combined path from storage
            data = dash_storage.get_data_storage()
            fn = format_project_path(data.get("workspace"), data.get("filename"))
            path_out = dash.no_update
            if not (fn or "").strip():
                return (
                    [
                        dbc.Alert(
                            "Native file picker is unavailable here. Enter a full project "
                            "file path, then click Load.",
                            color="danger",
                            className="mb-3",
                        ),
                    ],
                    create_overview_content(),
                    dash.no_update,
                    "overview",
                )
            fn = os.path.normpath(fn.strip())

        if not os.path.exists(fn):
            return (
                [
                    dbc.Alert(
                        f"File does not exist: {fn}",
                        color="danger",
                        className="mb-3",
                    ),
                ],
                create_overview_content(),
                path_out,
                "overview",
            )

        try:
            suffix = os.path.splitext(fn)[1].lower()
            if suffix == ".json":
                with open(fn, encoding="utf-8") as f:
                    blob = json.load(f)
                if isinstance(blob, dict):
                    for key, value in blob.items():
                        dash_storage.set_data(key, value)
                else:
                    raise ValueError("JSON project must contain an object at the root.")
            else:
                df = pd.read_csv(fn)
                if not {"key", "value"} <= set(df.columns):
                    raise ValueError(
                        "CSV project must contain 'key' and 'value' columns."
                    )
                print(f"Loaded CSV with {len(df)} rows")
                _load_project_rows_into_storage(df)

            if dash_storage.get_data("overview_map_basemap") == "stamen-terrain":
                dash_storage.set_data("overview_map_basemap", "opentopomap")

            path_after = format_project_path(
                dash_storage.get_data("workspace"),
                dash_storage.get_data("filename"),
            )
            return (
                [
                    dbc.Alert(
                        f"Project loaded successfully from {fn}",
                        color="success",
                        className="mb-3",
                    ),
                ],
                create_overview_content(),
                path_after or path_out,
                "overview",
            )
        except Exception as e:
            return (
                [
                    dbc.Alert(
                        f"Error loading project: {str(e)}",
                        color="danger",
                        className="mb-3",
                    ),
                ],
                create_overview_content(),
                path_out,
                "overview",
            )

    # Callback for ground surface slope input - saves to data storage
    @app.callback(
        Output("ground-slope-input", "value"),
        [
            Input("ground-slope-input", "value"),
            Input("ground-slope-input", "n_blur"),
            Input("ground-slope-input", "n_submit"),
            Input("ground-slope-input", "id")
        ],
        prevent_initial_call=False
    )
    def handle_ground_slope_input(value, n_blur, n_submit, component_id):
        """Handle ground surface slope input for all triggers: value change, blur, submit, and load."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved ground slope or use default, and save it
            ground_slope = dash_storage.get_data("ground_surface_slope") or 0.5
            dash_storage.set_data("ground_surface_slope", ground_slope)
            return ground_slope
        
        # Get the current value from the input
        current_value = value if value is not None else 0.5
        
        # Determine which trigger caused the callback
        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1]
        
        # Save ground slope for all triggers except initial load
        if trigger_prop != "id":
            dash_storage.set_data("ground_surface_slope", current_value)
        
        return current_value

    # Callback for maximum available area input - saves to data storage
    @app.callback(
        Output("max-area-input", "value"),
        [
            Input("max-area-input", "value"),
            Input("max-area-input", "n_blur"),
            Input("max-area-input", "n_submit"),
            Input("max-area-input", "id")
        ],
        prevent_initial_call=False
    )
    def handle_max_area_input(value, n_blur, n_submit, component_id):
        """Handle maximum available area input for all triggers: value change, blur, submit, and load."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved max area or use default, and save it
            max_area = dash_storage.get_data("max_available_area") or 1.0
            dash_storage.set_data("max_available_area", max_area)
            return max_area
        
        # Get the current value from the input
        current_value = value if value is not None else 1.0
        
        # Determine which trigger caused the callback
        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1]
        
        # Save max area for all triggers except initial load
        if trigger_prop != "id":
            dash_storage.set_data("max_available_area", current_value)
        
        return current_value

    # Callback for land use dropdown - saves to data storage
    @app.callback(
        Output("land-use-dropdown", "value"),
        [
            Input("land-use-dropdown", "value"),
            Input("land-use-dropdown", "id")
        ],
        prevent_initial_call=False
    )
    def handle_land_use_selection(value, component_id):
        """Handle land use dropdown selection and save to data storage."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved land use or use default, and save it
            land_use = dash_storage.get_data("land_use") or "Urban Residential"
            dash_storage.set_data("land_use", land_use)
            return land_use
        
        # Get the current selection
        current_selection = value if value else "Urban Residential"
        
        # Save land use selection to data storage
        dash_storage.set_data("land_use", current_selection)
        
        return current_selection

