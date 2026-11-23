"""
Decision Interpretation tab content for MAR DSS dashboard.
"""

import math
import string

import dash_bootstrap_components as dbc
import pandas as pd
from dash import dcc, html

import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.utils.cost_storage import (
    CAPITAL_COST_TOTAL_KEYS,
    MAINTENANCE_COST_TOTAL_KEYS,
    coerce_storage_cost_totals,
)

_HEADER_STYLE = {"backgroundColor": "#1e3a5f", "fontSize": "0.95rem"}


def _title_case_label(text):
    """Title Case for UI labels (first letter of each word)."""
    if text is None:
        return ""
    text = str(text).strip()
    if not text:
        return text
    return string.capwords(text)


_OPTION_TO_CAPITAL_COL = {
    "Surface Recharge": "Spreading Pond Cost ($)",
    "Injection Well": "Injection Wells Cost ($)",
    "Dry Well": "Dry Wells Cost ($)",
}

_OPTION_TO_MAINTENANCE_COL = {
    "Surface Recharge": "Spreading Pond Maintenance Cost ($)",
    "Injection Well": "Injection Wells Maintenance Cost ($)",
    "Dry Well": "Dry Wells Maintenance Cost ($)",
}

_OPTION_TO_NPV_COL = {
    "Surface Recharge": "Spreading Pond Net Present Value ($)",
    "Injection Well": "Injection Wells Net Present Value ($)",
    "Dry Well": "Dry Wells Net Present Value ($)",
}

_RESPONSE_LABELS = {
    0: "Acceptable",
    1: "Acceptable With Additional Cost",
    2: "Warning",
    3: "Mitigation Needed",
    4: "Reject",
}

_RESPONSE_COLORS = {
    0: "success",
    1: "success",
    2: "warning",
    3: "warning",
    4: "danger",
}

# Internal DSS status → user-facing feasibility label
_STATUS_DISPLAY = {
    "Recommended": "Feasible",
    "Recommended with Warnings": "Feasible",
    "Conditionally Recommended": "Conditionally Feasible",
    "Rejected": "Not Feasible",
}

_STATUS_COLORS = {
    "Feasible": "success",
    "Conditionally Feasible": "info",
    "Not Feasible": "danger",
}

