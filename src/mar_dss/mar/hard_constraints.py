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


    if aquifer_type.lower() == "Unconfined".lower():
        mx = get_default("maximum_rechargability")
        if rechargable_percentage < mx:
            check = False
            why = f"Rechargeable percentage {round(rechargable_percentage, 2)}% is less than the maximum rechargeable percentage {mx}"
        else:
            check = True
            why = f"Rechargeable percentage {round(rechargable_percentage, 2)}% is greater than the maximum rechargeable percentage {mx}"
    else:
        mx = get_default("maximum_rechargability")
        if confined_rechargability < mx:
            check = False
            why = f"Confined rechargeable percentage {round(confined_rechargability, 2)}% is less than the maximum rechargeable percentage {mx}"
        else:
            check = True
            why = f"Confined rechargeable percentage {round(confined_rechargability, 2)}% is greater than the maximum rechargeable percentage {mx}"
    
    recharge_efficiency_metric = {
        "name": "Recharge Efficiency",
        "pass": check,
        "why": why
       
    }
    constraints.append(recharge_efficiency_metric)

    
    return constraints