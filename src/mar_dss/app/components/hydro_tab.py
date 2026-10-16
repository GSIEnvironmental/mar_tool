"""
Hydrogeology tab content for MAR DSS dashboard.
"""

import ast
import copy
import json
import math

import dash_bootstrap_components as dbc
from dash import dcc, html
import pandas as pd
import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.utils.excel_table import build_table_legend
from mar_dss.app.utils.tab_tooltips import tab_nav_id, tab_tooltip
from mar_dss.mar.options import mar_options
from mar_dss.rules.defaults import get_default

columns = ["parameter", "Depth/Thickness (ft)", "Hydraulic Conductivity", "Storage Term"]

# Display labels for Initial Hydrologic Feasibility (internal option.name unchanged)
INITIAL_FEASIBILITY_OPTION_LABELS = {
    "Surface Recharge": "Surface Recharge (e.g., Infiltration Basin)",
    "Dry Well": "Dry Well(s)",
    "Injection Well": "Injection Well(s)",
}


def initial_feasibility_option_label(option_name: str) -> str:
    """User-facing name for an option in Initial Hydrologic Feasibility."""
    return INITIAL_FEASIBILITY_OPTION_LABELS.get(option_name, option_name)


# Typical hydrogeologic defaults by soil / lithology type (K ft/day, Ss 1/ft, Sy -).
# "Other" uses mid-range averages across the named types (geom. mean K; mean Sy/Ss).
SOIL_PROPERTIES = {
    "Gravel": {"conductivity": 100.0, "storage": 0.0001, "yield": 0.30},
    "Sand": {"conductivity": 10.0, "storage": 0.0001, "yield": 0.25},
    "Silt": {"conductivity": 0.01, "storage": 0.0001, "yield": 0.10},
    "Loam": {"conductivity": 0.001, "storage": 0.0001, "yield": 0.05},
    "Clay": {"conductivity": 0.0001, "storage": 0.0001, "yield": 0.01},
    "Other": {"conductivity": 0.063, "storage": 0.0001, "yield": 0.14},
}


def soil_property_defaults(soil_type: str) -> dict:
    """Return K / Ss / Sy defaults for a soil type (falls back to Other)."""
    props = SOIL_PROPERTIES.get(soil_type) or SOIL_PROPERTIES["Other"]
    return {
        "conductivity": props["conductivity"],
        "storage": props["storage"],
        "yield": props["yield"],
    }


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


def default_stratigraphy_layers():
    """Default three-layer profile used when no stratigraphy exists in storage."""
    sand = soil_property_defaults("Sand")
    silt = soil_property_defaults("Silt")
    gravel = soil_property_defaults("Gravel")
    return [
        {
            "layer": "Sand",
            "thickness": 60.0,
            **sand,
            "selected": False,
            "recharge_target": True,
        },
        {
            "layer": "Silt",
            "thickness": 60.0,
            **silt,
            "selected": False,
            "recharge_target": False,
        },
        {
            "layer": "Gravel",
            "thickness": 60.0,
            **gravel,
            "selected": False,
            "recharge_target": False,
        },
    ]


def normalize_stratigraphy_list_from_raw(value):
    """Parse ``stratigraphy_data`` from storage/CSV into a clean list of layer dicts.

    - Accepts ``list[dict]`` (filters out non-dicts and empty dicts).
    - Accepts JSON or Python literal strings (common in key/value CSV exports).
    - Returns ``None`` if nothing usable remains (caller may fall back to defaults).
    """
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if hasattr(value, "item") and callable(getattr(value, "item")):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, str):
        s = value.strip()
        if not s or s.lower() == "nan":
            return None
        parsed = None
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(s)
                break
            except (ValueError, TypeError, SyntaxError, json.JSONDecodeError):
                continue
        if not isinstance(parsed, list):
            return None
        value = parsed
    if not isinstance(value, list):
        return None
    rows = []
    for item in value:
        if not isinstance(item, dict) or not item:
            continue
        if item.get("layer") is None and item.get("thickness") is None:
            continue
        rows.append(copy.deepcopy(item))
    return rows or None


def stratigraphy_store_payload_from_storage():
    """Build ``stratigraphy-data-store`` data from ``dash_storage`` (deep copy, normalized).

    Does not write to ``dash_storage``. Call after project CSV/JSON load so the in-memory
    ``dcc.Store`` matches the loaded file (the table otherwise keeps layout-time defaults
    until the Hydro tab sync runs, which can race with other callbacks).
    """
    stored_data = dash_storage.get_data("stratigraphy_data")
    coerced = normalize_stratigraphy_list_from_raw(stored_data)
    if coerced is not None:
        normalize_stratigraphy_recharge_target(coerced)
        return coerced
    rows = copy.deepcopy(default_stratigraphy_layers())
    normalize_stratigraphy_recharge_target(rows)
    return rows


def _get_stratigraphy_data():
    """Get stratigraphy data from dash_storage or return defaults."""
    stored_data = dash_storage.get_data("stratigraphy_data")
    coerced = normalize_stratigraphy_list_from_raw(stored_data)
    if coerced is not None:
        normalize_stratigraphy_recharge_target(coerced)
        dash_storage.set_data("stratigraphy_data", coerced)
        return coerced
    default_data = default_stratigraphy_layers()
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
        _build_geometry_and_view_cards(),
        *_build_hydro_tab_header(),
        _build_recharge_mound_outputs_card(),
    ]


