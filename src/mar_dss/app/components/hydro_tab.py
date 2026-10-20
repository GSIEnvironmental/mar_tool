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

# Display labels for Initial Hydrogeologic Feasibility (internal option.name unchanged)
INITIAL_FEASIBILITY_OPTION_LABELS = {
    "Surface Recharge": "Surface Recharge (e.g., Infiltration Basin)",
    "Dry Well": "Dry Well(s)",
    "Injection Well": "Injection Well(s)",
}


def initial_feasibility_option_label(option_name: str) -> str:
    """User-facing name for an option in Initial Hydrogeologic Feasibility."""
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


def _help_eq(text):
    """Inline equation / formula styling for help text."""
    return html.Code(text, className="d-inline-block small px-1 text-dark")


def create_default_parameters_help_modal():
    """Help modal for (3.2) Default Parameters — paper-style parameter catalog."""
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Default Parameters Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.H6("1. Purpose and scope", className="fw-bold mb-2"),
                    html.P(
                        [
                            "Default Parameters supply the numerical thresholds, caps, and "
                            "reference lengths used inside the hydrogeologic knowledge "
                            "graph and the constraint checks. They do not replace "
                            "stratigraphy or groundwater data; they calibrate how those "
                            "data are interpreted. ",
                            html.Strong(
                                "Leave built-in values unchanged unless site-specific "
                                "measurements or regulatory guidance justify an override."
                            ),
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            "How those parameters enter spreading-pond sizing, well counts, "
                            "hard and soft constraints, and the traffic-light aggregation "
                            "is documented in the ",
                            html.Strong("Initial Hydrogeologic Feasibility Help"),
                            " on the Hydrogeologic Settings tab (Stages 2, 2b, 3, 4, and 5). "
                            "The present note catalogs each Default Parameter and states "
                            "which symbol or step in that procedure it controls, without "
                            "repeating the full calculation narrative.",
                        ],
                        className="mb-3",
                    ),
                    html.H6(
                        "2. Relation to Initial Hydrogeologic Feasibility",
                        className="fw-bold mb-2",
                    ),
                    html.P(
                        [
                            "When ",
                            html.Strong("Check Initial Feasibility"),
                            " is run, the same defaults participate in Stage 2 of the "
                            "feasibility help (knowledge-graph evaluation), Stage 2b "
                            "(spreading-pond and well sizing), and Stages 3–5 (hard "
                            "constraints, soft responses, and traffic lights). Changing a "
                            "default therefore changes intermediate quantities such as ",
                            _help_eq("η"),
                            ", ",
                            _help_eq("N"),
                            ", or ",
                            _help_eq("t_R"),
                            ", and may change pass, warning, or fail outcomes. The "
                            "definitions of hard versus soft constraints and of the green / "
                            "orange / red rules are not restated here; see that help.",
                        ],
                        className="mb-4",
                    ),
                    html.H6("3. Site and geometry defaults", className="fw-bold mb-2"),
                    html.P(
                        [
                            html.Strong("Aquitard hydraulic conductivity "),
                            _help_eq("K_aquitard"),
                            " (ft/day). ",
                            "A stratigraphy layer is treated as an aquitard when ",
                            _help_eq("K_i ≤ K_aquitard"),
                            ". That classification drives the confined versus unconfined "
                            "label used throughout the feasibility procedure (Stage 1). "
                            "Raising the cutoff makes more layers look like aquitards and "
                            "can flip the site toward confined rules; lowering it does the "
                            "opposite.",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            html.Strong("Confined aquifer head "),
                            "(ft). ",
                            "Optional operating head for confined dry-well and injection "
                            "feasibility. Injection requires a downward gradient into the "
                            "target unit. If the field is blank, the model approximates "
                            "head as about 80 percent of the static pressure head in the "
                            "recharge layer. An unrealistic value can collapse confined "
                            "well capacity in Stage 2b and thereby reduce ",
                            _help_eq("η"),
                            " below ",
                            _help_eq("η_min"),
                            " in the hard Recharge Efficiency check (feasibility help, "
                            "Stage 3).",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            html.Strong("Maximum dry well depth — construction limit "),
                            "(ft). ",
                            "Practical limit on how deep a dry-well screen may be built "
                            "(values much above about 120 feet are uncommon). It can "
                            "truncate dry-well capacity in sizing and cost. It is distinct "
                            "from the rule-depth cutoff ",
                            _help_eq("d_dw"),
                            " used in the unconfined dry-well head-difference formula in "
                            "feasibility help Stage 2b.",
                        ],
                        className="mb-4",
                    ),
                    html.H6("4. Rule defaults (overrides)", className="fw-bold mb-2"),
                    html.P(
                        [
                            html.Strong("Minimum vadose hydraulic conductivity "),
                            _help_eq("K_min"),
                            " (ft/day). ",
                            "Infiltration is treated as suitable when ",
                            _help_eq("K_vadose,min ≥ K_min"),
                            ", and spreading requires ",
                            _help_eq("K_target ≥ K_min"),
                            " (feasibility help, Stage 2 and Stage 2b). If the limiting "
                            "top layer is below ",
                            _help_eq("K_min"),
                            ", topsoil is treated as limiting and the operational "
                            "groundwater-depth floor is raised to that layer’s bottom. "
                            "Soft constraints affected include Vadose zone infiltration "
                            "and Surface recharge suitability; hard Recharge Efficiency "
                            "fails if spreading area collapses to zero.",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            html.Strong("Leakage radius "),
                            _help_eq("R_leak"),
                            " (ft). ",
                            "Enters the confined leakage ratio ",
                            _help_eq("S = B / R_leak"),
                            " with ",
                            _help_eq("B = √(T / L)"),
                            " as defined in feasibility help Stage 2. A smaller radius "
                            "increases ",
                            _help_eq("S"),
                            "’s severity classification and worsens the soft Confined "
                            "leakage significance score. There is no hard constraint that "
                            "reads ",
                            _help_eq("R_leak"),
                            " directly.",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            html.Strong("Confined aquifer depth thresholds "),
                            _help_eq("D_mod"),
                            " and ",
                            _help_eq("D_too"),
                            " (ft). ",
                            "With depth to target ",
                            _help_eq("D"),
                            " from feasibility help Stage 2, Low Depth corresponds to ",
                            _help_eq("D ≤ D_mod"),
                            ", Moderate Deep to ",
                            _help_eq("D_mod < D ≤ D_too"),
                            ", and Too Deep to ",
                            _help_eq("D > D_too"),
                            " (defaults 1500 and 3000 feet). These classes feed the soft "
                            "Confined aquifer depth Suitability score only.",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            html.Strong("Minimum recharge efficiency "),
                            _help_eq("η_min"),
                            " (%). ",
                            "Hard Recharge Efficiency requires ",
                            _help_eq("η ≥ η_min"),
                            " for the option under test, where ",
                            _help_eq("η"),
                            " is formed from sized recharge volume and source volume "
                            "(feasibility help Stages 2, 2b, and 3). Soft Surface "
                            "recharge suitability uses the same minimum for the surface "
                            "pathway. Raising ",
                            _help_eq("η_min"),
                            " makes both checks stricter.",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            html.Strong("Maximum injection flow rate per well "),
                            _help_eq("Q_max"),
                            " (ft³/day). ",
                            "Caps the Theis-derived hydrologic rate in Stage 2b: ",
                            _help_eq("Q_well = minimum of Q_hydro and Q_max"),
                            ". A lower cap increases the required well count or forces "
                            "truncation against ",
                            _help_eq("N_max"),
                            ", which can reduce ",
                            _help_eq("η"),
                            ".",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            html.Strong("Maximum number of injection wells "),
                            _help_eq("N_max"),
                            ". ",
                            "Appears in ",
                            _help_eq(
                                "N = minimum of ceil(V_day / Q_well) and N_max"
                            ),
                            " for both injection and dry-well sizing (feasibility help "
                            "Stage 2b). Truncation below the hydrologic need reduces "
                            "annual well-based recharge and can fail hard Recharge "
                            "Efficiency.",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            html.Strong("Maximum dry well transfer rate "),
                            "(gallons/minute). ",
                            "Upper bound on pumping or transfer into a dry well during "
                            "sizing and cost. If it limits annual dry-well volume enough, ",
                            _help_eq("η"),
                            " for Dry Well(s) may fall below ",
                            _help_eq("η_min"),
                            ".",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            html.Strong("Maximum dry well depth — rule cutoff "),
                            _help_eq("d_dw"),
                            " (ft). ",
                            "Used in the unconfined dry-well head difference ",
                            _help_eq(
                                "Δh = d_gw − max(d_gw,op, d_dw)"
                            ),
                            " (feasibility help Stage 2b). If ",
                            _help_eq("Δh ≤ 0"),
                            ", dry-well count and rate are set to zero. This is not the "
                            "construction depth limit listed in Section 3.",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            html.Strong("Minimum groundwater depth "),
                            _help_eq("d_gw,min"),
                            " (ft). ",
                            "Shallowest allowed depth to water for operations and "
                            "spreading-basin mound limits. Combined with Maximum MAR "
                            "Storage Depth, the stricter value becomes the operational "
                            "floor ",
                            _help_eq("d_gw,op"),
                            " used in ",
                            _help_eq("Δh_allow"),
                            " for spreading and in well head differences (feasibility "
                            "help Stage 2b). A larger buffer is safer against "
                            "waterlogging but can shrink usable MAR storage.",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            html.Strong("Average moisture content "),
                            _help_eq("θ"),
                            " (−). ",
                            "Used only when Water Quality Q1 indicates source "
                            "contaminants are present. Pore velocity and residence time "
                            "follow ",
                            _help_eq("v = i / θ"),
                            " and ",
                            _help_eq("t_R = b_unsat / v"),
                            " (feasibility help Stage 2). Higher ",
                            _help_eq("θ"),
                            " lengthens ",
                            _help_eq("t_R"),
                            " and makes it easier to clear the contaminant-class "
                            "thresholds below. Not applied to Injection Well options or "
                            "confined sites.",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            html.Strong("Residence-time thresholds "),
                            _help_eq("t*_c"),
                            " (days). ",
                            "Separate minima for pathogenic bacteria (default 30 days), "
                            "organic matter (7 days), trace organic matter (30 days), and "
                            "nutrients (30 days). A class is flagged when ",
                            _help_eq("t_R ≤ t*_c"),
                            ". All four thresholds feed only the soft Vadose zone "
                            "residence time constraint (feasibility help Stages 2 and 4); "
                            "they are not hard gates unless that soft metric is separately "
                            "configured as hard.",
                        ],
                        className="mb-4",
                    ),
                    html.H6("5. Practical guidance", className="fw-bold mb-2"),
                    html.Ul(
                        [
                            html.Li(
                                [
                                    "For the algebraic roles of ",
                                    _help_eq("A"),
                                    ", ",
                                    _help_eq("i"),
                                    ", ",
                                    _help_eq("Q_well"),
                                    ", ",
                                    _help_eq("N"),
                                    ", and the mound iteration, open ",
                                    html.Strong(
                                        "Initial Hydrogeologic Feasibility Help"
                                    ),
                                    ", Stage 2b.",
                                ]
                            ),
                            html.Li(
                                "After changing defaults, re-run Check Initial Feasibility "
                                "so the knowledge graph and traffic lights refresh."
                            ),
                            html.Li(
                                "Document overrides when they change rankings on the "
                                "Analysis or Decision tabs, because the same defaults "
                                "propagate into full DSS scoring."
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
        size="xl",
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
        dbc.Row(
            cols,
            className="g-2 g-md-3 align-items-start justify-content-lg-between",
        ),
        className="initial-feasibility-traffic initial-feasibility-traffic--pending mt-1",
    )


def create_initial_hydrologic_feasibility_help_modal():
    """Help modal for Initial Hydrogeologic Feasibility traffic-light check."""
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Initial Hydrogeologic Feasibility Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.H6("1. Purpose and scope", className="fw-bold mb-2"),
                    html.P(
                        "Initial Hydrogeologic Feasibility is a screening calculation that "
                        "asks, for each candidate managed aquifer recharge (MAR) option, "
                        "whether present site hydrogeology and default rule parameters are "
                        "compatible with that option. The options evaluated are Surface "
                        "Recharge (for example, an infiltration basin), Dry Well(s), and "
                        "Injection Well(s). The screen uses stratigraphy, groundwater "
                        "levels, ground-surface elevation, aquitard classification, water-"
                        "quality answers where relevant, and the Default Parameters "
                        "thresholds. It is intentionally limited to hydrogeologic hard and "
                        "soft constraints; full cost, environmental, legal, and multi-"
                        "criteria ranking are completed on later tabs.",
                        className="mb-3",
                    ),
                    html.H6("2. How to run the check", className="fw-bold mb-2"),
                    html.Ol(
                        [
                            html.Li(
                                "Enter or review Stratigraphy and Groundwater Level inputs, "
                                "and confirm Default Parameters if site-specific overrides "
                                "are needed."
                            ),
                            html.Li(
                                [
                                    "Click ",
                                    html.Strong("Check Initial Feasibility"),
                                    ". The tool rebuilds intermediate hydrogeologic "
                                    "quantities, evaluates hard and soft constraints for "
                                    "each option, and maps the results to a traffic light.",
                                ]
                            ),
                            html.Li(
                                "If required inputs are missing or inconsistent, an error "
                                "message is shown instead of traffic lights, together with "
                                "diagnostic detail."
                            ),
                        ],
                        className="mb-4 ps-3",
                    ),
                    html.H6(
                        "3. Calculation procedure (step by step)",
                        className="fw-bold mb-2",
                    ),
                    html.P(
                        "The calculation proceeds in five stages. Stages 1–3 assemble "
                        "shared site quantities; Stage 4 evaluates constraints option by "
                        "option; Stage 5 aggregates those outcomes into a single traffic-"
                        "light color.",
                        className="mb-3",
                    ),
                    html.H6(
                        "Stage 1 — Assemble site inputs",
                        className="fw-semibold mb-2",
                    ),
                    html.P(
                        [
                            "Let the stratigraphy consist of layers indexed by ",
                            _help_eq("i = 1, …, n"),
                            ", each with thickness ",
                            _help_eq("b_i"),
                            " (ft), hydraulic conductivity ",
                            _help_eq("K_i"),
                            " (ft/day), and storage parameter ",
                            _help_eq("S_i"),
                            " (specific yield or specific storage, as entered). One layer "
                            "is designated the target recharge layer. Ground-surface "
                            "elevation ",
                            _help_eq("z_gs"),
                            " and monthly groundwater elevations define depths to water. "
                            "Average groundwater depth below ground is denoted ",
                            _help_eq("d_gw"),
                            ". An aquitard conductivity cutoff ",
                            _help_eq("K_aquitard"),
                            " classifies layer ",
                            _help_eq("i"),
                            " as an aquitard when ",
                            _help_eq("K_i ≤ K_aquitard"),
                            ". From that classification the site is labeled confined or "
                            "unconfined, which selects which subsequent equations and "
                            "constraints apply.",
                        ],
                        className="mb-3",
                    ),
                    html.H6(
                        "Stage 2 — Evaluate the hydrogeologic knowledge graph",
                        className="fw-semibold mb-2",
                    ),
                    html.P(
                        [
                            "Site inputs are passed through a directed knowledge graph of "
                            "hydrogeologic rules. Representative derived quantities include "
                            "the following.",
                        ],
                        className="mb-2",
                    ),
                    html.P(
                        [
                            html.Strong("Infiltration suitability. "),
                            "Let ",
                            _help_eq("K_vadose,min"),
                            " be the minimum hydraulic conductivity in the unsaturated "
                            "zone and ",
                            _help_eq("K_min"),
                            " the Default Parameters threshold. Infiltration is treated as "
                            "suitable when ",
                            _help_eq("K_vadose,min ≥ K_min"),
                            ". Spreading area is computed only if the target layer also "
                            "satisfies ",
                            _help_eq("K_target ≥ K_min"),
                            "; otherwise the spreading area is set to zero.",
                        ],
                        className="mb-2",
                    ),
                    html.P(
                        [
                            html.Strong("Recharge efficiency. "),
                            "For each option, annual recharged volume ",
                            _help_eq("V_r"),
                            " and annual source volume ",
                            _help_eq("V_s"),
                            " define the rechargeable percentage ",
                            _help_eq("η = 100 · V_r / V_s"),
                            ". Injection and dry-well volumes depend on per-well rate "
                            "limits and well-count caps from Default Parameters; surface "
                            "volume depends on spreading area and infiltration rate.",
                        ],
                        className="mb-2",
                    ),
                    html.P(
                        [
                            html.Strong("Confined leakage significance. "),
                            "When the site is confined, transmissivity of the target unit "
                            "is ",
                            _help_eq("T = K_target · b_target"),
                            " and leakance of an adjacent confining bed is ",
                            _help_eq("L = K_confining / b_confining"),
                            ". The leakage factor is ",
                            _help_eq("B = √(T / L)"),
                            ". Relative to the leakage radius ",
                            _help_eq("R_leak"),
                            ", significance is ",
                            _help_eq("S = B / R_leak"),
                            ". Classification uses ",
                            _help_eq("S > 20"),
                            " for low leakage, ",
                            _help_eq("1 < S ≤ 20"),
                            " for medium leakage, and ",
                            _help_eq("S ≤ 1"),
                            " for high leakage.",
                        ],
                        className="mb-2",
                    ),
                    html.P(
                        [
                            html.Strong("Confined depth class. "),
                            "Depth to the target unit is ",
                            _help_eq("D = Σ b_i"),
                            " over layers above the target. With moderate and too-deep "
                            "thresholds ",
                            _help_eq("D_mod"),
                            " and ",
                            _help_eq("D_too"),
                            ", the class is Low Depth if ",
                            _help_eq("D ≤ D_mod"),
                            ", Moderate Deep if ",
                            _help_eq("D_mod < D ≤ D_too"),
                            ", and Too Deep if ",
                            _help_eq("D > D_too"),
                            ".",
                        ],
                        className="mb-2",
                    ),
                    html.P(
                        [
                            html.Strong("Vadose residence time. "),
                            "If Water Quality Q1 indicates source contaminants are "
                            "present, pore velocity is ",
                            _help_eq("v = i / θ"),
                            ", where ",
                            _help_eq("i"),
                            " is design infiltration rate and ",
                            _help_eq("θ"),
                            " is average moisture content. Residence time is ",
                            _help_eq("t_R = b_unsat / v"),
                            ", with ",
                            _help_eq("b_unsat"),
                            " the unsaturated thickness. Each contaminant class with "
                            "threshold ",
                            _help_eq("t*_c"),
                            " is flagged when ",
                            _help_eq("t_R ≤ t*_c"),
                            ". This pathway is not applied to Injection Well options or "
                            "to confined sites.",
                        ],
                        className="mb-3",
                    ),
                    html.H6(
                        "Stage 2b — Spreading-pond size and well-count calculations",
                        className="fw-semibold mb-2",
                    ),
                    html.P(
                        "Before recharge efficiency can be checked, the knowledge graph "
                        "sizes each recharge pathway. Surface Recharge uses a spreading "
                        "pond (or basin) footprint and an infiltration rate. Injection "
                        "wells and dry wells use a per-well flow rate and a well count. "
                        "The paragraphs below describe those calculations in the order "
                        "they are performed.",
                        className="mb-3",
                    ),
                    html.P(
                        [
                            html.Strong("Spreading pond (Surface Recharge). "),
                            "Let ",
                            _help_eq("V_month,max"),
                            " be the largest monthly source-water volume and define a "
                            "representative daily volume ",
                            _help_eq("V_day = V_month,max / 30.25"),
                            ". Let ",
                            _help_eq("K_vadose,min"),
                            " be the minimum vadose hydraulic conductivity and ",
                            _help_eq("A_land"),
                            " the maximum available land area. If the target recharge "
                            "layer hydraulic conductivity is below the Default Parameters "
                            "threshold ",
                            _help_eq("K_min"),
                            ", the spreading area is set to zero and Surface Recharge "
                            "cannot accept water. Otherwise an initial footprint is",
                        ],
                        className="mb-2",
                    ),
                    html.P(
                        [
                            _help_eq(
                                "A = minimum of (V_day / K_vadose,min) and A_land"
                            ),
                            ".",
                        ],
                        className="mb-2",
                    ),
                    html.P(
                        [
                            "Allowable mound height is the difference between average "
                            "groundwater depth and the operational groundwater-depth "
                            "floor, ",
                            _help_eq("Δh_allow = d_gw − d_gw,op"),
                            ". If that allowable height is missing or not positive, the "
                            "basin is sized by vadose hydraulic conductivity alone: the "
                            "infiltration rate is taken as ",
                            _help_eq("i = K_vadose,min"),
                            " and no mound iteration is needed.",
                        ],
                        className="mb-2",
                    ),
                    html.P(
                        [
                            "When ",
                            _help_eq("Δh_allow > 0"),
                            ", saturated-zone properties are formed from the layers below "
                            "the water table. Thickness-weighted means give aquifer "
                            "hydraulic conductivity ",
                            _help_eq("K̄"),
                            " and specific yield ",
                            _help_eq("S̄_y"),
                            ", together with saturated thickness ",
                            _help_eq("b_sat"),
                            ". The infiltration rate is initialized near the vadose limit, ",
                            _help_eq("i ← 0.99 · K_vadose,min"),
                            ". Then an iterative mound check is applied for up to 50 "
                            "iterations:",
                        ],
                        className="mb-2",
                    ),
                    html.Ol(
                        [
                            html.Li(
                                [
                                    "At the basin center and a long simulation time "
                                    "(near steady state, ",
                                    _help_eq("t = 50"),
                                    " days in the current implementation), compute the "
                                    "predicted mound rise ",
                                    _help_eq("Δh_pred"),
                                    " from the Hantush-type recharge-mound function using "
                                    "the current rate ",
                                    _help_eq("i"),
                                    ", footprint ",
                                    _help_eq("A"),
                                    ", and saturated properties ",
                                    _help_eq("K̄"),
                                    ", ",
                                    _help_eq("b_sat"),
                                    ", and ",
                                    _help_eq("S̄_y"),
                                    ".",
                                ]
                            ),
                            html.Li(
                                [
                                    "If ",
                                    _help_eq("Δh_pred"),
                                    " is finite and does not exceed ",
                                    _help_eq("Δh_allow"),
                                    ", stop. The pair ",
                                    _help_eq("(A, i)"),
                                    " is accepted.",
                                ]
                            ),
                            html.Li(
                                [
                                    "If the predicted mound is too large, scale the rate "
                                    "downward. Because mound height scales approximately "
                                    "with the square root of recharge rate, the update is ",
                                    _help_eq(
                                        "i ← i · 0.99 · (Δh_allow / Δh_pred)²"
                                    ),
                                    ", with a small positive floor so the rate never "
                                    "collapses to zero numerically. Return to step 1.",
                                ]
                            ),
                        ],
                        className="mb-2 ps-3",
                    ),
                    html.P(
                        [
                            "The ratio ",
                            _help_eq("i / K_vadose,min"),
                            " is stored as an infiltration-to-conductivity factor. Annual "
                            "surface recharge volume is then accumulated from the accepted "
                            "footprint and rate, and compared with source volume to form "
                            "the surface rechargeable percentage ",
                            _help_eq("η"),
                            ".",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            html.Strong("Number of injection wells. "),
                            "Injection sizing first chooses a confined or unconfined "
                            "regime from the inferred aquifer type. In either regime the "
                            "peak daily source demand is again ",
                            _help_eq("V_day = V_month,max / 30.25"),
                            ". A hydrologic maximum rate per well, ",
                            _help_eq("Q_hydro"),
                            ", is obtained by inverting a Theis-type well response: given "
                            "allowable head change ",
                            _help_eq("Δh"),
                            ", transmissivity ",
                            _help_eq("T"),
                            ", storativity ",
                            _help_eq("S"),
                            ", observation radius ",
                            _help_eq("r = 1"),
                            " ft, and time ",
                            _help_eq("t = 50"),
                            " days, solve for the pumping (injection) rate that produces "
                            "that head change. The operating rate is then capped by the "
                            "Default Parameters maximum injection rate ",
                            _help_eq("Q_max"),
                            ":",
                        ],
                        className="mb-2",
                    ),
                    html.P(
                        [
                            _help_eq("Q_well = minimum of Q_hydro and Q_max"),
                            ".",
                        ],
                        className="mb-2",
                    ),
                    html.P(
                        [
                            "For ",
                            html.Strong("confined"),
                            " injection, allowable head change is based on fracture-"
                            "gradient protection. With depth to the confined unit ",
                            _help_eq("D_c"),
                            ", ",
                            _help_eq("Δh = D_c · 0.6 · 2.31"),
                            " (0.6 psi/ft converted to feet of water). Transmissivity and "
                            "storage use the target confined layer: ",
                            _help_eq("T = K_target · b_target"),
                            " and ",
                            _help_eq("S = (sy/ss)_target · b_target"),
                            ".",
                        ],
                        className="mb-2",
                    ),
                    html.P(
                        [
                            "For ",
                            html.Strong("unconfined"),
                            " injection, the target layer must be saturated (its bottom "
                            "deeper than the average water table) and have adequate "
                            "hydraulic conductivity; otherwise the well count is set to "
                            "zero. Allowable head rise is ",
                            _help_eq("Δh = max(d_gw − d_gw,op, 0)"),
                            ", corrected for unconfined geometry as ",
                            _help_eq(
                                "Δh' = Δh − Δh² / (2 · b_sat)"
                            ),
                            ". Transmissivity and storage use saturated-zone thickness-"
                            "weighted means, ",
                            _help_eq("T = K̄ · b_sat"),
                            " and ",
                            _help_eq("S = S̄_y · b_sat"),
                            ".",
                        ],
                        className="mb-2",
                    ),
                    html.P(
                        [
                            "The required number of wells is the ceiling of daily demand "
                            "divided by per-well rate, then limited by the Default "
                            "Parameters maximum well count ",
                            _help_eq("N_max"),
                            ":",
                        ],
                        className="mb-2",
                    ),
                    html.P(
                        [
                            _help_eq(
                                "N = minimum of ceil(V_day / Q_well) and N_max"
                            ),
                            ".",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            "If demand would require more than ",
                            _help_eq("N_max"),
                            " wells, the design is truncated. Annual injection volume is "
                            "then based on ",
                            _help_eq("N"),
                            " wells at ",
                            _help_eq("Q_well"),
                            ", which can reduce ",
                            _help_eq("η"),
                            " and fail Recharge Efficiency.",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        [
                            html.Strong("Number of dry wells. "),
                            "Dry-well sizing follows a parallel Theis-based structure, "
                            "again distinguishing unconfined and confined regimes. In the ",
                            html.Strong("unconfined"),
                            " case, usable head difference is ",
                            _help_eq(
                                "Δh = d_gw − max(d_gw,op, d_dw)"
                            ),
                            ", where ",
                            _help_eq("d_dw"),
                            " is the Default Parameters dry-well rule-depth cutoff. If ",
                            _help_eq("Δh ≤ 0"),
                            ", no dry wells are assigned. Otherwise the same unconfined "
                            "correction ",
                            _help_eq("Δh'"),
                            " and saturated-zone ",
                            _help_eq("T"),
                            " and ",
                            _help_eq("S"),
                            " are used to invert for ",
                            _help_eq("Q_hydro"),
                            ", after which ",
                            _help_eq("Q_well"),
                            " and ",
                            _help_eq("N"),
                            " are computed exactly as for injection wells (including the ",
                            _help_eq("Q_max"),
                            " and ",
                            _help_eq("N_max"),
                            " caps). In the ",
                            html.Strong("confined"),
                            " dry-well path, allowable head is taken as a fraction of "
                            "depth to the confined unit, ",
                            _help_eq("Δh = 0.20 · D_c"),
                            ", and target-layer ",
                            _help_eq("T"),
                            " and ",
                            _help_eq("S"),
                            " are used in the Theis inversion before applying the same "
                            "well-count formulas.",
                        ],
                        className="mb-3",
                    ),
                    html.P(
                        "These sized volumes—surface spreading, injection, and dry "
                        "well—are the inputs to the rechargeable percentages used by hard "
                        "Recharge Efficiency and by soft Surface recharge suitability in "
                        "the stages that follow.",
                        className="mb-3",
                    ),
                    html.H6(
                        "Stage 3 — Hard constraints (pass / fail)",
                        className="fw-semibold mb-2",
                    ),
                    html.P(
                        [
                            "The three MAR options are evaluated one at a time: Surface "
                            "Recharge, Dry Well(s), and Injection Well(s). For each of "
                            "those options, every hard constraint returns either pass or "
                            "fail, plus a short explanation. Principal hard checks "
                            "include Physical surface rechargeability (Surface Recharge "
                            "fails on confined sites), Vadose zone contaminant impact and "
                            "Target aquifer anthropogenic contaminants (from water-"
                            "quality answers), and Recharge Efficiency. Recharge "
                            "Efficiency passes when that option’s rechargeable percentage "
                            "meets or exceeds the Default Parameters minimum, that is ",
                            _help_eq("η ≥ η_min"),
                            ", where ",
                            _help_eq("η"),
                            " is the percent of annual source water the option can "
                            "recharge and ",
                            _help_eq("η_min"),
                            " is the required minimum. Any hard failure is decisive for "
                            "the traffic light in Stage 5.",
                        ],
                        className="mb-3",
                    ),
                    html.H6(
                        "Stage 4 — Soft constraints (ordered response levels)",
                        className="fw-semibold mb-2",
                    ),
                    html.P(
                        [
                            "For the same MAR option, each soft constraint returns an "
                            "integer response ",
                            _help_eq("r"),
                            " in the set ",
                            _help_eq("{-1, 0, 1, 2, 3, 4}"),
                            ", together with optional penalty text. The scale is "
                            "interpreted as follows: ",
                            _help_eq("r = -1"),
                            " means the constraint is irrelevant for that option or "
                            "aquifer type; ",
                            _help_eq("r = 0"),
                            " means acceptable; ",
                            _help_eq("r = 1"),
                            " means acceptable with additional cost; ",
                            _help_eq("r = 2"),
                            " means warning; ",
                            _help_eq("r = 3"),
                            " means mitigation required; and ",
                            _help_eq("r = 4"),
                            " means reject. Examples include Vadose zone infiltration, "
                            "Vadose zone residence time, Surface recharge suitability, "
                            "Confined aquifer depth Suitability, and Confined leakage "
                            "significance. Irrelevant responses (",
                            _help_eq("r = -1"),
                            ") are ignored when aggregating warnings.",
                        ],
                        className="mb-3",
                    ),
                    html.H6(
                        "Stage 5 — Traffic-light aggregation",
                        className="fw-semibold mb-2",
                    ),
                    html.P(
                        "After hard and soft constraints are evaluated for a given MAR "
                        "option, that option’s traffic color is assigned by the following "
                        "ordered rules.",
                        className="mb-2",
                    ),
                    html.Ol(
                        [
                            html.Li(
                                "If any hard constraint failed, the result is red (Fail). "
                                "The displayed detail is taken from the first failed hard "
                                "constraint."
                            ),
                            html.Li(
                                "Otherwise, if any soft constraint returned reject "
                                "(response 4), the result is red (Fail), using that soft "
                                "constraint’s penalty text when available."
                            ),
                            html.Li(
                                "Otherwise, if any soft constraint returned a response of "
                                "1, 2, or 3, the result is orange (Pass with Warnings). "
                                "The status line reports the soft constraint with the "
                                "largest of those response values."
                            ),
                            html.Li(
                                "Otherwise the result is green (Pass): every hard "
                                "constraint passed, and every relevant soft response is "
                                "acceptable (response 0) or irrelevant."
                            ),
                        ],
                        className="mb-3 ps-3",
                    ),
                    html.P(
                        [
                            "In compact form, if ",
                            _help_eq("r_max"),
                            " is the largest nonnegative soft response for that option, "
                            "then the color is red if any hard constraint failed or ",
                            _help_eq("r_max = 4"),
                            "; orange if ",
                            _help_eq("r_max"),
                            " is 1, 2, or 3; and green otherwise.",
                        ],
                        className="mb-4",
                    ),
                    html.H6("4. Traffic-light meanings", className="fw-bold mb-2"),
                    html.Ul(
                        [
                            html.Li(
                                [
                                    html.Span(
                                        className="rounded-circle d-inline-block me-2",
                                        style={
                                            "width": "12px",
                                            "height": "12px",
                                            "backgroundColor": "#198754",
                                            "verticalAlign": "middle",
                                        },
                                    ),
                                    html.Strong("Green — Pass. "),
                                    "All hard constraints pass, and soft constraints are "
                                    "acceptable or not applicable.",
                                ]
                            ),
                            html.Li(
                                [
                                    html.Span(
                                        className="rounded-circle d-inline-block me-2",
                                        style={
                                            "width": "12px",
                                            "height": "12px",
                                            "backgroundColor": "#fd7e14",
                                            "verticalAlign": "middle",
                                        },
                                    ),
                                    html.Strong("Orange — Pass with Warnings. "),
                                    "No hard failure and no soft reject, but at least one "
                                    "soft constraint indicates added cost, a warning, or "
                                    "required mitigation.",
                                ]
                            ),
                            html.Li(
                                [
                                    html.Span(
                                        className="rounded-circle d-inline-block me-2",
                                        style={
                                            "width": "12px",
                                            "height": "12px",
                                            "backgroundColor": "#dc3545",
                                            "verticalAlign": "middle",
                                        },
                                    ),
                                    html.Strong("Red — Fail. "),
                                    "A hard constraint fails, or a soft constraint "
                                    "rejects the option.",
                                ]
                            ),
                        ],
                        className="mb-3",
                    ),
                    html.H6("5. Limitations", className="fw-bold mb-2"),
                    html.P(
                        "This calculation is an initial hydrogeologic screen. It does not "
                        "replace detailed engineering design, laboratory or field "
                        "validation of hydraulic properties, or the full multi-criteria "
                        "decision analysis performed on the Engineering, Analysis, and "
                        "Decision tabs. Changing Default Parameters or stratigraphy "
                        "changes the intermediate quantities in Stage 2 and can therefore "
                        "change both constraint outcomes and traffic colors.",
                        className="mb-0 text-muted",
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
        size="xl",
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
                                                "Initial Hydrogeologic Feasibility",
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
                                        html.P(
                                            (
                                                'Click "Check Initial Feasibility" to evaluate '
                                                "potential MAR options using hard and soft "
                                                "hydrogeologic constraints."
                                            ),
                                            className="text-muted fs-6 mb-2",
                                        ),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    dbc.Button(
                                                        "Check Initial Feasibility",
                                                        id="check-initial-feasibility-btn",
                                                        color="success",
                                                        className=(
                                                            "text-wrap fw-semibold shadow-sm "
                                                            "d-block"
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
                                                        "d-flex justify-content-start "
                                                        "align-items-start pb-2 pb-md-0"
                                                    ),
                                                ),
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
                                                    md=True,
                                                    className="ps-md-2 min-w-0",
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
                    html.P(
                        "Configure soil layers and their hydrogeological properties. "
                        "Selecting a soil type auto-fills hydraulic conductivity, "
                        "specific storage, and specific yield, but these can be "
                        "overridden.",
                        className="mb-4",
                    ),
                    
                    html.Div(id="stratigraphy-error-message", className="mb-3", children=[]),
                    
                    # Table controls
                    html.Small(
                        "Select rows to delete or move",
                        className="text-muted d-block mb-2",
                    ),
                    dbc.ButtonGroup(
                        [
                            dbc.Button(
                                "Add Layer",
                                id="add-layer-btn",
                                color="success",
                                size="sm",
                                title="Add a stratigraphy layer row",
                            ),
                            dbc.Button(
                                "Delete Selected",
                                id="delete-layer-btn",
                                color="danger",
                                size="sm",
                                title="Delete selected layer rows",
                            ),
                            dbc.Button(
                                "Move Up",
                                id="move-up-btn",
                                color="info",
                                size="sm",
                                title="Move selected layer up",
                            ),
                            dbc.Button(
                                "Move Down",
                                id="move-down-btn",
                                color="info",
                                size="sm",
                                title="Move selected layer down",
                            ),
                        ],
                        className="mb-3",
                    ),
                    
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
                                        "Target Recharge Layer",
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
                                html.Strong("Initial Hydrogeologic Feasibility — "),
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
                            html.Button(
                                "?",
                                id="groundwater-level-help-btn",
                                type="button",
                                className="mar-help-btn",
                                title="Help: groundwater level configuration",
                            ),
                        ],
                        className="d-flex align-items-center justify-content-end mb-3",
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
                                className="mb-2 collapse-toggle-check label-dark-grey",
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
                                "current hydrogeologic inputs. Contour method depends on "
                                "whether the site is classified as confined or unconfined.",
                                className="mb-3",
                            ),
                        ]
                    ),
                    html.H6("How mound contours are computed", className="fw-bold mb-2"),
                    html.P(
                        [
                            "Contours are evaluated on a plan-view grid over the MAR "
                            "footprint, then clipped to that rectangle. A uniform "
                            "regional hydraulic gradient of ",
                            _help_eq("i_reg = 0.02"),
                            " (2%) is added along ",
                            _help_eq("x"),
                            " so the displayed surface is ",
                            _help_eq("z = h_mound − i_reg · x"),
                            " (ft). Simulation time for the analytical kernels is ",
                            _help_eq("t = 50"),
                            " days.",
                        ],
                        className="mb-3",
                    ),
                    html.H6("Confined aquifer (Theis)", className="fw-bold mb-2"),
                    html.P(
                        [
                            "For confined sites, contours use the Theis well solution for "
                            "head rise (injection treated as a source) at radial distance ",
                            _help_eq("r = √(x² + y²)"),
                            " from the footprint center. Aquifer transmissivity and "
                            "storativity come from the recharge-target layer: ",
                            _help_eq("T = K · B"),
                            " and ",
                            _help_eq("S = S_s · B"),
                            ".",
                        ],
                        className="mb-2",
                    ),
                    html.Pre(
                        "u = (r² · S) / (4 · T · t)\n"
                        "W(u) = E₁(u) = ∫_u^∞ (e^{-y} / y) dy\n"
                        "h_Theis(r, t) = (Q / (4 · π · T)) · W(u)",
                        className="bg-light border rounded p-2 small mb-2",
                    ),
                    html.P(
                        [
                            "Injection rate ",
                            _help_eq("Q"),
                            " is the lesser of the configured maximum injection rate per "
                            "well and the Theis rate that produces allowable head rise ",
                            _help_eq("H_max"),
                            " at a reference well radius (",
                            _help_eq("r ≈ 1"),
                            " ft), with ",
                            _help_eq("H_max = 0.6 · 2.31 · D_conf"),
                            " where ",
                            _help_eq("D_conf"),
                            " is the depth to the top of the confined target unit (ft).",
                        ],
                        className="mb-3",
                    ),
                    html.H6("Unconfined aquifer (Hantush-type rectangular recharge)", className="fw-bold mb-2"),
                    html.P(
                        [
                            "For unconfined sites, contours use a Hantush-type solution for "
                            "continuous recharge over a rectangular basin of half-length ",
                            _help_eq("ℓ"),
                            " and half-width ",
                            _help_eq("a"),
                            " (from the designed spreading area). Saturated-zone "
                            "properties below the water table are thickness-weighted "
                            "means ",
                            _help_eq("K̄"),
                            " and ",
                            _help_eq("S̄_y"),
                            " with saturated thickness ",
                            _help_eq("b"),
                            ". Recharge strength ",
                            _help_eq("w"),
                            " is the designed infiltration rate (ft/day).",
                        ],
                        className="mb-2",
                    ),
                    html.Pre(
                        "ν = 4 · t · K̄ · b / S̄_y\n"
                        "\n"
                        "S(x, y) = S₁ + S₂ + S₃ + S₄\n"
                        "  S₁ = ∫₀¹ erf((ℓ + x)/√(ν τ)) · erf((a + y)/√(ν τ)) dτ\n"
                        "  S₂ = ∫₀¹ erf((ℓ + x)/√(ν τ)) · erf((a − y)/√(ν τ)) dτ\n"
                        "  S₃ = ∫₀¹ erf((ℓ − x)/√(ν τ)) · erf((a + y)/√(ν τ)) dτ\n"
                        "  S₄ = ∫₀¹ erf((ℓ − x)/√(ν τ)) · erf((a − y)/√(ν τ)) dτ\n"
                        "\n"
                        "Δh(x, y) = √[ (w / (2 · K̄)) · (K̄ · b / S̄_y) · t · S(x, y) ]",
                        className="bg-light border rounded p-2 small mb-2",
                    ),
                    html.P(
                        [
                            "The plotted mound field is ",
                            _help_eq("h_mound = Δh(x, y)"),
                            " (ft of water-table rise). Contours are then combined with "
                            "the same 2% regional gradient as in the confined case.",
                        ],
                        className="mb-0",
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
                                dbc.Checkbox(
                                    id="view-recharge-mound-outputs-check",
                                    label=html.Strong(
                                        "View Optional Recharge Mound Outputs"
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
                ],
                className="flex-grow-1 overflow-auto",
            ),
        ],
        className="mb-4 h-100 w-100 d-flex flex-column",
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
                ],
                className="flex-grow-1",
            ),
        ],
        className="mb-4 h-100 w-100 d-flex flex-column",
    )


