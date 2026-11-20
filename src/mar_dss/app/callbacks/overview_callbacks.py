"""
Overview tab callbacks for MAR DSS dashboard.
"""

import base64
import contextlib
import io
import json
import os

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, State
from dash.dependencies import ClientsideFunction

import mar_dss.app.utils.data_storage as dash_storage
import mar_dss.app.utils.helpers as helpers

try:
    from mar_dss.app.utils.project_file_path import format_project_path, split_project_path
    from mar_dss.app.utils.project_storage import (
        _parse_literal_if_needed,
        apply_project_storage_defaults,
        is_missing_storage_value,
        normalize_stored_string,
    )
except ImportError:
    from ..utils.project_file_path import format_project_path, split_project_path
    from ..utils.project_storage import (
        _parse_literal_if_needed,
        apply_project_storage_defaults,
        is_missing_storage_value,
        normalize_stored_string,
    )

# Import the overview content creation function
try:
    from mar_dss.app.components.hydro_tab import (
        normalize_groundwater_data,
        normalize_stratigraphy_list_from_raw,
        stratigraphy_store_payload_from_storage,
    )
    from mar_dss.app.components.layout import MAX_PROJECT_UPLOAD_BYTES, main_tab_panel_id
    from mar_dss.app.components.overview_tab import (
        ALLOWED_OVERVIEW_BASEMAP_STYLES,
        DEFAULT_LAND_USE,
        DEFAULT_OVERVIEW_MAP_BASEMAP,
        create_overview_content,
        get_overview_map_figure_params,
        get_overview_map_header_text,
        normalize_land_use,
        overview_map_header_children,
    )
    from mar_dss.app.components.water_source_tab import (
        build_water_source_location_map_figure,
        create_location_map,
        water_source_site_coordinates_summary_children,
    )
except ImportError:
    from ..components.hydro_tab import (
        normalize_groundwater_data,
        normalize_stratigraphy_list_from_raw,
        stratigraphy_store_payload_from_storage,
    )
    from ..components.layout import MAX_PROJECT_UPLOAD_BYTES, main_tab_panel_id
    from ..components.overview_tab import (
        ALLOWED_OVERVIEW_BASEMAP_STYLES,
        DEFAULT_LAND_USE,
        DEFAULT_OVERVIEW_MAP_BASEMAP,
        create_overview_content,
        get_overview_map_figure_params,
        get_overview_map_header_text,
        normalize_land_use,
        overview_map_header_children,
    )
    from ..components.water_source_tab import (
        build_water_source_location_map_figure,
        create_location_map,
        water_source_site_coordinates_summary_children,
    )


def _extract_mapbox_view_from_relayout(relayout_data):
    """Parse Plotly map/mapbox relayout payload for center and zoom."""
    if not relayout_data:
        return None, None, None
    lat = lon = zoom = None
    # Plotly 6+/7 use ``map.*``; older releases used ``mapbox.*``.
    for prefix in ("map", "mapbox"):
        z = relayout_data.get(f"{prefix}.zoom")
        if z is not None and zoom is None:
            with contextlib.suppress(TypeError, ValueError):
                zoom = float(z)
        center = relayout_data.get(f"{prefix}.center")
        if isinstance(center, dict) and lat is None:
            try:
                lat = float(center["lat"])
                lon = float(center["lon"])
            except (KeyError, TypeError, ValueError):
                pass
        if lat is None and f"{prefix}.center.lat" in relayout_data:
            with contextlib.suppress(TypeError, ValueError):
                lat = float(relayout_data[f"{prefix}.center.lat"])
        if lon is None and f"{prefix}.center.lon" in relayout_data:
            with contextlib.suppress(TypeError, ValueError):
                lon = float(relayout_data[f"{prefix}.center.lon"])
    return lat, lon, zoom