def create_default_parameters_help_modal():
    """Help modal for (3.2) Default Parameters — each field and effect on results."""
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Default Parameters Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.P(
                        [
                            "These values are built-in rule and design defaults used by hydrologic "
                            "feasibility, engineering sizing, hard/soft constraints, cost, and the "
                            "multi-criteria Analysis / Decision scores. ",
                            html.Strong(
                                "Leave them unchanged unless you have site-specific data "
                                "that justifies an override."
                            ),
                        ],
                        className="text-muted mb-3",
                    ),
                    html.H6("Site / geometry defaults", className="fw-bold mb-2"),
                    html.Dl(
                        [
                            html.Dt(
                                "Aquitard hydraulic conductivity (ft/day)",
                                className="fw-bold",
                            ),
                            html.Dd(
                                "Maximum hydraulic conductivity used to classify a stratigraphy "
                                "layer as an aquitard. Layers at or below this hydraulic "
                                "conductivity are treated as confining units when inferring "
                                "confined versus unconfined geometry. "
                                "Changing it can flip aquifer type, which switches mounding "
                                "methods, dry-well versus injection logic, and which feasibility "
                                "rules apply.",
                                className="mb-3",
                            ),
                            html.Dt("Confined aquifer head (ft)", className="fw-bold"),
                            html.Dd(
                                "Optional confined-system head used for dry-well / injection "
                                "feasibility. Head must allow a downward gradient for injection. "
                                "If blank, the model uses an internal default (~80% of static "
                                "pressure in the recharge layer). Incorrect head can falsely "
                                "pass or fail confined dry-well options.",
                                className="mb-3",
                            ),
                            html.Dt("Maximum dry well depth (ft)", className="fw-bold"),
                            html.Dd(
                                "Practical construction limit for dry-well screen depth "
                                "(commonly ≤ ~120 ft). Caps how deep dry wells may be designed; "
                                "deeper values increase constructability risk and can change "
                                "well counts, cost, and dry-well feasibility.",
                                className="mb-3",
                            ),
                        ]
                    ),
                    html.H6("Rule defaults (overrides)", className="fw-bold mb-2"),
                    html.Dl(
                        [
                            html.Dt(
                                "Minimum vadose hydraulic conductivity threshold (ft/day)",
                                className="fw-bold",
                            ),
                            html.Dd(
                                "Minimum vadose-zone hydraulic conductivity treated as "
                                "suitable for infiltration. "
                                "Below this, spreading/surface recharge is less favorable, "
                                "topsoil may be flagged as limiting, and operational "
                                "groundwater-depth rules tighten — often reducing surface "
                                "recharge scores and required basin area.",
                                className="mb-3",
                            ),
                            html.Dt("Leakage radius (ft)", className="fw-bold"),
                            html.Dd(
                                "Reference length for confined-aquifer leakage significance "
                                "(leakage factor ÷ radius). Smaller radius makes leakage "
                                "score “higher” (worse); larger radius makes leakage look "
                                "less significant. Affects confined aquifer property scores "
                                "in Initial Feasibility and Analysis.",
                                className="mb-3",
                            ),
                            html.Dt(
                                "Confined aquifer depth thresholds — moderate / too deep (ft)",
                                className="fw-bold",
                            ),
                            html.Dd(
                                "Two depth-to-target thresholds for confined aquifers "
                                "(shallower number first). Depth at or below the moderate "
                                "threshold is Low Depth (best). Between the moderate and "
                                "too-deep thresholds is Moderate Deep (cost warning). Deeper "
                                "than the too-deep threshold is Too Deep (reject). Defaults "
                                "are 1500 ft and 3000 ft. Deeper classification lowers aquifer "
                                "property scores and can push options toward poor feasibility "
                                "or higher cost (deeper wells).",
                                className="mb-3",
                            ),
                            html.Dt("Minimum recharge efficiency (%)", className="fw-bold"),
                            html.Dd(
                                "Minimum fraction of annual source water that an option must "
                                "recharge to pass the Recharge Efficiency check. "
                                "Raising it makes that hard constraint stricter; lowering it "
                                "makes more sites/options pass and can improve rankings.",
                                className="mb-3",
                            ),
                            html.Dt(
                                "Maximum injection flow rate per well (ft³/day)",
                                className="fw-bold",
                            ),
                            html.Dd(
                                "Cap on injection (and related dry-well) flow rate per well. "
                                "Lower caps increase the number of wells needed for the same "
                                "volume → higher capital and operations and maintenance cost "
                                "and can fail if well count hits the maximum-wells limit.",
                                className="mb-3",
                            ),
                            html.Dt(
                                "Maximum number of injection wells",
                                className="fw-bold",
                            ),
                            html.Dd(
                                "Hard cap on injection / dry-well counts in sizing rules. "
                                "If required wells exceed this, capacity is truncated — "
                                "recharge volume and rechargability drop, which can fail "
                                "efficiency constraints and lower Analysis scores.",
                                className="mb-3",
                            ),
                            html.Dt(
                                "Maximum dry well transfer rate (gallons/minute)",
                                className="fw-bold",
                            ),
                            html.Dd(
                                "Upper limit on pumping/transfer into a dry well. Limits "
                                "how aggressively a dry-well option can accept source water "
                                "and thus affects sizing and feasibility.",
                                className="mb-3",
                            ),
                            html.Dt(
                                "Maximum dry well depth — rule cutoff versus screen depth (ft)",
                                className="fw-bold",
                            ),
                            html.Dd(
                                "Rule cutoff compared with operating groundwater depth when "
                                "sizing dry wells (distinct from the construction depth "
                                "limit above). Larger cutoff reduces available head difference "
                                "for dry-well capacity; too large can zero out dry wells.",
                                className="mb-3",
                            ),
                            html.Dt("Minimum groundwater depth (ft)", className="fw-bold"),
                            html.Dd(
                                "Shallowest allowed depth to water (below ground) for "
                                "operations and spreading-basin mound limits. "
                                "Larger values leave more unsaturated buffer but "
                                "can shrink usable managed aquifer recharge storage and make "
                                "shallow sites fail; "
                                "smaller values are more permissive but raise waterlogging risk.",
                                className="mb-3",
                            ),
                            html.Dt("Average moisture content (-)", className="fw-bold"),
                            html.Dd(
                                "Default moisture content (0–1) used when estimating vadose "
                                "pore velocity (infiltration rate ÷ moisture). Higher moisture "
                                "→ slower travel → longer residence time (better attenuation "
                                "scores); lower moisture → shorter residence → more water-"
                                "quality soft-constraint penalties.",
                                className="mb-3",
                            ),
                            html.Dt(
                                "Pathogenic bacteria / organic / trace organic / nutrients "
                                "residence time (days)",
                                className="fw-bold",
                            ),
                            html.Dd(
                                "Minimum subsurface residence times assumed for natural "
                                "attenuation of each contaminant class. Computed vadose "
                                "travel time is compared against these thresholds; shortfalls "
                                "flag issues (e.g., pathogens, organics, nutrients) and apply "
                                "soft-constraint penalties that lower environmental / "
                                "decision scores for surface-recharge options.",
                                className="mb-3",
                            ),
                        ]
                    ),
                    html.H6("How these affect final results", className="fw-bold mb-2"),
                    html.Ul(
                        [
                            html.Li(
                                [
                                    html.Strong("Initial Hydrologic Feasibility — "),
                                    "Traffic-light pass/warn/fail for each engineering option "
                                    "uses these thresholds (hydraulic conductivity, depth, "
                                    "leakage, rechargability, well caps, groundwater depth).",
                                ]
                            ),
                            html.Li(
                                [
                                    html.Strong("Sizing & cost — "),
                                    "Well counts, basin area, and dry-well capacity feed "
                                    "Engineering and Cost Analysis; tighter caps usually "
                                    "raise cost or reduce achievable recharge volume.",
                                ]
                            ),
                            html.Li(
                                [
                                    html.Strong("Hard / soft constraints — "),
                                    "Recharge efficiency, mound/groundwater limits, and vadose "
                                    "residence-time checks can pass or fail options before "
                                    "ranking.",
                                ]
                            ),
                            html.Li(
                                [
                                    html.Strong("Analysis & Decision — "),
                                    "Feasibility metrics, DSS Algorithm scores, sensitivity, "
                                    "and AI decision text all inherit these defaults. Overrides "
                                    "should be documented when they change rankings.",
                                ]
                            ),
                        ],
                        className="mb-0",
                    ),
                ]
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="default-parameters-help-close-btn",
                    color="secondary",
                    className="ms-auto",
                )
            ),
        ],
        id="default-parameters-help-modal",
        is_open=False,
        size="lg",
        scrollable=True,
        backdrop=True,
        keyboard=True,
    )


