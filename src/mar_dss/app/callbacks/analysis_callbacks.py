"""
Callbacks for the Analysis tab lazy loading.
"""
from pathlib import Path
import logging
import dash
from dash import Input, Output, State, html
import dash_bootstrap_components as dbc
import mar_dss
import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.utils.cost_storage import (
    CAPITAL_COST_TOTAL_KEYS,
    MAINTENANCE_COST_TOTAL_KEYS,
    coerce_storage_cost_totals,
    totals_series_to_storage_dict,
)
from mar_dss.app.components.hydro_tab import normalize_stratigraphy_recharge_target
from mar_dss.rules.geohydro_rules import (
    DEFAULT_AQUITARD_K_MAX_FT_DAY,
    infer_dashboard_aquifer_type,
)
from mar_dss.mar.forward_run import evaluate_and_store_decision_graph, forward_run
from mar_dss.base import DecisionGraph
import pandas as pd
import copy
import hashlib
import json
import time
import numpy as np

# Set up logging
logger = logging.getLogger(__name__)

# Constants
DEFAULT_BASE_COST = 1_000_000
COST_THRESHOLDS = {
    'EXCELLENT': 1_000_000,  # < $1M
    'GOOD': 2_000_000,       # < $2M
    'MODERATE': 3_000_000,   # < $3M
    'POOR': 4_000_000        # < $4M
}
COST_SCORE_MAPPING = {
    'EXCELLENT': 100,
    'GOOD': 80,
    'MODERATE': 60,
    'POOR': 40,
    'VERY_POOR': 20
}
COST_RANGE_MULTIPLIER = {'low': 0.8, 'high': 1.2}

# Conversion factors
ACRES_TO_FT2 = 43560
MILES_TO_FEET = 5280

# Feasibility score weights
FEASIBILITY_WEIGHTS = {
    "physical": 0.25,
    "environmental": 0.20,
    "legal": 0.20,
    "cost": 0.15,
    "technical": 0.10,
    "social": 0.10
}

# Default feasibility scores by technology
DEFAULT_PHYSICAL_SCORES = {
    "spreading_basins": 75,
    "injection_wells": 80,
    "dry_wells": 70
}

DEFAULT_COST_SCORES = {
    "spreading_basins": 70,
    "injection_wells": 50,
    "dry_wells": 80
}

DEFAULT_TECHNICAL_SCORES = {
    "spreading_basins": 80,
    "injection_wells": 60,
    "dry_wells": 75
}

DEFAULT_SOCIAL_SCORE = 80

# Technology name mapping
TECHNOLOGY_NAMES = {
    "spreading_basins": "Spreading Basins",
    "injection_wells": "Injection Wells",
    "dry_wells": "Dry Wells",
}

# Mapping from DSS option names to UI technology identifiers
DSS_TO_UI_MAPPING = {
    "Surface Recharge": "spreading_basins",
    "Dry Well": "dry_wells",
    "Injection Well": "injection_wells",
}

# Reverse mapping from UI technology identifiers to DSS option names
UI_TO_DSS_MAPPING = {v: k for k, v in DSS_TO_UI_MAPPING.items()}
# Import all the analysis components
try:
    from mar_dss.app.components.dss_algorithm_tab import create_dss_algorithm_content
    from mar_dss.app.components.decision_sensitivity_tab import create_decision_sensitivity_content
    from mar_dss.app.components.decision_interpretation_tab import create_decision_interpretation_content
    from mar_dss.app.components.ai_generated_decision_tab import create_ai_generated_decision_content
    from mar_dss.app.components.data_export_tab import create_data_export_content
except ImportError:
    from ..components.dss_algorithm_tab import create_dss_algorithm_content
    from ..components.decision_sensitivity_tab import create_decision_sensitivity_content
    from ..components.decision_interpretation_tab import create_decision_interpretation_content
    from ..components.ai_generated_decision_tab import create_ai_generated_decision_content
    from ..components.data_export_tab import create_data_export_content

def read_knowledge():
    """Test function to read knowledge files and create graph."""
    # Get the path to the knowledge directory relative to the mar_dss package
    # Find the mar_dss package root
    
    mar_dss_path = Path(mar_dss.__file__).parent
    knowledge_dir = mar_dss_path / "knowledge"
    
    input_fn = knowledge_dir / "input.yaml"
    rules_fn = knowledge_dir / "rules.yaml"
    
    # Check if files exist
    if not input_fn.exists():
        raise FileNotFoundError(f"Knowledge file not found: {input_fn}")
    if not rules_fn.exists():
        raise FileNotFoundError(f"Knowledge file not found: {rules_fn}")
    
    graph = DecisionGraph()
    graph.from_yamls(
        [str(input_fn.resolve()), str(rules_fn.resolve())]
    )
    return graph

def get_session_graph():
    """Get or create the knowledge graph for this session."""
    graph = dash_storage.get_data("decision_graph")
    if graph is None:
        graph = read_knowledge()
        
    return graph

def get_dss_status_for_technology(ui_tech_id):
    """Get DSS status for a technology given its UI identifier.
    
    Args:
        ui_tech_id: UI technology identifier (e.g., "spreading_basins")
    
    Returns:
        str: DSS status ("Rejected", "Conditionally Recommended", "Recommended", "Recommended with Warnings")
             or None if not found
    """
    dss_results = dash_storage.get_data("dss_results")
    if dss_results is None or not hasattr(dss_results, 'results') or not dss_results.results:
        return None
    
    # Map UI identifier to DSS option name
    dss_option_name = UI_TO_DSS_MAPPING.get(ui_tech_id)
    if dss_option_name is None:
        return None
    
    # Get result from DSS
    result = dss_results.results.get(dss_option_name)
    if result is None:
        return None
    
    return result.get("status")

