"""
Runoff Calculator tab components for MAR DSS dashboard.
"""

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import dcc, html
import dash_leaflet as dl
import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.utils.excel_table import INPUT_CELL_BG
from mar_dss.app.utils.tab_tooltips import tab_nav_id, tab_tooltip


def _runoff_section_header(title, *, help_button=None):
    """Bold blue section header for peak vs. monthly runoff blocks."""
    title_row = (
        html.Div(
            [
                html.H3(
                    title,
                    className="fw-bold text-primary mb-0",
                    style={"fontSize": "1.75rem"},
                ),
                help_button,
            ],
            className="d-flex align-items-center gap-2",
        )
        if help_button
        else html.H3(
            title,
            className="fw-bold text-primary mb-2 mt-2",
            style={"fontSize": "1.75rem"},
        )
    )
    return html.Div(
        [
            title_row,
            html.Hr(className="my-0 mb-3"),
        ],
        className="mt-2" if help_button else None,
    )


def create_peak_runoff_calculations_help_modal():
    """Help modal for (A) Peak Runoff Calculations workflow and SCS CN method."""
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("(A) Peak Runoff Calculations Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.P(
                        "Peak storm runoff supports sizing of spreading ponds, diversions, "
                        "and site storage. Follow the steps below using the USDA Natural "
                        "Resources Conservation Service (NRCS) Curve Number method.",
                        className="text-muted mb-3",
                    ),
                    html.H6("Workflow", className="fw-bold mb-2"),
                    html.Ol(
                        [
                            html.Li(
                                "Choose option 1A or 1B to compute the percentage of "
                                "impervious cover."
                            ),
                            html.Li("Select the condition of the impervious area."),
                            html.Li(
                                "Select the condition of the pervious area (land cover)."
                            ),
                            html.Li("Select the soil type."),
                            html.Li([
                                "Enter latitude and longitude, then click ",
                                html.Strong("Download Rain Statistics"),
                                ".",
                            ]),
                            html.Li(
                                "Copy and paste the design storm depth of your choice into "
                                "the rainfall table."
                            ),
                            html.Li([
                                "If watershed area is not available, use the ",
                                html.Strong("Watershed Information"),
                                " tab to obtain it.",
                            ]),
                            html.Li(
                                "All remaining runoff values are computed automatically."
                            ),
                        ],
                        className="mb-4 ps-3",
                    ),
                    html.H6("Curve Number method", className="fw-bold mb-2"),
                    html.P(
                        "The Curve Number (CN) method estimates direct runoff from rainfall "
                        "based on land cover, hydrologic condition, and soil group. Impervious "
                        "and pervious areas each have a CN; a weighted composite CN represents "
                        "the watershed. Higher CN means less infiltration and more runoff.",
                        className="mb-3",
                    ),
                    html.P("Composite CN — option 1A (direct connection):", className="fw-bold mb-1"),
                    html.Pre(
                        "CN = (CN_imp × P_imp + CN_perv × (100 − P_imp)) / 100",
                        className="bg-light border rounded p-2 small mb-3",
                    ),
                    html.P(
                        [
                            "CN_imp and CN_perv are curve numbers for impervious and pervious "
                            "areas; P_imp is ",
                            html.Strong("Connected Impervious Area %"),
                            ".",
                        ],
                        className="small text-muted mb-3",
                    ),
                    html.P("Composite CN — option 1B (impervious flows over pervious):", className="fw-bold mb-1"),
                    html.Pre(
                        "CN₁ = (CN_imp × P_imp + CN_perv × (100 − P_imp)) / 100\n"
                        "CN = CN₁ − (R / 100 × P_imp × (CN₁ − CN_perv)) / 100",
                        className="bg-light border rounded p-2 small mb-3",
                    ),
                    html.P(
                        [
                            "P_imp is ",
                            html.Strong("Total Impervious Area %"),
                            "; R is the ",
                            html.Strong("R %"),
                            " routing factor for impervious flow over pervious land before "
                            "entering the drainage system.",
                        ],
                        className="small text-muted mb-3",
                    ),
                    html.H6("Runoff depth and volume", className="fw-bold mb-2"),
                    html.P(
                        "After composite CN is set, MAR-Tool applies the SCS rainfall–runoff "
                        "equation for a single design storm:",
                        className="mb-2",
                    ),
                    html.Pre(
                        "S = (1000 / CN) − 10                    (max potential storage, inches)\n"
                        "Ia = λ × S                              (initial abstraction; λ ≈ 0.05)\n"
                        "Q = (P − Ia)² / (P + (S − Ia))          (runoff depth, inches; if P > Ia)\n"
                        "V = Q × A × 43,560 / 12                 (runoff volume, ft³; A in acres)",
                        className="bg-light border rounded p-2 small mb-0",
                    ),
                    html.P(
                        [
                            "P is ",
                            html.Strong("24-hour Rainfall (inches)"),
                            " from NOAA Atlas 14.",
                        ],
                        className="small text-muted mt-3 mb-0",
                    ),
                ]
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="peak-runoff-help-close-btn",
                    color="secondary",
                    className="ms-auto",
                )
            ),
        ],
        id="peak-runoff-help-modal",
        is_open=False,
        size="lg",
        scrollable=True,
        backdrop=True,
        keyboard=True,
    )


def _peak_runoff_section_header_with_help():
    """Section (A) header with help button."""
    return _runoff_section_header(
        "(A) Peak Runoff Calculations",
        help_button=html.Button(
            "?",
            id="peak-runoff-help-btn",
            type="button",
            className="mar-help-btn",
            title="Help: peak runoff calculations workflow and equations",
        ),
    )


def _monthly_runoff_section_header_with_help():
    """Section (B) header with help button."""
    return _runoff_section_header(
        "(B) Average monthly runoff for recharge",
        help_button=html.Button(
            "?",
            id="monthly-runoff-recharge-help-btn",
            type="button",
            className="mar-help-btn",
            title="Help: monthly runoff for recharge workflow",
        ),
    )