def create_default_hydrologic_parameters_tab_content():
    """Content for the (3.2) Default Parameters tab (same level as 3.1)."""
    notice = html.Div(
        (
            "These default parameters are used in the initial feasibility check and are "
            "considered generally reasonable. They do not need to be updated unless you "
            "have reliable field data."
        ),
        className="text-success fw-bold mb-3",
    )
    return [notice, _build_geometry_hydrogeologic_parameters_card()]


def create_hydro_tab_content():
    """Create the content for the Hydrogeology tab with sub-tabs."""
    return [
        html.Div(
            [
                dbc.Tabs(
                    [
                        dbc.Tab(
                            label="(3.1) Hydrogeologic Settings",
                            id=tab_nav_id("hydrogeologic-settings-tab"),
                            tab_id="hydrogeologic-settings-tab",
                            children=create_hydrogeologic_settings_content(),
                            label_style={
                                "color": "#ffffff",
                                "fontWeight": "bold",
                                "backgroundColor": "#0d6efd",
                                "border": "1px solid #0d6efd",
                            },
                            active_label_style={
                                "color": "#ffffff",
                                "backgroundColor": "#0b5ed7",
                                "border": "1px solid #0b5ed7",
                            },
                        ),
                        dbc.Tab(
                            label="(3.2) Default Parameters",
                            id=tab_nav_id("default-hydrologic-parameters-tab"),
                            tab_id="default-hydrologic-parameters-tab",
                            children=create_default_hydrologic_parameters_tab_content(),
                            label_style={
                                "color": "#ffffff",
                                "fontWeight": "bold",
                                "backgroundColor": "#5dade2",
                                "border": "1px solid #5dade2",
                            },
                            active_label_style={
                                "color": "#ffffff",
                                "backgroundColor": "#4a9fd1",
                                "border": "1px solid #4a9fd1",
                            },
                        ),
                    ],
                    id="hydrogeology-subtabs",
                    active_tab="hydrogeologic-settings-tab",
                    className="hydrogeology-top-tabs w-100",
                ),
                tab_tooltip(
                    "hydrogeologic-settings-tab",
                    "Aquifer type, stratigraphy, groundwater elevations, and initial feasibility",
                ),
                tab_tooltip(
                    "default-hydrologic-parameters-tab",
                    "Default geometry and hydrogeologic parameters (change only with field data)",
                ),
            ]
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
    muted = {"color": "#000"}
    muted_sub = {"color": "#000"}
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
                                    initial_feasibility_option_label(opt.name),
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


def create_initial_hydrologic_feasibility_help_modal():
    """Help modal for Initial Hydrologic Feasibility traffic-light check."""
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Initial Hydrologic Feasibility Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.P(
                        [
                            "This card provides a quick hydrologic screening of each "
                            "engineering option (Surface Recharge, Dry Well(s), "
                            "Injection Well(s)) "
                            "based on the Hydrogeology inputs you enter on this tab—stratigraphy, "
                            "groundwater levels, ground surface elevation, and related settings.",
                        ],
                        className="text-muted mb-3",
                    ),
                    html.H6("How to run the check", className="fw-bold mb-2"),
                    html.Ol(
                        [
                            html.Li(
                                "Complete (or review) Stratigraphy and Groundwater "
                                "Level inputs as needed."
                            ),
                            html.Li([
                                "Click ",
                                html.Strong("Check Initial Feasibility"),
                                ". MAR-Tool evaluates hard and soft hydrologic constraints "
                                "for each option and shows a traffic-light result.",
                            ]),
                            html.Li(
                                "If evaluation fails, a message explains that some input may be "
                                "incorrect or missing, along with the detailed error text."
                            ),
                        ],
                        className="mb-4 ps-3",
                    ),
                    html.H6("Traffic-light meanings", className="fw-bold mb-2"),
                    html.Ul(
                        [
                            html.Li([
                                html.Span(
                                    className="rounded-circle d-inline-block me-2",
                                    style={
                                        "width": "12px",
                                        "height": "12px",
                                        "backgroundColor": "#198754",
                                        "verticalAlign": "middle",
                                    },
                                ),
                                html.Strong("Green — Pass"),
                                ": all hard constraints pass; soft constraints are "
                                "acceptable or not applicable.",
                            ]),
                            html.Li([
                                html.Span(
                                    className="rounded-circle d-inline-block me-2",
                                    style={
                                        "width": "12px",
                                        "height": "12px",
                                        "backgroundColor": "#fd7e14",
                                        "verticalAlign": "middle",
                                    },
                                ),
                                html.Strong("Orange — Pass with Warnings"),
                                ": no hard failures, but at least one soft constraint "
                                "indicates added cost, warning, or mitigation.",
                            ]),
                            html.Li([
                                html.Span(
                                    className="rounded-circle d-inline-block me-2",
                                    style={
                                        "width": "12px",
                                        "height": "12px",
                                        "backgroundColor": "#dc3545",
                                        "verticalAlign": "middle",
                                    },
                                ),
                                html.Strong("Red — Fail"),
                                ": a hard constraint fails, or a soft constraint rejects "
                                "the option.",
                            ]),
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            "This is an ",
                            html.Strong("initial"),
                            " hydrologic screen. Full cost, environmental, legal, and "
                            "multi-criteria results are refined on the Engineering, "
                            "Analysis, and Decision tabs.",
                        ],
                        className="small text-muted mb-0",
                    ),
                ]
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="initial-feasibility-help-close-btn",
                    color="secondary",
                    className="ms-auto",
                )
            ),
        ],
        id="initial-feasibility-help-modal",
        is_open=False,
        size="lg",
        scrollable=True,
        backdrop=True,
        keyboard=True,
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
                                    html.Div(
                                        [
                                            html.Span(
                                                "Initial Hydrologic Feasability",
                                                className="fw-bold",
                                            ),
                                            html.Button(
                                                "?",
                                                id="initial-feasibility-help-btn",
                                                type="button",
                                                className="mar-help-btn",
                                                title="Help: initial hydrologic feasibility",
                                            ),
                                        ],
                                        className=(
                                            "d-flex align-items-center "
                                            "justify-content-between w-100"
                                        ),
                                    ),
                                    className="bg-primary text-white py-2",
                                ),
                                create_initial_hydrologic_feasibility_help_modal(),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    dcc.Loading(
                                                        id="initial-feasibility-loading",
                                                        type="circle",
                                                        color="#198754",
                                                        children=html.Div(
                                                            id="initial-feasibility-traffic-output",
                                                            children=_build_initial_feasibility_traffic_placeholder(),
                                                            style={"minHeight": "4.5rem"},
                                                        ),
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
                    className="table-cell-input-borderless"
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
                    className="table-cell-input-borderless"
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
                    className="table-cell-input-borderless"
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
        label="Stratigraphy", id=tab_nav_id("stratigraphy-tab"),
        tab_id="stratigraphy-tab",
        label_style={
            "color": "#ffffff", 
            "fontWeight": "bold",
            "backgroundColor": "#0d6efd",
            "border": "1px solid #0d6efd"
        },
        active_label_style={
            "color": "#ffffff", 
            "backgroundColor": "#0b5ed7",
            "border": "1px solid #0b5ed7"
        },
        children=[
            html.Div(
                [
                    html.H5("Stratigraphy Configuration", className="mb-3"),
                    html.P(
                        "Configure soil layers and their hydrogeological properties"
                        "Selecting a soil type auto-fills hydraulic conductivity, "
                        "specific storage, and specific yield (you can still edit them).",
                        className="mb-4",
                    ),
                    
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
                                    html.Th(
                                        "Select",
                                        className="fw-bold text-white",
                                        style={"width": "4%", "backgroundColor": "#2c3e50"},
                                    ),
                                    html.Th(
                                        "Soil Type",
                                        className="fw-bold text-white",
                                        style={"width": "16%", "backgroundColor": "#2c3e50"},
                                    ),
                                    html.Th(
                                        "Recharge Target Layer",
                                        className="fw-bold text-white text-center",
                                        style={"width": "12%", "backgroundColor": "#2c3e50"},
                                    ),
                                    html.Th(
                                        "Thickness (ft)",
                                        className="fw-bold text-white",
                                        style={"width": "13%", "backgroundColor": "#2c3e50"},
                                    ),
                                    html.Th(
                                        "Hydraulic Conductivity (ft/day)",
                                        className="fw-bold text-white",
                                        style={"width": "18%", "backgroundColor": "#2c3e50"},
                                    ),
                                    html.Th(
                                        "Specific Storage (1/ft)",
                                        className="fw-bold text-white",
                                        style={"width": "17%", "backgroundColor": "#2c3e50"},
                                    ),
                                    html.Th(
                                        "Specific Yield",
                                        className="fw-bold text-white",
                                        style={"width": "16%", "backgroundColor": "#2c3e50"},
                                    ),
                                ])
                            ]),
                            html.Tbody(id="stratigraphy-table-body")
                        ],
                        striped=True,
                        bordered=True,
                        hover=True,
                        responsive=True,
                        className="mb-1 excel-cell-table"
                    ),
                    build_table_legend(compact=True),
                ],
                id="stratigraphy-content"
            )
        ]
    )