def get_graph_inputs():
    """Get the inputs for the graph with validation."""
    inputs = {}
    
    try:
        # Max infiltration area with validation
        max_infiltration_area_percent = dash_storage.get_data("max_infiltration_area")
        max_available_area = dash_storage.get_data("max_available_area")

        if max_available_area is None:
            max_available_area = 1e7
            max_infiltration_area = max_available_area
        else:
            try:
                max_infiltration_area = float(max_infiltration_area_percent) * float(max_available_area)
            except (ValueError, TypeError):
                logger.warning(
                    "Invalid max_infiltration_area: %s, using default",
                    max_infiltration_area_percent,
                )
                max_infiltration_area = float(max_available_area)
        
        max_infiltration_area_ft2 = max_infiltration_area * ACRES_TO_FT2
        if max_infiltration_area_ft2 <= 0:
            logger.warning("max_infiltration_area_ft2 <= 0, using default")
            max_infiltration_area_ft2 = 1e7
        inputs["max_available_area"] = max_infiltration_area_ft2
        
        # Ground surface slope with validation
        ground_surface_slope = dash_storage.get_data("ground_surface_slope")
        try:
            inputs["ground_surface_slope"] = float(ground_surface_slope) if ground_surface_slope is not None else 0.0
        except (ValueError, TypeError):
            logger.warning(f"Invalid ground_surface_slope: {ground_surface_slope}, using 0.0")
            inputs["ground_surface_slope"] = 0.0
        
        # Stratigraphy data with validation (includes recharge target layer flag per row)
        start_table = dash_storage.get_data("stratigraphy_data")
        if start_table is None or len(start_table) == 0:
            raise ValueError("stratigraphy_data is missing or empty")

        if isinstance(start_table, list):
            normalize_stratigraphy_recharge_target(start_table)

        start_df = pd.DataFrame(start_table)
        required_columns = ['thickness', 'conductivity', 'yield']
        missing_columns = [col for col in required_columns if col not in start_df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns in stratigraphy_data: {missing_columns}")

        inputs["stratigraphy_table"] = [
            [
                row['thickness'],
                row['conductivity'],
                row['yield'],
                bool(row.get('recharge_target', False)),
            ]
            for row in start_df.to_dict('records')
        ]
        
        # Groundwater data with validation
        gw_data_raw = dash_storage.get_data("groundwater_data")
        if gw_data_raw is None or len(gw_data_raw) == 0:
            raise ValueError("groundwater_data is missing or empty")
        
        gw_data = pd.DataFrame(gw_data_raw)
        if 'elevation' not in gw_data.columns:
            raise ValueError("Missing 'elevation' column in groundwater_data")
        
        gs_elevation = dash_storage.get_data("ground_surface_elevation")
        if gs_elevation is None:
            raise ValueError("ground_surface_elevation is missing")
        
        try:
            gs_elevation = float(gs_elevation)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid ground_surface_elevation: {gs_elevation}")
        
        depth_to_gw = gs_elevation - gw_data['elevation'].values
        inputs["monthly_gw_depth"] = depth_to_gw

        aq_k = DEFAULT_AQUITARD_K_MAX_FT_DAY
        aq_k_raw = dash_storage.get_data("aquitard_conductivity_ft_day")
        if aq_k_raw is not None:
            try:
                v = float(aq_k_raw)
                if np.isfinite(v) and v > 0.0:
                    aq_k = v
            except (TypeError, ValueError):
                pass

        aq_inferred = infer_dashboard_aquifer_type(
            start_table,
            gw_data_raw,
            gs_elevation,
            aquitard_k_max_ft_day=aq_k,
        )
        inputs["aq_type"] = aq_inferred
        dash_storage.set_data("aq_type", aq_inferred)
        
        # Source water volume
        source_water_volume = dash_storage.get_data("monthly_flow")
        inputs["source_water_volume"] = source_water_volume
        
        inputs["d_gw_min"] = 5.0
        
        return inputs
        
    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"Error getting graph inputs: {e}")
        raise ValueError(f"Invalid graph input data: {e}")

def create_inputs_hash(inputs):
    """Create a hash from the graph inputs for caching purposes."""
    # Convert inputs to a hashable format
    hashable_data = {}
    
    for key, value in inputs.items():
        if isinstance(value, (np.ndarray, np.generic)):
            # Convert numpy arrays to lists
            hashable_data[key] = value.tolist() if hasattr(value, 'tolist') else float(value)
        elif isinstance(value, (list, tuple)):
            # Ensure lists are hashable (convert nested arrays)
            hashable_data[key] = [
                [float(x) if isinstance(x, (np.generic, np.ndarray)) else x for x in row] 
                if isinstance(row, (list, tuple, np.ndarray)) 
                else (float(row) if isinstance(row, (np.generic, np.ndarray)) else row)
                for row in value
            ]
        elif isinstance(value, (int, float, str, bool, type(None))):
            hashable_data[key] = value
        else:
            # For other types, convert to string representation
            hashable_data[key] = str(value)
    
    # Create a JSON string from the hashable data (sorted for consistency)
    json_str = json.dumps(hashable_data, sort_keys=True, default=str)
    
    # Generate MD5 hash
    hash_obj = hashlib.md5(json_str.encode('utf-8'))
    return hash_obj.hexdigest()

def _calculate_cost_score_from_value(cost_value):
    """Calculate cost feasibility score from a cost value.
    
    Args:
        cost_value: Cost in dollars
    
    Returns:
        Score (0-100) where lower cost = higher score
    """
    if cost_value < COST_THRESHOLDS['EXCELLENT']:
        return COST_SCORE_MAPPING['EXCELLENT']
    elif cost_value < COST_THRESHOLDS['GOOD']:
        return COST_SCORE_MAPPING['GOOD']
    elif cost_value < COST_THRESHOLDS['MODERATE']:
        return COST_SCORE_MAPPING['MODERATE']
    elif cost_value < COST_THRESHOLDS['POOR']:
        return COST_SCORE_MAPPING['POOR']
    else:
        return COST_SCORE_MAPPING['VERY_POOR']


