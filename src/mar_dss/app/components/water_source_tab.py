"""
General tab content and utilities for MAR DSS dashboard (Water Source).
"""

import math

import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from dash import dcc, dash_table, html
from dash.dash_table.Format import Format, Scheme
import mar_dss.app.utils.data_storage as dash_storage
from .runoff_calculator_tab import create_runoff_calculator_tab, create_curve_number_tab


def _nearest_place_label(lat: float, lon: float) -> str | None:
    """Find nearest city/town/village name using Overpass, return a label or None.

    Called only as a fallback when Nominatim reverse doesn't provide a place-like name.
    Keep it conservative (short timeout, small responses) to avoid slowing normal UX.
    """
    try:
        overpass_url = "https://overpass-api.de/api/interpreter"
        # Escalate search radius (meters) only if needed
        for radius in (10_000, 25_000, 50_000, 100_000):
            query = f"""
[out:json][timeout:5];
(
  node(around:{radius},{lat},{lon})["place"~"^(city|town|village)$"];
  way(around:{radius},{lat},{lon})["place"~"^(city|town|village)$"];
  relation(around:{radius},{lat},{lon})["place"~"^(city|town|village)$"];
);
out center 30;
"""
            r = requests.post(
                overpass_url,
                data=query,
                headers={"User-Agent": "MAR-DSS-Dashboard/1.0"},
                timeout=6,
            )
            if r.status_code != 200:
                continue
            data = r.json()
            elems = data.get("elements") or []
            if not elems:
                continue

            # Pick nearest by simple squared-distance in degrees (good enough for small radii)
            best_name = None
            best_d2 = None
            for e in elems:
                tags = e.get("tags") or {}
                name = tags.get("name")
                if not name:
                    continue
                if "lat" in e and "lon" in e:
                    elat, elon = float(e["lat"]), float(e["lon"])
                else:
                    c = e.get("center") or {}
                    if "lat" not in c or "lon" not in c:
                        continue
                    elat, elon = float(c["lat"]), float(c["lon"])
                d2 = (elat - lat) ** 2 + (elon - lon) ** 2
                if best_d2 is None or d2 < best_d2:
                    best_d2 = d2
                    best_name = name

            if best_name:
                return f"Near {best_name}"
        return None
    except Exception:
        return None


def get_location_details(lat, lon):
    """Get closest city/town-style label from coordinates via reverse geocoding.

    Nominatim reverse-geocoding can return very local features (roads, hamlets) or
    only higher-level admin areas depending on where the point lies. For UI display,
    we prefer a human-friendly nearby place name (city/town/village/municipality).
    """
    try:
        url = (
            "https://nominatim.openstreetmap.org/reverse?format=json&lat="
            f"{lat}&lon={lon}&zoom=10&addressdetails=1&namedetails=1"
        )
        headers = {"User-Agent": "MAR-DSS-Dashboard/1.0"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            address = data.get("address", {})
            # Prefer nearby place-like labels (roughly "closest town/city" UX).
            place = (
                address.get("locality")
                or address.get("municipality")
                or address.get("hamlet")
                or address.get("village")
                or address.get("town")
                or address.get("city")
                or address.get("county")
            )
            state = address.get("state")
            country = address.get("country")
            if place and state and country:
                return f"{place}, {state}, {country}"
            elif place and country:
                return f"{place}, {country}"
            elif place:
                return f"{place}"
            elif state and country:
                return f"{state}, {country}"
            else:
                # Fallback to the first token of display_name (often a named place)
                display = (data.get("display_name") or "").split(",")[0].strip()
                if display:
                    return display
                near = _nearest_place_label(float(lat), float(lon))
                if near:
                    return near
                return country or "Unknown Location"
        return "Unknown Location"
    except Exception:
        return "Unknown Location"


_DEFAULT_MAP_STYLE = "open-street-map"
_ALLOWED_MAP_STYLES = frozenset(
    {
        "open-street-map",
        "carto-positron",
        "carto-darkmatter",
        "opentopomap",
        "satellite-streets",
        "white-bg",
    }
)

# Plotly's preset `stamen-terrain` often breaks (Stamen→Stadia; pan/zoom can freeze). Terrain via raster tiles.
_OPENTOPOMAP_TILES = ["https://tile.opentopomap.org/{z}/{x}/{y}.png"]

# Overview location map figure height (px); 720 = 50% increase over prior 480.
_LOCATION_MAP_HEIGHT_PX = 720

# Water Source map: minimum plot area below basemap when filling the card (flex layout).
_WATER_SOURCE_MAP_MIN_HEIGHT_PX = 360

# Satellite + roads/labels via Esri World Imagery and Reference overlays (no Mapbox token; Esri terms apply).
_ESRI_WORLD_IMAGERY = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
_ESRI_WORLD_TRANSPORTATION = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/"
    "MapServer/tile/{z}/{y}/{x}"
)
_ESRI_WORLD_BOUNDARIES_PLACES = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/"
    "MapServer/tile/{z}/{y}/{x}"
)