def create_groundwater_level_help_modal():
    """Help modal for Groundwater Level Configuration."""
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Groundwater Level Configuration Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.P(
                        "Enter ground-surface and water-table data used to compute depth to "
                        "groundwater, available MAR storage, aquifer type (with stratigraphy), "
                        "and hydrologic constraints that feed Initial Feasibility and the "
                        "final decision analysis.",
                        className="text-muted mb-3",
                    ),
                    html.H6("Parameters", className="fw-bold mb-2"),
                    html.Dl(
                        [
                            html.Dt("Ground Surface Elevation (ft)", className="fw-bold"),
                            html.Dd(
                                [
                                    "Absolute elevation of the land surface at the site (same "
                                    "vertical datum as the monthly water-table elevations). "
                                    "Depth to groundwater each month is computed as ",
                                    html.Strong("ground surface − water-table elevation"),
                                    ".",
                                ],
                                className="mb-3",
                            ),
                            html.Dt("Maximum MAR Storage Depth (ft)", className="fw-bold"),
                            html.Dd(
                                "Maximum vertical thickness of the vadose / storage zone you "
                                "are willing (or allowed) to use for recharge above the water "
                                "table and other operational limits. Must not be negative. "
                                "Combined with minimum groundwater-depth rules and limiting "
                                "layers to set operational head / storage limits.",
                                className="mb-3",
                            ),
                            html.Dt("Monthly Elevation (ft) table", className="fw-bold"),
                            html.Dd(
                                "Water-table elevation for each calendar month. Enter one "
                                "value per month (amber cells). Seasonal highs and lows "
                                "control the shallowest and deepest water-table conditions "
                                "used in feasibility and design.",
                                className="mb-3",
                            ),
                        ]
                    ),
                    html.H6("How these affect decisions", className="fw-bold mb-2"),
                    html.Ul(
                        [
                            html.Li([
                                html.Strong("Depth to groundwater — "),
                                "Monthly depths drive vadose-zone thickness, unsaturated "
                                "travel path, and whether spreading (surface) recharge is "
                                "hydrologically realistic.",
                            ]),
                            html.Li([
                                html.Strong("Aquifer type (confined vs unconfined) — "),
                                "Inferred with stratigraphy from where the water table sits "
                                "relative to layers. That choice switches mounding methods "
                                "(e.g., Plan View contours) and which hard/soft constraints apply.",
                            ]),
                            html.Li([
                                html.Strong("Available MAR storage & operating depth — "),
                                "Maximum MAR Storage Depth and the shallowest water table "
                                "(highest elevation / least depth) limit how much vertical "
                                "storage and mound rise can be used without violating "
                                "constraints.",
                            ]),
                            html.Li([
                                html.Strong("Initial Hydrologic Feasibility — "),
                                "Hard fails (red) or warnings (orange) for each engineering "
                                "option often depend on insufficient unsaturated thickness, "
                                "storage limits, or water-table interference.",
                            ]),
                            html.Li([
                                html.Strong("Final decision scores — "),
                                "Physical feasibility, required footprint / well counts, "
                                "cost, and multi-criteria ranking on the Analysis and Decision "
                                "tabs all use these hydrologic inputs. Incorrect ground "
                                "surface or water-table values can falsely pass or fail an option.",
                            ]),
                        ],
                        className="mb-0",
                    ),
                ]
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="groundwater-level-help-close-btn",
                    color="secondary",
                    className="ms-auto",
                )
            ),
        ],
        id="groundwater-level-help-modal",
        is_open=False,
        size="lg",
        scrollable=True,
        backdrop=True,
        keyboard=True,
    )


