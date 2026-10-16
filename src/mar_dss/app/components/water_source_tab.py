"""
General tab content and utilities for MAR DSS dashboard (Water Source).
"""

import math

import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from dash import dcc, html
import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.utils.excel_table import INPUT_CELL_BG, build_table_legend, label_cell_style
from mar_dss.app.utils.tab_tooltips import tab_nav_id, tab_tooltip
from .runoff_calculator_tab import (
    create_runoff_calculator_tab,
    create_curve_number_tab,
    create_optional_runoff_calculations_help_modal,
)

WATER_SOURCE_OPTIONS = [
    {
        "label": "(1) Surface Water (Streams, Reservoirs, Canals, etc.)",
        "value": "surface_water_sources",
    },
    {"label": "(2) Urban Stormwater Runoff", "value": "urban_stormwater_runoff"},
    {"label": "(3) Rural/Agricultural Runoff", "value": "rural_agricultural_runoff"},
    {"label": "(4) Treated Drinking Water", "value": "treated_drinking_water"},
    {"label": "(5) Treated Wastewater", "value": "reclaimed_water"},
    {"label": "(6) Other Groundwater Basin", "value": "other_groundwater_basin"},
    {
        "label": (
            "(7) Other Non-Conventional Sources (e.g. Industrial Process Water, "
            "Agricultural Return Flows, Produced Water, Dewatering Project Water, "
            "Desalinated Water, Environmental Remediation Site Water)"
        ),
        "value": "other_non_conventional_sources",
    },
]

WATER_SOURCE_LABELS = {opt["value"]: opt["label"] for opt in WATER_SOURCE_OPTIONS}

# Options (1)–(3): surface / stormwater / ag runoff — runoff calculator is the primary fit
RUNOFF_RELEVANT_WATER_SOURCES = frozenset(
    {
        "surface_water_sources",
        "urban_stormwater_runoff",
        "rural_agricultural_runoff",
    }
)

RUNOFF_CALCULATOR_SOURCE_WARNING = (
    "The Runoff calculator is most appropriate when the water source is surface runoff "
    "(options 1–3). You may still use it to get an estimate of available surface water, "
    "but you may choose not to use it."
)


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


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in statute miles (WGS84 mean Earth radius)."""
    r_earth_mi = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlamb = math.radians(lon2 - lon1)
    h = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlamb / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(h), math.sqrt(max(0.0, 1.0 - h)))
    return r_earth_mi * c


_SITE_COORD_VALUE_COLOR = "#fd7e14"


def water_source_site_coordinates_summary_children():
    """Layout children for Source / Recharge site lat-lon and source-to-site distance (mi)."""
    slat, slon, rlat, rlon = ensure_water_source_site_coordinates()
    dist_mi = _haversine_miles(slat, slon, rlat, rlon)
    num_style = {"color": _SITE_COORD_VALUE_COLOR}
    return [
        html.Label(
            "Site Coordinates",
            className="fw-bold small mb-1 text-primary",
        ),
        html.Div(
            [
                html.Span("Source Site Coordinate (LAT/LONG): "),
                html.Span(
                    f"{slat:.6f}, {slon:.6f}",
                    className="fw-bold",
                    style=num_style,
                ),
            ],
            className="small mb-0",
        ),
        html.Div(
            [
                html.Span("Recharge Site Coordinate (LAT/LONG): "),
                html.Span(
                    f"{rlat:.6f}, {rlon:.6f}",
                    className="fw-bold",
                    style=num_style,
                ),
            ],
            className="small mb-0",
        ),
        html.Div(
            [
                html.Span("Distance from the water source to the MAR project site: "),
                html.Span(
                    f"{dist_mi:.2f} mi",
                    className="fw-bold",
                    style=num_style,
                ),
            ],
            className="small mb-0",
        ),
    ]


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
        monthly_flow = list(FLOW_DEFAULTS)
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


FLOW_MONTHS = [
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
FLOW_DEFAULTS = [0.0] * 12
FLOW_VALUE_COL = "Flow (ft³/month)"


def _normalize_monthly_flows(monthly_flows_raw):
    """Return a length-12 float list from storage / CSV / list input."""
    monthly_flows = monthly_flows_raw
    if monthly_flows is None:
        monthly_flows = FLOW_DEFAULTS
    elif isinstance(monthly_flows, str):
        try:
            import ast

            monthly_flows = ast.literal_eval(monthly_flows)
            if not isinstance(monthly_flows, list) or len(monthly_flows) != 12:
                monthly_flows = FLOW_DEFAULTS
        except (ValueError, SyntaxError):
            monthly_flows = FLOW_DEFAULTS
    elif not isinstance(monthly_flows, list) or len(monthly_flows) != 12:
        monthly_flows = FLOW_DEFAULTS

    try:
        return [float(flow) if flow is not None else 0.0 for flow in monthly_flows]
    except (ValueError, TypeError):
        return list(FLOW_DEFAULTS)


def flow_dict_from_list(monthly_flows):
    """Jan–Dec dict from a 12-value list."""
    flows = _normalize_monthly_flows(monthly_flows)
    return {month: flow for month, flow in zip(FLOW_MONTHS, flows)}


def flow_records_from_dict(flow_data=None):
    """DataTable records from a month→flow dict (or storage defaults)."""
    if flow_data:
        monthly_flows = [
            float(flow_data.get(month, 0) or 0) for month in FLOW_MONTHS
        ]
    else:
        monthly_flows = _normalize_monthly_flows(dash_storage.get_data("monthly_flow"))
    return [
        {"Month": month, FLOW_VALUE_COL: flow}
        for month, flow in zip(FLOW_MONTHS, monthly_flows)
    ]


def flow_dict_from_records(table_data):
    """Month→flow dict from DataTable records."""
    flow_data = {month: 0.0 for month in FLOW_MONTHS}
    if not table_data:
        return flow_data
    for row in table_data:
        month = row.get("Month")
        if month not in flow_data:
            continue
        raw = row.get(FLOW_VALUE_COL, 0)
        try:
            flow_data[month] = float(raw) if raw is not None else 0.0
        except (TypeError, ValueError):
            flow_data[month] = 0.0
    return flow_data


def flow_dicts_equal(a, b):
    """Compare month→flow maps with numeric tolerance."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    for month in FLOW_MONTHS:
        try:
            if abs(float(a.get(month, 0) or 0) - float(b.get(month, 0) or 0)) > 1e-9:
                return False
        except (TypeError, ValueError):
            return False
    return True