def offset_latlon_miles_east(lat_deg: float, lon_deg: float, miles: float) -> tuple[float, float]:
    """Return (lat, lon) of the point ``miles`` statute miles east of (lat_deg, lon_deg)."""
    if miles == 0:
        return float(lat_deg), float(lon_deg)
    lat_rad = math.radians(float(lat_deg))
    m_per_deg_lat = 111_320.0
    cos_lat = math.cos(lat_rad)
    m_per_deg_lon = max(m_per_deg_lat * cos_lat, 1e-6)
    m_east = float(miles) * 1609.34
    dlon = m_east / m_per_deg_lon
    return float(lat_deg), float(lon_deg) + dlon


def _normalize_map_style(map_style):
    style = (
        map_style if map_style in _ALLOWED_MAP_STYLES else _DEFAULT_MAP_STYLE
    )
    return style


def _mapbox_dict_for_style(style, center_lat, center_lon, zoom):
    """Mapbox layout subtree for Scattermapbox (tiles / preset style)."""
    style = _normalize_map_style(style)
    mapbox = dict(
        center=dict(lat=float(center_lat), lon=float(center_lon)),
        zoom=float(zoom),
    )
    if style == "opentopomap":
        mapbox["style"] = "white-bg"
        mapbox["layers"] = [
            dict(
                sourcetype="raster",
                source=list(_OPENTOPOMAP_TILES),
                below="traces",
            )
        ]
    elif style == "satellite-streets":
        mapbox["style"] = "white-bg"
        mapbox["layers"] = [
            dict(sourcetype="raster", source=[_ESRI_WORLD_IMAGERY], below="traces"),
            dict(
                sourcetype="raster",
                source=[_ESRI_WORLD_TRANSPORTATION],
                below="traces",
            ),
            dict(
                sourcetype="raster",
                source=[_ESRI_WORLD_BOUNDARIES_PLACES],
                below="traces",
            ),
        ]
    else:
        mapbox["style"] = style
    return mapbox


_WATER_MAP_SOURCE_KEYS = ("water_map_source_lat", "water_map_source_lon")
_WATER_MAP_RECHARGE_KEYS = ("water_map_recharge_lat", "water_map_recharge_lon")


def ensure_water_source_site_coordinates():
    """Return saved source/recharge coords, seeding defaults if storage is incomplete."""

    def _float_or_none(raw):
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    plat = dash_storage.get_data(_WATER_MAP_SOURCE_KEYS[0])
    plon = dash_storage.get_data(_WATER_MAP_SOURCE_KEYS[1])
    rlat = dash_storage.get_data(_WATER_MAP_RECHARGE_KEYS[0])
    rlon = dash_storage.get_data(_WATER_MAP_RECHARGE_KEYS[1])
    platf = _float_or_none(plat)
    plonf = _float_or_none(plon)
    rlatf = _float_or_none(rlat)
    rlonf = _float_or_none(rlon)

    if all(v is not None for v in (platf, plonf, rlatf, rlonf)):
        return platf, plonf, rlatf, rlonf

    try:
        from mar_dss.app.components.overview_tab import (
            get_overview_map_figure_params,
        )
    except ImportError:
        from ..components.overview_tab import get_overview_map_figure_params

    proj_lat, proj_lon, _, _, _ = get_overview_map_figure_params()
    rlat_def, rlon_def = offset_latlon_miles_east(proj_lat, proj_lon, 1.0)
    dash_storage.set_data(_WATER_MAP_SOURCE_KEYS[0], proj_lat)
    dash_storage.set_data(_WATER_MAP_SOURCE_KEYS[1], proj_lon)
    dash_storage.set_data(_WATER_MAP_RECHARGE_KEYS[0], rlat_def)
    dash_storage.set_data(_WATER_MAP_RECHARGE_KEYS[1], rlon_def)
    return float(proj_lat), float(proj_lon), rlat_def, rlon_def