def _get_runoff_calculations_data():
    """Get runoff calculations table data from storage or return defaults."""
    saved_data = dash_storage.get_data("runoff_calculations_table")
    if saved_data:
        return saved_data
    
    # Return default data
    return [
        {"Parameter": "Area (acres)", "Value": 10},
        {"Parameter": "Composite Curve Number", "Value": 50},
        {"Parameter": "24-hour Rainfall (inches)", "Value": 5},
        {"Parameter": "Maximum Potential Storage (inches)", "Value": 10},
        {"Parameter": "Initial Abstraction", "Value": 0.05},
        {"Parameter": "Runoff Depth (inches)", "Value": 1},
        {"Parameter": "Runoff/Precipitation Ratio", "Value": 0.2},
        {"Parameter": "Runoff Volume (ft3)", "Value": 10000}
    ]


def create_runoff_map(lat=38.5816, lon=-121.4944, zoom=10):
    """Create an interactive runoff analysis map using Leaflet."""
    return dl.Map(
        center=[lat, lon],
        zoom=zoom,
        children=[
            dl.TileLayer(url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"),
            dl.LayerGroup(id="marker-layer"),
            dl.LayerGroup(id="stations-layer"),
            dl.LayerGroup(id="watershed-layer"),
        ],
        style={'width': '100%', 'height': '500px', 'borderRadius': '8px', 'boxShadow': '0 4px 6px rgba(0, 0, 0, 0.1)'},
        id="runoff-map"
    )


def create_map_card():
    """Create the map card component."""
    return dbc.Card([
        dbc.CardHeader("Runoff Analysis Map", className="fw-bold bg-primary text-white"),
        dbc.CardBody([
            create_runoff_map(),
            dbc.Tooltip(
                "Click the map to set coordinates; use layers for markers, stations, and watershed",
                target="runoff-map",
                placement="top",
            ),
        ])
    ])


def create_coordinate_inputs():
    """Create the latitude and longitude input fields."""
    return [
        html.Label("Selected Latitude:", className="fw-bold"),
        dbc.Input(
            id="selected-latitude",
            type="number",
            placeholder="Click map to set latitude",
            debounce=True,
            step=0.000001,
            style={"margin-bottom": "10px"}
        ),
        html.Label("Selected Longitude:", className="fw-bold"),
        dbc.Input(
            id="selected-longitude",
            type="number",
            placeholder="Click map to set longitude",
            debounce=True,
            step=0.000001,
            style={"margin-bottom": "15px"}
        ),
    ]


def create_action_buttons():
    """Create the action buttons for runoff analysis."""
    return [
        dbc.Button(
            "Obtain nearby streams",
            id="obtain-streams-btn",
            color="success",
            className="me-2 mb-3",
            title="Find stream features near the selected map location",
        ),
        dbc.Button(
            "Get Watershed Info",
            id="get-watershed-btn",
            color="info",
            className="me-2 mb-3",
            title="Retrieve watershed boundaries and attributes for the area",
        ),
        dbc.Button(
            "Reset drainage point",
            id="reset-watershed-map-btn",
            color="secondary",
            outline=True,
            className="mb-3",
            title=(
                "Clear the drainage marker, streams, and watershed overlay so you can "
                "click the map and choose a new drainage point"
            ),
        ),
    ]


def create_controls_card():
    """Create the analysis controls card component."""
    return dbc.Card([
        dbc.CardHeader("Analysis Controls", className="fw-bold bg-primary text-white"),
        dbc.CardBody([
            *create_action_buttons(),
            dcc.Loading(
                id="watershed-action-loading",
                type="circle",
                color="#0d6efd",
                parent_style={"minHeight": "48px"},
                children=html.Div(id="status-message", className="mt-3 mb-3"),
            ),
            html.Hr(),
            *create_coordinate_inputs(),
            html.Hr(),
            html.Div(id="runoff-results", className="mt-3"),
            html.Small(
                "Click on the map to add monitoring points or draw watershed boundaries.",
                className="text-muted"
            ),
            dbc.Tooltip(
                "Latitude from map click or manual entry (decimal degrees)",
                target="selected-latitude",
                placement="top",
            ),
            dbc.Tooltip(
                "Longitude from map click or manual entry (decimal degrees)",
                target="selected-longitude",
                placement="top",
            ),
            dbc.Tooltip(
                "Clear marker, streams, and watershed so you can pick a new drainage point",
                target="reset-watershed-map-btn",
                placement="top",
            ),
        ])
    ])


def create_impervious_curve_number_content():
    """Create the impervious curve number selection component."""
    # Curve number data for impervious surfaces
    curve_number_options = [
        {"label": "Concrete - Fresh/Uncracked (CN: 99)", "value": "concrete_fresh"},
        {"label": "Concrete - Weathered/Cracked (CN: 97)", "value": "concrete_weathered"},
        {"label": "Asphalt - Fresh/Uncracked (CN: 99)", "value": "asphalt_fresh"},
        {"label": "Asphalt - Weathered/Cracked (CN: 97)", "value": "asphalt_weathered"},
    ]
    
    return dbc.Card([
        dbc.CardHeader("Estimated Impervious Curve Number Values", className="fw-bold bg-primary text-white"),
        dbc.CardBody([
            html.Label("Select Surface Condition:", className="fw-bold mb-2"),
            dbc.Select(
                id="impervious-curve-number-select",
                options=curve_number_options,
                placeholder="Select a surface condition...",
                className="mb-3"
            ),
            html.Div(id="selected-impervious-curve-number-display", className="mt-3"),
            dbc.Tooltip(
                "Curve number for fully impervious surfaces (SCS CN tables)",
                target="impervious-curve-number-select",
                placement="top",
            ),
        ])
    ])


def create_cover_soil_curve_number_content():
    """Create the cover description and soil type curve number selection component."""
    # Cover Description options (rows)
    cover_description_options = [
        {"label": "Open Space - Poor Condition", "value": "open_space_poor"},
        {"label": "Open Space - Fair Condition", "value": "open_space_fair"},
        {"label": "Open Space - Good Condition", "value": "open_space_good"},
        {"label": "Natural Desert Landscaping (pervious areas only)", "value": "natural_desert"},
        {"label": "Developing Urban Areas - Newly Graded Areas", "value": "developing_urban"},
    ]
    
    # Hydrologic Soil Type options (columns)
    soil_type_options = [
        {"label": "Hydrologic Soil Type A", "value": "type_a"},
        {"label": "Hydrologic Soil Type B", "value": "type_b"},
        {"label": "Hydrologic Soil Type C", "value": "type_c"},
        {"label": "Hydrologic Soil Type D", "value": "type_d"},
    ]
    
    return dbc.Card([
        dbc.CardHeader("Estimated Pervious Curve Number Values", className="fw-bold bg-primary text-white"),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("Cover Description:", className="fw-bold mb-2"),
                    dbc.Select(
                        id="cover-description-select",
                        options=cover_description_options,
                        placeholder="Select cover description...",
                        className="mb-3"
                    ),
                ], width=6),
                dbc.Col([
                    html.Label("Hydrologic Soil Type:", className="fw-bold mb-2"),
                    dbc.Select(
                        id="soil-type-select",
                        options=soil_type_options,
                        placeholder="Select soil type...",
                        className="mb-3"
                    ),
                ], width=6)
            ]),
            html.Div(id="selected-curve-number-display", className="mt-3"),
            dbc.Tooltip(
                "Land cover condition for pervious portion of the watershed",
                target="cover-description-select",
                placement="top",
            ),
            dbc.Tooltip(
                "NRCS hydrologic soil group for pervious CN lookup",
                target="soil-type-select",
                placement="top",
            ),
        ])
    ])


