"""
Hydrogeology tab content for MAR DSS dashboard.
"""

import math

import dash_bootstrap_components as dbc
from dash import dcc, html
import pandas as pd
import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.mar.options import mar_options
from mar_dss.rules.defaults import get_default

columns = ["parameter", "Depth/Thickness (ft)", "Hydraulic Conductivity", "Storage Term"]


def normalize_stratigraphy_recharge_target(rows):
    """Ensure exactly one row has recharge_target True; default to the first (top) layer."""
    if not rows:
        return rows
    for row in rows:
        if "recharge_target" not in row:
            row["recharge_target"] = False
    if sum(1 for r in rows if r.get("recharge_target")) != 1:
        for row in rows:
            row["recharge_target"] = False
        rows[0]["recharge_target"] = True
    return rows

default_stratigraphy_unconfined = pd.DataFrame(columns=columns)
parameters = ["Depth of No MAR Storage Zone", "MAR Storage Zone", "Max. Groundwater Table Elevation", "Average Groundwater Table Elevation", "Min Groundwater Table Elevation", "Bedrock Depth"]


def _get_stratigraphy_data():
    """Get stratigraphy data from dash_storage or return defaults."""
    stored_data = dash_storage.get_data("stratigraphy_data")
    if stored_data:
        if isinstance(stored_data, list):
            normalize_stratigraphy_recharge_target(stored_data)
            dash_storage.set_data("stratigraphy_data", stored_data)
        return stored_data
    default_data = [
        {"layer": "Sand", "thickness": 60.0, "conductivity": 10.0, "storage": 0.0001, "yield": 0.25, "selected": False, "recharge_target": True},
        {"layer": "Silt", "thickness": 60.0, "conductivity": 0.01, "storage": 0.0001, "yield": 0.10, "selected": False, "recharge_target": False},
        {"layer": "Gravel", "thickness": 60.0, "conductivity": 100.0, "storage": 0.0001, "yield": 0.30, "selected": False, "recharge_target": False},
    ]
    normalize_stratigraphy_recharge_target(default_data)
    dash_storage.set_data("stratigraphy_data", default_data)
    return default_data


# Calendar order for the groundwater level table (always 12 rows).
GROUNDWATER_MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

_DEFAULT_GROUNDWATER_ELEVATIONS_FT = {
    "January": 75.0,
    "February": 72.0,
    "March": 78.0,
    "April": 82.0,
    "May": 85.0,
    "June": 88.0,
    "July": 90.0,
    "August": 89.0,
    "September": 86.0,
    "October": 83.0,
    "November": 79.0,
    "December": 76.0,
}


def normalize_groundwater_data(raw):
    """Return exactly 12 rows (January–December) with elevations merged from ``raw``."""
    by_month = {}
    if isinstance(raw, list):
        for row in raw:
            if not isinstance(row, dict):
                continue
            m = row.get("month")
            if m is None:
                continue
            key = str(m).strip()
            if key not in _DEFAULT_GROUNDWATER_ELEVATIONS_FT:
                continue
            ev = row.get("elevation")
            try:
                by_month[key] = float(ev)
            except (TypeError, ValueError):
                by_month[key] = _DEFAULT_GROUNDWATER_ELEVATIONS_FT[key]
    out = []
    for name in GROUNDWATER_MONTH_NAMES:
        ev = by_month.get(name)
        if ev is None:
            ev = _DEFAULT_GROUNDWATER_ELEVATIONS_FT[name]
        try:
            ev = float(ev)
            if not math.isfinite(ev):
                ev = _DEFAULT_GROUNDWATER_ELEVATIONS_FT[name]
        except (TypeError, ValueError):
            ev = _DEFAULT_GROUNDWATER_ELEVATIONS_FT[name]
        out.append({"month": name, "elevation": ev})
    return out


def _get_groundwater_data():
    """Get groundwater data from dash_storage or return defaults (always 12 months)."""
    stored_data = dash_storage.get_data("groundwater_data")
    norm = normalize_groundwater_data(stored_data if stored_data else [])
    dash_storage.set_data("groundwater_data", norm)
    return norm


def create_hydrogeologic_settings_content():
    """Create the content for the Hydrogeologic Settings sub-tab (3.1)."""
    return [
        *_build_hydro_tab_header(),
        _build_geometry_and_view_cards(),
    ]


def create_default_hydrologic_parameters_tab_content():
    """Content for the (3.2) Default Parameters tab (same level as 3.1)."""
    notice = html.Div(
        (
            "The default parameters here are generally reasonable. "
            "You do not need to change them unless you have reliable field data."
        ),
        className="text-success fw-bold mb-3",
    )
    return [notice, _build_geometry_hydrogeologic_parameters_card()]


