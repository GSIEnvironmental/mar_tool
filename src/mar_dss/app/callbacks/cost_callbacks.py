"""
Callbacks for Cost calculations and display in the Engineering tab.
"""

import json
import logging

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import MATCH, Input, Output, State, dash_table, dcc, html
from dash.dash_table.Format import Format, Scheme

import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.utils.cost_storage import (
    CAPITAL_COST_TOTAL_KEYS,
    MAINTENANCE_COST_TOTAL_KEYS,
    totals_series_to_storage_dict,
)
from mar_dss.app.utils.excel_table import (
    datatable_base_style_cell,
    datatable_base_style_header,
    datatable_computed_data_style,
)

logger = logging.getLogger(__name__)


try:
    from mar_dss.app.callbacks.cost_calculator import CostCalculator
except ImportError:
    from .cost_calculator import CostCalculator

_COST_COLUMN_TO_OPTION = {
    "Spreading Pond Cost ($)": "Surface Recharge",
    "Injection Wells Cost ($)": "Injection Well",
    "Dry Wells Cost ($)": "Dry Well",
    "Spreading Pond Maintenance Cost ($)": "Surface Recharge",
    "Injection Wells Maintenance Cost ($)": "Injection Well",
    "Dry Wells Maintenance Cost ($)": "Dry Well",
    "Spreading Pond Net Present Value ($)": "Surface Recharge",
    "Injection Wells Net Present Value ($)": "Injection Well",
    "Dry Wells Net Present Value ($)": "Dry Well",
}


def _round_to_nearest_thousand(value):
    """Round a dollar amount to the nearest $1,000 for Cost Analysis totals."""
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return 0.0
        amount = float(value)
    except (TypeError, ValueError):
        return 0.0
    return float(round(amount / 1000.0) * 1000)


# Cost Summary uncertainty band (−20% / +50%)
_COST_RANGE_LOW_FACTOR = 0.80
_COST_RANGE_HIGH_FACTOR = 1.50


def _format_total_usd(value):
    """Format a total cost rounded to the nearest $1,000."""
    rounded = _round_to_nearest_thousand(value)
    if rounded == 0:
        return "$0"
    return f"${rounded:,.0f}"


def _format_total_usd_range(value):
    """Format a Cost Summary total as −20% to +50% range, nearest $1,000."""
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "$0"
        amount = float(value)
    except (TypeError, ValueError):
        return "$0"
    if amount == 0:
        return "$0"
    low = _round_to_nearest_thousand(amount * _COST_RANGE_LOW_FACTOR)
    high = _round_to_nearest_thousand(amount * _COST_RANGE_HIGH_FACTOR)
    return f"${low:,.0f} – ${high:,.0f}"


def _is_total_cost_row_label(label):
    """True for Subtotal / Total summary rows in capital & maintenance tables."""
    text = str(label or "").lower()
    return "total" in text or "subtotal" in text or "grand maintenance" in text


def _ensure_label_column(df, preferred="Row Label"):
    """Ensure the row-label column exists after reset_index."""
    if preferred in df.columns:
        return df, preferred
    if "index" in df.columns:
        return df.rename(columns={"index": preferred}), preferred
    # Unnamed / named index after reset_index
    for candidate in ("level_0", "Item"):
        if candidate in df.columns:
            return df.rename(columns={candidate: preferred}), preferred
    if len(df.columns) > 0:
        first = df.columns[0]
        if first not in (
            "Unit Cost $",
            "Number of Units",
            "Category",
            "Item",
        ) and "Cost ($)" not in str(first):
            return df.rename(columns={first: preferred}), preferred
    return df, preferred


def _round_total_rows_in_cost_df(df, cost_columns, label_col="Row Label"):
    """Round cost cells on Total/Subtotal rows to the nearest $1,000 (in place)."""
    if df is None or df.empty or label_col not in df.columns:
        return df
    mask = df[label_col].map(_is_total_cost_row_label)
    for col in cost_columns:
        if col not in df.columns:
            continue
        df.loc[mask, col] = df.loc[mask, col].apply(
            lambda x: _round_to_nearest_thousand(x) if pd.notna(x) and str(x).strip() != "" else x,
        )
    return df


def _format_cost_column_values(df, cost_columns, label_col=None, round_all=False):
    """Format cost columns; round totals (or all rows) to nearest $1,000."""
    if df is None or df.empty:
        return df
    if label_col and label_col in df.columns:
        total_mask = df[label_col].map(_is_total_cost_row_label)
    else:
        total_mask = pd.Series([round_all] * len(df), index=df.index)

    for col in cost_columns:
        if col not in df.columns:
            continue
        formatted = []
        for val, is_tot in zip(df[col], total_mask if not round_all else [True] * len(df), strict=True):
            try:
                if pd.notna(val) and str(val).strip() != "":
                    if round_all or is_tot:
                        formatted.append(f"{_round_to_nearest_thousand(val):,.0f}")
                    else:
                        formatted.append(f"{float(val):,.1f}")
                else:
                    formatted.append("")
            except (ValueError, TypeError):
                formatted.append("")
        df[col] = formatted
    return df


def _get_not_feasible_option_names():
    """Option names rejected by feasibility analysis (same logic as Feasibilities tab).

    Prefers stored DSS results. If Analysis has not been run yet, evaluates hard
    (and soft reject) constraints directly so Cost Analysis can still show N/A.
    """
    dss_results = dash_storage.get_data("dss_results")
    if dss_results is not None and hasattr(dss_results, "results") and dss_results.results:
        from mar_dss.app.callbacks.feasibilities_callbacks import _categorize_options

        categorized = _categorize_options(
            dss_results.results,
            getattr(dss_results, "filters", {}),
        )
        return {opt["name"] for opt in categorized.get("rejected", [])}

    not_feasible = set()
    try:
        from mar_dss.mar import hard_constraints as hc_module
        from mar_dss.mar import soft_constraints as sc_module
        from mar_dss.mar.options import mar_options

        if dash_storage.get_data("decision_graph") is None:
            return set()
        for option in mar_options():
            if any(not hc.get("pass", True) for hc in hc_module.hard_constraints(option)):
                not_feasible.add(option.name)
                continue
            for sc in sc_module.soft_constraints(option):
                response = sc.get("response", 0)
                is_hard = sc.get("hard", True)
                if response == 4 or (is_hard and response >= 2):
                    not_feasible.add(option.name)
                    break
    except Exception:
        return set()
    return not_feasible


def _mask_infeasible_cost_columns(df, cost_columns, not_feasible_options):
    """Replace cost column cells with N/A for options that are not feasible."""
    if df is None or df.empty or not not_feasible_options:
        return df
    for col in cost_columns:
        option_name = _COST_COLUMN_TO_OPTION.get(col)
        if option_name and option_name in not_feasible_options and col in df.columns:
            df[col] = "N/A"
    return df


def _coerce_stored_dataframe(value):
    """Return a DataFrame from dash storage, or None if the value is not usable."""
    if isinstance(value, pd.DataFrame):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = json.loads(stripped)
        except (json.JSONDecodeError, ValueError, TypeError):
            return None
        value = parsed
    if isinstance(value, (list, dict)):
        try:
            return pd.DataFrame(value)
        except (ValueError, TypeError):
            return None
    return None


def _cost_table_dataframe(stored_df, cost_calculator, calculator_attr):
    """Copy a cost breakdown table from storage or the live calculator."""
    if isinstance(stored_df, pd.DataFrame):
        return stored_df.copy()
    if cost_calculator is not None:
        return getattr(cost_calculator, calculator_attr).copy()
    return pd.DataFrame()


_CAPITAL_COST_COLS = list(CAPITAL_COST_TOTAL_KEYS)
_MAINT_COST_COLS = list(MAINTENANCE_COST_TOTAL_KEYS)
_NPV_COLS = (
    "Spreading Pond Net Present Value ($)",
    "Injection Wells Net Present Value ($)",
    "Dry Wells Net Present Value ($)",
)