def create_single_storm_runoff_help_modal():
    """Help modal for the Runoff for Single Storm card."""
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Runoff for Single Storm Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.P(
                        "This section computes runoff from a user-specified design storm for "
                        "sizing engineering elements (e.g., spreading ponds, diversions, and "
                        "site storage).",
                        className="mb-3",
                    ),
                    html.H6("Design storm and NOAA rainfall", className="fw-bold mb-2"),
                    html.P(
                        [
                            "Choose a design return period and storm duration that match your "
                            "engineering criteria—for example, a ",
                            html.Strong("5-year"),
                            " annual recurrence interval (ARI) and a ",
                            html.Strong("24-hour"),
                            " duration. Enter latitude and longitude (or check ",
                            html.Strong("Use site coordinates"),
                            "), then click ",
                            html.Strong("Download Rain Statistics"),
                            " to load NOAA Atlas 14 precipitation frequency estimates for "
                            "that location.",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            "From the NOAA table, select the row for your chosen return period "
                            "and duration, and copy the precipitation depth (inches) into ",
                            html.Strong("24-hour Rainfall (inches)"),
                            " in the Runoff Calculations table—or type a value directly if you "
                            "already have a design depth.",
                        ],
                        className="mb-3",
                    ),
                    html.H6("Runoff Calculations table", className="fw-bold mb-2"),
                    html.Ul(
                        [
                            html.Li(
                                "Enter watershed area (acres), or obtain area from the "
                                "Watershed Information tab."
                            ),
                            html.Li(
                                "Composite Curve Number carries forward from Step 1."
                            ),
                            html.Li(
                                "Runoff depth, ratio, and volume update automatically from "
                                "the SCS curve number method."
                            ),
                            html.Li([
                                "Use the ",
                                html.Strong("?"),
                                " beside Runoff Calculations for parameter definitions and "
                                "equations.",
                            ]),
                            html.Li(
                                "Runoff Volume (ft³) can be synced to the Engineering tab "
                                "via the checkbox below the table."
                            ),
                        ],
                        className="mb-0 ps-3",
                    ),
                ]
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="single-storm-runoff-help-close-btn",
                    color="secondary",
                    className="ms-auto",
                )
            ),
        ],
        id="single-storm-runoff-help-modal",
        is_open=False,
        size="lg",
        scrollable=True,
        backdrop=True,
        keyboard=True,
    )


def create_monthly_runoff_recharge_help_modal():
    """Help modal for (B) Average monthly runoff for recharge."""
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("(B) Average Monthly Runoff for Recharge Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.P(
                        "This optional section estimates average monthly runoff volumes "
                        "available for managed aquifer recharge. Use it when you do not "
                        "already have monthly source-water estimates for your site.",
                        className="text-muted mb-3",
                    ),
                    html.H6("Workflow", className="fw-bold mb-2"),
                    html.Ol(
                        [
                            html.Li([
                                "Complete ",
                                html.Strong("Step 1"),
                                " (composite curve number) and ",
                                html.Strong("Step 2"),
                                " (runoff calculations table) in section (A) above—especially ",
                                html.Strong("Composite Curve Number"),
                                ", ",
                                html.Strong("Area (acres)"),
                                ", and site latitude/longitude.",
                            ]),
                            html.Li([
                                "Enter ",
                                html.Strong("Average number of rain events per month"),
                                " (typical runoff-producing storms used to annualize monthly "
                                "precipitation).",
                            ]),
                            html.Li([
                                "Click ",
                                html.Strong("Get Monthly Rainfall and Runoff"),
                                " to download NASA POWER monthly precipitation for the site and "
                                "compute monthly runoff depth and volume using the composite CN "
                                "from section (A).",
                            ]),
                            html.Li(
                                "Review the monthly table and chart. Runoff Volume (ft³/month) "
                                "is the primary output for recharge planning."
                            ),
                            html.Li([
                                "To use these values as your MAR source water, check ",
                                html.Strong("Use Runoff For Recharge"),
                                "—monthly volumes copy into ",
                                html.Strong("Volume Estimates"),
                                " (Step 3 on the Water Source tab).",
                            ]),
                        ],
                        className="mb-4 ps-3",
                    ),
                    html.H6("Inputs and data sources", className="fw-bold mb-2"),
                    html.Ul(
                        [
                            html.Li([
                                html.Strong("Composite CN"),
                                " and ",
                                html.Strong("Area (acres)"),
                                " come from the Runoff Calculations table in section (A).",
                            ]),
                            html.Li([
                                "Monthly precipitation is downloaded from ",
                                html.Strong("NASA POWER"),
                                " for the latitude/longitude entered in Step 2.",
                            ]),
                            html.Li(
                                "Monthly rain depth is divided by the number of rain events per "
                                "month; each event is routed through the SCS curve-number "
                                "method, then summed to give monthly runoff depth and volume."
                            ),
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            "The summary line below the section header updates automatically "
                            "to show the current CN, rain events per month, watershed area, "
                            "and site coordinates driving the calculation.",
                        ],
                        className="small text-muted mb-0",
                    ),
                ]
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="monthly-runoff-recharge-help-close-btn",
                    color="secondary",
                    className="ms-auto",
                )
            ),
        ],
        id="monthly-runoff-recharge-help-modal",
        is_open=False,
        size="lg",
        scrollable=True,
        backdrop=True,
        keyboard=True,
    )


