"""
Legal Constraints tab component.

(5.1) Regulatory considerations: informational checklist with expandable detail.
(5.2) AI-powered regulatory and permitting factors.
(5.3) AI-powered environmental, ecological, and cultural factors.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from mar_dss.app.components.environmental_impact_tab import (
    create_environmental_considerations_content,
)
from mar_dss.app.utils.tab_tooltips import tab_nav_id, tab_tooltip

# Informational considerations (formerly questionnaire topics). Not scored.
# Each item: (title, why_it_matters, example_obstacles_tuple)
REGULATORY_CONSIDERATIONS = (
    (
        "Site Feasibility",
        (
            (
                "Site control and access (ownership, leases, easements)",
                "MAR (managed aquifer recharge) facilities need long-term, reliable "
                "control of the land and access routes for construction, operations, "
                "monitoring wells, and emergency response. Incomplete ownership, short "
                "leases, or missing easements can stop a project even when "
                "hydrogeology is favorable.",
                (
                    "A proposed spreading basin sits on leased farmland whose "
                    "lease expires in five years and cannot be extended for "
                    "infrastructure, so financing and permits stall.",
                    "An injection well site is reachable only across a private "
                    "parcel; the landowner refuses a permanent access easement "
                    "for drilling and maintenance trucks.",
                    "Monitoring wells required by regulators would fall outside "
                    "the owned parcel, and neighboring owners will not grant "
                    "entry or well easements.",
                ),
            ),
            (
                "Land use and local approvals (zoning, conditional use, building, floodplain)",
                "Local zoning and building rules determine whether recharge "
                "basins, wells, berms, and treatment yards are allowed uses. "
                "Floodplain or conditional-use constraints can add years of "
                "hearings, redesign, or outright denial.",
                (
                    "A city zones the preferred basin site as residential and "
                    "denies a conditional-use permit for large open-water "
                    "recharge ponds near homes.",
                    "County floodplain rules prohibit fill and berms needed for "
                    "basin freeboard, forcing relocation to a less permeable "
                    "site.",
                    "Building permits for wellheads and electrical gear are "
                    "delayed because the site lacks compliant road access and "
                    "fire-flow infrastructure.",
                ),
            ),
            (
                "Waters and wetlands impacts (Clean Water Act §§404/401; Rivers and Harbors Act §10)",
                "If basins, pipelines, or outfalls affect wetlands, streams, or "
                "navigable waters, federal and state water-quality certifications "
                "may be required under the Clean Water Act—for example §404 "
                "(dredge/fill in waters of the United States), §401 (state "
                "water-quality certification), and Rivers and Harbors Act §10 "
                "(structures or work in navigable waters). Avoidance, mitigation, "
                "and seasonal work windows can dominate schedule and cost.",
                (
                    "Basin excavation would fill jurisdictional wetlands; a "
                    "Clean Water Act §404 permit is denied or requires mitigation "
                    "that exceeds project budget.",
                    "A diversion structure in a regulated stream triggers Rivers "
                    "and Harbors Act §10 review and multi-year agency consultation.",
                    "Clean Water Act §401 water-quality certification is withheld "
                    "until extensive turbidity and habitat studies are completed.",
                ),
            ),
            (
                "Sensitive resources (endangered species, cultural/historic, critical areas)",
                "Protected species, cultural sites, and critical habitat can "
                "restrict ground disturbance, seasonal construction, and long-term "
                "operations. Early surveys reduce the risk of late redesign or "
                "project stoppage.",
                (
                    "Basin construction coincides with nesting season for a "
                    "listed bird; work is barred for months each year, breaking "
                    "the recharge construction schedule.",
                    "A cultural resource survey finds eligible historic "
                    "features; agencies require avoidance that eliminates the "
                    "best infiltration footprint.",
                    "Critical aquifer recharge or habitat overlays impose "
                    "buffers that shrink usable basin area below design need.",
                ),
            ),
            (
                "Public lands and federal facilities authorizations",
                "Projects on federal, military, or other public lands typically "
                "need special-use permits, NEPA (National Environmental Policy "
                "Act) review, or host-agency approval. Authorization timelines "
                "and mission conflicts can block otherwise feasible sites.",
                (
                    "A Navy or BLM (Bureau of Land Management) special-use "
                    "authorization is denied because recharge ponds conflict "
                    "with training or conservation missions.",
                    "Federal land managers require multi-year NEPA "
                    "(National Environmental Policy Act) review before "
                    "allowing well drilling, delaying water-availability "
                    "targets.",
                    "A right-of-way across public land for a conveyance pipeline "
                    "is refused, isolating the only suitable recharge area.",
                ),
            ),
            (
                "Dam safety and geotechnical constraints",
                "Berms, dikes, and large ponds may be regulated as dams. "
                "Poor soils, liquefaction risk, or inadequate freeboard design "
                "can force costly redesign or make a basin concept infeasible.",
                (
                    "State dam safety classifies basin embankments as "
                    "jurisdictional dams requiring engineered spillways the "
                    "sponsor cannot fund.",
                    "Soft or collapsible soils fail slope-stability criteria, so regulators reject the basin geometry.",
                    "Geotechnical investigations show high liquefaction "
                    "potential under seismic loading, blocking embankment "
                    "approval.",
                ),
            ),
            (
                "Subsidence and seismic constraints",
                "Recharge and recovery can interact with land subsidence and "
                "seismic hazards. Agencies may limit rates, volumes, or well "
                "locations where ground movement or fault rupture risk is high.",
                (
                    "A basin near an active fault zone is rejected because "
                    "embankment failure risk under earthquake loading is "
                    "unacceptable.",
                    "Historic subsidence makes regulators require intensive "
                    "geodetic monitoring that the project cannot support.",
                    "Injection near critical infrastructure is limited because "
                    "of induced seismicity or ground-movement concerns.",
                ),
            ),
        ),
    ),
    (
        "Water Source Feasibility",
        (
            (
                "Legal right or entitlement to the source water (including storage for recharge)",
                "Without a clear legal right to divert, store, and recharge "
                "water, a MAR project cannot operate. Entitlements must cover "
                "timing, place of use, and often the storage of water "
                "underground.",
                (
                    "Surface-water rights are junior and rarely available in wet years when recharge is needed most.",
                    "A municipal allotment cannot be used for underground "
                    "storage because the place-of-use description excludes "
                    "recharge facilities.",
                    "Stored-water credits are disputed, so lenders will not finance recovery wells.",
                ),
            ),
            (
                "Recharge authorization, accounting, and recovery (state managed aquifer recharge / aquifer storage "
                "and recovery framework)",
                "Many states require explicit authorization to recharge and "
                "later recover water under an MAR (managed aquifer recharge) or "
                "ASR (aquifer storage and recovery) framework, plus accounting "
                "rules that define credits, losses, and priority. Missing "
                "framework approvals can strand invested infrastructure.",
                (
                    "The state does not have a formal ASR (aquifer storage and "
                    "recovery) / MAR (managed aquifer recharge) "
                    "storage-and-recovery accounting system, so even if water is "
                    "recharged, the project may have no legal right to recover it "
                    "later as credited project water.",
                    "Credit calculations assume high losses, making recovered yield too small to justify cost.",
                    "Recovery is limited to the same year as recharge, eliminating multi-year drought buffering.",
                ),
            ),
            (
                "Interstate compact or delivery compliance",
                "Projects that use water subject to interstate compacts or "
                "delivery contracts must stay within allocation and accounting "
                "rules. Noncompliance can halt diversions or trigger "
                "enforcement.",
                (
                    "Recharge diversions would violate compact delivery schedules to a downstream state.",
                    "Contract water may only be used for irrigation, not "
                    "underground storage for later municipal recovery.",
                    "Compact accounting cannot track banked water, so the project cannot claim stored credits.",
                ),
            ),
            (
                "Source-specific compliance (stormwater, surface water, recycled water, agricultural drainage, or "
                "other)",
                "Each source type carries distinct permitting, treatment, and "
                "monitoring expectations. Choosing a source that cannot meet "
                "those rules blocks the recharge pathway. For stormwater, an "
                "MS4 (Municipal Separate Storm Sewer System) is a public "
                "storm-drain network regulated under a Clean Water Act permit "
                "that often limits untreated discharges—including to "
                "infiltration or recharge facilities.",
                (
                    "Local MS4 (Municipal Separate Storm Sewer System) or "
                    "industrial discharge rules prohibit sending untreated "
                    "runoff to infiltration basins.",
                    "Recycled-water regulations require advanced treatment "
                    "before injection that the utility cannot build.",
                    "Agricultural drain water exceeds salinity or pesticide limits for recharge under state policy.",
                ),
            ),
            (
                "Conveyance and wheeling agreements (ditches, canals, pipelines)",
                "A wheeling agreement is a contract that lets you move your water "
                "through someone else’s canal, ditch, or pipeline—usually for a fee "
                "and under capacity and scheduling rules. Moving water to the "
                "recharge site often depends on such third-party conveyance. Without "
                "capacity and wheeling rights, physically available water cannot "
                "reach the project.",
                (
                    "A canal company refuses a wheeling agreement during peak "
                    "irrigation season when surplus water is available.",
                    "Pipeline capacity is fully subscribed; no interruptible capacity remains for recharge pulses.",
                    "Right-of-way for a new lateral cannot be obtained across multiple private parcels.",
                ),
            ),
        ),
    ),
    (
        "Water Quality Feasibility",
        (
            (
                "Recharge method implications (infiltration, injection, or both)",
                "Infiltration and injection face different permit pathways, "
                "treatment expectations, and aquifer risks. Method choice "
                "drives regulatory difficulty as much as hydrogeology does.",
                (
                    "Surface infiltration is preferred hydrologically, but "
                    "land use only allows small well pads suited to injection.",
                    "Injection is proposed where the aquifer is a drinking-water "
                    "source, triggering stricter UIC (Underground Injection "
                    "Control) and treatment rules than basin recharge would "
                    "require.",
                    "A dual method design creates two permit tracks that the "
                    "sponsor cannot staff or fund simultaneously.",
                ),
            ),
            (
                "Underground Injection Control Class V (Safe Drinking Water Act) or equivalent permit feasibility",
                "Injection wells typically need a UIC (Underground Injection "
                "Control) Class V permit under the Safe Drinking Water Act (or "
                "a state-equivalent authorization) demonstrating no endangerment "
                "of underground sources of drinking water. Permit denial or "
                "conditions can make injection infeasible.",
                (
                    "UIC (Underground Injection Control) reviewers reject the "
                    "injection proposal because source water quality cannot meet "
                    "no-endangerment demonstrations.",
                    "Permit conditions require continuous treatment and "
                    "shutdown criteria that exceed O&M (operations and "
                    "maintenance) capacity.",
                    "Well construction standards for Class V cannot be met "
                    "in the local geology without prohibitive cost.",
                ),
            ),
            (
                "Receiving aquifer as an underground source of drinking water or planned potable use",
                "If the receiving aquifer is or will be used for drinking water—"
                "including designation as a USDW (underground source of drinking "
                "water)—regulators apply stricter quality and monitoring "
                "standards. That can require treatment levels the project cannot "
                "deliver.",
                (
                    "The target aquifer is classified as a USDW (underground "
                    "source of drinking water); untreated stormwater recharge "
                    "is prohibited.",
                    "A future municipal well field is planned downgradient, "
                    "so agencies impose near-drinking-water standards on "
                    "recharge water.",
                    "Anti-degradation policy forbids any increase in key contaminants in a potable aquifer.",
                ),
            ),
            (
                "Ability to meet Safe Drinking Water Act maximum contaminant levels / no-endangerment and state "
                "reuse criteria",
                "Projects must show recharged water will not cause MCL "
                "(maximum contaminant level) exceedances under the Safe "
                "Drinking Water Act, or violate state reuse criteria. Persistent "
                "contaminants or unreliable treatment can block approval.",
                (
                    "Source nitrate or disinfection byproduct precursors "
                    "routinely exceed levels acceptable for recharge.",
                    "State reuse rules require full advanced treatment before any subsurface application.",
                    "Pilot data show MCL (maximum contaminant level) "
                    "exceedances in downgradient monitoring wells during "
                    "recharge tests.",
                ),
            ),
            (
                "Anti-degradation and total maximum daily load compliance",
                "Anti-degradation policies and TMDLs (total maximum daily "
                "loads—the maximum amount of a pollutant a water body can "
                "receive and still meet water-quality standards) can limit new "
                "pollutant loads to groundwater or connected surface waters. "
                "MAR (managed aquifer recharge) may be treated as a discharge "
                "that must fit within remaining allocation.",
                (
                    "A TMDL (total maximum daily load) leaves no assimilative "
                    "capacity for nutrients associated with the proposed source "
                    "water.",
                    "Anti-degradation review classifies the project as "
                    "lowering high-quality groundwater, triggering denial.",
                    "Connected surface-water TMDLs constrain recharge that would increase baseflow pollutant loads.",
                ),
            ),
            (
                "Geochemical compatibility (mobilization or precipitation risks)",
                "Mixing recharge water with native groundwater can mobilize "
                "arsenic, metals, or organics, or cause clogging precipitates. "
                "Unfavorable geochemistry is a common technical and regulatory "
                "obstacle.",
                (
                    "Oxic recharge mobilizes arsenic from aquifer sediments, "
                    "raising downgradient concentrations above MCLs "
                    "(maximum contaminant levels).",
                    "Calcite or iron precipitation clogs injection wells "
                    "within weeks, making continuous operation impractical.",
                    "Regulators require geochemical modeling the project "
                    "cannot validate with available mineralogy data.",
                ),
            ),
            (
                "Contaminants of emerging concern / PFAS and monitoring-order compliance",
                "PFAS (per- and polyfluoroalkyl substances) and other CECs "
                "(contaminants of emerging concern) are increasingly regulated "
                "for reuse and recharge. Detection, treatment, or monitoring "
                "orders can halt projects that otherwise meet conventional MCLs "
                "(maximum contaminant levels).",
                (
                    "Source water or site soils contain PFAS (per- and "
                    "polyfluoroalkyl substances) above proposed recharge "
                    "thresholds with no affordable treatment path.",
                    "A monitoring order requires multi-year CEC "
                    "(contaminants of emerging concern) sampling before any "
                    "recharge authorization is issued.",
                    "Downgradient drinking-water wells trigger stricter PFAS limits that the project cannot guarantee.",
                ),
            ),
            (
                "Residuals handling (backwash/brine) permitting",
                "Treatment trains for recharge often produce backwash, brine, "
                "or residuals that need discharge or disposal permits. "
                "Without a lawful residuals pathway, treatment cannot operate.",
                (
                    "RO (reverse osmosis) brine has no permitted discharge "
                    "outlet or disposal well, blocking advanced pretreatment.",
                    "Filter backwash solids fail landfill acceptance criteria.",
                    "Local sewer capacity refuses high-TDS (total dissolved "
                    "solids) residuals from treatment for injection.",
                ),
            ),
            (
                "Well construction and monitoring plan (state standards / Underground Injection Control)",
                "Regulators typically require compliant well construction, "
                "annular seals, and a monitoring network that can detect "
                "migration or water-quality changes—often under UIC "
                "(Underground Injection Control) rules. Inadequate monitoring "
                "design can prevent permit issuance.",
                (
                    "State well standards require multi-point monitoring the "
                    "sponsor cannot install because of land-access limits.",
                    "UIC (Underground Injection Control) reviewers reject the "
                    "monitoring plan as unable to detect vertical migration "
                    "into a USDW (underground source of drinking water).",
                    "Existing wells do not meet sanitary-seal standards and "
                    "cannot be used as permitted injection or observation "
                    "wells.",
                ),
            ),
        ),
    ),
    (
        "Project And Jurisdiction Screen",
        (
            (
                "Federal nexus that may trigger federal environmental laws and reviews (for example National "
                "Environmental Policy Act, Endangered Species Act, National Historic Preservation Act)",
                "Federal funding, permits, or land create a federal nexus that "
                "can trigger NEPA (National Environmental Policy Act), ESA "
                "(Endangered Species Act), NHPA (National Historic Preservation "
                "Act), and related consultations. These reviews often control "
                "overall schedule more than local permits.",
                (
                    "Federal cost-share triggers an IS (environmental impact "
                    "statement) lasting several years before construction can "
                    "start.",
                    "A federal permit requires ESA (Endangered Species Act) "
                    "consultation that concludes with project-limiting "
                    "reasonable and prudent measures.",
                    "NHPA (National Historic Preservation Act) Section 106 "
                    "consultation identifies adverse effects that force major "
                    "alignment changes.",
                ),
            ),
            (
                "Tribal lands/resources or interstate context requiring additional coordination",
                "Projects affecting tribal lands, treaty resources, or "
                "interstate waters need early government-to-government or "
                "multi-state coordination. Late engagement can stop permitting "
                "or create unresolved opposition.",
                (
                    "Recharge may affect culturally important springs; tribal "
                    "consultation results in a request to abandon the site.",
                    "An interstate groundwater basin requires dual-state approvals that conflict on accounting rules.",
                    "Treaty fishing or water rights concerns lead agencies to "
                    "pause permits until mitigation is negotiated.",
                ),
            ),
        ),
    ),
)


def _slugify_consideration(section_idx: int, item_idx: int) -> str:
    """Stable index key for Dash pattern-matching IDs."""
    return f"{section_idx}-{item_idx}"


def _consideration_item(
    section_idx: int,
    item_idx: int,
    title: str,
    why: str,
    examples: tuple,
    *,
    is_last: bool = False,
):
    """One consideration row with collapsible detail."""
    item_key = _slugify_consideration(section_idx, item_idx)
    toggle_id = {"type": "reg-detail-toggle", "index": item_key}
    collapse_id = {"type": "reg-detail-collapse", "index": item_key}

    return html.Div(
        [
            html.Div(
                [
                    html.Span(title, className="flex-grow-1"),
                    dbc.Button(
                        [
                            html.I(className="fas fa-chevron-down me-1"),
                            "View more",
                        ],
                        id=toggle_id,
                        color="link",
                        size="sm",
                        className="py-0 px-1 text-primary text-nowrap",
                        n_clicks=0,
                    ),
                ],
                className="d-flex align-items-start justify-content-between gap-2",
            ),
            dbc.Collapse(
                html.Div(
                    [
                        html.P(
                            [html.Strong("Why it matters: "), why],
                            className="mb-2 small",
                        ),
                        html.P(
                            html.Strong("Example obstacles for MAR projects"),
                            className="mb-1 small",
                        ),
                        html.Ul(
                            [html.Li(ex, className="mb-1 small") for ex in examples],
                            className="mb-0 ps-3",
                        ),
                    ],
                    className="mt-2 p-2 rounded border-start border-3 border-primary bg-light",
                ),
                id=collapse_id,
                is_open=False,
            ),
        ],
        className="mb-0" if is_last else "mb-3 pb-2 border-bottom",
    )


def create_basic_regulation_feasibility_content():
    """Create informational regulatory considerations (sub-tab 5.1) — no user scoring."""
    section_cards = []
    for section_idx, (section_title, items) in enumerate(REGULATORY_CONSIDERATIONS):
        item_nodes = [
            _consideration_item(
                section_idx,
                item_idx,
                title,
                why,
                examples,
                is_last=(item_idx == len(items) - 1),
            )
            for item_idx, (title, why, examples) in enumerate(items)
        ]

        section_cards.append(
            dbc.Card(
                [
                    dbc.CardHeader(
                        section_title,
                        className="fw-bold bg-primary text-white py-2",
                    ),
                    dbc.CardBody(item_nodes, className="p-3"),
                ],
                className="mb-3",
            ),
        )

    return [
        html.P(
            "Regulatory and permitting requirements for MAR projects are highly "
            "site-specific and can be complex. This tab is meant to help you think "
            "through some potential considerations early in planning, and is not "
            "meant to provide a complete checklist or legal advice. The regulatory "
            "and permitting considerations below are general starting points only; "
            "they are not exhaustive, and what applies to your project will depend "
            "on location, water source, recharge method, and jurisdiction. Expand "
            "any item for additional information and example difficulties for MAR "
            "projects. The information provided in this tab is for planning "
            "awareness only, it is not scored and does not affect feasibility "
            "rankings or the final analysis provided by this tool.",
            className="text-muted mb-3",
        ),
        *section_cards,
        dbc.Alert(
            [
                html.Strong("Next step: "),
                "Use sub-tab (5.2) AI-Powered Regulatory and Permitting Factors to build "
                "a location-specific prompt for your preferred AI model.",
            ],
            color="info",
            className="mb-0",
        ),
    ]


def create_ai_regulations_permits_content():
    """Create regulations prompt-builder content (sub-tab 5.2). No in-app AI API."""
    return [
        dbc.Alert(
            [
                html.Div(
                    "Build a regulatory and permitting prompt from the Project Location "
                    "set on (1) Overview, then paste it into your preferred AI model. "
                    "Results are generated as an HTML file that can be opened in any "
                    "browser.",
                    className="mb-0",
                ),
            ],
            color="light",
            className="border mb-3 py-2",
        ),
        dbc.Card(
            [
                dbc.CardHeader(
                    "Build Regulations Prompt",
                    className="fw-bold bg-primary text-white py-2",
                ),
                dbc.CardBody(
                    [
                        html.Small(
                            "Uses Project Location from the Overview tab. Create the prompt, "
                            "then paste it into your preferred AI model.",
                            className="text-muted d-block mb-2",
                        ),
                        dbc.ButtonGroup(
                            [
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
                            ],
                            className="mb-2",
                        ),
                        html.Div(id="mar-regs-prompt-feedback", className="mb-2"),
                        dcc.Textarea(
                            id="mar-regs-prompt-display",
                            value="",
                            readOnly=True,
                            placeholder=("Click Build Prompt to generate the text for the Overview project location…"),
                            style={
                                "width": "100%",
                                "minHeight": "220px",
                                "fontFamily": "monospace",
                                "fontSize": "12px",
                                "resize": "vertical",
                            },
                        ),
                    ],
                    className="p-3",
                ),
            ],
            className="mb-3",
        ),
        dbc.Tooltip(
            "Create the regulations prompt using Overview Project Location",
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
                html.H4("How To Use This Tab", className="mb-2 text-primary"),
                html.Ol(
                    [
                        html.Li(
                            [
                                html.Strong("(5.1) Regulatory and Permitting Considerations: "),
                                "Review regulatory and permitting considerations for a MAR "
                                "project to understand their potential applicability for "
                                "your project.",
                            ],
                            className="mb-2",
                        ),
                        html.Li(
                            [
                                html.Strong("(5.2) AI-Powered Regulatory and Permitting Factors: "),
                                "Build a prompt, then paste it into your preferred AI model "
                                "to identify potential regulatory and permitting factors "
                                "relevant to your project.",
                            ],
                            className="mb-2",
                        ),
                        html.Li(
                            [
                                html.Strong("(5.3) AI-Powered Environmental, Ecological, and Cultural Factors: "),
                                "Build a prompt, then paste it into your preferred AI model "
                                "to explore potential environmental, ecological, and cultural "
                                "factors relevant to your project.",
                            ],
                            className="mb-0",
                        ),
                    ],
                    className="mb-3 ps-3 text-muted",
                ),
                dbc.Tabs(
                    [
                        dbc.Tab(
                            label="(5.1) Regulatory and Permitting Considerations",
                            id=tab_nav_id("basic-regulation-tab"),
                            tab_id="basic-regulation-tab",
                            children=create_basic_regulation_feasibility_content(),
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
                            label="(5.2) AI-Powered Regulatory and Permitting Factors",
                            id=tab_nav_id("ai-regulations-permits-tab"),
                            tab_id="ai-regulations-permits-tab",
                            children=create_ai_regulations_permits_content(),
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
                        dbc.Tab(
                            label="(5.3) AI-Powered Environmental, Ecological, and Cultural Factors",
                            id=tab_nav_id("environmental-considerations-tab"),
                            tab_id="environmental-considerations-tab",
                            children=create_environmental_considerations_content(),
                            label_style={
                                "color": "#ffffff",
                                "fontWeight": "bold",
                                "backgroundColor": "#20c997",
                                "border": "1px solid #20c997",
                            },
                            active_label_style={
                                "color": "#ffffff",
                                "backgroundColor": "#1aa179",
                                "border": "1px solid #1aa179",
                            },
                        ),
                    ],
                    id="legal-constraints-tabs",
                    active_tab="basic-regulation-tab",
                ),
                tab_tooltip(
                    "basic-regulation-tab",
                    "Informational regulatory and permitting themes (not scored)",
                ),
                tab_tooltip(
                    "ai-regulations-permits-tab",
                    "AI-assisted location-specific regulatory and permitting factors",
                ),
                tab_tooltip(
                    "environmental-considerations-tab",
                    "AI-assisted environmental, ecological, and cultural factors",
                ),
            ],
        ),
    ]