def calculate_physical_feasibility(selected_technology, graph, node_values, aq_type):
    """Calculate physical feasibility score based on hydrogeological conditions."""
    if graph is None:
        return DEFAULT_PHYSICAL_SCORES.get(selected_technology, 50)
    
    aq_type = str(aq_type).lower() if aq_type else ''
    
    if selected_technology == "spreading_basins":
        if aq_type == "unconfined":
            surface_recharge = node_values.get('surface_recharge_suitability', False)
            return 100 if surface_recharge else 60
        else:
            return 0  # Infeasible for confined
    elif selected_technology == "injection_wells":
        if aq_type == "confined":
            confined_rechargability = node_values.get('confined_rechargability', 0)
            leakage = node_values.get('leakage_significance', 'high')
            if confined_rechargability >= 50 and leakage == "low":
                return 90
            elif confined_rechargability >= 50 or leakage == "low":
                return 70
            else:
                return 50
        else:
            return 75  # Works for unconfined
    elif selected_technology == "dry_wells":
        if aq_type == "unconfined":
            return 85
        else:
            return 0  # Infeasible for confined
    
    return DEFAULT_PHYSICAL_SCORES.get(selected_technology, 50)


def calculate_environmental_feasibility():
    """Calculate environmental feasibility score based on risk assessment."""
    env_inputs = [
        dash_storage.get_data("tss_turbidity_risk") or "LOW RISK",
        dash_storage.get_data("doc_toc_risk") or "LOW RISK",
        dash_storage.get_data("ph_alkalinity_risk") or "LOW RISK",
        dash_storage.get_data("tds_salinity_risk") or "LOW RISK",
        dash_storage.get_data("inorganic_contaminants_risk") or "LOW RISK",
        dash_storage.get_data("emerging_contaminants_risk") or "LOW RISK",
        dash_storage.get_data("redox_compatibility_risk") or "LOW RISK",
        dash_storage.get_data("pathogen_risk") or "LOW RISK",
    ]
    
    try:
        from mar_dss.app.components.environmental_impact_tab import DECISION_LOGIC
        env_score = 0
        input_keys = ["step1_tss", "step2a_doc", "step2b_ph", "step3_tds", 
                      "step4_inorganic", "step5a_ec", "step5b_redox", "step6_pathogens"]
        for key, value in zip(input_keys, env_inputs):
            if key in DECISION_LOGIC and value in DECISION_LOGIC[key]:
                score = DECISION_LOGIC[key][value].get("score", 0)
                env_score += score
        
        # Convert risk score (0-8+) to feasibility score (0-100)
        # Lower risk = higher feasibility
        if env_score >= 8:
            return 20  # Very high risk
        elif env_score >= 5:
            return 40  # High risk
        elif env_score >= 3:
            return 60  # Moderate risk
        elif env_score >= 1:
            return 80  # Low risk
        else:
            return 100  # No risk
    except Exception as e:
        logger.warning(f"Could not calculate environmental score: {e}")
        return 60  # Default moderate


def calculate_legal_feasibility():
    """Calculate legal feasibility score based on constraints assessment."""
    legal_fatal = dash_storage.get_data("legal_fatal_issues") or False
    legal_conditional = dash_storage.get_data("legal_conditional_issues") or 0
    
    if legal_fatal:
        return 0  # Not feasible
    elif legal_conditional > 2:
        return 50  # Conditionally feasible
    elif legal_conditional > 0:
        return 75  # Some conditions
    else:
        return 100  # Fully feasible


def calculate_cost_feasibility(selected_technology):
    """Calculate cost feasibility score based on capital costs."""
    raw = dash_storage.get_data("capital_cost_num")

    if raw is None:
        return DEFAULT_COST_SCORES.get(selected_technology, 50)

    try:
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return _calculate_cost_score_from_value(float(raw))

        capital_cost = coerce_storage_cost_totals(raw, CAPITAL_COST_TOTAL_KEYS)
        if capital_cost is None:
            return 50

        cost_column = _get_cost_column_name(selected_technology)
        if cost_column and cost_column in capital_cost.index:
            cost_value = float(capital_cost[cost_column])
            return _calculate_cost_score_from_value(cost_value)
        return 50
    except Exception as e:
        logger.warning(f"Could not calculate cost score: {e}")
        return 50  # Default


def calculate_technical_complexity(selected_technology):
    """Calculate technical complexity score."""
    return DEFAULT_TECHNICAL_SCORES.get(selected_technology, 50)


def calculate_social_acceptance(selected_technology):
    """Calculate social acceptance score (placeholder for future enhancement)."""
    # This could be based on stakeholder input if available
    return DEFAULT_SOCIAL_SCORE


def calculate_individual_feasibility_metrics(selected_technology, graph=None):
    """Calculate individual feasibility metrics (Physical, Environmental, Legal, Cost, Technical, Social).
    
    Returns a dictionary with scores (0-100) for each metric.
    """
    metrics = {
        "physical": 0,
        "environmental": 0,
        "legal": 0,
        "cost": 0,
        "technical": 0,
        "social": 0
    }
    
    if selected_technology is None:
        return metrics
    
    if graph is None:
        graph = dash_storage.get_data("decision_graph")
    
    try:
        # Ensure graph is evaluated
        node_values = {}
        aq_type = None
        if graph is not None:
            try:
                inputs = get_graph_inputs()
                evaluate_and_store_decision_graph(graph, inputs)
                node_values = graph.get_node_values()
                aq_type = dash_storage.get_data("aq_type")
                if aq_type is None:
                    aq_type = node_values.get('aq_type', '')
            except Exception as eval_error:
                logger.warning(f"Could not evaluate graph in calculate_individual_feasibility_metrics: {eval_error}")
        
        # Calculate each metric using dedicated functions
        metrics["physical"] = calculate_physical_feasibility(selected_technology, graph, node_values, aq_type)
        metrics["environmental"] = calculate_environmental_feasibility()
        metrics["legal"] = calculate_legal_feasibility()
        metrics["cost"] = calculate_cost_feasibility(selected_technology)
        metrics["technical"] = calculate_technical_complexity(selected_technology)
        metrics["social"] = calculate_social_acceptance(selected_technology)
        
        # Ensure all scores are between 0 and 100
        for key in metrics:
            metrics[key] = max(0, min(100, metrics[key]))
        
        return metrics
    except Exception as e:
        logger.error(f"Error calculating individual feasibility metrics: {e}", exc_info=True)
        return metrics

