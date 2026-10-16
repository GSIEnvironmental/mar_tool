"""
Engineering Options tab component.
"""

import dash_bootstrap_components as dbc
from dash import html, dcc
import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.utils.tab_tooltips import tab_nav_id, tab_tooltip


def _eng_help_btn(section, title="Help"):
    """Standard ? help button for an Engineering card."""
    return html.Button(
        "?",
        id={"type": "eng-help-btn", "section": section},
        type="button",
        className="mar-help-btn eng-help-btn",
        title=title,
    )


def _eng_card_title(text, section, help_title=None):
    """Compact section title row with a contextual ? help button."""
    return html.Div(
        [
            html.H6(text, className="eng-section-title mb-0"),
            _eng_help_btn(section, help_title or f"Help: {text}"),
        ],
        className="eng-section-header",
    )


def _eng_question(text, className="eng-question"):
    """Bold question / field label."""
    return html.Label(text, className=className)


def _eng_metric(component_id, children="—", className="eng-metric"):
    """Compact read-only metric value."""
    return html.Div(id=component_id, children=children, className=className)


def _eng_help_modal(section, title, body_children):
    """Help modal paired with an Engineering card help button."""
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle(title), close_button=True),
            dbc.ModalBody(body_children),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id={"type": "eng-help-close", "section": section},
                    className="ms-auto",
                    color="secondary",
                )
            ),
        ],
        id={"type": "eng-help-modal", "section": section},
        size="lg",
        scrollable=True,
        is_open=False,
    )


