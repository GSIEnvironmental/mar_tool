"""
Overview tab callbacks for MAR DSS dashboard.
"""

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, html, dependencies
import mar_dss.app.utils.data_storage as dash_storage
import mar_dss.app.utils.helpers as helpers
import ast
import json
import os

import pandas as pd

try:
    from mar_dss.app.utils.native_file_dialog import ask_open_project_path
except ImportError:
    from ..utils.native_file_dialog import ask_open_project_path

# Import the overview content creation function
try:
    from mar_dss.app.components.overview_tab import (
        create_overview_content,
        get_overview_map_header_text,
        get_overview_map_figure_params,
        ALLOWED_OVERVIEW_BASEMAP_STYLES,
        DEFAULT_OVERVIEW_MAP_BASEMAP,
    )
    from mar_dss.app.components.water_source_tab import create_location_map
except ImportError:
    from ..components.overview_tab import (
        create_overview_content,
        get_overview_map_header_text,
        get_overview_map_figure_params,
        ALLOWED_OVERVIEW_BASEMAP_STYLES,
        DEFAULT_OVERVIEW_MAP_BASEMAP,
    )
    from ..components.water_source_tab import create_location_map


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

    @app.callback(
        Output("location-map", "figure"),
        Input("overview-map-basemap", "value"),
        prevent_initial_call=True,
    )
    def apply_overview_map_basemap(style):
        """Rebuild map tiles only; center/zoom come from storage (last pan/zoom)."""
        style = style if style in ALLOWED_OVERVIEW_BASEMAP_STYLES else DEFAULT_OVERVIEW_MAP_BASEMAP
        dash_storage.set_data("overview_map_basemap", style)
        lat, lon, zoom, marker_name, _ = get_overview_map_figure_params()
        return create_location_map(
            lat=lat,
            lon=lon,
            location_name=marker_name,
            zoom=float(zoom),
            map_style=style,
        )

    # Map pan/zoom: persist center & zoom, update header label, and (optionally) fill Project Location input
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
    def update_location_title_and_input(relayout_data, project_location_value, n_blur, n_submit, component_id):
        """Persist overview map view (lat/lon/zoom) and keep Project Location in sync.

        - When the user pans/zooms the map: reverse-geocode the center and fill the input.
        - When the user edits the input: store it and update the header label.
        """
        ctx = dash.callback_context

        old_lat = dash_storage.get_data("overview_map_lat")
        old_lon = dash_storage.get_data("overview_map_lon")

        # Default to stored value on initial load
        stored_project_location = dash_storage.get_data("project_location") or ""

        trigger_id = None
        trigger_prop = None
        if ctx.triggered:
            trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
            trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1]

        # 1) Map moved: update stored view + reverse-geocode (only when moved meaningfully)
        if trigger_id == "location-map":
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
                return get_overview_map_header_text(), location_name

            # No meaningful change: keep current stored input
            return get_overview_map_header_text(), stored_project_location

        # 2) User edited the Project Location input: store it and update header
        if trigger_id == "project-location-input" and trigger_prop != "id":
            current_value = (project_location_value or "").strip()
            dash_storage.set_data("project_location", current_value)
            if current_value:
                dash_storage.set_data(
                    "overview_map_location_label",
                    f"Project Location — {current_value}",
                )
            return get_overview_map_header_text(), current_value

        # Initial load / unrelated triggers: keep stored values
        return get_overview_map_header_text(), stored_project_location

    # Callback for workspace input - saves to data storage
    @app.callback(
        Output("workspace-input", "value"),
        [
            Input("workspace-input", "value"),
            Input("workspace-input", "n_blur"),
            Input("workspace-input", "n_submit"),
            Input("workspace-input", "id")
        ],
        prevent_initial_call=False
    )
    def handle_workspace_input(value, n_blur, n_submit, component_id):
        """Handle workspace input for all triggers: value change, blur, submit, and load."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved workspace or use default, and save it
            workspace = dash_storage.get_data("workspace") or ""
            dash_storage.set_data("workspace", workspace)
            return workspace
        
        # Get the current value from the input
        current_value = value if value else ""
        
        # Determine which trigger caused the callback
        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1]
        
        # Save workspace for all triggers except initial load
        if trigger_prop != "id" and current_value:
            dash_storage.set_data("workspace", current_value)
        
        return current_value

    # Callback for filename input - saves to data storage
    @app.callback(
        Output("filename-input", "value"),
        [
            Input("filename-input", "value"),
            Input("filename-input", "n_blur"),
            Input("filename-input", "n_submit"),
            Input("filename-input", "id")
        ],
        prevent_initial_call=False
    )
    def handle_filename_input(value, n_blur, n_submit, component_id):
        """Handle filename input for all triggers: value change, blur, submit, and load."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved filename or use default, and save it
            filename = dash_storage.get_data("filename") or ""
            dash_storage.set_data("filename", filename)
            return filename
        
        # Get the current value from the input
        current_value = value if value else ""
        
        # Determine which trigger caused the callback
        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1]
        
        # Save filename for all triggers except initial load
        if trigger_prop != "id" and current_value:
            dash_storage.set_data("filename", current_value)
        
        return current_value

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
        Output("main-content", "children", allow_duplicate=True),
        Output("workspace-input", "value", allow_duplicate=True),
        Output("filename-input", "value", allow_duplicate=True),
        [Input("btn-open", "n_clicks")],
        prevent_initial_call=True,
    )
    def handle_open_project(n_clicks):
        """Pick a CSV/JSON project file (Tk dialog) then load into storage."""
        noop = dash.no_update, dash.no_update, dash.no_update
        if not n_clicks:
            return noop

        picked = ask_open_project_path()

        # User dismissed the native picker without choosing a path
        if picked == "":
            return noop

        if isinstance(picked, str) and picked:
            fn = picked
            workspace_dir = os.path.dirname(fn) or ""
            base_name = os.path.basename(fn)
            dash_storage.set_data("workspace", workspace_dir)
            dash_storage.set_data("filename", base_name)
            workspace_out = workspace_dir
            filename_out = base_name
        else:
            # Tk unavailable: use workspace + filename fields from storage
            data = dash_storage.get_data_storage()
            raw_ws = data.get("workspace")
            workspace_dir = raw_ws.strip() if isinstance(raw_ws, str) else ""
            raw_fn = data.get("filename")
            base_name = raw_fn.strip() if isinstance(raw_fn, str) else ""
            workspace_out = dash.no_update
            filename_out = dash.no_update
            if not workspace_dir:
                ov = create_overview_content()
                return (
                    [
                        dbc.Alert(
                            "Native file picker is unavailable here. Enter a Workspace path, "
                            "a File name, then click Load.",
                            color="danger",
                            className="mb-3",
                        ),
                    ]
                    + ov,
                    dash.no_update,
                    dash.no_update,
                )
            if not base_name:
                ov = create_overview_content()
                return (
                    [
                        dbc.Alert(
                            "Native file picker is unavailable here. Enter a File name, "
                            "then click Load.",
                            color="danger",
                            className="mb-3",
                        ),
                    ]
                    + ov,
                    dash.no_update,
                    dash.no_update,
                )
            fn = os.path.join(workspace_dir, base_name)

        if not os.path.exists(fn):
            ov = create_overview_content()
            return (
                [
                    dbc.Alert(
                        f"File does not exist: {fn}",
                        color="danger",
                        className="mb-3",
                    ),
                ]
                + ov,
                workspace_out,
                filename_out,
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

            ov = create_overview_content()
            return (
                [
                    dbc.Alert(
                        f"Project loaded successfully from {fn}",
                        color="success",
                        className="mb-3",
                    ),
                ]
                + ov,
                workspace_out,
                filename_out,
            )
        except Exception as e:
            ov = create_overview_content()
            return (
                [
                    dbc.Alert(
                        f"Error loading project: {str(e)}",
                        color="danger",
                        className="mb-3",
                    ),
                ]
                + ov,
                workspace_out,
                filename_out,
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