def calculate_feasibility_score(selected_technology, graph=None):
    """Calculate overall feasibility score based on selected technology and site conditions.
    Uses weighted average of individual metrics.
    """
    if selected_technology is None:
        return 0
    
    # Get individual metrics
    metrics = calculate_individual_feasibility_metrics(selected_technology, graph)
    
    # Weighted average using constants
    overall_score = sum(metrics[key] * FEASIBILITY_WEIGHTS[key] for key in FEASIBILITY_WEIGHTS)
    return round(overall_score)

def _get_cost_column_name(selected_technology):
    """Map selected technology to cost column name."""
    if selected_technology is None:
        return None
    
    # Map technology identifiers to cost column names
    tech_mapping = {
        "spreading_basins": "Spreading Pond Cost ($)",
        "Surface Recharge": "Spreading Pond Cost ($)",
        "injection_wells": "Injection Wells Cost ($)",
        "Injection Well": "Injection Wells Cost ($)",
        "dry_wells": "Dry Wells Cost ($)",
        "Dry Well": "Dry Wells Cost ($)",
    }
    
    return tech_mapping.get(selected_technology)


def _format_cost_value(cost_value):
    """Format a single cost value for display."""
    if cost_value is None or pd.isna(cost_value):
        return "$0"
    
    cost = float(cost_value)
    if cost >= 1000000:
        return f"${cost/1000000:.1f}M"
    elif cost >= 1000:
        return f"${cost/1000:.0f}K"
    else:
        return f"${cost:,.0f}"


def calculate_project_cost_range(selected_technology):
    """Calculate project cost range based on selected technology.
    
    Returns:
        - If technology is selected: Shows cost for that technology with ±20% range
        - If no technology selected: Shows all three costs (Spreading Pond, Injection Wells, Dry Wells)
    """
    try:
        # Get stored cost data if available
        raw_capital = dash_storage.get_data("capital_cost_num")
        capital_cost = (
            coerce_storage_cost_totals(raw_capital, CAPITAL_COST_TOTAL_KEYS)
            if raw_capital is not None
            else None
        )

        if raw_capital is not None:
            import pandas as pd
            if isinstance(raw_capital, (int, float)) and not isinstance(raw_capital, bool):
                low_cost = float(raw_capital) * COST_RANGE_MULTIPLIER["low"]
                high_cost = float(raw_capital) * COST_RANGE_MULTIPLIER["high"]
                low_str = _format_cost_value(low_cost)
                high_str = _format_cost_value(high_cost)
                return f"{low_str} - {high_str}"
            if capital_cost is not None and isinstance(capital_cost, pd.Series):
                # We have three cost values
                if selected_technology is None:
                    # Show all three values
                    spreading = _format_cost_value(capital_cost.get("Spreading Pond Cost ($)", 0))
                    injection = _format_cost_value(capital_cost.get("Injection Wells Cost ($)", 0))
                    dry_well = _format_cost_value(capital_cost.get("Dry Wells Cost ($)", 0))
                    return f"Spreading: {spreading} | Injection: {injection} | Dry Well: {dry_well}"
                else:
                    # Show selected technology cost with range
                    cost_column = _get_cost_column_name(selected_technology)
                    if cost_column and cost_column in capital_cost.index:
                        cost_value = capital_cost[cost_column]
                        low_cost = float(cost_value) * COST_RANGE_MULTIPLIER['low']
                        high_cost = float(cost_value) * COST_RANGE_MULTIPLIER['high']
                        low_str = _format_cost_value(low_cost)
                        high_str = _format_cost_value(high_cost)
                        return f"{low_str} - {high_str}"
                    else:
                        # Fallback: show all three
                        spreading = _format_cost_value(capital_cost.get("Spreading Pond Cost ($)", 0))
                        injection = _format_cost_value(capital_cost.get("Injection Wells Cost ($)", 0))
                        dry_well = _format_cost_value(capital_cost.get("Dry Wells Cost ($)", 0))
                        return f"Spreading: {spreading} | Injection: {injection} | Dry Well: {dry_well}"
            else:
                try:
                    low_cost = float(raw_capital) * COST_RANGE_MULTIPLIER["low"]
                    high_cost = float(raw_capital) * COST_RANGE_MULTIPLIER["high"]
                    low_str = _format_cost_value(low_cost)
                    high_str = _format_cost_value(high_cost)
                    return f"{low_str} - {high_str}"
                except (TypeError, ValueError):
                    pass
        
        # Default cost ranges by technology type (if no calculation available)
        default_costs = {
            "spreading_basins": (1.5, 3.0),
            "injection_wells": (2.5, 4.5),
            "dry_wells": (1.0, 2.5),
        }
        
        if selected_technology is None:
            return "Spreading: $1.5M - $3.0M | Injection: $2.5M - $4.5M | Dry Well: $1.0M - $2.5M"
        
        cost_range = default_costs.get(selected_technology, (2.0, 4.0))
        return f"${cost_range[0]:.1f}M - ${cost_range[1]:.1f}M"
        
    except Exception as e:
        logger.error(f"Error calculating project cost: {e}", exc_info=True)
        return "$0 - $0"