def create_engineering_help_modals():
    """One help modal per Engineering Elements card."""
    return [
        _eng_help_modal(
            "design-metrics",
            "Design Metrics Help",
            [
                html.P(
                    "Sizing depends on how much water is available and how fast it "
                    "arrives. The same monthly total can need very different pipes "
                    "and ponds if it arrives in a few storm pulses versus nearly "
                    "every day.",
                    className="text-muted mb-3",
                ),
                html.H6("Design event flow", className="fw-bold mb-2"),
                html.P(
                    [
                        "This card uses the ",
                        html.Strong("maximum monthly flow"),
                        " from Water Source → Flow Estimates (ft³/month). You set "
                        "how many events that month’s water arrives in; each event "
                        "is treated as a one-day design flow:",
                    ],
                    className="mb-2",
                ),
                html.Pre(
                    "Q_month = max(monthly Flow Estimates)   [ft³/month]\n"
                    "N_events = Number of events per month   [user input]\n"
                    "Q_design (ft³/day) = Q_month / N_events\n"
                    "\n"
                    "Examples:\n"
                    "  • ~4 storm events/month → N_events = 4\n"
                    "  • Nearly uniform daily arrival → N_events = 30",
                    className="bg-light border rounded p-2 small mb-2",
                ),
                html.P(
                    "Smaller N_events → larger Q_design and more conservative sizing"
                    "Capture fraction is fixed at 1.",
                    className="small text-muted mb-3",
                ),
                html.H6(
                    "Peak flow (triangular 24-hour hydrograph)",
                    className="fw-bold mb-2",
                ),
                html.P(
                    "The cost engine treats Q_design as the volume arriving in one "
                    "day and approximates a triangular hydrograph:",
                    className="mb-2",
                ),
                html.Pre(
                    "V_day (ft³) = Q_design (ft³/day)\n"
                    "V = ½ × T_base × Q_peak,   T_base = 24 h\n"
                    "⇒ Q_peak (ft³/h) = V_day / 12\n"
                    "Q_peak (gpm) = Q_peak (ft³/h) × 0.124675",
                    className="bg-light border rounded p-2 small mb-2",
                ),
                html.P(
                    "Dividing by 12 (not 24) gives a peak twice the uniform 24-hour "
                    "average — a screening approximation, not a site-calibrated "
                    "hydrograph. Downstream cards size conveyance and treatment from "
                    "Q_peak and basins from V_day.",
                    className="small text-muted mb-0",
                ),
            ],
        ),
        _eng_help_modal(
            "conveyance-sediment",
            "Conveyance to Recharge Site Help",
            [
                html.P(
                    "Choose how source water is conveyed to the recharge site"
                    "Length is the straight-line (great-circle) distance between "
                    "the source and recharge locations on the Water Source tab.",
                    className="text-muted mb-3",
                ),
                html.H6("Allowable methods", className="fw-bold mb-2"),
                html.Ul(
                    [
                        html.Li(
                            [
                                html.Strong("Gravity Flow in Ditch/Channel: "),
                                "open-channel civil cost only (channel capacity ≥ Q_peak).",
                            ]
                        ),
                        html.Li(
                            [
                                html.Strong("Gravity Flow in Pipeline: "),
                                "gravity pipe/culvert civil cost only "
                                "(Capacity ≥ Q_peak).",
                            ]
                        ),
                        html.Li(
                            [
                                html.Strong("Pumped into Pipeline: "),
                                "force-main package (pipe + pumping) along the "
                                "conveyance length.",
                            ]
                        ),
                        html.Li(
                            [
                                html.Strong("Pumped into Ditch/Channel: "),
                                "channel civil cost plus a separate pump package "
                                "(lift into the ditch/channel).",
                            ]
                        ),
                    ],
                    className="mb-3",
                ),
                html.H6("Cost model", className="fw-bold mb-2"),
                html.Pre(
                    "L (ft) = haversine(source, recharge) × 5280\n"
                    "\n"
                    "Gravity ditch/channel:   Channel @ $93/LF × L\n"
                    "Gravity pipeline:       Pipeline @ $72/LF × L\n"
                    "Pumped pipeline:        Pumped conveyance @ $400/LF × L\n"
                    "Pumped ditch/channel:   Channel @ $93/LF × L\n"
                    "                      + Pump package @ $307/LF × L\n"
                    "                        (civil + pump ≈ $400/LF total)",
                    className="bg-light border rounded p-2 small mb-0",
                ),
            ],
        ),
        _eng_help_modal(
            "sediment-pond",
            "Sediment Removal Help",
            [
                html.P(
                    "Choose whether sediment removal (for example a pond or filter) "
                    "is needed before recharge. When Yes, capital and maintenance "
                    "costs for sediment removal are included.",
                    className="text-muted mb-3",
                ),
                html.H6("Removal target (automatic)", className="fw-bold mb-2"),
                html.P(
                    [
                        "The silt removal target is set from Environmental Impact → "
                        "Water Quality ",
                        html.Strong("question 2 (source-water turbidity)"),
                        ", not from a separate Engineering input:",
                    ],
                    className="mb-2",
                ),
                html.Pre(
                    "If turbidity < 20 NTU  (answers \"<5 NTU\" or \"5-20 NTU\")\n"
                    "    → Medium Silt\n"
                    "Else (\">20 NTU\" or Unknown)\n"
                    "    → Fine Silt  (more conservative / longer settling)",
                    className="bg-light border rounded p-2 small mb-3",
                ),
                html.H6("Sizing equations (when needed = Yes)", className="fw-bold mb-2"),
                html.Pre(
                    "t_settle (min) = (number of 0.4-in falls) × (time per 0.4-in fall)\n"
                    "V_trap (gal) = t_settle (min) × Q_peak (gpm)\n"
                    "Footprint (ft²) = V_trap (ft³) / Water Depth (ft)\n"
                    "  with V_trap (ft³) = V_trap (gal) / 7.48",
                    className="bg-light border rounded p-2 small mb-0",
                ),
            ],
        ),
        _eng_help_modal(
            "storage-pond",
            "Storage Help",
            [
                html.P(
                    "Choose whether a storage pond is needed prior to recharge"
                    "When Yes, capital costs for temporary storage are included.",
                    className="text-muted mb-3",
                ),
                html.H6("Automatic pumped conveyance (when Yes)", className="fw-bold mb-2"),
                html.P(
                    "If a storage pond is used, pumped conveyance to the storage "
                    "pond is assumed automatically (not shown as a separate card). "
                    "All packages are included — pipeline, pumping and bag filter, "
                    "controls, and electrical system — and the conveyance distance "
                    "is fixed at 500 ft.",
                    className="mb-3",
                ),
                html.H6("Sizing (when needed = Yes)", className="fw-bold mb-2"),
                html.Pre(
                    "Area (ft²) = V_day (ft³) / Depth (ft)   [typical depth ≈ 5 ft]\n"
                    "Side length (ft) ≈ √Area   (square footprint assumption)\n"
                    "\n"
                    "Pumped conveyance to storage (automatic):\n"
                    "  Distance = 500 ft (hard-coded)\n"
                    "  Includes: pipeline, pumping/bag filter, controls, electrical",
                    className="bg-light border rounded p-2 small mb-0",
                ),
            ],
        ),
        _eng_help_modal(
            "infiltration-method",
            "Recharge Methods Help",
            [
                html.P(
                    "Choose which recharge methods you would like to evaluate"
                    "Sizing uses transfer rates and capacities from DSS defaults; "
                    "surface methods are volume-based from V_day and available area.",
                    className="text-muted mb-3",
                ),
                html.H6(
                    "Automatic pumped conveyance to infiltration site",
                    className="fw-bold mb-2",
                ),
                html.P(
                    "Pumped conveyance to the infiltration site is always included "
                    "in costing (not shown as a separate card). All packages are "
                    "active: pipeline, pumping and bag filter, controls, and "
                    "electrical system.",
                    className="mb-3",
                ),
                html.H6("Methods", className="fw-bold mb-2"),
                html.Ul(
                    [
                        html.Li(
                            [
                                html.Strong("Surface recharge methods: "),
                                "e.g. infiltration basin, Ag MAR, Flood MAR; "
                                "footprint from volume and depth, constrained by "
                                "maximum infiltration area.",
                            ]
                        ),
                        html.Li(
                            [
                                html.Strong("Dry well(s): "),
                                "vadose-zone wells; count from capacity vs transfer rate.",
                            ]
                        ),
                        html.Li(
                            [
                                html.Strong("Injection well(s): "),
                                "direct aquifer injection; count from per-well Q limits.",
                            ]
                        ),
                    ],
                    className="mb-3",
                ),
                html.H6("Maximum area for recharge", className="fw-bold mb-2"),
                html.P(
                    "The maximum area available for recharge is fixed at 70% of the "
                    "total MAR site area from Overview (not shown as a separate input). "
                    "The remaining 30% is reserved for other infrastructure needed for "
                    "the MAR site. This constraint applies especially to surface recharge "
                    "methods.",
                    className="mb-3",
                ),
                html.H6("Key equations", className="fw-bold mb-2"),
                html.Pre(
                    "N_wells ≈ ceil( Transfer_rate / Well_capacity )\n"
                    "Time_to_drain (days) = V_day (gal) / System_recharge_rate (gal/day)\n"
                    "\n"
                    "Basin area (ft²) = V_day (ft³) / Depth (ft)\n"
                    "Basin drain time (days) ≈ (Depth_ft × 12) / (K_in/hr × 24)\n"
                    "\n"
                    "Max recharge area = 70% of Overview MAR site area\n"
                    "  (30% reserved for other MAR infrastructure)\n"
                    "\n"
                    "Pumped conveyance to infiltration (always on):\n"
                    "  pipeline, pumping/bag filter, controls, electrical",
                    className="bg-light border rounded p-2 small mb-0",
                ),
            ],
        ),
    ]