def create_composite_cn_help_modal():
    """Help modal for the composite curve number table (Step 1)."""
    help_items = [
        (
            "Entering curve numbers",
            [
                "If you already know the curve numbers for impervious and pervious areas, "
                "type them directly in the table below. Otherwise, click ",
                html.Strong("Select Curve Numbers"),
                " to choose typical impervious surface conditions, land cover, and "
                "hydrologic soil type—the selected values populate ",
                html.Strong("CN impervious"),
                " and ",
                html.Strong("CN pervious"),
                " in the table.",
            ],
        ),
        (
            "CN impervious",
            "Curve number for impervious surfaces (e.g., pavement, roofs). Typically "
            "97–99 from SCS tables depending on surface condition.",
        ),
        (
            "CN pervious",
            "Curve number for pervious land cover and hydrologic soil group (A–D). "
            "Reflects infiltration capacity of undeveloped or landscaped areas.",
        ),
        (
            "Connected Impervious Area % (option 1A only)",
            "Percent of the watershed that is impervious and drains directly to the "
            "storm system without flowing over pervious land.",
        ),
        (
            "Total Impervious Area % (option 1B only)",
            "Total percent of the watershed covered by impervious surfaces, including "
            "areas that route over pervious land before entering the drainage system.",
        ),
        (
            "R % (option 1B only)",
            "Routing factor (%): fraction of impervious area whose runoff travels over "
            "pervious land before reaching the outlet. Used in the option 1B composite "
            "CN equation.",
        ),
        (
            "Composite CN",
            "Weighted curve number for the whole watershed. Computed automatically from "
            "the rows above (see the ? beside (A) Peak Runoff Calculations for "
            "equations). Used in Step 2 runoff calculations.",
        ),
    ]

    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Composite Curve Number Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.P(
                        "Choose option 1A or 1B above, then complete the composite CN table.",
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
                    id="composite-cn-help-close-btn",
                    color="secondary",
                    className="ms-auto",
                )
            ),
        ],
        id="composite-cn-help-modal",
        is_open=False,
        size="lg",
        scrollable=True,
        backdrop=True,
        keyboard=True,
    )


def create_curve_number_selection_help_modal():
    """Help modal explaining Select Curve Numbers popup options."""
    impervious_items = [
        ("Concrete — Fresh/Uncracked (CN 99)", "New, uncracked concrete; runoff is essentially complete."),
        ("Concrete — Weathered/Cracked (CN 97)", "Older or cracked concrete; slightly more infiltration than fresh."),
        ("Asphalt — Fresh/Uncracked (CN 99)", "New asphalt pavement; very little infiltration."),
        ("Asphalt — Weathered/Cracked (CN 97)", "Worn or cracked asphalt; modestly lower CN than fresh."),
    ]
    cover_items = [
        (
            "Open Space — Poor Condition",
            "Lawns, parks, or open areas in fair-to-poor hydrologic condition (e.g., sparse cover, compaction).",
        ),
        (
            "Open Space — Fair Condition",
            "Average lawns, parks, or cemeteries with moderate cover and infiltration.",
        ),
        (
            "Open Space — Good Condition",
            "Well-maintained lawns, parks, or open space with good vegetative cover.",
        ),
        (
            "Natural Desert Landscaping (pervious areas only)",
            "Desert landscaping with rock or xeric plants on pervious portions of the site.",
        ),
        (
            "Developing Urban Areas — Newly Graded Areas",
            "Bare or newly graded urban land with little vegetative cover.",
        ),
    ]
    soil_items = [
        ("Hydrologic Soil Type A", "High infiltration (e.g., sand, gravel); lowest CN for a given cover."),
        ("Hydrologic Soil Type B", "Moderate infiltration (e.g., sandy loam)."),
        ("Hydrologic Soil Type C", "Slow infiltration (e.g., loam, silty soils)."),
        ("Hydrologic Soil Type D", "Very slow infiltration (e.g., clay); highest CN for a given cover."),
    ]

    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Select Curve Numbers Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.P(
                        "Choose typical NRCS/TR-55 curve numbers for impervious and pervious "
                        "portions of the watershed. Selections populate CN impervious and "
                        "CN pervious in the composite CN table when you close this window.",
                        className="text-muted mb-3",
                    ),
                    html.H6("Impervious surface condition", className="fw-bold mb-2"),
                    html.Dl(
                        [
                            item
                            for title, desc in impervious_items
                            for item in (
                                html.Dt(title, className="fw-bold"),
                                html.Dd(desc, className="mb-2"),
                            )
                        ],
                        className="mb-3",
                    ),
                    html.H6("Pervious cover description", className="fw-bold mb-2"),
                    html.Dl(
                        [
                            item
                            for title, desc in cover_items
                            for item in (
                                html.Dt(title, className="fw-bold"),
                                html.Dd(desc, className="mb-2"),
                            )
                        ],
                        className="mb-3",
                    ),
                    html.H6("Hydrologic soil type", className="fw-bold mb-2"),
                    html.Dl(
                        [
                            item
                            for title, desc in soil_items
                            for item in (
                                html.Dt(title, className="fw-bold"),
                                html.Dd(desc, className="mb-2"),
                            )
                        ],
                        className="mb-3",
                    ),
                    html.H6("Pervious CN lookup (cover × soil)", className="fw-bold mb-2"),
                    html.P(
                        "CN pervious is read from the standard lookup below once both cover "
                        "and soil type are selected:",
                        className="small mb-2",
                    ),
                    html.Table(
                        [
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th("Cover", className="small"),
                                        html.Th("A", className="small text-center"),
                                        html.Th("B", className="small text-center"),
                                        html.Th("C", className="small text-center"),
                                        html.Th("D", className="small text-center"),
                                    ]
                                )
                            ),
                            html.Tbody(
                                [
                                    html.Tr(
                                        [
                                            html.Td(label, className="small"),
                                            html.Td(str(row["type_a"]), className="small text-center"),
                                            html.Td(str(row["type_b"]), className="small text-center"),
                                            html.Td(str(row["type_c"]), className="small text-center"),
                                            html.Td(str(row["type_d"]), className="small text-center"),
                                        ]
                                    )
                                    for label, row in [
                                        ("Open Space — Poor", {"type_a": 56, "type_b": 70, "type_c": 79, "type_d": 84}),
                                        ("Open Space — Fair", {"type_a": 36, "type_b": 57, "type_c": 70, "type_d": 77}),
                                        ("Open Space — Good", {"type_a": 26, "type_b": 48, "type_c": 64, "type_d": 71}),
                                        ("Natural Desert", {"type_a": 50, "type_b": 67, "type_c": 78, "type_d": 82}),
                                        ("Developing Urban", {"type_a": 67, "type_b": 79, "type_c": 87, "type_d": 91}),
                                    ]
                                ]
                            ),
                        ],
                        className="table table-sm table-bordered mb-0",
                    ),
                ]
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="curve-number-selection-help-close-btn",
                    color="secondary",
                    className="ms-auto",
                )
            ),
        ],
        id="curve-number-selection-help-modal",
        is_open=False,
        size="lg",
        scrollable=True,
        backdrop=True,
        keyboard=True,
    )


