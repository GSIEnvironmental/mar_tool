"""AI-assisted engineering option scoring for MAR DSS."""

from __future__ import annotations

import json
import math
import textwrap
from typing import Any

import mar_dss.app.utils.data_storage as dash_storage
import pandas as pd
from mar_dss.app.callbacks.ai_environment import (
    _location_text,
    downloadable_html_deliverable_instructions,
)

ENGINEERING_OPTIONS = ("Surface Recharge", "Injection Well", "Dry Well")

# Keys included in AI context (no dollar amounts or unit prices).
_CONTEXT_KEYS = (
    "project_location",
    "project_name",
    "analysis_date",
    "mar_purpose",
    "land_use",
    "max_available_area",
    "ground_surface_slope",
    "ground_surface_elevation",
    "aq_type",
    "wq_source_contaminants",
    "wq_source_turbidity",
    "wq_vadose_impacted",
    "wq_aquifer_anthropogenic",
    "wq_aquifer_natural",
    "total_runoff_ft3",
    "design_events_per_month",
    "fraction_flow_capture",
    "distance_to_storage_pond_ft",
    "conveyance_method",
    "distance_to_sediment",
    "monthly_flow",
    "stratigraphy_data",
    "groundwater_data",
    "flow_capture_values",
    "analysis_last_error",
    "water_map_recharge_lat",
    "water_map_recharge_lon",
    "water_map_source_lat",
    "water_map_source_lon",
    "max_infiltration_area",
    "sediment_pond_values",
    "sediment_target",
    "sediment_removal_needed",
    "storage_needed",
    "pumped_storage_values",
    "storage_pond_values",
    "pumped_infiltration_values",
    "remove_sediment_removal_pond",
    "infiltration_method",
    "max_dry_well_depth_ft",
    "max_mar_storage_depth",
)

# Explicitly excluded — internal cost estimates must not influence the AI.
_EXCLUDED_STORAGE_KEYS = frozenset(
    {
        "capital_cost_num",
        "maintenance_cost_num",
        "net_val",
        "cost_mapping",
        "capital_costs_calculations_df",
        "maintenance_costs_calculations_df",
        "npv_calculations_df",
    }
)

_QUANTITY_BILL_COLUMNS = ("Category", "Item", "Unit", "Number of Units")
_QUANTITY_BILL_SKIP_ITEMS = frozenset(
    {
        "subtotal",
        "subtotal_with_fees",
        "Capital Total Cost",
        "Annual Grand Maintenance Cost",
        "Contingency",
        "Contingency (30%)",
        "Legal Fees",
        "Legal Fees (2%)",
        "Engineering",
        "Engineering (10%)",
        "Engineering (18%)",
        "Construction Admin and Oversight",
        "Construction Admin and Oversight (12%)",
        "Project Management",
        "Project Management (10%)",
        "Permitting",
        "Permitting (2%)",
        "Permitting (15%)",
        "Reporting",
        "Reporting (2%)",
    }
)

_GRAPH_QUANTITY_NODES = (
    "number_of_injection_wells",
    "number_of_dry_wells",
    "max_infiltration_area",
    "infiltration_area",
    "basin_area",
)

_SKIP_KEYS = frozenset(
    {
        "decision_graph",
        "workspace",
        "filename",
    }
) | _EXCLUDED_STORAGE_KEYS


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    """Convert storage values to JSON-serializable structures."""
    if depth > 8:
        return str(value)
    if value is None:
        return None
    if isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, pd.DataFrame):
        if value.empty:
            return []
        return value.where(pd.notnull(value), None).to_dict(orient="records")
    if isinstance(value, pd.Series):
        return {
            str(k): _json_safe(v, depth=depth + 1)
            for k, v in value.to_dict().items()
        }
    if isinstance(value, dict):
        return {
            str(k): _json_safe(v, depth=depth + 1)
            for k, v in value.items()
            if str(k) not in _SKIP_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(v, depth=depth + 1) for v in value]
    if hasattr(value, "tolist"):
        try:
            return _json_safe(value.tolist(), depth=depth + 1)
        except (TypeError, ValueError):
            pass
    if hasattr(value, "__dict__"):
        return str(value)
    return str(value)


