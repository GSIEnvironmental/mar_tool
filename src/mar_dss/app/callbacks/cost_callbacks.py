"""
Callbacks for Cost calculations and display in the Engineering tab.
"""

import dash
from dash import Input, Output, State, html, dash_table, dcc, MATCH
import dash_bootstrap_components as dbc
import json
import pandas as pd
import plotly.graph_objects as go
import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.utils.excel_table import (
    datatable_base_style_cell,
    datatable_base_style_header,
    datatable_column_styles,
    datatable_computed_data_style,
)
from mar_dss.app.utils.cost_storage import (
    CAPITAL_COST_TOTAL_KEYS,
    MAINTENANCE_COST_TOTAL_KEYS,
    totals_series_to_storage_dict,
)


try:
    from mar_dss.app.callbacks.cost_calculator import CostCalculator
    from mar_dss.app.components.water_source_tab import WATER_SOURCE_LABELS
except ImportError:
    from .cost_calculator import CostCalculator
    from ..components.water_source_tab import WATER_SOURCE_LABELS

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
    return (
        "total" in text
        or "subtotal" in text
        or "grand maintenance" in text
    )


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
            lambda x: _round_to_nearest_thousand(x)
            if pd.notna(x) and str(x).strip() != ""
            else x
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
        for val, is_tot in zip(df[col], total_mask if not round_all else [True] * len(df)):
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
    """Option names rejected by feasibility analysis (same logic as Feasibilities tab)."""
    dss_results = dash_storage.get_data("dss_results")
    if dss_results is None or not hasattr(dss_results, "results") or not dss_results.results:
        return set()
    from mar_dss.app.callbacks.feasibilities_callbacks import _categorize_options

    categorized = _categorize_options(
        dss_results.results,
        getattr(dss_results, "filters", {}),
    )
    return {opt["name"] for opt in categorized.get("rejected", [])}


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
            ensure_water_source_site_coordinates,
            _haversine_miles,
        )
    except ImportError:
        from ..components.water_source_tab import (
            ensure_water_source_site_coordinates,
            _haversine_miles,
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
    "pipeline_cost",
    "pumping_bag_filter_cost",
    "controls",
    "electrical_system",
]
_STORAGE_CONVEYANCE_DISTANCE_FT = 500.0
_DEFAULT_PUMPED_INFILTRATION_VALUES = [
    "infiltration_pipeline_cost",
    "infiltration_pumping_bag_filter_cost",
    "infiltration_controls",
    "infiltration_electrical_system",
]
# Fraction of MAR site area available for recharge (rest for other infrastructure)
_DEFAULT_MAX_INFILTRATION_AREA_FRACTION = 0.70


def _sync_storage_pumped_conveyance(storage_needed_yes):
    """When storage is Yes, enable all pumped-to-storage packages at 500 ft."""
    if storage_needed_yes:
        dash_storage.set_data(
            "storage_pond_values", ["storage_pond_construction"]
        )
        dash_storage.set_data(
            "pumped_storage_values", list(_DEFAULT_PUMPED_STORAGE_VALUES)
        )
        dash_storage.set_data(
            "distance_to_storage_pond_ft", _STORAGE_CONVEYANCE_DISTANCE_FT
        )
    else:
        dash_storage.set_data("storage_pond_values", [])
        dash_storage.set_data("pumped_storage_values", [])


def _sync_pumped_infiltration_always_on():
    """Pumped conveyance to infiltration is always fully included (no UI)."""
    dash_storage.set_data(
        "pumped_infiltration_values", list(_DEFAULT_PUMPED_INFILTRATION_VALUES)
    )