def create_and_run_cost_calculator():
    """
    Create and run cost calculator with inputs from data storage.
    
    Returns:
        CostCalculator instance with calculated costs
    """
    try:
        from mar_dss.app.callbacks.cost_calculator import CostCalculator
    except ImportError:
        from .cost_calculator import CostCalculator
    
    # Get inputs from data storage
    aquifer_type = dash_storage.get_data("aq_type")
    total_runoff_ft3 = dash_storage.get_data("total_runoff_ft3") or 0.0
    fraction_flow_capture = dash_storage.get_data("fraction_flow_capture") or 0.0
    runoff_volume_ft3 = float(total_runoff_ft3) * float(fraction_flow_capture)
    distance_to_sediment_miles = dash_storage.get_data("distance_to_sediment") or 1.0
    distance_to_sediment_ft = float(distance_to_sediment_miles) * MILES_TO_FEET
    distance_to_storage_pond_ft = float(dash_storage.get_data("distance_to_storage_pond_ft")) or 1.0
    sediment_target = dash_storage.get_data("sediment_target")
    sediment_target_display = "Medium Silt" if sediment_target == "medium_silt" else "Fine Silt"
    graph = dash_storage.get_data("decision_graph")
    if graph is None:
        raise ValueError("decision_graph is missing; run graph evaluation before cost calculation")

    from mar_dss.rules.defaults import get_default

    number_of_injection_wells_results = graph.get_node_value("number_of_injection_wells")
    # compute_number_of_injection_wells returns None when neither confined nor unconfined is true
    if not isinstance(number_of_injection_wells_results, dict):
        q_def = float(get_default("max_injection_Q_per_well"))
        logger.warning(
            "number_of_injection_wells not available from graph (confined/unconfined may be unset); "
            "using placeholder values for cost calculator"
        )
        number_of_injection_wells_results = {
            "number_of_wells": 5,
            "Q_per_well": q_def,
        }

    number_of_injection_wells = int(
        float(number_of_injection_wells_results.get("number_of_wells", 5))
    )
    injection_Q_ft3_per_day = float(
        number_of_injection_wells_results.get(
            "Q_per_well", get_default("max_injection_Q_per_well")
        )
    )

    dry_well_results = graph.get_node_value("number_of_dry_wells")
    if not isinstance(dry_well_results, dict):
        logger.warning(
            "number_of_dry_wells not available from graph; using zeros for cost calculator"
        )
        dry_well_results = {"number_of_dry_wells": 0, "Q_per_dry_well": 0.0}
    if aquifer_type.lower() == "confined":
        recharge_method = "injection_well"
    else:
        recharge_method = "dry_well"
    
    # Convert ft³/day to gpm (gallons per minute)
    # 1 ft³ = 7.48052 gallons, 1 day = 1440 minutes
    # gpm = (ft³/day) × (7.48052 gallons/ft³) / (1440 minutes/day)
    injection_Q_gpm = injection_Q_ft3_per_day * 7.48052 / 1440
    
    storm_design_depth = 1.8
    cost_calculator = CostCalculator(
        water_source="stormwater",
        storm_design_depth=storm_design_depth,
        drainage_basin_area_acres=35,  # TODO: should be renamed to MAR site area
        total_storm_volume_af=6.52,  # TODO: not used, remove if not needed
        basin_soil_type_infiltration_rate_in_per_hr=0.2,
        total_runoff_volume_ft3=runoff_volume_ft3,
        fine_sediment_removal_goal=sediment_target_display,
        distance_collection_to_sediment_pond_ft=distance_to_sediment_ft,
        distance_sediment_to_storage_pond_ft=distance_to_storage_pond_ft,
        dry_well_infiltration_rate_in_per_hr=5,
        dry_well_transfer_rate_gpm=50,
        injection_well_transfer_rate_gpm=injection_Q_gpm,
        number_of_injection_wells=number_of_injection_wells,
        collection_to_sediment_removal__conveyance_method="trapezoidal",
        dry_well_diameter_ft=6,
        recharge_method="dry_well", 
        number_of_dry_wells=int(float(dry_well_results.get("number_of_dry_wells", 0))),
        dry_well_Q_ft3_per_day=float(dry_well_results.get("Q_per_dry_well", 0.0)),
    )
    
    # Run cost calculation
    cost_calculator.calculate_cost()
    
    return cost_calculator


def extract_capital_costs(cost_calculator):
    """
    Extract capital costs from cost calculator.
    
    Args:
        cost_calculator: CostCalculator instance with calculated costs
    
    Returns:
        pandas Series with capital costs for each technology
    """
    cols = ['Spreading Pond Cost ($)', 'Injection Wells Cost ($)', 'Dry Wells Cost ($)']
    capital_cost_num = cost_calculator.capital_costs_calculations.loc['Capital Total Cost', cols]
    return capital_cost_num


def map_costs_to_options(capital_costs_series, maintenance_costs_series=None):
    """
    Map cost calculator column names to MAR option names.
    
    Args:
        capital_costs_series: pandas Series with capital cost calculator column names as index
        maintenance_costs_series: Optional pandas Series with maintenance cost calculator column names as index
    
    Returns:
        Dictionary mapping option names to cost values (capital and maintenance)
        Format: {
            "Surface Recharge": {"capital": 1500000, "maintenance": 50000},
            "Dry Well": {"capital": 2000000, "maintenance": 60000},
            "Injection Well": {"capital": 1800000, "maintenance": 55000}
        }
        Or if maintenance_costs_series is None:
        Format: {"Surface Recharge": 1500000, "Dry Well": 2000000, "Injection Well": 1800000}
    """
    # Map capital costs
    capital_mapping = {
        "Surface Recharge": capital_costs_series.get("Spreading Pond Cost ($)", 1000000),
        "Dry Well": capital_costs_series.get("Dry Wells Cost ($)", 1000000),
        "Injection Well": capital_costs_series.get("Injection Wells Cost ($)", 1000000)
    }
    
    # Convert to float and handle NaN values for capital costs
    for key, value in capital_mapping.items():
        try:
            capital_mapping[key] = float(value) if pd.notna(value) else 1000000.0
        except (ValueError, TypeError):
            capital_mapping[key] = 1000000.0
    
    # If maintenance costs are provided, include them
    if maintenance_costs_series is not None:
        maintenance_mapping = {
            "Surface Recharge": maintenance_costs_series.get("Spreading Pond Maintenance Cost ($)", 0),
            "Dry Well": maintenance_costs_series.get("Dry Wells Maintenance Cost ($)", 0),
            "Injection Well": maintenance_costs_series.get("Injection Wells Maintenance Cost ($)", 0)
        }
        
        # Convert to float and handle NaN values for maintenance costs
        for key, value in maintenance_mapping.items():
            try:
                maintenance_mapping[key] = float(value) if pd.notna(value) else 0.0
            except (ValueError, TypeError):
                maintenance_mapping[key] = 0.0
        
        # Combine into nested dictionary
        cost_mapping = {
            option: {
                "capital": capital_mapping[option],
                "maintenance": maintenance_mapping[option]
            }
            for option in capital_mapping.keys()
        }
    else:
        # Return flat dictionary with just capital costs (backward compatible)
        cost_mapping = capital_mapping
    
    return cost_mapping