def _build_groundwater_level_tab():
    """Build the groundwater level tab content."""
    return dbc.Tab(
        label="Groundwater Level", id=tab_nav_id("groundwater-level-tab"),
        tab_id="groundwater-level-tab",
        label_style={
            "color": "#ffffff", 
            "fontWeight": "bold",
            "backgroundColor": "#5dade2",
            "border": "1px solid #5dade2"
        },
        active_label_style={
            "color": "#ffffff", 
            "backgroundColor": "#4a9fd1",
            "border": "1px solid #4a9fd1"
        },
        children=[
            html.Div(
                [
                    html.Div(
                        [
                            html.H5(
                                "Groundwater Level Configuration",
                                className="mb-0",
                            ),
                            html.Button(
                                "?",
                                id="groundwater-level-help-btn",
                                type="button",
                                className="mar-help-btn",
                                title="Help: groundwater level configuration",
                            ),
                        ],
                        className="d-flex align-items-center gap-2 mb-3",
                    ),
                    create_groundwater_level_help_modal(),
                    # Input fields for elevation and storage depth
                    dbc.Row([
                        dbc.Col([
                            html.Label("Ground Surface Elevation (ft)", className="fw-bold", style={"fontSize": "12px"}),
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
                            html.Label("Maximum MAR Storage Depth (ft)", className="fw-bold", style={"fontSize": "12px"}),
                            dbc.Input(
                                id="max-mar-storage-depth",
                                type="number",
                                value=dash_storage.get_data("max_mar_storage_depth") or 20.0,
                                debounce=True,
                                step=0.1,
                                placeholder="Enter storage depth",
                                size="sm",
                            ),
                            dbc.FormFeedback(
                                id="max-mar-storage-depth-feedback",
                                type="invalid",
                            ),
                        ], width=6),
                        dbc.Col([
                            html.Label(
                                "Monthly Groundwater Elevation (ft)",
                                className="fw-bold mb-2",
                                style={"fontSize": "12px"},
                            ),
                            dbc.Checkbox(
                                id="constant-groundwater-level-check",
                                label="Use January value for all months",
                                value=False,
                                className="mb-2 collapse-toggle-check",
                            ),
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
                                className="mb-1 excel-cell-table"
                            ),
                            build_table_legend(compact=True),
                        ], width=6)
                    ], className="mb-3"),
                    # groundwater-data-store is defined in layout._build_root_layout (always mounted).
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


def create_horizontal_extension_help_modal():
    """Help modal for Horizontal Extent Configuration."""
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Horizontal Extent Configuration Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.P(
                        "Define the plan-view footprint of the MAR facility. These dimensions "
                        "set the horizontal extent used in Plan View, groundwater mounding "
                        "contours, and related hydrologic / engineering checks.",
                        className="text-muted mb-3",
                    ),
                    html.H6("Parameters", className="fw-bold mb-2"),
                    html.Dl(
                        [
                            html.Dt("Length (ft)", className="fw-bold"),
                            html.Dd(
                                "Long dimension of the MAR footprint (e.g., spreading area "
                                "or well-field extent) in feet.",
                                className="mb-3",
                            ),
                            html.Dt("Width (ft)", className="fw-bold"),
                            html.Dd(
                                "Short dimension of the MAR footprint in feet.",
                                className="mb-3",
                            ),
                            html.Dt("Rotation from North (degrees)", className="fw-bold"),
                            html.Dd(
                                "Clockwise or project-defined rotation of the rectangle from "
                                "north. 0° aligns the length axis with north; adjust to match "
                                "site orientation.",
                                className="mb-3",
                            ),
                        ]
                    ),
                    html.H6("Where it is used", className="fw-bold mb-2"),
                    html.Ul(
                        [
                            html.Li([
                                html.Strong("Plan View"),
                                " — draws the rectangular footprint and (optionally) mound "
                                "contours for confined or unconfined aquifers.",
                            ]),
                            html.Li(
                                "Feasibility and engineering calculations that need a "
                                "horizontal project area or aspect ratio."
                            ),
                        ],
                        className="mb-0",
                    ),
                ]
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="horizontal-extension-help-close-btn",
                    color="secondary",
                    className="ms-auto",
                )
            ),
        ],
        id="horizontal-extension-help-modal",
        is_open=False,
        size="lg",
        scrollable=True,
        backdrop=True,
        keyboard=True,
    )