def create_hydro_tab_content():
    """Create the content for the Hydrogeology tab with sub-tabs."""
    return [
        dbc.Tabs(
            [
                dbc.Tab(
                    label="(3.1) Hydrogeologic Settings",
                    tab_id="hydrogeologic-settings-tab",
                    children=create_hydrogeologic_settings_content(),
                ),
                dbc.Tab(
                    label="(3.2) Default Parameters",
                    tab_id="default-hydrologic-parameters-tab",
                    children=create_default_hydrologic_parameters_tab_content(),
                ),
            ],
            id="hydrogeology-subtabs",
            active_tab="hydrogeologic-settings-tab",
            className="hydrogeology-top-tabs w-100",
        ),
    ]


def _build_initial_feasibility_traffic_placeholder():
    """Muted traffic-style columns in one row until the user runs Check Initial Feasibility."""
    dot_style = {
        "width": "22px",
        "height": "22px",
        "backgroundColor": "#adb5bd",
        "opacity": 0.35,
        "verticalAlign": "middle",
    }
    muted = {"opacity": 0.55, "color": "#6c757d"}
    muted_sub = {"opacity": 0.45, "color": "#868e96"}
    cols = []
    for i, opt in enumerate(mar_options()):
        col_border = (
            "mb-2 mb-sm-3 mb-md-0 border-start border-secondary border-opacity-25 ps-md-3"
            if i
            else "mb-2 mb-sm-3 mb-md-0"
        )
        cols.append(
            dbc.Col(
                dbc.Row(
                    [
                        dbc.Col(
                            html.Span(
                                className="rounded-circle d-inline-block flex-shrink-0",
                                style=dot_style,
                            ),
                            width="auto",
                            className="d-flex align-items-start pt-2",
                        ),
                        dbc.Col(
                            [
                                html.Div(
                                    opt.name,
                                    className="fw-semibold fs-5",
                                    style=muted,
                                ),
                                html.Div(
                                    "Not evaluated yet",
                                    className="fs-6",
                                    style=muted_sub,
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
        [
            html.P(
                (
                    'Click "Check Initial Feasibility" to evaluate each engineering option '
                    "using hard and soft hydrogeologic constraints."
                ),
                className="text-muted fs-6 mb-2",
            ),
            html.Div(
                dbc.Row(
                    cols,
                    className="g-2 g-md-3 align-items-start justify-content-lg-between",
                ),
                className="initial-feasibility-traffic initial-feasibility-traffic--pending mt-1",
            ),
        ]
    )


def _build_hydro_tab_header():
    """Build the Hydrogeologic Settings top row (initial feasibility card)."""
    return [
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    "Initial Hydrologic Feasability",
                                    className="fw-bold bg-primary text-white py-2",
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    html.Div(
                                                        id="initial-feasibility-traffic-output",
                                                        children=_build_initial_feasibility_traffic_placeholder(),
                                                    ),
                                                    xs=12,
                                                    md=9,
                                                    lg=9,
                                                    className="pe-md-2 min-w-0",
                                                ),
                                                dbc.Col(
                                                    dbc.Button(
                                                        "Check Initial Feasibility",
                                                        id="check-initial-feasibility-btn",
                                                        color="success",
                                                        className=(
                                                            "text-wrap fw-semibold shadow-sm "
                                                            "ms-md-auto d-block"
                                                        ),
                                                        style={
                                                            "maxWidth": "11rem",
                                                            "minHeight": "3.25rem",
                                                            "lineHeight": "1.15",
                                                            "paddingTop": "0.65rem",
                                                            "paddingBottom": "0.65rem",
                                                            "paddingLeft": "0.75rem",
                                                            "paddingRight": "0.75rem",
                                                        },
                                                        n_clicks=0,
                                                    ),
                                                    xs=12,
                                                    md="auto",
                                                    className=(
                                                        "d-flex justify-content-center "
                                                        "justify-content-md-end align-items-start "
                                                        "pt-2 pt-md-0"
                                                    ),
                                                ),
                                            ],
                                            className="g-2 align-items-start",
                                        ),
                                    ],
                                    className="py-3",
                                ),
                            ],
                            className="h-100",
                        )
                    ],
                    xs=12,
                ),
            ],
            className="g-3 align-items-stretch mb-3",
        )
    ]


