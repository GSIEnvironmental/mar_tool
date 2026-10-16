
from typing import Any, Dict, List
from mar_dss.mar.options import MAROption
import mar_dss.app.utils.data_storage as data_storage

hardend_constraints =[]
levels = {
    -1: "Irrelevant",
    0: "Acceptable",
    1: "Acceptable with additional Cost",
    2: "Warning",
    3: "Mitigation",
    4: "Reject",
}

NOT_AVAILABLE_RISK = "Unknown"
_WQ_DATA_GAP_PREFIX = "Warning: Data gap — "
WQ_UNKNOWN = "Unknown"
WQ_NO = "No"
WQ_YES = "Yes"
WQ_TURBIDITY_LOW = "<5 NTU"
WQ_TURBIDITY_MOD = "5-20 NTU"
WQ_TURBIDITY_HIGH = ">20 NTU"


def _water_quality_data_gap_penalty(parameter_label: str) -> str:
    return (
        f"{_WQ_DATA_GAP_PREFIX}{parameter_label} not available; "
        "assumed very low risk pending water quality data collection."
    )


def _finalize_water_quality_group_response(response: int, penalty: list) -> tuple[int, list]:
    """Promote to Warning when only data-gap messages exist (very low risk, but flagged)."""
    if response > 0:
        return response, penalty
    if any(p.startswith(_WQ_DATA_GAP_PREFIX) for p in penalty):
        return 2, penalty
    return response, penalty