def create_water_source_sites_map(
    source_lat,
    source_lon,
    recharge_lat,
    recharge_lon,
    center_lat,
    center_lon,
    zoom,
    map_style=None,
    uirevision="mar-water-source-location-map",
    fill_container=True,
):
    """Two-marker map for Water Source tab (red Source, blue Recharge); camera follows overview storage."""
    style = _normalize_map_style(map_style)
    fig = go.Figure()
    fig.add_trace(
        go.Scattermapbox(
            lat=[float(source_lat)],
            lon=[float(source_lon)],
            mode="markers",
            marker=dict(size=18, color="red", symbol="circle"),
            text=["Source Site"],
            textposition="top center",
            name="Source Site",
        )
    )
    fig.add_trace(
        go.Scattermapbox(
            lat=[float(recharge_lat)],
            lon=[float(recharge_lon)],
            mode="markers",
            marker=dict(size=18, color="blue", symbol="circle"),
            text=["Recharge Site"],
            textposition="top center",
            name="Recharge Site",
        )
    )
    mapbox = _mapbox_dict_for_style(style, center_lat, center_lon, zoom)
    layout = dict(
        mapbox=mapbox,
        margin=dict(l=0, r=0, t=0, b=0),
        uirevision=uirevision,
        dragmode="pan",
        showlegend=False,
    )
    if fill_container:
        layout["autosize"] = True
    else:
        layout["height"] = _LOCATION_MAP_HEIGHT_PX
    fig.update_layout(**layout)
    return fig


def build_water_source_location_map_figure(map_style):
    """Build the Water Source location card figure from storage (basemap, camera, site coords)."""
    try:
        from mar_dss.app.components.overview_tab import (
            ALLOWED_OVERVIEW_BASEMAP_STYLES,
            DEFAULT_OVERVIEW_MAP_BASEMAP,
            get_overview_map_figure_params,
        )
    except ImportError:
        from ..components.overview_tab import (
            ALLOWED_OVERVIEW_BASEMAP_STYLES,
            DEFAULT_OVERVIEW_MAP_BASEMAP,
            get_overview_map_figure_params,
        )

    style = (
        map_style
        if map_style in ALLOWED_OVERVIEW_BASEMAP_STYLES
        else DEFAULT_OVERVIEW_MAP_BASEMAP
    )
    slat, slon, rlat, rlon = ensure_water_source_site_coordinates()
    cam_lat, cam_lon, cam_zoom, _, _ = get_overview_map_figure_params()
    return create_water_source_sites_map(
        source_lat=slat,
        source_lon=slon,
        recharge_lat=rlat,
        recharge_lon=rlon,
        center_lat=cam_lat,
        center_lon=cam_lon,
        zoom=float(cam_zoom),
        map_style=style,
        uirevision="mar-water-source-location-map",
        fill_container=True,
    )


def create_location_map(
    lat=38.5816,
    lon=-121.4944,
    location_name="Sacramento, CA",
    zoom=10,
    map_style=None,
    uirevision="mar-overview-location-map",
    fill_container=False,
):
    """Create a map centered on specified location with default Sacramento."""
    style = _normalize_map_style(map_style)
    fig = go.Figure()
    fig.add_trace(
        go.Scattermapbox(
            lat=[lat],
            lon=[lon],
            mode="markers",
            marker=dict(size=20, color="red", symbol="circle"),
            text=[location_name],
            textposition="top center",
            name=location_name,
        )
    )
    mapbox = _mapbox_dict_for_style(style, lat, lon, zoom)
    layout = dict(
        mapbox=mapbox,
        margin=dict(l=0, r=0, t=0, b=0),
        uirevision=uirevision,
        dragmode="pan",
    )
    if fill_container:
        layout["autosize"] = True
    else:
        layout["height"] = _LOCATION_MAP_HEIGHT_PX
    fig.update_layout(**layout)
    return fig