# Help text keyed by exact constraint name from hard/soft constraint engines
CONSTRAINT_HELP = {
    "Physical surface rechargeability": {
        "meaning": (
            "Hard check that the MAR method can physically deliver water into the "
            "target aquifer type (unconfined vs confined)."
        ),
        "triggered": (
            "Fails when Surface Recharge is selected for a confined aquifer. "
            "Passes for unconfined aquifers, and for well-based options on confined sites."
        ),
        "why": (
            "Surface spreading cannot reach a confined unit behind a confining layer; "
            "using the wrong method makes the option not feasible."
        ),
    },
    "Vadose zone contaminant impact": {
        "meaning": (
            "Hard check on whether an impacted vadose / unsaturated zone blocks surface recharge (Water Quality Q3)."
        ),
        "triggered": (
            "Fails for Surface Recharge when vadose impact = Yes. Well options pass because they can bypass the vadose."
        ),
        "why": ("Recharging through contaminated unsaturated soils can mobilize contaminants into the aquifer."),
    },
    "Target aquifer anthropogenic contaminants": {
        "meaning": (
            "Hard check that the target aquifer is not already unsuitable due to "
            "human-caused contamination (Water Quality Q4)."
        ),
        "triggered": ("Fails for every MAR option when aquifer anthropogenic contaminants = Yes."),
        "why": ("Recharging into a compromised aquifer does not meet water-quality goals and can increase liability."),
    },
    "Recharge Efficiency": {
        "meaning": (
            "Hard check that the option can recharge enough of the annual source "
            "water volume (rechargeable percentage vs minimum threshold)."
        ),
        "triggered": (
            "Fails when the option-specific rechargeable percentage (or confined "
            "rechargability) is below the configured minimum acceptable recharge %."
        ),
        "why": (
            "If too little source water can be recharged, the project cannot meet storage / water-supply objectives."
        ),
    },
    "Ground surface slope Suitability": {
        "meaning": ("Soft check on whether ground slope is suitable for surface infiltration basins or spreading."),
        "triggered": (
            "Uses ground-surface slope significance. For Surface Recharge: Gentle → "
            "acceptable; Moderate → cost; Steep → mitigation. Dry/Injection wells stay "
            "acceptable. Confined aquifers → Not Applicable."
        ),
        "why": ("Steep slopes raise earthwork cost and reduce reliable basin performance."),
    },
    "Vadose zone infiltration": {
        "meaning": ("Soft check that unsaturated-zone hydraulic conductivity supports infiltration."),
        "triggered": (
            "Always Not Applicable (−1 / grey) for Injection Well. Confined → "
            "Not Applicable. If the vadose K threshold is not met, Surface Recharge → "
            "mitigation (consider bypassing the vadose)."
        ),
        "why": (
            "Low infiltration capacity limits recharge volume for surface methods; "
            "injection wells bypass the vadose so this check does not apply."
        ),
    },
    "Vadose zone pollution": {
        "meaning": "Soft check for pollution already present in the vadose zone.",
        "triggered": (
            "Always Not Applicable (−1 / grey) for Injection Well. Confined → "
            "Not Applicable. If pollution is present, Surface Recharge → mitigation "
            "(bypass or remediate)."
        ),
        "why": (
            "Recharge through a polluted vadose can mobilize contaminants; injection wells bypass the vadose pathway."
        ),
    },
    "Vadose zone pollution biodegradability": {
        "meaning": ("Soft check on whether vadose pollution can biodegrade / attenuate naturally."),
        "triggered": (
            "Always Not Applicable (−1 / grey) for Injection Well. Confined → "
            "Not Applicable. Only scored when vadose pollution is present. "
            "Biodegradable + Surface Recharge → warning; non-biodegradable + "
            "Surface Recharge → mitigation; Dry Well may get a "
            "mounding/mobilization warning."
        ),
        "why": (
            "Toxicity and attenuation control remediation needs for pathways "
            "that interact with the vadose; injection wells bypass it."
        ),
    },
    "Vadose zone remediation needed": {
        "meaning": ("Soft check on whether vadose cleanup is needed before or during recharge."),
        "triggered": (
            "Always Not Applicable (−1 / grey) for Injection Well. Confined → "
            "Not Applicable. If remediation is needed, Surface Recharge → mitigation."
        ),
        "why": (
            "Remediation adds cost and complexity for surface methods; injection "
            "wells bypass the vadose so this check does not apply."
        ),
    },
    "Vadose zone residence time": {
        "meaning": (
            "Soft check on travel time of water through the vadose relative to "
            "natural treatment needs (pathogens, organics, nutrients)."
        ),
        "triggered": (
            "Always Not Applicable (−1 / grey) for Injection Well. Computed only when "
            "Water Quality Q1 (source water contaminants) = Yes. Uses stratigraphy, "
            "groundwater depth, and design infiltration rate. If residence time is "
            "not reasonable for listed constituents → mitigation; if computed and "
            "reasonable → monitoring warning. Confined aquifers → Not Applicable. "
            "Q1 No / Unknown → not computed (acceptable)."
        ),
        "why": (
            "Too-short residence time reduces natural treatment of contaminated "
            "source water through the vadose; injection wells bypass that pathway."
        ),
    },
    "Surface recharge suitability": {
        "meaning": (
            "Overall soft roll-up of whether surface recharge is suitable (slope, infiltration, vadose issues)."
        ),
        "triggered": (
            "Always Not Applicable (−1 / grey) for Injection Well and Dry Well. "
            "Confined aquifers → Not Applicable. For surface options: True → "
            "acceptable; False → mitigation."
        ),
        "why": (
            "Flags that surface methods are unlikely to work without major mitigation; "
            "not applicable to well-based options that bypass surface spreading."
        ),
    },
    "Confined aquifer depth Suitability": {
        "meaning": ("Soft check that a confined target is at a workable well depth."),
        "triggered": (
            "Unconfined → Not Applicable. Confined: Too Deep → reject; Moderate Deep → warning; otherwise acceptable."
        ),
        "why": ("Excessive depth drives drilling cost and may make injection impractical."),
    },
    "Confined leakage significance": {
        "meaning": "Soft check on leakage through confining layers.",
        "triggered": ("Unconfined → Not Applicable. Confined: low → acceptable; medium → warning; high → mitigation."),
        "why": ("High leakage can lose recharge, affect adjacent units, or create pressure issues."),
    },
    "Land Use": {
        "meaning": ("Soft check on land-use compatibility for land-intensive surface recharge."),
        "triggered": (
            "Overview land use Residential or Commercial/Industrial → additional "
            "cost for Surface Recharge; Agricultural / Open Space → acceptable. "
            "Dry Well and Injection Well stay acceptable."
        ),
        "why": ("Developed land is costly and may face zoning limits for basins and spreading."),
    },
    "Source Water Contaminants": {
        "meaning": ("Water-quality soft check on industrial, domestic, or emerging contaminants in source water."),
        "triggered": ("Yes → mitigation / extra cost beyond this tool. Unknown → data-gap warning. No → acceptable."),
        "why": ("Contaminated source water may need treatment or may be unsuitable for some MAR goals."),
    },
    "Clogging & Fouling Risks": {
        "meaning": ("Water-quality soft check on turbidity-related clogging of basins or wells."),
        "triggered": (
            "Turbidity >20 NTU → mitigation (pretreatment); 5–20 NTU → additional cost; "
            "Unknown → data-gap warning; <5 NTU → acceptable."
        ),
        "why": ("High solids reduce infiltration rates and increase O&M (scraping, well rehabilitation)."),
    },
    "Vadose Zone Contaminant Impact": {
        "meaning": (
            "Water-quality soft check on vadose / unsaturated-zone contaminant "
            "impact for the surface recharge pathway (Water Quality Q3)."
        ),
        "triggered": (
            "Confined → Not Applicable. Vadose impacted Yes + Surface Recharge → reject. "
            "Wells that bypass the vadose stay acceptable. Unknown → yellow data-gap "
            "warning (missing information — not a remediation requirement)."
        ),
        "why": (
            "Surface recharge through an impacted vadose can transport contaminants; "
            "wells may still be viable. Unknown means collect data first."
        ),
    },
    # Legacy alias kept for older saved DSS result payloads
    "Need for Remediation": {
        "meaning": ("Legacy name for Vadose Zone Contaminant Impact (Water Quality Q3)."),
        "triggered": (
            "Confined → Not Applicable. Vadose impacted Yes + Surface Recharge → reject. "
            "Wells that bypass the vadose stay acceptable. Unknown → yellow data-gap "
            "warning (missing information — not a remediation requirement)."
        ),
        "why": (
            "Surface recharge through an impacted vadose can transport contaminants; "
            "wells may still be viable. Unknown means collect data first."
        ),
    },
    "Target Aquifer Anthropogenic Contaminants": {
        "meaning": ("Water-quality soft check that the target aquifer is free of human-caused contamination."),
        "triggered": ("Yes → reject all MAR options. Unknown → data-gap warning. No → acceptable."),
        "why": ("Recharging into an already unsuitable aquifer fails water-quality objectives."),
    },
    "Target Aquifer Naturally Occurring Contaminants": {
        "meaning": ("Water-quality soft check for natural / geogenic contaminants in the target aquifer."),
        "triggered": (
            "Yes → warning (site-specific cost / treatment may be needed). Unknown → data-gap warning. No → acceptable."
        ),
        "why": ("Natural contaminants may still allow MAR but often need extra monitoring or treatment."),
    },
}