def _build_aquifer_type_notice():
    """Static note: aquifer type is inferred from stratigraphy and water-table inputs."""
    return html.P(
        "Aquifer type will be inferred from stratigraphy and water table",
        className="mb-0 small text-muted",
    )


def _build_stratigraphy_table_header():
    """Build the stratigraphy table header."""
    return html.Thead(
        html.Tr(
            [
                html.Th("Parameter", className="fw-bold text-white", style={"background-color": "#2c3e50"}),
                html.Th("Depth/Thickness (ft)", className="fw-bold text-white", style={"background-color": "#2c3e50"}),
                html.Th("Hydraulic Conductivity", className="fw-bold text-white", style={"background-color": "#2c3e50"}),
                html.Th("Storage Term", className="fw-bold text-white", style={"background-color": "#2c3e50"}),
            ]
        )
    )


def _build_stratigraphy_table_row(parameter, depth_id, conductivity_id, storage_id, bg_color, text_color=None):
    """Build a single row for the stratigraphy table."""
    style = {"background-color": bg_color}
    if text_color:
        style["color"] = text_color
    
    return html.Tr(
        [
            html.Td(parameter, className="fw-bold", style=style),
            html.Td(
                dbc.Input(
                    id=depth_id,
                    type="number",
                    placeholder="0.0",
                    size="sm",
                    debounce=True,
                    className="border-0"
                ),
                style=style
            ),
            html.Td(
                dbc.Input(
                    id=conductivity_id,
                    type="number",
                    placeholder="0.0",
                    size="sm",
                    debounce=True,
                    className="border-0"
                ),
                style=style
            ),
            html.Td(
                dbc.Input(
                    id=storage_id,
                    type="number",
                    placeholder="0.0",
                    size="sm",
                    debounce=True,
                    className="border-0"
                ),
                style=style
            ),
        ],
        style=style
    )


def _build_stratigraphy_table_body():
    """Build the stratigraphy table body with all rows."""
    return html.Tbody(
        [
            _build_stratigraphy_table_row(
                "Ground Surface Elevation",
                "ground-surface-depth",
                "ground-surface-conductivity",
                "ground-surface-storage",
                "#ecf0f1"
            ),
            _build_stratigraphy_table_row(
                "Top of MAR Storage Zone",
                "mar-storage-depth",
                "mar-storage-conductivity",
                "mar-storage-storage",
                "#d5dbdb"
            ),
            _build_stratigraphy_table_row(
                "Max. Groundwater Table Elevation",
                "max-gw-depth",
                "max-gw-conductivity",
                "max-gw-storage",
                "#ecf0f1"
            ),
            _build_stratigraphy_table_row(
                "Average Groundwater Table Elevation",
                "avg-gw-depth",
                "avg-gw-conductivity",
                "avg-gw-storage",
                "#d5dbdb"
            ),
            _build_stratigraphy_table_row(
                "Min Groundwater Table Elevation",
                "min-gw-depth",
                "min-gw-conductivity",
                "min-gw-storage",
                "#ecf0f1"
            ),
            _build_stratigraphy_table_row(
                "Bedrock Depth",
                "bedrock-depth",
                "bedrock-conductivity",
                "bedrock-storage",
                "#a9a9a9",
                "white"
            ),
        ]
    )


def _build_stratigraphy_table():
    """Build the complete stratigraphy table."""
    return dbc.Table(
        [
            _build_stratigraphy_table_header(),
            _build_stratigraphy_table_body()
        ],
        striped=True,
        bordered=True,
        hover=True,
        responsive=True,
        className="mb-3"
    )