def create_monthly_flow_chart(flow_data=None):
    """Create a chart showing monthly flow and cumulative annual flow."""
    months = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    if flow_data is None:
        monthly_flow = [
            4500,
            4200,
            2800,
            2200,
            1800,
            1500,
            1200,
            1000,
            1300,
            2000,
            3800,
            4100,
        ]
    else:
        monthly_flow = [flow_data.get(month, 0) for month in months]
    cumulative_flow = np.cumsum(monthly_flow)
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=months,
            y=monthly_flow,
            name="Monthly Flow",
            marker_color="lightblue",
            yaxis="y",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=months,
            y=cumulative_flow,
            mode="lines+markers",
            name="Cumulative Annual Flow",
            line=dict(color="red", width=3),
            marker=dict(size=8),
            yaxis="y2",
        )
    )
    fig.update_layout(
        title="Monthly Flow and Cumulative Annual Flow",
        xaxis_title="Month",
        yaxis=dict(title="Monthly Flow (ft³/month)", side="left"),
        yaxis2=dict(title="Cumulative Flow (ft³)", side="right", overlaying="y"),
        height=480,
        width=800,
        margin=dict(l=0, r=50, t=50, b=50),
        legend=dict(
            yanchor="top", y=0.95, xanchor="center", x=0.5, orientation="v"
        ),
        autosize=False,
    )
    return fig


def _get_flow_store_data():
    """Get flow data in dictionary format for flow-data-store from dash_storage."""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    default_flows = [4500, 4200, 2800, 2200, 1800, 1500, 1200, 1000, 1300, 2000, 3800, 4100]
    monthly_flows = dash_storage.get_data("monthly_flow") or default_flows
    
    # Ensure we have exactly 12 values
    if len(monthly_flows) != 12:
        monthly_flows = default_flows
    
    # Convert list to dictionary format
    return {month: flow for month, flow in zip(months, monthly_flows)}


def create_editable_flow_table():
    """Create an editable table for monthly flow data."""
    months = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    # Get existing values from data storage if available
    default_flows = [4500, 4200, 2800, 2200, 1800, 1500, 1200, 1000, 1300, 2000, 3800, 4100]
    monthly_flows = dash_storage.get_data("monthly_flow") or default_flows
    
    # Ensure we have exactly 12 values
    if len(monthly_flows) != 12:
        monthly_flows = default_flows
    
    df = pd.DataFrame(
        {
            "Month": months,
            "Flow (ft³/month)": monthly_flows,
        }
    )
    table = html.Div(
        [
            dash_table.DataTable(
                id="flow-data-table",
                data=df.to_dict("records"),
                columns=[
                    {"name": "Month", "id": "Month", "type": "text", "editable": False},
                    {
                        "name": "Flow (ft³/month)",
                        "id": "Flow (ft³/month)",
                        "type": "numeric",
                        "editable": True,
                        "format": Format(precision=1, scheme=Scheme.fixed),
                    },
                ],
                style_cell={
                    "textAlign": "center",
                    "padding": "8px",
                    "fontFamily": "Arial, sans-serif",
                    "fontSize": "14px",
                },
                style_header={
                    "backgroundColor": "#28a745",
                    "color": "white",
                    "fontWeight": "bold",
                },
                style_data={"backgroundColor": "white", "color": "black"},
                style_data_conditional=[
                    {"if": {"row_index": "odd"}, "backgroundColor": "#f8f9fa"}
                ],
                editable=True,
                row_deletable=False,
                sort_action="none",
                filter_action="none",
                style_table={"width": "300px", "maxWidth": "300px"},
            )
        ]
    )
    return table