_CAPITAL_UNIT_OVERRIDES_KEY = "capital_cost_unit_overrides"
_MAINT_UNIT_OVERRIDES_KEY = "maintenance_cost_unit_overrides"
_COST_ECONOMICS_REVISION_KEY = "cost_economics_revision"
# Annual O&M is a flat fraction of each option's Capital Total Cost.
_MAINTENANCE_FRACTION_OF_CAPITAL = 0.05


def bump_cost_economics_revision():
    """Invalidate Feasibility Summary / cost charts that depend on stored totals."""
    try:
        rev = int(dash_storage.get_data(_COST_ECONOMICS_REVISION_KEY) or 0)
    except (TypeError, ValueError):
        rev = 0
    rev += 1
    dash_storage.set_data(_COST_ECONOMICS_REVISION_KEY, rev)
    return rev


def persist_calculator_costs_with_unit_overrides(cost_calculator):
    """
    Store capital / maintenance / NPV from a CostCalculator, applying any
    user Unit Cost $ overrides from the Capital Cost table.
    """
    if cost_calculator is None:
        return None, None, None

    capital_df = cost_calculator.capital_costs_calculations.copy().reset_index()
    capital_df, label_col = _ensure_label_column(capital_df)
    _apply_unit_overrides_to_display_df(
        capital_df,
        dash_storage.get_data(_CAPITAL_UNIT_OVERRIDES_KEY),
        label_col=label_col,
    )
    _recompute_capital_display_df(capital_df, label_col=label_col)
    capital_totals = _totals_from_display_df(capital_df, _CAPITAL_COST_COLS, "Capital Total Cost", label_col)
    maint_totals = _maintenance_totals_from_capital(capital_totals)
    npv_df = _compute_npv_series(capital_totals, maint_totals)
    net_val = {col: float(npv_df[col].iloc[-1]) for col in _NPV_COLS if col in npv_df.columns}

    dash_storage.set_data(
        "capital_cost_num",
        totals_series_to_storage_dict(pd.Series(capital_totals), CAPITAL_COST_TOTAL_KEYS),
    )
    dash_storage.set_data(
        "maintenance_cost_num",
        totals_series_to_storage_dict(pd.Series(maint_totals), MAINTENANCE_COST_TOTAL_KEYS),
    )
    dash_storage.set_data("net_val", net_val)
    dash_storage.set_data(
        "capital_costs_calculations_df",
        cost_calculator.capital_costs_calculations,
    )
    dash_storage.set_data(
        "maintenance_costs_calculations_df",
        cost_calculator.maintenance_costs_calculations,
    )
    dash_storage.set_data("npv_calculations_df", npv_df.copy())
    bump_cost_economics_revision()
    return capital_totals, maint_totals, net_val


def feasibility_economics_summary_from_storage():
    """Rebuild Feasibility Summary option cards from current stored costs."""
    try:
        from mar_dss.app.callbacks.feasibilities_callbacks import (
            _build_engineering_options_summary,
            _categorize_options,
        )
    except ImportError:
        from .feasibilities_callbacks import (
            _build_engineering_options_summary,
            _categorize_options,
        )

    dss_results = dash_storage.get_data("dss_results")
    if dss_results is None or not hasattr(dss_results, "results") or not dss_results.results:
        return dash.no_update
    filters = getattr(dss_results, "filters", {}) or {}
    categorized = _categorize_options(dss_results.results, filters)
    return _build_engineering_options_summary(categorized)


# Method columns exclude technology-specific line items by Item name.
_CAPITAL_METHOD_EXCLUDE_ITEMS = {
    "Spreading Pond Cost ($)": {
        "Dry Well Cost",
        "Injection Wells",
        "Distribution Piping - Injection",
        "Distribution Piping - Dry Well",
    },
    "Injection Wells Cost ($)": {
        "Dry Well Cost",
        "Distribution Piping - Dry Well",
        "Infiltration Basin",
    },
    "Dry Wells Cost ($)": {
        "Injection Wells",
        "Distribution Piping - Injection",
        "Infiltration Basin",
    },
}
_MAINT_METHOD_EXCLUDE_ITEMS = {
    "Spreading Pond Maintenance Cost ($)": {
        "Dry Well Maintenance",
        "Injection Well Maintenance",
        "Injection Well Pumping and Bag Filter",
        "Injection Well Power",
    },
    "Injection Wells Maintenance Cost ($)": {
        "Dry Well Maintenance",
        "Infiltration Basin Maintenance",
    },
    "Dry Wells Maintenance Cost ($)": {
        "Injection Well Maintenance",
        "Injection Well Pumping and Bag Filter",
        "Injection Well Power",
        "Infiltration Basin Maintenance",
    },
}

_CAPITAL_SOFT_FEE_ROWS = (
    ("Project Management (10%)", 0.10),
    ("Permitting (15%)", 0.15),
    ("Engineering (18%)", 0.18),
)
_MAINT_SOFT_FEE_ROWS = (
    ("Project Management (10%)", 0.10),
    ("Reporting (2%)", 0.02),
    ("Engineering (18%)", 0.18),
)
_CAPITAL_SOFT_LABELS = frozenset(
    {
        "Subtotal",
        "subtotal_with_fees",
        "Capital Total Cost",
        *(label for label, _ in _CAPITAL_SOFT_FEE_ROWS),
    },
)
_MAINT_SOFT_LABELS = frozenset(
    {
        "Subtotal Maintenance Cost ($)",
        "Subtotal with Admin Fees",
        "Annual Grand Maintenance Cost",
        *(label for label, _ in _MAINT_SOFT_FEE_ROWS),
    },
)