def create_curve_number_selection_modal():
    """Modal with impervious + pervious curve number selectors."""
    return [
        dbc.Modal(
            [
                dbc.ModalHeader(
                    html.Div(
                        [
                            dbc.ModalTitle("Select Curve Numbers", className="mb-0"),
                            html.Button(
                                "?",
                                id="curve-number-selection-help-btn",
                                type="button",
                                className="mar-help-btn me-4",
                                title="Help: explain curve number options",
                            ),
                        ],
                        className="d-flex align-items-center justify-content-between w-100 pe-2",
                    ),
                    close_button=True,
                ),
                dbc.ModalBody(
                    dbc.Row(
                        [
                            dbc.Col(create_impervious_curve_number_content(), md=6, className="mb-3 mb-md-0"),
                            dbc.Col(create_cover_soil_curve_number_content(), md=6),
                        ]
                    )
                ),
                dbc.ModalFooter(
                    dbc.Button(
                        "Done",
                        id="curve-number-modal-done-btn",
                        color="primary",
                        className="ms-auto",
                    )
                ),
            ],
            id="curve-number-selection-modal",
            is_open=False,
            size="xl",
            scrollable=True,
            backdrop=True,
            keyboard=True,
        ),
        create_curve_number_selection_help_modal(),
    ]


def create_runoff_calculations_help_modal():
    """Help modal describing Runoff Calculations table parameters and formulas."""
    help_items = [
        (
            "Area (acres)",
            "Watershed or project drainage area. Enter manually or obtain from the "
            "Watershed Information tab.",
        ),
        (
            "Composite Curve Number",
            "Weighted curve number from impervious and pervious land cover (Composite CN table). "
            "Used in SCS runoff equations.",
        ),
        (
            "24-hour Rainfall (inches)",
            "Design storm depth for a 24-hour period. Copy a value from the NOAA Atlas 14 "
            "rain statistics table after downloading rain data.",
        ),
        (
            "Maximum Potential Storage (inches)",
            "Maximum soil retention before runoff begins (SCS method). "
            "Computed as S = (1000 / CN) − 10 from the composite curve number.",
        ),
        (
            "Initial Abstraction",
            "Fraction of maximum potential storage (S) representing initial losses "
            "(interception, depression storage, infiltration). A typical value is 0.05. "
            "Initial abstraction depth is Ia = fraction × S.",
        ),
        (
            "Runoff Depth (inches)",
            "Runoff depth Q from the SCS equation: Q = (P − Ia)² / (P + (S − Ia)), "
            "where P is rainfall, S is maximum potential storage, and Ia is initial abstraction depth. "
            "Computed automatically when inputs change.",
        ),
        (
            "Runoff/Precipitation Ratio",
            "Fraction of rainfall that becomes runoff: Q / P. Computed automatically.",
        ),
        (
            "Runoff Volume (ft³)",
            "Total runoff volume: Q × area × 43,560 / 12, converting acre-inches of runoff "
            "depth to cubic feet. Computed automatically.",
        ),
    ]

    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Runoff Calculations Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.P(
                        [
                            "This table uses the USDA SCS Curve Number method for a single design storm. ",
                            html.Span(className="excel-legend-swatch excel-legend-input me-1"),
                            " Amber cells are entered by you; ",
                            html.Span(className="excel-legend-swatch excel-legend-computed me-1"),
                            " blue cells are computed automatically when inputs change.",
                        ],
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
                    id="runoff-calculations-help-close-btn",
                    color="secondary",
                    className="ms-auto",
                )
            ),
        ],
        id="runoff-calculations-help-modal",
        is_open=False,
        size="lg",
        scrollable=True,
        backdrop=True,
        keyboard=True,
    )


def _optional_runoff_help_body():
    """Build help modal body for Optional Runoff Calculations."""
    return [
        html.P(
            [
                "This is an optional step if you do not already have information about "
                "water available for MAR at your site. The Runoff Calculator is used for "
                "two goals: ",
                html.Strong("(a) peak runoff calculations"),
                ", for sizing and design of engineering elements (e.g., spreading ponds, "
                "diversions, and site storage); and ",
                html.Strong("(b) average monthly runoff for recharge"),
                ", which estimates available volumes by month—you can choose to recharge "
                "a fraction of these rates. ",
                html.Em("Details are provided throughout the runoff calculation below."),
                " On the ",
                html.Strong("Runoff Calculator"),
                " tab, curve number methods, NOAA rainfall statistics, single-storm peak "
                "runoff, and monthly recharge estimates are combined; use the ",
                html.Strong("?"),
                " beside ",
                html.Strong("(A) Peak Runoff Calculations"),
                " and ",
                html.Strong("(B) Average monthly runoff for recharge"),
                " for workflow steps and equations. Check ",
                html.Strong("Use Runoff For Recharge"),
                " in section (B) to copy results into Volume Estimates. The ",
                html.Strong("Watershed Information"),
                " tab (use the ",
                html.Strong("?"),
                " there) provides an interactive map, nearby streams, and watershed "
                "delineation to obtain drainage area and basin characteristics.",
            ],
            className="mb-0",
        ),
    ]