def _build_horizontal_extension_panel():
    """Horizontal footprint inputs for recharge mound / plan-view analysis."""
    return html.Div(
        [
            html.Div(
                [
                    html.H5(
                        "Horizontal Extent",
                        className="mb-0",
                    ),
                    html.Button(
                        "?",
                        id="horizontal-extension-help-btn",
                        type="button",
                        className="mar-help-btn",
                        title="Help: horizontal extent configuration",
                    ),
                ],
                className="d-flex align-items-center gap-2 mb-3",
            ),
            create_horizontal_extension_help_modal(),
            html.P(
                "Define the plan-view footprint used for recharge mound contours",
                className="text-muted fs-6 mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Label("Length (ft)", className="fw-bold mb-2"),
                            dbc.Input(
                                id="extension-length",
                                type="number",
                                value=dash_storage.get_data("extension_length")
                                or 100.0,
                                debounce=True,
                                step=0.1,
                                placeholder="Enter length",
                            ),
                        ],
                        width=6,
                    ),
                    dbc.Col(
                        [
                            html.Label("Width (ft)", className="fw-bold mb-2"),
                            dbc.Input(
                                id="extension-width",
                                type="number",
                                value=dash_storage.get_data("extension_width")
                                or 50.0,
                                debounce=True,
                                step=0.1,
                                placeholder="Enter width",
                            ),
                        ],
                        width=6,
                    ),
                ],
                className="mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Label(
                                "Rotation from North (degrees)",
                                className="fw-bold mb-2",
                            ),
                            dbc.Input(
                                id="extension-rotation",
                                type="number",
                                value=dash_storage.get_data("extension_rotation")
                                or 0.0,
                                debounce=True,
                                step=1.0,
                                placeholder="Enter rotation angle",
                            ),
                        ],
                        width=6,
                    ),
                ],
                className="mb-3",
            ),
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
        id="horizontal-extension-content",
    )


def _build_plan_view_panel():
    """Plan-view plot and recharge-mound contour controls."""
    return html.Div(
        [
            html.H5("Plan View", className="mb-3"),
            html.P(
                "Plan-view layout of the MAR footprint and optional recharge-mound "
                "head contours.",
                className="text-muted fs-6 mb-3",
            ),
            dbc.Button(
                "Show Contour Lines",
                id="xy-view-show-contours-btn",
                color="primary",
                size="sm",
                className="mb-2",
                n_clicks=0,
            ),
            html.Div(
                id="xy-view-contour-message",
                className="mb-3",
            ),
            dcc.Graph(
                id="xy-view-plot",
                style={"height": "500px"},
            ),
            dbc.Tooltip(
                "Plan-view layout of the MAR geometry",
                target="xy-view-plot",
                placement="top",
            ),
        ],
        id="xy-view-content",
    )