def _display_status(status):
    """Map internal DSS status to Feasible / Conditionally Feasible / Not Feasible."""
    return _STATUS_DISPLAY.get(status, status)


def _get_status_color(status):
    """Color for displayed feasibility status (accepts internal or display labels)."""
    display = _display_status(status) if status in _STATUS_DISPLAY else status
    if display in _STATUS_COLORS:
        return _STATUS_COLORS[display]
    # Fallback for legacy strings
    legacy = {
        "Recommended": "success",
        "Recommended with Warnings": "success",
        "Conditionally Recommended": "info",
        "Rejected": "danger",
    }
    return legacy.get(status, "secondary")


def _format_cost(cost):
    """Format cost for display."""
    if isinstance(cost, list):
        if len(cost) == 0:
            return "To Be Calculated"
        return f"{len(cost)} cost items"
    if isinstance(cost, (int, float)):
        return f"${cost:,.0f}"
    return str(cost)


def _round_to_nearest_thousand(value):
    """Round a dollar amount to the nearest $1,000."""
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return 0.0
        amount = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(amount) or amount <= 0:
        return 0.0
    return float(round(amount / 1000.0) * 1000)


def _format_usd_nearest_thousand(value):
    """Format a dollar amount rounded to the nearest $1,000."""
    rounded = _round_to_nearest_thousand(value)
    if rounded <= 0:
        return "—"
    return f"${rounded:,.0f}"


