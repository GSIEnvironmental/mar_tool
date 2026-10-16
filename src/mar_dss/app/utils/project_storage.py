"""Normalize and default-fill MAR DSS project values in dash storage."""

from __future__ import annotations

import ast
import copy
import json
import math
from typing import Any

import pandas as pd

import mar_dss.app.utils.data_storage as dash_storage

_STRING_KEYS = frozenset({
    "project_name",
    "project_location",
    "analysis_date",
    "workspace",
    "filename",
    "land_use",
    "water_source",
    "water_conveyance",
    "water_ownership",
    "pumping_needed",
    "aq_type",
    "vadose_zone_pollution",
    "overview_map_basemap",
    "overview_map_location_label",
    "water_source_map_site",
    "wq_source_contaminants",
    "wq_source_turbidity",
    "wq_vadose_impacted",
    "wq_aquifer_anthropogenic",
    "wq_aquifer_natural",
})


def normalize_stored_string(value: Any) -> str:
    """Treat None, NaN, and empty CSV sentinels as missing; else return stripped str."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text.lower() in ("nan", "none", "<na>", "nat"):
        return ""
    return text


def is_missing_storage_value(value: Any) -> bool:
    """True when a stored value should be replaced with a project default."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, str) and normalize_stored_string(value) == "":
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return False
    return False