def create_recharge_mound_outputs_help_modal():
    """Help modal for Recharge Mound Outputs card."""
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Recharge Mound Outputs Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.P(
                        "Additional outputs for evaluating the groundwater recharge mound "
                        "around the MAR facility. Set the horizontal footprint, then "
                        "review the plan view and optional head contours.",
                        className="text-muted mb-3",
                    ),
                    html.Dl(
                        [
                            html.Dt("Horizontal Extent", className="fw-bold"),
                            html.Dd(
                                "Length, width, and rotation of the recharge footprint "
                                "used in mounding and plan-view analysis.",
                                className="mb-3",
                            ),
                            html.Dt("Plan View", className="fw-bold"),
                            html.Dd(
                                "Map of the MAR footprint. Use Show Contour Lines to "
                                "display estimated recharge-mound head contours for the "
                                "current hydrogeologic inputs.",
                                className="mb-0",
                            ),
                        ]
                    ),
                ]
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="recharge-mound-outputs-help-close-btn",
                    color="secondary",
                    className="ms-auto",
                )
            ),
        ],
        id="recharge-mound-outputs-help-modal",
        is_open=False,
        size="lg",
        scrollable=True,
        backdrop=True,
        keyboard=True,
    )


def _build_recharge_mound_outputs_card():
    """Card below Initial Feasibility: horizontal extension + plan view."""
    view_mound = bool(dash_storage.get_data("view_recharge_mound_outputs"))
    return dbc.Card(
        [
            dbc.CardHeader(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Span(
                                    "Recharge Mound Outputs",
                                    className="fw-bold me-3",
                                ),
                                dbc.Checkbox(
                                    id="view-recharge-mound-outputs-check",
                                    label=html.Span(
                                        "Additional information, check if you care!",
                                        className="fw-semibold",
                                    ),
                                    value=view_mound,
                                    className="mb-0 text-white collapse-toggle-check",
                                    input_class_name="me-1",
                                    label_class_name="text-white mb-0",
                                ),
                            ],
                            className="d-flex align-items-center flex-wrap gap-2",
                        ),
                        html.Button(
                            "?",
                            id="recharge-mound-outputs-help-btn",
                            type="button",
                            className="mar-help-btn",
                            title="Help: recharge mound outputs",
                        ),
                    ],
                    className=(
                        "d-flex align-items-center "
                        "justify-content-between w-100"
                    ),
                ),
                className="bg-primary text-white py-2",
            ),
            create_recharge_mound_outputs_help_modal(),
            dbc.Collapse(
                dbc.CardBody(
                    [
                        html.P(
                            "Additional outputs for the recharge mound: set the horizontal "
                            "footprint and review the plan-view contours.",
                            className="text-muted fs-6 mb-3",
                        ),
                        dbc.Row(
                            [
                                dbc.Col(_build_horizontal_extension_panel(), md=5),
                                dbc.Col(_build_plan_view_panel(), md=7),
                            ],
                            className="g-3",
                        ),
                    ],
                    className="p-3",
                ),
                id="recharge-mound-outputs-collapse",
                is_open=view_mound,
            ),
        ],
        className="mb-3",
    )


def _build_geometry_tabs():
    """Build the geometry tabs container."""
    return html.Div(
        [
            dbc.Tabs(
                id="geometry-tabs",
                children=[
                    _build_stratigraphy_tab(),
                    _build_groundwater_level_tab(),
                ],
                active_tab="stratigraphy-tab",
            ),
            tab_tooltip(
                "stratigraphy-tab",
                "Configure soil layers and hydrogeological properties",
            ),
            tab_tooltip(
                "groundwater-level-tab",
                "Monthly groundwater elevation data and seasonal variation",
            ),
        ]
    )


def _build_geometry_card():
    """Build the Geometry card."""
    return dbc.Card(
        [
            dbc.CardHeader(
                "Stratigraphy and Groundwater Levels",
                className="fw-bold bg-primary text-white",
            ),
            dbc.CardBody(
                [
                    dcc.Store(
                        id="aq-type-inferred-store",
                        data="unconfined",
                    ),
                    _build_geometry_tabs(),
                ]
            ),
        ],
        className="mb-4",
    )


def _build_view_card():
    """Build the View card with stratigraphy and storage tabs."""
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
                    id=tab_nav_id("stratigraphy-cross-section"),
                                tab_id="stratigraphy-cross-section",
                                children=[
                                    html.Div(
                                        [
                                            html.H6("Stratigraphy Cross Section", className="mb-3"),
                                            html.P("Visual representation of subsurface stratigraphy layers", className="mb-3"),
                                            
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
                                    "backgroundColor": "#0d6efd",
                                    "border": "1px solid #0d6efd"
                                },
                                active_label_style={
                                    "color": "#ffffff", 
                                    "backgroundColor": "#0b5ed7",
                                    "border": "1px solid #0b5ed7"
                                },
                            ),
                            dbc.Tab(
                                label="Available MAR Storage",
                    id=tab_nav_id("available-mar-storage"),
                                tab_id="available-mar-storage",
                                children=[
                                    html.Div(
                                        [
                                            html.H6("Available MAR Storage", className="mb-3"),
                                            html.P("Analysis of available storage capacity for MAR operations", className="mb-3"),
                                            
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
                                    "backgroundColor": "#5dade2",
                                    "border": "1px solid #5dade2"
                                },
                                active_label_style={
                                    "color": "#ffffff", 
                                    "backgroundColor": "#4a9fd1",
                                    "border": "1px solid #4a9fd1"
                                },
                            ),
                        ],
                        id="view-tabs",
                        active_tab="stratigraphy-cross-section",
                    ),
                    tab_tooltip(
                        "stratigraphy-cross-section",
                        "Cross-section visualization of subsurface stratigraphy",
                    ),
                    tab_tooltip(
                        "available-mar-storage",
                        "Available MAR storage capacity based on stratigraphy and head limits",
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
                ]
            ),
        ],
        className="mb-4",
    )