def _relayout_has_mapbox_camera(relayout_data):
    """True when relayout reflects user map camera (not autosize/width churn)."""
    if not relayout_data or not isinstance(relayout_data, dict):
        return False
    for key in relayout_data:
        if key in ("map.zoom", "mapbox.zoom"):
            return True
        if key.startswith("map.center") or key.startswith("mapbox.center"):
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
            center_changed = ola is None or olo is None or abs(ola - lat) > 0.002 or abs(olo - lon) > 0.002
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

    @app.callback(
        Output("starting-info-help-modal", "is_open"),
        [
            Input("starting-info-help-btn", "n_clicks"),
            Input("starting-info-help-close-btn", "n_clicks"),
        ],
        State("starting-info-help-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_starting_information_help_modal(open_clicks, close_clicks, is_open):
        """Open or close the MAR-Tool Starting Information help popup."""
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger == "starting-info-help-btn":
            return True
        if trigger == "starting-info-help-close-btn":
            return False
        return bool(is_open)

    # Combined callback for project name input - handles all triggers
    @app.callback(
        Output("project-name-input", "value"),
        [
            Input("project-name-input", "value"),
            Input("project-name-input", "n_blur"),
            Input("project-name-input", "n_submit"),
            Input("project-name-input", "id"),
        ],
        prevent_initial_call=False,
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
            Input("analysis-date-input", "id"),
        ],
        prevent_initial_call=False,
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
                    if (
                        isinstance(analysis_date, str)
                        and len(analysis_date) == 10
                        and analysis_date[4] == "-"
                        and analysis_date[7] == "-"
                    ):
                        formatted_date = analysis_date
                    else:
                        # Try to parse and reformat the date
                        from datetime import datetime

                        parsed_date = helpers.parse_unknown_date(analysis_date)
                        formatted_date = parsed_date.strftime("%Y-%m-%d")
                    dash_storage.set_data("analysis_date", formatted_date)
                    return formatted_date
                except Exception:
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
                if (
                    isinstance(current_value, str)
                    and len(current_value) == 10
                    and current_value[4] == "-"
                    and current_value[7] == "-"
                ):
                    formatted_date = current_value
                else:
                    # Try to parse and reformat
                    parsed_date = datetime.strptime(str(current_value), "%Y-%m-%d")
                    formatted_date = parsed_date.strftime("%Y-%m-%d")
                dash_storage.set_data("analysis_date", formatted_date)
            except Exception:
                # If formatting fails, save as is
                dash_storage.set_data("analysis_date", current_value)

        return current_value

    # Callback for MAR purpose checklist - saves selections to data storage
    @app.callback(
        Output("mar-purpose-checklist", "value"),
        [Input("mar-purpose-checklist", "value"), Input("mar-purpose-checklist", "id")],
        prevent_initial_call=False,
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
        style = style_value if style_value in ALLOWED_OVERVIEW_BASEMAP_STYLES else DEFAULT_OVERVIEW_MAP_BASEMAP
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
        return _overview_map_figure_with_style(style_overview, fill_container=True)

    @app.callback(
        Output("water-source-location-map", "figure"),
        Input("water-source-overview-map-basemap", "value"),
        prevent_initial_call=True,
    )
    def apply_overview_map_basemap_water_source(style_ws):
        style = style_ws if style_ws in ALLOWED_OVERVIEW_BASEMAP_STYLES else DEFAULT_OVERVIEW_MAP_BASEMAP
        dash_storage.set_data("overview_map_basemap", style)
        return build_water_source_location_map_figure(style)

    app.clientside_callback(
        ClientsideFunction(
            namespace="clientside",
            function_name="installOverviewMapClickRelay",
        ),
        Output("overview-map-click-relay-hook", "children"),
        [
            Input("location-map", "figure"),
            Input("top-tabs", "active_tab"),
        ],
    )

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
        Output("location-map", "figure", allow_duplicate=True),
        Output("location-card-header", "children", allow_duplicate=True),
        Output("project-location-input", "value", allow_duplicate=True),
        Output("project-location-store", "data", allow_duplicate=True),
        Input("overview-map-mapbox-click-store", "data"),
        State("overview-map-basemap", "value"),
        prevent_initial_call=True,
    )
    def place_overview_site_from_map_click(picked, basemap_dropdown_value):
        """Place the red project-location marker at the map click."""
        if not picked or not isinstance(picked, dict):
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update

        lat = picked.get("lat")
        lon = picked.get("lon")
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (TypeError, ValueError):
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update

        dash_storage.set_data("overview_map_lat", lat_f)
        dash_storage.set_data("overview_map_lon", lon_f)

        try:
            from mar_dss.app.components.water_source_tab import get_location_details
        except ImportError:
            from ..components.water_source_tab import get_location_details

        location_name = get_location_details(lat_f, lon_f)
        dash_storage.set_data("project_location", location_name)
        dash_storage.set_data(
            "overview_map_location_label",
            f"Project Location — {location_name}",
        )

        fig = _overview_map_figure_with_style(basemap_dropdown_value, fill_container=True)
        hdr = get_overview_map_header_text()
        return (
            fig,
            overview_map_header_children(hdr),
            location_name,
            location_name,
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
        Output("project-location-store", "data", allow_duplicate=True),
        [
            Input("location-map", "relayoutData"),
            Input("project-location-input", "value"),
            Input("project-location-input", "n_blur"),
            Input("project-location-input", "n_submit"),
            Input("project-location-input", "id"),
        ],
        prevent_initial_call="initial_duplicate",
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
                return dash.no_update, dash.no_update, dash.no_update
            hdr, loc_inp = _persist_shared_map_view_from_relayout(relayout_overview)
            return overview_map_header_children(hdr), loc_inp, loc_inp

        if trigger_id == "project-location-input" and trigger_prop != "id":
            current_value = (project_location_value or "").strip()
            dash_storage.set_data("project_location", current_value)
            if current_value:
                dash_storage.set_data(
                    "overview_map_location_label",
                    f"Project Location — {current_value}",
                )
            return (
                overview_map_header_children(),
                current_value,
                current_value,
            )

        return (
            overview_map_header_children(),
            stored_project_location,
            stored_project_location,
        )

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
        """Populate dash_storage from a key/value CSV export.

        Skip ``workspace`` / ``filename``: those must reflect where *this* user
        opened or saved the file, not paths embedded from a colleague's machine.
        """
        for _, row in df.iterrows():
            key = row["key"]
            if key in ("workspace", "filename"):
                continue
            value = row["value"]

            if is_missing_storage_value(value):
                continue

            value = _parse_literal_if_needed(value)

            if key == "stratigraphy_data":
                coerced = normalize_stratigraphy_list_from_raw(value)
                if coerced is None:
                    continue
                value = coerced

            dash_storage.set_data(key, value)

        apply_project_storage_defaults()

    def _error_outputs(message):
        """Outputs for handle_open_project when a file can't be loaded: show the
        error and leave the stores alone."""
        return (
            [dbc.Alert(message, color="danger", className="mb-3")],
            create_overview_content(),
            dash.no_update,
            "overview",
            dash.no_update,
            dash.no_update,
            dash.no_update,
            None,
        )

    # Open button: load the project file the user uploaded.
    # This used to open a desktop file dialog (tkinter), which only works when the
    # app runs on the user's own computer. On a server the dialog would open on the
    # server, if at all. Now the Open button is a dcc.Upload (see layout.py): the
    # browser picks the file and sends its contents here.
    @app.callback(
        Output("main-content-flash", "children", allow_duplicate=True),
        Output(main_tab_panel_id("overview"), "children", allow_duplicate=True),
        Output("project-path-input", "value", allow_duplicate=True),
        Output("top-tabs", "active_tab", allow_duplicate=True),
        Output("stratigraphy-data-store", "data", allow_duplicate=True),
        Output("groundwater-data-store", "data", allow_duplicate=True),
        Output("project-location-store", "data", allow_duplicate=True),
        # Reset after each load so the same file can be opened again.
        Output("upload-project", "contents"),
        Input("upload-project", "contents"),
        State("upload-project", "filename"),
        prevent_initial_call=True,
    )
    def handle_open_project(contents, filename):
        """Load an uploaded CSV/JSON project file into storage.

        The upload arrives as base64 text, so decode it first, then parse it the
        same way the old file-path version did.
        """
        if not contents:
            return (dash.no_update,) * 8

        filename = os.path.basename(filename or "project.csv")
        try:
            _, encoded = contents.split(",", 1)
            payload = base64.b64decode(encoded)
            if len(payload) > MAX_PROJECT_UPLOAD_BYTES:
                return _error_outputs("Project files must be 10 MiB or smaller.")
            text = payload.decode("utf-8-sig")
        except (ValueError, UnicodeDecodeError) as e:
            return _error_outputs(f"Error loading project: could not read {filename} ({e})")

        try:
            suffix = os.path.splitext(filename)[1].lower()
            if suffix == ".json":
                blob = json.loads(text)
                if isinstance(blob, dict):
                    for key, value in blob.items():
                        if key in ("workspace", "filename"):
                            continue
                        if is_missing_storage_value(value):
                            continue
                        dash_storage.set_data(key, _parse_literal_if_needed(value))
                else:
                    raise ValueError("JSON project must contain an object at the root.")
                apply_project_storage_defaults()
            else:
                df = pd.read_csv(io.StringIO(text))
                if not {"key", "value"} <= set(df.columns):
                    raise ValueError("CSV project must contain 'key' and 'value' columns.")
                _load_project_rows_into_storage(df)

            # We only get the file name, not where it is on the user's computer.
            dash_storage.set_data("workspace", "")
            dash_storage.set_data("filename", filename)

            if dash_storage.get_data("overview_map_basemap") == "stamen-terrain":
                dash_storage.set_data("overview_map_basemap", "opentopomap")
            strat_out = stratigraphy_store_payload_from_storage()
            gw_out = normalize_groundwater_data(dash_storage.get_data("groundwater_data") or [])
            project_loc = normalize_stored_string(dash_storage.get_data("project_location"))
            return (
                [
                    dbc.Alert(
                        f"Project loaded successfully from {filename}",
                        color="success",
                        className="mb-3",
                    ),
                ],
                create_overview_content(),
                filename,
                "overview",
                strat_out,
                gw_out,
                project_loc,
                None,
            )
        except Exception as e:
            return _error_outputs(f"Error loading project: {str(e)}")

    # Callback for ground surface slope input - saves to data storage
    @app.callback(
        Output("ground-slope-input", "value"),
        [
            Input("ground-slope-input", "value"),
            Input("ground-slope-input", "n_blur"),
            Input("ground-slope-input", "n_submit"),
            Input("ground-slope-input", "id"),
        ],
        prevent_initial_call=False,
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
            Input("max-area-input", "id"),
        ],
        prevent_initial_call=False,
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
        [Input("land-use-dropdown", "value"), Input("land-use-dropdown", "id")],
        prevent_initial_call=False,
    )
    def handle_land_use_selection(value, component_id):
        """Handle land use dropdown selection and save to data storage."""
        ctx = dash.callback_context

        if not ctx.triggered:
            # Initial load - get saved land use or use default, and save it
            land_use = normalize_land_use(dash_storage.get_data("land_use"))
            dash_storage.set_data("land_use", land_use)
            return land_use

        # Get the current selection
        current_selection = normalize_land_use(value) if value else DEFAULT_LAND_USE

        # Save land use selection to data storage
        dash_storage.set_data("land_use", current_selection)

        return current_selection