def _build_stratigraphy_tab():
    """Build the stratigraphy tab content."""
    return dbc.Tab(
        label="Stratigraphy",
        tab_id="stratigraphy-tab",
        label_style={
            "color": "#ffffff", 
            "fontWeight": "bold",
            "backgroundColor": "#28a745",
            "border": "1px solid #28a745"
        },
        active_label_style={
            "color": "#ffffff", 
            "backgroundColor": "#1e7e34",
            "border": "1px solid #1e7e34"
        },
        children=[
            html.Div(
                [
                    html.H5("Stratigraphy Configuration", className="mb-3"),
                    html.P("Configure soil layers and their hydrogeological properties.", className="mb-4"),
                    
                    html.Div(id="stratigraphy-error-message", className="mb-3", children=[]),
                    
                    # Table controls
                    dbc.Row([
                        dbc.Col([
                            dbc.ButtonGroup([
                                dbc.Button("Add Layer", id="add-layer-btn", color="success", size="sm", title="Add a stratigraphy layer row"),
                                dbc.Button("Delete Selected", id="delete-layer-btn", color="danger", size="sm", title="Delete selected layer rows"),
                                dbc.Button("Move Up", id="move-up-btn", color="info", size="sm", title="Move selected layer up"),
                                dbc.Button("Move Down", id="move-down-btn", color="info", size="sm", title="Move selected layer down"),
                            ])
                        ], width=8),
                        dbc.Col([
                            html.Small("Select rows to delete or move", className="text-muted")
                        ], width=4)
                    ], className="mb-3"),
                    
                    # Stratigraphy table
                    dbc.Table(
                        [
                            html.Thead([
                                html.Tr([
                                    html.Th("Select", style={"width": "4%"}),
                                    html.Th("Layer", style={"width": "16%"}),
                                    html.Th("Recharge Target Layer", style={"width": "12%"}, className="text-center"),
                                    html.Th("Thickness (ft)", style={"width": "13%"}),
                                    html.Th("Hydraulic Conductivity (ft/day)", style={"width": "18%"}),
                                    html.Th("Specific Storage (1/ft)", style={"width": "17%"}),
                                    html.Th("Specific Yield", style={"width": "16%"}),
                                ])
                            ]),
                            html.Tbody(id="stratigraphy-table-body")
                        ],
                        striped=True,
                        bordered=True,
                        hover=True,
                        responsive=True,
                        className="mb-3"
                    ),
                    
                    # Store for table data - load from dash_storage if available
                    dcc.Store(id="stratigraphy-data-store", data=_get_stratigraphy_data()),
                ],
                id="stratigraphy-content"
            )
        ]
    )


def _build_groundwater_level_tab():
    """Build the groundwater level tab content."""
    return dbc.Tab(
        label="Groundwater Level",
        tab_id="groundwater-level-tab",
        label_style={
            "color": "#ffffff", 
            "fontWeight": "bold",
            "backgroundColor": "#17a2b8",
            "border": "1px solid #17a2b8"
        },
        active_label_style={
            "color": "#ffffff", 
            "backgroundColor": "#138496",
            "border": "1px solid #138496"
        },
        children=[
            html.Div(
                [
                    html.H5("Groundwater Level Configuration", className="mb-3"),
                    html.P(
                        "Monthly groundwater elevations (ft); one row per calendar month.",
                        className="mb-4",
                    ),
                    # Input fields for elevation and storage depth
                    dbc.Row([
                        dbc.Col([
                            html.Label("Ground Surface Elevation (ft):", className="fw-bold", style={"fontSize": "12px"}),
                            dbc.Input(
                                id="ground-surface-elevation",
                                type="number",
                                value=dash_storage.get_data("ground_surface_elevation") or 120.0,
                                debounce=True,
                                step=0.1,
                                placeholder="Enter elevation",
                                size="sm",
                                className="mb-2"
                            ),
                            html.Label("Maximum MAR Storage Depth (ft):", className="fw-bold", style={"fontSize": "12px"}),
                            dbc.Input(
                                id="max-mar-storage-depth",
                                type="number",
                                value=dash_storage.get_data("max_mar_storage_depth") or 20.0,
                                debounce=True,
                                step=0.1,
                                placeholder="Enter storage depth",
                                size="sm"
                            )
                        ], width=6),
                        dbc.Col([
                            # Groundwater level table
                            dbc.Table(
                                [
                                    html.Thead([
                                        html.Tr([
                                            html.Th("Month", style={"width": "45%"}),
                                            html.Th("Elevation (ft)", style={"width": "55%"}),
                                        ])
                                    ]),
                                    html.Tbody(id="groundwater-table-body")
                                ],
                                striped=True,
                                bordered=True,
                                hover=True,
                                responsive=True,
                                className="mb-3"
                            )
                        ], width=6)
                    ], className="mb-3"),
                    
                    # Store for groundwater data - load from dash_storage if available
                    dcc.Store(id="groundwater-data-store", data=_get_groundwater_data()),
                    dbc.Tooltip(
                        "Ground surface elevation used with groundwater levels for storage and graphics",
                        target="ground-surface-elevation",
                        placement="top",
                    ),
                    dbc.Tooltip(
                        "Maximum vertical thickness available for MAR storage above constraints",
                        target="max-mar-storage-depth",
                        placement="top",
                    ),
                ],
                id="groundwater-level-content"
            )
        ]
    )


