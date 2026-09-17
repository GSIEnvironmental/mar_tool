
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
    if aquifer_type.lower() == "confined":
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
    if aquifer_type.lower() == "confined":
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
    if aquifer_type.lower() == "confined":
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
    if aquifer_type.lower() == "confined":
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
    if aquifer_type.lower() == "confined":
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
    if aquifer_type.lower() == "confined":
        response = -1
        penalty = []
    else:
        if surface_recharge_suitability is None:
            response = 0
            penalty = []
        else:
            if surface_recharge_suitability:
                response = 0
                penalty = []
            else:
                if option.name in ["Injection Well", "Dry Well"]:
                    response = -1
                    penalty = []
                else:
                    response = 3
                    penalty = ["Mitigation: Surface recharge is likely not suitable because of ground slope, infiltration, or vadose zone contamination"]
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

    # ==================================================================
    # Regulation Constraints (Basic Regulation Feasibility)
    # ==================================================================
    
    # Get regulation data from data storage
    regulation_data = data_storage.get_data("regulation_data")
    
    if regulation_data:
        # ==================================================================
        # Group 0: Project/Jurisdiction Screen (1 constraint)
        # ==================================================================
        group_0 = regulation_data.get("group_0", {})
        federal_nexus = group_0.get("federal_nexus", "No")
        tribal_interstate = group_0.get("tribal_interstate", "None")
        
        # Evaluate all Group 0 inputs and determine worst-case response
        group_0_response = 0
        group_0_penalty = []
        group_0_issues = []
        
        if federal_nexus and federal_nexus.startswith("Yes"):
            group_0_issues.append("Federal nexus triggers NEPA/ESA/NHPA reviews")
            group_0_response = max(group_0_response, 3)
        
        if tribal_interstate in ["Tribal lands/resources", "Interstate compact", "Both"]:
            group_0_issues.append("Tribal/interstate context requires additional coordination")
            group_0_response = max(group_0_response, 2)
        
        if group_0_response >= 3:
            group_0_penalty.append("Mitigation + Cost: High jurisdictional complexity - multiple federal and tribal/interstate requirements increase project timeline and cost")
        elif group_0_response == 2:
            group_0_penalty.append("Warning + Cost: Jurisdictional complexity - additional coordination, permits, and compliance reviews required")
        elif group_0_response == 0 and len(group_0_issues) > 0:
            group_0_penalty.append("Cost: Moderate jurisdictional complexity - additional coordination and compliance requirements")
        
        group_0_constraint = {
            "name": "Project/Jurisdiction Regulatory Feasibility",
            "response": group_0_response,
            "penalty": group_0_penalty,
            "type": "Regulation",
            "hard": True if "Project/Jurisdiction Regulatory Feasibility" in hardend_constraints else False
        }
        constraints.append(group_0_constraint)
        
        # ==================================================================
        # Group A: Site Feasibility (1 constraint)
        # ==================================================================
        group_a = regulation_data.get("group_a", {})
        a_control = group_a.get("site_control", "Have site control")
        a_zoning = group_a.get("zoning", "Allowed")
        a_wetlands = group_a.get("wetlands", "No impacts")
        a_sensitive = group_a.get("sensitive", "None")
        a_public = group_a.get("public_lands", "Not applicable")
        a_dams = group_a.get("dams", "Not applicable")
        a_seismic = group_a.get("seismic", "Compliant")
        
        # Evaluate all Group A inputs and determine worst-case response
        group_a_response = 0
        group_a_penalty = []
        group_a_issues = []
        
        # Site control
        if "Cannot secure" in a_control or "Prohibited" in a_control:
            group_a_response = 4
            group_a_issues.append("Cannot secure site control")
        elif "Can secure" in a_control:
            group_a_response = max(group_a_response, 1)
            group_a_issues.append("Site control must be secured")
        
        # Zoning
        if "Prohibited" in a_zoning:
            group_a_response = 4
            group_a_issues.append("Land use/zoning prohibits project")
        elif "Conditionally" in a_zoning or "permit" in a_zoning.lower() or "variance" in a_zoning.lower():
            group_a_response = max(group_a_response, 2)
            group_a_issues.append("Conditional land use approval required")
        
        # Wetlands
        if "Permit unlikely" in a_wetlands or "Prohibited" in a_wetlands:
            group_a_response = 4
            group_a_issues.append("Wetlands permit not feasible")
        elif "permit" in a_wetlands.lower() and "No impacts" not in a_wetlands:
            group_a_response = max(group_a_response, 2)
            group_a_issues.append("Wetlands permit required")
        
        # Sensitive resources
        if "unmitigable" in a_sensitive.lower() or "Prohibited" in a_sensitive:
            group_a_response = 4
            group_a_issues.append("Sensitive resources unmitigable")
        elif "Present" in a_sensitive and "mitigable" in a_sensitive.lower():
            group_a_response = max(group_a_response, 2)
            group_a_issues.append("Sensitive resources require mitigation")
        
        # Public lands
        if "unobtainable" in a_public.lower() or "Prohibited" in a_public:
            group_a_response = 4
            group_a_issues.append("Public lands authorization unobtainable")
        elif "obtainable" in a_public.lower():
            group_a_response = max(group_a_response, 1)
            group_a_issues.append("Public lands authorization required")
        
        # Dam safety
        if "Not approvable" in a_dams or "Prohibited" in a_dams:
            group_a_response = 4
            group_a_issues.append("Dam safety approval not obtainable")
        elif "Approvable with conditions" in a_dams:
            group_a_response = max(group_a_response, 2)
            group_a_issues.append("Dam safety approval with conditions")
        
        # Seismic
        if "Noncompliant" in a_seismic or "Prohibited" in a_seismic:
            group_a_response = 4
            group_a_issues.append("Seismic compliance not met")
        elif "Mitigable" in a_seismic:
            group_a_response = max(group_a_response, 2)
            group_a_issues.append("Seismic mitigation required")
        
        if group_a_response == 4:
            group_a_penalty.append("Reject: Site feasibility requirements cannot be met - project prohibited")
        elif group_a_response >= 2:
            group_a_penalty.append(f"Warning + Cost: Site feasibility requires compliance - {', '.join(group_a_issues[:3])}")
        elif group_a_response == 1:
            group_a_penalty.append(f"Cost: Site feasibility requires additional approvals - {', '.join(group_a_issues[:2])}")
        
        group_a_constraint = {
            "name": "Site Feasibility Regulatory Compliance",
            "response": group_a_response,
            "penalty": group_a_penalty,
            "type": "Regulation",
            "hard": True if "Site Feasibility Regulatory Compliance" in hardend_constraints else False
        }
        constraints.append(group_a_constraint)

        
        
        
        # ==================================================================
        # Group B: Water Source Feasibility (1 constraint)
        # ==================================================================
        group_b = regulation_data.get("group_b", {})
        b_right = group_b.get("right", "Valid right/contract")
        b_account = group_b.get("accounting", "Authorized")
        b_compact = group_b.get("compact", "Not applicable")
        b_src_feasible = group_b.get("src_feasible", "Feasible")
        b_convey = group_b.get("conveyance", "Available")
        
        # Evaluate all Group B inputs and determine worst-case response
        group_b_response = 0
        group_b_penalty = []
        group_b_issues = []
        
        # Water rights
        if "No path" in b_right or "Prohibited" in b_right:
            group_b_response = 4
            group_b_issues.append("No path to valid water right")
        elif "Obtainable" in b_right:
            group_b_response = max(group_b_response, 1)
            group_b_issues.append("Water right must be obtained")
        
        # Recharge authorization
        if "No statutory" in b_account or "Prohibited" in b_account:
            group_b_response = 4
            group_b_issues.append("No statutory pathway for recharge authorization")
        elif "Authorizable with conditions" in b_account:
            group_b_response = max(group_b_response, 2)
            group_b_issues.append("Recharge authorization requires conditions")
        
        # Interstate compact
        if "Noncompliant" in b_compact or "Prohibited" in b_compact:
            group_b_response = 4
            group_b_issues.append("Interstate compact noncompliance")
        
        # Source-specific compliance
        if "Not feasible" in b_src_feasible or "Prohibited" in b_src_feasible:
            group_b_response = 4
            group_b_issues.append("Source-specific compliance not feasible")
        elif "Feasible with conditions" in b_src_feasible:
            group_b_response = max(group_b_response, 1)
            group_b_issues.append("Source-specific compliance with conditions")
        
        # Conveyance
        if "Unavailable" in b_convey or "Prohibited" in b_convey:
            group_b_response = 4
            group_b_issues.append("Conveyance unavailable")
        elif "Negotiable" in b_convey:
            group_b_response = max(group_b_response, 1)
            group_b_issues.append("Conveyance requires negotiation")
        
        if group_b_response == 4:
            group_b_penalty.append("Reject: Water source feasibility requirements cannot be met - project prohibited")
        elif group_b_response >= 2:
            group_b_penalty.append(f"Warning + Cost: Water source feasibility requires compliance - {', '.join(group_b_issues[:3])}")
        elif group_b_response == 1:
            group_b_penalty.append(f"Cost: Water source feasibility requires additional approvals - {', '.join(group_b_issues[:2])}")
        
        group_b_constraint = {
            "name": "Water Source Regulatory Feasibility",
            "response": group_b_response,
            "penalty": group_b_penalty,
            "type": "Regulation",
            "hard": True if "Water Source Regulatory Feasibility" in hardend_constraints else False
        }
        constraints.append(group_b_constraint)
        
        # ==================================================================
        # Group C: Water Quality Feasibility (1 constraint)
        # ==================================================================
        group_c = regulation_data.get("group_c", {})
        c_uic = group_c.get("uic", "Not applicable")
        c_mcls = group_c.get("mcls", "Assured")
        c_antideg = group_c.get("antideg", "No lowering")
        c_compat = group_c.get("compat", "Acceptable")
        c_cecs = group_c.get("cecs", "Compliant")
        c_residuals = group_c.get("residuals", "Permittable")
        c_wells = group_c.get("wells", "Compliant")
        
        # Evaluate all Group C inputs and determine worst-case response
        group_c_response = 0
        group_c_penalty = []
        group_c_issues = []
        
        # UIC permit
        if "Not feasible" in c_uic or "Prohibited" in c_uic:
            group_c_response = 4
            group_c_issues.append("UIC Class V permit not feasible")
        elif c_uic == "Feasible":
            group_c_response = max(group_c_response, 1)
            group_c_issues.append("UIC Class V permit required")
        
        # MCLs/no-endangerment
        if "Cannot be met" in c_mcls or "Prohibited" in c_mcls:
            group_c_response = 4
            group_c_issues.append("SDWA MCLs/no-endangerment standards cannot be met")
        elif "Achievable with treatment" in c_mcls or "monitoring" in c_mcls.lower():
            group_c_response = max(group_c_response, 2)
            group_c_issues.append("MCLs/no-endangerment requires treatment/monitoring")
        
        # Anti-degradation
        if "Not compliant" in c_antideg or "Prohibited" in c_antideg:
            group_c_response = 4
            group_c_issues.append("Anti-degradation/TMDL noncompliance")
        elif "Lowering justified" in c_antideg or "studies" in c_antideg.lower():
            group_c_response = max(group_c_response, 2)
            group_c_issues.append("Anti-degradation/TMDL requires justification/studies")
        
        # Geochemical compatibility
        if "Not acceptable" in c_compat or "Prohibited" in c_compat:
            group_c_response = 4
            group_c_issues.append("Geochemical compatibility not acceptable")
        elif "Mitigable with treatment" in c_compat or "modeling" in c_compat.lower():
            group_c_response = max(group_c_response, 2)
            group_c_issues.append("Geochemical compatibility requires treatment/modeling")
        
        # CECs/PFAS
        if "Not compliant" in c_cecs or "Prohibited" in c_cecs:
            group_c_response = 4
            group_c_issues.append("CECs/PFAS compliance not met")
        elif "Compliant with advanced treatment" in c_cecs:
            group_c_response = max(group_c_response, 2)
            group_c_issues.append("CECs/PFAS requires advanced treatment")
        
        # Residuals handling
        if "Not permittable" in c_residuals or "Prohibited" in c_residuals:
            group_c_response = 4
            group_c_issues.append("Residuals handling not permittable")
        elif "Permittable with conditions" in c_residuals:
            group_c_response = max(group_c_response, 2)
            group_c_issues.append("Residuals handling requires conditions")
        
        # Well construction
        if "Noncompliant" in c_wells or "Prohibited" in c_wells:
            group_c_response = 4
            group_c_issues.append("Well construction/monitoring noncompliance")
        elif "Compliant with conditions" in c_wells:
            group_c_response = max(group_c_response, 2)
            group_c_issues.append("Well construction/monitoring requires conditions")
        
        if group_c_response == 4:
            group_c_penalty.append("Reject: Water quality feasibility requirements cannot be met - project prohibited")
        elif group_c_response >= 2:
            group_c_penalty.append(f"Warning + Cost: Water quality feasibility requires compliance - {', '.join(group_c_issues[:3])}")
        elif group_c_response == 1:
            group_c_penalty.append(f"Cost: Water quality feasibility requires additional approvals - {', '.join(group_c_issues[:2])}")
        
        group_c_constraint = {
            "name": "Water Quality Regulatory Feasibility",
            "response": group_c_response,
            "penalty": group_c_penalty,
            "type": "Regulation",
            "hard": True if "Water Quality Regulatory Feasibility" in hardend_constraints else False
        }
        constraints.append(group_c_constraint)

    return constraints