def _parse_cost_float(value, default=0.0):
    """Parse a table cell to float (handles blanks and currency strings)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    if isinstance(value, (int, float)):
        try:
            v = float(value)
            return v if v == v else default
        except (TypeError, ValueError):
            return default
    text = str(value).strip()
    if not text or text.lower() in ("nan", "none", "n/a"):
        return default
    text = text.replace("$", "").replace(",", "")
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _row_item_name(row):
    item = row.get("Item") if isinstance(row, dict) else None
    if item is None or (isinstance(item, float) and pd.isna(item)):
        return ""
    text = str(item).strip()
    return "" if text.lower() in ("", "nan", "none") else text


def _row_label_text(row, label_col="Row Label"):
    label = row.get(label_col) if isinstance(row, dict) else None
    if label is None or (isinstance(label, float) and pd.isna(label)):
        return ""
    return str(label).strip()


def _is_editable_cost_line_row(row, soft_labels, label_col="Row Label"):
    """True for bill-of-quantity rows (not soft-cost / total rows)."""
    label = _row_label_text(row, label_col)
    if label in soft_labels:
        return False
    return bool(_row_item_name(row))


def _apply_unit_overrides_to_display_df(df, overrides, label_col="Row Label"):
    """Apply stored per-Item Unit Cost $ overrides (quantities stay calculated)."""
    if df is None or df.empty or not isinstance(overrides, dict) or not overrides:
        return df
    for i in df.index:
        item = _row_item_name(df.loc[i].to_dict())
        if not item or item not in overrides:
            continue
        ov = overrides.get(item) or {}
        if "Unit Cost $" in ov and ov["Unit Cost $"] is not None:
            df.at[i, "Unit Cost $"] = _parse_cost_float(ov["Unit Cost $"])
    return df


def _extract_unit_overrides_from_display_df(df, soft_labels, label_col="Row Label"):
    """Build Item → {Unit Cost $} from editable line rows."""
    overrides = {}
    if df is None or df.empty:
        return overrides
    for i in df.index:
        row = df.loc[i].to_dict()
        if not _is_editable_cost_line_row(row, soft_labels, label_col):
            continue
        item = _row_item_name(row)
        overrides[item] = {
            "Unit Cost $": _parse_cost_float(row.get("Unit Cost $")),
        }
    return overrides


def _recompute_method_costs_from_units(
    df,
    cost_columns,
    exclude_by_col,
    soft_labels,
    soft_fee_rows,
    subtotal_label,
    fees_subtotal_label,
    grand_total_label,
    label_col="Row Label",
):
    """
    Rebuild method cost columns from Unit Cost $ × Number of Units, then soft fees.

    Soft-cost rows are not editable sources; their values are recomputed.
    """
    if df is None or df.empty:
        return df

    for col in cost_columns:
        if col not in df.columns:
            continue
        excl = exclude_by_col.get(col, set())
        for i in df.index:
            row = df.loc[i].to_dict()
            label = _row_label_text(row, label_col)
            if label in soft_labels:
                continue
            item = _row_item_name(row)
            if not item:
                df.at[i, col] = 0.0
                continue
            line = _parse_cost_float(row.get("Unit Cost $")) * _parse_cost_float(row.get("Number of Units"))
            df.at[i, col] = 0.0 if item in excl else line

        line_sum = 0.0
        for i in df.index:
            row = df.loc[i].to_dict()
            if not _is_editable_cost_line_row(row, soft_labels, label_col):
                continue
            line_sum += _parse_cost_float(df.at[i, col])

        fees_sum = sum(line_sum * rate for _, rate in soft_fee_rows)
        with_fees = line_sum + fees_sum
        for i in df.index:
            label = _row_label_text(df.loc[i].to_dict(), label_col)
            if label == subtotal_label:
                df.at[i, col] = line_sum
            elif label in (fees_subtotal_label, grand_total_label):
                df.at[i, col] = with_fees
            else:
                for fee_label, rate in soft_fee_rows:
                    if label == fee_label:
                        df.at[i, col] = line_sum * rate
                        break
    return df


def _recompute_capital_display_df(df, label_col="Row Label"):
    return _recompute_method_costs_from_units(
        df,
        _CAPITAL_COST_COLS,
        _CAPITAL_METHOD_EXCLUDE_ITEMS,
        _CAPITAL_SOFT_LABELS,
        _CAPITAL_SOFT_FEE_ROWS,
        subtotal_label="Subtotal",
        fees_subtotal_label="subtotal_with_fees",
        grand_total_label="Capital Total Cost",
        label_col=label_col,
    )


def _recompute_maintenance_display_df(df, label_col="Row Label"):
    return _recompute_method_costs_from_units(
        df,
        _MAINT_COST_COLS,
        _MAINT_METHOD_EXCLUDE_ITEMS,
        _MAINT_SOFT_LABELS,
        _MAINT_SOFT_FEE_ROWS,
        subtotal_label="Subtotal Maintenance Cost ($)",
        fees_subtotal_label="Subtotal with Admin Fees",
        grand_total_label="Annual Grand Maintenance Cost",
        label_col=label_col,
    )


def _totals_from_display_df(df, cost_columns, total_label, label_col="Row Label"):
    """Read method totals from the grand-total soft-cost row."""
    out = dict.fromkeys(cost_columns, 0.0)
    if df is None or df.empty:
        return out
    for i in df.index:
        if _row_label_text(df.loc[i].to_dict(), label_col) != total_label:
            continue
        for col in cost_columns:
            if col in df.columns:
                out[col] = _parse_cost_float(df.at[i, col])
        break
    return out


def _maintenance_totals_from_capital(capital_totals):
    """Annual O&M = fraction of each option's capital total."""
    out = {}
    for cap_col, maint_col in zip(CAPITAL_COST_TOTAL_KEYS, MAINTENANCE_COST_TOTAL_KEYS, strict=True):
        out[maint_col] = (
            _parse_cost_float(
                (capital_totals or {}).get(cap_col)
                if isinstance(capital_totals, dict)
                else (capital_totals.get(cap_col) if hasattr(capital_totals, "get") else 0),
            )
            * _MAINTENANCE_FRACTION_OF_CAPITAL
        )
    return out


def _simple_maintenance_display_df(capital_totals):
    """Build the simplified maintenance table (5% of capital per option)."""
    maint_totals = _maintenance_totals_from_capital(capital_totals)
    line = {
        "Row Label": 0,
        "Category": "ANNUAL O&M",
        "Item": "Maintenance (5% of capital)",
        "Unit": "LS",
        "Unit Cost $": None,
        "Number of Units": 1.0,
    }
    for col in _MAINT_COST_COLS:
        line[col] = maint_totals.get(col, 0.0)
    rows = [line]
    for label in (
        "Subtotal Maintenance Cost ($)",
        "Annual Grand Maintenance Cost",
    ):
        row = {
            "Row Label": label,
            "Category": "",
            "Item": "",
            "Unit": "",
            "Unit Cost $": None,
            "Number of Units": None,
        }
        for col in _MAINT_COST_COLS:
            row[col] = maint_totals.get(col, 0.0)
        rows.append(row)
    return pd.DataFrame(rows)


def _compute_npv_series(capital_totals, maintenance_totals):
    """20-year NPV table matching CostCalculator.net_present_value."""
    annual_esclation_rate = 2.99 / 100.0
    npv_discount_rate = 5.01 / 100.0
    df = pd.DataFrame({"Year": list(range(1, 21))})
    methods = (
        (
            "Spreading Pond",
            "Spreading Pond Cost ($)",
            "Spreading Pond Maintenance Cost ($)",
            "Spreading Pond Net Present Value ($)",
        ),
        (
            "Injection Wells",
            "Injection Wells Cost ($)",
            "Injection Wells Maintenance Cost ($)",
            "Injection Wells Net Present Value ($)",
        ),
        ("Dry Wells", "Dry Wells Cost ($)", "Dry Wells Maintenance Cost ($)", "Dry Wells Net Present Value ($)"),
    )
    for _name, cap_key, maint_key, npv_key in methods:
        capital_cost = _parse_cost_float(capital_totals.get(cap_key))
        annual_maintenance_cost = _parse_cost_float(maintenance_totals.get(maint_key))
        inflation_adjusted = []
        pv_costs = 0.0
        net_value = []
        for i in range(1, 21):
            if i == 1:
                current = annual_maintenance_cost
            else:
                previous = inflation_adjusted[i - 2]
                current = previous + previous * annual_esclation_rate
            inflation_adjusted.append(current)
            pv_costs = pv_costs + (current / (1 + npv_discount_rate) ** i)
            net_value.append(pv_costs + capital_cost)
        df[npv_key] = net_value
    return df


def _prepare_cost_display_df(df, cost_columns, not_feasible_options, label_col="Row Label"):
    """Round/format method columns and mask infeasible options for DataTable."""
    if df is None or df.empty:
        return df
    out = df.copy()
    # Keep Unit Cost / Number of Units numeric for editing
    for col in ("Unit Cost $", "Number of Units"):
        if col not in out.columns:
            continue

        def _num_or_none(x, *, round_to=None):
            if x is None or (isinstance(x, float) and pd.isna(x)) or str(x).strip() == "":
                return None
            val = _parse_cost_float(x)
            if round_to is not None:
                return round(val, round_to)
            return val

        if col == "Number of Units":
            out[col] = out[col].apply(lambda x: _num_or_none(x, round_to=2))
        else:
            out[col] = out[col].apply(_num_or_none)
    _round_total_rows_in_cost_df(out, cost_columns, label_col=label_col)
    _format_cost_column_values(out, cost_columns, label_col=label_col, round_all=False)
    _mask_infeasible_cost_columns(out, cost_columns, not_feasible_options)
    return out.fillna("")


def _editable_cost_datatable(df, table_id, summary_styles):
    """DataTable with editable Unit Cost $ (Number of Units is read-only)."""
    columns = []
    for col in df.columns:
        if col == "Number of Units":
            columns.append(
                {
                    "name": col,
                    "id": col,
                    "type": "numeric",
                    "editable": False,
                    "format": Format(precision=2, scheme=Scheme.fixed),
                },
            )
        elif col == "Unit Cost $":
            columns.append(
                {
                    "name": col,
                    "id": col,
                    "type": "numeric",
                    "editable": True,
                },
            )
        else:
            columns.append({"name": col, "id": col, "editable": False})
    return dash_table.DataTable(
        id=table_id,
        data=df.to_dict("records"),
        columns=columns,
        style_cell=datatable_base_style_cell(textAlign="left"),
        style_header=datatable_base_style_header(),
        style_data=datatable_computed_data_style(whiteSpace="normal", height="auto"),
        style_data_conditional=list(summary_styles)
        + [
            {
                "if": {"column_id": "Unit Cost $"},
                "backgroundColor": "#fff8e1",
            },
        ],
        page_size=50,
        tooltip_header={
            "Unit Cost $": "Editable — change unit cost and totals recalculate",
            "Number of Units": "Calculated quantity (not editable)",
        },
        tooltip_delay=0,
        tooltip_duration=None,
    )