def _parse_literal_if_needed(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    if (text.startswith("[") and text.endswith("]")) or (
        text.startswith("{") and text.endswith("}")
    ):
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            pass
    return value


def build_project_storage_defaults() -> dict[str, Any]:
    """Default project values aligned with the New Project reset."""
    from mar_dss.app.components.hydro_tab import (
        default_stratigraphy_layers,
        normalize_groundwater_data,
        normalize_stratigraphy_recharge_target,
    )
    from mar_dss.app.components.overview_tab import (
        DEFAULT_OVERVIEW_MAP_BASEMAP,
        DEFAULT_OVERVIEW_MAP_LAT,
        DEFAULT_OVERVIEW_MAP_LON,
        DEFAULT_OVERVIEW_MAP_ZOOM,
    )

    strat = default_stratigraphy_layers()
    normalize_stratigraphy_recharge_target(strat)

    return {
        "project_name": "",
        "project_location": "",
        "analysis_date": "",
        "workspace": "",
        "filename": "",
        "mar_purpose": ["secure_water_supply"],
        "ground_surface_slope": 0.5,
        "max_available_area": 1.0,
        "max_infiltration_area": 0.7,
        "land_use": "Residential",
        "water_source": "surface_water_sources",
        "proximity_distance": 1.0,
        "water_conveyance": "open_canals_ditches",
        "water_ownership": "legal_rights",
        "pumping_needed": "no",
        "monthly_flow": [0.0] * 12,
        "design_events_per_month": 4.0,
        "total_runoff_ft3": 0.0,
        "fraction_flow_capture": 1.0,
        "flow_capture_values": [
            "flow_capture_structure",
            "pump_used",
            "rough_grading",
        ],
        "sediment_removal_needed": "yes",
        "storage_needed": "yes",
        "storage_pond_values": ["storage_pond_construction"],
        "pumped_storage_values": [
            "pipeline_cost",
            "pumping_bag_filter_cost",
            "controls",
            "electrical_system",
        ],
        "distance_to_storage_pond_ft": 500.0,
        "pumped_infiltration_values": [
            "infiltration_pipeline_cost",
            "infiltration_pumping_bag_filter_cost",
            "infiltration_controls",
            "infiltration_electrical_system",
        ],
        "view_runoff_calculator": False,
        "view_recharge_mound_outputs": False,
        "view_treatment_cost_guidance": False,
        "view_feasibility_details": False,
        "physical_parameters": [],
        "chemical_parameters": [],
        "biological_indicators": [],
        "emerging_contaminants": [],
        "wq_source_contaminants": "Unknown",
        "wq_source_turbidity": "Unknown",
        "wq_vadose_impacted": "Unknown",
        "wq_aquifer_anthropogenic": "Unknown",
        "wq_aquifer_natural": "Unknown",
        "vadose_zone_pollution": "None",
        "aq_type": "unconfined",
        "confined_aquifer_head_ft": None,
        "max_dry_well_depth_ft": 120.0,
        "aquitard_conductivity_ft_day": 1e-3,
        "stratigraphy_data": strat,
        "groundwater_data": normalize_groundwater_data([]),
        "ground_surface_elevation": 120.0,
        "max_mar_storage_depth": 20.0,
        "extension_length": 100.0,
        "extension_width": 50.0,
        "extension_rotation": 0.0,
        "upstream_head": 10.0,
        "downstream_head": 5.0,
        "overview_map_lat": DEFAULT_OVERVIEW_MAP_LAT,
        "overview_map_lon": DEFAULT_OVERVIEW_MAP_LON,
        "overview_map_zoom": DEFAULT_OVERVIEW_MAP_ZOOM,
        "overview_map_location_label": "",
        "overview_map_basemap": DEFAULT_OVERVIEW_MAP_BASEMAP,
        "water_source_map_site": "source_site",
    }


def coerce_storage_value(key: str, value: Any, default: Any) -> Any:
    """Coerce a loaded/stored value to the expected shape for ``key``."""
    from mar_dss.app.components.hydro_tab import (
        normalize_groundwater_data,
        normalize_stratigraphy_list_from_raw,
        normalize_stratigraphy_recharge_target,
    )
    from mar_dss.app.components.overview_tab import normalize_land_use

    value = _parse_literal_if_needed(value)

    if key in _STRING_KEYS:
        return normalize_stored_string(value)

    if key == "land_use":
        return normalize_land_use(value)

    if key == "mar_purpose":
        if isinstance(value, list) and value:
            return value
        if isinstance(value, str) and value.strip():
            parsed = _parse_literal_if_needed(value)
            if isinstance(parsed, list) and parsed:
                return parsed
        return copy.deepcopy(default)

    if key == "monthly_flow":
        if isinstance(value, list) and len(value) == 12:
            try:
                return [float(v) for v in value]
            except (TypeError, ValueError):
                return copy.deepcopy(default)
        return copy.deepcopy(default)

    if key == "stratigraphy_data":
        coerced = normalize_stratigraphy_list_from_raw(value)
        if coerced is None:
            return copy.deepcopy(default)
        normalize_stratigraphy_recharge_target(coerced)
        return coerced

    if key == "groundwater_data":
        return normalize_groundwater_data(value if value is not None else [])

    if key == "overview_map_basemap" and value == "stamen-terrain":
        return "opentopomap"

    if isinstance(default, bool):
        return bool(value)

    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return default

    if isinstance(default, float):
        try:
            out = float(value)
            if math.isfinite(out):
                return out
        except (TypeError, ValueError):
            pass
        return default

    if isinstance(default, list):
        if isinstance(value, list):
            return value
        return copy.deepcopy(default)

    if isinstance(default, dict):
        if isinstance(value, dict):
            return value
        return copy.deepcopy(default)

    return value


def apply_project_storage_defaults() -> None:
    """Fill missing keys and coerce known values so save/load stays consistent."""
    defaults = build_project_storage_defaults()
    for key, default_val in defaults.items():
        current = dash_storage.get_data(key)
        if is_missing_storage_value(current):
            stored = copy.deepcopy(default_val) if isinstance(default_val, (list, dict)) else default_val
            dash_storage.set_data(key, stored)
            continue
        coerced = coerce_storage_value(key, current, default_val)
        dash_storage.set_data(key, coerced)


def prepare_project_storage_for_export() -> None:
    """Ensure storage has complete, serializable defaults before CSV/JSON export."""
    apply_project_storage_defaults()

    # Drop values that cannot be serialized; export uses its own skip list too.
    for key, value in list((dash_storage.get_data_storage() or {}).items()):
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            dash_storage.set_data(key, None)