def flow_dict_from_input_values(values, ids, fallback=None):
    """Month→flow dict from pattern-matching monthly-flow-input values/ids.

    Blank / None cells keep the fallback (stored) value so a click/focus/blur
    without an edit cannot wipe populated months to zero.
    """
    flow_data = {month: 0.0 for month in FLOW_MONTHS}
    if isinstance(fallback, dict):
        for month in FLOW_MONTHS:
            try:
                flow_data[month] = float(fallback.get(month, 0) or 0)
            except (TypeError, ValueError):
                flow_data[month] = 0.0

    if not values or not ids:
        return flow_data

    for id_dict, raw in zip(ids, values):
        if not isinstance(id_dict, dict):
            continue
        month = id_dict.get("month")
        if month not in flow_data:
            continue
        # Uncommitted / cleared-while-editing → keep previous value
        if raw is None:
            continue
        if isinstance(raw, str) and raw.strip() == "":
            continue
        try:
            flow_data[month] = float(raw)
        except (TypeError, ValueError):
            continue
    return flow_data


def _get_flow_store_data():
    """Get flow data in dictionary format for flow-data-store from dash_storage."""
    return flow_dict_from_list(dash_storage.get_data("monthly_flow"))


def create_editable_flow_table(flow_data=None):
    """Excel-like monthly flow editor: values commit on blur (no Enter required)."""
    if flow_data:
        monthly_flows = [
            float(flow_data.get(month, 0) or 0) for month in FLOW_MONTHS
        ]
    else:
        monthly_flows = _normalize_monthly_flows(dash_storage.get_data("monthly_flow"))

    rows = [
        html.Tr(
            [
                html.Th("Month", className="text-center text-white py-2 px-2"),
                html.Th("Flow (ft³/month)", className="text-center text-white py-2 px-2"),
            ],
            style={"backgroundColor": "#28a745"},
        )
    ]
    for i, (month, flow) in enumerate(zip(FLOW_MONTHS, monthly_flows)):
        rows.append(
            html.Tr(
                [
                    html.Td(
                        month,
                        className="text-center align-middle fw-semibold py-1 px-2",
                        style=label_cell_style(i),
                    ),
                    html.Td(
                        dbc.Input(
                            id={"type": "monthly-flow-input", "month": month},
                            type="number",
                            value=flow,
                            min=0,
                            step=1,
                            debounce=True,
                            size="sm",
                            className="text-center table-cell-input-borderless monthly-flow-input-borderless excel-cell-input",
                        ),
                        className="text-center py-0 px-1 align-middle",
                        style={"backgroundColor": INPUT_CELL_BG},
                    ),
                ],
            )
        )

    return html.Div(
        [
            html.Table(
                rows,
                className="table table-sm table-bordered mb-0 excel-cell-table",
                style={"width": "300px", "maxWidth": "300px", "backgroundColor": "white"},
            ),
            build_table_legend(compact=True),
        ],
        id="flow-data-table",
    )