def _series_value(series_or_none, column):
    if series_or_none is None or not column:
        return 0.0
    try:
        if column not in series_or_none.index:
            return 0.0
        raw = series_or_none[column]
        if pd.isna(raw):
            return 0.0
        val = float(raw)
        return val if math.isfinite(val) else 0.0
    except (TypeError, ValueError, AttributeError):
        return 0.0


def _npv_dict_from_storage():
    """Coerce dash_storage ``net_val`` to a plain dict of NPV column → value."""
    raw = dash_storage.get_data("net_val")
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, pd.Series):
        return {k: raw[k] for k in raw.index}
    return {}


def _option_cost_totals(option_name):
    """Return capital, annual maintenance, and NPV for an option (raw dollars)."""
    capital = coerce_storage_cost_totals(dash_storage.get_data("capital_cost_num"), CAPITAL_COST_TOTAL_KEYS)
    maintenance = coerce_storage_cost_totals(dash_storage.get_data("maintenance_cost_num"), MAINTENANCE_COST_TOTAL_KEYS)
    npv_dict = _npv_dict_from_storage()

    capital_val = _series_value(capital, _OPTION_TO_CAPITAL_COL.get(option_name))
    maintenance_val = _series_value(maintenance, _OPTION_TO_MAINTENANCE_COL.get(option_name))
    npv_col = _OPTION_TO_NPV_COL.get(option_name)
    npv_val = 0.0
    if npv_col and npv_col in npv_dict:
        try:
            raw = npv_dict[npv_col]
            if raw is not None and not (isinstance(raw, float) and pd.isna(raw)):
                npv_val = float(raw)
                if not math.isfinite(npv_val):
                    npv_val = 0.0
        except (TypeError, ValueError):
            npv_val = 0.0

    return capital_val, maintenance_val, npv_val


def _cost_line(label, value_text, emphasize=False):
    value_class = "di-cost-value-lg" if emphasize else "di-cost-value"
    return html.Div(
        [
            html.Div(label, className="di-cost-label"),
            html.Div(value_text, className=value_class),
        ],
        className="di-cost-row",
    )


def _cost_section_body(option_name, legacy_cost, not_feasible=False):
    """Build capital / maintenance / NPV display for an option.

    Not-feasible options show N/A for all cost fields (same policy as Cost Analysis).
    """
    if not_feasible:
        return html.Div(
            [
                _cost_line("Capital Cost (Total)", "N/A", emphasize=True),
                _cost_line("Annual Maintenance Cost", "N/A"),
                _cost_line("20-Year Net Present Value", "N/A"),
            ],
            className="di-cost-block",
        )

    capital, maintenance, npv = _option_cost_totals(option_name)
    has_stored = capital > 0 or maintenance > 0 or npv > 0

    if has_stored:
        return html.Div(
            [
                _cost_line(
                    "Capital Cost (Total)",
                    _format_usd_nearest_thousand(capital),
                    emphasize=True,
                ),
                _cost_line(
                    "Annual Maintenance Cost",
                    _format_usd_nearest_thousand(maintenance),
                ),
                _cost_line(
                    "20-Year Net Present Value",
                    _format_usd_nearest_thousand(npv),
                ),
            ],
            className="di-cost-block",
        )

    # Fallback to DSS result cost field when cost analysis has not been run
    if isinstance(legacy_cost, list):
        if legacy_cost:
            return html.Ul(
                [html.Li(item if isinstance(item, str) else str(item)) for item in legacy_cost],
                className="mb-0 di-list",
            )
        return html.P(
            "Cost items to be calculated. Run Cost Analysis to populate totals.",
            className="text-muted mb-0 small",
        )
    return html.P(
        f"Total Cost: {_format_cost(legacy_cost)}",
        className="mb-0",
    )