def _extract_quantity_bill(df: pd.DataFrame, *, bill_type: str) -> list[dict]:
    """Return line-item quantities only (no unit prices or dollar totals)."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []

    rows: list[dict] = []
    for _, row in df.iterrows():
        item = str(row.get("Item", "")).strip()
        if not item or item in _QUANTITY_BILL_SKIP_ITEMS:
            continue
        try:
            qty = float(row.get("Number of Units", 0) or 0)
        except (TypeError, ValueError):
            qty = 0.0
        if qty <= 0:
            continue
        rows.append(
            {
                "bill_type": bill_type,
                "category": str(row.get("Category", "")).strip(),
                "item": item,
                "unit": str(row.get("Unit", "")).strip(),
                "number_of_units": qty,
            }
        )
    return rows


def _summarize_graph_quantities() -> dict | None:
    """Pull engineering quantity nodes from the knowledge graph (no costs)."""
    graph = dash_storage.get_data("decision_graph")
    if graph is None or not hasattr(graph, "get_node_value"):
        return None

    quantities: dict[str, Any] = {}
    for node_id in _GRAPH_QUANTITY_NODES:
        try:
            value = graph.get_node_value(node_id)
        except Exception:
            continue
        if value is None:
            continue
        quantities[node_id] = _json_safe(value)
    return quantities or None


def _summarize_dss_results(dss_results: Any) -> dict | None:
    if dss_results is None:
        return None
    summary: dict[str, Any] = {}
    results = getattr(dss_results, "results", None)
    if isinstance(results, dict) and results:
        for option_name, result in results.items():
            if not isinstance(result, dict):
                continue
            summary[str(option_name)] = {
                "status": result.get("status"),
                "benefit_score": result.get("benefit_score"),
                "warnings": (result.get("warnings") or [])[:12],
                "mitigations": (result.get("mitigations") or [])[:12],
            }
    filters = getattr(dss_results, "filters", None)
    if filters:
        summary["_rule_filters"] = _json_safe(filters)
    return summary or None


def summarize_project_context() -> dict:
    """Build a JSON-safe snapshot of project data from all tabs."""
    storage = dash_storage.get_data_storage() or {}
    context: dict[str, Any] = {}

    for key in _CONTEXT_KEYS:
        if key in storage and key not in _EXCLUDED_STORAGE_KEYS:
            context[key] = _json_safe(storage[key])

    quantity_rows: list[dict] = []
    for df_key, bill_type in (
        ("capital_costs_calculations_df", "capital"),
        ("maintenance_costs_calculations_df", "maintenance"),
    ):
        df = storage.get(df_key)
        if df is not None:
            quantity_rows.extend(_extract_quantity_bill(df, bill_type=bill_type))

    if quantity_rows:
        context["engineering_quantity_bill"] = quantity_rows

    graph_quantities = _summarize_graph_quantities()
    if graph_quantities:
        context["engineering_quantities_from_model"] = graph_quantities

    dss_summary = _summarize_dss_results(storage.get("dss_results"))
    if dss_summary:
        context["dss_rule_based_results"] = dss_summary

    location = _location_text(context.get("project_location"))
    if location:
        context["project_location"] = location

    context["_cost_data_policy"] = (
        "MAR DSS internal unit prices, cost estimates, NPV, and totals are intentionally "
        "excluded. Use engineering_quantity_bill and engineering_quantities_from_model for "
        "scope only. Research location-specific capital and O&M costs independently from "
        "public sources, regional bid data, and industry references for "
        f"{location or 'the project location'}."
    )

    return context


def build_engineering_decision_prompt(context: dict | None = None) -> str:
    """Build the MAR engineering-option scoring prompt for an external AI model."""
    context = context if context is not None else summarize_project_context()
    location = _location_text(context.get("project_location")) or "unspecified location"
    context_json = json.dumps(context, indent=2, default=str)

    options_list = ", ".join(f'"{name}"' for name in ENGINEERING_OPTIONS)
    html_instructions = downloadable_html_deliverable_instructions(
        f"MAR Engineering Option Decision Report — {location}",
        context_line=f"Project location: {location}",
    )

    return textwrap.dedent(
        f"""
        **ROLE:** Multidisciplinary Managed Aquifer Recharge (MAR) Decision Support Expert
        (Hydrogeologist, Civil/Environmental Engineer, Regulatory Specialist, Economist)

        **GOAL:** Evaluate and rank the three MAR engineering options for **{location}** using
        all project data provided below. Assign a feasibility score (0–100) to each option and
        explain your decision with actionable warnings and recommendations.

        **ENGINEERING OPTIONS (use these exact names):**
        1. Surface Recharge (spreading ponds / spreading basins)
        2. Injection Well
        3. Dry Well

        **PROJECT DATA (JSON from MAR DSS — Overview, Water Source, Hydro, Engineering,
        Feasibilities, Environmental, and rule-based DSS if available):**

        **IMPORTANT — COST DATA POLICY:** The JSON deliberately excludes MAR DSS internal unit
        prices, line-item unit costs, capital totals, maintenance totals, NPV, and cost_mapping.
        It includes **engineering quantities only** (`engineering_quantity_bill`: category, item,
        unit, number_of_units). You must **not** use or infer costs from any omitted fields.
        Instead, independently research **location-specific** capital and O&M cost estimates for
        **{location}** using credible online/public sources (regional bid tabs, RSMeans or similar
        indices, published utility/agency project costs, contractor estimates, academic/industry
        references). Cite the type of source in explanation rows when cost affects your ranking.

        ```json
        {context_json}
        ```

        ---

        ### TASK INSTRUCTIONS

        1. **Synthesize** hydrologic, hydrogeologic, engineering scope (quantities/units),
           environmental, regulatory, and DSS rule-based inputs from the JSON above.
        2. **Estimate costs independently** for each option using the quantity bill and project
           location — do not use any internal MAR DSS dollar figures (none are provided).
        3. **Score each option** on overall feasibility (0 = not feasible, 100 = highly feasible).
           Sub-factors include water availability, site geology, independently researched
           lifecycle cost, regulatory burden, environmental risk, constructability, and O&M.
        4. **Rank** options 1 (best) through 3 (least feasible). Ranks must be unique.
        5. **Identify gaps:** if critical data is missing, lower confidence in scores and note
           this in the explanation table. Include at least one explanation row on cost methodology
           or regional cost assumptions when cost influences the ranking.

        ---

        ### OUTPUT CONSTRAINTS

        #### Table 1 — Option Feasibility Scores (PRIMARY — scores only)

        Produce **exactly three rows**, one per option: {options_list}.

        Columns:
        | Engineering Option | Feasibility Score (0–100) | Rank (1–3) | Score Summary |

        - `engineering_option` must match one of the three names exactly.
        - `feasibility_score` is numeric 0–100.
        - `rank` is integer 1 (best) to 3.
        - `score_summary` is one concise sentence explaining the score.

        #### Table 2 — Decision Explanation (SECONDARY)

        Provide supporting rows with columns:
        | Category | Topic | Detail | Related Option |

        - `category`: one of Warning, Recommendation, Key Finding, Decision Rationale, Mitigation, Data Gap
        - `topic`: short title
        - `detail`: actionable explanation
        - `related_option`: option name or "All"

        Include at least:
        - 3 Decision Rationale rows (why the top option ranks first)
        - 2 Warning rows (if applicable)
        - 2 Recommendation rows
        - 1 Key Finding row summarizing trade-offs across options

        Present both tables inside the downloadable HTML report. Scores table is the
        authoritative ranking; explanations must not contradict the scores or ranks.

        {html_instructions}
        """
    ).strip()