def create_water_source_location_map_card(water_source=None):
    """Project location map plus water-source configuration controls (full-width card)."""
    if water_source is None:
        water_source = dash_storage.get_data("water_source") or "surface_water_sources"
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
    return dbc.Card(
        [
            dbc.CardHeader(
                html.Div(
                    [
                        html.Span(
                            header_text,
                            id="water-source-location-card-header",
                            className="fw-bold",
                        ),
                        html.Button(
                            "?",
                            id="water-source-config-help-btn",
                            type="button",
                            className="mar-help-btn",
                            title="Help: explain water source configuration",
                        ),
                    ],
                    className="d-flex align-items-center justify-content-between w-100",
                ),
                className="bg-primary text-white py-2",
            ),
            dbc.CardBody(
                [
                    create_water_source_configuration_help_modal(),
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Label(
                                        "Water Source",
                                        className="fw-bold small mb-1 text-primary",
                                    ),
                                    dcc.Dropdown(
                                        id="water-source-dropdown",
                                        options=WATER_SOURCE_OPTIONS,
                                        value=water_source,
                                        placeholder="Select water source...",
                                        className="mb-0",
                                    ),
                                ],
                                xs=12,
                                lg=7,
                            ),
                        ],
                        className="g-2 mb-2",
                    ),
                    dbc.Tooltip(
                        "Primary source supplying water for MAR (surface water, stormwater, reclaimed, etc.)",
                        target="water-source-dropdown",
                        placement="top",
                    ),
                    html.Div(
                        id="water-source-site-coordinates-summary",
                        children=water_source_site_coordinates_summary_children(),
                        className="mb-2",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Label(
                                                "Place marker",
                                                className="fw-bold small me-2 mb-0",
                                            ),
                                            dcc.RadioItems(
                                                id="water-source-map-site-radio",
                                                options=[
                                                    {
                                                        "label": html.Span(
                                                            [
                                                                "Source Site ",
                                                                html.Span(
                                                                    "●",
                                                                    style={
                                                                        "color": "#dc3545",
                                                                        "fontSize": "1.1rem",
                                                                    },
                                                                    title="Red marker",
                                                                ),
                                                            ],
                                                            className="d-inline-flex align-items-center",
                                                        ),
                                                        "value": "source_site",
                                                    },
                                                    {
                                                        "label": html.Span(
                                                            [
                                                                "Recharge Site ",
                                                                html.Span(
                                                                    "●",
                                                                    style={
                                                                        "color": "#0d6efd",
                                                                        "fontSize": "1.1rem",
                                                                    },
                                                                    title="Blue marker",
                                                                ),
                                                            ],
                                                            className="d-inline-flex align-items-center",
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
                                                className="mb-0 small",
                                                inline=True,
                                                labelStyle={
                                                    "display": "inline-flex",
                                                    "alignItems": "center",
                                                    "marginRight": "1rem",
                                                    "cursor": "pointer",
                                                },
                                                inputStyle={"marginRight": "4px"},
                                            ),
                                        ],
                                        className="d-flex align-items-center flex-wrap",
                                    ),
                                    html.Div(
                                        [
                                            html.Label(
                                                "Basemap",
                                                className="fw-bold small me-2 mb-0",
                                            ),
                                            dcc.Dropdown(
                                                id="water-source-overview-map-basemap",
                                                options=OVERVIEW_BASEMAP_OPTIONS,
                                                value=basemap,
                                                clearable=False,
                                                className="mb-0",
                                                style={
                                                    "width": "220px",
                                                    "minWidth": "180px",
                                                },
                                            ),
                                        ],
                                        className="d-flex align-items-center",
                                    ),
                                ],
                                className=(
                                    "d-flex flex-wrap align-items-center "
                                    "justify-content-between gap-2 mb-1"
                                ),
                            ),
                            dbc.Tooltip(
                                "Choose which marker to move, then click the map "
                                "to drop the red Source Site or blue Recharge Site.",
                                target="water-source-map-site-radio",
                                placement="top",
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
                        className="d-flex flex-column",
                        style={"flex": "1 1 auto", "minHeight": 0},
                    ),
                ],
                className="p-3 d-flex flex-column flex-grow-1",
                style={"minHeight": 0},
            ),
        ],
        className="w-100 d-flex flex-column mb-3",
    )