def _metric_card(value, label, value_class="text-primary"):
    return dbc.Col(
        html.Div(
            [
                html.Div(value, className=f"di-metric-value {value_class}"),
                html.Div(label, className="di-metric-label"),
            ],
            className="di-metric",
        ),
        width=6,
        className="mb-2",
    )


def _section(title, children, accent=None):
    # accent kept for call-site compatibility; section titles use dashboard blue
    return html.Div(
        [
            html.H6(title, className="di-section-title"),
            html.Div(children, className="di-section-body"),
        ],
        className="di-section",
    )


def _constraint_help_btn(constraint_name):
    return html.Button(
        "?",
        id={"type": "di-constraint-help-btn", "name": constraint_name},
        type="button",
        className="mar-help-btn eng-help-btn di-constraint-help-btn",
        title=f"Help: {constraint_name}",
    )


def _constraint_name_cell(constraint_name):
    display_name = _title_case_label(constraint_name)
    return html.Td(
        html.Div(
            [
                html.Span(display_name, className="di-constraint-name"),
                _constraint_help_btn(constraint_name),
            ],
            className="d-flex align-items-center justify-content-between gap-2",
        ),
    )


def constraint_help_body(constraint_name):
    """Build modal body content for a constraint help entry."""
    info = CONSTRAINT_HELP.get(constraint_name)
    if info is None:
        # Tolerate Title Case / original-case key mismatches
        for key, value in CONSTRAINT_HELP.items():
            if _title_case_label(key) == _title_case_label(constraint_name):
                info = value
                break
    display_name = _title_case_label(constraint_name)
    if not info:
        return [
            html.P(
                f'No detailed help is defined yet for "{display_name}".',
                className="mb-0",
            ),
        ]
    return [
        html.P(
            [html.Strong("What It Means: "), info["meaning"]],
            className="mb-2",
        ),
        html.P(
            [html.Strong("How It Is Triggered: "), info["triggered"]],
            className="mb-2",
        ),
        html.P(
            [html.Strong("Why It Matters: "), info["why"]],
            className="mb-0",
        ),
    ]


def _constraint_help_modal():
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle(id="di-constraint-help-title", children="Constraint Help"),
                close_button=True,
            ),
            dbc.ModalBody(id="di-constraint-help-body"),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="di-constraint-help-close",
                    className="ms-auto",
                    color="secondary",
                ),
            ),
        ],
        id="di-constraint-help-modal",
        size="lg",
        scrollable=True,
        is_open=False,
    )


def _enrich_issue_labels(labels, soft_constraints):
    """Replace bare constraint names with data-gap vs finding-specific text.

    Prefer penalty text from soft constraints so Unknown answers say \"data gap\"
    and confirmed issues (e.g. contamination) say that. Already-descriptive
    labels from the DSS are left unchanged when they include detail after ':'.
    """
    try:
        from mar_dss.mar.dss import _format_soft_issue_message
    except ImportError:
        from ...mar.dss import _format_soft_issue_message

    by_name = {sc.get("name"): sc for sc in (soft_constraints or []) if isinstance(sc, dict) and sc.get("name")}
    enriched = []
    for label in labels or []:
        text = label if isinstance(label, str) else str(label)
        # Already enriched by DSS (Name: detail)
        if ": " in text and not text.endswith(":"):
            name_part = text.split(":", 1)[0].strip()
            if name_part in by_name:
                enriched.append(_format_soft_issue_message(by_name[name_part]))
                continue
            enriched.append(text)
            continue
        sc = by_name.get(text)
        if sc is not None:
            enriched.append(_format_soft_issue_message(sc))
        else:
            enriched.append(text)
    return enriched


