import logging
from typing import Any, Dict, Mapping, Optional, TYPE_CHECKING

import mar_dss.app.utils.data_storage as data_storage
from mar_dss.mar import hard_constraints as hc_module
from mar_dss.mar import soft_constraints as sc_module
from mar_dss.mar import benefits as benefits_module
from mar_dss.mar.dss import DecisionSupportSystem
from mar_dss.mar.options import mar_options

if TYPE_CHECKING:
    from mar_dss.base import DecisionGraph

logger = logging.getLogger(__name__)


def evaluate_and_store_decision_graph(graph: "DecisionGraph", inputs: Mapping[str, Any]) -> None:
    """
    Evaluate the YAML knowledge graph with site inputs and persist it for MAR DSS.

    Hard/soft constraints and benefits read ``decision_graph`` from app storage; this
    must run before ``forward_run`` and before cost calculations that use graph outputs.
    """
    if graph is None:
        raise ValueError("decision_graph is required")
    graph.evaluate(dict(inputs), trace=True)
    data_storage.set_data("decision_graph", graph)
    from mar_dss.graph_computation_log import format_computation_log_entries

    data_storage.set_data("graph_computation_log", graph.computation_log)
    data_storage.set_data(
        "graph_computation_log_text",
        format_computation_log_entries(graph.computation_log),
    )


def forward_run(cost_override: Optional[Dict[str, float]] = None):
    """
    Run DSS evaluation for all MAR options (after the knowledge graph is evaluated).

    Constraint modules read the evaluated graph from ``data_storage`` (``decision_graph``).
    For a full run from site inputs, use :func:`run_forward_analysis` instead.

    Args:
        cost_override: Optional dictionary mapping option names to cost values.
                      If provided, overrides the base_cost for each option.
                      Format: {"Surface Recharge": 1500000, "Dry Well": 2000000, ...}

    Returns:
        DssResult object with results and filters
    """
    mar_options_list = mar_options()

    # Apply cost override if provided
    if cost_override:
        for option in mar_options_list:
            if option.name in cost_override:
                option.base_cost = float(cost_override[option.name])
                logger.info(
                    "Updated %s base_cost to $%.0f",
                    option.name,
                    option.base_cost,
                )

    class DssResult:
        pass

    results = {}
    filters = {}
    scores = {}
    for option in mar_options_list:
        hc_list = hc_module.hard_constraints(option)
        sc_list = sc_module.soft_constraints(option)
        benefits_list = benefits_module.benefits(option)

        dss_instance = DecisionSupportSystem(hc_list, sc_list, benefits_list)
        results[option.name] = dss_instance.evaluate(option)
        filters[option.name] = {"hard": hc_list, "soft": sc_list, "benefits": benefits_list}
        scores[option.name] = dss_instance.calculate_type_scores()
    dss_result = DssResult()
    dss_result.results = results
    dss_result.filters = filters
    dss_result.scores = scores
    return dss_result


def run_forward_analysis(
    graph: "DecisionGraph",
    inputs: Mapping[str, Any],
    cost_override: Optional[Dict[str, float]] = None,
):
    """
    Main MAR DSS analysis entry: evaluate the knowledge graph, then score all options.

    This is the single orchestrated path for option-level DSS (used by integrated
    analysis after costs are computed, or alone when defaults are acceptable).
    """
    evaluate_and_store_decision_graph(graph, inputs)
    return forward_run(cost_override=cost_override)