def _create_optional_runoff_calculations_card():
    """Card below Flow Estimates: nested Runoff Calculator and Watershed tabs."""
    water_source = dash_storage.get_data("water_source") or "surface_water_sources"
    show_warning = water_source not in RUNOFF_RELEVANT_WATER_SOURCES
    view_runoff = bool(dash_storage.get_data("view_runoff_calculator"))
    card = dbc.Card(
        [
            dbc.CardHeader(
                html.Div(
                    [
                        html.Span(
                            "Optional Runoff Calculations",
                            className="fw-bold",
                        ),
                        html.Button(
                            "?",
                            id="optional-runoff-help-btn",
                            type="button",
                            className="mar-help-btn",
                            title="Help: optional runoff calculations sections",
                        ),
                    ],
                    className="d-flex align-items-center justify-content-between w-100",
                ),
                className="bg-primary text-white py-2",
            ),
            dbc.CardBody(
                [
                    create_optional_runoff_calculations_help_modal(),
                    html.Div(
                        id="optional-runoff-water-source-warning",
                        children=(
                            dbc.Alert(
                                RUNOFF_CALCULATOR_SOURCE_WARNING,
                                color="warning",
                                className="mb-3",
                            )
                            if show_warning
                            else []
                        ),
                    ),
                    html.Div(
                        [
                            dbc.Tabs(
                                [
                                    dbc.Tab(
                                        label="Runoff Calculator",
                    id=tab_nav_id("curve-number"),
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
                    id=tab_nav_id("runoff-calculator"),
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
                            ),
                            tab_tooltip(
                                "curve-number",
                                "Composite curve number and impervious cover runoff calculations",
                            ),
                            tab_tooltip(
                                "runoff-calculator",
                                "Watershed map, rainfall data, and runoff results for the site",
                            ),
                        ]
                    )
                ],
                className="p-2",
            ),
        ],
        className="mb-3",
    )
    return html.Div(
        [
            dbc.Checkbox(
                id="view-runoff-calculator-check",
                label=html.Strong(
                    "View Runoff Calculator (only if runoff calculator is to be used)"
                ),
                value=view_runoff,
                className="mb-2 collapse-toggle-check",
            ),
            dbc.Collapse(
                card,
                id="optional-runoff-calculations-collapse",
                is_open=view_runoff,
            ),
        ],
        className="mb-3",
    )


def create_water_source_configuration_help_modal():
    """Help modal for Water Source Configuration inputs and decision use."""
    help_items = [
        (
            "Water Source",
            "Select the primary water supply for MAR (surface water, stormwater, "
            "agricultural runoff, treated wastewater, groundwater, or other). This "
            "choice drives cost and design assumptions, environmental and regulatory "
            "context, and whether the optional runoff calculator is the best fit "
            "(most appropriate for options 1–3).",
        ),
        (
            "Source Site Coordinate",
            "Latitude and longitude where water is obtained or enters the system. "
            "Set by selecting Source Site on the map and clicking the desired location. "
            "Used for regional data, runoff tools, conveyance distance, and project context "
            "in feasibility and AI-assisted decisions.",
        ),
        (
            "Recharge Site Coordinate",
            "Latitude and longitude of the MAR recharge project site. Set by selecting "
            "Recharge Site on the map and clicking the location. Paired with the source "
            "site for distance and siting in engineering and decision analysis.",
        ),
        (
            "Distance from water source to MAR project site",
            "Great-circle distance (miles) between source and recharge coordinates. "
            "Informs conveyance length, engineering design, and cost estimates on later tabs.",
        ),
        (
            "Map",
            "Use the map below to place source (red) and recharge (blue) markers, choose a "
            "basemap, and pan/zoom. The saved view is shared with the Overview tab project "
            "location map.",
        ),
    ]

    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Water Source Configuration Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.P(
                        "Define where MAR water comes from and how it relates to the "
                        "recharge site. These settings are saved with your project and flow "
                        "into flow estimates, runoff tools, engineering options, cost "
                        "analysis, and decision support.",
                        className="text-muted mb-3",
                    ),
                    html.Dl(
                        [
                            item
                            for title, description in help_items
                            for item in (
                                html.Dt(title, className="fw-bold"),
                                html.Dd(description, className="mb-3"),
                            )
                        ]
                    ),
                ]
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="water-source-config-help-close-btn",
                    color="secondary",
                    className="ms-auto",
                )
            ),
        ],
        id="water-source-config-help-modal",
        is_open=False,
        size="lg",
        scrollable=True,
        backdrop=True,
        keyboard=True,
    )