def _build_horizontal_extension_tab():
    """Build the horizontal extension tab content."""
    return dbc.Tab(
        label="Horizontal Extension",
        tab_id="horizontal-extension-tab",
        label_style={
            "color": "#ffffff", 
            "fontWeight": "bold",
            "backgroundColor": "#6c757d",
            "border": "1px solid #6c757d"
        },
        active_label_style={
            "color": "#ffffff", 
            "backgroundColor": "#545b62",
            "border": "1px solid #545b62"
        },
        children=[
            html.Div(
                [
                    html.H5("Horizontal Extension Configuration", className="mb-3"),
                    html.P("Configure the horizontal extension parameters for MAR project analysis.", className="mb-4"),
                    
                    # Input fields in two columns
                    dbc.Row([
                        dbc.Col([
                            html.Label("Length (ft):", className="fw-bold mb-2"),
                            dbc.Input(
                                id="extension-length",
                                type="number",
                                value=dash_storage.get_data("extension_length") or 100.0,
                                debounce=True,
                                step=0.1,
                                placeholder="Enter length"
                            )
                        ], width=6),
                        dbc.Col([
                            html.Label("Width (ft):", className="fw-bold mb-2"),
                            dbc.Input(
                                id="extension-width",
                                type="number",
                                value=dash_storage.get_data("extension_width") or 50.0,
                                debounce=True,
                                step=0.1,
                                placeholder="Enter width"
                            )
                        ], width=6)
                    ], className="mb-3"),
                    
                    dbc.Row([
                        dbc.Col([
                            html.Label("Rotation from North (degrees):", className="fw-bold mb-2"),
                            dbc.Input(
                                id="extension-rotation",
                                type="number",
                                value=dash_storage.get_data("extension_rotation") or 0.0,
                                debounce=True,
                                step=1.0,
                                placeholder="Enter rotation angle"
                            )
                        ], width=6),
                    ], className="mb-3"),
                    dbc.Tooltip(
                        "MAR footprint length for horizontal extent analysis (feet)",
                        target="extension-length",
                        placement="top",
                    ),
                    dbc.Tooltip(
                        "MAR footprint width for horizontal extent analysis (feet)",
                        target="extension-width",
                        placement="top",
                    ),
                    dbc.Tooltip(
                        "Rotation of the MAR area from north (degrees)",
                        target="extension-rotation",
                        placement="top",
                    ),
                ],
                id="horizontal-extension-content"
            )
        ]
    )


def _build_geometry_tabs():
    """Build the geometry tabs container."""
    return dbc.Tabs(
        id="geometry-tabs",
        children=[
            _build_stratigraphy_tab(),
            _build_groundwater_level_tab(),
            _build_horizontal_extension_tab(),
        ],
        active_tab="stratigraphy-tab"
    )


def _build_geometry_card():
    """Build the Geometry card."""
    aq_label = dash_storage.get_data("aq_type") or "unconfined"
    try:
        aq_display = str(aq_label).replace("-", " ").title()
    except Exception:
        aq_display = "Unconfined"

    return dbc.Card(
        [
            dbc.CardHeader(
                "Geometry and Stratigraphy",
                className="fw-bold bg-primary text-white",
            ),
            dbc.CardBody(
                [
                    html.Div(
                        [
                            dcc.Store(
                                id="aq-type-inferred-store",
                                data="unconfined",
                            ),
                            html.Div(
                                id="aquifer-type-display",
                                children=f"Aquifer Type: {aq_display}",
                                className="fw-bold mb-2",
                                style={"color": "#fd7e14"},
                            ),
                            _build_aquifer_type_notice(),
                        ],
                        className="mb-3 pb-3 border-bottom",
                    ),
                    _build_geometry_tabs(),
                ]
            ),
        ],
        className="mb-4",
    )