DEFAULT_MAX_DRY_WELL_DEPTH_FT = 120.0

# Field titles stay solid black; notes use a softer muted italic for contrast.
_FIELD_TITLE_STYLE = {
    "fontSize": "0.72rem",
    "lineHeight": 1.2,
    "color": "#212529",
    "fontWeight": "600",
}
_FIELD_NOTE_STYLE = {
    "fontSize": "0.72rem",
    "lineHeight": 1.25,
    "color": "#6c757d",
    "fontStyle": "italic",
}


def _input_field_note(text: str):
    """Helper text under a compact numeric input (muted italic vs field title)."""
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
                        style=_FIELD_TITLE_STYLE,
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
                    style=_FIELD_TITLE_STYLE,
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
                    style=_FIELD_TITLE_STYLE,
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
            style={
                "fontSize": "0.75rem",
                "color": "#6c757d",
                "fontStyle": "italic",
            },
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
                                        style=_FIELD_TITLE_STYLE,
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
                                        style=_FIELD_TITLE_STYLE,
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
                                        style=_FIELD_TITLE_STYLE,
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
    """Build the Geometry and View cards side by side (equal half-width)."""
    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        _build_geometry_card(),
                        xs=12,
                        md=6,
                        className="d-flex",
                        style={"minWidth": 0},
                    ),
                    dbc.Col(
                        _build_view_card(),
                        xs=12,
                        md=6,
                        className="d-flex",
                        style={"minWidth": 0},
                    ),
                ],
                className="align-items-stretch g-3 w-100",
            ),
        ],
        className="w-100",
    )