def _cost_summary_single_value(text):
    """Centered single total for Cost Summary cards."""
    return html.Div(
        text,
        style={
            "fontSize": "1.25rem",
            "fontWeight": "700",
            "color": "#1c2833",
            "fontVariantNumeric": "tabular-nums",
            "letterSpacing": "-0.01em",
            "textAlign": "center",
            "width": "100%",
        },
    )


def _cost_summary_option_rows(rows):
    """Neat label / value rows for Spreading, Injection, Dry Well."""
    children = []
    for i, (label, value) in enumerate(rows):
        children.append(
            html.Div(
                [
                    html.Div(
                        label,
                        style={
                            "fontSize": "0.7rem",
                            "fontWeight": "700",
                            "letterSpacing": "0.05em",
                            "textTransform": "uppercase",
                            "color": "#6c757d",
                            "marginBottom": "0.15rem",
                        },
                    ),
                    html.Div(
                        value,
                        style={
                            "fontSize": "0.92rem",
                            "fontWeight": "600",
                            "color": "#1c2833",
                            "fontVariantNumeric": "tabular-nums",
                            "lineHeight": "1.25",
                        },
                    ),
                ],
                style={
                    "padding": "0.5rem 0",
                    "borderBottom": ("1px solid #e8ecef" if i < len(rows) - 1 else "none"),
                },
            ),
        )
    return html.Div(children, style={"width": "100%", "textAlign": "left"})


def _format_cost_summary_display(cost_data, cost_type, selected_technology, not_feasible_options):
    """Format Cost Summary cards (capital / maintenance / NPV)."""
    if cost_data is None:
        return _cost_summary_single_value("$0")

    if isinstance(cost_data, dict):
        cost_data = pd.Series(cost_data)

    def _cost_str_for_option(option_name, value):
        if option_name in not_feasible_options:
            return "N/A"
        if not pd.notna(value) or float(value) == 0:
            return "$0"
        return _format_total_usd_range(value)

    def _three_option_block(spreading, injection, dry_well):
        return _cost_summary_option_rows(
            [
                ("Spreading", _cost_str_for_option("Surface Recharge", spreading)),
                ("Injection", _cost_str_for_option("Injection Well", injection)),
                ("Dry Well", _cost_str_for_option("Dry Well", dry_well)),
            ],
        )

    if isinstance(cost_data, pd.Series):
        if cost_type == "Capital":
            spreading_col = "Spreading Pond Cost ($)"
            injection_col = "Injection Wells Cost ($)"
            dry_well_col = "Dry Wells Cost ($)"
        elif cost_type == "Maintenance":
            spreading_col = "Spreading Pond Maintenance Cost ($)"
            injection_col = "Injection Wells Maintenance Cost ($)"
            dry_well_col = "Dry Wells Maintenance Cost ($)"
        elif cost_type == "NPV":
            spreading_col = "Spreading Pond Net Present Value ($)"
            injection_col = "Injection Wells Net Present Value ($)"
            dry_well_col = "Dry Wells Net Present Value ($)"
        else:
            spreading_col = "Spreading Pond Cost ($)"
            injection_col = "Injection Wells Cost ($)"
            dry_well_col = "Dry Wells Cost ($)"

        if selected_technology is None:
            spreading = cost_data.get(spreading_col, 0) if spreading_col in cost_data.index else 0
            injection = cost_data.get(injection_col, 0) if injection_col in cost_data.index else 0
            dry_well = cost_data.get(dry_well_col, 0) if dry_well_col in cost_data.index else 0
            return _three_option_block(spreading, injection, dry_well)

        tech_mapping = {
            "spreading_basins": spreading_col,
            "Surface Recharge": spreading_col,
            "injection_wells": injection_col,
            "Injection Well": injection_col,
            "dry_wells": dry_well_col,
            "Dry Well": dry_well_col,
        }
        cost_column = None
        for tech_key, col_name in tech_mapping.items():
            if (
                tech_key.lower() in str(selected_technology).lower()
                or str(selected_technology).lower() in tech_key.lower()
            ) and col_name in cost_data.index:
                cost_column = col_name
                break
        if cost_column and cost_column in cost_data.index:
            option_name = _COST_COLUMN_TO_OPTION.get(cost_column)
            if option_name in not_feasible_options:
                return _cost_summary_single_value("N/A")
            cost_value = cost_data[cost_column]
            return _cost_summary_single_value(_format_total_usd_range(cost_value) if pd.notna(cost_value) else "$0")
        spreading = cost_data.get(spreading_col, 0) if spreading_col in cost_data.index else 0
        injection = cost_data.get(injection_col, 0) if injection_col in cost_data.index else 0
        dry_well = cost_data.get(dry_well_col, 0) if dry_well_col in cost_data.index else 0
        return _three_option_block(spreading, injection, dry_well)

    return _cost_summary_single_value(_format_total_usd_range(cost_data) if pd.notna(cost_data) else "$0")


def _build_npv_panel(npv_df, not_feasible_options):
    """NPV chart + table panel used by Cost Analysis."""
    npv_columns = list(_NPV_COLS)
    npv_df_plot = npv_df.copy()
    for col in npv_columns:
        if col in npv_df_plot.columns:
            npv_df_plot[col] = npv_df_plot[col].apply(
                lambda x: _round_to_nearest_thousand(x) if pd.notna(x) and str(x).strip() != "" else x,
            )
    for col in npv_columns:
        if col in npv_df.columns:
            npv_df[col] = npv_df[col].apply(
                lambda x: f"{_round_to_nearest_thousand(x):,.0f}" if pd.notna(x) and str(x).strip() != "" else "",
            )
    _mask_infeasible_cost_columns(npv_df, npv_columns, not_feasible_options)
    npv_df = npv_df.fillna("")

    npv_plot = go.Figure()
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c"]
    for i, col in enumerate(npv_columns):
        if col not in npv_df_plot.columns:
            continue
        option_name = _COST_COLUMN_TO_OPTION.get(col)
        if option_name in not_feasible_options:
            continue
        yvals = npv_df_plot[col]
        npv_plot.add_trace(
            go.Bar(
                x=npv_df_plot["Year"] if "Year" in npv_df_plot.columns else list(range(1, 21)),
                y=yvals,
                name=col.replace(" Net Present Value ($)", ""),
                marker_color=colors[i % len(colors)],
                text=[f"${_parse_cost_float(v):,.0f}" for v in yvals],
                textposition="outside",
                hovertemplate="Year: %{x}<br>" + col + ": $%{y:,.0f}<extra></extra>",
            ),
        )
    npv_plot.update_layout(
        title="Net Present Value Over 20 Years",
        xaxis_title="Year",
        yaxis_title="Net Present Value ($)",
        xaxis={"tickmode": "linear", "tick0": 1, "dtick": 1},
        yaxis={"tickformat": "$,.0f"},
        height=500,
        autosize=True,
        margin={"l": 50, "r": 50, "t": 50, "b": 50},
        plot_bgcolor="white",
        paper_bgcolor="white",
        barmode="group",
    )
    table = dash_table.DataTable(
        data=npv_df.to_dict("records"),
        columns=[{"name": col, "id": col} for col in npv_df.columns],
        style_cell=datatable_base_style_cell(textAlign="left"),
        style_header=datatable_base_style_header(),
        style_data=datatable_computed_data_style(whiteSpace="normal", height="auto"),
        style_data_conditional=[
            {
                "if": {"row_index": max(len(npv_df) - 1, 0)},
                "backgroundColor": "#bbdefb",
                "fontWeight": "bold",
                "color": "#0d47a1",
            },
        ],
        page_size=25,
    )
    return dbc.Container(
        [
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.H5("Net Present Value Chart", className="mb-3"),
                            dcc.Graph(figure=npv_plot, id="npv-chart", style={"height": "500px"}),
                        ],
                        width=12,
                    ),
                ],
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.H5("Net Present Value Table", className="mb-3"),
                            table,
                        ],
                        width=12,
                    ),
                ],
            ),
        ],
        fluid=True,
    )