def _build_view_card():
    """Build the View card with three colored tabs."""
    return dbc.Card(
        [
            dbc.CardHeader(
                "View",
                className="fw-bold bg-primary text-white",
            ),
            dbc.CardBody(
                [
                    dbc.Tabs(
                        [
                            dbc.Tab(
                                label="Stratigraphy Cross Section",
                                tab_id="stratigraphy-cross-section",
                                children=[
                                    html.Div(
                                        [
                                            html.H6("Stratigraphy Cross Section", className="mb-3"),
                                            html.P("Visual representation of subsurface stratigraphy layers.", className="mb-3"),
                                            
                                            # Cross-section plot
                                            dcc.Graph(
                                                id="stratigraphy-cross-section-plot",
                                                style={'height': '500px'}
                                            )
                                        ],
                                        id="stratigraphy-cross-section-content"
                                    )
                                ],
                                label_style={
                                    "color": "#ffffff", 
                                    "fontWeight": "bold",
                                    "backgroundColor": "#dc3545",
                                    "border": "1px solid #dc3545"
                                },
                                active_label_style={
                                    "color": "#ffffff", 
                                    "backgroundColor": "#b02a37",
                                    "border": "1px solid #b02a37"
                                },
                            ),
                            dbc.Tab(
                                label="Available MAR Storage",
                                tab_id="available-mar-storage",
                                children=[
                                    html.Div(
                                        [
                                            html.H6("Available MAR Storage", className="mb-3"),
                                            html.P("Analysis of available storage capacity for MAR operations.", className="mb-3"),
                                            
                                            # Groundwater level plot
                                            dcc.Graph(
                                                id="groundwater-plot",
                                                style={'height': '600px'}
                                            )
                                        ],
                                        id="available-mar-storage-content"
                                    )
                                ],
                                label_style={
                                    "color": "#ffffff", 
                                    "fontWeight": "bold",
                                    "backgroundColor": "#28a745",
                                    "border": "1px solid #28a745"
                                },
                                active_label_style={
                                    "color": "#ffffff", 
                                    "backgroundColor": "#1e7e34",
                                    "border": "1px solid #1e7e34"
                                },
                            ),
                            dbc.Tab(
                                label="XY View",
                                tab_id="xy-view",
                                children=[
                                    html.Div(
                                        [
                                            html.H6("XY View", className="mb-3"),
                                            html.P("Plan view visualization of hydrogeological features.", className="mb-3"),
                                            dbc.Button(
                                                "Show Contour Lines",
                                                id="xy-view-show-contours-btn",
                                                color="primary",
                                                size="sm",
                                                className="mb-3",
                                                n_clicks=0,
                                            ),
                                            dcc.Graph(
                                                id="xy-view-plot",
                                                style={"height": "500px"},
                                            ),
                                        ],
                                        id="xy-view-content",
                                    )
                                ],
                                label_style={
                                    "color": "#ffffff", 
                                    "fontWeight": "bold",
                                    "backgroundColor": "#007bff",
                                    "border": "1px solid #007bff"
                                },
                                active_label_style={
                                    "color": "#ffffff", 
                                    "backgroundColor": "#0056b3",
                                    "border": "1px solid #0056b3"
                                },
                            ),
                        ],
                        id="view-tabs",
                        active_tab="stratigraphy-cross-section",
                    ),
                    dbc.Tooltip(
                        "Cross-section sketch of stratigraphy and key horizons",
                        target="stratigraphy-cross-section-plot",
                        placement="top",
                    ),
                    dbc.Tooltip(
                        "Groundwater level and available MAR storage visualization",
                        target="groundwater-plot",
                        placement="top",
                    ),
                    dbc.Tooltip(
                        "Plan-view layout of the MAR geometry",
                        target="xy-view-plot",
                        placement="top",
                    ),
                ]
            ),
        ],
        className="mb-4",
    )


DEFAULT_MAX_DRY_WELL_DEPTH_FT = 120.0

_FIELD_NOTE_STYLE = {"fontSize": "0.72rem", "lineHeight": 1.25}


def _input_field_note(text: str):
    """Single-line helper text under a compact numeric input."""
    return html.Small(
        text,
        className="text-muted d-block",
        style=_FIELD_NOTE_STYLE,
    )