def create_water_source_location_map_card():
    """Same map setup as Overview: shared dash_storage lat/lon/zoom/basemap/header."""
    try:
        from mar_dss.app.components.overview_tab import (
            OVERVIEW_BASEMAP_OPTIONS,
            get_overview_map_figure_params,
            get_overview_map_header_text,
        )
    except ImportError:
        from ..components.overview_tab import (
            OVERVIEW_BASEMAP_OPTIONS,
            get_overview_map_figure_params,
            get_overview_map_header_text,
        )

    _, _, _, _, basemap = get_overview_map_figure_params()
    header_text = get_overview_map_header_text()
    # Match ``create_location_map_section`` in overview_tab (card + tooltips structure)
    return dbc.Card(
        [
            dbc.CardHeader(
                header_text,
                id="water-source-location-card-header",
                className="fw-bold bg-primary text-white",
            ),
            dbc.CardBody(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label(
                                        "Basemap:",
                                        className="fw-bold small me-2 mb-0",
                                    ),
                                    dcc.Dropdown(
                                        id="water-source-overview-map-basemap",
                                        options=OVERVIEW_BASEMAP_OPTIONS,
                                        value=basemap,
                                        clearable=False,
                                        className="mb-0",
                                        style={
                                            "flex": "1 1 auto",
                                            "width": "100%",
                                            "minWidth": "min(380px, 100%)",
                                        },
                                    ),
                                    dbc.Tooltip(
                                        "Switch background tiles; center and zoom stay as "
                                        "last saved from the map. Terrain uses OpenTopoMap "
                                        "(© OpenStreetMap contributors). Satellite + streets "
                                        "uses Esri imagery and reference overlays; comply with "
                                        "Esri terms. Same extent as Overview.",
                                        target="water-source-overview-map-basemap",
                                        placement="top",
                                    ),
                                ],
                                className=(
                                    "d-flex flex-wrap align-items-center gap-2 w-100"
                                ),
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        "Change Source and Recharge Sites",
                                        className="fw-bold small mb-1 w-100 text-start",
                                    ),
                                    dcc.RadioItems(
                                        id="water-source-map-site-radio",
                                        options=[
                                            {
                                                "label": html.Span(
                                                    [
                                                        html.Span(
                                                            "Source Site",
                                                            className="d-inline-flex align-items-center",
                                                            style={
                                                                "lineHeight": "2.7rem",
                                                                "height": "2.7rem",
                                                            },
                                                        ),
                                                        html.Span(
                                                            "●",
                                                            style={
                                                                "color": "#dc3545",
                                                                "fontSize": "2.7rem",
                                                                "lineHeight": "2.7rem",
                                                                "marginLeft": "6px",
                                                                "display": "inline-flex",
                                                                "alignItems": "center",
                                                                "height": "2.7rem",
                                                            },
                                                            title="Red marker",
                                                        ),
                                                    ],
                                                    className=(
                                                        "d-inline-flex align-items-center "
                                                        "flex-nowrap"
                                                    ),
                                                ),
                                                "value": "source_site",
                                            },
                                            {
                                                "label": html.Span(
                                                    [
                                                        html.Span(
                                                            "Recharge Site",
                                                            className="d-inline-flex align-items-center",
                                                            style={
                                                                "lineHeight": "2.7rem",
                                                                "height": "2.7rem",
                                                            },
                                                        ),
                                                        html.Span(
                                                            "●",
                                                            style={
                                                                "color": "#0d6efd",
                                                                "fontSize": "2.7rem",
                                                                "lineHeight": "2.7rem",
                                                                "marginLeft": "6px",
                                                                "display": "inline-flex",
                                                                "alignItems": "center",
                                                                "height": "2.7rem",
                                                            },
                                                            title="Blue marker",
                                                        ),
                                                    ],
                                                    className=(
                                                        "d-inline-flex align-items-center "
                                                        "flex-nowrap"
                                                    ),
                                                ),
                                                "value": "recharge_site",
                                            },
                                        ],
                                        value=(
                                            dash_storage.get_data(
                                                "water_source_map_site"
                                            )
                                            or "source_site"
                                        ),
                                        className="mb-0",
                                        labelStyle={
                                            "display": "inline-flex",
                                            "alignItems": "center",
                                            "marginRight": "1.25rem",
                                            "cursor": "pointer",
                                        },
                                        inputStyle={"marginRight": "6px"},
                                    ),
                                    dbc.Tooltip(
                                        "Choose which marker to move, then click the map "
                                        "to drop the red Source Site or blue Recharge Site.",
                                        target="water-source-map-site-radio",
                                        placement="top",
                                    ),
                                ],
                                className="d-flex flex-column align-items-start w-100",
                            ),
                        ],
                        className="d-flex flex-column gap-2 pb-2",
                        style={"flexShrink": 0},
                    ),
                    html.Div(
                        [
                            dcc.Store(
                                id="water-source-map-mapbox-click-store",
                                data=None,
                            ),
                            html.Div(
                                id="water-source-map-click-relay-hook",
                                style={"display": "none"},
                                children=[],
                            ),
                            dcc.Graph(
                                figure=build_water_source_location_map_figure(
                                    basemap
                                ),
                                config={
                                    "displayModeBar": True,
                                    "scrollZoom": True,
                                },
                                id="water-source-location-map",
                                responsive=True,
                                style={
                                    "flex": "1 1 auto",
                                    "minHeight": f"{_WATER_SOURCE_MAP_MIN_HEIGHT_PX}px",
                                    "height": "100%",
                                    "overflow": "hidden",
                                },
                            ),
                            dbc.Tooltip(
                                "Red = Source Site, blue = Recharge Site (defaults: "
                                "source at saved project location, recharge ~1 mi east). "
                                "Choose Source Site or Recharge Site above, then click "
                                "the map to place that marker.",
                                target="water-source-location-map-shell",
                                placement="top",
                            ),
                        ],
                        id="water-source-location-map-shell",
                        style={
                            "flex": "1 1 auto",
                            "minHeight": 0,
                            "display": "flex",
                            "flexDirection": "column",
                            "overflow": "hidden",
                            "overscrollBehavior": "contain",
                        },
                        className="water-source-location-map-shell",
                    ),
                ],
                className="p-3 d-flex flex-column flex-grow-1",
                style={"minHeight": 0, "overflow": "hidden"},
            ),
        ],
        className="h-100 w-100 d-flex flex-column mb-3 mb-lg-0",
    )


