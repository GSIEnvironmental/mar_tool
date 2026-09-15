# hard constraints for mar options

from typing import Any, Dict, List
from mar_dss.mar.options import MAROption
import mar_dss.app.utils.data_storage as data_storage
from mar_dss.rules.defaults import get_default

def hard_constraints(option: MAROption) -> List[Dict[str, bool]]:
    """Generate hard constraints for MAR options."""
   
    constraints = []
    graph = data_storage.get_data("decision_graph")

    if graph.get_node_value("confined"):
        aquifer_type = "confined"
    else:
        aquifer_type = "unconfined"
    #graph.get_node_value('aq_type')  # ['Unconfined', 'Confined', 'Semi-confined', 'Karstic', 'Fractured', 'Other']

    # ==================================================================
    # Surface rechargeability
    # ==================================================================   
    if aquifer_type.lower() == "Unconfined".lower():
        check = True
        why = "Unconfined aquifer is suitable for surface recharge"
    else:
        if option.name in ["Surface Recharge"]:
            check = False
            why = f"Surface recharge is not suitable for recharging {aquifer_type} aquifer"
        else:
            check = True
            why = f"{option.name} is suitable for recharging {aquifer_type} aquifer"
    initial_surface_rechargeability = {
        "name": "Physical surface rechargeability",
        "pass": check,
        "why": why
    }
    constraints.append(initial_surface_rechargeability)

    # ==================================================================
    # Recharge Efficiency
    # ==================================================================
    rechargability = graph.get_node_value('rechargability')
    if rechargability is None:
        rechargability = {}
    surface_recharge_percentage = rechargability.get('surface_recharge_percentage', 0)
    injection_recharge_percentage = rechargability.get('injection_recharge_percentage', 0)
    dry_well_recharge_percentage = rechargability.get('dry_well_recharge_percentage', 0)
    if option.name == "Surface Recharge":
        rechargable_percentage = surface_recharge_percentage
    elif option.name == "Injection Well":
        rechargable_percentage = injection_recharge_percentage
    elif option.name == "Dry Well":
        rechargable_percentage = dry_well_recharge_percentage
    else:
        rechargable_percentage = 0
  


    confined_rechargability = graph.get_node_value('confined_rechargability')
    if confined_rechargability is None:
        confined_rechargability = 0


    rechargeable_pct_def = (
        "the share of the total annual source water volume this option can actually "
        "recharge into the aquifer"
    )

    if aquifer_type.lower() == "Unconfined".lower():
        mx = get_default("maximum_rechargability")
        if rechargable_percentage < mx:
            check = False
            why = (
                f"Rechargeable percentage ({rechargeable_pct_def}) is "
                f"{round(rechargable_percentage, 2)}%, below the required minimum of {mx}%"
            )
            if option.name == "Injection Well":
                injection_wells_result = graph.get_node_value('number_of_injection_wells')
                if isinstance(injection_wells_result, dict) and injection_wells_result.get("reason"):
                    why = f"{injection_wells_result['reason']} ({round(rechargable_percentage, 2)}% of source water recharged this way)"
        else:
            check = True
            why = (
                f"Rechargeable percentage ({rechargeable_pct_def}) is "
                f"{round(rechargable_percentage, 2)}%, meeting the required minimum of {mx}%"
            )
    else:
        mx = get_default("maximum_rechargability")
        if confined_rechargability < mx:
            check = False
            why = (
                f"Confined rechargeable percentage ({rechargeable_pct_def}, via injection "
                f"into the confined unit) is {round(confined_rechargability, 2)}%, below the "
                f"required minimum of {mx}%"
            )
        else:
            check = True
            why = (
                f"Confined rechargeable percentage ({rechargeable_pct_def}, via injection "
                f"into the confined unit) is {round(confined_rechargability, 2)}%, meeting the "
                f"required minimum of {mx}%"
            )
    
    recharge_efficiency_metric = {
        "name": "Recharge Efficiency",
        "pass": check,
        "why": why
       
    }
    constraints.append(recharge_efficiency_metric)

    
    return constraints