# Matches ``mar_dss.rules.defaults`` keys (lines 3–26); editable overrides in ``rule_defaults_overrides``.
# Each row: key, label, step, note (shown under the input).
RULE_DEFAULT_SCALAR_ROWS = [
    (
        "k_min_vadose_threshold",
        "K min vadose threshold (ft/day)",
        0.01,
        "Minimum K treated as vadose-dominated for classification rules.",
    ),
    (
        "leakage_radius",
        "Leakage radius (ft)",
        1,
        "Horizontal extent (ft) used in leakage-related rule checks.",
    ),
    (
        "maximum_rechargability",
        "Maximum rechargability (%)",
        1,
        "Upper bound on the fraction of source water that may be recharged (%).",
    ),
    (
        "max_injection_Q_per_well",
        "Max injection Q per well (ft³/day)",
        1,
        "Maximum injection rate assumed per well for feasibility and routing rules.",
    ),
    (
        "max_number_of_injection_wells",
        "Max number of injection wells",
        1,
        "Cap on the count of injection wells used in scenario logic.",
    ),
    (
        "max_dry_well_infiltration_rate_in_per_hr",
        "Max dry well infiltration rate (in/hr)",
        1,
        "Upper limit on surface infiltration into the dry well (in/hr).",
    ),
    (
        "max_dry_well_transfer_rate_gpm",
        "Max dry well transfer rate (gpm)",
        1,
        "Upper limit on pumping or transfer into the dry well (gpm).",
    ),
    (
        "max_drywell_depth_ft",
        "Max drywell depth — rule cutoff vs screen depth (ft)",
        1,
        "Rule cutoff comparing screen depth to defaults—not the construction depth limit above.",
    ),
    (
        "vadose_effective_porosity",
        "Vadose effective porosity (-)",
        0.01,
        "Default effective porosity when stratigraphy does not supply a value.",
    ),
    (
        "average_moisture_content",
        "Average moisture content (-)",
        0.01,
        "Default moisture content (0–1) for vadose estimates.",
    ),
    (
        "pathogenic_bacteria_residence_time",
        "Pathogenic bacteria residence time (days)",
        1,
        "Minimum subsurface residence (days) assumed for pathogen attenuation.",
    ),
    (
        "organic_matter_residence_time",
        "Organic matter residence time (days)",
        1,
        "Minimum residence time (days) for natural attenuation of organic matter.",
    ),
    (
        "trace_organic_matter_residence_time",
        "Trace organic matter residence time (days)",
        1,
        "Minimum residence time (days) for trace organic attenuation.",
    ),
    (
        "Nutrients_residence_time",
        "Nutrients residence time (days)",
        1,
        "Minimum residence time (days) for nutrient-related attenuation.",
    ),
]


def _rule_def_input_id(key: str) -> str:
    return f"rule-def-{key.replace('_', '-')}-input"


def _build_rule_defaults_fields_children():
    """Inputs for geohydro ``defaults`` scalars + excessive-deep aquifer bounds (compact columns)."""
    rule_cols = []
    for key, label, step, note in RULE_DEFAULT_SCALAR_ROWS:
        inp_id = _rule_def_input_id(key)
        rule_cols.append(
            dbc.Col(
                [
                    html.Label(
                        label,
                        className="mb-0 text-muted small",
                        htmlFor=inp_id,
                        style={"fontSize": "0.72rem", "lineHeight": 1.2},
                    ),
                    dbc.Input(
                        id=inp_id,
                        type="number",
                        step=step,
                        debounce=True,
                        value=get_default(key),
                        size="sm",
                        className="mb-1",
                    ),
                    _input_field_note(note),
                ],
                xs=12,
                sm=6,
                md=4,
                lg=3,
                className="mb-1",
            )
        )
    lo_id = "rule-def-excessive-deep-aquifer-0-input"
    hi_id = "rule-def-excessive-deep-aquifer-1-input"
    _eda = get_default("excessive_deep_aquifer")
    deep_cols = [
        dbc.Col(
            [
                html.Label(
                    "Excessive deep aquifer — lower (ft)",
                    className="mb-0 text-muted small",
                    htmlFor=lo_id,
                    style={"fontSize": "0.72rem", "lineHeight": 1.2},
                ),
                dbc.Input(
                    id=lo_id,
                    type="number",
                    step=1,
                    debounce=True,
                    value=float(_eda[0]),
                    size="sm",
                    className="mb-1",
                ),
                _input_field_note(
                    "Lower bound of screened aquifer depth (ft) classed as excessively deep."
                ),
            ],
            xs=12,
            sm=6,
            md=4,
            lg=3,
        ),
        dbc.Col(
            [
                html.Label(
                    "Excessive deep aquifer — upper (ft)",
                    className="mb-0 text-muted small",
                    htmlFor=hi_id,
                    style={"fontSize": "0.72rem", "lineHeight": 1.2},
                ),
                dbc.Input(
                    id=hi_id,
                    type="number",
                    step=1,
                    debounce=True,
                    value=float(_eda[1]),
                    size="sm",
                    className="mb-1",
                ),
                _input_field_note(
                    "Upper bound (ft) of the excessively deep aquifer depth band for rules."
                ),
            ],
            xs=12,
            sm=6,
            md=4,
            lg=3,
        ),
    ]
    return [
        html.Hr(className="my-2"),
        html.Div(
            "Overrides for mar_dss.rules.defaults (blank = built-in default).",
            className="text-muted small mb-2",
            style={"fontSize": "0.75rem"},
        ),
        dbc.Row(rule_cols + deep_cols, className="g-2 gx-2 gy-1 mb-0"),
    ]


def _confined_aquifer_head_input_value():
    """Initial display for confined aquifer head (ft); empty if unset."""
    raw = dash_storage.get_data("confined_aquifer_head_ft")
    if raw is None:
        return ""
    try:
        return float(raw)
    except (TypeError, ValueError):
        return ""