def run_integrated_analysis():
    """
    Main entry point: Run cost calculation and DSS together.

    Pipeline (unified around :func:`mar_dss.mar.forward_run.forward_run`):
    1. Build graph inputs and evaluate the knowledge graph (required for cost + constraints)
    2. Run cost calculation (uses evaluated node values, e.g. well counts)
    3. Map costs to MAR options and run forward DSS with optional cost override
    4. Store DSS results

    Returns:
        tuple: (dss_results, cost_calculator)
    """
    logger.info("Running integrated analysis (cost + DSS)...")

    inputs = get_graph_inputs()
    graph = get_session_graph()
    evaluate_and_store_decision_graph(graph, inputs)

    # Step 1: Run cost calculation (requires evaluated decision_graph in storage)
    try:
        cost_calculator = create_and_run_cost_calculator()
        logger.info("Cost calculation completed successfully")
    except Exception as e:
        logger.error(f"Error in cost calculation: {e}", exc_info=True)
        # Continue with default costs if cost calculation fails
        cost_calculator = None
        cost_mapping = None
    else:
        # Step 2: Extract capital costs
        capital_costs = extract_capital_costs(cost_calculator)
        
        # Extract maintenance costs
        cols = ['Spreading Pond Maintenance Cost ($)', 'Injection Wells Maintenance Cost ($)', 'Dry Wells Maintenance Cost ($)']
        maintenance_cost_num = cost_calculator.maintenance_costs_calculations.loc['Annual Grand Maintenance Cost', cols]
        
        # Step 3: Map costs to option names (including maintenance costs)
        cost_mapping = map_costs_to_options(capital_costs, maintenance_cost_num)
        logger.debug(f"Cost mapping: {cost_mapping}")
        
        # Store cost data in dash_storage for UI display (dict keys = calculator columns)
        dash_storage.set_data(
            "capital_cost_num",
            totals_series_to_storage_dict(capital_costs, CAPITAL_COST_TOTAL_KEYS),
        )
        dash_storage.set_data(
            "maintenance_cost_num",
            totals_series_to_storage_dict(maintenance_cost_num, MAINTENANCE_COST_TOTAL_KEYS),
        )
        
        # Store NPV
        cols = ['Spreading Pond Net Present Value ($)', 'Injection Wells Net Present Value ($)', 'Dry Wells Net Present Value ($)']
        net_val = cost_calculator.net_present_value_calculations[cols].values[-1]
        net_val_dict = {}
        for i, col in enumerate(cols):
            net_val_dict[col] = net_val[i]
        dash_storage.set_data("net_val", net_val_dict)
        
        # Store cost calculator DataFrames for table display (without recalculating)
        dash_storage.set_data("capital_costs_calculations_df", cost_calculator.capital_costs_calculations)
        dash_storage.set_data("maintenance_costs_calculations_df", cost_calculator.maintenance_costs_calculations)
        dash_storage.set_data("npv_calculations_df", cost_calculator.net_present_value_calculations)
        
        # Store full cost mapping (with capital and maintenance costs)
        dash_storage.set_data("cost_mapping", cost_mapping)
    
    # Step 4: Run DSS evaluation with cost override
    try:
        # Extract capital costs for forward_run (it expects flat dict with capital costs)
        if cost_mapping is not None and isinstance(cost_mapping, dict) and len(cost_mapping) > 0:
            first_value = list(cost_mapping.values())[0]
            if isinstance(first_value, dict):
                # Nested structure - extract capital costs
                capital_cost_override = {
                    option: costs["capital"]
                    for option, costs in cost_mapping.items()
                }
            else:
                # Flat structure (backward compatible)
                capital_cost_override = cost_mapping
        else:
            capital_cost_override = None

        dss_results = forward_run(cost_override=capital_cost_override)
        logger.info("DSS evaluation completed successfully")
    except Exception as e:
        logger.error(f"Error in DSS evaluation with cost override: {e}", exc_info=True)
        try:
            dss_results = forward_run()
            logger.info("DSS evaluation completed without cost override")
        except Exception as fallback_error:
            logger.error(f"Error in DSS evaluation: {fallback_error}", exc_info=True)
            raise RuntimeError(f"DSS evaluation failed: {fallback_error}") from fallback_error

    # Step 5: Store DSS results
    dash_storage.set_data("dss_results", dss_results)

    return dss_results, cost_calculator


def _format_analysis_error(exc):
    """Turn analysis exceptions into a user-facing message with guidance."""
    msg = str(exc).strip()
    if not msg:
        msg = "Analysis could not be completed."

    guidance = [
        ("stratigraphy_data", "Add stratigraphy layers on the Hydrogeology tab."),
        ("groundwater_data", "Add groundwater data on the Hydrogeology tab."),
        ("ground_surface_elevation", "Set ground surface elevation on the Hydrogeology tab."),
        ("decision_graph", "The decision knowledge graph could not be loaded."),
        ("DSS evaluation failed", "Check that required inputs are entered across Overview, Water Source, Hydrogeology, Engineering, and Regulations tabs."),
    ]
    extra = next((hint for key, hint in guidance if key in msg), None)
    if extra and extra not in msg:
        return f"{msg} {extra}"
    return msg