def _create_optional_runoff_calculations_card():
    """Card below Volume Estimates: nested Runoff Calculator and Watershed tabs."""
    return dbc.Card(
        [
            dbc.CardHeader(
                "Optional Runoff Calculations",
                className="fw-bold bg-primary text-white py-2",
            ),
            dbc.CardBody(
                [
                    dbc.Tabs(
                        [
                            dbc.Tab(
                                label="Runoff Calculator",
                                tab_id="curve-number",
                                children=create_curve_number_tab(),
                                label_style={
                                    "color": "#ffffff",
                                    "fontWeight": "bold",
                                    "backgroundColor": "#28a745",
                                    "border": "1px solid #28a745",
                                },
                                active_label_style={
                                    "color": "#ffffff",
                                    "backgroundColor": "#1e7e34",
                                    "border": "1px solid #1e7e34",
                                },
                            ),
                            dbc.Tab(
                                label="Watershed Information",
                                tab_id="runoff-calculator",
                                children=create_runoff_calculator_tab(),
                                label_style={
                                    "color": "#ffffff",
                                    "fontWeight": "bold",
                                    "backgroundColor": "#dc3545",
                                    "border": "1px solid #dc3545",
                                },
                                active_label_style={
                                    "color": "#ffffff",
                                    "backgroundColor": "#a71e2a",
                                    "border": "1px solid #a71e2a",
                                },
                            ),
                        ],
                        id="optional-runoff-tabs",
                        active_tab="curve-number",
                    )
                ],
                className="p-2",
            ),
        ],
        className="mb-3",
    )