def _create_option_interpretation(option_name, result, filters=None):
    """Create detailed interpretation content for a selected option."""
    status = result.get("status", "Unknown")
    display_status = _display_status(status)
    cost = result.get("cost", [])
    warnings = result.get("warnings", [])
    mitigations = result.get("mitigations", [])

    hard_constraints = []
    soft_constraints = []
    if filters and option_name in filters:
        filter_data = filters[option_name]
        hard_constraints = filter_data.get("hard", [])
        soft_constraints = filter_data.get("soft", [])

    warnings = _enrich_issue_labels(warnings, soft_constraints)
    mitigations = _enrich_issue_labels(mitigations, soft_constraints)

    status_color = _get_status_color(status)

    sections = [
        html.Div(
            [
                html.Div(
                    [
                        html.H5(option_name, className="di-option-name mb-0"),
                        dbc.Badge(
                            display_status,
                            color=status_color,
                            className="di-status-badge",
                        ),
                    ],
                    className=("d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3"),
                ),
                dbc.Row(
                    [
                        _metric_card(str(len(warnings)), "Warnings", "text-warning"),
                        _metric_card(str(len(mitigations)), "Mitigations", "text-info"),
                    ],
                    className="g-2 mb-1",
                ),
                dbc.Alert(
                    _get_status_interpretation(status, warnings, mitigations),
                    color=status_color,
                    className="di-status-alert mb-0",
                ),
            ],
            className="di-option-header",
        ),
    ]

    sections.append(
        _section(
            "Cost Information",
            _cost_section_body(
                option_name,
                cost,
                not_feasible=(display_status == "Not Feasible"),
            ),
        ),
    )

    if warnings:
        sections.append(
            _section(
                "Warnings",
                html.Ul(
                    [html.Li(w) for w in warnings],
                    className="mb-0 di-list di-list-warning",
                ),
                accent="warning",
            ),
        )

    if mitigations:
        sections.append(
            _section(
                "Required Mitigations",
                html.Ul(
                    [html.Li(m) for m in mitigations],
                    className="mb-0 di-list di-list-info",
                ),
                accent="info",
            ),
        )

    if hard_constraints:
        hard_rows = []
        for hc in hard_constraints:
            passed = hc.get("pass", False)
            hard_rows.append(
                html.Tr(
                    [
                        _constraint_name_cell(hc.get("name", "Unknown")),
                        html.Td(
                            dbc.Badge(
                                "Pass" if passed else "Fail",
                                color="success" if passed else "danger",
                            ),
                        ),
                        html.Td(hc.get("why", "No Explanation Available")),
                    ],
                ),
            )
        sections.append(
            _section(
                "Hard Constraints",
                dbc.Table(
                    [
                        html.Thead(
                            html.Tr(
                                [
                                    html.Th("Constraint"),
                                    html.Th("Status"),
                                    html.Th("Explanation"),
                                ],
                            ),
                        ),
                        html.Tbody(hard_rows),
                    ],
                    bordered=False,
                    hover=True,
                    responsive=True,
                    className="mb-0 table-sm di-table",
                ),
            ),
        )

    if soft_constraints:
        soft_rows = []
        for sc in soft_constraints:
            response = sc.get("response", 0)
            if response == -1:
                continue
            penalty = sc.get("penalty", [])
            soft_rows.append(
                html.Tr(
                    [
                        _constraint_name_cell(sc.get("name", "Unknown")),
                        html.Td(
                            dbc.Badge(
                                _RESPONSE_LABELS.get(response, "Unknown"),
                                color=_RESPONSE_COLORS.get(response, "secondary"),
                                className="text-wrap",
                            ),
                        ),
                        html.Td(
                            html.Ul(
                                [html.Li(p if isinstance(p, str) else str(p)) for p in penalty],
                                className="mb-0 di-list-compact",
                            )
                            if isinstance(penalty, list) and penalty
                            else html.Span("None", className="text-muted"),
                        ),
                    ],
                ),
            )
        if soft_rows:
            sections.append(
                _section(
                    "Soft Constraints",
                    dbc.Table(
                        [
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th("Constraint"),
                                        html.Th("Response"),
                                        html.Th("Notes"),
                                    ],
                                ),
                            ),
                            html.Tbody(soft_rows),
                        ],
                        bordered=False,
                        hover=True,
                        responsive=True,
                        className="mb-0 table-sm di-table",
                    ),
                ),
            )

    return html.Div(sections, className="di-details")