_LEGACY_CONVEYANCE = {
    "trapezoidal": "gravity_ditch",
    "pipeline": "gravity_pipeline",
    "pumped": "pumped_pipeline",
}
_VALID_CONVEYANCE = {
    "gravity_ditch",
    "gravity_pipeline",
    "pumped_pipeline",
    "pumped_ditch",
}
_DEFAULT_CONVEYANCE = "gravity_ditch"
_MILES_TO_FEET = 5280.0


def _normalize_conveyance_method(method):
    """Map legacy conveyance values to the current 4-option set."""
    if method in _LEGACY_CONVEYANCE:
        method = _LEGACY_CONVEYANCE[method]
    if method not in _VALID_CONVEYANCE:
        return _DEFAULT_CONVEYANCE
    return method


def _source_to_recharge_distance_miles():
    """Straight-line miles between Water Source tab source and recharge sites."""
    try:
        from mar_dss.app.components.water_source_tab import (
            _haversine_miles,
            ensure_water_source_site_coordinates,
        )
    except ImportError:
        from ..components.water_source_tab import (
            _haversine_miles,
            ensure_water_source_site_coordinates,
        )
    slat, slon, rlat, rlon = ensure_water_source_site_coordinates()
    return float(_haversine_miles(slat, slon, rlat, rlon))


def _sync_conveyance_distance_storage():
    """Store source→recharge distance (miles) for costing and reports."""
    miles = _source_to_recharge_distance_miles()
    dash_storage.set_data("distance_to_sediment", miles)
    return miles


def _sediment_target_from_turbidity():
    """
    Map Water Quality Q2 turbidity to sediment removal target.

    turbidity < 20 NTU (<5 or 5-20) → Medium Silt
    otherwise (>20 or Unknown) → Fine Silt
    """
    try:
        from mar_dss.app.components.environmental_impact_tab import (
            WQ_TURBIDITY_LOW,
            WQ_TURBIDITY_MOD,
        )
    except ImportError:
        from ..components.environmental_impact_tab import (
            WQ_TURBIDITY_LOW,
            WQ_TURBIDITY_MOD,
        )
    turbidity = dash_storage.get_data("wq_source_turbidity") or "Unknown"
    if turbidity in (WQ_TURBIDITY_LOW, WQ_TURBIDITY_MOD):
        return "medium_silt", "Medium Silt", turbidity
    return "fine_silt", "Fine Silt", turbidity


def _sync_sediment_target_from_turbidity():
    """Write sediment_target from WQ turbidity and return display label."""
    key, label, _turbidity = _sediment_target_from_turbidity()
    dash_storage.set_data("sediment_target", key)
    return key, label


_DEFAULT_PUMPED_STORAGE_VALUES = [
    "pumping_bag_filter_cost",
    "controls",
    "electrical_system",
]
_STORAGE_CONVEYANCE_DISTANCE_FT = 500.0
# Pipeline only — pump / bag filter / controls / electrical are consolidated
# under PUMPED CONVEYANCE in capital costs.
_DEFAULT_PUMPED_INFILTRATION_VALUES = [
    "infiltration_pipeline_cost",
]
# Fraction of MAR site area available for recharge (rest for other infrastructure)
_DEFAULT_MAX_INFILTRATION_AREA_FRACTION = 0.70


def _sync_storage_pumped_conveyance(storage_needed_yes):
    """When storage is Yes, enable all pumped-to-storage packages at 500 ft."""
    if storage_needed_yes:
        dash_storage.set_data("storage_pond_values", ["storage_pond_construction"])
        dash_storage.set_data("pumped_storage_values", list(_DEFAULT_PUMPED_STORAGE_VALUES))
        dash_storage.set_data("distance_to_storage_pond_ft", _STORAGE_CONVEYANCE_DISTANCE_FT)
    else:
        dash_storage.set_data("storage_pond_values", [])
        dash_storage.set_data("pumped_storage_values", [])


def _sync_pumped_infiltration_always_on():
    """Pumped conveyance to infiltration is always fully included (no UI)."""
    dash_storage.set_data("pumped_infiltration_values", list(_DEFAULT_PUMPED_INFILTRATION_VALUES))


def _sync_max_infiltration_area_always_on():
    """Max recharge area is always 70% of MAR site (no UI)."""
    dash_storage.set_data("max_infiltration_area", _DEFAULT_MAX_INFILTRATION_AREA_FRACTION)


def _sediment_removal_needed():
    """True when sediment removal is needed (Yes). Migrates legacy remove flag."""
    needed = dash_storage.get_data("sediment_removal_needed")
    if needed in ("yes", "no"):
        return needed == "yes"
    # Legacy: remove_sediment_removal_pond True meant exclude pond
    remove = dash_storage.get_data("remove_sediment_removal_pond")
    if remove is True:
        dash_storage.set_data("sediment_removal_needed", "no")
        return False
    dash_storage.set_data("sediment_removal_needed", "yes")
    return True


