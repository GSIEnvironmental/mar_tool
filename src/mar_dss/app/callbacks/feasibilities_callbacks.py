"""
Callbacks for the Feasibilities tab.
"""

import json
import logging
import math
import string
from datetime import datetime

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, dcc, html

import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.utils.cost_storage import (
    CAPITAL_COST_TOTAL_KEYS,
    MAINTENANCE_COST_TOTAL_KEYS,
    coerce_storage_cost_totals,
)

logger = logging.getLogger(__name__)

_NPV_VALUE_COLS = (
    "Spreading Pond Net Present Value ($)",
    "Injection Wells Net Present Value ($)",
    "Dry Wells Net Present Value ($)",
)

# Model recharge volumes are computed in ft³/yr; convert to acre-ft for $/acre-ft metrics.
_FT3_PER_ACRE_FT = 43560.0

MAR_ENGINEERING_OPTIONS = ("Surface Recharge", "Injection Well", "Dry Well")

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

_OPTION_CARD_STYLE = {
    "Surface Recharge": {"color": "#28a745", "bg": "#e8f5e9", "icon": "fas fa-water"},
    "Injection Well": {"color": "#0d6efd", "bg": "#e7f1ff", "icon": "fas fa-arrow-down"},
    "Dry Well": {"color": "#fd7e14", "bg": "#fff3e6", "icon": "fas fa-circle-arrow-down"},
}


def _annual_recharged_volume_acre_ft(option_name):
    """Annual recharged volume (acre-ft/yr) for a MAR option from the decision graph."""
    graph = dash_storage.get_data("decision_graph")
    if graph is None:
        return 0.0

    confined = bool(graph.get_node_value("confined"))
    if option_name == "Surface Recharge":
        vol_ft3 = graph.get_node_value("annual_surface_recharge_volume")
    elif option_name == "Injection Well":
        if confined:
            vol_ft3 = graph.get_node_value("annual_confined_storage_volume")
        else:
            vol_ft3 = graph.get_node_value("annual_injection_volume")
    elif option_name == "Dry Well":
        vol_ft3 = graph.get_node_value("annual_dry_well_volume")
    else:
        vol_ft3 = None

    if vol_ft3 is None:
        return 0.0
    try:
        vol = float(vol_ft3)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(vol) or vol <= 0:
        return 0.0
    return vol / _FT3_PER_ACRE_FT


def _format_currency(val):
    """Format a dollar amount for compact display."""
    if val is None or not math.isfinite(val) or val <= 0:
        return "—"
    if val >= 1e6:
        return f"${val / 1e6:.2f}M"
    if val >= 1e3:
        return f"${val / 1e3:.0f}K"
    return f"${val:,.0f}"


# Feasibility Summary cost uncertainty band (−20% / +50%)
_COST_RANGE_LOW_FACTOR = 0.80
_COST_RANGE_HIGH_FACTOR = 1.50

# Heatmap / legend response labels (Title Case for consistent graph text)
_RESPONSE_LEVEL_LABELS = {
    -1: "Not Applicable",
    0: "Acceptable",
    1: "Acceptable With Additional Cost",
    2: "Warning",
    3: "Mitigation Needed",
    4: "Reject",
}


def _title_case_label(text):
    """Capitalize the first letter of each word for graph / legend labels."""
    if text is None:
        return ""
    text = str(text).strip()
    if not text:
        return text
    return string.capwords(text)


def _format_currency_range(val):
    """Format a cost as a low–high range (−20% to +50%)."""
    if val is None or not math.isfinite(val) or val <= 0:
        return "—"
    low = val * _COST_RANGE_LOW_FACTOR
    high = val * _COST_RANGE_HIGH_FACTOR
    return f"{_format_currency(low)} – {_format_currency(high)}"


def _format_per_acre_ft(val):
    """Format a cost per acre-ft value (nearest $100)."""
    if val is None or not math.isfinite(val) or val <= 0:
        return "—"
    rounded = round(val / 100.0) * 100.0
    return f"${rounded:,.0f}/acre-ft"


def _round_to_nearest(val, step):
    """Round ``val`` to the nearest multiple of ``step``."""
    return round(val / step) * step


def _format_per_acre_ft_range(val):
    """Format a unit cost as a low–high range (−20% to +50%), nearest $100.

    When both ends round to the same $100 bucket (common for O&M near
    ~$60–$100/acre-ft), fall back to nearest $10 so the Class 5 band stays visible.
    """
    if val is None or not math.isfinite(val) or val <= 0:
        return "—"
    low = val * _COST_RANGE_LOW_FACTOR
    high = val * _COST_RANGE_HIGH_FACTOR
    low_r = _round_to_nearest(low, 100.0)
    high_r = _round_to_nearest(high, 100.0)
    # $100 steps collapse or go to $0 for small unit O&M — use $10 instead.
    if low_r == high_r or low_r <= 0:
        low_r = _round_to_nearest(low, 10.0)
        high_r = _round_to_nearest(high, 10.0)
    if low_r == high_r:
        return f"${low:,.0f} – ${high:,.0f}/acre-ft"
    return f"${low_r:,.0f} – ${high_r:,.0f}/acre-ft"


def _format_volume_acre_ft(val):
    """Format annual recharge volume in acre-ft/yr."""
    if val is None or not math.isfinite(val) or val <= 0:
        return "—"
    return f"{val:,.1f} acre-ft/yr"


def _recharge_percentage(option_name):
    """Share of source water recharged (%) for a MAR option from the decision graph."""
    graph = dash_storage.get_data("decision_graph")
    if graph is None:
        return None

    confined = bool(graph.get_node_value("confined"))
    if option_name == "Injection Well" and confined:
        raw = graph.get_node_value("confined_rechargability")
    else:
        rechargability = graph.get_node_value("rechargability") or {}
        if not isinstance(rechargability, dict):
            rechargability = {}
        key = {
            "Surface Recharge": "surface_recharge_percentage",
            "Injection Well": "injection_recharge_percentage",
            "Dry Well": "dry_well_recharge_percentage",
        }.get(option_name)
        raw = rechargability.get(key) if key else None

    try:
        pct = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(pct) or pct < 0:
        return None
    return min(pct, 100.0)


def _format_recharge_percent(val):
    """Format recharge share of source water as a percentage (capped at 100%)."""
    if val is None or not math.isfinite(val) or val < 0:
        return "—"
    return f"{min(val, 100.0):.1f}%"


def _well_counts_from_graph():
    """Return (n_injection_wells, n_dry_wells) from the decision graph."""
    graph = dash_storage.get_data("decision_graph")
    n_injection = None
    n_dry = None
    if graph is None:
        return n_injection, n_dry

    injection_result = graph.get_node_value("number_of_injection_wells")
    if isinstance(injection_result, dict):
        raw = injection_result.get("number_of_wells")
        try:
            n_injection = int(float(raw)) if raw is not None else None
        except (TypeError, ValueError):
            n_injection = None

    dry_result = graph.get_node_value("number_of_dry_wells")
    if isinstance(dry_result, dict):
        raw = dry_result.get("number_of_dry_wells")
        try:
            n_dry = int(float(raw)) if raw is not None else None
        except (TypeError, ValueError):
            n_dry = None

    return n_injection, n_dry


def _format_well_count(n):
    """Format a required well count for summary display."""
    if n is None:
        return "—"
    try:
        count = int(n)
    except (TypeError, ValueError):
        return "—"
    if count < 0:
        return "—"
    return f"{count:,}"