def run_feasibility_analysis():
    """Run the full feasibility pipeline (graph evaluation, costs, DSS).

    Returns None on success, or an error message string on failure.
    """
    try:
        inputs = get_graph_inputs()
        current_hash = create_inputs_hash(inputs)

        logger.info(f"Feasibility analysis running (inputs hash: {current_hash[:8]}...)")
        dash_storage.set_data("feasibility_analysis_hash", current_hash)

        run_integrated_analysis()
        dash_storage.set_data("analysis_last_error", None)
        return None
    except Exception as exc:
        error_message = _format_analysis_error(exc)
        dash_storage.set_data("analysis_last_error", error_message)
        logger.error("Feasibility analysis failed: %s", error_message, exc_info=True)
        return error_message


def _analysis_loading_banner():
    """Banner shown while integrated analysis is running."""
    return dbc.Alert(
        [
            dbc.Spinner(
                size="sm",
                color="primary",
                type="border",
                spinner_class_name="me-2",
            ),
            html.Strong("Analysis in progress."),
            html.Span(
                " Please wait while feasibility and cost results are calculated.",
                className="ms-1",
            ),
        ],
        color="info",
        className="py-2 mb-0 d-flex align-items-center",
    )


def _analysis_error_banner(message):
    """Banner shown when integrated analysis fails."""
    return dbc.Alert(
        [
            html.I(className="fas fa-exclamation-triangle me-2"),
            html.Strong("Analysis could not be completed. "),
            html.Span(message),
        ],
        color="danger",
        className="py-2 mb-0",
    )