def soft_constraints(option: MAROption) -> List[Dict[str, Any]]:
    """Generate soft constraints for MAR options."""
    

    constraints = []
    graph = data_storage.get_data("decision_graph")
    if graph.get_node_value("confined"):
        aquifer_type = "confined"
    else:
        aquifer_type = "unconfined"
    water_source = data_storage.get_data("water_source")
    
    
    # ==================================================================
    # 1. ground surface slope
    # ==================================================================    
    slope_significance = graph.get_node_value('gs_slope_significance')
    if aquifer_type.lower() == "confined":
        response = -1
        penalty = []
    else:
        response = 0
        penalty = []
        if slope_significance == "Gentle":
            pass
        elif slope_significance == "Moderate":
            if option.name == "Surface Recharge":
                response = 1
                penalty = ["Cost: Moderate extra cost for earthwork to mitigate slope"]
            else:
                response = 0
                penalty = []
        elif slope_significance == "Steep":
            if option.name == "Surface Recharge":
                response = 3
                penalty = ["Cost: Significant extra cost for earthwork to mitigate slope"]
            else:
                response = 0
                penalty = []

        if option.name in ["Dry Well", "Injection Well"]:
            response = 0
            penalty = []
   
    
    ground_surface_slope = {
        "name": "Ground surface slope Suitability",
        "response": response,   # 0–4
        "penalty": penalty,
        "type": "hydrogeologic",
        "hard": True if "Ground surface slope Suitability" in hardend_constraints else False
    }
    constraints.append(ground_surface_slope)

    # ==================================================================
    # 2. restrictive vadose zone infiltration
    # ==================================================================
    high_infiltration = graph.get_node_value('k_vadose_threshold')
    # Injection wells bypass the vadose; this check does not apply
    if option.name == "Injection Well":
        response = -1
        penalty = []
    elif aquifer_type.lower() == "confined":
        response = -1
        penalty = []
    else:
        if (high_infiltration):
            response = 0
            penalty = []
        else:
            if option.name == "Surface Recharge":
                response = 3
                penalty = ["Cost: Consider bypassing vadose zone infiltration"]
            else:
                response = 0
                penalty = []
            
    vadose_infiltration = {
        "name": "Vadose zone infiltration",
        "response": response,   # 0–4
        "penalty": penalty,
        "type": "hydrogeologic",
        "hard": True if "Vadose zone infiltration" in hardend_constraints else False
    }
    constraints.append(vadose_infiltration)

     # ==================================================================
    # 3. vadose zone pollution
    # ==================================================================

    vadose_pollution = graph.get_node_value('vadose_pollution_present')
    if option.name == "Injection Well":
        response = -1
        penalty = []
    elif aquifer_type.lower() == "confined":
        response = -1
        penalty = []
    else:
        if not (vadose_pollution):
            response = 0
            penalty = []
        else:
            if option.name == "Surface Recharge":
                response = 3
                penalty = ["Cost: Consider bypassing vadose zone pollution or remediation"]
            else:
                response = 0
                penalty = []       
        
    vadose_pollution_metric = {
        "name": "Vadose zone pollution",
        "response": response,   # 0–4
        "penalty": penalty, 
        "type": "hydrogeologic",
        "hard": True if "Vadose zone pollution" in hardend_constraints else False
    }
    constraints.append(vadose_pollution_metric)
    
    # ==================================================================
    # 4. vadose_biodegradable
    # ==================================================================
    vadose_biodegradable = graph.get_node_value('vadose_biodegradable')
    if option.name == "Injection Well":
        response = -1
        penalty = []
    elif aquifer_type.lower() == "confined":
        response = -1
        penalty = []
    else:
        if vadose_pollution:
            if vadose_biodegradable:
                if option.name == "Surface Recharge":
                    response = 2 # warning
                    penalty = ["Warning: Vadose zone pollution is biodegradable, ensure natural attenuation is monitored"]
                else:
                    response = 0
                    penalty = []
            else:
                if option.name == "Surface Recharge":
                    response = 3
                    penalty = ["Cost: Consider bypassing vadose zone pollution or remediation"]
                else:            
                    response = 2 # warning
                    penalty = ["Action: Toxic contamination in the vadose. Although can be bypassed, mounding water table may mobilize contaminants to the aquifer"]
        else:
            response = 0
            penalty = []

    vadose_biodegradable_metric = {
        "name": "Vadose zone pollution biodegradability",
        "response": response,   # 0–4
        "penalty": penalty,
        "type": "hydrogeologic",
        "hard": True if "Vadose zone biodegradability" in hardend_constraints else False
    }
    constraints.append(vadose_biodegradable_metric)
    
    # ==================================================================
    # 5. vadose zone remediation
    # ==================================================================
    vadose_remediation = graph.get_node_value('vadose_remediation_needed')
    if option.name == "Injection Well":
        response = -1
        penalty = []
    elif aquifer_type.lower() == "confined":
        response = -1
        penalty = []
    else:
        if vadose_remediation:
            if option.name == "Surface Recharge":
                response = 3
                penalty = ["Cost: Consider bypassing vadose zone or remediation"]
            else:
                response = 0
                penalty = []
        else:
            response = 0
            penalty = []
    vadose_remediation_needed = {
        "name": "Vadose zone remediation needed",
        "response": response,   # 0–4
        "penalty": penalty,
        "type": "hydrogeologic",
        "hard": True if "Vadose zone remediation needed" in hardend_constraints else False
    }
    constraints.append(vadose_remediation_needed)

    # ==================================================================
    # 6. vadose zone residence time
    # ==================================================================
    vadose_residence_time = graph.get_node_value('vadose_residence_time')
    residence_time_issues = graph.get_node_value('vadose_residence_time_issues')
    if option.name == "Injection Well":
        response = -1
        penalty = []
    elif aquifer_type.lower() == "confined":
        response = -1
        penalty = []
    else:
        if vadose_residence_time is None:
            response = 0
            penalty = []
        else:
            if residence_time_issues is not None and len(residence_time_issues) > 0:
                response = 3
                penalty = [f"Mitigation: Vadose zone residence time ({vadose_residence_time} days) is not reasonable for {', '.join(residence_time_issues)}"]
            else:
                response = 2
                penalty = [f"Warning: Vadose zone residence time ({vadose_residence_time} days) is reasonable but careful monitoring is needed"]
 
    vadose_residence_time_metric = {
        "name": "Vadose zone residence time",
        "response": response,   # 0–4
        "penalty": penalty,
        "type": "hydrogeologic",
        "hard": True if "Vadose zone residence time" in hardend_constraints else False
    }
    constraints.append(vadose_residence_time_metric)

    # ==================================================================
    # 7. surface recharge suitability
    # ==================================================================
    surface_recharge_suitability = graph.get_node_value('surface_recharge_suitability')
    # Not applicable to well-based options (they bypass surface recharge)
    if option.name in ["Injection Well", "Dry Well"]:
        response = -1
        penalty = []
    elif aquifer_type.lower() == "confined":
        response = -1
        penalty = []
    else:
        if surface_recharge_suitability is None:
            response = 0
            penalty = []
        elif surface_recharge_suitability:
            response = 0
            penalty = []
        else:
            response = 3
            penalty = [
                "Mitigation: Surface recharge is likely not suitable because of "
                "ground slope, infiltration, or vadose zone contamination"
            ]
    surface_recharge_suitability_metric = {
        "name": "Surface recharge suitability",
        "response": response,   # 0–4
        "penalty": penalty,
        "type": "hydrogeologic",
        "hard": True if "Surface recharge suitability" in hardend_constraints else False
    }
    constraints.append(surface_recharge_suitability_metric)

    # ==================================================================
    # 8. confined aquifer depth
    # ==================================================================
    confined_aquifer_depth = graph.get_node_value('excessive_deep_aquifer')
    if aquifer_type.lower() == "unconfined":
        response = -1
        penalty = []
    else:
        if confined_aquifer_depth is None:
            response = 0
            penalty = []
        else:
            if aquifer_type.lower() == "confined":
                if confined_aquifer_depth == "Too Deep":
                    response = 4
                    penalty = ["Reject :: Confined aquifer depth is too deep"]
                elif confined_aquifer_depth == "Moderate Deep":
                    response = 2
                    penalty = ["Cost: Confined aquifer depth is moderate deep"]
                else:
                    response = 0
                    penalty = []
            else:
                response = 0
                penalty = []
    confined_aquifer_depth_metric = {
        "name": "Confined aquifer depth Suitability",
        "response": response,   # 0–4
        "penalty": penalty, 
        "type": "hydrogeologic",
        "hard": True if "Confined aquifer depth" in hardend_constraints else False
    }
    constraints.append(confined_aquifer_depth_metric)

    # ==================================================================
    # leakage significance
    # ==================================================================
    leakage_significance = graph.get_node_value('leakage_significance')
    if aquifer_type.lower() == "unconfined":
        response = -1
        penalty = []
    else: # confined
        if leakage_significance == "low":
            response = 0
            penalty = []
        elif leakage_significance == "medium":
            response = 2
            penalty = ["Warning: Confined leakage is moderate"]
        elif leakage_significance == "high":
            response = 3
            penalty = ["Mitigation: Confined leakage is significant"]
        else:
            response = 0
            penalty = []

    leakage_significance_metric = {
        "name": "Confined leakage significance",
        "response": response,   # 0–4
        "penalty": penalty, 
        "type": "hydrogeologic",
        "hard": True if "Confined leakage significance" in hardend_constraints else False
    }
    constraints.append(leakage_significance_metric)

    # ==================================================================
    # land use
    # ==================================================================
    land_use = data_storage.get_data("land_use")
    land_use_response = 0
    land_use_penalty = []
    if land_use in [
        "Residential",
        "Commercial/Industrial",
        "Urban Residential",
        "Urban Nonresidential",
    ]:
        if option.name == "Surface Recharge":
            land_use_response = 1
            land_use_penalty.append("Cost: Land cost increase in urban areas. Check zoning requirements and land use regulations.")
        else:
            land_use_response = 0
            land_use_penalty = []

    land_use_constraint = {
        "name": "Land Use",
        "response": land_use_response,
        "penalty": land_use_penalty,
        "type": "hydrogeologic",
        "hard": True if "Land Use" in hardend_constraints else False
    }
    constraints.append(land_use_constraint)

    # ==================================================================
    # Environmental Assessment Constraints (based on Water Quality & Geochemistry tab)
    # ==================================================================
    
    # Get environmental assessment data from data storage
    # Note: data_storage is the same module used throughout the app
    # Get water quality screening answers from data storage
    source_contaminants = data_storage.get_data("wq_source_contaminants") or WQ_UNKNOWN
    source_turbidity = data_storage.get_data("wq_source_turbidity") or WQ_UNKNOWN
    vadose_impacted = data_storage.get_data("wq_vadose_impacted") or WQ_UNKNOWN
    aquifer_anthropogenic = data_storage.get_data("wq_aquifer_anthropogenic") or WQ_UNKNOWN
    aquifer_natural = data_storage.get_data("wq_aquifer_natural") or WQ_UNKNOWN

    # if land_use in ["Urban Residential", "Urban Nonresidential"]:
    #     if water_source in ["Urban Stormwater Runoff"]:
    #         environmental_assessment_response = 1
    #         environmental_assessment_penalty.append("Cost: Environmental assessment cost increase in urban areas. Check zoning requirements and land use regulations.")
    #     else:
    #         environmental_assessment_response = 0
    #         environmental_assessment_penalty = []

 

    # ==================================================================
    # 1. Source Water Contaminants
    # ==================================================================
    source_contaminants_response = 0
    source_contaminants_penalty = []
    if source_contaminants == WQ_YES:
        source_contaminants_response = 3
        source_contaminants_penalty.append(
            "Mitigation + Cost: Source water is impacted with industrial, domestic, or emerging contaminants — "
            "MAR may still be possible based on site-specific conditions and overall objectives, but "
            "additional considerations and potential costs may be necessary and are beyond the scope of this tool."
        )
    elif source_contaminants == WQ_UNKNOWN:
        source_contaminants_penalty.append(
            _water_quality_data_gap_penalty("Source water contaminants")
        )

    source_contaminants_response, source_contaminants_penalty = _finalize_water_quality_group_response(
        source_contaminants_response, source_contaminants_penalty
    )
    constraints.append({
        "name": "Source Water Contaminants",
        "response": source_contaminants_response,
        "penalty": source_contaminants_penalty,
        "type": "environmental",
        "hard": True if "Source Water Contaminants" in hardend_constraints else False
    })

    # ==================================================================
    # 2. Clogging & Fouling Risks (turbidity)
    # ==================================================================
    clogging_fouling_response = 0
    clogging_fouling_penalty = []
    if source_turbidity == WQ_TURBIDITY_HIGH:
        clogging_fouling_response = 3
        clogging_fouling_penalty.append(
            "Mitigation + Cost: Source-water turbidity >20 NTU requires pretreatment to prevent clogging"
        )
    elif source_turbidity == WQ_TURBIDITY_MOD:
        clogging_fouling_response = 1
        clogging_fouling_penalty.append(
            "Warning + Cost: Source-water turbidity 5-20 NTU may require sedimentation/clarification"
        )
    elif source_turbidity == WQ_UNKNOWN:
        clogging_fouling_penalty.append(_water_quality_data_gap_penalty("Source water turbidity"))

    clogging_fouling_response, clogging_fouling_penalty = _finalize_water_quality_group_response(
        clogging_fouling_response, clogging_fouling_penalty
    )
    constraints.append({
        "name": "Clogging & Fouling Risks",
        "response": clogging_fouling_response,
        "penalty": clogging_fouling_penalty,
        "type": "environmental",
        "hard": True if "Clogging & Fouling Risks" in hardend_constraints else False
    })

    # ==================================================================
    # 3. Need for Remediation (vadose / unsaturated zone)
    # ==================================================================
    remediation_needed_response = 0
    remediation_needed_penalty = []
    if aquifer_type.lower() == "confined":
        remediation_needed_response = -1
        remediation_needed_penalty = []
    elif vadose_impacted == WQ_YES:
        if option.name == "Surface Recharge":
            remediation_needed_response = 4
            remediation_needed_penalty.append(
                "Reject: Vadose/unsaturated zone is impacted by contaminants — "
                "surface recharge is not feasible"
            )
        else:
            remediation_needed_response = 0
            remediation_needed_penalty = []
    elif vadose_impacted == WQ_UNKNOWN:
        remediation_needed_penalty.append(
            _water_quality_data_gap_penalty("Vadose/unsaturated zone contamination")
        )
        remediation_needed_response, remediation_needed_penalty = _finalize_water_quality_group_response(
            remediation_needed_response, remediation_needed_penalty
        )

    constraints.append({
        "name": "Need for Remediation",
        "response": remediation_needed_response,
        "penalty": remediation_needed_penalty,
        "type": "environmental",
        "hard": True if "Need for Remediation" in hardend_constraints else False
    })

    # ==================================================================
    # 4. Target Aquifer Anthropogenic Contaminants
    # ==================================================================
    aquifer_anthro_response = 0
    aquifer_anthro_penalty = []
    if aquifer_anthropogenic == WQ_YES:
        aquifer_anthro_response = 4
        aquifer_anthro_penalty.append(
            "Reject: Target aquifer is impacted by anthropogenic contaminants — "
            "aquifer water quality is unsuitable; all MAR options are not feasible"
        )
    elif aquifer_anthropogenic == WQ_UNKNOWN:
        aquifer_anthro_penalty.append(
            _water_quality_data_gap_penalty("Target aquifer anthropogenic contaminants")
        )

    aquifer_anthro_response, aquifer_anthro_penalty = _finalize_water_quality_group_response(
        aquifer_anthro_response, aquifer_anthro_penalty
    )
    constraints.append({
        "name": "Target Aquifer Anthropogenic Contaminants",
        "response": aquifer_anthro_response,
        "penalty": aquifer_anthro_penalty,
        "type": "environmental",
        "hard": True if "Target Aquifer Anthropogenic Contaminants" in hardend_constraints else False
    })

    # ==================================================================
    # 5. Target Aquifer Naturally Occurring Contaminants
    # ==================================================================
    aquifer_natural_response = 0
    aquifer_natural_penalty = []
    if aquifer_natural == WQ_YES:
        aquifer_natural_response = 2
        aquifer_natural_penalty.append(
            "Warning + Cost: Target aquifer is impacted by naturally occurring contaminants — "
            "MAR may still be possible based on site-specific conditions and overall objectives, but "
            "additional considerations and potential costs may be necessary and are beyond the scope of this tool."
        )
    elif aquifer_natural == WQ_UNKNOWN:
        aquifer_natural_penalty.append(
            _water_quality_data_gap_penalty("Target aquifer naturally occurring contaminants")
        )

    aquifer_natural_response, aquifer_natural_penalty = _finalize_water_quality_group_response(
        aquifer_natural_response, aquifer_natural_penalty
    )
    constraints.append({
        "name": "Target Aquifer Naturally Occurring Contaminants",
        "response": aquifer_natural_response,
        "penalty": aquifer_natural_penalty,
        "type": "environmental",
        "hard": True if "Target Aquifer Naturally Occurring Contaminants" in hardend_constraints else False
    })

    # Regulation questionnaire scoring removed: (5.1) is informational only
    # and must not affect DSS / feasibility decisions.

    return constraints