def _collect_engineering_option_economics():
    """Collect capital, O&M, volume, well counts, and unit-cost metrics for each MAR option."""
    capital_cost_num = coerce_storage_cost_totals(dash_storage.get_data("capital_cost_num"), CAPITAL_COST_TOTAL_KEYS)
    maintenance_cost_num = coerce_storage_cost_totals(
        dash_storage.get_data("maintenance_cost_num"),
        MAINTENANCE_COST_TOTAL_KEYS,
    )
    n_injection, n_dry = _well_counts_from_graph()

    economics = []
    for option_name in MAR_ENGINEERING_OPTIONS:
        capital_col = _OPTION_TO_CAPITAL_COL.get(option_name)
        maintenance_col = _OPTION_TO_MAINTENANCE_COL.get(option_name)

        capital_val = 0.0
        if capital_col and capital_cost_num is not None and capital_col in capital_cost_num.index:
            raw = capital_cost_num[capital_col]
            capital_val = float(raw) if pd.notna(raw) else 0.0

        maintenance_val = 0.0
        if maintenance_col and maintenance_cost_num is not None and maintenance_col in maintenance_cost_num.index:
            raw = maintenance_cost_num[maintenance_col]
            maintenance_val = float(raw) if pd.notna(raw) else 0.0

        acre_ft = _annual_recharged_volume_acre_ft(option_name)
        recharge_pct = _recharge_percentage(option_name)
        if option_name == "Injection Well":
            wells_required = n_injection
            wells_label = "Injection Wells Required"
        elif option_name == "Dry Well":
            wells_required = n_dry
            wells_label = "Dry Wells Required"
        else:
            wells_required = None
            wells_label = None

        economics.append(
            {
                "name": option_name,
                "capital": capital_val,
                "maintenance": maintenance_val,
                "acre_ft": acre_ft,
                "recharge_pct": recharge_pct,
                "capital_per_acre_ft": capital_val / acre_ft if acre_ft > 0 and capital_val > 0 else None,
                "maintenance_per_acre_ft": maintenance_val / acre_ft if acre_ft > 0 and maintenance_val > 0 else None,
                "wells_required": wells_required,
                "wells_label": wells_label,
            },
        )
    return economics


def _is_option_not_feasible(categorized_data, option_name):
    """True when the option failed feasibility (rejected)."""
    rejected_names = {opt["name"] for opt in categorized_data.get("rejected", [])}
    return option_name in rejected_names


def _option_feasibility_badges(categorized_data):
    """Map option names to feasibility badge label and color."""
    badges = {}
    for opt in categorized_data.get("recommended", []):
        badges[opt["name"]] = ("Feasible", "success")
    for opt in categorized_data.get("conditional", []):
        badges[opt["name"]] = ("Conditionally Feasible", "warning")
    for opt in categorized_data.get("rejected", []):
        badges[opt["name"]] = ("Not Feasible", "danger")
    return badges


def _option_metric_row(label, value, *, highlight=False):
    """Single label/value row for an option economics card."""
    # Match Analysis / Feasibility tab label readability (~1rem).
    _text_style = {"fontSize": "1rem"}
    value_class = "fw-semibold text-end mb-0"
    if highlight:
        value_class += " text-primary"
    return dbc.Row(
        [
            dbc.Col(
                html.Span(label, className="text-muted", style=_text_style),
                width=7,
                className="pe-0",
            ),
            dbc.Col(
                html.P(value, className=value_class, style=_text_style),
                width=5,
            ),
        ],
        className="g-1 mb-2 align-items-center",
    )


def _build_engineering_options_summary(categorized_data):
    """Build option cards showing cost, recharge volume, and unit economics."""
    economics = _collect_engineering_option_economics()
    badges = _option_feasibility_badges(categorized_data)
    cards = []

    for econ in economics:
        name = econ["name"]
        style = _OPTION_CARD_STYLE.get(name, {"color": "#1e3a5f", "bg": "#f8f9fa", "icon": "fas fa-circle"})
        badge_label, badge_color = badges.get(name, ("Not Evaluated", "secondary"))
        not_feasible = badge_label == "Not Feasible"
        capital_display = "N/A" if not_feasible else _format_currency_range(econ["capital"])
        maintenance_display = "N/A" if not_feasible else _format_currency_range(econ["maintenance"])
        capital_unit_display = "N/A" if not_feasible else _format_per_acre_ft_range(econ["capital_per_acre_ft"])
        maintenance_unit_display = "N/A" if not_feasible else _format_per_acre_ft_range(econ["maintenance_per_acre_ft"])

        cards.append(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader(
                            [
                                html.I(className=f"{style['icon']} me-2"),
                                html.Span(name, className="fw-bold"),
                                dbc.Badge(
                                    badge_label,
                                    color=badge_color,
                                    className="float-end",
                                    style={
                                        "fontSize": "0.9rem",
                                        **(
                                            {
                                                "border": "1px solid #000",
                                                "boxShadow": "none",
                                            }
                                            if badge_label == "Feasible"
                                            else {}
                                        ),
                                    },
                                ),
                            ],
                            className="text-white py-2",
                            style={"backgroundColor": style["color"], "fontSize": "1rem"},
                        ),
                        dbc.CardBody(
                            [
                                html.Div(
                                    f"Project Costs ({datetime.now().year})",
                                    className="text-uppercase text-muted fw-semibold mb-2",
                                    style={"fontSize": "0.9rem", "letterSpacing": "0.05em"},
                                ),
                                _option_metric_row("Capital Cost", capital_display),
                                _option_metric_row("Annual O&M Cost", maintenance_display),
                                html.Hr(className="my-2"),
                                html.Div(
                                    "Recharge Performance",
                                    className="text-uppercase text-muted fw-semibold mb-2",
                                    style={"fontSize": "0.9rem", "letterSpacing": "0.05em"},
                                ),
                                _option_metric_row(
                                    "Total Annual Recharge",
                                    _format_volume_acre_ft(econ["acre_ft"]),
                                    highlight=True,
                                ),
                                _option_metric_row(
                                    "Recharge %",
                                    ("N/A" if not_feasible else _format_recharge_percent(econ.get("recharge_pct"))),
                                ),
                                *(
                                    [
                                        _option_metric_row(
                                            econ["wells_label"],
                                            ("N/A" if not_feasible else _format_well_count(econ["wells_required"])),
                                        ),
                                    ]
                                    if econ.get("wells_label")
                                    else []
                                ),
                                html.Hr(className="my-2"),
                                html.Div(
                                    "Unit Economics",
                                    className="text-uppercase text-muted fw-semibold mb-2",
                                    style={"fontSize": "0.9rem", "letterSpacing": "0.05em"},
                                ),
                                _option_metric_row(
                                    "Capital Cost / Volume/Year",
                                    capital_unit_display,
                                ),
                                _option_metric_row(
                                    "O&M Cost / Volume/Year",
                                    maintenance_unit_display,
                                ),
                            ],
                            style={"backgroundColor": style["bg"], "padding": "1rem"},
                        ),
                    ],
                    className="h-100 shadow-sm border-0 w-100",
                    style={"borderTop": f"4px solid {style['color']}"},
                ),
                className="d-flex px-1",
                lg=4,
                md=4,
                sm=12,
            ),
        )

    return html.Div(
        dbc.Row(cards, className="g-0 mx-0 w-100"),
        className="w-100",
    )


def _efficiency_from_min_ratio(value, min_positive):
    """Map a positive metric to 0–100 where the minimum value scores 100."""
    if value > 0 and min_positive > 0:
        return max(0.0, min(100.0, 100.0 * (min_positive / value)))
    return 0.0