def create_engineering_elements_content():
    """Create the Engineering Elements sub-tab content."""
    return [
        *create_engineering_help_modals(),
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.Div(
                            [
                                # Design Metrics
                                html.Div(
                                    [
                                        _eng_card_title(
                                            "Design Metrics",
                                            "design-metrics",
                                            "Help: design flow and peak equations",
                                        ),
                                        html.P(
                                            "Design event flow = max monthly flow ÷ number of events (ft³/day)",
                                            className="eng-hint",
                                        ),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        _eng_question(
                                                            "Maximum Monthly Flow (ft³/month)"
                                                        ),
                                                        _eng_metric(
                                                            "max-monthly-flow-display",
                                                            "0.0",
                                                        ),
                                                    ],
                                                    md=4,
                                                    className="eng-field",
                                                ),
                                                dbc.Col(
                                                    [
                                                        _eng_question(
                                                            "Number of Events per Month"
                                                        ),
                                                        dbc.Input(
                                                            type="number",
                                                            value=float(
                                                                dash_storage.get_data(
                                                                    "design_events_per_month"
                                                                )
                                                                or 4.0
                                                            ),
                                                            id="design-events-per-month-input",
                                                            debounce=True,
                                                            min=0.1,
                                                            step=0.1,
                                                            className="eng-input",
                                                        ),
                                                        html.Small(
                                                            "e.g. 4 storms, or 30 for daily arrival",
                                                            className="eng-hint mb-0",
                                                        ),
                                                    ],
                                                    md=4,
                                                    className="eng-field",
                                                ),
                                                dbc.Col(
                                                    [
                                                        _eng_question(
                                                            "Design Event Flow (ft³/day)"
                                                        ),
                                                        _eng_metric(
                                                            "design-event-flow-display",
                                                            "0.0",
                                                            className="eng-metric eng-metric-accent",
                                                        ),
                                                    ],
                                                    md=4,
                                                    className="eng-field",
                                                ),
                                            ],
                                            className="g-2",
                                        ),
                                    ],
                                    className="eng-section",
                                ),
                                # Conveyance
                                html.Div(
                                    [
                                        _eng_card_title(
                                            "Conveyance to Recharge Site",
                                            "conveyance-sediment",
                                            "Help: conveyance methods and distance",
                                        ),
                                        _eng_question(
                                            "How will source water be conveyed to the recharge site?"
                                        ),
                                        dbc.RadioItems(
                                            options=[
                                                {
                                                    "label": "Pumped into Ditch/Channel",
                                                    "value": "pumped_ditch",
                                                },
                                                {
                                                    "label": "Gravity Flow in Ditch/Channel",
                                                    "value": "gravity_ditch",
                                                },
                                                {
                                                    "label": "Pumped into Pipeline",
                                                    "value": "pumped_pipeline",
                                                },
                                                {
                                                    "label": "Gravity Flow in Pipeline",
                                                    "value": "gravity_pipeline",
                                                },
                                            ],
                                            value="gravity_ditch",
                                            id="conveyance-method-radio",
                                            className="eng-radio-stack",
                                        ),
                                        _eng_question(
                                            "Conveyance length (source → recharge)"
                                        ),
                                        _eng_metric(
                                            "conveyance-distance-display",
                                            "Not available — set source and recharge "
                                            "locations on the Water Source tab.",
                                        ),
                                        html.Small(
                                            "Straight-line distance from Water Source tab locations",
                                            className="eng-hint mb-0",
                                        ),
                                    ],
                                    className="eng-section",
                                ),
                                # Sediment + Storage side by side
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                html.Div(
                                                    [
                                                        _eng_card_title(
                                                            "Sediment Removal",
                                                            "sediment-pond",
                                                            "Help: sediment removal need and target",
                                                        ),
                                                        _eng_question(
                                                            "Is sediment removal needed prior to recharge?"
                                                        ),
                                                        dbc.RadioItems(
                                                            options=[
                                                                {
                                                                    "label": "No",
                                                                    "value": "no",
                                                                },
                                                                {
                                                                    "label": "Yes",
                                                                    "value": "yes",
                                                                },
                                                            ],
                                                            value="yes",
                                                            id="sediment-removal-needed-radio",
                                                            inline=True,
                                                            className="eng-radio-inline",
                                                        ),
                                                        _eng_question(
                                                            "Sediment removal target"
                                                        ),
                                                        _eng_metric(
                                                            "sediment-removal-target-display",
                                                            "Medium Silt",
                                                        ),
                                                        html.Small(
                                                            "Auto from Environmental → Water Quality Q2 (turbidity)",
                                                            className="eng-hint mb-0",
                                                        ),
                                                    ],
                                                    className="eng-section eng-section-nested h-100",
                                                ),
                                            ],
                                            md=6,
                                        ),
                                        dbc.Col(
                                            [
                                                html.Div(
                                                    [
                                                        _eng_card_title(
                                                            "Storage",
                                                            "storage-pond",
                                                            "Help: storage pond need",
                                                        ),
                                                        _eng_question(
                                                            "Is a storage pond needed prior to recharge?"
                                                        ),
                                                        dbc.RadioItems(
                                                            options=[
                                                                {
                                                                    "label": "No",
                                                                    "value": "no",
                                                                },
                                                                {
                                                                    "label": "Yes",
                                                                    "value": "yes",
                                                                },
                                                            ],
                                                            value="yes",
                                                            id="storage-needed-radio",
                                                            inline=True,
                                                            className="eng-radio-inline",
                                                        ),
                                                    ],
                                                    className="eng-section eng-section-nested h-100",
                                                ),
                                            ],
                                            md=6,
                                        ),
                                    ],
                                    className="g-2 eng-section-pair",
                                ),
                                # Recharge Methods
                                html.Div(
                                    [
                                        _eng_card_title(
                                            "Recharge Methods",
                                            "infiltration-method",
                                            "Help: surface, dry wells, injection wells",
                                        ),
                                        _eng_question(
                                            "Which recharge method would you like to evaluate?"
                                        ),
                                        dbc.RadioItems(
                                            options=[
                                                {
                                                    "label": (
                                                        "Surface Recharge Methods "
                                                        "(e.g., Infiltration Basin, Ag MAR, Flood MAR)"
                                                    ),
                                                    "value": "infiltration_basin",
                                                },
                                                {
                                                    "label": "Dry Well(s)",
                                                    "value": "dry_wells",
                                                },
                                                {
                                                    "label": "Injection Well(s)",
                                                    "value": "injection_wells",
                                                },
                                            ],
                                            value="infiltration_basin",
                                            id="infiltration-method-radio",
                                            className="eng-radio-stack",
                                        ),
                                    ],
                                    className="eng-section eng-section-last",
                                ),
                            ],
                            className="eng-panel",
                        ),
                    ],
                    width=8,
                ),
                dbc.Col(
                    [
                        html.Div(
                            [
                                html.Img(
                                    src="assets/Engineering2.jpg",
                                    alt="Engineering",
                                    className="eng-side-image",
                                ),
                            ],
                            className="eng-side-panel",
                        )
                    ],
                    width=4,
                ),
            ],
            className="g-3 align-items-start",
        ),
        dbc.Tooltip(
            "Maximum of the twelve monthly Flow Estimates on the Water Source tab",
            target="max-monthly-flow-display",
            placement="top",
        ),
        dbc.Tooltip(
            "How many events the maximum monthly flow is assumed to arrive in "
            "(e.g. 4 storms, or 30 for nearly uniform daily arrival)",
            target="design-events-per-month-input",
            placement="top",
        ),
        dbc.Tooltip(
            "Max monthly flow ÷ number of events (design event flow in ft³/day)",
            target="design-event-flow-display",
            placement="top",
        ),
        dbc.Tooltip(
            "How source water is conveyed to the recharge site",
            target="conveyance-method-radio",
            placement="top",
        ),
        dbc.Tooltip(
            "Straight-line distance between Water Source tab source and recharge sites",
            target="conveyance-distance-display",
            placement="top",
        ),
        dbc.Tooltip(
            "Whether sediment removal is needed before recharge",
            target="sediment-removal-needed-radio",
            placement="top",
        ),
        dbc.Tooltip(
            "Auto-set from Water Quality question 2 (turbidity)",
            target="sediment-removal-target-display",
            placement="top",
        ),
        dbc.Tooltip(
            "Whether a storage pond is needed before recharge",
            target="storage-needed-radio",
            placement="top",
        ),
        dbc.Tooltip(
            "Choose which recharge method to evaluate for sizing and costing",
            target="infiltration-method-radio",
            placement="top",
        ),
    ]


