"""
Runoff Calculator tab components for MAR DSS dashboard.
"""

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import dcc, html
import dash_leaflet as dl
import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.utils.tab_tooltips import tab_nav_id, tab_tooltip


def _runoff_section_header(title):
    """Bold blue section header for peak vs. monthly runoff blocks."""
    return html.H3(
        title,
        className="fw-bold text-primary mb-4 mt-2",
        style={"fontSize": "1.75rem"},
    )


def _peak_runoff_steps_summary():
    """Numbered workflow summary under the peak runoff section header."""
    return html.Ol(
        [
            html.Li(
                "Choose option 1A or 1B to compute the percentage of impervious cover."
            ),
            html.Li("Select the condition of the impervious area."),
            html.Li("Select the condition of the pervious area (land cover)."),
            html.Li("Select the soil type."),
            html.Li([
                "Enter latitude and longitude, then click ",
                html.Strong("Download Rain Statistics"),
                ".",
            ]),
            html.Li(
                "Copy and paste the design storm depth of your choice into the rainfall table."
            ),
            html.Li([
                "If watershed area is not available, use the ",
                html.Strong("Watershed Information"),
                " tab to obtain it.",
            ]),
            html.Li("All remaining runoff values are computed automatically."),
        ],
        className="mb-4 ps-3",
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
            className="mb-3",
            title="Retrieve watershed boundaries and attributes for the area",
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


def create_curve_number_selection_modal():
    """Modal with impervious + pervious curve number selectors."""
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Select Curve Numbers"),
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
        dbc.Alert(
            [
                html.Div("About this section", className="fw-bold mb-2"),
                html.P(
                    "This is an optional step if you do not already have information about "
                    "water available for MAR at your site.",
                    className="mb-2",
                ),
                html.P("The Runoff Calculator is used for two goals:", className="mb-2"),
                html.Ul(
                    [
                        html.Li([
                            html.Strong("(a) Peak runoff calculations: "),
                            "Used in the sizing and design of engineering elements "
                            "(e.g., spreading ponds, diversions, and site storage).",
                        ]),
                        html.Li([
                            html.Strong("(b) Average monthly runoff for recharge: "),
                            "Estimates available recharge volumes by month; you can choose "
                            "to recharge a fraction of these rates.",
                        ]),
                    ],
                    className="mb-0 ps-3",
                ),
            ],
            color="light",
            className="border mb-3 py-2",
        ),
        html.P(
            "The runoff calculations was developed based on STORME-PFAS tool that was developed "
            "as part of SERDP Project ER23-3741 (PFAS in Stormwater) (Vines et al., in review)",
            className="mb-3 text-danger fst-italic fw-bold",
        ),
        _runoff_section_header("(A) Peak Runoff Calculations"),
        _peak_runoff_steps_summary(),
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
                                    html.P(
                                        [
                                            "Enter curve number values directly in the table below, ",
                                            "or use typical values from ",
                                            html.Strong("Select Curve Numbers"),
                                            ".",
                                        ],
                                        className="text-muted small mb-2",
                                    ),
                                    dbc.Button(
                                        "Select Curve Numbers",
                                        id="open-curve-number-modal-btn",
                                        color="primary",
                                        className="mb-3",
                                        title="Choose typical impervious and pervious curve number values",
                                    ),
                                    html.Div(id="composite-cn-table", className="mt-0"),
                                    dcc.Store(id="composite-cn-table-store", data=None),
                                    create_curve_number_selection_modal(),
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
                                dbc.CardHeader("Runoff for Single Storm", className="fw-bold bg-primary text-white"),
                                dbc.CardBody([
                                    html.H5("Step 2: Provide watershed area upstream of the diversion point of interest, and compute runoff.", 
                                            className="fw-bold mb-3"),
                                    html.Small(
                                        "The single storm runoff calculation is useful for the design of the MAR spreading pond sizing and site storage needed. The storm intensity will be downloaded from NOAA at the coordinate provided.",
                                        className="text-muted d-block mb-3"
                                    ),
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
                                            html.H6("Runoff Calculations", className="fw-bold mb-2"),
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
                    _runoff_section_header("(B) Average monthly runoff for recharge"),
                    html.P(
                        [
                            "This section is an optional tool to estimate monthly runoff volumes "
                            "available for recharge. If you choose to use this estimate, run the "
                            "calculation and check the ",
                            html.Strong("Use Runoff For Recharge"),
                            " box.",
                        ],
                        className="mb-2",
                    ),
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
                                            html.Label("Average number of rain events per month:", 
                                                       className="form-label mb-2"),
                                            dbc.Input(
                                                id="rain-events-per-month",
                                                type="number",
                                                value=3.0,
                                                min=0.1,
                                                step=0.1,
                                                className="mb-3"
                                            )
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
        html.H3("Watershed Information", className="mb-4"),
        html.P("Calculate and analyze runoff patterns for your MAR project location.", className="mb-4"),

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