"""
Environmental Impact tab component - MAR Source Water Suitability Assessment.
Based on chem2.py dashboard.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html, dash_table
import plotly.graph_objects as go
import pandas as pd
import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.callbacks.ai_environment import _normalize_stored_string
from mar_dss.app.utils.tab_tooltips import tab_nav_id, tab_tooltip

# --- Data Structures for Logic and Display ---

# --- Water quality screening answers (shared with callbacks and soft_constraints) ---
WQ_UNKNOWN = "Unknown"
WQ_NO = "No"
WQ_YES = "Yes"
WQ_TURBIDITY_LOW = "<5 NTU"
WQ_TURBIDITY_MOD = "5-20 NTU"
WQ_TURBIDITY_HIGH = ">20 NTU"
DEFAULT_WATER_QUALITY_RISK = WQ_UNKNOWN
NOT_AVAILABLE_RISK = WQ_UNKNOWN  # legacy alias used by scoring / data-gap logic

YES_NO_UNKNOWN = (WQ_UNKNOWN, WQ_NO, WQ_YES)
TURBIDITY_OPTIONS = (
    WQ_UNKNOWN,
    WQ_TURBIDITY_LOW,
    WQ_TURBIDITY_MOD,
    WQ_TURBIDITY_HIGH,
)

# Answers that do not trigger treatment or a suitability warning.
WQ_BENIGN_ANSWERS = frozenset({WQ_UNKNOWN, WQ_NO, WQ_TURBIDITY_LOW})

WQ_QUESTIONS = (
    {
        "key": "source_contaminants",
        "storage_key": "wq_source_contaminants",
        "component_id": "env-wq-q1",
        "number": "1",
        "text": (
            "Is the source water impacted with industrial, domestic, or emerging "
            "contaminants (e.g., VOCs, metals, PFAS)?"
        ),
        "options": YES_NO_UNKNOWN,
        "tooltip": "Industrial, domestic, or emerging contaminants in the source water",
    },
    {
        "key": "source_turbidity",
        "storage_key": "wq_source_turbidity",
        "component_id": "env-wq-q2",
        "number": "2",
        "text": "What is the turbidity of the source water?",
        "options": TURBIDITY_OPTIONS,
        "tooltip": "Source-water turbidity as a clogging and pretreatment indicator",
    },
    {
        "key": "vadose_impacted",
        "storage_key": "wq_vadose_impacted",
        "component_id": "env-wq-q3",
        "number": "3",
        "text": (
            "Is the Vadose/Unsaturated Zone Impacted by Contaminants "
            "(e.g. VOCs, metals, emerging contaminants)?"
        ),
        "options": YES_NO_UNKNOWN,
        "tooltip": "Contamination in the unsaturated zone above the target aquifer",
    },
    {
        "key": "aquifer_anthropogenic",
        "storage_key": "wq_aquifer_anthropogenic",
        "component_id": "env-wq-q4",
        "number": "4",
        "text": (
            "Is the Target Aquifer Impacted by Anthropogenic Contaminants "
            "(e.g. VOCs, metals, emerging contaminants)?"
        ),
        "options": YES_NO_UNKNOWN,
        "tooltip": "Human-caused contaminants already present in native groundwater",
    },
    {
        "key": "aquifer_natural",
        "storage_key": "wq_aquifer_natural",
        "component_id": "env-wq-q5",
        "number": "5",
        "text": (
            "Is the Target Aquifer Impacted by Naturally Occurring Contaminants "
            "(e.g. salts, inorganic compounds)?"
        ),
        "options": YES_NO_UNKNOWN,
        "tooltip": "Naturally occurring salts or inorganics in native groundwater",
    },
)

WQ_STORAGE_KEYS = tuple(q["storage_key"] for q in WQ_QUESTIONS)
WQ_COMPONENT_IDS = tuple(q["component_id"] for q in WQ_QUESTIONS)
WQ_LOGIC_KEYS = tuple(q["key"] for q in WQ_QUESTIONS)
WQ_ALLOWED_BY_STORAGE = {q["storage_key"]: set(q["options"]) for q in WQ_QUESTIONS}

# Radio option text in Water Quality assessment cards (black, not muted grey)
_WQ_RADIO_LABEL_STYLE = {
    "display": "block",
    "margin-bottom": "8px",
    "fontSize": "0.85rem",
    "color": "#000",
}


# 1. Decision Logic and Scoring (Maps screening answer to score, treatment, and recommendations)
DECISION_LOGIC = {
    "source_contaminants": {
        WQ_UNKNOWN: {
            "score": 0, "color": "secondary", "treatment_key": "Q1_NA",
            "rec": "Collect source-water contaminant data (VOCs, metals, PFAS) before final suitability assessment.",
        },
        WQ_NO: {
            "score": 0, "color": "success", "treatment_key": "Q1_NO",
            "rec": "None.",
        },
        WQ_YES: {
            "score": 5, "color": "danger", "treatment_key": "Q1_YES",
            "rec": (
                "If yes, MAR may still be possible based on site-specific conditions and overall "
                "objectives, but additional considerations and potential costs may be necessary "
                "and are beyond the scope of this tool."
            ),
        },
    },
    "source_turbidity": {
        WQ_UNKNOWN: {
            "score": 0, "color": "secondary", "treatment_key": "Q2_NA",
            "rec": "Collect turbidity data before final suitability assessment.",
        },
        WQ_TURBIDITY_LOW: {
            "score": 0, "color": "success", "treatment_key": "Q2_LOW",
            "rec": "None.",
        },
        WQ_TURBIDITY_MOD: {
            "score": 1, "color": "warning", "treatment_key": "Q2_MOD",
            "rec": "Sedimentation/clarification recommended; evaluate seasonal variation.",
        },
        WQ_TURBIDITY_HIGH: {
            "score": 2, "color": "danger", "treatment_key": "Q2_HIGH",
            "rec": "Pre-treatment required (sedimentation and filtration) to prevent clogging.",
        },
    },
    "vadose_impacted": {
        WQ_UNKNOWN: {
            "score": 0, "color": "secondary", "treatment_key": "Q3_NA",
            "rec": "Investigate vadose/unsaturated zone contamination before recharge.",
        },
        WQ_NO: {
            "score": 0, "color": "success", "treatment_key": "Q3_NO",
            "rec": "None.",
        },
        WQ_YES: {
            "score": 3, "color": "danger", "treatment_key": "Q3_YES",
            "rec": (
                "Vadose/unsaturated zone is impacted by contaminants. "
                "Surface recharge is not feasible; consider options that bypass "
                "the vadose zone (e.g., injection) or site remediation."
            ),
        },
    },
    "aquifer_anthropogenic": {
        WQ_UNKNOWN: {
            "score": 0, "color": "secondary", "treatment_key": "Q4_NA",
            "rec": "Characterize native groundwater for anthropogenic contaminants before recharge.",
        },
        WQ_NO: {
            "score": 0, "color": "success", "treatment_key": "Q4_NO",
            "rec": "None.",
        },
        WQ_YES: {
            "score": 5, "color": "danger", "treatment_key": "Q4_YES",
            "rec": (
                "Target aquifer is impacted by anthropogenic contaminants. "
                "Aquifer water quality is unsuitable; all MAR options are not feasible."
            ),
        },
    },
    "aquifer_natural": {
        WQ_UNKNOWN: {
            "score": 0, "color": "secondary", "treatment_key": "Q5_NA",
            "rec": "Characterize native groundwater for salts and naturally occurring inorganics.",
        },
        WQ_NO: {
            "score": 0, "color": "success", "treatment_key": "Q5_NO",
            "rec": "None.",
        },
        WQ_YES: {
            "score": 2, "color": "warning", "treatment_key": "Q5_YES",
            "rec": (
                "If yes, MAR may still be possible based on site-specific conditions and overall "
                "objectives, but additional considerations and potential costs may be necessary "
                "and are beyond the scope of this tool."
            ),
        },
    },
}

# Sum of maximum points from every assessment step (all HIGH / worst-case answers).
RISK_SCORE_MAX = sum(
    max(int(level.get("score", 0) or 0) for level in step.values())
    for step in DECISION_LOGIC.values()
)

# Decision bands used by Final Assessment (must match update_dashboard thresholds).
RISK_SCORE_SUITABLE_MAX = 2       # 0–2 Suitable
RISK_SCORE_CONDITIONAL_MAX = 7    # 3–7 Conditionally suitable
RISK_SCORE_UNSUITABLE_MIN = 8     # 8+ Not suitable

ASSESSMENT_QUESTION_LABELS = {
    "source_contaminants": "1",
    "source_turbidity": "2",
    "vadose_impacted": "3",
    "aquifer_anthropogenic": "4",
    "aquifer_natural": "5",
}

# 2. Treatment Technology Database
# Cost ranges shown in $/ft³ (converted from literature mid-range $/m³ ÷ 35.3147).
_TREATMENT_COST_RANGES_M3 = [
    (0.05, 0.15),
    (0.10, 0.30),
    (0.20, 0.60),
    (0.30, 0.80),
    (0.40, 1.20),
    (0.80, 2.50),
    (0.50, 1.50),
    (0.10, 0.40),
    (0.15, 0.35),
]


def _format_cost_range_ft3(lo_m3: float, hi_m3: float) -> str:
    lo_ft3 = lo_m3 / 35.3147
    hi_ft3 = hi_m3 / 35.3147
    return f"${lo_ft3:.4f}-{hi_ft3:.4f}"


TREATMENT_DF = pd.DataFrame({
    "Treatment Technology": [
        "Sedimentation/Clarification",
        "Media Filtration (Sand/Anthracite)",
        "Membrane Filtration (MF/UF)",
        "Granular Activated Carbon (GAC)",
        "Ion Exchange",
        "Reverse Osmosis (RO)",
        "Advanced Oxidation (AOP)",
        "Disinfection (Chlorination/UV/Ozone)",
        "Aeration/Oxidation",
    ],
    "Cost Range ($/ft³)": [
        _format_cost_range_ft3(lo, hi) for lo, hi in _TREATMENT_COST_RANGES_M3
    ],
    "Capital Cost Scale": [
        "Low",
        "Low-Medium",
        "Medium-High",
        "Medium",
        "Medium-High",
        "Very High",
        "High",
        "Low-Medium",
        "Low-Medium",
    ],
    "O&M Intensity": [
        "Low",
        "Low-Medium",
        "Medium",
        "Medium-High",
        "Medium",
        "High",
        "Medium-High",
        "Low",
        "Low-Medium",
    ],
    "Best For": [
        "TSS/Turbidity removal",
        "Particle removal, polishing",
        "Fine particle, pathogen removal",
        "Organic matter, emerging contaminants",
        "Ion removal (nitrate, metals)",
        "TDS/salinity reduction",
        "Emerging contaminants, organics",
        "Pathogen inactivation",
        "Redox adjustment, Fe/Mn removal",
    ],
})

# 3. Treatment Mapping (from decision logic to treatment technologies)
TREATMENT_MAPPING = {
    "Q1_NA": [],
    "Q1_NO": [],
    "Q1_YES": [
        "Granular Activated Carbon (GAC)",
        "Advanced Oxidation (AOP)",
        "Ion Exchange",
        "Reverse Osmosis (RO)",
    ],
    "Q2_NA": [],
    "Q2_LOW": [],
    "Q2_MOD": ["Sedimentation/Clarification"],
    "Q2_HIGH": [
        "Sedimentation/Clarification",
        "Media Filtration (Sand/Anthracite)",
        "Membrane Filtration (MF/UF)",
    ],
    "Q3_NA": [],
    "Q3_NO": [],
    "Q3_YES": ["Vadose Zone Remediation (Toxic Contaminants)"],
    "Q4_NA": [],
    "Q4_NO": [],
    "Q4_YES": [
        "Granular Activated Carbon (GAC)",
        "Advanced Oxidation (AOP)",
        "Ion Exchange",
    ],
    "Q5_NA": [],
    "Q5_NO": [],
    "Q5_YES": ["Reverse Osmosis (RO)", "Ion Exchange"],
}

# 4. Treatment Options (maps treatment keys to list of (tech_name, cost_scale) tuples)
# Based on TREATMENT_MAPPING and TREATMENT_DF cost scales
TREATMENT_OPTIONS = {
    "Q1_NA": [],
    "Q1_NO": [],
    "Q1_YES": [
        ("Granular Activated Carbon (GAC)", "Medium"),
        ("Advanced Oxidation (AOP)", "High"),
        ("Ion Exchange", "Medium-High"),
        ("Reverse Osmosis (RO)", "Very High"),
    ],
    "Q2_NA": [],
    "Q2_LOW": [],
    "Q2_MOD": [("Sedimentation/Clarification", "Low")],
    "Q2_HIGH": [
        ("Sedimentation/Clarification", "Low"),
        ("Media Filtration (Sand/Anthracite)", "Low-Medium"),
        ("Membrane Filtration (MF/UF)", "Medium-High"),
    ],
    "Q3_NA": [],
    "Q3_NO": [],
    "Q3_YES": [("Vadose Zone Remediation (Toxic Contaminants)", "High")],
    "Q4_NA": [],
    "Q4_NO": [],
    "Q4_YES": [
        ("Granular Activated Carbon (GAC)", "Medium"),
        ("Advanced Oxidation (AOP)", "High"),
        ("Ion Exchange", "Medium-High"),
    ],
    "Q5_NA": [],
    "Q5_NO": [],
    "Q5_YES": [
        ("Reverse Osmosis (RO)", "Very High"),
        ("Ion Exchange", "Medium-High"),
    ],
}

# 5. Treatment Cost Map (costs in $/m³, using mid-range values from TREATMENT_DF)
TREATMENT_COST_MAP = {
    "Sedimentation/Clarification": 0.10,  # $0.05-0.15 -> 0.10
    "Media Filtration (Sand/Anthracite)": 0.20,  # $0.10-0.30 -> 0.20
    "Membrane Filtration (MF/UF)": 0.40,  # $0.20-0.60 -> 0.40
    "Granular Activated Carbon (GAC)": 0.55,  # $0.30-0.80 -> 0.55
    "Ion Exchange": 0.80,  # $0.40-1.20 -> 0.80
    "Reverse Osmosis (RO)": 1.65,  # $0.80-2.50 -> 1.65
    "Advanced Oxidation (AOP)": 1.00,  # $0.50-1.50 -> 1.00
    "Disinfection (Chlorination/UV/Ozone)": 0.25,  # $0.10-0.40 -> 0.25
    "Aeration/Oxidation": 0.25,  # $0.15-0.35 -> 0.25
}

# 6. Vadose Zone Remediation Costs (in $/acre-ft)
VADOSE_REMEDIATION_COSTS = {
    "Vadose Zone Remediation (Biodegradable)": 50,  # Low end estimate
    "Vadose Zone Remediation (Toxic Contaminants)": 500,  # High end estimate
}

# 7. Cost Scale to Score Mapping (for fallback cost estimation)
COST_SCALE_TO_SCORE = {
    "Low": 1,
    "Low-Medium": 2,
    "Moderate": 3,
    "Medium": 3,
    "Medium-High": 4,
    "High": 5,
    "Very High": 6,
    "Very High - Prohibitive": 7,
    "Moderate Study Cost": 3,
    "Moderate + High Study": 4,
}

_FT3_PER_M3 = 35.3147  # 1 m³ ≈ 35.3147 ft³


def _tech_unit_cost_per_m3(tech_name: str, cost_scale: str) -> float:
    """Unit water-treatment cost ($/m³); vadose remediation techs return 0 here."""
    if tech_name in VADOSE_REMEDIATION_COSTS:
        return 0.0
    if tech_name in TREATMENT_COST_MAP:
        return float(TREATMENT_COST_MAP[tech_name])
    return float(COST_SCALE_TO_SCORE.get(cost_scale, 0) or 0) * 50.0


def _worst_case_water_treatment_cost_per_ft3() -> float:
    """
    Sum of the most expensive water-treatment option for the highest-scoring
    answer on every assessment step (theoretical dial ceiling, $/ft³).
    """
    total_m3 = 0.0
    for step_levels in DECISION_LOGIC.values():
        best = max(
            step_levels.values(),
            key=lambda d: int(d.get("score", 0) or 0),
        )
        treatments = TREATMENT_OPTIONS.get(best.get("treatment_key", ""), [])
        max_m3 = 0.0
        for tech_name, cost_scale in treatments:
            max_m3 = max(max_m3, _tech_unit_cost_per_m3(tech_name, cost_scale))
        total_m3 += max_m3
    return total_m3 / _FT3_PER_M3


# Ceiling for the Treatment Cost dial (matches calculate_cost_score units).
TREATMENT_COST_FT3_MAX = round(_worst_case_water_treatment_cost_per_ft3(), 4)

_LEGACY_VADOSE_YES = (
    "Yes, highly toxic contaminants in the vadose zone "
    "(e.g., heavy metals, volatile organic compounds, radioactive materials)"
)


def _migrate_legacy_wq_answer(storage_key: str) -> str | None:
    """Map old risk-level answers onto the simplified screening questions."""
    if storage_key == "wq_source_turbidity":
        old = str(dash_storage.get_data("tss_turbidity_risk") or "").upper()
        if "HIGH" in old:
            return WQ_TURBIDITY_HIGH
        if "MODERATE" in old:
            return WQ_TURBIDITY_MOD
        if "LOW" in old:
            return WQ_TURBIDITY_LOW
        if old:
            return WQ_UNKNOWN
        return None
    if storage_key == "wq_vadose_impacted":
        old = str(dash_storage.get_data("vadose_zone_pollution") or "")
        if old.startswith("Yes"):
            return WQ_YES
        if old == "None":
            return WQ_NO
        return None
    if storage_key == "wq_source_contaminants":
        emerging = str(dash_storage.get_data("emerging_contaminants_risk") or "").upper()
        inorganic = str(dash_storage.get_data("inorganic_contaminants_risk") or "").upper()
        pathogen = str(dash_storage.get_data("pathogen_risk") or "").upper()
        answers = [emerging, inorganic, pathogen]
        if any("HIGH" in a for a in answers):
            return WQ_YES
        present = [a for a in answers if a]
        if present and all("LOW" in a and "MODERATE" not in a for a in present):
            return WQ_NO
        return None
    return None


def load_wq_answer(storage_key: str) -> str:
    """Load a screening answer, falling back to Unknown or a legacy mapping."""
    allowed = WQ_ALLOWED_BY_STORAGE.get(storage_key, set(YES_NO_UNKNOWN))
    raw = dash_storage.get_data(storage_key)
    if raw in allowed:
        return raw
    migrated = _migrate_legacy_wq_answer(storage_key)
    if migrated in allowed:
        return migrated
    return DEFAULT_WATER_QUALITY_RISK


def _sync_legacy_vadose_storage(choice: str) -> None:
    """Keep the legacy vadose_zone_pollution key aligned for reports and AI context."""
    if choice == WQ_YES:
        dash_storage.set_data("vadose_zone_pollution", _LEGACY_VADOSE_YES)
    elif choice == WQ_NO:
        dash_storage.set_data("vadose_zone_pollution", "None")
    else:
        dash_storage.set_data("vadose_zone_pollution", "None")


def persist_wq_answer(storage_key: str, value) -> str:
    """Validate and store a Water Quality radio selection."""
    allowed = WQ_ALLOWED_BY_STORAGE.get(storage_key, set(YES_NO_UNKNOWN))
    fallback = load_wq_answer(storage_key)
    choice = value if value in allowed else fallback
    if choice not in allowed:
        choice = DEFAULT_WATER_QUALITY_RISK
    dash_storage.set_data(storage_key, choice)
    if storage_key == "wq_vadose_impacted":
        _sync_legacy_vadose_storage(choice)
    return choice


def _wq_radio(question) -> dcc.RadioItems:
    return dcc.RadioItems(
        id=question["component_id"],
        options=[{"label": option, "value": option} for option in question["options"]],
        value=load_wq_answer(question["storage_key"]),
        className="d-flex flex-column",
        labelStyle=_WQ_RADIO_LABEL_STYLE,
    )


def _wq_question_block(question, *, last: bool = False):
    children = [
        html.P(
            [
                html.Span(f"{question['number']}. ", className="fw-bold text-primary"),
                question["text"],
            ],
            className="fw-bold mb-2",
            style={"fontSize": "0.95rem", "color": "#000"},
        ),
        _wq_radio(question),
    ]
    if not last:
        children.append(html.Hr(className="my-3"))
    return html.Div(children)


def create_water_quality_content():
    """Create the Water Quality screening content."""
    question_blocks = [
        _wq_question_block(question, last=(i == len(WQ_QUESTIONS) - 1))
        for i, question in enumerate(WQ_QUESTIONS)
    ]
    question_tooltips = [
        dbc.Tooltip(question["tooltip"], target=question["component_id"], placement="top")
        for question in WQ_QUESTIONS
    ]

    return [
        html.Div(
            [
        dbc.Row([
            dbc.Col([
                html.H5("Water Quality Screening", className="mb-3 text-primary", style={"fontSize": "1.1rem"}),
                dbc.Card([
                    dbc.CardHeader(
                        html.H6(
                            "Source Water, Vadose Zone, and Target Aquifer",
                            className="mb-0 text-white fw-bold",
                            style={"fontSize": "0.95rem"},
                        ),
                        className="bg-primary py-2",
                    ),
                    dbc.CardBody(question_blocks, className="p-3"),
                ], className="mb-3", style={"border-left": "4px solid #007bff"}),

                html.Hr(className="my-2"),
                html.H6("Treatment Cost Summary Table", className="mt-2 mb-2 text-dark", style={"fontSize": "0.95rem"}),
                html.Div(
                    dash_table.DataTable(
                        id='env-treatment-appendix-table',
                        columns=[{"name": i, "id": i} for i in TREATMENT_DF.columns],
                        data=TREATMENT_DF.to_dict('records'),
                        style_header={
                            'backgroundColor': '#f8f9fa',
                            'fontWeight': 'bold',
                            'fontSize': '11px'
                        },
                        style_cell={
                            'textAlign': 'left',
                            'minWidth': '70px', 'width': '100px', 'maxWidth': '200px',
                            'whiteSpace': 'normal',
                            'border': '1px solid #dee2e6',
                            'fontSize': '11px',
                            'padding': '5px'
                        },
                        style_header_conditional=[
                            {'if': {'column_id': 'Treatment Technology'}, 'backgroundColor': '#e3f2fd', 'color': '#0d47a1'},
                            {'if': {'column_id': 'Cost Range ($/ft³)'}, 'backgroundColor': '#e8f5e9', 'color': '#1b5e20'},
                            {'if': {'column_id': 'Capital Cost Scale'}, 'backgroundColor': '#fff3e0', 'color': '#e65100'},
                            {'if': {'column_id': "O&M Intensity"}, 'backgroundColor': '#f3e5f5', 'color': '#4a148c'},
                            {'if': {'column_id': 'Best For'}, 'backgroundColor': '#ede7f6', 'color': '#283593'}
                        ],
                        style_data_conditional=[
                            {'if': {'column_id': 'Treatment Technology'}, 'backgroundColor': '#f5faff'},
                            {'if': {'column_id': 'Cost Range ($/ft³)'}, 'backgroundColor': '#f4fbf4'},
                            {'if': {'column_id': 'Capital Cost Scale'}, 'backgroundColor': '#fff8ef'},
                            {'if': {'column_id': "O&M Intensity"}, 'backgroundColor': '#faf4fb'},
                            {'if': {'column_id': 'Best For'}, 'backgroundColor': '#f6f4fb'}
                        ],
                        export_format='csv'
                    ),
                    className="mb-2",
                    style={
                        "maxWidth": "100%",
                        "overflowX": "auto"
                    }
                )
            ], width=12, lg=7, style={
                "padding-right": "10px"
            }),

            dbc.Col([
                html.H6("Risk Score & Treatment Cost", className="mb-2 text-info", style={"fontSize": "0.95rem"}),
                dbc.Row([
                    dbc.Col([
                        html.P("Risk Score", className="text-center mb-1 small fw-bold", style={"fontSize": "0.85rem"}),
                        dcc.Graph(
                            id='env-score-gauge',
                            config={'displayModeBar': False, 'responsive': True},
                            style={'height': '200px', 'width': '100%', 'minHeight': '200px'}
                        ),
                    ], width=6),
                    dbc.Col([
                        html.P("Treatment Cost", className="text-center mb-1 small fw-bold", style={"fontSize": "0.85rem"}),
                        dcc.Graph(
                            id='env-cost-gauge',
                            config={'displayModeBar': False, 'responsive': True},
                            style={'height': '200px', 'width': '100%', 'minHeight': '200px'}
                        ),
                    ], width=6),
                ], className="mb-2"),

                html.H6("Final Assessment", className="mb-2 text-danger", style={"fontSize": "0.95rem"}),
                html.Div(id='env-final-decision-output', className="mb-2"),
                html.H6("Risk Score Details", className="mt-2 mb-1 text-info small", style={"fontSize": "0.85rem"}),
                html.Div(id='env-score-details-output', className="alert alert-light border mb-2 small", style={"padding": "0.5rem", "fontSize": "0.8rem"}),
                html.H6("Cost Details", className="mt-2 mb-1 text-info small", style={"fontSize": "0.85rem"}),
                html.Div(id='env-cost-details-output', className="alert alert-light border mb-2 small", style={"padding": "0.5rem", "fontSize": "0.8rem"}),
                html.Hr(className="my-2"),
                html.H6("Required Treatment & Recommendations", className="mt-2 mb-2 text-info", style={"fontSize": "0.95rem"}),
                html.Div(id='env-treatment-summary-output', className="mb-2"),
                html.H6("Recommendations by Risk Factor", className="mt-2 mb-1 text-secondary small", style={"fontSize": "0.85rem"}),
                html.Ul(id='env-recommendations-list', className="list-group small", style={"fontSize": "0.8rem"}),
            ], width=12, lg=5, style={
                "position": "sticky",
                "top": "20px",
                "align-self": "start"
            }),
        ]),
        *question_tooltips,
        dbc.Tooltip(
            "Reference treatment technologies and indicative unit costs",
            target="env-treatment-appendix-table",
            placement="top",
        ),
        dbc.Tooltip(
            "Composite suitability score from the screening questions",
            target="env-score-gauge",
            placement="top",
        ),
        dbc.Tooltip(
            "Order-of-magnitude treatment cost index from selected technologies",
            target="env-cost-gauge",
            placement="top",
        ),
            ],
            className="water-quality-tab",
        ),
    ]


def create_environmental_considerations_content():
    """Create the Environmental Considerations content (sub-tab 4.2)."""
    gemini_api_key = _normalize_stored_string(dash_storage.get_data("gemini_api_key"))
    gemini_api_file = _normalize_stored_string(dash_storage.get_data("gemini_api_file"))
    if not gemini_api_file:
        gemini_api_file = r"C:\workspace\api\gemini.txt"
    project_location = str(dash_storage.get_data("project_location") or "").strip()

    return [
        dbc.Alert([
            html.Div("Choose how to generate MAR environmental factors:", className="fw-bold mb-2"),
            html.Ul([
                html.Li([
                    html.Span("Option 1 — ", className="fw-bold"),
                    html.Span(
                        "Gemini with personal API",
                        className="fw-bold text-success",
                    ),
                    html.Span(
                        ": enter your API key (right), set location, and click ",
                        className="text-muted",
                    ),
                    html.Span("Generate MAR Factors", className="fw-semibold"),
                    html.Span(".", className="text-muted"),
                ], className="mb-2"),
                html.Li([
                    html.Span("Option 2 — ", className="fw-bold"),
                    html.Span(
                        "Create the prompt and use it in your chosen AI model",
                        className="fw-bold text-primary",
                    ),
                    html.Span(
                        ": click ",
                        className="text-muted",
                    ),
                    html.Span("Build Prompt", className="fw-semibold"),
                    html.Span(", then ", className="text-muted"),
                    html.Span("Copy Prompt", className="fw-semibold"),
                    html.Span(
                        " and paste into ChatGPT, Claude, Copilot, or another tool.",
                        className="text-muted",
                    ),
                ], className="mb-0"),
            ], className="mb-0 ps-3"),
        ], color="light", className="border mb-3 py-2"),
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(
                        "AI-Generated MAR Factors",
                        className="fw-bold bg-primary text-white py-2",
                    ),
                    dbc.CardBody([
                        html.Label("Location:", className="fw-bold small mb-1"),
                        dbc.InputGroup([
                            dbc.Input(
                                id="mar-location-input",
                                type="text",
                                value=project_location,
                                placeholder="City, State or City, Country",
                                size="sm",
                            ),
                            dbc.Button(
                                [
                                    html.I(className="fas fa-brain me-1"),
                                    "Generate MAR Factors",
                                ],
                                id="generate-mar-factors-btn",
                                color="success",
                                size="sm",
                                n_clicks=0,
                                title="Call Gemini to build an environmental factors checklist",
                            ),
                        ], className="mb-1"),
                        html.Small(
                            "Populated from Overview Project Location; edit if needed.",
                            className="text-muted d-block mb-2",
                        ),
                        dcc.Loading(
                            id="mar-factors-loading",
                            type="circle",
                            color="#198754",
                            parent_style={"minHeight": "80px"},
                            children=html.Div(
                                id="mar-factors-table-container",
                                className="mb-3",
                            ),
                        ),
                        dbc.Row([
                            dbc.Col([
                                html.Label("Model:", className="fw-bold small mb-1"),
                                dcc.Dropdown(
                                    id="gemini-model-select",
                                    options=[
                                        {"label": "gemini-2.5-flash", "value": "gemini-2.5-flash"},
                                        {"label": "gemini-1.5-flash", "value": "gemini-1.5-flash"},
                                        {"label": "gemini-1.5-pro", "value": "gemini-1.5-pro"},
                                        {"label": "gemini-pro", "value": "gemini-pro"},
                                    ],
                                    value=dash_storage.get_data("gemini_model") or "gemini-2.5-flash",
                                    clearable=False,
                                ),
                            ], xs=12, md=6),
                            dbc.Col([
                                html.Label("Temperature:", className="fw-bold small mb-1"),
                                dcc.Slider(
                                    id="temperature-slider",
                                    min=0.0,
                                    max=2.0,
                                    step=0.1,
                                    value=float(dash_storage.get_data("gemini_temperature") or 0.5),
                                    marks={0.0: "0", 1.0: "1", 2.0: "2"},
                                    tooltip={"placement": "bottom", "always_visible": False},
                                ),
                                html.Div(id="temperature-value-display", className="mt-1"),
                            ], xs=12, md=6, className="mt-2 mt-md-0"),
                        ], className="g-2"),
                    ], className="p-3"),
                ]),
            ], xs=12, lg=7, className="mb-3 mb-lg-0"),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(
                        "Gemini API Settings",
                        className="fw-bold bg-primary text-white py-2",
                    ),
                    dbc.CardBody([
                        html.Label("Gemini API Key:", className="fw-bold small mb-1"),
                        dbc.Input(
                            id="gemini-api-key-input",
                            type="password",
                            value=gemini_api_key,
                            placeholder="Enter API key (optional if file/env set)",
                            debounce=True,
                            size="sm",
                            className="mb-1",
                        ),
                        html.Small(
                            "Optional if using Gemini here. Stored locally. "
                            "Get a key at aistudio.google.com/apikey",
                            className="text-muted d-block mb-3",
                        ),
                        html.Label("API Key File Path:", className="fw-bold small mb-1"),
                        dbc.Input(
                            id="gemini-api-file-input",
                            type="text",
                            value=gemini_api_file,
                            placeholder=r"C:\workspace\api\gemini.txt",
                            debounce=True,
                            size="sm",
                            className="mb-1",
                        ),
                        html.Small(
                            "Fallback file if key is not entered above.",
                            className="text-muted",
                        ),
                    ], className="p-3"),
                ], className="h-100"),
            ], xs=12, lg=5, className="mb-3 mb-lg-0"),
        ], className="mb-3 g-3 align-items-stretch"),
        dbc.Card([
            dbc.CardHeader(
                "Use Your Own AI Model",
                className="fw-bold bg-primary text-white py-2",
            ),
            dbc.CardBody([
                html.Small(
                    "Build the same prompt used for Gemini, then copy and paste it into "
                    "ChatGPT, Claude, Copilot, or another AI tool if you prefer not to use Gemini.",
                    className="text-muted d-block mb-2",
                ),
                dbc.ButtonGroup([
                    dbc.Button(
                        [html.I(className="fas fa-file-alt me-1"), "Build Prompt"],
                        id="build-mar-factors-prompt-btn",
                        color="outline-primary",
                        size="sm",
                        n_clicks=0,
                    ),
                    dbc.Button(
                        [html.I(className="fas fa-copy me-1"), "Copy Prompt"],
                        id="copy-mar-factors-prompt-btn",
                        color="outline-secondary",
                        size="sm",
                        n_clicks=0,
                    ),
                ], className="mb-2"),
                html.Div(id="mar-prompt-feedback", className="mb-2"),
                dcc.Textarea(
                    id="mar-factors-prompt-display",
                    value="",
                    readOnly=True,
                    placeholder="Click Build Prompt to generate the text for your location…",
                    style={
                        "width": "100%",
                        "minHeight": "180px",
                        "fontFamily": "monospace",
                        "fontSize": "12px",
                        "resize": "vertical",
                    },
                ),
            ], className="p-3"),
        ], className="mb-3"),
        dbc.Tooltip(
            "Google Gemini API key (stored locally for this session)",
            target="gemini-api-key-input",
            placement="top",
        ),
        dbc.Tooltip(
            "Optional text file on disk containing the API key",
            target="gemini-api-file-input",
            placement="top",
        ),
        dbc.Tooltip(
            "Gemini model used for environmental factor generation",
            target="gemini-model-select",
            placement="top",
        ),
        dbc.Tooltip(
            "Sampling temperature: lower is more deterministic; higher is more varied",
            target="temperature-slider",
            placement="top",
        ),
        dbc.Tooltip(
            "Plain-language place name sent to the AI",
            target="mar-location-input",
            placement="top",
        ),
        dbc.Tooltip(
            "Create the MAR factors prompt for the current location",
            target="build-mar-factors-prompt-btn",
            placement="top",
        ),
        dbc.Tooltip(
            "Copy the prompt below to your clipboard",
            target="copy-mar-factors-prompt-btn",
            placement="top",
        ),
    ]


def create_environmental_impact_content():
    """Create the Environmental Impact tab content (Water Quality and Geochemistry)."""
    return create_water_quality_content()