def setup_analysis_callbacks(app):
    """Set up callbacks for lazy loading analysis tab content."""

    @app.callback(
        Output("analysis-run-status-row", "children"),
        [
            Input("top-tabs", "active_tab"),
            Input("analysis-rerun-count", "data"),
            Input("analysis-tabs", "active_tab"),
        ],
        prevent_initial_call=True,
    )
    def show_analysis_loading_banner(active_tab, rerun_count, analysis_sub_tab):
        """Show a status banner as soon as analysis is triggered."""
        if active_tab != "analysis":
            return []
        return _analysis_loading_banner()

    @app.callback(
        [
            Output("knowledge-graph-store", "data"),
            Output("analysis-run-status-row", "children", allow_duplicate=True),
        ],
        [
            Input("top-tabs", "active_tab"),
            Input("analysis-rerun-count", "data"),
            Input("analysis-tabs", "active_tab"),
        ],
        [State("stratigraphy-data-store", "data")],
        prevent_initial_call="initial_duplicate",
    )
    def on_analysis_top_tab(active_tab, rerun_count, analysis_sub_tab, strat_store):
        """Re-run the integrated pipeline when Analysis is shown, re-clicked, or sub-tab changes.

        ``active_tab`` (top) does not change when the user clicks (7) Analysis again;
        ``analysis-rerun-count`` (clientside) covers that. ``analysis-tabs`` covers
        switching among Feasibilities, Cost, DSS Algorithm, etc., while staying on
        the Analysis top tab.
        """
        if active_tab != "analysis":
            return dash.no_update, dash.no_update

        if strat_store is not None and isinstance(strat_store, list) and len(strat_store) > 0:
            rows = copy.deepcopy(strat_store)
            normalize_stratigraphy_recharge_target(rows)
            dash_storage.set_data("stratigraphy_data", rows)

        if dash_storage.get_data("decision_graph") is None:
            graph = read_knowledge()
            dash_storage.set_data("decision_graph", graph)
            logger.debug("Knowledge graph initialized from YAML")

        logger.debug(
            "Running feasibility analysis (top=analysis sub=%s rerun_count=%s)",
            analysis_sub_tab,
            rerun_count,
        )
        error_message = run_feasibility_analysis()
        if error_message:
            logger.debug("Feasibility analysis failed: %s", error_message)
            return {
                "initialized": False,
                "graph_ready": False,
                "error": error_message,
            }, _analysis_error_banner(error_message)

        logger.debug("Feasibility analysis completed - results available for Feasibilities tab")

        return {
            "initialized": True,
            "graph_ready": True,
            "last_analysis_at": time.time(),
        }, []

    
    # DISABLED: Callback removed because Feasibility Summary tab was removed
    # This callback populated technology cards in the removed tab
    # @app.callback(
    #     [Output("feasible-technologies-container", "children"),
    #      Output("conditionally-feasible-technologies-container", "children"),
    #      Output("infeasible-technologies-container", "children")],
    #     [Input("top-tabs", "active_tab"),
    #      Input("analysis-tabs", "active_tab"),
    #      Input("knowledge-graph-store", "data")],
    #     prevent_initial_call=False
    # )
    # def populate_technology_cards(top_tab, analysis_tab, graph_store):
    #     """Populate feasible, conditionally feasible, and infeasible technology cards based on DSS results."""
    #     # Function body commented out - tab was removed
    #     pass
    
    # DISABLED: Callback removed because Feasibility Summary tab was removed
    # @app.callback(
    #     [Output("technology-selection-feedback", "children"),
    #      Output("feasible-technologies", "value", allow_duplicate=True),
    #      Output("conditionally-feasible-technologies", "value", allow_duplicate=True),
    #      Output("overall-feasibility-score", "children", allow_duplicate=True),
    #      Output("total-project-cost", "children", allow_duplicate=True)],
    #     [Input("feasible-technologies", "value"),
    #      Input("conditionally-feasible-technologies", "value")],
    #      prevent_initial_call=True
    # )
    # def handle_technology_selection(feasible_tech, conditionally_feasible_tech):
    #     """Handle technology selection from both Feasible and Conditionally Feasible lists."""
    #     # Function body commented out - tab was removed
    #     pass
    
    # DISABLED: Callback removed because Feasibility Summary tab was removed
    # @app.callback(
    #     [Output("overall-feasibility-score", "children", allow_duplicate=True),
    #      Output("total-project-cost", "children", allow_duplicate=True)],
    #     [Input("top-tabs", "active_tab"),
    #      Input("analysis-tabs", "active_tab"),
    #      Input("knowledge-graph-store", "data")],
    #     prevent_initial_call='initial_duplicate'
    # )
    # def update_feasibility_metrics(top_tab, analysis_tab, graph_store):
    #     """Update feasibility score and cost when analysis runs or dashboard is accessed."""
    #     # Function body commented out - tab was removed
    #     pass
    
    # DISABLED: Callback removed because Feasibility Summary tab was removed
    # @app.callback(
    #     [
    #         Output("feasibility-metric-physical", "value"),
    #         Output("feasibility-metric-physical", "color"),
    #         Output("feasibility-metric-environmental", "value"),
    #         Output("feasibility-metric-environmental", "color"),
    #         Output("feasibility-metric-legal", "value"),
    #         Output("feasibility-metric-legal", "color"),
    #         Output("feasibility-metric-cost", "value"),
    #         Output("feasibility-metric-cost", "color"),
    #         Output("feasibility-metric-technical", "value"),
    #         Output("feasibility-metric-technical", "color"),
    #         Output("feasibility-metric-social", "value"),
    #         Output("feasibility-metric-social", "color"),
    #         Output("feasibility-metrics-overall-score", "children"),
    #         Output("feasibility-metrics-summary-text", "children"),
    #     ],
    #     [
    #         Input("top-tabs", "active_tab"),
    #         Input("analysis-tabs", "active_tab"),
    #         Input("technology-analysis-tabs", "active_tab"),
    #         Input("feasible-technologies-container", "children"),
    #         Input("conditionally-feasible-technologies-container", "children"),
    #         Input("knowledge-graph-store", "data"),
    #     ],
    #     prevent_initial_call=False
    # )
    # def update_individual_feasibility_metrics(top_tab, analysis_tab, tech_analysis_tab, feasible_container, conditionally_feasible_container, graph_store):
    #     """Update individual feasibility metrics when technology is selected or tab is accessed."""
    #     # Function body commented out - tab was removed
    #     pass
    
    @app.callback(
        Output("analysis-dss-algorithm-content", "children"),
        [Input("analysis-tabs", "active_tab")],
        prevent_initial_call=True
    )
    def load_dss_algorithm_content(active_tab):
        if active_tab == "analysis-dss-algorithm":
            return create_dss_algorithm_content()
        return "Loading..."
    
    @app.callback(
        Output("analysis-decision-sensitivity-content", "children"),
        [Input("analysis-tabs", "active_tab")],
        prevent_initial_call=True
    )
    def load_decision_sensitivity_content(active_tab):
        if active_tab == "analysis-decision-sensitivity":
            return create_decision_sensitivity_content()
        return "Loading..."
    
    @app.callback(
        Output("analysis-decision-interpretation-content", "children"),
        [
            Input("analysis-tabs", "active_tab"),
            Input("knowledge-graph-store", "data"),
        ],
        prevent_initial_call=True
    )
    def load_decision_interpretation_content(active_tab, graph_store):
        """Load decision interpretation content when tab is accessed or analysis runs."""
        if active_tab == "analysis-decision-interpretation":
            return create_decision_interpretation_content()
        return "Loading..."
    
    @app.callback(
        Output("decision-interpretation-details", "children"),
        [
            Input("decision-interpretation-option-selector", "value"),
            Input("analysis-tabs", "active_tab"),
            Input("knowledge-graph-store", "data"),
        ],
        prevent_initial_call=False
    )
    def update_option_interpretation(selected_option, active_tab, graph_store):
        """Update detailed interpretation when an option is selected."""
        from mar_dss.app.components.decision_interpretation_tab import _create_option_interpretation
        
        # Only update if we're on the decision interpretation tab
        if active_tab != "analysis-decision-interpretation":
            return dash.no_update
        
        if selected_option is None:
            return html.Div(
                dbc.Alert(
                    "Please select an option from the dropdown above to view detailed interpretation.",
                    color="info",
                )
            )
        
        # Get DSS results from storage
        dss_results = dash_storage.get_data("dss_results")
        
        if dss_results is None or not hasattr(dss_results, 'results') or not dss_results.results:
            return html.Div(
                dbc.Alert(
                    "No evaluation results available. Please run the feasibility analysis first.",
                    color="warning",
                )
            )
        
        results = dss_results.results
        filters = getattr(dss_results, 'filters', {})
        
        if selected_option not in results:
            return html.Div(
                dbc.Alert(
                    f"Option '{selected_option}' not found in results.",
                    color="danger",
                )
            )
        
        result = results[selected_option]
        return _create_option_interpretation(selected_option, result, filters)

    @app.callback(
        Output("decision-interpretation-workbook-text", "children"),
        [
            Input("decision-interpretation-subtabs", "active_tab"),
            Input("knowledge-graph-store", "data"),
            Input("analysis-tabs", "active_tab"),
        ],
        prevent_initial_call=False,
    )
    def refresh_decision_workbook_text(active_subtab, graph_store, analysis_tab):
        """Fill the Detailed calculations workbook when the user opens that sub-tab."""
        if analysis_tab != "analysis-decision-interpretation":
            return dash.no_update
        if active_subtab != "decision-interpretation-workbook":
            return dash.no_update
        from mar_dss.graph_computation_log import format_computation_log_entries

        text = dash_storage.get_data("graph_computation_log_text")
        if text is not None:
            return text
        raw = dash_storage.get_data("graph_computation_log")
        return format_computation_log_entries(raw)

    @app.callback(
        Output("analysis-ai-decision-content", "children"),
        [Input("analysis-tabs", "active_tab")],
        prevent_initial_call=True
    )
    def load_ai_decision_content(active_tab):
        if active_tab == "analysis-ai-decision":
            return create_ai_generated_decision_content()
        return "Loading..."
    
    @app.callback(
        Output("analysis-data-export-content", "children"),
        [Input("analysis-tabs", "active_tab")],
        prevent_initial_call=True
    )
    def load_data_export_content(active_tab):
        if active_tab == "analysis-data-export":
            return create_data_export_content()
        return "Loading..."