def create_optional_runoff_calculations_help_modal():
    """Help modal for Optional Runoff Calculations (section list is data-driven)."""
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Optional Runoff Calculations Help"),
                close_button=True,
            ),
            dbc.ModalBody(_optional_runoff_help_body()),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="optional-runoff-help-close-btn",
                    color="secondary",
                    className="ms-auto",
                )
            ),
        ],
        id="optional-runoff-help-modal",
        is_open=False,
        size="lg",
        scrollable=True,
        backdrop=True,
        keyboard=True,
    )


def create_watershed_information_help_modal():
    """Help modal for the Watershed Information tab."""
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Watershed Information Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.H6("Primary goal", className="fw-bold mb-2"),
                    html.P(
                        [
                            "The main purpose of this tab is to obtain ",
                            html.Strong("watershed information"),
                            "—such as ",
                            html.Strong("drainage area"),
                            ", ",
                            html.Strong("land use"),
                            ", and related basin characteristics—for your selected map "
                            "location. Use these values on the ",
                            html.Strong("Runoff Calculator"),
                            " tab: enter ",
                            html.Strong("Area (acres)"),
                            " in the Runoff Calculations table and use land-cover / "
                            "impervious-cover information when choosing curve numbers in ",
                            html.Strong("Step 1 (Composite Curve Number)"),
                            ".",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        "After streams are shown, choose the drainage outlet by clicking "
                        "on a stream. Keep the marker on the stream line so watershed "
                        "delineation is accurate.",
                        className="text-muted mb-3",
                    ),
                    html.H6("Workflow", className="fw-bold mb-2"),
                    html.Ol(
                        [
                            html.Li([
                                "Click the ",
                                html.Strong("Runoff Analysis Map"),
                                " near your site of interest—the coordinates appear in ",
                                html.Strong("Analysis Controls"),
                                " and can be edited manually.",
                            ]),
                            html.Li([
                                "Click ",
                                html.Strong("Obtain nearby streams"),
                                " to download and display stream features near the selected "
                                "point (within approximately 10 miles) as blue lines on the map.",
                            ]),
                            html.Li([
                                "Select a ",
                                html.Strong("point of drainage"),
                                " by clicking on the stream where you want the watershed "
                                "outlet. Place the marker ",
                                html.Strong("directly on the stream"),
                                "—if there is space between the marker and the stream, the "
                                "watershed may not be calculated correctly.",
                            ]),
                            html.Li([
                                "Click ",
                                html.Strong("Get Watershed Info"),
                                " to delineate the watershed for that drainage point. The "
                                "watershed boundary appears in red on the map; basin characteristics "
                                "(area, land use, and other parameters) load in the ",
                                html.Strong("Watershed Information"),
                                " results table below the map.",
                            ]),
                            html.Li([
                                "To choose a different drainage point after streams or a "
                                "watershed are shown, click ",
                                html.Strong("Reset drainage point"),
                                " to clear the marker and map overlays, then click the map "
                                "(or a stream) again and re-run ",
                                html.Strong("Obtain nearby streams"),
                                " and/or ",
                                html.Strong("Get Watershed Info"),
                                ".",
                            ]),
                            html.Li([
                                "Review the results table and transfer values to the Runoff "
                                "Calculator tab: copy ",
                                html.Strong("Area (acres)"),
                                " into the Runoff Calculations table, and use land-use / "
                                "cover information to select appropriate impervious and pervious "
                                "curve numbers in ",
                                html.Strong("Step 1"),
                                ".",
                            ]),
                        ],
                        className="mb-4 ps-3",
                    ),
                    html.H6("Map symbols", className="fw-bold mb-2"),
                    html.Ul(
                        [
                            html.Li([
                                html.Strong("Red marker"),
                                " — selected ",
                                html.Strong("point of drainage"),
                                " (the latitude/longitude used by ",
                                html.Strong("Get Watershed Info"),
                                "). Place it ",
                                html.Strong("directly on a stream"),
                                "; a gap between the red marker and the stream can cause "
                                "incorrect watershed results.",
                            ]),
                            html.Li([
                                html.Strong("Blue lines"),
                                " — nearby streams loaded by ",
                                html.Strong("Obtain nearby streams"),
                                ". Use these to choose where to put the red drainage marker.",
                            ]),
                            html.Li([
                                html.Strong("Red outline / shaded area"),
                                " — delineated watershed boundary after ",
                                html.Strong("Get Watershed Info"),
                                ".",
                            ]),
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            "On the Runoff Calculator tab, check ",
                            html.Strong("Use site coordinates"),
                            " to copy the Water Source site location into rainfall download "
                            "and single-storm runoff fields.",
                        ],
                        className="small text-muted mb-0",
                    ),
                ]
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="watershed-info-help-close-btn",
                    color="secondary",
                    className="ms-auto",
                )
            ),
        ],
        id="watershed-info-help-modal",
        is_open=False,
        size="lg",
        scrollable=True,
        backdrop=True,
        keyboard=True,
    )


def _watershed_info_tab_header_with_help():
    """Watershed Information tab title with help button."""
    return _runoff_section_header(
        "Watershed Information",
        help_button=html.Button(
            "?",
            id="watershed-info-help-btn",
            type="button",
            className="mar-help-btn",
            title="Help: watershed map, streams, and delineation",
        ),
    )


def create_results_card():
    """Create the watershed information results card."""
    return dbc.Card([
        dbc.CardHeader("Watershed Information", className="fw-bold bg-primary text-white"),
        dbc.CardBody([
            dcc.Loading(
                id="watershed-info-loading",
                type="circle",
                color="#0d6efd",
                children=html.Div(
                    id="watershed-info-content",
                    style={"minHeight": "400px", "overflow": "auto"},
                ),
            )
        ])
    ], style={'minHeight': '500px'})


