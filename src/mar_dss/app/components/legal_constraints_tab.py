"""
Legal Constraints tab component.

Managed Aquifer Recharge (MAR) legal and regulatory feasibility decision tree:
- Project/Jurisdiction screen
- A) Site feasibility
- B) Water source feasibility
- C) Water quality feasibility

The project is feasible only if all three branches are Feasible or Conditionally feasible.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html
from mar_dss.app.utils.tab_tooltips import tab_nav_id, tab_tooltip
from mar_dss.app.components.environmental_impact_tab import (
    create_environmental_considerations_content,
)
from mar_dss.app.callbacks.ai_environment import _normalize_stored_string
import mar_dss.app.utils.data_storage as dash_storage


def _section_card(header_text, body_children):
    return dbc.Card(
        [
            dbc.CardHeader(header_text, className="fw-bold bg-light"),
            dbc.CardBody(body_children),
        ],
        className="mb-3",
        style={
            "box-shadow": "0 4px 8px 0 rgba(0,0,0,0.1)",
            "transition": "0.3s",
            "border-left": "5px solid #0d6efd",
        },
    )


def _radio(id_, options, value):
    return dcc.RadioItems(
        id=id_,
        options=[{"label": o, "value": o} for o in options],
        value=value,
        className="d-flex flex-column",
        labelStyle={"display": "block", "margin-bottom": "8px"},
    )


def _pill(label, color="secondary"):
    return html.Span(label, className=f"badge bg-{color} ms-2")


def create_basic_regulation_feasibility_content():
    """Create the Basic Regulation Feasibility content (sub-tab 1)."""
    return [
        dbc.Row(
            [
                # Left: Inputs
                dbc.Col(
                    [
                        html.H3("Legal & Regulatory Feasibility Inputs", className="mb-4 text-primary"),
                        dbc.Alert(
                            [
                                html.I(className="fas fa-triangle-exclamation me-2"),
                                html.Strong("Legal disclaimer: "),
                                "This decision aid is for informational purposes only and does not constitute legal advice. ",
                                "Regulatory requirements vary by jurisdiction and project specifics. ",
                                "Additional review may be required to confirm local, state, Tribal, and federal laws, permits, and approvals.",
                            ],
                            color="danger",
                            className="mb-4",
                        ),

                        # 0) Project/Jurisdiction screen
                        _section_card(
                            "0) Project/Jurisdiction Screen",
                            [
                                html.P("(Federal nexus) Does your project has a direct federal connection such that federal environmental laws and reviews are triggered?"),
                                _radio(
                                    "legal-proj-federal-nexus",
                                    ["No", "Yes - NEPA (National Environmental Policy Act) / ESA (Endangered Species Act) / NHPA (National Historic Preservation Act) likely"],
                                    "No",
                                ),
                                html.Hr(),
                                html.P("Tribal or interstate context?"),
                                _radio(
                                    "legal-proj-tribal-interstate",
                                    ["None", "Tribal lands/resources", "Interstate compact", "Both"],
                                    "None",
                                ),
                            ],
                        ),

                        # A) Site feasibility
                        _section_card(
                            "A) Site Feasibility (Location, Land Rights, Environmental Review)",
                            [
                                html.P("A1. Site control and access"),
                                _radio(
                                    "legal-site-control",
                                    ["Have site control", "Can secure site control", "Cannot secure site control (Prohibited)"],
                                    "Have site control",
                                ),
                                html.Hr(),
                                html.P("A2. Land use and local approvals (zoning/conditional use/building/floodplain)"),
                                _radio(
                                    "legal-site-zoning",
                                    ["Allowed", "Conditionally allowed (permit/variance)", "Prohibited (no variance)"],
                                    "Allowed",
                                ),
                                html.Hr(),
                                html.P("A3. Waters/wetlands impacts (CWA (Clean Water Act) §§404/401; RHA (Rivers and Harbors Act) §10)"),
                                _radio(
                                    "legal-site-wetlands",
                                    ["No impacts", "General permit likely", "Individual permit feasible", "Permit unlikely (Prohibited)"],
                                    "No impacts",
                                ),
                                html.Hr(),
                                html.P("A4. Sensitive resources (ESA/cultural/historic/critical areas)"),
                                _radio(
                                    "legal-site-sensitive",
                                    ["None", "Present - mitigable", "Present - unmitigable (Prohibited)"],
                                    "None",
                                ),
                                html.Hr(),
                                html.P("A5. Public lands/federal facilities authorizations"),
                                _radio(
                                    "legal-site-public-lands",
                                    ["Not applicable", "Authorizations obtainable", "Authorizations unobtainable (Prohibited)"],
                                    "Not applicable",
                                ),
                                html.Hr(),
                                html.P("A6. Dam safety/geotechnical constraints"),
                                _radio(
                                    "legal-site-dams",
                                    ["Not applicable", "Approvable with conditions", "Not approvable (Prohibited)"],
                                    "Not applicable",
                                ),
                                html.Hr(),
                                html.P("A7. Subsidence/seismic constraints"),
                                _radio(
                                    "legal-site-seismic",
                                    ["Compliant", "Mitigable", "Noncompliant (Prohibited)"],
                                    "Compliant",
                                ),
                            ],
                        ),

                        # B) Water source feasibility
                        _section_card(
                            "B) Water Source Feasibility (Rights, Compacts, Conveyance)",
                            [
                                html.P("B1. Legal right/entitlement to source (incl. storage for recharge)"),
                                _radio(
                                    "legal-src-right",
                                    ["Valid right/contract", "Obtainable without injury", "No path to a valid right (Prohibited)"],
                                    "Valid right/contract",
                                ),
                                html.Hr(),
                                html.P("B2. Recharge authorization, accounting, and recovery (state MAR (Managed Aquifer Recharge)/ASR (Aquifer Storage and Recovery) framework)"),
                                _radio(
                                    "legal-src-accounting",
                                    ["Authorized", "Authorizable with conditions", "No statutory/administrative pathway (Prohibited)"],
                                    "Authorized",
                                ),
                                html.Hr(),
                                html.P("B3. Interstate compact/delivery compliance"),
                                _radio(
                                    "legal-src-compact",
                                    ["Not applicable", "Compliant", "Noncompliant (Prohibited)"],
                                    "Not applicable",
                                ),
                                html.Hr(),
                                html.P("B4. Source-specific compliance feasible?"),
                                dcc.Dropdown(
                                    id="legal-src-type",
                                    options=[
                                        {"label": "Stormwater/Urban Runoff", "value": "stormwater"},
                                        {"label": "Surface Water", "value": "surface"},
                                        {"label": "Recycled Water", "value": "recycled"},
                                        {"label": "Agricultural Drainage/Return Flows", "value": "ag"},
                                        {"label": "Other/Industrial", "value": "other"},
                                    ],
                                    value="stormwater",
                                    clearable=False,
                                    style={"maxWidth": "420px"},
                                ),
                                _radio(
                                    "legal-src-type-feasible",
                                    ["Feasible", "Feasible with conditions", "Not feasible (Prohibited)"],
                                    "Feasible",
                                ),
                                html.Hr(),
                                html.P("B5. Conveyance/wheeling agreements (ditches/canals/pipelines)"),
                                _radio(
                                    "legal-src-conveyance",
                                    ["Available", "Negotiable", "Unavailable (Prohibited)"],
                                    "Available",
                                ),
                            ],
                        ),

                        # C) Water quality feasibility
                        _section_card(
                            "C) Water Quality Feasibility (UIC, Anti-degradation, Standards)",
                            [
                                html.P("C1. Recharge method"),
                                dcc.Dropdown(
                                    id="legal-qual-method",
                                    options=[
                                        {"label": "Infiltration (basins/galleries)", "value": "infiltration"},
                                        {"label": "Direct Injection (wells)", "value": "injection"},
                                        {"label": "Both / To be determined", "value": "both"},
                                    ],
                                    value="infiltration",
                                    clearable=False,
                                    style={"maxWidth": "420px"},
                                ),
                                html.Br(),
                                html.P("C2. UIC (Underground Injection Control) Class V (SDWA (Safe Drinking Water Act)) or equivalent permit feasibility"),
                                _radio(
                                    "legal-qual-uic",
                                    ["Not applicable", "Feasible", "Not feasible (Prohibited)"],
                                    "Not applicable",
                                ),
                                html.Hr(),
                                html.P("C3. Receiving aquifer a USDW (Underground Source of Drinking Water) or planned potable use?"),
                                _radio(
                                    "legal-qual-usdw",
                                    ["No", "Yes - MCLs/no endangerment apply"],
                                    "No",
                                ),
                                html.Br(),
                                html.P("C4. Ability to meet SDWA (Safe Drinking Water Act) MCLs (Maximum Contaminant Levels)/no-endangerment and state reuse criteria (if applicable)"),
                                _radio(
                                    "legal-qual-mcls",
                                    ["Assured", "Achievable with treatment/monitoring", "Cannot be met (Prohibited)"],
                                    "Assured",
                                ),
                                html.Hr(),
                                html.P("C5. Anti-degradation/TMDL (Total Maximum Daily Load) compliance"),
                                _radio(
                                    "legal-qual-antideg",
                                    ["No lowering", "Lowering justified with mitigation", "Likely with studies", "Not compliant (Prohibited)"],
                                    "No lowering",
                                ),
                                html.Hr(),
                                html.P("C6. Geochemical compatibility (mobilization/precipitation risks)"),
                                _radio(
                                    "legal-qual-compat",
                                    ["Acceptable", "Mitigable with treatment/modeling", "Not acceptable (Prohibited)"],
                                    "Acceptable",
                                ),
                                html.Hr(),
                                html.P("C7. CECs (Constituents of Emerging Concern)/PFAS (Per- and Polyfluoroalkyl Substances) and monitoring orders compliance"),
                                _radio(
                                    "legal-qual-cecs",
                                    ["Compliant", "Compliant with advanced treatment", "Not compliant (Prohibited)"],
                                    "Compliant",
                                ),
                                html.Hr(),
                                html.P("C8. Residuals handling (backwash/brine) permitting"),
                                _radio(
                                    "legal-qual-residuals",
                                    ["Permittable", "Permittable with conditions", "Not permittable (Prohibited)"],
                                    "Permittable",
                                ),
                                html.Hr(),
                                html.P("C9. Well construction & monitoring plan (state standards/UIC)"),
                                _radio(
                                    "legal-qual-wells",
                                    ["Compliant", "Compliant with conditions", "Noncompliant (Prohibited)"],
                                    "Compliant",
                                ),
                            ],
                        ),
                    ],
                    width=12,
                    lg=8,
                    style={
                        "max-height": "calc(100vh - 200px)",
                        "overflow-y": "auto",
                        "overflow-x": "hidden",
                        "padding-right": "10px",
                    },
                ),

                # Right: Outputs
                dbc.Col(
                    [
                        html.H3("Legal/Regulatory Decision", className="mb-4 text-danger"),
                        html.Div(id="legal-final-decision-output", className="mb-4"),

                        html.H4("Regulatory Risk Score", className="mt-4 mb-3 text-info"),
                        dcc.Graph(
                            id="legal-risk-gauge",
                            config={"displayModeBar": False, "responsive": True},
                            style={"height": "250px", "width": "100%", "minHeight": "250px"},
                        ),
                        html.Div(id="legal-risk-details-output", className="alert alert-light border"),

                        html.Hr(),
                        html.H4("Branch Results", className="mt-4 mb-3 text-secondary"),
                        _section_card("A) Site Branch Result", [html.Div(id="legal-branch-site-output")]),
                        _section_card("B) Water Source Branch Result", [html.Div(id="legal-branch-source-output")]),
                        _section_card("C) Water Quality Branch Result", [html.Div(id="legal-branch-quality-output")]),

                        html.Hr(),
                        html.H4("Required Permits & Approvals (Checklist)", className="mt-4 mb-3 text-secondary"),
                        html.Ul(id="legal-required-permits-list", className="list-group"),
                    ],
                    width=12,
                    lg=4,
                    style={"position": "sticky", "top": "20px", "align-self": "start"},
                ),
            ]
        ),
        dbc.Tooltip(
            "Source-water category for applying source-specific regulatory pathways",
            target="legal-src-type",
            placement="top",
        ),
        dbc.Tooltip(
            "Primary MAR delivery mechanism affecting UIC and construction rules",
            target="legal-qual-method",
            placement="top",
        ),
        dbc.Tooltip(
            "Summary regulatory risk index from your feasibility questionnaire",
            target="legal-risk-gauge",
            placement="top",
        ),
    ]


def create_ai_regulations_permits_content():
    """Create the AI-Powered Regulations and Permits content (sub-tab 2)."""
    gemini_api_key = _normalize_stored_string(dash_storage.get_data("gemini_api_key"))
    gemini_api_file = _normalize_stored_string(dash_storage.get_data("gemini_api_file"))
    if not gemini_api_file:
        gemini_api_file = r"C:\workspace\api\gemini.txt"
    project_location = _normalize_stored_string(dash_storage.get_data("project_location"))

    return [
        dbc.Alert([
            html.Div("Choose how to generate MAR regulatory and permitting requirements:", className="fw-bold mb-2"),
            html.Ul([
                html.Li([
                    html.Span("Option 1 — ", className="fw-bold"),
                    html.Span("Gemini with personal API", className="fw-bold text-success"),
                    html.Span(": enter your API key (right), set location, and click ", className="text-muted"),
                    html.Span("Generate Regulations Matrix", className="fw-semibold"),
                    html.Span(".", className="text-muted"),
                ], className="mb-2"),
                html.Li([
                    html.Span("Option 2 — ", className="fw-bold"),
                    html.Span(
                        "Create the prompt and use it in your chosen AI model",
                        className="fw-bold text-primary",
                    ),
                    html.Span(": click ", className="text-muted"),
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
                        "AI-Generated MAR Regulations & Permits",
                        className="fw-bold bg-primary text-white py-2",
                    ),
                    dbc.CardBody([
                        html.Label("Location:", className="fw-bold small mb-1"),
                        dbc.InputGroup([
                            dbc.Input(
                                id="mar-regs-location-input",
                                type="text",
                                value=project_location,
                                placeholder="City, State or City, Country",
                                size="sm",
                            ),
                            dbc.Button(
                                [
                                    html.I(className="fas fa-gavel me-1"),
                                    "Generate Regulations Matrix",
                                ],
                                id="generate-mar-regs-btn",
                                color="success",
                                size="sm",
                                n_clicks=0,
                                title="Call Gemini to build a regulatory and permitting matrix",
                            ),
                        ], className="mb-1"),
                        html.Small(
                            "Populated from Overview Project Location; edit if needed.",
                            className="text-muted d-block mb-2",
                        ),
                        dcc.Loading(
                            id="mar-regs-loading",
                            type="circle",
                            color="#198754",
                            parent_style={"minHeight": "80px"},
                            children=html.Div(
                                id="mar-regs-table-container",
                                className="mb-3",
                            ),
                        ),
                        dbc.Row([
                            dbc.Col([
                                html.Label("Model:", className="fw-bold small mb-1"),
                                dcc.Dropdown(
                                    id="mar-regs-gemini-model-select",
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
                                    id="mar-regs-temperature-slider",
                                    min=0.0,
                                    max=2.0,
                                    step=0.1,
                                    value=float(dash_storage.get_data("gemini_temperature") or 0.5),
                                    marks={0.0: "0", 1.0: "1", 2.0: "2"},
                                    tooltip={"placement": "bottom", "always_visible": False},
                                ),
                                html.Div(id="mar-regs-temperature-display", className="mt-1"),
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
                            id="mar-regs-gemini-api-key-input",
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
                            id="mar-regs-gemini-api-file-input",
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
                        id="build-mar-regs-prompt-btn",
                        color="outline-primary",
                        size="sm",
                        n_clicks=0,
                    ),
                    dbc.Button(
                        [html.I(className="fas fa-copy me-1"), "Copy Prompt"],
                        id="copy-mar-regs-prompt-btn",
                        color="outline-secondary",
                        size="sm",
                        n_clicks=0,
                    ),
                ], className="mb-2"),
                html.Div(id="mar-regs-prompt-feedback", className="mb-2"),
                dcc.Textarea(
                    id="mar-regs-prompt-display",
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
            target="mar-regs-gemini-api-key-input",
            placement="top",
        ),
        dbc.Tooltip(
            "Optional text file on disk containing the API key",
            target="mar-regs-gemini-api-file-input",
            placement="top",
        ),
        dbc.Tooltip(
            "Gemini model used for regulatory matrix generation",
            target="mar-regs-gemini-model-select",
            placement="top",
        ),
        dbc.Tooltip(
            "Sampling temperature: lower is more deterministic; higher is more varied",
            target="mar-regs-temperature-slider",
            placement="top",
        ),
        dbc.Tooltip(
            "Plain-language place name sent to the AI",
            target="mar-regs-location-input",
            placement="top",
        ),
        dbc.Tooltip(
            "Create the MAR regulations prompt for the current location",
            target="build-mar-regs-prompt-btn",
            placement="top",
        ),
        dbc.Tooltip(
            "Copy the prompt below to your clipboard",
            target="copy-mar-regs-prompt-btn",
            placement="top",
        ),
    ]


def create_legal_constraints_content():
    """Create the Legal Constraints tab content with sub-tabs."""
    return [
        html.Div(
            [
                dbc.Tabs(
                    [
                        dbc.Tab(
                            label="(1) Basic Regulation Feasibility",
                    id=tab_nav_id("basic-regulation-tab"),
                            tab_id="basic-regulation-tab",
                            children=create_basic_regulation_feasibility_content(),
                        ),
                        dbc.Tab(
                            label="(2) AI-Powered Regulations and Permits",
                            id=tab_nav_id("ai-regulations-permits-tab"),
                            tab_id="ai-regulations-permits-tab",
                            children=create_ai_regulations_permits_content(),
                        ),
                        dbc.Tab(
                            label="(3) AI-Powered Environmental, Ecological, and Cultural Factors",
                            id=tab_nav_id("environmental-considerations-tab"),
                            tab_id="environmental-considerations-tab",
                            children=create_environmental_considerations_content(),
                        ),
                    ],
                    id="legal-subtabs",
                    active_tab="basic-regulation-tab",
                ),
                tab_tooltip(
                    "basic-regulation-tab",
                    "Structured regulatory decision tree: site, water source, and water quality feasibility",
                ),
                tab_tooltip(
                    "ai-regulations-permits-tab",
                    "AI-generated regulatory requirements, permits, agency coordination, and legal considerations for your site",
                ),
                tab_tooltip(
                    "environmental-considerations-tab",
                    "AI-generated environmental, ecological, and cultural MAR factors for your site",
                ),
            ]
        )
    ]