def _get_status_interpretation(status, warnings, mitigations):
    """Get interpretation text for a status (uses Feasible wording)."""
    display = _display_status(status)
    if display == "Feasible" and status == "Recommended with Warnings":
        return (
            f"Feasible, with {len(warnings)} warning(s) to monitor during "
            "implementation or operation. Hard constraints pass; soft constraints "
            "raised warnings but do not require mitigation to proceed."
        )
    if display == "Feasible":
        return (
            "Feasible for implementation. No mitigations are required. It meets hard "
            "constraints and has acceptable soft-constraint responses."
        )
    if display == "Conditionally Feasible":
        return f"Conditionally feasible — address {len(mitigations)} mitigation measure(s) before proceeding."
    if display == "Not Feasible":
        return (
            "Not feasible under current inputs: hard-constraint failures or critical "
            "soft-constraint violations that cannot be mitigated."
        )
    return "Status interpretation not available."


def _empty_state():
    return html.Div(
        [
            _constraint_help_modal(),
            dbc.Card(
                [
                    dbc.CardHeader(
                        "Decision Interpretation",
                        className="fw-bold text-white py-2",
                        style=_HEADER_STYLE,
                    ),
                    dbc.CardBody(
                        dbc.Alert(
                            "No evaluation results available. Run the feasibility "
                            "analysis first to interpret MAR option decisions.",
                            color="info",
                            className="mb-0",
                        ),
                        className="p-3",
                    ),
                ],
                className="di-panel shadow-sm",
            ),
        ],
        className="di-root",
    )


def create_decision_interpretation_content():
    """Create content for Decision Interpretation tab."""
    dss_results = dash_storage.get_data("dss_results")

    if dss_results is None or not hasattr(dss_results, "results") or not dss_results.results:
        return _empty_state()

    option_names = list(dss_results.results.keys())

    return html.Div(
        [
            _constraint_help_modal(),
            dbc.Card(
                [
                    dbc.CardHeader(
                        "Decision Interpretation",
                        className="fw-bold text-white py-2",
                        style=_HEADER_STYLE,
                    ),
                    dbc.CardBody(
                        [
                            html.P(
                                "Review why each MAR option is feasible, conditionally "
                                "feasible, or not feasible — including costs, warnings, "
                                "mitigations, and constraint results.",
                                className="di-lead text-muted mb-3",
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        "MAR Technology Option",
                                        className="di-label form-label fw-bold mb-2",
                                    ),
                                    dcc.Dropdown(
                                        id="decision-interpretation-option-selector",
                                        options=[
                                            {
                                                "label": _title_case_label(name),
                                                "value": name,
                                            }
                                            for name in option_names
                                        ],
                                        value=option_names[0] if option_names else None,
                                        placeholder="Select an option…",
                                        className="di-dropdown",
                                    ),
                                ],
                                className="di-dropdown-highlight mb-2",
                            ),
                            dbc.Tooltip(
                                "Choose an option to see its decision narrative and constraint evaluation.",
                                target="decision-interpretation-option-selector",
                                placement="bottom",
                            ),
                            html.Div(
                                id="decision-interpretation-details",
                                className="mt-3",
                            ),
                        ],
                        className="p-3",
                    ),
                ],
                className="di-panel shadow-sm",
            ),
        ],
        className="di-root",
    )