def setup_cost_callbacks(app):
    """Set up all cost-related callbacks."""

    @app.callback(
        Output({"type": "eng-help-modal", "section": MATCH}, "is_open"),
        [
            Input({"type": "eng-help-btn", "section": MATCH}, "n_clicks"),
            Input({"type": "eng-help-close", "section": MATCH}, "n_clicks"),
        ],
        State({"type": "eng-help-modal", "section": MATCH}, "is_open"),
        prevent_initial_call=True,
    )
    def toggle_engineering_card_help_modal(open_clicks, close_clicks, is_open):
        """Open or close an Engineering card help popup."""
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update
        trigger = ctx.triggered[0]["prop_id"]
        if "eng-help-btn" in trigger:
            return True
        if "eng-help-close" in trigger:
            return False
        return not is_open

    def _max_monthly_flow_ft3():
        """Maximum monthly Flow Estimate (ft³/month) from Water Source."""
        monthly = dash_storage.get_data("monthly_flow")
        if not isinstance(monthly, (list, tuple)) or len(monthly) == 0:
            return 0.0, None
        try:
            values = [float(v or 0) for v in monthly]
        except (TypeError, ValueError):
            return 0.0, None
        max_val = max(values) if values else 0.0
        try:
            from mar_dss.app.components.water_source_tab import FLOW_MONTHS
        except ImportError:
            from ..components.water_source_tab import FLOW_MONTHS
        month_label = None
        if len(values) == len(FLOW_MONTHS):
            month_label = FLOW_MONTHS[values.index(max_val)]
        return max_val, month_label

    def _design_event_flow_ft3_per_day(max_monthly, n_events):
        """Q_design (ft³/day) = max monthly flow / number of events."""
        try:
            max_monthly = float(max_monthly or 0.0)
            n_events = float(n_events or 0.0)
        except (TypeError, ValueError):
            return 0.0
        if n_events <= 0:
            return 0.0
        return max_monthly / n_events

    def _sync_total_runoff_from_design(max_monthly=None, n_events=None):
        """Store design event flow (ft³/day) as total_runoff_ft3 for cost sizing."""
        if max_monthly is None:
            max_monthly, _ = _max_monthly_flow_ft3()
        if n_events is None:
            n_events = dash_storage.get_data("design_events_per_month") or 4.0
        design_flow = _design_event_flow_ft3_per_day(max_monthly, n_events)
        dash_storage.set_data("total_runoff_ft3", design_flow)
        dash_storage.set_data("fraction_flow_capture", 1.0)
        return design_flow

    # Callback: refresh design metrics from monthly flow + events
    @app.callback(
        [
            Output("max-monthly-flow-display", "children"),
            Output("design-event-flow-display", "children"),
        ],
        [
            Input("top-tabs", "active_tab"),
            Input("design-events-per-month-input", "value"),
        ],
        prevent_initial_call=False,
    )
    def update_design_metrics_from_monthly_flow(active_tab, n_events):
        """Show max monthly flow and design event flow; sync total_runoff_ft3."""
        max_monthly, month_label = _max_monthly_flow_ft3()
        if n_events is None:
            n_events = dash_storage.get_data("design_events_per_month") or 4.0

        try:
            n_events = float(n_events)
        except (TypeError, ValueError):
            n_events = 4.0

        # Capture fraction is fixed at 1; design event flow (ft³/day) drives sizing.
        dash_storage.set_data("fraction_flow_capture", 1.0)
        design_flow = _sync_total_runoff_from_design(max_monthly, n_events)

        if month_label and max_monthly > 0:
            max_text = f"{max_monthly:,.2f}  ({month_label})"
        else:
            max_text = f"{max_monthly:,.2f}"

        return max_text, f"{design_flow:,.2f}"

    # Callback to save number of design events per month
    @app.callback(
        Output("design-events-per-month-input", "value"),
        [
            Input("design-events-per-month-input", "value"),
            Input("design-events-per-month-input", "n_blur"),
            Input("design-events-per-month-input", "n_submit"),
            Input("design-events-per-month-input", "id"),
        ],
        prevent_initial_call=False,
    )
    def handle_design_events_per_month(value, n_blur, n_submit, component_id):
        """Handle design events-per-month input and save to data storage."""
        ctx = dash.callback_context

        if not ctx.triggered:
            events = dash_storage.get_data("design_events_per_month") or 4.0
            dash_storage.set_data("design_events_per_month", float(events))
            return float(events)

        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1]
        if trigger_prop == "id":
            stored = dash_storage.get_data("design_events_per_month")
            if stored is not None:
                return float(stored)
            return value if value is not None else 4.0

        try:
            current_value = float(value) if value is not None else 4.0
        except (TypeError, ValueError):
            current_value = 4.0
        if current_value <= 0:
            current_value = 4.0
        dash_storage.set_data("design_events_per_month", current_value)
        _sync_total_runoff_from_design(n_events=current_value)
        return current_value

    # Callback to save conveyance method to data storage
    @app.callback(
        Output("conveyance-method-radio", "value"),
        [Input("conveyance-method-radio", "value"), Input("conveyance-method-radio", "id")],
        prevent_initial_call=False,
    )
    def handle_conveyance_method(value, component_id):
        """Handle conveyance method selection and save to data storage."""
        ctx = dash.callback_context

        if not ctx.triggered:
            method = _normalize_conveyance_method(dash_storage.get_data("conveyance_method") or _DEFAULT_CONVEYANCE)
            dash_storage.set_data("conveyance_method", method)
            return method

        current_selection = _normalize_conveyance_method(value if value else _DEFAULT_CONVEYANCE)
        dash_storage.set_data("conveyance_method", current_selection)
        return current_selection

    @app.callback(
        Output("conveyance-distance-display", "children"),
        Input("top-tabs", "active_tab"),
        prevent_initial_call=False,
    )
    def update_conveyance_distance_display(active_tab):
        """Show source→recharge straight-line distance used for conveyance length."""
        miles = _sync_conveyance_distance_storage()
        feet = miles * _MILES_TO_FEET
        return f"{miles:,.2f} miles  ({feet:,.0f} ft)"

    # Sediment removal needed (Yes/No)
    @app.callback(
        Output("sediment-removal-needed-radio", "value"),
        [
            Input("sediment-removal-needed-radio", "value"),
            Input("sediment-removal-needed-radio", "id"),
        ],
        prevent_initial_call=False,
    )
    def handle_sediment_removal_needed(value, component_id):
        """Save whether sediment removal is needed prior to recharge."""
        ctx = dash.callback_context

        if not ctx.triggered:
            needed = "yes" if _sediment_removal_needed() else "no"
            dash_storage.set_data("sediment_removal_needed", needed)
            # Keep legacy key in sync for older cost paths
            dash_storage.set_data("remove_sediment_removal_pond", needed == "no")
            return needed

        current = value if value in ("yes", "no") else "yes"
        dash_storage.set_data("sediment_removal_needed", current)
        dash_storage.set_data("remove_sediment_removal_pond", current == "no")
        return current

    @app.callback(
        Output("sediment-removal-target-display", "children"),
        Input("top-tabs", "active_tab"),
        prevent_initial_call=False,
    )
    def update_sediment_removal_target_display(active_tab):
        """Show silt target derived from Water Quality Q2 turbidity."""
        _key, label = _sync_sediment_target_from_turbidity()
        return label

    # Storage pond needed (Yes/No); auto-enables all pumped-to-storage at 500 ft
    @app.callback(
        Output("storage-needed-radio", "value"),
        [
            Input("storage-needed-radio", "value"),
            Input("storage-needed-radio", "id"),
        ],
        prevent_initial_call=False,
    )
    def handle_storage_needed(value, component_id):
        """Save whether a storage pond is needed; sync hidden pumped conveyance."""
        ctx = dash.callback_context

        if not ctx.triggered:
            needed = dash_storage.get_data("storage_needed")
            if needed not in ("yes", "no"):
                values = dash_storage.get_data("storage_pond_values") or []
                needed = "yes" if (not values) or ("storage_pond_construction" in values) else "no"
            dash_storage.set_data("storage_needed", needed)
            _sync_storage_pumped_conveyance(needed == "yes")
            return needed

        current = value if value in ("yes", "no") else "yes"
        dash_storage.set_data("storage_needed", current)
        _sync_storage_pumped_conveyance(current == "yes")
        return current

    # All three recharge methods are always estimated (fixed checklist; not user-editable).
    _ALL_INFILTRATION_METHODS = [
        "infiltration_basin",
        "dry_wells",
        "injection_wells",
    ]

    @app.callback(
        Output("infiltration-method-checklist", "value"),
        [
            Input("infiltration-method-checklist", "value"),
            Input("infiltration-method-checklist", "id"),
        ],
        prevent_initial_call=False,
    )
    def handle_infiltration_method(value, component_id):
        """Keep all three recharge methods selected and sync related storage."""
        # Always keep pumped conveyance to infiltration fully active (hidden UI)
        _sync_pumped_infiltration_always_on()
        # Always keep max recharge area at 70% of MAR site (hidden UI)
        _sync_max_infiltration_area_always_on()

        dash_storage.set_data("infiltration_method", "infiltration_basin")
        dash_storage.set_data("infiltration_methods", list(_ALL_INFILTRATION_METHODS))
        return list(_ALL_INFILTRATION_METHODS)

    @app.callback(
        [
            Output("capital-cost-display", "children"),
            Output("annual-maintenance-cost-display", "children"),
            Output("npv-20-years-display", "children"),
            Output("capital-cost-table-content", "children"),
            Output("maintenance-cost-table-content", "children"),
            Output("npv-table-content", "children"),
            Output("cost-economics-revision", "data"),
        ],
        [
            Input("top-tabs", "active_tab"),
            Input("analysis-tabs", "active_tab"),
        ],
        prevent_initial_call=False,
    )
    def update_cost_calculations(
        top_tab,
        analysis_tab,
    ):
        """Update cost calculations based on engineering inputs.

        Always recalculates when the Cost Analysis tab is shown so changes such as
        conveyance method (stored from Engineering) are reflected. Do not Input
        Engineering component ids here — that tab is lazy-loaded and those ids
        are absent until Engineering has been opened.
        """

        # Only calculate if we're on the Analysis tab and Cost sub-tab is selected
        if not top_tab or not analysis_tab or top_tab != "analysis" or analysis_tab != "analysis-cost":
            return (
                dash.no_update,
                dash.no_update,
                dash.no_update,
                dash.no_update,
                dash.no_update,
                dash.no_update,
                dash.no_update,
            )

        cost_calculator = None
        try:
            from mar_dss.app.callbacks.analysis_callbacks import (
                create_and_run_cost_calculator,
            )

            cost_calculator = create_and_run_cost_calculator()
        except Exception as exc:
            logger.warning(f"create_and_run_cost_calculator failed ({exc}); falling back to local CostCalculator")
            cost_calculator = None

        if cost_calculator is None:
            monthly = dash_storage.get_data("monthly_flow") or []
            try:
                max_monthly = max(float(v or 0) for v in monthly) if monthly else 0.0
            except (TypeError, ValueError):
                max_monthly = 0.0
            n_events = float(dash_storage.get_data("design_events_per_month") or 4.0)
            if n_events <= 0:
                n_events = 4.0
            total_runoff_ft3 = max_monthly / n_events
            dash_storage.set_data("total_runoff_ft3", total_runoff_ft3)
            dash_storage.set_data("fraction_flow_capture", 1.0)
            runoff_volume_ft3 = float(total_runoff_ft3)
            distance_to_sediment_miles = _sync_conveyance_distance_storage()
            distance_to_sediment_ft = float(distance_to_sediment_miles) * _MILES_TO_FEET
            distance_to_storage_pond_ft = float(dash_storage.get_data("distance_to_storage_pond_ft")) or 1.0
            sediment_target, sediment_target_display = _sync_sediment_target_from_turbidity()
            conveyance_method = _normalize_conveyance_method(
                dash_storage.get_data("conveyance_method") or _DEFAULT_CONVEYANCE,
            )
            dash_storage.set_data("conveyance_method", conveyance_method)

            storm_design_depth = 1.8
            from mar_dss.rules.defaults import get_default

            # Prefer geohydro dry-/injection-well counts from the decision graph.
            graph = dash_storage.get_data("decision_graph")
            n_dry = 0
            n_inj = 5
            q_inj_gpm = 50.0
            if graph is not None:
                dry_result = graph.get_node_value("number_of_dry_wells")
                if isinstance(dry_result, dict):
                    try:
                        n_dry = int(float(dry_result.get("number_of_dry_wells", 0) or 0))
                    except (TypeError, ValueError):
                        n_dry = 0
                inj_result = graph.get_node_value("number_of_injection_wells")
                if isinstance(inj_result, dict):
                    try:
                        n_inj = int(float(inj_result.get("number_of_wells", 5) or 5))
                    except (TypeError, ValueError):
                        n_inj = 5
                    try:
                        from mar_dss.rules.defaults import ft3_per_day_to_gpm

                        q_inj_gpm = ft3_per_day_to_gpm(float(inj_result.get("Q_per_well", 0) or 0))
                        if q_inj_gpm <= 0:
                            q_inj_gpm = 50.0
                    except (TypeError, ValueError):
                        q_inj_gpm = 50.0

            cost_calculator = CostCalculator(
                water_source="stormwater",
                storm_design_depth=storm_design_depth,
                drainage_basin_area_acres=35,
                total_storm_volume_af=6.52,
                basin_soil_type_infiltration_rate_in_per_hr=0.2,
                total_runoff_volume_ft3=runoff_volume_ft3,
                fine_sediment_removal_goal=sediment_target_display,
                distance_collection_to_sediment_pond_ft=distance_to_sediment_ft,
                distance_sediment_to_storage_pond_ft=distance_to_storage_pond_ft,
                dry_well_infiltration_rate_in_per_hr=5,
                dry_well_transfer_rate_gpm=float(get_default("max_dry_well_transfer_rate_gpm")),
                injection_well_transfer_rate_gpm=q_inj_gpm,
                number_of_injection_wells=n_inj,
                collection_to_sediment_removal__conveyance_method=conveyance_method,
                dry_well_diameter_ft=6,
                recharge_method="dry_well",
                number_of_dry_wells=n_dry,
            )
            cost_calculator.calculate_cost()

        cols = [
            "Spreading Pond Cost ($)",
            "Injection Wells Cost ($)",
            "Dry Wells Cost ($)",
        ]
        capital_cost_num = cost_calculator.capital_costs_calculations.loc["Capital Total Cost", cols]
        dash_storage.set_data(
            "capital_cost_num",
            totals_series_to_storage_dict(capital_cost_num, CAPITAL_COST_TOTAL_KEYS),
        )

        cols = [
            "Spreading Pond Maintenance Cost ($)",
            "Injection Wells Maintenance Cost ($)",
            "Dry Wells Maintenance Cost ($)",
        ]
        maintenance_cost_num = cost_calculator.maintenance_costs_calculations.loc["Annual Grand Maintenance Cost", cols]
        dash_storage.set_data(
            "maintenance_cost_num",
            totals_series_to_storage_dict(maintenance_cost_num, MAINTENANCE_COST_TOTAL_KEYS),
        )
        cols = [
            "Spreading Pond Net Present Value ($)",
            "Injection Wells Net Present Value ($)",
            "Dry Wells Net Present Value ($)",
        ]
        net_val = cost_calculator.net_present_value_calculations[cols].values[-1]
        net_val_dict = {}
        for i, col in enumerate(cols):
            net_val_dict[col] = net_val[i]
        dash_storage.set_data("net_val", net_val_dict)

        dash_storage.set_data(
            "capital_costs_calculations_df",
            cost_calculator.capital_costs_calculations,
        )
        dash_storage.set_data(
            "maintenance_costs_calculations_df",
            cost_calculator.maintenance_costs_calculations,
        )
        dash_storage.set_data(
            "npv_calculations_df",
            cost_calculator.net_present_value_calculations,
        )

        # Get selected technology to determine which cost to display
        selected_technology = dash_storage.get_data("selected_mar_technology")
        not_feasible_options = _get_not_feasible_option_names()

        # Capital table — apply user unit/quantity overrides, then recompute
        capital_df = _cost_table_dataframe(None, cost_calculator, "capital_costs_calculations")
        capital_df = capital_df.reset_index()
        capital_df, capital_label_col = _ensure_label_column(capital_df)
        _apply_unit_overrides_to_display_df(
            capital_df,
            dash_storage.get_data(_CAPITAL_UNIT_OVERRIDES_KEY),
            label_col=capital_label_col,
        )
        _recompute_capital_display_df(capital_df, label_col=capital_label_col)
        capital_totals = _totals_from_display_df(
            capital_df,
            _CAPITAL_COST_COLS,
            "Capital Total Cost",
            label_col=capital_label_col,
        )
        dash_storage.set_data(
            "capital_cost_num",
            totals_series_to_storage_dict(pd.Series(capital_totals), CAPITAL_COST_TOTAL_KEYS),
        )
        capital_df_display = _prepare_cost_display_df(
            capital_df,
            _CAPITAL_COST_COLS,
            not_feasible_options,
            capital_label_col,
        )
        capital_summary_styles = [
            {
                "if": {
                    "filter_query": (
                        '{Row Label} contains "Total" || {Row Label} contains "Subtotal" '
                        '|| {Row Label} contains "Capital" || {Item} = null'
                    ),
                },
                "backgroundColor": "#bbdefb",
                "fontWeight": "bold",
                "color": "#0d47a1",
            },
        ]
        capital_cost_table = html.Div(
            [
                html.Div(
                    [
                        dbc.Button(
                            "Reset unit costs to defaults",
                            id="reset-capital-unit-costs-btn",
                            size="sm",
                            className="me-2",
                            style={
                                "backgroundColor": "#fd7e14",
                                "borderColor": "#fd7e14",
                                "color": "white",
                            },
                        ),
                        html.Span(
                            "Yellow Unit Cost $ cells are editable. Number of Units is calculated and not editable.",
                            className="small fw-bold",
                        ),
                    ],
                    className="d-flex align-items-center flex-wrap mb-2 gap-2",
                ),
                _editable_cost_datatable(
                    capital_df_display,
                    "capital-cost-datatable",
                    capital_summary_styles,
                ),
            ],
        )

        # Maintenance = 5% of capital (no line-item O&M model)
        maintenance_totals = _maintenance_totals_from_capital(capital_totals)
        dash_storage.set_data(
            "maintenance_cost_num",
            totals_series_to_storage_dict(pd.Series(maintenance_totals), MAINTENANCE_COST_TOTAL_KEYS),
        )
        dash_storage.set_data(_MAINT_UNIT_OVERRIDES_KEY, {})
        maintenance_df_display = _prepare_cost_display_df(
            _simple_maintenance_display_df(capital_totals),
            _MAINT_COST_COLS,
            not_feasible_options,
            "Row Label",
        )
        maintenance_summary_styles = [
            {
                "if": {
                    "filter_query": (
                        '{Row Label} contains "Total" || {Row Label} contains "Subtotal" '
                        '|| {Row Label} contains "Maintenance" || {Item} = null'
                    ),
                },
                "backgroundColor": "#bbdefb",
                "fontWeight": "bold",
                "color": "#0d47a1",
            },
        ]
        # Read-only table (O&M is derived from capital, not edited here)
        maint_columns = [
            {
                "name": col,
                "id": col,
                "editable": False,
                **(
                    {
                        "type": "numeric",
                        "format": Format(precision=2, scheme=Scheme.fixed),
                    }
                    if col == "Number of Units"
                    else ({"type": "numeric"} if col == "Unit Cost $" else {})
                ),
            }
            for col in maintenance_df_display.columns
        ]
        maintenance_cost_table = html.Div(
            [
                html.P(
                    "Annual maintenance is 5% of each option's Capital Total Cost.",
                    className="text-muted small mb-2 fw-bold",
                ),
                dash_table.DataTable(
                    id="maintenance-cost-datatable",
                    data=maintenance_df_display.to_dict("records"),
                    columns=maint_columns,
                    style_cell=datatable_base_style_cell(textAlign="left"),
                    style_header=datatable_base_style_header(),
                    style_data=datatable_computed_data_style(whiteSpace="normal", height="auto"),
                    style_data_conditional=maintenance_summary_styles,
                    page_size=50,
                ),
            ],
        )

        npv_df = _compute_npv_series(capital_totals, maintenance_totals)
        net_val_dict = {col: float(npv_df[col].iloc[-1]) for col in _NPV_COLS if col in npv_df.columns}
        dash_storage.set_data("net_val", net_val_dict)
        dash_storage.set_data("npv_calculations_df", npv_df.copy())

        capital_cost = _format_cost_summary_display(
            pd.Series(capital_totals),
            "Capital",
            selected_technology,
            not_feasible_options,
        )
        annual_maintenance_cost = _format_cost_summary_display(
            pd.Series(maintenance_totals),
            "Maintenance",
            selected_technology,
            not_feasible_options,
        )
        npv_20_years = _format_cost_summary_display(
            pd.Series(net_val_dict),
            "NPV",
            selected_technology,
            not_feasible_options,
        )
        npv_table = _build_npv_panel(npv_df, not_feasible_options)

        return (
            capital_cost,
            annual_maintenance_cost,
            npv_20_years,
            capital_cost_table,
            maintenance_cost_table,
            npv_table,
            bump_cost_economics_revision(),
        )

    def _capital_edit_outputs(capital_totals, capital_display_df):
        """Shared outputs after capital changes: capital + 5% O&M + NPV."""
        selected_technology = dash_storage.get_data("selected_mar_technology")
        not_feasible_options = _get_not_feasible_option_names()
        maint_totals = _maintenance_totals_from_capital(capital_totals)
        dash_storage.set_data(
            "maintenance_cost_num",
            totals_series_to_storage_dict(pd.Series(maint_totals), MAINTENANCE_COST_TOTAL_KEYS),
        )
        maint_display_df = _prepare_cost_display_df(
            _simple_maintenance_display_df(capital_totals),
            _MAINT_COST_COLS,
            not_feasible_options,
            "Row Label",
        )
        capital_display = _format_cost_summary_display(
            pd.Series(capital_totals),
            "Capital",
            selected_technology,
            not_feasible_options,
        )
        maint_display = _format_cost_summary_display(
            pd.Series(maint_totals),
            "Maintenance",
            selected_technology,
            not_feasible_options,
        )
        npv_df = _compute_npv_series(capital_totals, maint_totals)
        net_val = {col: float(npv_df[col].iloc[-1]) for col in _NPV_COLS if col in npv_df.columns}
        dash_storage.set_data("net_val", net_val)
        dash_storage.set_data("npv_calculations_df", npv_df.copy())
        npv_display = _format_cost_summary_display(
            pd.Series(net_val),
            "NPV",
            selected_technology,
            not_feasible_options,
        )
        revision = bump_cost_economics_revision()
        return (
            capital_display_df.to_dict("records"),
            capital_display,
            maint_display_df.to_dict("records"),
            maint_display,
            npv_display,
            _build_npv_panel(npv_df, not_feasible_options),
            revision,
        )

    def _rebuild_capital_display_from_defaults():
        """Rebuild capital table from calculator defaults (no unit-cost overrides)."""
        not_feasible_options = _get_not_feasible_option_names()
        raw = _coerce_stored_dataframe(dash_storage.get_data("capital_costs_calculations_df"))
        if raw is None or raw.empty:
            try:
                from mar_dss.app.callbacks.analysis_callbacks import (
                    create_and_run_cost_calculator,
                )

                calc = create_and_run_cost_calculator()
                raw = calc.capital_costs_calculations.copy()
            except Exception:
                return None
        df = raw.reset_index()
        df, label_col = _ensure_label_column(df)
        _recompute_capital_display_df(df, label_col=label_col)
        totals = _totals_from_display_df(df, _CAPITAL_COST_COLS, "Capital Total Cost", label_col)
        dash_storage.set_data(
            "capital_cost_num",
            totals_series_to_storage_dict(pd.Series(totals), CAPITAL_COST_TOTAL_KEYS),
        )
        display_df = _prepare_cost_display_df(df, _CAPITAL_COST_COLS, not_feasible_options, label_col)
        return _capital_edit_outputs(totals, display_df)

    def _sync_costs_after_capital_unit_edit(rows):
        """Recompute capital method/soft costs after Unit Cost $ edit."""
        if not rows:
            return (dash.no_update,) * 7

        df = pd.DataFrame(rows)
        df, label_col = _ensure_label_column(df)
        not_feasible_options = _get_not_feasible_option_names()
        soft_labels = _CAPITAL_SOFT_LABELS
        for i in df.index:
            row = df.loc[i].to_dict()
            if not _is_editable_cost_line_row(row, soft_labels, label_col):
                df.at[i, "Unit Cost $"] = None
        _recompute_capital_display_df(df, label_col=label_col)
        overrides = _extract_unit_overrides_from_display_df(df, soft_labels, label_col)
        dash_storage.set_data(_CAPITAL_UNIT_OVERRIDES_KEY, overrides)
        totals = _totals_from_display_df(df, _CAPITAL_COST_COLS, "Capital Total Cost", label_col)
        dash_storage.set_data(
            "capital_cost_num",
            totals_series_to_storage_dict(pd.Series(totals), CAPITAL_COST_TOTAL_KEYS),
        )
        display_df = _prepare_cost_display_df(df, _CAPITAL_COST_COLS, not_feasible_options, label_col)
        return _capital_edit_outputs(totals, display_df)

    @app.callback(
        Output("capital-cost-datatable", "data"),
        Output("capital-cost-display", "children", allow_duplicate=True),
        Output("maintenance-cost-datatable", "data", allow_duplicate=True),
        Output("annual-maintenance-cost-display", "children", allow_duplicate=True),
        Output("npv-20-years-display", "children", allow_duplicate=True),
        Output("npv-table-content", "children", allow_duplicate=True),
        Output("cost-economics-revision", "data", allow_duplicate=True),
        Input("capital-cost-datatable", "data_timestamp"),
        State("capital-cost-datatable", "data"),
        prevent_initial_call=True,
    )
    def on_capital_cost_units_edited(_ts, rows):
        return _sync_costs_after_capital_unit_edit(rows)

    @app.callback(
        Output("capital-cost-datatable", "data", allow_duplicate=True),
        Output("capital-cost-display", "children", allow_duplicate=True),
        Output("maintenance-cost-datatable", "data", allow_duplicate=True),
        Output("annual-maintenance-cost-display", "children", allow_duplicate=True),
        Output("npv-20-years-display", "children", allow_duplicate=True),
        Output("npv-table-content", "children", allow_duplicate=True),
        Output("cost-economics-revision", "data", allow_duplicate=True),
        Input("reset-capital-unit-costs-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def on_reset_capital_unit_costs(n_clicks):
        if not n_clicks:
            return (dash.no_update,) * 7
        dash_storage.set_data(_CAPITAL_UNIT_OVERRIDES_KEY, {})
        rebuilt = _rebuild_capital_display_from_defaults()
        if rebuilt is None:
            return (dash.no_update,) * 7
        return rebuilt