def _sync_max_infiltration_area_always_on():
    """Max recharge area is always 70% of MAR site (no UI)."""
    dash_storage.set_data(
        "max_infiltration_area", _DEFAULT_MAX_INFILTRATION_AREA_FRACTION
    )


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
        [
            Input("conveyance-method-radio", "value"),
            Input("conveyance-method-radio", "id")
        ],
        prevent_initial_call=False
    )
    def handle_conveyance_method(value, component_id):
        """Handle conveyance method selection and save to data storage."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            method = _normalize_conveyance_method(
                dash_storage.get_data("conveyance_method") or _DEFAULT_CONVEYANCE
            )
            dash_storage.set_data("conveyance_method", method)
            return method

        current_selection = _normalize_conveyance_method(
            value if value else _DEFAULT_CONVEYANCE
        )
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
                needed = (
                    "yes"
                    if (not values) or ("storage_pond_construction" in values)
                    else "no"
                )
            dash_storage.set_data("storage_needed", needed)
            _sync_storage_pumped_conveyance(needed == "yes")
            return needed

        current = value if value in ("yes", "no") else "yes"
        dash_storage.set_data("storage_needed", current)
        _sync_storage_pumped_conveyance(current == "yes")
        return current

    # Callback to save infiltration method to data storage
    @app.callback(
        Output("infiltration-method-radio", "value"),
        [
            Input("infiltration-method-radio", "value"),
            Input("infiltration-method-radio", "id")
        ],
        prevent_initial_call=False
    )
    def handle_infiltration_method(value, component_id):
        """Handle infiltration method selection and save to data storage."""
        ctx = dash.callback_context
        # Always keep pumped conveyance to infiltration fully active (hidden UI)
        _sync_pumped_infiltration_always_on()
        # Always keep max recharge area at 70% of MAR site (hidden UI)
        _sync_max_infiltration_area_always_on()

        if not ctx.triggered:
            # Initial load - get saved value or use default, and save it
            method = dash_storage.get_data("infiltration_method") or "infiltration_basin"
            dash_storage.set_data("infiltration_method", method)
            return method
        
        current_selection = value if value else "infiltration_basin"
        dash_storage.set_data("infiltration_method", current_selection)
        return current_selection
    
    @app.callback(
        [
            Output("capital-cost-display", "children"),
            Output("annual-maintenance-cost-display", "children"),
            Output("npv-20-years-display", "children"),
            Output("capital-cost-table-content", "children"),
            Output("maintenance-cost-table-content", "children"),
            Output("npv-table-content", "children"),
        ],
        [
            Input("top-tabs", "active_tab"),
            Input("analysis-tabs", "active_tab"),
        ],
        prevent_initial_call=False
    )
    def update_cost_calculations(
        top_tab,
        analysis_tab,
    ):
        """Update cost calculations based on engineering inputs."""        
        
        # Only calculate if we're on the Analysis tab and Cost sub-tab is selected
        if not top_tab or not analysis_tab or top_tab != "analysis" or analysis_tab != "analysis-cost":
          
            return (
                dash.no_update,
                dash.no_update,
                dash.no_update,
                dash.no_update,
                dash.no_update,
                dash.no_update,
            )
       
        # Check if cost data already exists (from integrated analysis)
        existing_capital_costs = dash_storage.get_data("capital_cost_num")
        existing_capital_df = _coerce_stored_dataframe(
            dash_storage.get_data("capital_costs_calculations_df")
        )
        existing_maintenance_df = _coerce_stored_dataframe(
            dash_storage.get_data("maintenance_costs_calculations_df")
        )
        existing_npv_df = _coerce_stored_dataframe(
            dash_storage.get_data("npv_calculations_df")
        )

        if existing_capital_costs is not None and existing_capital_df is not None:
            # Cost data already exists from integrated analysis - use it without recalculating
            print("Using existing cost data from integrated analysis (skipping recalculation)")
            capital_cost_num = existing_capital_costs
            cost_calculator = None  # We'll use stored DataFrames instead
            
            # Get maintenance costs and NPV from storage
            maintenance_cost_num = dash_storage.get_data("maintenance_cost_num")
            net_val_dict = dash_storage.get_data("net_val") or {}
        else:
            # Cost data doesn't exist - run calculation
            print("Cost data not found - running cost calculation...")
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
            sediment_target, sediment_target_display = (
                _sync_sediment_target_from_turbidity()
            )
            conveyance_method = _normalize_conveyance_method(
                dash_storage.get_data("conveyance_method") or _DEFAULT_CONVEYANCE
            )
            dash_storage.set_data("conveyance_method", conveyance_method)
            
            storm_design_depth = 1.8
            from mar_dss.rules.defaults import get_default

            cost_calculator = CostCalculator(
            water_source="stormwater", storm_design_depth=storm_design_depth,
            drainage_basin_area_acres=35, # todo: this should be renamed to MAR site area.
            total_storm_volume_af=6.52, # todo: not used, remove if not needed
            basin_soil_type_infiltration_rate_in_per_hr=0.2,
            total_runoff_volume_ft3=runoff_volume_ft3,
            fine_sediment_removal_goal= sediment_target_display,
            distance_collection_to_sediment_pond_ft=distance_to_sediment_ft,
            distance_sediment_to_storage_pond_ft=distance_to_storage_pond_ft,
            dry_well_infiltration_rate_in_per_hr=5,
            dry_well_transfer_rate_gpm=float(
                get_default("max_dry_well_transfer_rate_gpm")
            ),
            injection_well_transfer_rate_gpm=50,
            number_of_injection_wells=5,
            collection_to_sediment_removal__conveyance_method=conveyance_method,
            dry_well_diameter_ft=6,
            recharge_method="dry_well"
        )
            cost_calculator.calculate_cost()
            cols = ['Spreading Pond Cost ($)', 'Injection Wells Cost ($)', 'Dry Wells Cost ($)']
            capital_cost_num = cost_calculator.capital_costs_calculations.loc['Capital Total Cost',
             cols]
            dash_storage.set_data(
                "capital_cost_num",
                totals_series_to_storage_dict(capital_cost_num, CAPITAL_COST_TOTAL_KEYS),
            )

            cols = [ 'Spreading Pond Maintenance Cost ($)', 'Injection Wells Maintenance Cost ($)', 'Dry Wells Maintenance Cost ($)']
            maintenance_cost_num = cost_calculator.maintenance_costs_calculations.loc['Annual Grand Maintenance Cost', cols]
            dash_storage.set_data(
                "maintenance_cost_num",
                totals_series_to_storage_dict(maintenance_cost_num, MAINTENANCE_COST_TOTAL_KEYS),
            )
            cols =['Spreading Pond Net Present Value ($)',
           'Injection Wells Net Present Value ($)',
           'Dry Wells Net Present Value ($)']
            net_val = cost_calculator.net_present_value_calculations[cols].values[-1]
            net_val_dict = {}
            for i, col in enumerate(cols):
                net_val_dict[col] =net_val[i]
            net_val = net_val_dict
            dash_storage.set_data("net_val",net_val_dict)
            
            # Store DataFrames for future use
            dash_storage.set_data("capital_costs_calculations_df", cost_calculator.capital_costs_calculations)
            dash_storage.set_data("maintenance_costs_calculations_df", cost_calculator.maintenance_costs_calculations)
            dash_storage.set_data("npv_calculations_df", cost_calculator.net_present_value_calculations)
        
        # Get selected technology to determine which cost to display
        selected_technology = dash_storage.get_data("selected_mar_technology")
        not_feasible_options = _get_not_feasible_option_names()

        def _cost_str_for_option(option_name, value):
            if option_name in not_feasible_options:
                return "N/A"
            if not pd.notna(value) or float(value) == 0:
                return "$0"
            return _format_total_usd_range(value)

        # Format costs - show all three or one based on selection
        def format_cost_display(cost_data, cost_type="Capital"):
            """Format cost display to show 3 values or 1 based on selection."""
            if cost_data is None:
                return "$0"

            if isinstance(cost_data, dict):
                cost_data = pd.Series(cost_data)

            if isinstance(cost_data, pd.Series):
                # We have three cost values
                # Get column names based on cost type
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
                    # Show all three values
                    spreading = cost_data.get(spreading_col, 0) if spreading_col in cost_data.index else 0
                    injection = cost_data.get(injection_col, 0) if injection_col in cost_data.index else 0
                    dry_well = cost_data.get(dry_well_col, 0) if dry_well_col in cost_data.index else 0
                    
                    spreading_str = _cost_str_for_option("Surface Recharge", spreading)
                    injection_str = _cost_str_for_option("Injection Well", injection)
                    dry_well_str = _cost_str_for_option("Dry Well", dry_well)
                    return html.Div([
                        html.Div(f"Spreading: {spreading_str}", style={"margin-bottom": "5px"}),
                        html.Div(f"Injection: {injection_str}", style={"margin-bottom": "5px"}),
                        html.Div(f"Dry Well: {dry_well_str}")
                    ])
                else:
                    # Show selected technology cost
                    tech_mapping = {
                        "spreading_basins": spreading_col,
                        "Surface Recharge": spreading_col,
                        "injection_wells": injection_col,
                        "Injection Well": injection_col,
                        "dry_wells": dry_well_col,
                        "Dry Well": dry_well_col,
                    }
                    
                    # Try to find matching column
                    cost_column = None
                    for tech_key, col_name in tech_mapping.items():
                        if (tech_key.lower() in str(selected_technology).lower() or 
                            str(selected_technology).lower() in tech_key.lower()):
                            if col_name in cost_data.index:
                                cost_column = col_name
                                break
                    
                    if cost_column and cost_column in cost_data.index:
                        option_name = _COST_COLUMN_TO_OPTION.get(cost_column)
                        if option_name in not_feasible_options:
                            return "N/A"
                        cost_value = cost_data[cost_column]
                        return (
                            _format_total_usd_range(cost_value)
                            if pd.notna(cost_value)
                            else "$0"
                        )
                    else:
                        # Fallback: show all three
                        spreading = cost_data.get(spreading_col, 0) if spreading_col in cost_data.index else 0
                        injection = cost_data.get(injection_col, 0) if injection_col in cost_data.index else 0
                        dry_well = cost_data.get(dry_well_col, 0) if dry_well_col in cost_data.index else 0
                        
                        spreading_str = _cost_str_for_option("Surface Recharge", spreading)
                        injection_str = _cost_str_for_option("Injection Well", injection)
                        dry_well_str = _cost_str_for_option("Dry Well", dry_well)
                        return html.Div([
                            html.Div(f"Spreading: {spreading_str}", style={"margin-bottom": "5px"}),
                            html.Div(f"Injection: {injection_str}", style={"margin-bottom": "5px"}),
                            html.Div(f"Dry Well: {dry_well_str}")
                        ])
            else:
                # Single value (old format)
                return (
                    _format_total_usd_range(cost_data)
                    if pd.notna(cost_data)
                    else "$0"
                )
        
        capital_cost = format_cost_display(capital_cost_num, "Capital")
        annual_maintenance_cost = format_cost_display(maintenance_cost_num, "Maintenance")
        
        # Format NPV display - convert dict to Series for format_cost_display
        if net_val_dict:
            npv_series = pd.Series(net_val_dict)
            npv_20_years = format_cost_display(npv_series, "NPV")
        else:
            npv_20_years = "$0"
        
        # Create Capital Cost Table
        capital_df = _cost_table_dataframe(
            existing_capital_df, cost_calculator, "capital_costs_calculations"
        )
        # Reset index to make it a column
        capital_df = capital_df.reset_index()
        capital_df, capital_label_col = _ensure_label_column(capital_df)
        
        # Format numeric columns
        if 'Number of Units' in capital_df.columns:
            def format_units(x):
                try:
                    if pd.notna(x) and x != '' and str(x).strip() != '':
                        return f"{float(x):.2f}"
                    return ''
                except (ValueError, TypeError):
                    return ''
            capital_df['Number of Units'] = capital_df['Number of Units'].apply(format_units)
        
        cost_columns = ['Spreading Pond Cost ($)', 'Injection Wells Cost ($)', 'Dry Wells Cost ($)']
        _round_total_rows_in_cost_df(capital_df, cost_columns, label_col=capital_label_col)
        _format_cost_column_values(
            capital_df, cost_columns, label_col=capital_label_col, round_all=False
        )
        
        # Fill NaN values with empty strings for better display
        capital_df = capital_df.fillna('')

        summary_styles = [
            {
                'if': {
                    'filter_query': '{Row Label} contains "Total" || {Row Label} contains "Subtotal" || {Row Label} contains "Capital" || {Item} = null'
                },
                'backgroundColor': '#bbdefb',
                'fontWeight': 'bold',
                'color': '#0d47a1',
            }
        ]
        
        capital_cost_table = dash_table.DataTable(
            data=capital_df.to_dict('records'),
            columns=[
                {'name': col, 'id': col} for col in capital_df.columns
            ],
            style_cell=datatable_base_style_cell(textAlign='left'),
            style_header=datatable_base_style_header(),
            style_data=datatable_computed_data_style(whiteSpace='normal', height='auto'),
            style_data_conditional=summary_styles,
            page_size=50
        )
        
        # Create Maintenance Cost Table
        maintenance_df = _cost_table_dataframe(
            existing_maintenance_df, cost_calculator, "maintenance_costs_calculations"
        )
        # Reset index to make it a column
        maintenance_df = maintenance_df.reset_index()
        maintenance_df, maint_label_col = _ensure_label_column(maintenance_df)
        
        # Format numeric columns
        if 'Number of Units' in maintenance_df.columns:
            def format_units(x):
                try:
                    if pd.notna(x) and x != '' and str(x).strip() != '':
                        return f"{float(x):.2f}"
                    return ''
                except (ValueError, TypeError):
                    return ''
            maintenance_df['Number of Units'] = maintenance_df['Number of Units'].apply(format_units)
        
        maintenance_cost_columns = [
            'Spreading Pond Maintenance Cost ($)',
            'Injection Wells Maintenance Cost ($)',
            'Dry Wells Maintenance Cost ($)',
        ]
        # Round Subtotal / Total rows to nearest $1,000 (same as capital table)
        _round_total_rows_in_cost_df(
            maintenance_df, maintenance_cost_columns, label_col=maint_label_col
        )
        _format_cost_column_values(
            maintenance_df,
            maintenance_cost_columns,
            label_col=maint_label_col,
            round_all=False,
        )
        
        # Fill NaN values with empty strings for better display
        maintenance_df = maintenance_df.fillna('')

        maintenance_summary_styles = [
            {
                'if': {
                    'filter_query': '{Row Label} contains "Total" || {Row Label} contains "Subtotal" || {Row Label} contains "Maintenance" || {Item} = null'
                },
                'backgroundColor': '#bbdefb',
                'fontWeight': 'bold',
                'color': '#0d47a1',
            }
        ]
        
        maintenance_cost_table = dash_table.DataTable(
            data=maintenance_df.to_dict('records'),
            columns=[
                {'name': col, 'id': col} for col in maintenance_df.columns
            ],
            style_cell=datatable_base_style_cell(textAlign='left'),
            style_header=datatable_base_style_header(),
            style_data=datatable_computed_data_style(whiteSpace='normal', height='auto'),
            style_data_conditional=maintenance_summary_styles,
            page_size=50
        )
        
        # Create Net Present Value Table and Plot
        npv_df = _cost_table_dataframe(
            existing_npv_df, cost_calculator, "net_present_value_calculations"
        )
        # Reset index to make Year a column
        npv_df = npv_df.reset_index()
        if 'index' in npv_df.columns:
            npv_df = npv_df.rename(columns={'index': 'Year'})
        elif 'Year' not in npv_df.columns and npv_df.index.name == 'Year':
            npv_df.index.name = None
            npv_df = npv_df.reset_index()
            npv_df = npv_df.rename(columns={'index': 'Year'})
        
        npv_columns = [
            'Spreading Pond Net Present Value ($)',
            'Injection Wells Net Present Value ($)',
            'Dry Wells Net Present Value ($)'
        ]

        # Round all NPV values to nearest $1,000 for plot and table
        npv_df_plot = npv_df.copy()
        for col in npv_columns:
            if col in npv_df_plot.columns:
                npv_df_plot[col] = npv_df_plot[col].apply(
                    lambda x: _round_to_nearest_thousand(x)
                    if pd.notna(x) and str(x).strip() != ""
                    else x
                )

        _format_cost_column_values(
            npv_df, npv_columns, label_col=None, round_all=True
        )
        # Prefer $ prefix in NPV table for clarity
        for col in npv_columns:
            if col in npv_df.columns:
                npv_df[col] = [
                    f"${v}" if v not in ("", None) and not str(v).startswith("$") else (v or "")
                    for v in npv_df[col]
                ]
        
        # Get selected technology to determine which NPV to display
        selected_technology = dash_storage.get_data("selected_mar_technology")
        
        # Fill NaN values with empty strings for better display
        npv_df = npv_df.fillna('')
        
        # Create the bar plot
        npv_plot = go.Figure()
        
        # Map technology to column name
        tech_to_column = {
            "spreading_basins": "Spreading Pond Net Present Value ($)",
            "Surface Recharge": "Spreading Pond Net Present Value ($)",
            "injection_wells": "Injection Wells Net Present Value ($)",
            "Injection Well": "Injection Wells Net Present Value ($)",
            "dry_wells": "Dry Wells Net Present Value ($)",
            "Dry Well": "Dry Wells Net Present Value ($)",
        }
        
        if selected_technology is None:
            # Show all three technologies
            colors = ['#3498db', '#2ecc71', '#e74c3c']
            for i, col in enumerate(npv_columns):
                if col in npv_df_plot.columns:
                    npv_plot.add_trace(go.Bar(
                        x=npv_df_plot['Year'],
                        y=npv_df_plot[col],
                        name=col.replace(' Net Present Value ($)', ''),
                        marker_color=colors[i],
                        text=[f"${val:,.0f}" for val in npv_df_plot[col]],
                        textposition='outside',
                        hovertemplate=f'Year: %{{x}}<br>{col}: $%{{y:,.0f}}<extra></extra>'
                    ))
            npv_plot.update_layout(
                title='Net Present Value Over 20 Years',
                xaxis_title='Year',
                yaxis_title='Net Present Value ($)',
                xaxis=dict(tickmode='linear', tick0=1, dtick=1),
                yaxis=dict(tickformat='$,.0f'),
                height=500,
                autosize=True,
                margin=dict(l=50, r=50, t=50, b=50),
                plot_bgcolor='white',
                paper_bgcolor='white',
                barmode='group'
            )
        else:
            # Show selected technology only
            cost_column = None
            for tech_key, col_name in tech_to_column.items():
                if (tech_key.lower() in str(selected_technology).lower() or 
                    str(selected_technology).lower() in tech_key.lower()):
                    if col_name in npv_df_plot.columns:
                        cost_column = col_name
                        break
            
            if cost_column and cost_column in npv_df_plot.columns:
                npv_plot.add_trace(go.Bar(
                    x=npv_df_plot['Year'],
                    y=npv_df_plot[cost_column],
                    marker_color='#3498db',
                    text=[f"${val:,.0f}" for val in npv_df_plot[cost_column]],
                    textposition='outside',
                    hovertemplate=f'Year: %{{x}}<br>{cost_column}: $%{{y:,.0f}}<extra></extra>'
                ))
            else:
                # Fallback: show all three
                colors = ['#3498db', '#2ecc71', '#e74c3c']
                for i, col in enumerate(npv_columns):
                    if col in npv_df_plot.columns:
                        npv_plot.add_trace(go.Bar(
                            x=npv_df_plot['Year'],
                            y=npv_df_plot[col],
                            name=col.replace(' Net Present Value ($)', ''),
                            marker_color=colors[i],
                            text=[f"${val:,.0f}" for val in npv_df_plot[col]],
                            textposition='outside',
                            hovertemplate=f'Year: %{{x}}<br>{col}: $%{{y:,.0f}}<extra></extra>'
                        ))
            
            npv_plot.update_layout(
                title='Net Present Value Over 20 Years',
                xaxis_title='Year',
                yaxis_title='Net Present Value ($)',
                xaxis=dict(tickmode='linear', tick0=1, dtick=1),
                yaxis=dict(tickformat='$,.0f'),
                height=500,
                autosize=True,
                margin=dict(l=50, r=50, t=50, b=50),
                plot_bgcolor='white',
                paper_bgcolor='white'
            )
        
        npv_table = dash_table.DataTable(
            data=npv_df.to_dict('records'),
            columns=[
                {'name': col, 'id': col} for col in npv_df.columns
            ],
            style_cell=datatable_base_style_cell(textAlign='left'),
            style_header=datatable_base_style_header(),
            style_data=datatable_computed_data_style(whiteSpace='normal', height='auto'),
            style_data_conditional=[
                {
                    'if': {'row_index': len(npv_df) - 1},
                    'backgroundColor': '#bbdefb',
                    'fontWeight': 'bold',
                    'color': '#0d47a1',
                }
            ],
            page_size=25
        )
        
        # Combine table and plot in a row layout
        npv_table = dbc.Container([
            dbc.Row([
                dbc.Col([
                    html.H5("Net Present Value Chart", className="mb-3"),
                    dcc.Graph(
                        figure=npv_plot,
                        id='npv-chart',
                        style={'height': '500px'}
                    )
                ], width=12)
            ]),
            dbc.Row([
                dbc.Col([
                    html.H5("Net Present Value Table", className="mb-3"),
                    npv_table
                ], width=12)
            ])
        ], fluid=True)
        
        return (
            capital_cost,
            annual_maintenance_cost,
            npv_20_years,
            capital_cost_table,
            maintenance_cost_table,
            npv_table,
        )