DEFAULT_MAX_DRY_WELL_DEPTH_FT = 120.0

_FIELD_NOTE_STYLE = {"fontSize": "0.72rem", "lineHeight": 1.25, "color": "#000"}


def _input_field_note(text: str):
    """Single-line helper text under a compact numeric input."""
    return html.Small(
        text,
        className="d-block",
        style=_FIELD_NOTE_STYLE,
    )


# Matches ``mar_dss.rules.defaults`` keys (lines 3–26); editable overrides in ``rule_defaults_overrides``.
# Each row: key, label, step, note (shown under the input).
RULE_DEFAULT_SCALAR_ROWS = [
    (
        "k_min_vadose_threshold",
        "Minimum vadose hydraulic conductivity threshold (ft/day)",
        0.01,
        "Minimum hydraulic conductivity treated as vadose-dominated for classification rules.",
    ),
    (
        "leakage_radius",
        "Leakage radius (ft)",
        1,
        "Horizontal extent (ft) used in leakage-related rule checks.",
    ),
    (
        "maximum_rechargability",
        "Minimum recharge efficiency (%)",
        1,
        "Lowest acceptable percent of annual source water that an option must recharge to pass.",
    ),
    (
        "max_injection_Q_per_well",
        "Maximum injection flow rate per well (ft³/day)",
        1,
        "Maximum injection flow rate assumed per well for feasibility and routing rules.",
    ),
    (
        "max_number_of_injection_wells",
        "Maximum number of injection wells",
        1,
        "Cap on the count of injection wells used in scenario logic.",
    ),
    (
        "max_dry_well_transfer_rate_gpm",
        "Maximum dry well transfer rate (gallons/minute)",
        1,
        "Upper limit on pumping or transfer into the dry well (gallons per minute).",
    ),
    (
        "max_drywell_depth_ft",
        "Maximum dry well depth — rule cutoff versus screen depth (ft)",
        1,
        "Rule cutoff comparing screen depth to defaults—not the construction depth limit above.",
    ),
    (
        "d_gw_min",
        "Minimum groundwater depth (ft)",
        0.1,
        "Shallowest allowed depth to water table (below ground). Used for operational "
        "groundwater depth and spreading-basin mound limits.",
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
                        className="mb-0 small",
                        htmlFor=inp_id,
                        style={"fontSize": "0.72rem", "lineHeight": 1.2, "color": "#000"},
                    ),
                    dbc.Input(
                        id=inp_id,
                        type="number",
                        step=step,
                        debounce=True,
                        value=get_default(key),
                        size="sm",
                        className="mb-1",
                        style={"color": "#000"},
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
                    "Confined aquifer — moderate-depth threshold (ft)",
                    className="mb-0 small",
                    htmlFor=lo_id,
                    style={"fontSize": "0.72rem", "lineHeight": 1.2, "color": "#000"},
                ),
                dbc.Input(
                    id=lo_id,
                    type="number",
                    step=1,
                    debounce=True,
                    value=float(_eda[0]),
                    size="sm",
                    className="mb-1",
                    style={"color": "#000"},
                ),
                _input_field_note(
                    "Depths deeper than this (up to the too-deep threshold) are Moderate Deep. "
                    "Default 1500 ft. Must be less than the too-deep threshold."
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
                    "Confined aquifer — too-deep threshold (ft)",
                    className="mb-0 small",
                    htmlFor=hi_id,
                    style={"fontSize": "0.72rem", "lineHeight": 1.2, "color": "#000"},
                ),
                dbc.Input(
                    id=hi_id,
                    type="number",
                    step=1,
                    debounce=True,
                    value=float(_eda[1]),
                    size="sm",
                    className="mb-1",
                    style={"color": "#000"},
                ),
                _input_field_note(
                    "Depths deeper than this are Too Deep (rejected for confined options). "
                    "Default 3000 ft. Must be greater than the moderate-depth threshold."
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
            className="small mb-2",
            style={"fontSize": "0.75rem", "color": "#000"},
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
                html.Div(
                    [
                        html.Span("Default parameters", className="fw-bold"),
                        html.Button(
                            "?",
                            id="default-parameters-help-btn",
                            type="button",
                            className="mar-help-btn",
                            title="Help: default parameters",
                        ),
                    ],
                    className=(
                        "d-flex align-items-center "
                        "justify-content-between w-100"
                    ),
                ),
                className="bg-primary text-white py-2 px-3 small",
            ),
            create_default_parameters_help_modal(),
            dbc.CardBody(
                [
                    dbc.Button(
                        "Reset to default values",
                        id="reset-default-parameters-btn",
                        color="secondary",
                        size="sm",
                        outline=True,
                        className="mb-3",
                        n_clicks=0,
                        title=(
                            "Restore all Default Parameters on this page to their "
                            "built-in original values"
                        ),
                    ),
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Label(
                                        "Aquitard hydraulic conductivity (ft/day)",
                                        className="mb-0 small",
                                        htmlFor="aquitard-conductivity-input",
                                        style={"fontSize": "0.72rem", "color": "#000"},
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
                                        style={"color": "#000"},
                                    ),
                                    _input_field_note(
                                        "Layers with hydraulic conductivity at or below this value are treated "
                                        "as aquitards when inferring confined versus unconfined aquifer geometry."
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
                                        className="mb-0 small",
                                        htmlFor="confined-aquifer-head-input",
                                        style={"fontSize": "0.72rem", "color": "#000"},
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
                                        style={"color": "#000"},
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
                                        className="mb-0 small",
                                        htmlFor="max-dry-well-depth-input",
                                        style={"fontSize": "0.72rem", "color": "#000"},
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
                                        style={"color": "#000"},
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
        className="mb-4 default-parameters-card",
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