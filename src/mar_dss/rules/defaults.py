
defaults = {}
defaults["k_min_vadose_threshold"] = 0.3
defaults['leakage_radius'] = 1000
defaults['excessive_deep_aquifer'] = [1500.0, 3000.0]
# [moderate_deep_threshold_ft, too_deep_threshold_ft]:
# depth <= [0] → Low Depth; ( [0], [1] ] → Moderate Deep; > [1] → Too Deep

# maximum perecenatge of source water that can be recharged
defaults["maximum_rechargability"] = 50
defaults["max_injection_Q_per_well"] = 100000 #  ft^3/day
defaults["max_number_of_injection_wells"] = 20

#dary well 
defaults["max_dry_well_infiltration_rate_in_per_hr"] = 60000 #  ft^3/day
defaults["max_dry_well_transfer_rate_gpm"] = 50
defaults["max_drywell_depth_ft"] = 10

# Minimum depth to water table below ground surface (ft) before waterlogging /
# operational constraints bind. Used as graph input ``d_gw_min``.
defaults["d_gw_min"] = 5.0


# default effective porosity for vadose zone (if not available from stratigraphy)
defaults["vadose_effective_porosity"] = 0.2 # porosity times moisture content
defaults["average_moisture_content"] = 0.1 # dimensionless

# minimum residence time for natural attenuation (days)
defaults["pathogenic_bacteria_residence_time"] = 30  # days - minimum for biodegradation
defaults["organic_matter_residence_time"] = 7 
defaults["trace_organic_matter_residence_time"] = 30
defaults["Nutrients_residence_time"] = 30


RULE_DEFAULTS_OVERRIDES_STORAGE_KEY = "rule_defaults_overrides"


def get_default(key):
    """
    Return a rule default, optionally overridden by dashboard storage
    ``rule_defaults_overrides`` (flat dict merged with :data:`defaults`).
    """
    base = defaults[key]
    try:
        import mar_dss.app.utils.data_storage as dash_storage

        ov = dash_storage.get_data(RULE_DEFAULTS_OVERRIDES_STORAGE_KEY)
        if not isinstance(ov, dict) or key not in ov or ov[key] is None:
            return base
        val = ov[key]
        if key == "excessive_deep_aquifer":
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                return [float(val[0]), float(val[1])]
            return list(base)
        if isinstance(base, bool):
            return bool(val)
        if isinstance(base, int) and not isinstance(base, bool):
            try:
                return int(round(float(val)))
            except (TypeError, ValueError):
                return base
        if isinstance(base, float):
            try:
                return float(val)
            except (TypeError, ValueError):
                return base
        return val
    except Exception:
        pass
    return base