def create_volume_estimates_help_modal():
    """Help modal for Flow Estimates inputs and decision use."""
    help_items = [
        (
            "Monthly Average Flow (ft³/month)",
            "Enter the flow of water potentially available for MAR in each calendar "
            "month. Values are averages (not a single storm). The sum of "
            "all twelve months approximates annual supply. Edit a cell and click away or "
            "Tab to save; no Enter key is required.",
        ),
        (
            "Monthly Flow Chart",
            "Visual summary of the table: monthly bars and cumulative annual flow. "
            "Updates automatically when table values change.",
        ),
        (
            "Runoff calculator (optional)",
            [
                "Runoff calculator in the following section can be used to estimate "
                "available surface water. If you decide to use runoff calculator values "
                "as the recharge source, check the ",
                html.Strong("Use Runoff For Recharge"),
                " box in Step 3 below.",
            ],
        ),
        (
            "Use in MAR-Tool decisions",
            "Monthly flows become source water flow in the integrated feasibility "
            "analysis. They drive spread-area sizing, injection and dry-well counts, "
            "annual recharge comparisons, and water-balance checks against aquifer "
            "storage and operational limits on the Analysis tab.",
        ),
    ]

    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Flow Estimates Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.P(
                        "Document how much water may be available for MAR each month"
                        "These flows are saved with your project and feed engineering "
                        "sizing, cost analysis, and feasibility decision rules.",
                        className="text-muted mb-3",
                    ),
                    html.Dl(
                        [
                            item
                            for title, description in help_items
                            for item in (
                                html.Dt(title, className="fw-bold"),
                                html.Dd(description, className="mb-3"),
                            )
                        ]
                    ),
                ]
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="volume-estimates-help-close-btn",
                    color="secondary",
                    className="ms-auto",
                )
            ),
        ],
        id="volume-estimates-help-modal",
        is_open=False,
        size="lg",
        scrollable=True,
        backdrop=True,
        keyboard=True,
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
        html.P(
            "Where the MAR project water will come from, and flows available",
            className="text-muted fs-6 mb-3",
        ),
        dbc.Row(
            [
                dbc.Col(
                    [create_water_source_location_map_card(water_source)],
                    width=12,
                ),
            ],
            className="mb-3",
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    html.Div(
                                        [
                                            html.Span(
                                                "Flow Estimates",
                                                className="fw-bold",
                                            ),
                                            html.Button(
                                                "?",
                                                id="volume-estimates-help-btn",
                                                type="button",
                                                className="mar-help-btn",
                                                title="Help: explain flow estimates",
                                            ),
                                        ],
                                        className="d-flex align-items-center justify-content-between w-100",
                                    ),
                                    className="bg-primary text-white py-2",
                                ),
                                dbc.CardBody(
                                    [
                                        create_volume_estimates_help_modal(),
                                        html.P(
                                            "Total monthly flow potentially available for MAR",
                                            className="text-muted fs-6 mb-1",
                                        ),
                                        html.P(
                                            [
                                                "Runoff calculator in the following section can be used to estimate available surface water. ",
                                                "If you decide to use runoff calculator values as the recharge source, check the ",
                                                html.Strong("Use Runoff For Recharge"),
                                                " box in Step 3 below.",
                                            ],
                                            className="text-primary fs-6 mb-3",
                                        ),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        html.Label(
                                                            "Monthly Average Flow (ft³/month)",
                                                            className="fw-bold mb-2",
                                                        ),
                                                        dbc.Checkbox(
                                                            id="constant-monthly-flow-check",
                                                            label="Use January value for all months",
                                                            value=False,
                                                            className="mb-2 collapse-toggle-check",
                                                        ),
                                                        dcc.Store(
                                                            id="flow-data-store",
                                                            data=_get_flow_store_data(),
                                                        ),
                                                        create_editable_flow_table(
                                                            _get_flow_store_data()
                                                        ),
                                                    ],
                                                    width=4,
                                                ),
                                                dbc.Col(
                                                    [
                                                        html.Label(
                                                            "Monthly Flow Chart",
                                                            className="fw-bold mb-2",
                                                        ),
                                                        dcc.Graph(
                                                            id="monthly-flow-chart",
                                                            figure=create_monthly_flow_chart(
                                                                _get_flow_store_data()
                                                            ),
                                                            config={"displayModeBar": True},
                                                        ),
                                                    ],
                                                    width=8,
                                                ),
                                            ]
                                        ),
                                        dbc.Tooltip(
                                            "Edit a cell and click away (or Tab); value saves without pressing Enter",
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
    """Water Source main tab body (cards only; no nested tab bar)."""
    return create_water_source_info_tab()


