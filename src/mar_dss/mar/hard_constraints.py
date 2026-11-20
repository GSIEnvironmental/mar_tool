# hard constraints for mar options

import mar_dss.app.utils.data_storage as data_storage
from mar_dss.mar.options import MAROption
from mar_dss.rules.defaults import get_default


def hard_constraints(option: MAROption) -> list[dict[str, bool]]:
    """Generate hard constraints for MAR options."""

    constraints = []
    graph = data_storage.get_data("decision_graph")

    if graph.get_node_value("confined"):
        aquifer_type = "confined"
    else:
        aquifer_type = "unconfined"
    # graph.get_node_value('aq_type')  # ['Unconfined', 'Confined', 'Semi-confined', 'Karstic', 'Fractured', 'Other']

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
        "why": why,
        "type": "hydrogeologic",
    }
    constraints.append(initial_surface_rechargeability)

    # ==================================================================
    # Vadose / unsaturated zone contamination (Water Quality Q3)
    # ==================================================================
    vadose_impacted = data_storage.get_data("wq_vadose_impacted") or "Unknown"
    if option.name == "Surface Recharge" and vadose_impacted == "Yes":
        vadose_check = False
        vadose_why = "Surface recharge is not feasible: the vadose/unsaturated zone is impacted by contaminants"
    else:
        vadose_check = True
        if vadose_impacted == "Yes":
            vadose_why = f"{option.name} can bypass the impacted vadose/unsaturated zone"
        else:
            vadose_why = "Vadose/unsaturated zone contamination does not preclude this option"
    constraints.append(
        {
            "name": "Vadose zone contaminant impact",
            "pass": vadose_check,
            "why": vadose_why,
            "type": "water_quality",
        },
    )

    # ==================================================================
    # Target aquifer anthropogenic contaminants (Water Quality Q4)
    # ==================================================================
    aquifer_anthropogenic = data_storage.get_data("wq_aquifer_anthropogenic") or "Unknown"
    if aquifer_anthropogenic == "Yes":
        anthro_check = False
        anthro_why = (
            f"{option.name} is not feasible: the target aquifer is impacted by "
            "anthropogenic contaminants (poor aquifer water quality)"
        )
    else:
        anthro_check = True
        anthro_why = "Target aquifer anthropogenic contaminant status does not preclude this option"
    constraints.append(
        {
            "name": "Target aquifer anthropogenic contaminants",
            "pass": anthro_check,
            "why": anthro_why,
            "type": "water_quality",
        },
    )

    # ==================================================================
    # Recharge Efficiency
    # ==================================================================
    rechargability = graph.get_node_value("rechargability")
    if rechargability is None:
        rechargability = {}
    surface_recharge_percentage = rechargability.get("surface_recharge_percentage", 0)
    injection_recharge_percentage = rechargability.get("injection_recharge_percentage", 0)
    dry_well_recharge_percentage = rechargability.get("dry_well_recharge_percentage", 0)
    if option.name == "Surface Recharge":
        rechargeable_percentage = surface_recharge_percentage
    elif option.name == "Injection Well":
        rechargeable_percentage = injection_recharge_percentage
    elif option.name == "Dry Well":
        rechargeable_percentage = dry_well_recharge_percentage
    else:
        rechargeable_percentage = 0

    confined_rechargability = graph.get_node_value("confined_rechargability")
    if confined_rechargability is None:
        confined_rechargability = 0

    rechargeable_pct_def = (
        "the share of the total annual source water volume this option can actually recharge into the aquifer"
    )

    if aquifer_type.lower() == "Unconfined".lower():
        mx = get_default("maximum_rechargability")
        if rechargeable_percentage < mx:
            check = False
            why = (
                f"Rechargeable percentage ({rechargeable_pct_def}) is "
                f"{round(rechargeable_percentage, 2)}%, below the required minimum of {mx}%"
            )
            if option.name == "Injection Well":
                injection_wells_result = graph.get_node_value("number_of_injection_wells")
                if isinstance(injection_wells_result, dict) and injection_wells_result.get("reason"):
                    why = (
                        f"{injection_wells_result['reason']} ({round(rechargeable_percentage, 2)}% of source water "
                        "recharged this way)"
                    )
        else:
            check = True
            why = (
                f"Rechargeable percentage ({rechargeable_pct_def}) is "
                f"{round(rechargeable_percentage, 2)}%, meeting the required minimum of {mx}%"
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
        "why": why,
        "type": "hydrogeologic",
    }
    constraints.append(recharge_efficiency_metric)

    return constraints
