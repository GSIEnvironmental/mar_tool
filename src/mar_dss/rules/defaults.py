defaults = {}
defaults["k_min_vadose_threshold"] = 0.3
defaults["leakage_radius"] = 1000
defaults["excessive_deep_aquifer"] = [1500.0, 3000.0]
# [moderate_deep_threshold_ft, too_deep_threshold_ft]:
# depth <= [0] → Low Depth; ( [0], [1] ] → Moderate Deep; > [1] → Too Deep

# maximum perecenatge of source water that can be recharged
defaults["maximum_rechargability"] = 50
# Cap on injection rate per well — gallons per minute.
# Hydrologic kernels still use ft³/day via :func:`get_max_injection_Q_per_well_ft3_day`.
defaults["max_injection_Q_per_well"] = 500  # gpm
defaults["max_number_of_injection_wells"] = 20
defaults["max_number_of_dry_wells"] = 20

# dry well — transfer-rate cap used for dry-well count sizing (gpm → ft³/day)
defaults["max_dry_well_transfer_rate_gpm"] = 50
defaults["max_drywell_depth_ft"] = 10

# Minimum depth to water table below ground surface (ft) before waterlogging /
# operational constraints bind. Used as graph input ``d_gw_min``.
defaults["d_gw_min"] = 5.0


defaults["average_moisture_content"] = 0.1  # dimensionless

# minimum residence time for natural attenuation (days)
defaults["pathogenic_bacteria_residence_time"] = 30  # days - minimum for biodegradation
defaults["organic_matter_residence_time"] = 7
defaults["trace_organic_matter_residence_time"] = 30
defaults["Nutrients_residence_time"] = 30


RULE_DEFAULTS_OVERRIDES_STORAGE_KEY = "rule_defaults_overrides"

GALLONS_PER_FT3 = 7.48051948
MINUTES_PER_DAY = 1440.0
# Overrides above this are treated as legacy ft³/day (old default was 100000).
_LEGACY_INJECTION_Q_FT3_DAY_THRESHOLD = 5000.0


def gpm_to_ft3_per_day(gpm) -> float:
    """Convert gallons per minute to cubic feet per day."""
    return float(gpm) * MINUTES_PER_DAY / GALLONS_PER_FT3


def ft3_per_day_to_gpm(ft3_per_day) -> float:
    """Convert cubic feet per day to gallons per minute."""
    return float(ft3_per_day) * GALLONS_PER_FT3 / MINUTES_PER_DAY


def _coerce_injection_q_gpm(val, fallback):
    """Interpret stored max injection Q as gpm; convert legacy ft³/day if needed."""
    try:
        raw = float(val)
    except (TypeError, ValueError):
        return fallback
    if not (raw > 0) or raw != raw:  # NaN / non-positive
        return fallback
    # Old UI stored ft³/day (~1e5); new UI stores gpm (~500).
    if raw > _LEGACY_INJECTION_Q_FT3_DAY_THRESHOLD:
        return ft3_per_day_to_gpm(raw)
    return raw


def get_max_injection_Q_per_well_ft3_day() -> float:
    """Maximum injection rate per well in ft³/day for Theis / well-count sizing."""
    return gpm_to_ft3_per_day(get_default("max_injection_Q_per_well"))


def get_max_dry_well_transfer_rate_ft3_day() -> float:
    """Maximum dry-well transfer rate in ft³/day for dry-well count sizing."""
    return gpm_to_ft3_per_day(get_default("max_dry_well_transfer_rate_gpm"))


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
        if key == "max_injection_Q_per_well":
            return _coerce_injection_q_gpm(val, float(base))
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