def _normalize_net_val_dict(raw):
    """Coerce dash_storage ``net_val`` to a dict keyed by NPV column names."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, pd.Series):
        out = {}
        for c in _NPV_VALUE_COLS:
            if c in raw.index:
                out[c] = raw[c]
        return out
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {}
    if isinstance(raw, (list, tuple)):
        vals = list(raw)
        cols = list(_NPV_VALUE_COLS)
        if len(vals) == len(cols):
            return {cols[i]: vals[i] for i in range(len(cols))}
        return {}
    try:
        arr = getattr(raw, "flatten", lambda: None)()
        if arr is None:
            return {}
        size = getattr(arr, "size", len(arr) if hasattr(arr, "__len__") else 0)
        cols = list(_NPV_VALUE_COLS)
        if size == len(cols):
            flat = arr.tolist() if hasattr(arr, "tolist") else list(arr)
            return {cols[i]: flat[i] for i in range(len(cols))}
    except (TypeError, ValueError):
        pass
    return {}


def _ensure_dss_results_available():
    """Ensure DSS results are available, running analysis if needed.

    This function ensures that Analysis tab callbacks have run before
    Feasibilities tab tries to access the results.
    """
    # First check if DSS results already exist
    dss_results = dash_storage.get_data("dss_results")
    has_dss_results = dss_results is not None and hasattr(dss_results, "results") and dss_results.results

    # Only run analysis if results don't exist
    if not has_dss_results:
        logger.debug("No DSS results found - running feasibility analysis")
        try:
            from mar_dss.app.callbacks.analysis_callbacks import run_feasibility_analysis

            run_feasibility_analysis()
            logger.debug("Feasibility analysis completed")
        except Exception as e:
            logger.error(f"Error running feasibility analysis: {e}", exc_info=True)

        # Get DSS results after running analysis
        dss_results = dash_storage.get_data("dss_results")

        # If still no results, try running integrated analysis directly
        if dss_results is None or not hasattr(dss_results, "results") or not dss_results.results:
            logger.info("No DSS results found after feasibility analysis. Running integrated analysis directly...")
            try:
                from mar_dss.app.callbacks.analysis_callbacks import run_integrated_analysis

                dss_results, _ = run_integrated_analysis()
                logger.info("Integrated analysis completed successfully")
            except Exception as e:
                logger.error(f"Error running integrated analysis: {e}", exc_info=True)
    else:
        logger.debug("DSS results already available - skipping analysis")

    return dss_results


def _get_empty_dashboard_content(is_dark=False):
    """Return empty dashboard content when no DSS results are available."""
    empty_engineering_summary = _build_empty_engineering_options_summary()
    font_color = "#f8f9fa" if is_dark else "#212529"
    template = "plotly_dark" if is_dark else "plotly_white"
    paper_bg = "rgba(0,0,0,0)" if is_dark else "white"

    empty_hydro_heatmap_fig = go.Figure()
    empty_hydro_heatmap_fig.update_layout(
        title=None,
        template=template,
        height=300,
        paper_bgcolor=paper_bg,
        font={"color": font_color},
        margin={"t": 30},
    )

    empty_hydro_heatmap_legend = html.Div()

    empty_env_heatmap_fig = go.Figure()
    empty_env_heatmap_fig.update_layout(
        title=None,
        template=template,
        height=300,
        paper_bgcolor=paper_bg,
        font={"color": font_color},
        margin={"t": 30},
    )

    empty_env_heatmap_legend = html.Div()

    empty_capital_fig = go.Figure()
    empty_capital_fig.update_layout(
        title={"text": "Capital Cost", "font": {"color": font_color}},
        template=template,
        height=300,
        paper_bgcolor=paper_bg,
        font={"color": font_color},
    )

    empty_maintenance_fig = go.Figure()
    empty_maintenance_fig.update_layout(
        title={"text": "Maintenance Cost", "font": {"color": font_color}},
        template=template,
        height=300,
        paper_bgcolor=paper_bg,
        font={"color": font_color},
    )

    empty_npv_fig = go.Figure()
    empty_npv_fig.update_layout(
        title={"text": "20-Year Net Present Value", "font": {"color": font_color}},
        template=template,
        height=300,
        paper_bgcolor=paper_bg,
        font={"color": font_color},
    )

    empty_spider_plots = html.Div(
        "No DSS evaluation results available. Please run the feasibility analysis first.",
        className="text-muted text-center p-4",
    )

    return (
        empty_engineering_summary,
        empty_hydro_heatmap_fig,
        empty_hydro_heatmap_legend,
        empty_env_heatmap_fig,
        empty_env_heatmap_legend,
        empty_capital_fig,
        empty_maintenance_fig,
        empty_npv_fig,
        empty_spider_plots,
    )


def _categorize_options(results, filters):
    """Categorize options into recommended, conditional, and rejected based on DSS results."""
    recommended = []
    conditional = []
    rejected = []

    # Count statistics for funnel
    total_options = len(results)
    hard_constraint_fails = 0
    soft_rule_rejects = 0
    after_hard_constraints = 0
    after_soft_rules = 0
    recommended_count = 0

    for option_name, result in results.items():
        status = result.get("status", "Unknown")
        cost = result.get("cost", [])
        benefit_score = result.get("benefit_score", 0.0) * 100  # Convert to percentage
        warnings = result.get("warnings", [])
        mitigations = result.get("mitigations", [])

        # Format cost - get base cost from option if available
        cost_mapping = dash_storage.get_data("cost_mapping")
        if cost_mapping and option_name in cost_mapping:
            cost_data = cost_mapping[option_name]
            if isinstance(cost_data, dict):
                cost_val = cost_data.get("capital", 0)
            else:
                cost_val = float(cost_data) if cost_data else 0
        elif isinstance(cost, list):
            if len(cost) > 0:
                try:
                    cost_val = sum(float(c) for c in cost if isinstance(c, (int, float, str)))
                except (ValueError, TypeError):
                    cost_val = 0
            else:
                cost_val = 0
        else:
            cost_val = float(cost) if cost else 0

        cost_str = (
            f"${cost_val / 1e6:.1f}M" if cost_val >= 1e6 else f"${cost_val / 1e3:.0f}K" if cost_val > 0 else "N/A"
        )

        # Check filters to count hard constraint fails
        passed_hard = True
        passed_soft = True

        if option_name in filters:
            filter_data = filters[option_name]
            hard_constraints = filter_data.get("hard", [])
            soft_constraints = filter_data.get("soft", [])

            # Check hard constraint failures
            failed_hard = [hc for hc in hard_constraints if not hc.get("pass", True)]
            if failed_hard:
                hard_constraint_fails += 1
                passed_hard = False
                rejected.append(
                    {
                        "name": option_name,
                        "reason": f"Hard constraint: {', '.join([hc.get('name', 'Unknown') for hc in failed_hard])}",
                    },
                )
            else:
                after_hard_constraints += 1

            # Check soft rule rejects (level 4 or hard soft constraints with level >= 2)
            rejected_soft_list = []
            for sc in soft_constraints:
                response = sc.get("response", 0)
                is_hard = sc.get("hard", True)
                if response == 4 or (is_hard and response >= 2):
                    rejected_soft_list.append(sc.get("name", "Unknown"))

            if rejected_soft_list:
                soft_rule_rejects += 1
                passed_soft = False
                if passed_hard:  # Only add to rejected if it passed hard constraints
                    rejected.append(
                        {"name": option_name, "reason": f"Soft rule reject: {', '.join(rejected_soft_list)}"},
                    )
            elif passed_hard:
                after_soft_rules += 1
        else:
            # No filters available, assume passed if status is not Rejected
            if status != "Rejected":
                after_hard_constraints += 1
                after_soft_rules += 1

        # Only categorize if it passed both hard and soft constraints
        if not passed_hard or not passed_soft:
            continue

        # Categorize by status
        if status == "Recommended":
            recommended.append(
                {
                    "name": option_name,
                    "cost": cost_str,
                    "benefit": f"{benefit_score:.0f}",
                    "description": "Meets all feasibility criteria",
                },
            )
            recommended_count += 1
        elif status == "Conditionally Recommended":
            conditional.append(
                {
                    "name": option_name,
                    "cost": cost_str,
                    "benefit": f"{benefit_score:.0f}",
                    "requirements": ", ".join(mitigations) if mitigations else "Additional review required",
                },
            )
        elif status == "Recommended with Warnings":
            recommended.append(
                {
                    "name": option_name,
                    "cost": cost_str,
                    "benefit": f"{benefit_score:.0f}",
                    "description": f"Warnings: {', '.join(warnings)}" if warnings else "Meets criteria with warnings",
                },
            )
            recommended_count += 1
        else:  # Rejected
            rejected.append({"name": option_name, "reason": f"Status: {status}"})

    return {
        "recommended": recommended,
        "conditional": conditional,
        "rejected": rejected,
        "stats": {
            "total_options": total_options,
            "hard_constraint_fails": hard_constraint_fails,
            "soft_rule_rejects": soft_rule_rejects,
            "after_hard_constraints": after_hard_constraints,
            "after_soft_rules": after_soft_rules,
            "recommended_count": recommended_count,
        },
    }


def _build_empty_engineering_options_summary():
    """Placeholder when feasibility analysis has not run yet."""
    return html.Div(
        html.P(
            "No DSS evaluation results available. Please run the feasibility analysis first",
            className="text-muted text-center p-4 mb-0",
        ),
    )


def _prepare_constraints_data(results, filters, constraint_type=None):
    """Prepare constraint data for heatmap, optionally filtered by type.

    Returns
    -------
    sorted_constraints :
        Constraint names for the heatmap columns.
    constraint_data :
        ``{option_name: {constraint_name: response_level}}``.
    detail_data :
        ``{option_name: {constraint_name: detail_text}}`` for hover (penalty /
        why text). Data-gap Unknown answers keep warning level 2 but use
        data-gap wording rather than remediation language.
    """
    all_constraints = set()
    constraint_data = {}  # {option_name: {constraint_name: response_level}}
    detail_data = {}  # {option_name: {constraint_name: detail_text}}

    _RESPONSE_LABELS = dict(_RESPONSE_LEVEL_LABELS)

    for option_name in results:
        constraint_data[option_name] = {}
        detail_data[option_name] = {}
        if option_name in filters:
            filter_data = filters[option_name]
            hard_constraints = filter_data.get("hard", [])
            soft_constraints = filter_data.get("soft", [])

            # Process hard constraints (convert pass/fail to response level)
            # Note: Hard constraints don't have a type, so we only include them when constraint_type is None
            if constraint_type is None:
                for hc in hard_constraints:
                    constraint_name = hc.get("name", "Unknown")
                    all_constraints.add(constraint_name)
                    # Hard constraint: 0 if pass, 4 if fail
                    response_level = 0 if hc.get("pass", True) else 4
                    constraint_data[option_name][constraint_name] = response_level
                    detail_data[option_name][constraint_name] = hc.get("why") or (
                        "Pass" if response_level == 0 else "Fail"
                    )

            # Process soft constraints (use response level directly)
            for sc in soft_constraints:
                constraint_name = sc.get("name", "Unknown")
                constraint_type_value = sc.get("type", "unknown")

                # Filter by constraint type if specified
                if constraint_type is None or constraint_type_value == constraint_type:
                    all_constraints.add(constraint_name)
                    response_level = sc.get("response", 0)
                    penalties = sc.get("penalty") or []
                    if penalties:
                        detail = penalties[0] if isinstance(penalties[0], str) else str(penalties[0])
                    else:
                        detail = _RESPONSE_LABELS.get(response_level, f"Response {response_level}")
                    # If this constraint already exists (from hard), keep the higher severity
                    if constraint_name in constraint_data[option_name]:
                        if response_level >= constraint_data[option_name][constraint_name]:
                            constraint_data[option_name][constraint_name] = response_level
                            detail_data[option_name][constraint_name] = detail
                    else:
                        constraint_data[option_name][constraint_name] = response_level
                        detail_data[option_name][constraint_name] = detail

    # Filter constraint_data to only include constraints that are in all_constraints
    # This ensures we only show constraints that match the type filter
    for option_name in constraint_data:
        constraint_data[option_name] = {k: v for k, v in constraint_data[option_name].items() if k in all_constraints}
        detail_data[option_name] = {k: v for k, v in detail_data[option_name].items() if k in all_constraints}

    return sorted(all_constraints), constraint_data, detail_data


def _create_constraints_heatmap(results, filters, constraint_type=None, title=None, is_dark=False):
    """Create the constraints heatmap chart and legend for a specific constraint type."""
    sorted_constraints, constraint_data, detail_data = _prepare_constraints_data(results, filters, constraint_type)
    option_names = list(results.keys())
    font_color = "#f8f9fa" if is_dark else "#212529"
    grid_color = "#495057" if is_dark else "lightgray"
    plot_bg = "#212529" if is_dark else "white"
    paper_bg = "rgba(0,0,0,0)" if is_dark else "white"

    _RESPONSE_LABELS = dict(_RESPONSE_LEVEL_LABELS)

    show_title = bool(title and str(title).strip())
    title_text = _title_case_label(title) if show_title else None

    if not sorted_constraints or not constraint_data:
        heatmap_fig = go.Figure()
        heatmap_fig.update_layout(
            title={"text": title_text, "font": {"size": 16, "color": font_color}} if show_title else None,
            template="plotly_dark" if is_dark else "plotly_white",
            height=520,
            autosize=True,
            xaxis_title="No Constraints Data Available",
            yaxis_title="",
            paper_bgcolor=paper_bg,
            plot_bgcolor=plot_bg,
            font={"color": font_color},
            margin={"t": 30} if not show_title else None,
        )
        return heatmap_fig, html.Div()

    # Get all option names from results to ensure consistent y-axis across all heatmaps
    all_option_names = [_title_case_label(n) for n in results]
    # Display names (Title Case) while looking up data with original keys
    display_constraints = [_title_case_label(n) for n in sorted_constraints]

    # Prepare data for measles chart (scatter plot with circles)
    x_data = []  # Constraint names (display)
    y_data = []  # Option names (display)
    response_levels = []  # Response levels for coloring
    marker_sizes = []  # Marker sizes (fixed or based on response level)
    status_details = []  # Penalty / why text for hover

    for option_name in option_names:
        option_display = _title_case_label(option_name)
        for constraint_name in sorted_constraints:
            response_level = constraint_data[option_name].get(constraint_name, 0)
            x_data.append(_title_case_label(constraint_name))
            y_data.append(option_display)
            response_levels.append(response_level)
            # Fixed marker size, or could vary based on response level
            marker_sizes.append(34)  # Circle diameter for measles/heatmap markers
            status_details.append(
                detail_data.get(option_name, {}).get(constraint_name)
                or _RESPONSE_LABELS.get(response_level, f"Response {response_level}"),
            )

    # Create color mapping for response levels
    color_map = {
        -1: "#808080",  # Grey for irrelevant
        0: "#28a745",  # Dark Green
        1: "#90ee90",  # Light Green
        2: "#ffc107",  # Yellow/Gold
        3: "#fd7e14",  # Orange
        4: "#dc3545",  # Red
    }

    # Map response levels to colors
    marker_colors = [color_map.get(level, "#cccccc") for level in response_levels]

    # Create scatter plot (measles chart) with circles
    heatmap_fig = go.Figure()

    # Add scatter trace for circles (measles chart)
    # Create separate traces for irrelevant vs relevant constraints for better control
    relevant_indices = [i for i, level in enumerate(response_levels) if level != -1]
    irrelevant_indices = [i for i, level in enumerate(response_levels) if level == -1]

    # Add trace for relevant constraints
    if relevant_indices:
        heatmap_fig.add_trace(
            go.Scatter(
                x=[x_data[i] for i in relevant_indices],
                y=[y_data[i] for i in relevant_indices],
                mode="markers+text",
                marker={
                    "size": [marker_sizes[i] for i in relevant_indices],
                    "color": [marker_colors[i] for i in relevant_indices],
                    "line": {"width": 1.5, "color": "white"},
                    "sizemode": "diameter",
                    "opacity": 0.9,
                },
                text=[str(response_levels[i]) for i in relevant_indices],
                textposition="middle center",
                textfont={"size": 9, "color": "white", "family": "Arial, sans-serif"},
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>%{x}<br>"
                    "Response: %{customdata[1]} (%{customdata[2]})<br>"
                    "%{customdata[3]}<extra></extra>"
                ),
                customdata=[
                    [
                        y_data[i],
                        response_levels[i],
                        _RESPONSE_LABELS.get(response_levels[i], str(response_levels[i])),
                        status_details[i],
                    ]
                    for i in relevant_indices
                ],
                showlegend=False,
            ),
        )

    # Add trace for irrelevant constraints (greyed out)
    if irrelevant_indices:
        heatmap_fig.add_trace(
            go.Scatter(
                x=[x_data[i] for i in irrelevant_indices],
                y=[y_data[i] for i in irrelevant_indices],
                mode="markers+text",
                marker={
                    "size": [marker_sizes[i] for i in irrelevant_indices],
                    "color": [marker_colors[i] for i in irrelevant_indices],
                    "line": {"width": 1, "color": "#666666"},
                    "sizemode": "diameter",
                    "opacity": 0.4,
                },
                text=["—" for _ in irrelevant_indices],  # Use dash for irrelevant
                textposition="middle center",
                textfont={"size": 9, "color": "#666666", "family": "Arial, sans-serif"},
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>%{x}<br>Response Level: Not Applicable "
                    "(excluded from analysis)<extra></extra>"
                ),
                customdata=[[y_data[i], "Not Applicable"] for i in irrelevant_indices],
                showlegend=False,
            ),
        )

    # Function to split constraint names into two lines
    def split_constraint_name(name):
        """Split constraint name into two lines on whole words only.

        Avoids bugs like splitting ``Risks`` on ``Risk`` → ``s Risk``.
        """
        words = name.split()
        if len(words) <= 1:
            return name

        # Prefer breaking before a trailing keyword when present as a full word.
        trailing_keywords = {
            "Cost",
            "Costs",
            "Efficiency",
            "Volume",
            "Volumes",
            "Rate",
            "Rates",
            "Depth",
            "Area",
            "Quality",
            "Risk",
            "Risks",
            "Impact",
            "Impacts",
            "Factor",
            "Factors",
            "Level",
            "Levels",
            "Ratio",
            "Ratios",
            "Index",
            "Constraint",
            "Constraints",
            "Feasibility",
            "Suitability",
            "Contaminants",
            "Contamination",
        }
        for i in range(1, len(words)):
            if words[i] in trailing_keywords:
                return f"{' '.join(words[:i])}<br>{' '.join(words[i:])}"

        # Otherwise split near the middle for long labels
        if len(name) > 15:
            mid = len(words) // 2
            return f"{' '.join(words[:mid])}<br>{' '.join(words[mid:])}"

        return name

    # Create x-axis labels with two lines (Title Case constraint names)
    x_labels = [split_constraint_name(name) for name in display_constraints]

    # Use categorical axes to ensure consistent spacing across all heatmaps
    # Both x and y axes are categorical to prevent layout shifts
    heatmap_fig.update_layout(
        title={"text": title_text, "font": {"size": 16, "color": font_color}} if show_title else None,
        xaxis_title={"text": "Constraints", "font": {"size": 13, "color": font_color}},
        yaxis_title={"text": "Options", "font": {"size": 13, "color": font_color}},
        template="plotly_dark" if is_dark else "plotly_white",
        height=520,
        autosize=True,
        margin={"l": 100, "r": 40, "t": 30 if not show_title else 50, "b": 120},
        paper_bgcolor=paper_bg,
        plot_bgcolor=plot_bg,
        font={"color": font_color},
        xaxis={
            "type": "category",  # Categorical x-axis for consistent spacing
            "categoryorder": "array",
            "categoryarray": display_constraints,
            "tickmode": "array",
            "tickvals": display_constraints,
            "ticktext": x_labels,  # Use two-line labels for display
            "side": "bottom",
            "tickangle": 0,  # No rotation needed with two-line labels
            "showgrid": True,
            "gridcolor": grid_color,
            "tickfont": {"size": 12, "color": font_color},
            "title_font": {"color": font_color},
        },
        yaxis={
            "type": "category",  # Use categorical axis for consistent spacing
            "categoryorder": "array",
            "categoryarray": all_option_names[::-1],  # Reversed for top-to-bottom order
            "showgrid": True,
            "gridcolor": grid_color,
            "fixedrange": True,  # Prevent zoom/pan that could affect spacing
            "tickfont": {"size": 12, "color": font_color},
            "title_font": {"color": font_color},
        },
    )

    # Create legend
    legend = html.Div(
        [
            html.Div(
                [
                    html.Span(
                        "",
                        style={
                            "display": "inline-block",
                            "width": "20px",
                            "height": "20px",
                            "backgroundColor": _get_response_color(0),
                            "marginRight": "8px",
                            "border": "1px solid white",
                            "borderRadius": "50%",  # Make it a circle
                            "verticalAlign": "middle",
                        },
                    ),
                    html.Small("0: Acceptable", className="me-4"),
                    html.Span(
                        "",
                        style={
                            "display": "inline-block",
                            "width": "20px",
                            "height": "20px",
                            "backgroundColor": _get_response_color(1),
                            "marginRight": "8px",
                            "border": "1px solid white",
                            "borderRadius": "50%",  # Make it a circle
                            "verticalAlign": "middle",
                        },
                    ),
                    html.Small("1: Acceptable With Additional Cost", className="me-4"),
                    html.Span(
                        "",
                        style={
                            "display": "inline-block",
                            "width": "20px",
                            "height": "20px",
                            "backgroundColor": _get_response_color(2),
                            "marginRight": "8px",
                            "border": "1px solid white",
                            "borderRadius": "50%",  # Make it a circle
                            "verticalAlign": "middle",
                        },
                    ),
                    html.Small("2: Warning", className="me-4"),
                    html.Span(
                        "",
                        style={
                            "display": "inline-block",
                            "width": "20px",
                            "height": "20px",
                            "backgroundColor": _get_response_color(3),
                            "marginRight": "8px",
                            "border": "1px solid white",
                            "borderRadius": "50%",  # Make it a circle
                            "verticalAlign": "middle",
                        },
                    ),
                    html.Small("3: Mitigation Needed", className="me-4"),
                    html.Span(
                        "",
                        style={
                            "display": "inline-block",
                            "width": "20px",
                            "height": "20px",
                            "backgroundColor": _get_response_color(4),
                            "marginRight": "8px",
                            "border": "1px solid white",
                            "borderRadius": "50%",  # Make it a circle
                            "verticalAlign": "middle",
                        },
                    ),
                    html.Small("4: Reject", className="me-4"),
                    html.Span(
                        "",
                        style={
                            "display": "inline-block",
                            "width": "20px",
                            "height": "20px",
                            "backgroundColor": _get_response_color(-1),
                            "marginRight": "8px",
                            "border": "1px solid #666666",
                            "borderRadius": "50%",  # Make it a circle
                            "verticalAlign": "middle",
                            "opacity": "0.4",
                        },
                    ),
                    html.Small("-1: Not Applicable", className="text-muted"),
                ],
                className="d-flex align-items-center justify-content-center flex-wrap",
            ),
        ],
    )

    return heatmap_fig, legend


def _extract_cost_data():
    """Extract cost data from storage and return mapped values."""
    capital_cost_num = coerce_storage_cost_totals(dash_storage.get_data("capital_cost_num"), CAPITAL_COST_TOTAL_KEYS)
    maintenance_cost_num = coerce_storage_cost_totals(
        dash_storage.get_data("maintenance_cost_num"),
        MAINTENANCE_COST_TOTAL_KEYS,
    )
    net_val_dict = _normalize_net_val_dict(dash_storage.get_data("net_val"))

    if capital_cost_num is None or maintenance_cost_num is None:
        return None, None, None, None

    # Map cost column names to option names
    cost_column_mapping = {
        "Spreading Pond Cost ($)": "Surface Recharge",
        "Injection Wells Cost ($)": "Injection Well",
        "Dry Wells Cost ($)": "Dry Well",
    }

    maintenance_column_mapping = {
        "Spreading Pond Maintenance Cost ($)": "Surface Recharge",
        "Injection Wells Maintenance Cost ($)": "Injection Well",
        "Dry Wells Maintenance Cost ($)": "Dry Well",
    }

    npv_column_mapping = {
        "Spreading Pond Net Present Value ($)": "Surface Recharge",
        "Injection Wells Net Present Value ($)": "Injection Well",
        "Dry Wells Net Present Value ($)": "Dry Well",
    }

    # Extract data for each option
    option_names = []
    capital_costs = []
    maintenance_costs = []
    npv_values = []

    for col_name, option_name in cost_column_mapping.items():
        if col_name in capital_cost_num.index:
            option_names.append(option_name)
            capital_costs.append(float(capital_cost_num[col_name]) if pd.notna(capital_cost_num[col_name]) else 0)

            # Get maintenance cost
            maint_col = col_name.replace("Cost ($)", "Maintenance Cost ($)")
            if maint_col in maintenance_cost_num.index:
                maintenance_costs.append(
                    float(maintenance_cost_num[maint_col]) if pd.notna(maintenance_cost_num[maint_col]) else 0,
                )
            else:
                maintenance_costs.append(0)

            # Get NPV
            npv_col = col_name.replace("Cost ($)", "Net Present Value ($)")
            if npv_col in net_val_dict:
                npv_values.append(float(net_val_dict[npv_col]) if pd.notna(net_val_dict[npv_col]) else 0)
            else:
                npv_values.append(0)

    return option_names, capital_costs, maintenance_costs, npv_values


def _format_cost_bar_label(cost):
    """Compact rounded cost label for bar text and hover."""
    try:
        c = float(cost)
    except (TypeError, ValueError):
        return "$0"
    if not math.isfinite(c):
        return "$0"
    if abs(c) >= 1e6:
        return f"${c / 1e6:.2f}M"
    if abs(c) >= 1e3:
        return f"${c / 1e3:.0f}K"
    return f"${c:,.0f}"


def _create_cost_chart(option_names, values, title, color):
    """Create a single cost chart (capital, maintenance, or NPV)."""
    labels = [_format_cost_bar_label(c) for c in values]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=option_names,
            y=values,
            marker_color=color,
            text=labels,
            textposition="auto",
            name=title,
            customdata=labels,
            hovertemplate="<b>%{x}</b><br>%{fullData.name}: %{customdata}<extra></extra>",
        ),
    )
    fig.update_layout(
        title=title,
        xaxis_title=None,
        yaxis_title="Cost ($)",
        template="plotly_white",
        height=320,
        autosize=True,
        margin={"l": 50, "r": 20, "t": 40, "b": 50},
        showlegend=False,
        yaxis={"tickformat": "$,.0f"},
        hoverlabel={"namelength": -1},
    )
    return fig


def _create_empty_cost_charts(message=None):
    """Create empty cost charts when no data is available."""
    msg = message or "No cost data available. Please run cost analysis first."
    empty_capital_fig = go.Figure()
    empty_capital_fig.update_layout(
        title="Capital Cost",
        template="plotly_white",
        height=350,
        xaxis_title=msg,
        yaxis_title="",
    )

    empty_maintenance_fig = go.Figure()
    empty_maintenance_fig.update_layout(
        title="Annual Maintenance Cost",
        template="plotly_white",
        height=350,
        xaxis_title=msg,
        yaxis_title="",
    )

    empty_npv_fig = go.Figure()
    empty_npv_fig.update_layout(
        title="20-Year Net Present Value",
        template="plotly_white",
        height=350,
        xaxis_title=msg,
        yaxis_title="",
    )

    return empty_capital_fig, empty_maintenance_fig, empty_npv_fig


def _create_cost_comparison_charts(categorized_data=None):
    """Create the three cost comparison charts (feasible options only)."""
    option_names, capital_costs, maintenance_costs, npv_values = _extract_cost_data()

    if not option_names:
        return _create_empty_cost_charts()

    if categorized_data is not None:
        filtered = [
            (name, cap, maint, npv)
            for name, cap, maint, npv in zip(
                option_names, capital_costs, maintenance_costs, npv_values, strict=True
            )
            if not _is_option_not_feasible(categorized_data, name)
        ]
        if not filtered:
            return _create_empty_cost_charts(
                "No feasible options to compare. Not-feasible options are omitted."
            )
        option_names, capital_costs, maintenance_costs, npv_values = map(list, zip(*filtered, strict=True))

    capital_fig = _create_cost_chart(option_names, capital_costs, "Capital Cost", "#007bff")
    maintenance_fig = _create_cost_chart(option_names, maintenance_costs, "Annual Maintenance Cost", "#28a745")
    npv_fig = _create_cost_chart(option_names, npv_values, "20-Year Net Present Value", "#ffc107")

    return capital_fig, maintenance_fig, npv_fig


def setup_feasibilities_callbacks(app):
    """Set up all callbacks for the Feasibilities tab."""

    @app.callback(
        Output("spider-performance-help-modal", "is_open"),
        [
            Input({"type": "spider-help-btn", "option": ALL}, "n_clicks"),
            Input("spider-help-close", "n_clicks"),
        ],
        State("spider-performance-help-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_spider_performance_help(open_clicks, close_clicks, is_open):
        """Open or close the spider-plot help modal from any ? button."""
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update
        trigger = ctx.triggered[0]["prop_id"]
        if "spider-help-btn" in trigger:
            # Ignore pattern-matching fires with no real click
            if not any(open_clicks or []):
                return dash.no_update
            return True
        if "spider-help-close" in trigger:
            return False
        return not bool(is_open)

    @app.callback(
        Output("hydro-constraints-help-modal", "is_open"),
        [
            Input("hydro-constraints-help-btn", "n_clicks"),
            Input("hydro-constraints-help-note-btn", "n_clicks"),
            Input("hydro-constraints-help-close", "n_clicks"),
        ],
        State("hydro-constraints-help-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_hydro_constraints_help(open_clicks, note_clicks, close_clicks, is_open):
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update
        trigger = ctx.triggered[0]["prop_id"]
        if "hydro-constraints-help-btn" in trigger or "hydro-constraints-help-note-btn" in trigger:
            return True
        if "hydro-constraints-help-close" in trigger:
            return False
        return not bool(is_open)

    @app.callback(
        Output("wq-constraints-help-modal", "is_open"),
        [
            Input("wq-constraints-help-btn", "n_clicks"),
            Input("wq-constraints-help-note-btn", "n_clicks"),
            Input("wq-constraints-help-close", "n_clicks"),
        ],
        State("wq-constraints-help-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_wq_constraints_help(open_clicks, note_clicks, close_clicks, is_open):
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update
        trigger = ctx.triggered[0]["prop_id"]
        if "wq-constraints-help-btn" in trigger or "wq-constraints-help-note-btn" in trigger:
            return True
        if "wq-constraints-help-close" in trigger:
            return False
        return not bool(is_open)

    @app.callback(
        Output("feasibility-details-collapse", "is_open"),
        Input("view-feasibility-details-check", "value"),
        prevent_initial_call=False,
    )
    def toggle_feasibility_details(view_details):
        """Expand or collapse Feasibility Details when View is checked."""
        checked = bool(view_details)
        dash_storage.set_data("view_feasibility_details", checked)
        return checked

    @app.callback(
        [
            Output("engineering-options-summary", "children"),
            Output("hydrogeologic-constraints-heatmap-chart", "figure"),
            Output("hydrogeologic-constraints-heatmap-legend", "children"),
            Output("environmental-constraints-heatmap-chart", "figure"),
            Output("environmental-constraints-heatmap-legend", "children"),
            Output("capital-cost-chart", "figure"),
            Output("maintenance-cost-chart", "figure"),
            Output("npv-cost-chart", "figure"),
            Output("spider-plots-container", "children"),
        ],
        [
            Input("analysis-tabs", "active_tab"),
            Input("knowledge-graph-store", "data"),
            Input("app-container", "className"),
            Input("cost-economics-revision", "data"),
        ],
        prevent_initial_call=False,
    )
    def update_feasibilities_dashboard(active_tab, _graph_store, container_class, _cost_revision):
        """Update engineering options economics and feasibility charts from DSS results.

        Listens to ``knowledge-graph-store`` so the Feasibilities view refreshes whenever
        the Analysis pipeline finishes (e.g. selecting the Analysis top tab), not only when
        switching away from and back to this sub-tab.

        Also listens to ``cost-economics-revision`` so Capital Cost table unit-price
        edits refresh the Feasibility Summary cards and cost charts.

        This callback depends on Analysis tab callbacks completing first.
        When Feasibilities sub-tab is selected, it ensures analysis has run and then
        displays the results.

        Execution order:
        1. Analysis tab callbacks run (initialize graph, run feasibility analysis)
        2. This callback runs when Feasibilities sub-tab is selected or graph store updates
        3. Then it accesses and displays the results
        """
        # Only refresh Feasibilities UI when this sub-tab is active
        if active_tab != "analysis-feasibilities":
            return (dash.no_update,) * 9

        is_dark = "mar-theme-dark" in str(container_class or "")

        # CRITICAL: Ensure Analysis tab callbacks have run first
        # This ensures the knowledge graph is initialized and feasibility analysis has completed
        # before we try to access DSS results.
        # _ensure_dss_results_available() will run run_feasibility_analysis() if needed,
        # ensuring Analysis tab callbacks complete before this callback proceeds.
        logger.debug("Feasibilities callback triggered - ensuring Analysis callbacks have completed")
        dss_results = _ensure_dss_results_available()
        dash_storage.set_data("dss_results", dss_results)

        # Check if results are available
        if dss_results is None or not hasattr(dss_results, "results") or not dss_results.results:
            return _get_empty_dashboard_content(is_dark=is_dark)

        # Extract results and filters
        results = dss_results.results
        filters = getattr(dss_results, "filters", {})

        # Categorize options
        categorized_data = _categorize_options(results, filters)

        # Build components (costs come from capital_cost_num, including unit-price edits)
        engineering_summary = _build_engineering_options_summary(categorized_data)

        # Create separate heatmaps for each constraint type
        hydro_heatmap_fig, hydro_heatmap_legend = _create_constraints_heatmap(
            results,
            filters,
            constraint_type="hydrogeologic",
            title="",
            is_dark=is_dark,
        )
        env_heatmap_fig, env_heatmap_legend = _create_constraints_heatmap(
            results,
            filters,
            constraint_type="environmental",
            title="",
            is_dark=is_dark,
        )

        capital_fig, maintenance_fig, npv_fig = _create_cost_comparison_charts(categorized_data)

        # Create spider plots
        spider_plots_content = _create_spider_plots(dss_results, categorized_data)

        return (
            engineering_summary,
            hydro_heatmap_fig,
            hydro_heatmap_legend,
            env_heatmap_fig,
            env_heatmap_legend,
            capital_fig,
            maintenance_fig,
            npv_fig,
            spider_plots_content,
        )


def _create_spider_plots(dss_results, categorized_data):
    """Create spider plots for each MAR option (6 axes including $/acre-ft efficiency)."""
    if dss_results is None or not hasattr(dss_results, "results") or not dss_results.results:
        return html.Div(
            "No DSS evaluation results available. Please run the feasibility analysis first.",
            className="text-muted text-center p-4",
        )

    # Get scores and cost data
    scores = getattr(dss_results, "scores", {})
    capital_cost_num = coerce_storage_cost_totals(dash_storage.get_data("capital_cost_num"), CAPITAL_COST_TOTAL_KEYS)
    maintenance_cost_num = coerce_storage_cost_totals(
        dash_storage.get_data("maintenance_cost_num"),
        MAINTENANCE_COST_TOTAL_KEYS,
    )
    net_val_dict = _normalize_net_val_dict(dash_storage.get_data("net_val"))

    if not scores:
        return html.Div(
            "No scoring data available. Please run the feasibility analysis first.",
            className="text-muted text-center p-4",
        )

    # Map option names to cost column names (shared module constants)
    option_to_capital_col = _OPTION_TO_CAPITAL_COL
    option_to_maintenance_col = _OPTION_TO_MAINTENANCE_COL
    option_to_npv_col = _OPTION_TO_NPV_COL

    # Get all capital, maintenance costs, and NPV values and find minimums
    capital_cost_dict = {}  # Store capital cost per option
    maintenance_cost_dict = {}  # Store maintenance cost per option
    npv_dict = {}  # Store NPV per option
    capital_costs = []
    maintenance_costs = []
    npv_values = []

    for option_name in scores:
        option_not_feasible = _is_option_not_feasible(categorized_data, option_name)

        # Get capital cost
        capital_col = option_to_capital_col.get(option_name)
        if capital_col and capital_cost_num is not None and capital_col in capital_cost_num.index:
            capital_val = float(capital_cost_num[capital_col]) if pd.notna(capital_cost_num[capital_col]) else 0
            capital_cost_dict[option_name] = capital_val
            if capital_val > 0 and not option_not_feasible:
                capital_costs.append(capital_val)
        else:
            capital_cost_dict[option_name] = 0

        # Get maintenance cost
        maintenance_col = option_to_maintenance_col.get(option_name)
        if maintenance_col and maintenance_cost_num is not None and maintenance_col in maintenance_cost_num.index:
            maintenance_val = (
                float(maintenance_cost_num[maintenance_col]) if pd.notna(maintenance_cost_num[maintenance_col]) else 0
            )
            maintenance_cost_dict[option_name] = maintenance_val
            if maintenance_val > 0 and not option_not_feasible:
                maintenance_costs.append(maintenance_val)
        else:
            maintenance_cost_dict[option_name] = 0

        # Get NPV
        npv_col = option_to_npv_col.get(option_name)
        if npv_col and npv_col in net_val_dict:
            npv_val = float(net_val_dict[npv_col]) if pd.notna(net_val_dict[npv_col]) else 0
            npv_dict[option_name] = npv_val
            if npv_val > 0 and not option_not_feasible:
                npv_values.append(npv_val)
        else:
            npv_dict[option_name] = 0

    # Find minimum costs, NPV, and cost/acre-ft for efficiency calculation
    min_capital_cost = min(capital_costs) if capital_costs else 1
    min_maintenance_cost = min(maintenance_costs) if maintenance_costs else 1
    min_npv = min(npv_values) if npv_values else 1

    cost_per_acre_ft_dict = {}
    cost_per_acre_ft_values = []
    for option_name in scores:
        if _is_option_not_feasible(categorized_data, option_name):
            cost_per_acre_ft_dict[option_name] = 0.0
            continue
        capital_val = capital_cost_dict.get(option_name, 0.0)
        acre_ft = _annual_recharged_volume_acre_ft(option_name)
        if capital_val > 0 and acre_ft > 0:
            cppa = capital_val / acre_ft
            cost_per_acre_ft_dict[option_name] = cppa
            cost_per_acre_ft_values.append(cppa)
        else:
            cost_per_acre_ft_dict[option_name] = 0.0
    min_cost_per_acre_ft = min(cost_per_acre_ft_values) if cost_per_acre_ft_values else 1

    # Create spider plots for each option
    spider_plots = []
    for option_name, option_scores in scores.items():
        # Get scores
        hydro_score = option_scores.get("hydrogeologic", 0.0)
        env_score = option_scores.get("environmental", 0.0)

        not_feasible = _is_option_not_feasible(categorized_data, option_name)

        if not_feasible:
            # Infeasible options: all performance axes are zero
            hydro_score = 0.0
            env_score = 0.0
            capital_efficiency = 0.0
            maintenance_efficiency = 0.0
            npv_efficiency = 0.0
            cost_per_acre_ft_efficiency = 0.0
            cost_per_acre_ft_val = 0.0
        else:
            # Calculate capital cost efficiency: 100 for lowest cost, 100 * (min_cost / x) for others
            capital_val = capital_cost_dict.get(option_name, 0.0)
            if capital_val > 0 and min_capital_cost > 0:
                capital_efficiency = 100.0 * (min_capital_cost / capital_val)
            else:
                capital_efficiency = 0.0
            capital_efficiency = max(0.0, min(100.0, capital_efficiency))

            # Calculate maintenance cost efficiency: 100 for lowest cost, 100 * (min_cost / x) for others
            maintenance_val = maintenance_cost_dict.get(option_name, 0.0)
            if maintenance_val > 0 and min_maintenance_cost > 0:
                maintenance_efficiency = 100.0 * (min_maintenance_cost / maintenance_val)
            else:
                maintenance_efficiency = 0.0
            maintenance_efficiency = max(0.0, min(100.0, maintenance_efficiency))

            # Calculate NPV efficiency: 100 for lowest NPV, 100 * (min_npv / x) for others
            npv_val = npv_dict.get(option_name, 0.0)
            if npv_val > 0 and min_npv > 0:
                npv_efficiency = 100.0 * (min_npv / npv_val)
            else:
                npv_efficiency = 0.0
            npv_efficiency = max(0.0, min(100.0, npv_efficiency))

            cost_per_acre_ft_val = cost_per_acre_ft_dict.get(option_name, 0.0)
            cost_per_acre_ft_efficiency = _efficiency_from_min_ratio(cost_per_acre_ft_val, min_cost_per_acre_ft)

        # Helper function to get color and style based on score
        def get_score_style(score):
            """Get color and font weight based on score value."""
            if score < 50:
                return {"color": "red", "weight": "bold"}
            elif score < 75:
                return {"color": "orange", "weight": "bold"}
            else:
                return {"color": "green", "weight": "bold"}

        # Create spider plot
        fig = go.Figure()

        # Categories for radar chart - order matters for positioning
        categories = [
            "Hydrogeologic",
            "Water Quality",
            "Capital Cost Efficiency",
            "Maintenance Cost Efficiency",
            "NPV Efficiency",
            "Annual Capital Cost Per Acre-ft",
        ]
        values = [
            hydro_score,
            env_score,
            capital_efficiency,
            maintenance_efficiency,
            npv_efficiency,
            cost_per_acre_ft_efficiency,
        ]

        # Create categories with scores (score below category name, centered)
        categories_with_scores = []
        for category, score in zip(categories, values, strict=True):
            style = get_score_style(score)
            if category == "Annual Capital Cost Per Acre-ft":
                if cost_per_acre_ft_val > 0:
                    label = (
                        f"{category}\n"
                        f'<span style="color:{style["color"]};">{score:.0f}%</span> '
                        f'<span style="color:#495057;">'
                        f"\n(${cost_per_acre_ft_val:,.1f}/acre-ft)"
                        f"</span>"
                    )
                else:
                    label = (
                        f"{category}\n"
                        f'<span style="color:{style["color"]};">{score:.0f}%</span> '
                        f'<span style="color:#000;">N/A</span>'
                    )
            else:
                label = f'{category}\n<span style="color:{style["color"]};">{score:.0f}%</span>'
            categories_with_scores.append(label)

        # Close the polygon by adding the first point at the end
        # Use original categories for theta (for positioning), but labels will show scores
        categories_closed = categories + [categories[0]]
        values_closed = values + [values[0]]

        # Add trace with blue polygon
        fig.add_trace(
            go.Scatterpolar(
                r=values_closed,
                theta=categories_closed,
                fill="toself",
                name=option_name,
                line={"color": "#1e90ff", "width": 3},
                fillcolor="rgba(30, 144, 255, 0.4)",
                mode="lines+markers",
                marker={"size": 8, "color": "#1e90ff", "line": {"width": 2, "color": "white"}},
                hovertemplate="<b>%{theta}</b><br>Value: %{r:.1f}<extra></extra>",
            ),
        )

        # Update layout with clean polar plot
        fig.update_layout(
            polar={
                "radialaxis": {
                    "visible": True,
                    "range": [0, 100],
                    "tickmode": "linear",
                    "tick0": 0,
                    "dtick": 20,
                    "tickfont": {"size": 9, "color": "black"},
                    "gridcolor": "lightgrey",
                    "gridwidth": 1,
                    "linecolor": "grey",
                    "linewidth": 1,
                    "showline": True,
                },
                "angularaxis": {
                    "tickmode": "array",
                    "tickvals": categories,
                    "ticktext": categories_with_scores,
                    "tickfont": {"size": 10, "family": "Arial, sans-serif"},
                    "rotation": 0,
                    "direction": "clockwise",
                    "linecolor": "grey",
                    "linewidth": 1,
                    "gridcolor": "lightgrey",
                    "gridwidth": 1,
                },
                "bgcolor": "white",
            },
            plot_bgcolor="white",
            paper_bgcolor="white",
            showlegend=False,
            height=350,
            margin={"l": 80, "r": 80, "t": 100, "b": 80},
            title={
                "text": option_name,
                "x": 0.5,
                "y": 0.98,
                "font": {"size": 16, "color": "#006400", "family": "Arial, sans-serif", "weight": "bold"},
                "xanchor": "center",
                "yanchor": "top",
                "pad": {"t": 10},
            },
        )

        # Create card for this option's spider plot
        option_key = option_name.replace(" ", "-").lower()
        spider_plots.append(
            dbc.Col(
                [
                    dbc.Card(
                        [
                            dbc.CardHeader(
                                html.Div(
                                    [
                                        html.Span(
                                            option_name,
                                            className="fw-bold text-white",
                                        ),
                                        html.Button(
                                            "?",
                                            id={
                                                "type": "spider-help-btn",
                                                "option": option_key,
                                            },
                                            type="button",
                                            className="mar-help-btn eng-help-btn",
                                            title=(f"Help: how {option_name} spider plot scores are computed"),
                                        ),
                                    ],
                                    className=("d-flex align-items-center justify-content-between w-100"),
                                ),
                                className="py-2",
                                style={
                                    "backgroundColor": "#1e3a5f",
                                    "fontSize": "0.9rem",
                                },
                            ),
                            dbc.CardBody(
                                [dcc.Graph(figure=fig, config={"displayModeBar": False})],
                                style={
                                    "paddingTop": "0.5rem",
                                    "display": "flex",
                                    "flexDirection": "column",
                                    "justifyContent": "flex-end",
                                },
                            ),
                        ],
                        className="h-100",
                        style={"minHeight": "400px"},
                    ),
                ],
                width=4,
                className="mb-3",
            ),
        )

    # Return in rows of 3
    rows = []
    for i in range(0, len(spider_plots), 3):
        row_plots = spider_plots[i : i + 3]
        rows.append(dbc.Row(row_plots, className="mb-3"))

    return html.Div(rows)


def _get_response_color(level):
    """Get color for response level (0-4, or -1 for irrelevant)."""
    color_map = {
        -1: "#808080",  # Grey for irrelevant
        0: "#28a745",  # Dark Green
        1: "#90ee90",  # Light Green
        2: "#ffc107",  # Yellow/Gold
        3: "#fd7e14",  # Orange
        4: "#dc3545",  # Red
    }
    return color_map.get(level, "#ffffff")