def create_cost_content():
    """Create the Cost sub-tab content."""
    return [
        _eng_help_modal(
            "cost-summary",
            "Cost Summary Help",
            [
                html.P(
                    "Capital, annual maintenance, and 20-year net present value are "
                    "built from the Engineering options you selected and the design "
                    "flow (Q_design → Q_peak / V_day).",
                    className="text-muted mb-3",
                ),
                html.Ul(
                    [
                        html.Li(
                            [
                                html.Strong("Capital Cost: "),
                                "sum of included structures, conveyance, ponds, "
                                "pumps, and infiltration works.",
                            ]
                        ),
                        html.Li(
                            [
                                html.Strong("Annual Maintenance: "),
                                "recurring O&M line items tied to those facilities.",
                            ]
                        ),
                        html.Li(
                            [
                                html.Strong("NPV (20 years): "),
                                "present worth of capital plus discounted maintenance "
                                "over the analysis horizon.",
                            ]
                        ),
                    ],
                    className="mb-3",
                ),
                html.P(
                    "Detail tables (Capital, Maintenance, NPV) list unit costs and "
                    "quantities for each line item. Values update when you change "
                    "Engineering options and re-run analysis.",
                    className="mb-0",
                ),
            ],
        ),
        dbc.Card(
            [
                dbc.CardBody(
                    [
                        _eng_card_title(
                            "Cost Summary",
                            "cost-summary",
                            "Help: capital, maintenance, and NPV",
                        ),
                    ]
                ),
            ],
            className="mb-4",
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.H5(
                                            "Capital Cost",
                                            className="text-center mb-3"
                                        ),
                                        html.H2(
                                            "$0",
                                            className="text-center",
                                            id="capital-cost-display",
                                            style={
                                                "font-size": "1.75rem",
                                                "font-weight": "bold",
                                                "color": "#2c3e50"
                                            }
                                        ),
                                    ]
                                ),
                            ],
                            className="mb-4 text-center",
                        )
                    ],
                    width=4,
                ),
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.H5(
                                            "Annual Maintenance Cost",
                                            className="text-center mb-3"
                                        ),
                                        html.H2(
                                            "$0",
                                            className="text-center",
                                            id="annual-maintenance-cost-display",
                                            style={
                                                "font-size": "1.75rem",
                                                "font-weight": "bold",
                                                "color": "#2c3e50"
                                            }
                                        ),
                                    ]
                                ),
                            ],
                            className="mb-4 text-center",
                        )
                    ],
                    width=4,
                ),
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.H5(
                                            "Net Present Value After 20 Years",
                                            className="text-center mb-3"
                                        ),
                                        html.H2(
                                            "$0",
                                            className="text-center",
                                            id="npv-20-years-display",
                                            style={
                                                "font-size": "1.75rem",
                                                "font-weight": "bold",
                                                "color": "#2c3e50"
                                            }
                                        ),
                                    ]
                                ),
                            ],
                            className="mb-4 text-center",
                        )
                    ],
                    width=4,
                ),
            ],
            className="mb-4",
        ),
        dbc.Tabs(
            [
                dbc.Tab(
                    label="Capital Cost Table", id=tab_nav_id("capital-cost-table-tab"),
                    tab_id="capital-cost-table-tab",
                    children=[
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.P(
                                            "Capital Cost Table will be displayed "
                                            "here.",
                                            id="capital-cost-table-content"
                                        ),
                                    ]
                                ),
                            ],
                            className="mb-4",
                        )
                    ]
                ),
                dbc.Tab(
                    label="Maintenance Cost Table",
                    id=tab_nav_id("maintenance-cost-table-tab"),
                    tab_id="maintenance-cost-table-tab",
                    children=[
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.P(
                                            "Maintenance Cost Table will be "
                                            "displayed here.",
                                            id="maintenance-cost-table-content"
                                        ),
                                    ]
                                ),
                            ],
                            className="mb-4",
                        )
                    ]
                ),
                dbc.Tab(
                    label="Net Present Value Table", id=tab_nav_id("npv-table-tab"),
                    tab_id="npv-table-tab",
                    children=[
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.P(
                                            "Net Present Value Table will be "
                                            "displayed here.",
                                            id="npv-table-content"
                                        ),
                                    ]
                                ),
                            ],
                            className="mb-4",
                        )
                    ]
                ),
            ],
            id="cost-tables-tabs",
            active_tab="capital-cost-table-tab",
        ),
        tab_tooltip(
            "capital-cost-table-tab",
            "Detailed breakdown of capital infrastructure and equipment costs",
        ),
        tab_tooltip(
            "maintenance-cost-table-tab",
            "Annual operating and maintenance cost breakdown by component",
        ),
        tab_tooltip(
            "npv-table-tab",
            "20-year net present value cost and benefit summary",
        ),
        dbc.Tooltip(
            "Total estimated capital cost from engineering selections",
            target="capital-cost-display",
            placement="top",
        ),
        dbc.Tooltip(
            "Annual O&M cost estimate for the MAR facility",
            target="annual-maintenance-cost-display",
            placement="top",
        ),
        dbc.Tooltip(
            "20-year net present value of benefits minus costs",
            target="npv-20-years-display",
            placement="top",
        ),
    ]


def create_engineering_options_content():
    """Create the Engineering Options tab content."""
    return create_engineering_elements_content()