def create_curve_number_tab():
    """Create the content for the Runoff Calculator tab."""
    return [
        html.P(
            "The runoff calculations was developed based on STORME-PFAS tool that was developed "
            "as part of SERDP Project ER23-3741 (PFAS in Stormwater) (Vines et al., in review)",
            className="mb-3 text-danger fst-italic fw-bold",
        ),
        _peak_runoff_section_header_with_help(),
        create_peak_runoff_calculations_help_modal(),
        dbc.Card([
            dbc.CardBody([
                html.H5("Step 1: Composite Curve Number Based on % Impervious Cover Calculator (Pick 1A or 1B)", 
                        className="fw-bold mb-3"),
                            dbc.Row([
                                dbc.Col([
                                    html.Div(
                                        dbc.RadioItems(
                                            id="impervious-outlet-option",
                                            options=[
                                                {
                                                    "label": (
                                                        "1A: Pick this one if all of your impervious areas "
                                                        "outlet directly to the drainage system "
                                                        "(see figure below)."
                                                    ),
                                                    "value": "1A",
                                                },
                                                {
                                                    "label": (
                                                        "1B: Pick this one if all/some of impervious area "
                                                        "flow spreads over pervious areas before entering "
                                                        "the drainage system."
                                                    ),
                                                    "value": "1B",
                                                },
                                            ],
                                            value="1A",
                                            className="runoff-outlet-radio-group",
                                            input_class_name="runoff-outlet-radio-input",
                                            label_class_name="runoff-outlet-radio-label",
                                            label_checked_class_name="runoff-outlet-radio-label-checked",
                                        ),
                                        className="runoff-outlet-radio-group-wrapper mb-3",
                                    ),
                                    html.Div(
                                        [
                                            dbc.Button(
                                                "Select Curve Numbers",
                                                id="open-curve-number-modal-btn",
                                                color="primary",
                                                className="mb-3 me-2",
                                                title="Choose typical impervious and pervious curve number values",
                                            ),
                                            html.Button(
                                                "?",
                                                id="composite-cn-help-btn",
                                                type="button",
                                                className="mar-help-btn mb-3",
                                                title="Help: composite curve number table",
                                            ),
                                        ],
                                        className="d-flex align-items-center flex-wrap",
                                    ),
                                    create_composite_cn_help_modal(),
                                    html.Div(id="composite-cn-table", className="mt-0"),
                                    dcc.Store(id="composite-cn-table-store", data=None),
                                    *create_curve_number_selection_modal(),
                                ], width=6),
                                dbc.Col([
                                    html.Img(
                                        src="/assets/curve_number.jpg",
                                        alt="Curve Number Diagram",
                                        style={"maxWidth": "70%", "height": "auto"}
                                    )
                                ], width=6)
                            ])
                        ])
                    ], className="mt-4 mb-4"),
                    dbc.Row([
                        dbc.Col([
                            dbc.Card([
                                dbc.CardHeader(
                                    html.Div(
                                        [
                                            html.Span(
                                                "Runoff for Single Storm",
                                                className="fw-bold",
                                            ),
                                            html.Button(
                                                "?",
                                                id="single-storm-runoff-help-btn",
                                                type="button",
                                                className="mar-help-btn",
                                                title="Help: single-storm design runoff",
                                            ),
                                        ],
                                        className="d-flex align-items-center justify-content-between w-100",
                                    ),
                                    className="bg-primary text-white py-2",
                                ),
                                dbc.CardBody([
                                    create_single_storm_runoff_help_modal(),
                                    html.H5("Step 2: Provide watershed area upstream of the diversion point of interest, and compute runoff.", 
                                            className="fw-bold mb-3"),
                                    dbc.Row([
                                        dbc.Col([
                                            html.Label("Latitude:", className="fw-bold mb-2"),
                                            dbc.Input(
                                                id="runoff-single-storm-latitude",
                                                type="number",
                                                value=38.5816,
                                                debounce=True,
                                                placeholder="Enter latitude",
                                                className="mb-2",
                                            ),
                                        ], width=6),
                                        dbc.Col([
                                            html.Label("Longitude:", className="fw-bold mb-2"),
                                            dbc.Input(
                                                id="runoff-single-storm-longitude",
                                                type="number",
                                                value=-121.4944,
                                                debounce=True,
                                                placeholder="Enter longitude",
                                                className="mb-2",
                                            ),
                                        ], width=6),
                                    ]),
                                    html.Div(
                                        dbc.Checkbox(
                                            id="use-site-coordinates-for-runoff-check",
                                            label="Use site coordinates (Source Site from Water Source map)",
                                            value=bool(
                                                dash_storage.get_data(
                                                    "use_site_coords_for_runoff"
                                                )
                                            ),
                                            className="runoff-engineering-sync-check mb-0",
                                            input_class_name="runoff-engineering-sync-input",
                                            label_class_name="runoff-engineering-sync-label",
                                        ),
                                        className="runoff-engineering-sync-card mb-3",
                                    ),
                                    dbc.Button(
                                        "Download Rain Statistics",
                                        id="download-rain-statistics-btn",
                                        color="secondary",
                                        className="mb-3",
                                        title="Fetch NOAA precipitation statistics for the coordinates entered",
                                    ),
                                    html.Div(id="rain-statistics-download-message", className="mb-2"),
                                    html.Div(id="runoff-calculations-content", className="mt-3"),
                                    dbc.Row([
                                        dbc.Col([
                                            html.Div(
                                                [
                                                    html.H6(
                                                        "Runoff Calculations",
                                                        className="fw-bold mb-0",
                                                    ),
                                                    html.Button(
                                                        "?",
                                                        id="runoff-calculations-help-btn",
                                                        type="button",
                                                        className="mar-help-btn ms-2",
                                                        title="Help: explain runoff calculation parameters",
                                                    ),
                                                ],
                                                className="d-flex align-items-center mb-2",
                                            ),
                                            create_runoff_calculations_help_modal(),
                                            dcc.Store(
                                                id="runoff-calculations-table",
                                                data=_get_runoff_calculations_data(),
                                            ),
                                            html.Div(id="runoff-calculations-table-view"),
                                            html.Div(
                                                [
                                                    html.P(
                                                        [
                                                            html.Strong("Note: "),
                                                            "The ",
                                                            html.Strong("Runoff Volume (ft³)"),
                                                            " value can be used in the ",
                                                            html.Strong("Engineering"),
                                                            " tab to size engineering elements.",
                                                        ],
                                                        className="mb-2 small",
                                                    ),
                                                    dbc.Checkbox(
                                                        id="use-runoff-for-engineering-check",
                                                        label=(
                                                            "Use this estimate for Engineering "
                                                            "(copies Runoff Volume to Total Runoff on the Engineering tab)"
                                                        ),
                                                        value=False,
                                                        className="runoff-engineering-sync-check mb-0",
                                                        input_class_name="runoff-engineering-sync-input",
                                                        label_class_name="runoff-engineering-sync-label",
                                                    ),
                                                ],
                                                className="runoff-engineering-sync-card mt-3 mb-0",
                                            ),
                                        ], width=6),
                                        dbc.Col([
                                            html.Div(id="rain-statistics-table-placeholder")
                                        ], width=6)
                                    ])
                                ])
                            ])
                        ], width=12)
                    ], className="mt-4"),
                    _monthly_runoff_section_header_with_help(),
                    create_monthly_runoff_recharge_help_modal(),
                    html.Div(
                        id="monthly-runoff-calc-summary",
                        className="text-muted small mb-4",
                    ),
                    dbc.Row([
                        dbc.Col([
                            dbc.Card([
                                dbc.CardHeader("Monthly Runoff Estimation", className="fw-bold bg-primary text-white"),
                                dbc.CardBody([
                                    html.H5("Step 3: Estimate Annual Runoff", 
                                            className="fw-bold mb-3"),
                                    dbc.Row([
                                        dbc.Col([
                                            html.Label(
                                                "Average number of rain events per month:",
                                                className="form-label mb-2",
                                            ),
                                            html.Div(
                                                [
                                                    dbc.Input(
                                                        id="rain-events-per-month",
                                                        type="number",
                                                        value=3.0,
                                                        step=0.1,
                                                        className="text-center table-cell-input-borderless excel-cell-input",
                                                        style={"maxWidth": "100px"},
                                                    ),
                                                    dbc.FormFeedback(
                                                        id="rain-events-per-month-feedback",
                                                        type="invalid",
                                                    ),
                                                ],
                                                className="excel-rain-events-cell d-inline-block mb-3",
                                                style={
                                                    "backgroundColor": INPUT_CELL_BG,
                                                    "border": "1px solid #dee2e6",
                                                    "borderRadius": "2px",
                                                    "padding": "2px 4px",
                                                },
                                            ),
                                        ], width="auto"),
                                    ]),
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Button(
                                                "Get Monthly Rainfall and Runoff",
                                                id="get-monthly-rain-btn",
                                                color="primary",
                                                className="mb-3",
                                                title="Compute monthly rainfall depth and runoff using storm statistics",
                                            )
                                        ], width="auto"),
                                        dbc.Col([
                                            html.Div(
                                                dbc.Checkbox(
                                                    id="use-runoff-for-recharge-check",
                                                    label="Use Runoff For Recharge",
                                                    value=False,
                                                    className="runoff-engineering-sync-check mb-0",
                                                    input_class_name="runoff-engineering-sync-input",
                                                    label_class_name="runoff-engineering-sync-label",
                                                ),
                                                className="runoff-engineering-sync-card mb-3 ms-3",
                                            )
                                        ], width="auto")
                                    ]),
                                    html.Div(id="monthly-runoff-estimation-content")
                                ])
                            ])
                        ], width=12)
                    ], className="mt-4"),
        dbc.Tooltip(
            "Open typical impervious and pervious curve number selectors",
            target="open-curve-number-modal-btn",
            placement="top",
        ),
        dbc.Tooltip(
            "Choose how impervious drainage connects to the storm system (affects composite CN)",
            target="impervious-outlet-option",
            placement="top",
        ),
        dbc.Tooltip(
            "When checked, Latitude/Longitude are filled from the Water Source Source Site marker",
            target="use-site-coordinates-for-runoff-check",
            placement="top",
        ),
        dbc.Tooltip(
            "Latitude for NOAA rain download and single-storm runoff (decimal degrees)",
            target="runoff-single-storm-latitude",
            placement="top",
        ),
        dbc.Tooltip(
            "Longitude for NOAA rain download and single-storm runoff (decimal degrees)",
            target="runoff-single-storm-longitude",
            placement="top",
        ),
        dbc.Tooltip(
            "Editable runoff calculation inputs and intermediate results",
            target="runoff-calculations-table",
            placement="top",
        ),
        dbc.Tooltip(
            "Typical number of runoff-producing storms per month for annualization",
            target="rain-events-per-month",
            placement="top",
        ),
        dbc.Tooltip(
            "When checked, monthly runoff estimates can feed MAR recharge inputs elsewhere",
            target="use-runoff-for-recharge-check",
            placement="top",
        ),
        dbc.Tooltip(
            "When checked, copies Runoff Volume (ft³) to Total Runoff on the Engineering tab",
            target="use-runoff-for-engineering-check",
            placement="top",
        ),
    ]


def create_runoff_calculator_tab():
    """Create the content for the Watershed Information tab."""
    return [
        _watershed_info_tab_header_with_help(),
        create_watershed_information_help_modal(),
        html.Div(
            [
                dbc.Tabs(
                    [
                        dbc.Tab(
                            label="Rainfall and Watershed Information",
                    id=tab_nav_id("rainfall-watershed-tab"),
                            tab_id="rainfall-watershed-tab",
                            children=[
                                dbc.Row([
                                    dbc.Col([
                                        create_map_card()
                                    ], width=8),
                                    dbc.Col([
                                        create_controls_card()
                                    ], width=4)
                                ], className="mb-4"),

                                dbc.Row([
                                    dbc.Col([
                                        create_results_card()
                                    ])
                                ])
                            ]
                        )
                    ],
                    id="runoff-calculator-tabs",
                    active_tab="rainfall-watershed-tab",
                ),
                tab_tooltip(
                    "rainfall-watershed-tab",
                    "Interactive watershed map, rainfall controls, and runoff results",
                ),
            ]
        )
    ]