def _max_dry_well_depth_input_value():
    """Initial display for maximum dry well depth (ft); default 120."""
    raw = dash_storage.get_data("max_dry_well_depth_ft")
    if raw is None:
        return DEFAULT_MAX_DRY_WELL_DEPTH_FT
    try:
        v = float(raw)
        if math.isfinite(v) and v > 0:
            return v
    except (TypeError, ValueError):
        pass
    return DEFAULT_MAX_DRY_WELL_DEPTH_FT


def _aquitard_conductivity_input_value():
    """Initial display for aquitard K threshold (ft/day); default 1e-3."""
    raw = dash_storage.get_data("aquitard_conductivity_ft_day")
    try:
        aquitard_k = float(raw) if raw is not None else 1e-3
        if aquitard_k <= 0:
            aquitard_k = 1e-3
    except (TypeError, ValueError):
        aquitard_k = 1e-3
    if isinstance(aquitard_k, (int, float)):
        return f"{float(aquitard_k):.12f}".rstrip("0").rstrip(".")
    return str(aquitard_k)


def _build_geometry_hydrogeologic_parameters_card():
    """Default hydrologic parameters below Geometry / View (confined head, dry well, rule overrides)."""
    return dbc.Card(
        [
            dbc.CardHeader(
                "Default parameters",
                className="fw-bold bg-primary text-white py-2 px-3 small",
            ),
            dbc.CardBody(
                [
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Label(
                                        "Aquitard conductivity (ft/day)",
                                        className="mb-0 text-muted small",
                                        htmlFor="aquitard-conductivity-input",
                                        style={"fontSize": "0.72rem"},
                                    ),
                                    dbc.Input(
                                        id="aquitard-conductivity-input",
                                        type="text",
                                        placeholder="e.g. 0.001",
                                        autoComplete="off",
                                        debounce=True,
                                        value=_aquitard_conductivity_input_value(),
                                        size="sm",
                                        className="mb-1",
                                    ),
                                    _input_field_note(
                                        "Layers with hydraulic conductivity at or below this value are treated "
                                        "as aquitards when inferring confined vs unconfined aquifer geometry."
                                    ),
                                    dbc.Tooltip(
                                        "Maximum hydraulic conductivity (ft/day) for classifying a stratigraphy "
                                        "layer as an aquitard in dashboard inference.",
                                        target="aquitard-conductivity-input",
                                        placement="top",
                                    ),
                                ],
                                xs=12,
                                className="mb-2",
                            ),
                        ],
                        className="g-2 gx-2 gy-1 mb-1",
                    ),
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Label(
                                        "Confined aquifer head (ft)",
                                        className="mb-0 text-muted small",
                                        htmlFor="confined-aquifer-head-input",
                                        style={"fontSize": "0.72rem"},
                                    ),
                                    dbc.Input(
                                        id="confined-aquifer-head-input",
                                        type="number",
                                        step=0.1,
                                        debounce=True,
                                        placeholder="Optional; default ~80% static pressure in recharge layer",
                                        value=_confined_aquifer_head_input_value(),
                                        size="sm",
                                        className="mb-1",
                                    ),
                                    _input_field_note(
                                        "Dry-well feasibility: head must allow a downward gradient to inject."
                                    ),
                                ],
                                xs=12,
                                md=6,
                                className="mb-2 mb-md-0",
                            ),
                            dbc.Col(
                                [
                                    html.Label(
                                        "Maximum dry well depth (ft)",
                                        className="mb-0 text-muted small",
                                        htmlFor="max-dry-well-depth-input",
                                        style={"fontSize": "0.72rem"},
                                    ),
                                    dbc.Input(
                                        id="max-dry-well-depth-input",
                                        type="number",
                                        step=1,
                                        min=0.1,
                                        debounce=True,
                                        value=_max_dry_well_depth_input_value(),
                                        size="sm",
                                        className="mb-1",
                                    ),
                                    _input_field_note(
                                        "Values above ~120 ft are uncommon and harder to construct."
                                    ),
                                ],
                                xs=12,
                                md=6,
                            ),
                        ],
                        className="g-2 gx-2 gy-1 mb-1",
                    ),
                    *_build_rule_defaults_fields_children(),
                ],
                className="py-2 px-3",
            ),
        ],
        className="mb-4",
    )


def _build_geometry_and_view_cards():
    """Build the Geometry and View cards side by side."""
    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(_build_geometry_card(), width=6),
                    dbc.Col(_build_view_card(), width=6),
                ]
            ),
        ]
    )