def create_water_source_info_tab():
    """Create the content for the Water Source Information tab."""
    # Get existing values from data storage if available
    water_source = dash_storage.get_data("water_source") or "surface_water_sources"
    # Removed from UI: proximity_distance (still stored elsewhere if needed)
    # Removed from UI: water_conveyance (still defaulted on new project / backward compat)
    # Removed from UI: water_ownership, pumping_needed (still stored elsewhere if needed)
    physical_parameters = dash_storage.get_data("physical_parameters") or []
    chemical_parameters = dash_storage.get_data("chemical_parameters") or []
    biological_indicators = dash_storage.get_data("biological_indicators") or []
    emerging_contaminants = dash_storage.get_data("emerging_contaminants") or []
    
    return [
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    "Water Source Configuration",
                                    className="fw-bold bg-primary text-white py-2",
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        html.Label(
                                                            "Water Source:",
                                                            className="fw-bold mb-2",
                                                        ),
                                                        dcc.Dropdown(
                                                            id="water-source-dropdown",
                                                            options=[
                                                                {
                                                                    "label": "(1) Surface Water Sources (streams, Reservoir, canals)",
                                                                    "value": "surface_water_sources",
                                                                },
                                                                {
                                                                    "label": "(2) Urban Stormwater Runoff",
                                                                    "value": "urban_stormwater_runoff",
                                                                },
                                                                {
                                                                    "label": "(3) Rural/Agricultural Runoff",
                                                                    "value": "rural_agricultural_runoff",
                                                                },
                                                                {
                                                                    "label": "(4) Reclaimed Water",
                                                                    "value": "reclaimed_water",
                                                                },
                                                                {
                                                                    "label": "(5) Other Groundwater Basin",
                                                                    "value": "other_groundwater_basin",
                                                                },
                                                                {
                                                                    "label": "(6) Other Non-Conventional Sources",
                                                                    "value": "other_non_conventional_sources",
                                                                },
                                                            ],
                                                            value=water_source,
                                                            placeholder="Select water source...",
                                                        ),
                                                    ],
                                                    width=12,
                                                ),
                                            ]
                                        ),
                                        dbc.Tooltip(
                                            "Primary source supplying water for MAR (surface water, stormwater, reclaimed, etc.)",
                                            target="water-source-dropdown",
                                            placement="top",
                                        ),
                                    ],
                                    className="p-3",
                                ),
                            ],
                            className="h-100 mb-3 mb-lg-0",
                        ),
                    ],
                    xs=12,
                    lg=6,
                ),
                dbc.Col(
                    [create_water_source_location_map_card()],
                    xs=12,
                    lg=6,
                    className="mb-3 mb-lg-0",
                    style={"minHeight": 0, "display": "flex", "flexDirection": "column"},
                ),
            ],
            className="mb-3 g-3 align-items-stretch",
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    "Volume Estimates",
                                    className="fw-bold bg-primary text-white py-2",
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        html.Label(
                                                            "Monthly Average Flow (ft³/month):",
                                                            className="fw-bold mb-2",
                                                        ),
                                                        dcc.Store(
                                                            id="flow-data-store",
                                                            data=_get_flow_store_data(),
                                                        ),
                                                        html.Div(id="flow-table-container"),
                                                    ],
                                                    width=4,
                                                ),
                                                dbc.Col(
                                                    [
                                                        html.Label(
                                                            "Monthly Flow Chart:",
                                                            className="fw-bold mb-2",
                                                        ),
                                                        dcc.Graph(
                                                            id="monthly-flow-chart",
                                                            figure=create_monthly_flow_chart(),
                                                            config={"displayModeBar": True},
                                                        ),
                                                    ],
                                                    width=8,
                                                ),
                                            ]
                                        ),
                                        dbc.Tooltip(
                                            "Edit monthly flows (ft³/month); values feed charts and saved project data",
                                            target="flow-data-table",
                                            placement="top",
                                        ),
                                        dbc.Tooltip(
                                            "Monthly flow bars and cumulative annual flow trend",
                                            target="monthly-flow-chart",
                                            placement="top",
                                        ),
                                    ],
                                    className="p-3",
                                ),
                            ],
                            className="mb-3",
                        )
                    ],
                    width=12,
                )
            ],
        ),
        dbc.Row(
            [
                dbc.Col([_create_optional_runoff_calculations_card()], width=12),
            ],
        ),
    ]


def create_general_tab_content():
    """Create the main tab structure with Water Source Information (includes optional runoff)."""
    return [
        dbc.Tabs(
            [
                dbc.Tab(
                    label="Water Source Information",
                    tab_id="water-source-info",
                    children=create_water_source_info_tab(),
                    label_style={
                        "color": "#ffffff", 
                        "fontWeight": "bold",
                        "backgroundColor": "#2c5aa0",
                        "border": "1px solid #2c5aa0"
                    },
                    active_label_style={
                        "color": "#ffffff", 
                        "backgroundColor": "#1e3d72",
                        "border": "1px solid #1e3d72"
                    },
                ),
            ],
            id="water-source-tabs",
            active_tab="water-source-info",
        )
    ]


