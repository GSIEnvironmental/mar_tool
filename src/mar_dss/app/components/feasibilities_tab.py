"""
Feasibilities tab content for MAR DSS dashboard.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.utils.tab_tooltips import tab_nav_id, tab_tooltip

_HEADER_STYLE = {"backgroundColor": "#1e3a5f", "fontSize": "1rem"}


def _detail_card_header(title, help_btn=None):
    children = [html.Span(title, className="fw-bold text-white")]
    if help_btn is not None:
        children = [
            html.Div(
                [
                    html.Span(title, className="fw-bold text-white"),
                    help_btn,
                ],
                className="d-flex align-items-center justify-content-between w-100",
            ),
        ]
    return dbc.CardHeader(
        children if help_btn is not None else title,
        className="fw-bold text-white py-2",
        style=_HEADER_STYLE,
    )


def _spider_help_btn(option_key, title="Help: how to read this spider plot"):
    return html.Button(
        "?",
        id={"type": "spider-help-btn", "option": option_key},
        type="button",
        className="mar-help-btn eng-help-btn",
        title=title,
    )


def _spider_performance_help_modal():
    """Shared help modal for MAR Option Performance Comparison spider plots."""
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("MAR Option Performance Comparison Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.P(
                        "Each spider (radar) plot summarizes one MAR engineering option "
                        "on six axes. Values are percentages from 0 (center) to 100 "
                        "(outer ring). A larger polygon generally means stronger overall "
                        "performance for that option.",
                        className="mb-3",
                    ),
                    html.H6("How to read the plot", className="fw-bold mb-2"),
                    html.Ul(
                        [
                            html.Li(
                                "Each spoke is one criterion. The plotted point on that "
                                "spoke is the score for this option.",
                            ),
                            html.Li(
                                "The blue filled shape connects all six scores. "
                                "Compare shapes across options: farther from the center "
                                "is better on that axis.",
                            ),
                            html.Li("Score colors under each axis label: green ≥ 75%, orange 50–75%, red < 50%."),
                            html.Li(
                                "If an option is not feasible, all six scores are set "
                                "to 0% so the polygon collapses to the center.",
                            ),
                        ],
                        className="mb-3",
                    ),
                    html.H6("What each score means", className="fw-bold mb-2"),
                    html.Ul(
                        [
                            html.Li(
                                [
                                    html.Strong("Hydrogeologic: "),
                                    "DSS soft hydrogeologic constraints (and benefits) "
                                    "scored as points vs ideal points, reported as 0–100%. "
                                    "Constraint response levels map to points "
                                    "(acceptable = 10 … reject = 0). Hard hydrogeologic "
                                    "failure forces this score to 0%.",
                                ],
                            ),
                            html.Li(
                                [
                                    html.Strong("Water Quality: "),
                                    "Same scoring approach using water-quality "
                                    "(environmental) soft constraints and benefits "
                                    "(0–100%).",
                                ],
                            ),
                            html.Li(
                                [
                                    html.Strong("Capital / Maintenance / NPV efficiency: "),
                                    "Relative cost efficiency among feasible options. "
                                    "The lowest-cost feasible option scores 100%; others "
                                    "score 100 × (minimum cost ÷ this option’s cost). "
                                    "Lower cost → higher efficiency.",
                                ],
                            ),
                            html.Li(
                                [
                                    html.Strong("Annual Capital Cost Per Acre-ft: "),
                                    "Same relative-efficiency idea using capital cost "
                                    "divided by annual recharge volume (acre-ft/yr). "
                                    "The lowest $/acre-ft among feasible options is 100%. "
                                    "The label may also show the absolute $/acre-ft.",
                                ],
                            ),
                        ],
                        className="mb-3",
                    ),
                    html.H6("Key equations", className="fw-bold mb-2"),
                    html.Pre(
                        "Constraint/benefit type score:\n"
                        "  Score = (actual_points / ideal_points) × 100\n"
                        "  ideal_points = (#constraints × 10) + (#benefits × 10)\n"
                        "\n"
                        "Cost efficiency (capital, O&M, NPV, or $/acre-ft):\n"
                        "  Efficiency = 100 × (min_feasible_value / this_value)\n"
                        "  (clamped to 0–100; infeasible options → 0)",
                        className="bg-light border rounded p-2 small mb-0",
                    ),
                ],
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="spider-help-close",
                    className="ms-auto",
                    color="secondary",
                ),
            ),
        ],
        id="spider-performance-help-modal",
        size="lg",
        scrollable=True,
        is_open=False,
    )


def _performance_comparison_panel():
    return html.Div(
        [
            _spider_performance_help_modal(),
            dbc.Card(
                [
                    _detail_card_header(
                        "MAR Option Performance Comparison",
                        help_btn=_spider_help_btn(
                            "panel",
                            "Help: how spider plot scores are computed",
                        ),
                    ),
                    dbc.CardBody(
                        [html.Div(id="spider-plots-container")],
                        style={"padding": "0.75rem"},
                    ),
                ],
                className="shadow-sm",
            ),
        ],
    )


def _executive_summary_card():
    return dbc.Card(
        [
            dbc.CardHeader(
                "Feasibility Summary",
                className="fw-bold text-white py-2",
                style=_HEADER_STYLE,
            ),
            dbc.CardBody(
                html.Div(
                    id="engineering-options-summary",
                    children=[
                        html.Div(
                            "Loading option economics...",
                            className="text-center text-muted p-3",
                            style={"fontSize": "1rem"},
                        ),
                    ],
                ),
                style={"padding": "0.5rem 0.75rem"},
            ),
        ],
        className="shadow-sm mb-3",
    )


def _constraint_help_btn(btn_id, title):
    return html.Button(
        "?",
        id=btn_id,
        type="button",
        className="mar-help-btn eng-help-btn",
        title=title,
    )


def _constraint_help_note(btn_id, title="Help: constraint meanings"):
    """Inline note with an active ? button that opens the panel help modal."""
    return html.P(
        [
            "Click the ",
            html.Button(
                "?",
                id=btn_id,
                type="button",
                className="mar-help-btn eng-help-btn d-inline-flex align-items-center justify-content-center",
                title=title,
                style={
                    "width": "1.25rem",
                    "height": "1.25rem",
                    "fontSize": "0.7rem",
                    "verticalAlign": "middle",
                    "padding": "0",
                    "lineHeight": "1",
                },
            ),
            " icon for more details about the meaning of each constraint — "
            "how it is defined, how the response level is computed, and why it matters.",
        ],
        className="small text-muted mb-2 mb-md-3",
    )


def _constraint_entry(name, definition, computed, why):
    return html.Li(
        [
            html.Strong(f"{name}. "),
            html.Span(definition + " "),
            html.Em("How computed: "),
            html.Span(computed + " "),
            html.Em("Why it matters: "),
            html.Span(why),
        ],
        className="mb-2",
    )


def _response_level_help_block():
    return html.Div(
        [
            html.H6("How to read the chart", className="fw-bold mb-2"),
            html.Ul(
                [
                    html.Li("Each column is one soft constraint; each row is one MAR option."),
                    html.Li("Circle color and number are the DSS response level for that option–constraint pair."),
                    html.Li(
                        [
                            "Response levels: ",
                            html.Strong("−1"),
                            " Not Applicable (grey; excluded); ",
                            html.Strong("0"),
                            " Acceptable; ",
                            html.Strong("1"),
                            " Acceptable With Additional Cost; ",
                            html.Strong("2"),
                            " Warning; ",
                            html.Strong("3"),
                            " Mitigation Needed; ",
                            html.Strong("4"),
                            " Reject.",
                        ],
                    ),
                    html.Li(
                        "Higher levels reduce the hydrogeologic / water-quality "
                        "score on the Performance Comparison spiders "
                        "(points drop from 10 at level 0 toward 0 at level 4).",
                    ),
                    html.Li(
                        "For Water Quality answers of Unknown, level 2 (yellow) is a "
                        "data-gap warning — collect information; it does not mean "
                        "remediation is already required.",
                    ),
                ],
                className="mb-3",
            ),
        ],
    )


def _hydrogeologic_constraints_help_modal():
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Hydrogeologic Constraints Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.P(
                        "These soft constraints screen each MAR option against "
                        "site hydrogeology from the decision graph and related inputs. "
                        "Many vadose/surface checks apply mainly to Surface Recharge "
                        "and are marked Not Applicable (−1) for confined aquifers or for "
                        "well-based options when the pathway is bypassed.",
                        className="mb-3",
                    ),
                    _response_level_help_block(),
                    html.H6("Constraint definitions", className="fw-bold mb-2"),
                    html.Ul(
                        [
                            _constraint_entry(
                                "Ground surface slope Suitability",
                                "Whether ground slope is suitable for surface infiltration basins / spreading.",
                                "Uses ground-surface slope significance (Gentle / "
                                "Moderate / Steep). For Surface Recharge: Gentle → 0; "
                                "Moderate → 1 (earthwork cost); Steep → 3 (mitigation). "
                                "Dry Well and Injection Well stay at 0. Confined "
                                "aquifers → −1.",
                                "Steep sites raise earthwork cost and reduce reliable "
                                "basin performance for surface recharge.",
                            ),
                            _constraint_entry(
                                "Vadose zone infiltration",
                                "Whether unsaturated-zone hydraulic conductivity supports meaningful infiltration.",
                                "Always Not Applicable (−1 / grey) for Injection Well. "
                                "Confined → −1. If infiltration is inadequate, "
                                "Surface Recharge → 3 (consider bypassing the vadose); "
                                "Dry Well stays 0.",
                                "Low infiltration capacity limits recharge volume for "
                                "surface methods; injection wells bypass the vadose.",
                            ),
                            _constraint_entry(
                                "Vadose zone pollution",
                                "Whether the vadose zone currently contains pollution.",
                                "Always Not Applicable (−1 / grey) for Injection Well. "
                                "Confined → −1. If pollution is present, Surface "
                                "Recharge → 3 (bypass or remediate); Dry Well stays 0.",
                                "Recharge through a polluted vadose can mobilize "
                                "contaminants; injection wells bypass that pathway.",
                            ),
                            _constraint_entry(
                                "Vadose zone pollution biodegradability",
                                "Whether vadose pollution can biodegrade / attenuate naturally.",
                                "Always Not Applicable (−1 / grey) for Injection Well. "
                                "Only scored when vadose pollution is present. "
                                "Biodegradable + Surface Recharge → 2 (monitor "
                                "attenuation). Non-biodegradable + Surface Recharge → 3; "
                                "Dry Well → 2 (mounding may still mobilize toxins). "
                                "Confined → −1.",
                                "Toxicity and attenuation control remediation needs "
                                "for vadose pathways; injection wells bypass the vadose.",
                            ),
                            _constraint_entry(
                                "Vadose zone remediation needed",
                                "Whether cleanup of the vadose is required before or during recharge.",
                                "Always Not Applicable (−1 / grey) for Injection Well. "
                                "Confined → −1. If remediation is needed, Surface "
                                "Recharge → 3.",
                                "Remediation adds cost for surface methods; injection wells bypass the vadose.",
                            ),
                            _constraint_entry(
                                "Vadose zone residence time",
                                "Travel time of water through the vadose relative to "
                                "treatment / risk needs for contaminated source water.",
                                "Always Not Applicable (−1 / grey) for Injection Well. "
                                "Computed only when Water Quality Q1 (source "
                                "contaminants) = Yes. If residence-time issues are "
                                "flagged → 3 (mitigation); otherwise a monitoring "
                                "warning (2). Confined → −1. Q1 No/Unknown → not "
                                "computed (0).",
                                "Too-short residence time reduces natural treatment "
                                "through the vadose; injection wells bypass that pathway.",
                            ),
                            _constraint_entry(
                                "Surface recharge suitability",
                                "Overall Boolean suitability for surface recharge "
                                "(slope, infiltration, vadose contamination, etc.).",
                                "Always Not Applicable (−1 / grey) for Injection Well and "
                                "Dry Well. Confined → −1. False → 3 for surface "
                                "options; True → 0.",
                                "A single roll-up flag that surface methods are "
                                "unlikely to be suitable without major mitigation; "
                                "not applicable to well-based options.",
                            ),
                            _constraint_entry(
                                "Confined aquifer depth Suitability",
                                "Whether the confined target is at a workable depth for wells.",
                                "Unconfined → −1. Confined: Too Deep → 4 (reject); Moderate Deep → 2; otherwise 0.",
                                "Excessive depth drives drilling cost and may make injection impractical.",
                            ),
                            _constraint_entry(
                                "Confined leakage significance",
                                "Degree of leakage through confining layers.",
                                "Unconfined → −1. Confined: low → 0; medium → 2; high → 3.",
                                "High leakage can lose recharge, affect adjacent "
                                "units, or create pressure/geomechanical issues.",
                            ),
                            _constraint_entry(
                                "Land Use",
                                "Compatibility of land use with land-intensive surface recharge.",
                                "Overview land use Residential or "
                                "Commercial/Industrial → 1 (extra land cost) for "
                                "Surface Recharge; Agricultural / Open Space → 0. "
                                "Dry Well and Injection Well stay 0.",
                                "Developed land is costly and may face zoning limits for basins and spreading areas.",
                            ),
                        ],
                        className="mb-0",
                    ),
                ],
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="hydro-constraints-help-close",
                    className="ms-auto",
                    color="secondary",
                ),
            ),
        ],
        id="hydro-constraints-help-modal",
        size="lg",
        scrollable=True,
        is_open=False,
    )


def _water_quality_constraints_help_modal():
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Water Quality Constraints Help"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.P(
                        "These soft constraints come from the Water Quality screening "
                        "answers (source contaminants, turbidity, vadose impact, and "
                        "aquifer contaminant flags). Unknown answers create a data-gap "
                        "warning (response 2) so missing information is visible without "
                        "assuming high risk.",
                        className="mb-3",
                    ),
                    _response_level_help_block(),
                    html.H6("Constraint definitions", className="fw-bold mb-2"),
                    html.Ul(
                        [
                            _constraint_entry(
                                "Source Water Contaminants",
                                "Whether source water has industrial, domestic, or emerging contaminants.",
                                "Yes → 3 (mitigation / extra cost beyond this tool’s "
                                "scope). Unknown → data-gap warning (2). No → 0.",
                                "Contaminated source water may need treatment, "
                                "monitoring, or may be unsuitable for some MAR goals.",
                            ),
                            _constraint_entry(
                                "Clogging & Fouling Risks",
                                "Turbidity-related risk of clogging basins or wells.",
                                "Turbidity >20 NTU → 3 (pretreatment). 5–20 NTU → 1 "
                                "(possible sedimentation/clarification). Unknown → "
                                "data-gap warning (2). <5 NTU → 0.",
                                "High solids reduce infiltration rates and increase "
                                "O&M (scraping, well rehabilitation).",
                            ),
                            _constraint_entry(
                                "Vadose Zone Contaminant Impact",
                                "Whether the vadose / unsaturated zone is contaminant-"
                                "impacted (surface pathway risk; Water Quality Q3).",
                                "Confined aquifers → −1. Vadose impacted Yes + Surface "
                                "Recharge → 4 (reject). Dry Well and Injection Well "
                                "stay 0 (can bypass the vadose). Unknown → yellow "
                                "data-gap warning (2) — missing information, not a "
                                "remediation requirement.",
                                "Surface recharge through an impacted vadose can "
                                "transport contaminants; well options that bypass the "
                                "vadose may still be viable. Unknown means collect data, "
                                "not that remediation is already required.",
                            ),
                            _constraint_entry(
                                "Target Aquifer Anthropogenic Contaminants",
                                "Whether the target aquifer already has human-caused contamination.",
                                "Yes → 4 (reject all MAR options). Unknown → data-gap warning (2). No → 0.",
                                "Recharging into an already unsuitable aquifer does "
                                "not meet water-quality objectives and can worsen "
                                "liability.",
                            ),
                            _constraint_entry(
                                "Target Aquifer Naturally Occurring Contaminants",
                                "Whether natural geogenic contaminants (e.g. metals, "
                                "arsenic) affect the target aquifer.",
                                "Yes → 2 (warning; site-specific cost / treatment may "
                                "be needed beyond this tool). Unknown → data-gap "
                                "warning (2). No → 0.",
                                "Natural contaminants may still allow MAR but often "
                                "need extra monitoring, blending, or treatment.",
                            ),
                        ],
                        className="mb-0",
                    ),
                ],
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="wq-constraints-help-close",
                    className="ms-auto",
                    color="secondary",
                ),
            ),
        ],
        id="wq-constraints-help-modal",
        size="lg",
        scrollable=True,
        is_open=False,
    )


def _hydrogeologic_constraints_panel():
    return html.Div(
        [
            _hydrogeologic_constraints_help_modal(),
            dbc.Card(
                [
                    _detail_card_header(
                        "Hydrogeologic Constraints",
                        help_btn=_constraint_help_btn(
                            "hydro-constraints-help-btn",
                            "Help: hydrogeologic constraint meanings",
                        ),
                    ),
                    dbc.CardBody(
                        [
                            _constraint_help_note(
                                "hydro-constraints-help-note-btn",
                                "Help: hydrogeologic constraint meanings",
                            ),
                            dcc.Graph(
                                id="hydrogeologic-constraints-heatmap-chart",
                                style={"height": "520px", "width": "100%"},
                                config={"displayModeBar": False},
                                className="w-100",
                            ),
                            html.Div(
                                id="hydrogeologic-constraints-heatmap-legend",
                                className="mt-2",
                            ),
                        ],
                        style={"padding": "0.75rem"},
                        className="w-100",
                    ),
                ],
                className="shadow-sm w-100",
            ),
        ],
    )


def _water_quality_constraints_panel():
    return html.Div(
        [
            _water_quality_constraints_help_modal(),
            dbc.Card(
                [
                    _detail_card_header(
                        "Water Quality Constraints",
                        help_btn=_constraint_help_btn(
                            "wq-constraints-help-btn",
                            "Help: water quality constraint meanings",
                        ),
                    ),
                    dbc.CardBody(
                        [
                            _constraint_help_note(
                                "wq-constraints-help-note-btn",
                                "Help: water quality constraint meanings",
                            ),
                            dcc.Graph(
                                id="environmental-constraints-heatmap-chart",
                                style={"height": "520px", "width": "100%"},
                                config={"displayModeBar": False},
                                className="w-100",
                            ),
                            html.Div(
                                id="environmental-constraints-heatmap-legend",
                                className="mt-2",
                            ),
                        ],
                        style={"padding": "0.75rem"},
                        className="w-100",
                    ),
                ],
                className="shadow-sm w-100",
            ),
        ],
    )


def _cost_comparison_panel():
    chart_style = {"height": "320px", "width": "100%", "maxWidth": "520px"}
    return dbc.Card(
        [
            _detail_card_header("Cost Comparison"),
            dbc.CardBody(
                [
                    html.Div(
                        [
                            dcc.Graph(
                                id="capital-cost-chart",
                                style=chart_style,
                                config={"displayModeBar": False},
                                className="mb-3",
                            ),
                            dcc.Graph(
                                id="maintenance-cost-chart",
                                style=chart_style,
                                config={"displayModeBar": False},
                                className="mb-3",
                            ),
                            dcc.Graph(
                                id="npv-cost-chart",
                                style=chart_style,
                                config={"displayModeBar": False},
                            ),
                        ],
                        className="d-flex flex-column align-items-center w-100",
                    ),
                ],
                style={"padding": "0.75rem"},
                className="w-100",
            ),
        ],
        className="shadow-sm w-100",
    )


def _feasibility_details_inner_tabs():
    """Sub-tabs for each Feasibility Details section (full-width panels)."""
    return dbc.Tabs(
        [
            dbc.Tab(
                label="Performance Comparison",
                tab_id="feasibility-detail-performance-tab",
                id=tab_nav_id("feasibility-detail-performance-tab"),
                children=_performance_comparison_panel(),
            ),
            dbc.Tab(
                label="Hydrogeologic Constraints",
                tab_id="feasibility-detail-hydro-tab",
                id=tab_nav_id("feasibility-detail-hydro-tab"),
                children=_hydrogeologic_constraints_panel(),
            ),
            dbc.Tab(
                label="Water Quality Constraints",
                tab_id="feasibility-detail-env-tab",
                id=tab_nav_id("feasibility-detail-env-tab"),
                children=_water_quality_constraints_panel(),
            ),
            dbc.Tab(
                label="Cost Comparison",
                tab_id="feasibility-detail-cost-tab",
                id=tab_nav_id("feasibility-detail-cost-tab"),
                children=_cost_comparison_panel(),
            ),
        ],
        id="feasibility-details-inner-tabs",
        active_tab="feasibility-detail-performance-tab",
        className="mb-2",
    )


def create_feasibilities_content():
    """Create content for Feasibilities tab.

    Feasibility Summary card at the top. Feasibility Details is a separate tab
    below, with a View checkbox; when open, each former card is its own sub-tab.
    """
    view_details = bool(dash_storage.get_data("view_feasibility_details"))

    feasibility_details_tab_body = html.Div(
        [
            html.Div(
                [
                    dbc.Checkbox(
                        id="view-feasibility-details-check",
                        label=html.Strong("View additional details about the feasibility of each option"),
                        value=view_details,
                        className="mb-0 collapse-toggle-check",
                        input_class_name="me-1",
                        label_class_name="mb-0",
                    ),
                ],
                className="d-flex align-items-center py-2 px-1",
            ),
            dbc.Collapse(
                _feasibility_details_inner_tabs(),
                id="feasibility-details-collapse",
                is_open=view_details,
            ),
        ],
    )

    return html.Div(
        [
            _executive_summary_card(),
            dbc.Tabs(
                [
                    dbc.Tab(
                        label="Feasibility Details",
                        tab_id="feasibility-details-tab",
                        id=tab_nav_id("feasibility-details-tab"),
                        children=feasibility_details_tab_body,
                    ),
                ],
                id="feasibility-subtabs",
                active_tab="feasibility-details-tab",
                className="mb-2",
            ),
            tab_tooltip(
                "feasibility-details-tab",
                "Performance comparison, constraints heatmaps, and cost charts",
            ),
            tab_tooltip(
                "feasibility-detail-performance-tab",
                "Radar comparison of constraint scores and cost efficiencies",
            ),
            tab_tooltip(
                "feasibility-detail-hydro-tab",
                "Hydrogeologic constraint intensity by option",
            ),
            tab_tooltip(
                "feasibility-detail-env-tab",
                "Water quality constraint intensity by option",
            ),
            tab_tooltip(
                "feasibility-detail-cost-tab",
                "Capital, maintenance, and NPV cost comparison",
            ),
            dbc.Tooltip(
                "Show performance comparison, constraints, and cost charts for each option",
                target="view-feasibility-details-check",
                placement="top",
            ),
            dbc.Tooltip(
                "Capital cost, annual recharge volume, and unit costs for each MAR technology",
                target="engineering-options-summary",
                placement="top",
            ),
            dbc.Tooltip(
                "Constraint intensity by option for hydrogeologic criteria",
                target="hydrogeologic-constraints-heatmap-chart",
                placement="top",
            ),
            dbc.Tooltip(
                "Radar comparison of constraint scores and cost efficiencies (including $/acre-ft)",
                target="spider-plots-container",
                placement="top",
            ),
            dbc.Tooltip(
                "Constraint intensity for water quality criteria",
                target="environmental-constraints-heatmap-chart",
                placement="top",
            ),
            dbc.Tooltip(
                "Capital cost comparison across MAR technology options",
                target="capital-cost-chart",
                placement="top",
            ),
            dbc.Tooltip(
                "Annual maintenance cost comparison across options",
                target="maintenance-cost-chart",
                placement="top",
            ),
            dbc.Tooltip(
                "Net present value comparison across options",
                target="npv-cost-chart",
                placement="top",
            ),
        ],
        style={"padding": "0.5rem"},
    )
