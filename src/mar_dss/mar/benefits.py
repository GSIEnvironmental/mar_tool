from typing import Any, Dict, List
from mar_dss.mar.options import MAROption
import mar_dss.app.utils.data_storage as data_storage

def benefits(option: MAROption) -> List[Dict[str, float]]:
    """Generate benefit metrics for MAR options."""

    benefits_list = []
    graph = data_storage.get_data("decision_graph")
    if graph.get_node_value("confined"):
        aquifer_type = "confined"
    else:
        aquifer_type = "unconfined" # ['Unconfined', 'Confined', 'Semi-confined', 'Karstic', 'Fractured', 'Other']

    # ==================================================================
    # 1. Volume of source water that can be recharged
    # ==================================================================
    rechargability = graph.get_node_value('rechargability')
    if rechargability is None:
        rechargability = {}
    if option.name == "Surface Recharge":
        rechargable_percentage = rechargability.get('surface_recharge_percentage', 0)
    elif option.name == "Injection Well":
        rechargable_percentage = rechargability.get('injection_recharge_percentage', 0)
    elif option.name == "Dry Well":
        rechargable_percentage = rechargability.get('dry_well_recharge_percentage', 0)
    else:
        rechargable_percentage = 0

    confined_rechargability = graph.get_node_value('confined_rechargability')
    if confined_rechargability is None:
        confined_rechargability = 0
    if aquifer_type.lower() == "Unconfined".lower():        
        value = rechargable_percentage/100
        weight = 100
    else: # confined       
       value = confined_rechargability/100
       weight = 100

    source_water_volume_rechargable = {
        "name": "Recharge Efficiency",
        "value": value,
        "weight": weight
    }
    benefits_list.append(source_water_volume_rechargable)

  
   

    # normalize weights to 1
    total_weight = sum(benefit["weight"] for benefit in benefits_list)
    for benefit in benefits_list:
        benefit["weight"] = benefit["weight"] / total_weight

    return benefits_list
