import logging
import numpy as np
import pandas as pd
from mar_dss.rules.analytical_solutions import (
    compute_mounding_grid,
    compute_recharge_rate,
    compute_recharge_mound,
    mounding_integral_sum_at_point,
    theis_drawdown_or_Q,
)
from mar_dss.rules.defaults import get_default

logger = logging.getLogger(__name__)


def recharge_target_layer_row_index(strat_df):
    """
    Return the 0-based row index of the layer where recharge target is True.

    Accepts either:
    - **pandas.DataFrame** with column ``"Recharge Target Layer"`` (preferred), or
    - **list** inputs (legacy / some graph pipelines):
      - list of dicts with key ``"recharge_target"``
      - list of lists where the 4th element is a boolean recharge flag

    If no flag is present (or none are True), defaults to **0** (top layer),
    matching the dashboard default.
    """
    if strat_df is None:
        return 0

    # DataFrame path
    if isinstance(strat_df, pd.DataFrame):
        col = "Recharge Target Layer"
        if col not in strat_df.columns:
            return 0
        for i in range(len(strat_df)):
            v = strat_df.iloc[i][col]
            if pd.notna(v) and bool(v):
                return i
        return 0

    # List paths
    if isinstance(strat_df, list) and strat_df:
        first = strat_df[0]

        # list of dicts from dashboard storage
        if isinstance(first, dict):
            for i, row in enumerate(strat_df):
                if bool(row.get("recharge_target", False)):
                    return i
            return 0

        # list of lists from analysis inputs / knowledge graph
        if isinstance(first, list):
            for i, row in enumerate(strat_df):
                if len(row) >= 4 and bool(row[3]):
                    return i
            return 0

    return 0


_GW_MONTH_ORDER = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _strat_df_to_dashboard_rows(strat_df):
    """Convert graph ``strat_df`` (DataFrame from ``get_stratigraphy_table``) to dashboard row dicts."""
    if isinstance(strat_df, pd.DataFrame):
        rows = []
        for _, row in strat_df.iterrows():
            rt = row.get("Recharge Target Layer", False)
            if pd.isna(rt):
                rt = False
            rows.append(
                {
                    "thickness": float(row["thickness"]),
                    "conductivity": float(row["K"]),
                    "recharge_target": bool(rt),
                }
            )
        return rows
    if isinstance(strat_df, list) and strat_df:
        if isinstance(strat_df[0], dict):
            return list(strat_df)
        if isinstance(strat_df[0], list):
            out = []
            for r in strat_df:
                t, k = float(r[0]), float(r[1])
                rt = bool(r[3]) if len(r) >= 4 else False
                out.append(
                    {"thickness": t, "conductivity": k, "recharge_target": rt}
                )
            return out
    return []


def _monthly_depths_to_gw_rows(monthly_gw_depth):
    """Build dashboard-style groundwater rows; use datum ``gs=0`` so ``elevation = -depth`` (see ``infer_aquifer_type``)."""
    d = np.asarray(monthly_gw_depth, dtype=float).reshape(-1)
    if d.size == 0:
        return []
    if d.size < 12:
        d = np.pad(d, (0, 12 - int(d.size)), mode="edge")
    elif d.size > 12:
        d = d[:12]
    return [
        {"month": _GW_MONTH_ORDER[i], "elevation": -float(d[i])}
        for i in range(12)
    ]


def infer_aquifer_type(strat_df, monthly_gw_depth):
    """
    Decision-graph entry point: same inference as :func:`infer_dashboard_aquifer_type`.

    Uses monthly **depths** (ft below ground) with a fixed datum ``gs = 0`` so that
    ``elevation = -depth``; confined vs unconfined depends only on thicknesses and
    depths, matching the dashboard rule for identical stratigraphy and depths.
    """
    strat_rows = _strat_df_to_dashboard_rows(strat_df)
    gw_rows = _monthly_depths_to_gw_rows(monthly_gw_depth)
    return infer_dashboard_aquifer_type(strat_rows, gw_rows, 0.0)


def aquifer_inference_regime(strat_df, monthly_gw_depth):
    """Return ``\"confined\"`` or ``\"unconfined\"`` from inferred geometry/hydraulics only.

    This is the single branch selector for MAR sizing physics. Rule nodes ``confined`` /
    ``unconfined`` are derived from the same inference, but sizing must not rely on
    ambiguous truthiness or stale graph booleans ending up both falsy.

    Anything that does not normalize to ``\"confined\"`` is treated as unconfined
    for well-count purposes.
    """
    try:
        aq = infer_aquifer_type(strat_df, monthly_gw_depth)
    except Exception as exc:
        logger.warning(
            "infer_aquifer_type failed (%s); defaulting regime to unconfined for sizing",
            exc,
        )
        return "unconfined"
    if aq is None:
        logger.warning(
            "infer_aquifer_type returned None; defaulting regime to unconfined for sizing"
        )
        return "unconfined"
    normalized = str(aq).strip().lower()
    if normalized == "confined":
        return "confined"
    return "unconfined"


# Default max *K* (ft/day) for classifying a dashboard layer as an aquitard when the user
# does not supply ``aquitard_k_max_ft_day`` and dashboard storage has no value.
DEFAULT_AQUITARD_K_MAX_FT_DAY = 1e-3


def _resolve_aquitard_k_max_ft_day(explicit):
    """Match Hydrogeology tab + callbacks: explicit value, else ``aquitard_conductivity_ft_day``."""
    if explicit is not None and str(explicit).strip() != "":
        try:
            v = float(str(explicit).strip())
            if np.isfinite(v) and v > 0.0:
                return v
        except (TypeError, ValueError):
            pass
    try:
        from mar_dss.app.utils import data_storage as dash_storage

        raw = dash_storage.get_data("aquitard_conductivity_ft_day")
        if raw is not None:
            try:
                v = float(raw)
                if np.isfinite(v) and v > 0.0:
                    return v
            except (TypeError, ValueError):
                pass
    except Exception:
        pass
    return DEFAULT_AQUITARD_K_MAX_FT_DAY


def infer_dashboard_aquifer_type(
    stratigraphy_rows,
    groundwater_rows,
    ground_surface_elevation,
    aquitard_k_max_ft_day=None,
):
    """Infer *confined* vs *unconfined* from stratigraphy + monthly water-table elevations.

    **Confined** when all apply:

    - **Aquifer geometry:** *(i)* If the target is **not** the bottom layer, an aquitard
      (low *K*) must lie immediately **above and below** the target. *(ii)* If the target
      is the **lowest** layer, only an aquitard **above** is required (base of column =
      lower boundary; no layer beneath the target).
    - **Hydraulic position:** The **top** of the recharge-target layer has an elevation
      **strictly below** the **minimum** monthly water-table elevation.

    Otherwise returns **unconfined**. Semi-confined is not inferred here.

    Parameters
    ----------
    stratigraphy_rows : list[dict]
        Dashboard ``stratigraphy_data`` rows with ``thickness``, ``conductivity``, and
        ``recharge_target`` keys.
    groundwater_rows : list[dict]
        Dashboard ``groundwater_data`` rows with numeric ``elevation`` (ft AMSL).
    ground_surface_elevation : float | None
        Ground surface elevation (ft AMSL), same datum as water-table elevations.
    aquitard_k_max_ft_day : float | None
        Layers with conductivity at or below this value (ft/day) are treated as aquitards.
        If omitted or invalid, uses dashboard ``aquitard_conductivity_ft_day`` (Hydrogeology:
        "Aquitard conductivity (ft/day):"), then ``DEFAULT_AQUITARD_K_MAX_FT_DAY``.
    """
    k_max = _resolve_aquitard_k_max_ft_day(aquitard_k_max_ft_day)

    def _is_aquitard(row):
        if not isinstance(row, dict):
            return False
        try:
            k = float(row.get("conductivity", row.get("K", 0.0)))
        except (TypeError, ValueError):
            return False
        return k <= k_max

    try:
        gs = float(ground_surface_elevation)
    except (TypeError, ValueError):
        return "unconfined"

    if stratigraphy_rows is None or groundwater_rows is None:
        return "unconfined"

    rows = (
        list(stratigraphy_rows)
        if isinstance(stratigraphy_rows, list)
        else []
    )
    if len(rows) < 2:
        return "unconfined"

    ti = None
    for i, r in enumerate(rows):
        if isinstance(r, dict) and r.get("recharge_target"):
            ti = i
            break
    if ti is None:
        ti = 0

    # Top layer: no unit above → cannot satisfy upper aquitard rule.
    if ti < 1:
        return "unconfined"

    if not _is_aquitard(rows[ti - 1]):
        return "unconfined"

    is_bottom_target = ti >= len(rows) - 1
    if not is_bottom_target:
        # Interior target: need lower aquitard as well.
        if not _is_aquitard(rows[ti + 1]):
            return "unconfined"

    try:
        thicknesses = [float(r.get("thickness", 0.0)) for r in rows]
    except (TypeError, ValueError):
        return "unconfined"

    depth_top_target = float(np.sum(thicknesses[:ti]))
    elev_top_target = gs - depth_top_target

    elevs = []
    for r in groundwater_rows:
        if isinstance(r, dict) and r.get("elevation") is not None:
            try:
                elevs.append(float(r["elevation"]))
            except (TypeError, ValueError):
                continue
    if not elevs:
        return "unconfined"

    min_wt_elev = float(np.min(elevs))

    if elev_top_target < min_wt_elev:
        return "confined"
    return "unconfined"


def is_unconfined(strat_df, monthly_gw_depth):
    return aquifer_inference_regime(strat_df, monthly_gw_depth) == "unconfined"


def is_confined(strat_df, monthly_gw_depth):
    return aquifer_inference_regime(strat_df, monthly_gw_depth) == "confined"

def find_limiting_layer(strat_df, unconfined, monthly_gw_depth):
    """The limiting layer is in the vadose zone: the lowest-K layer at or above the water table."""
    if unconfined:
        cumulative_depth = strat_df["thickness"].cumsum()
        depth = np.mean(monthly_gw_depth)

        # Position of the first layer whose bottom reaches the water table depth. A layer
        # whose bottom lands exactly on the water table is itself the last vadose layer
        # (fully unsaturated), not the layer below it, which is already saturated.
        at_or_below_wt = (cumulative_depth >= depth).to_numpy()
        if at_or_below_wt.any():
            wt_layer_pos = int(np.argmax(at_or_below_wt))
        else:
            # Water table lies below the entire stratigraphy column: it is all vadose.
            wt_layer_pos = len(strat_df) - 1

        df_ = strat_df.iloc[0:wt_layer_pos + 1]
        limit_layer_index = df_["K"].argmin()

        return limit_layer_index
    else:
        return None # irrelevant for confined aquifer

def find_min_k_vadose_zone(strat_df, limiting_layer):
    if limiting_layer is None:
        return None # irrelevant for confined aquifer
    return strat_df.iloc[limiting_layer]["K"]

def check_k_vadose_threshold(k_min_vadose):
    """
    Check if vadose zone minimum hydraulic conductivity meets threshold for infiltration.
    
    Parameters:
    - k_min_vadose: Minimum hydraulic conductivity in vadose zone (ft/day)
    
    Returns:
    - True if k_min_vadose >= threshold (suitable for infiltration)
    - False if k_min_vadose < threshold or is None
    """
    if k_min_vadose is None:
        return False
    threshold = get_default("k_min_vadose_threshold")
    return k_min_vadose >= threshold

def check_vadose_pollution(unconfined, vadose_polluted_present):
    if not (unconfined):
        return None # irrelevant for confined aquifer
    if vadose_polluted_present is None:
        return None

    if vadose_polluted_present:
        return True
    else:
        return False

def check_vadose_high_toxicity(vadose_pollution_present, vadose_pollution_high_toxicity):
    """
    Check if highly toxic contaminants are present in the vadose zone.
    
    Parameters:
    - vadose_pollution_present: Boolean indicating if pollution is present
    - vadose_pollution_high_toxicity: Boolean flag indicating high toxicity presence
    
    Returns:
    - True if highly toxic contaminants are present
    - False if no high toxicity or not applicable
    - None if no pollution present (irrelevant)
    """
    if  vadose_pollution_present is None:
        return None  # irrelevant for confined aquifer

    if vadose_pollution_high_toxicity:
        return True
    else:
        return False

def check_vadose_biodegradable(vadose_pollution_present, vadose_pollution_high_toxicity):
    if vadose_pollution_high_toxicity is None:
        return None # irrelevant for confined aquifer
    if vadose_pollution_present and not vadose_pollution_high_toxicity:
        return True
    else:
        return False
    
def check_vadose_remediation(vadose_pollution_high_toxicity):
    """
    Check if vadose zone remediation is available, completed, or feasible.
    
    Parameters:
    - vadose_pollution_present: Boolean indicating if pollution is present
    - vadose_remediation_data: Boolean, string, or dict indicating remediation status
    
    Returns:
    - True if remediation is available/completed/feasible
    - False if remediation is not available or not needed
    - None if no pollution present (remediation not applicable)
    """
    if vadose_pollution_high_toxicity is None:
        return None # irrelevant for confined aquifer
    if vadose_pollution_high_toxicity:
        return True
    else:
        return False




def check_topsoil_limiting(limiting_layer, k_min_vadose):
    if limiting_layer == 0 and k_min_vadose < get_default("k_min_vadose_threshold"):
        return True 
    else:
        return False

def check_topsoil_removable(top_soil_limiting, strat_df):
    
    if top_soil_limiting:
        top_soil_thickness = strat_df["thickness"].values[0]
        if top_soil_thickness < 6:
            return True
        else:
            return False
    else:
        return None # irrelevant if top soil is not limiting
def compute_min_gw_depth(limiting_layer, strat_df, d_gw_min, max_mar_storage_depth):
   
    if limiting_layer is None:
        return None # irrelevant for confined aquifer
    d_gw_min = float(d_gw_min)
    try:
        max_mar = float(max_mar_storage_depth)
        if not np.isfinite(max_mar) or max_mar < 0:
            max_mar = 0.0
    except (TypeError, ValueError):
        max_mar = 0.0
    # Effective operational floor: stricter of rule min and Maximum MAR Storage Depth
    d_gw_minX = max(d_gw_min, max_mar)
    

    limiting_layer = int(limiting_layer)
    k_min_vadose = strat_df.iloc[limiting_layer]["K"]
    if k_min_vadose >= get_default("k_min_vadose_threshold"):        
        return d_gw_minX
    else:
        layer_bottom_depth = strat_df["thickness"].cumsum()
        limiting_layer_bottom_depth = layer_bottom_depth.iloc[limiting_layer]
        return max(d_gw_minX, limiting_layer_bottom_depth)



def compute_spread_area(k_min_vadose, max_available_area, gw_depth, source_water_volume, strat_df, limiting_layer, op_gw_depth, top_soil_removable):

    if top_soil_removable is None:
        # None means irrelevant, False means not removable, True means removable
        pass
    else:
        if top_soil_removable:
            pass
        else:
            # not removable, so no spread area
            return None

    if k_min_vadose is None:
        return None # irrelevant for confined aquifer

    # `k_min_vadose` only measures how fast water can percolate through the vadose zone
    # above the water table; it says nothing about the recharge TARGET layer itself. A
    # highly permeable vadose zone sitting on top of a low-K target (e.g. recharging into
    # an aquitard) would otherwise look "feasible" even though the target formation can't
    # actually accept or transmit the water once it arrives.
    target_layer_index = recharge_target_layer_row_index(strat_df)
    target_k = float(strat_df.iloc[target_layer_index]["K"])
    k_threshold = get_default("k_min_vadose_threshold")
    if target_k < k_threshold:
        return {
            "spread_area": 0.0,
            "infl_rate": 0.0,
            "inf_k_ratio": 0.0,
            "reason": (
                f"Recharge target layer hydraulic conductivity ({target_k:g} ft/day) is "
                f"below the infiltration threshold ({k_threshold:g} ft/day); the target "
                "formation cannot accept meaningful recharge regardless of vadose-zone "
                "permeability."
            ),
        }

    max_available_area = float(max_available_area)
    k_min_vadose = float(k_min_vadose)
    avg_gw_depth = np.mean(gw_depth)
    limiting_layer = int(limiting_layer)
    

    layer_depths = strat_df['thickness'].cumsum()

    saturated_layres = layer_depths - avg_gw_depth
    saturated_layres = saturated_layres[saturated_layres>0]
    saturated_thickness = saturated_layres.sum()
    sat_thks = saturated_layres.diff()
    sat_thks.iloc[0] = saturated_layres.iloc[0]

    sy_s = strat_df.iloc[-(len(sat_thks)):]['sy/ss']
    k_s = strat_df.iloc[-(len(sat_thks)):]['K']
    k_mean = (k_s.values * sat_thks.values).sum() / sat_thks.values.sum()
    sy_mean = (sy_s.values * sat_thks.values).sum() / sat_thks.values.sum()

    dh = avg_gw_depth - op_gw_depth
    t = 50  # long time for near steady state
    vol_max_available = float(np.max(source_water_volume) / 30.25)

    # No allowable mound height: size footprint by vadose K only.
    if not np.isfinite(dh) or dh <= 0:
        spread_area = min(vol_max_available / k_min_vadose, max_available_area)
        return {
            "spread_area": spread_area,
            "infl_rate": k_min_vadose,
            "inf_k_ratio": 1.0,
        }

    # Footprint from vadose-limited sizing, capped by available land.
    spread_area = min(vol_max_available / k_min_vadose, max_available_area)
    if not np.isfinite(spread_area) or spread_area <= 0:
        return {
            "spread_area": 0.0,
            "infl_rate": k_min_vadose,
            "inf_k_ratio": 1.0,
        }

    # Invert Hantush mound for rate at allowable head, then take vadose limit.
    # try:
    #     rate_mound_limited = float(
    #         compute_recharge_rate(
    #             x=0,
    #             y=0,
    #             t=t,
    #             del_h=dh,
    #             spread_area=spread_area,
    #             k=k_min_vadose,
    #             b=saturated_thickness,
    #             sy=sy_mean,
    #         )
    #     )
    # except Exception:
    # rate_mound_limited = k_min_vadose

    # if not np.isfinite(rate_mound_limited) or rate_mound_limited <= 0:
    #     rate_mound_limited = k_min_vadose

    infl_rate = k_min_vadose * 0.99

    # del_h ∝ sqrt(rate): if numerical mound still exceeds, scale rate down.
    max_iterations = 50
    for _ in range(max_iterations):
        dh_actual = compute_recharge_mound(
            x=0,
            y=0,
            t=t,
            recharge_rate=infl_rate,
            spread_area=spread_area,
            k=k_mean,
            b=saturated_thickness,
            sy=sy_mean,
        )
        if not np.isfinite(dh_actual) or dh_actual <= dh:
            break
        scale = (dh / dh_actual) ** 2
        infl_rate = max(infl_rate * scale * 0.99, 1e-12)

    return {
        "spread_area": spread_area,
        "infl_rate": infl_rate,
        "inf_k_ratio": infl_rate / k_min_vadose if k_min_vadose else None,
    }

def compute_number_of_injection_wells(source_water_volume, op_gw_depth, strat_df, gw_depth, Hmax, confined, unconfined):
    regime = aquifer_inference_regime(strat_df, gw_depth)
    if not bool(confined) and not bool(unconfined):
        logger.warning(
            "Graph confined/unconfined flags are both falsy (%r, %r); using inferred regime %r for injection sizing.",
            confined,
            unconfined,
            regime,
        )
    elif regime == "confined" and not bool(confined):
        logger.debug(
            "Injection sizing follows inferred confined regime despite confined node value %r",
            confined,
        )
    elif regime == "unconfined" and not bool(unconfined):
        logger.debug(
            "Injection sizing follows inferred unconfined regime despite unconfined node value %r",
            unconfined,
        )

    if regime == "confined":
        target_layer_index = recharge_target_layer_row_index(strat_df)
        depth_of_confined_unit = strat_df.iloc[0:target_layer_index]["thickness"].sum()
        # if len(strat_df) != 4:
        #     raise ValueError("Stratigraphy table must have four layers for confined aquifer")
        txt = '==========================================================='
        txt = txt+"\n* Compute maximum allowed head change in the confined aquifer"
        txt = txt+"\n   - Maximum allowable head change is the fracture head"
        txt = txt+"\n   - The fractured gradient is 0.6 psi/ft"
        Hmax = depth_of_confined_unit * 0.6 * 2.31 # convert psi to feet
        txt = txt+f"\n  - For a depth of {depth_of_confined_unit} ft, the maximum allowable head change is {Hmax} ft"
        txt = txt+"\n   - Fracture head is the head at the fracture zone"

        kaq = strat_df.iloc[target_layer_index]["K"]
        B = strat_df.iloc[target_layer_index]["thickness"]
        Ss = strat_df.iloc[target_layer_index]["sy/ss"]
        transmissivity = kaq * B
        Ss = Ss * B
        Qmax = get_default("max_injection_Q_per_well") 
        max_Q_per_well = theis_drawdown_or_Q(Q_or_dh=Hmax, T=transmissivity, S=Ss, r=1, t=50, compute_Q=True)
        Q_per_well = min(Qmax, max_Q_per_well)     
        number_of_wells = np.ceil((np.max(source_water_volume)/30.25) / Q_per_well)       
        number_of_wells =min(get_default("max_number_of_injection_wells"), number_of_wells)
        return {"number_of_wells": number_of_wells, "Q_per_well": Q_per_well,
         'transmissivity':transmissivity, 'Ss':Ss, 'Hmax':Hmax, 'time':50, 'r':1} 

    # Unconfined / inferred default path (Thiem equation)
    target_layer_index = recharge_target_layer_row_index(strat_df)
    if strat_df.iloc[target_layer_index]["K"] < 0.2: # todo: make this general
         return {"number_of_wells": 0, "Q_per_well": 0}

    avg_gw_depth = np.mean(gw_depth)
    layer_depths = strat_df['thickness'].cumsum()

    # This sizing path models a fully screened/cased Injection Well via Theis/Thiem
    # saturated-aquifer response (transmissivity, storativity), which only applies to a
    # saturated target. A target layer above the water table is a vadose-zone recharge
    # target, already modeled by Dry Well sizing (K-based unsaturated infiltration) rather
    # than by this Theis-based method.
    bottom_of_target_depth = layer_depths.iloc[target_layer_index]
    if bottom_of_target_depth <= avg_gw_depth:
        logger.warning(
            "Recharge target layer (index %d, bottom depth %.2f ft) lies above the average "
            "water table (%.2f ft bgs); it is unsaturated, so Theis-based injection-well "
            "sizing does not apply. Vadose-zone injection is still feasible via Dry Well "
            "or surface spreading sizing.",
            target_layer_index, bottom_of_target_depth, avg_gw_depth,
        )
        return {
            "number_of_wells": 0,
            "Q_per_well": 0,
            "reason": (
                "Recharge target layer is unsaturated (above the water table); this "
                "Injection Well sizing method assumes a saturated target and does not apply. "
                "Use Dry Well or surface spreading for vadose-zone recharge."
            ),
        }

    saturated_layres = layer_depths - avg_gw_depth
    saturated_layres = saturated_layres[saturated_layres>0]
    saturated_thickness = saturated_layres.sum()
    sat_thks = saturated_layres.diff()
    sat_thks.iloc[0] = saturated_layres.iloc[0]

    sy_s = strat_df.iloc[-(len(sat_thks)):]['sy/ss']
    k_s = strat_df.iloc[-(len(sat_thks)):]['K']
    k_mean = (k_s.values * sat_thks.values).sum() / sat_thks.values.sum()
    sy_mean = (sy_s.values * sat_thks.values).sum() / sat_thks.values.sum()
    dh = avg_gw_depth - op_gw_depth
    if dh < 0:
        dh = 0

    # corrected drawdown for unconfined aquifer
    dh_corrected = dh - dh*dh/(2.0*saturated_thickness)
    if dh_corrected < 0:
        dh_corrected = 0
    transmissivity = k_mean * saturated_thickness
    Ss = sy_mean * saturated_thickness
    max_Q_per_well = theis_drawdown_or_Q(Q_or_dh=dh_corrected, T=transmissivity, S=Ss, r=1, t=50, compute_Q=True)

    #max_Q_per_well = (2 * 3.14159 * k_mean*saturated_thickness*dh) / (np.log(300))
    Qmax = get_default("max_injection_Q_per_well") #  ft^3/day, arround 20L/sec
    Q_per_well = min(max_Q_per_well, Qmax)
    number_of_wells = np.ceil((np.max(source_water_volume)/30.25) / Q_per_well)
    number_of_wells =min(get_default("max_number_of_injection_wells"), number_of_wells)

    return {"number_of_wells": number_of_wells, "Q_per_well": Q_per_well}


def compute_number_of_dry_wells(source_water_volume, op_gw_depth, strat_df, gw_depth, unconfined):
    regime = aquifer_inference_regime(strat_df, gw_depth)
    if not bool(unconfined) and regime == "unconfined":
        logger.debug(
            "Dry-well sizing follows inferred unconfined regime despite unconfined node value %r",
            unconfined,
        )

    if regime == "unconfined":
        # thiem equation
        target_layer_index = recharge_target_layer_row_index(strat_df)
        if strat_df.iloc[target_layer_index]["K"] < 0.2: # todo: make this general
            return {"number_of_dry_wells": 0, "Q_per_dry_well": 0}
        avg_gw_depth = np.mean(gw_depth)
        layer_depths = strat_df['thickness'].cumsum()

        saturated_layres = layer_depths - avg_gw_depth
        saturated_layres = saturated_layres[saturated_layres>0]
        saturated_thickness = saturated_layres.sum()
        sat_thks = saturated_layres.diff()
        sat_thks.iloc[0] = saturated_layres.iloc[0]

        sy_s = strat_df.iloc[-(len(sat_thks)):]['sy/ss']
        k_s = strat_df.iloc[-(len(sat_thks)):]['K']
        k_mean = (k_s.values * sat_thks.values).sum() / sat_thks.values.sum()
        sy_mean = (sy_s.values * sat_thks.values).sum() / sat_thks.values.sum()

        dh = avg_gw_depth - max(op_gw_depth, get_default("max_drywell_depth_ft"))
        if dh <=0:
            return {"number_of_dry_wells": 0, "Q_per_dry_well": 0}
        # corrected drawdown for unconfined aquifer
        dh_corrected = dh - dh*dh/(2.0*saturated_thickness)
        transmissivity = k_mean * saturated_thickness
        Ss = sy_mean * saturated_thickness
        max_Q_per_well = theis_drawdown_or_Q(Q_or_dh=dh_corrected, T=transmissivity, S=Ss, r=1, t=50, compute_Q=True)

        #max_Q_per_well = (2 * 3.14159 * k_mean*saturated_thickness*dh) / (np.log(300))
        Qmax = get_default("max_injection_Q_per_well") #  ft^3/day, arround 20L/sec
        Q_per_well = min(max_Q_per_well, Qmax)
        number_of_wells = np.ceil((np.max(source_water_volume)/30.25) / Q_per_well)
        number_of_wells =min(get_default("max_number_of_injection_wells"), number_of_wells)
                                        
        return {"number_of_dry_wells": number_of_wells, "Q_per_dry_well": Q_per_well}

    # Confined regime: dry-well count from target confined unit / head limits
    target_layer_index = recharge_target_layer_row_index(strat_df)
    depth_of_confined_unit = strat_df.iloc[0:target_layer_index]["thickness"].sum()
    Hmax_local = 0.20 * depth_of_confined_unit
    transmissivity = strat_df.iloc[target_layer_index]["K"] * strat_df.iloc[target_layer_index]["thickness"]
    Ss = strat_df.iloc[target_layer_index]["sy/ss"] * strat_df.iloc[target_layer_index]["thickness"]
    max_Q_per_well = theis_drawdown_or_Q(Q_or_dh=Hmax_local, T=transmissivity, S=Ss, r=1, t=50, compute_Q=True)
    Qmax = get_default("max_injection_Q_per_well") #  ft^3/day, arround 20L/sec
    Q_per_well = min(Qmax, max_Q_per_well)
    number_of_wells = np.ceil((np.max(source_water_volume)/30.25) / Q_per_well)
    number_of_wells = min(get_default("max_number_of_injection_wells"), number_of_wells)
    return {"number_of_dry_wells": number_of_wells, "Q_per_dry_well": Q_per_well}

      
    

def compute_annual_recharge_volume(design_sizing_result, source_water_volume):
    if design_sizing_result is None:
        return None # irrelevant for confined aquifer
    spread_area = design_sizing_result["spread_area"]
    infl_rate = design_sizing_result["infl_rate"]
    inf_k_ratio = design_sizing_result["inf_k_ratio"]

    annual_recharge_volume = 0
    # 30.25 is the number of days in a month
    for i in range(12):
        current_month_storage = spread_area * infl_rate * 30.25
        act_recharge =min(current_month_storage, source_water_volume[i])
        annual_recharge_volume += act_recharge

    return annual_recharge_volume   

def compute_annual_injection_volume(number_of_injection_wells_result, source_water_volume):
    if number_of_injection_wells_result is None:
        return None # irrelevant for confined aquifer
    number_of_wells = number_of_injection_wells_result["number_of_wells"]
    Q_per_well = number_of_injection_wells_result["Q_per_well"]
    annual_injection_volume = number_of_wells * Q_per_well * 365.25

    annual_injection_volume = min(annual_injection_volume, np.sum(source_water_volume))
    return annual_injection_volume

def compute_annual_dry_well_volume(number_of_dry_wells_result, source_water_volume):
    if number_of_dry_wells_result is None:
        return None # irrelevant for confined aquifer
    number_of_wells = number_of_dry_wells_result["number_of_dry_wells"]
    Q_per_dry_well = number_of_dry_wells_result["Q_per_dry_well"]
    annual_dry_well_volume = number_of_wells * Q_per_dry_well * 365.25
    annual_dry_well_volume = min(annual_dry_well_volume, np.sum(source_water_volume))
    return annual_dry_well_volume

def compute_vadose_residence_time(vadose_biodegradable, design_zing, strat_df,  avg_gw_depth):

    # Not applicable for confined aquifers
    #vadose_biodegradable = True # debug only
    if not vadose_biodegradable:
        return None
    # Calculate effective porosity from vadose zone layers
    # Use sy/ss from stratigraphy layers above water table
    #effective_porosity = defaults["vadose_effective_porosity"]  # default   

    layer_depths = strat_df['thickness'].cumsum()
    unsaturated_layres = layer_depths - np.mean(avg_gw_depth)
    unsaturated_layres = unsaturated_layres[unsaturated_layres<0]
    unsaturated_thickness = unsaturated_layres.abs().sum()
    #ks = strat_df.iloc[:(len(unsaturated_layres))]['K']

    
    # ratio = defaults["average_moisture_content"] / effective_porosity#
    # v = ks.values * ratio / effective_porosity# todo: v = k * i * theta, 
    
    infl_rate = design_zing["infl_rate"]
    v = infl_rate / get_default("average_moisture_content")
    residence_time = unsaturated_thickness / v
    return residence_time

def check_vadose_residence_time_reasonable(vadose_residence_time):
    if vadose_residence_time is None:
        return None
    unreasonble = []
    if vadose_residence_time <= 7:
        unreasonble.append("Organic Matter")
    if vadose_residence_time <=30:
        unreasonble.append("Pathogenic Bacteria")
        unreasonble.append("Trace Organic Matter")
        unreasonble.append("Nutrients")

    return unreasonble    

def compute_rechargable_percentage(annual_surface_recharge_volume, 
                                    annual_injection_volume, 
                                    annual_dry_well_volume,
                                    source_water_volume):
    # 
    if annual_surface_recharge_volume is None:
       annual_surface_recharge_volume  = 0 # irrelevant for confined aquifer
    if annual_injection_volume is None:
        annual_injection_volume = 0
    if annual_dry_well_volume is None:
        annual_dry_well_volume = 0

    rechargability_dict = {}
    rechargability_dict["surface_recharge_percentage"] =  100.0*annual_surface_recharge_volume / np.sum(source_water_volume)
    rechargability_dict["injection_recharge_percentage"] =  100.0*annual_injection_volume / np.sum(source_water_volume)
    rechargability_dict["dry_well_recharge_percentage"] =  100.0*annual_dry_well_volume / np.sum(source_water_volume)

    return rechargability_dict

    return 100.0*annual_surface_recharge_volume / np.sum(source_water_volume)


def compute_confined_storage_volume(confined, strat_df, Hmax, injection_wells_result, source_water_volume):
    # annual injection volume
    if confined:
        target_layer_index = recharge_target_layer_row_index(strat_df)
        depth_of_confined_unit = strat_df.iloc[0:target_layer_index]["thickness"].sum()       
        Hmax = depth_of_confined_unit * 0.6 * 2.31 # convert psi to feet

        
        kaq = strat_df.iloc[target_layer_index]["K"]
        B = strat_df.iloc[target_layer_index]["thickness"]
        Ss = strat_df.iloc[target_layer_index]["sy/ss"]
        transmissivity = kaq * B
        Ss = Ss * B      

        if injection_wells_result["number_of_wells"] == 1:
            max_injection_rate = injection_wells_result['number_of_wells'] * theis_drawdown_or_Q(Q_or_dh=Hmax, T=transmissivity, S=Ss, r=1, t=50, compute_Q=True)
        else:
            Q_per_well = np.max(source_water_volume)/30.25/injection_wells_result["number_of_wells"]
            dh_from_well_at_300ft = theis_drawdown_or_Q(Q_or_dh=Q_per_well, T=transmissivity, S=Ss, r=300, t=50, compute_Q=False)
            dh_superimposed = (Hmax/injection_wells_result["number_of_wells"]) + (dh_from_well_at_300ft * (injection_wells_result["number_of_wells"] -1))
            max_injection_rate = theis_drawdown_or_Q(Q_or_dh=dh_superimposed, T=transmissivity, S=Ss, r=1, t=50, compute_Q=True)
         
        
        return max_injection_rate * 365.25
    else:
        return None

def compute_confined_rechargability(annual_confined_storage_volume, source_water_volume):
    if annual_confined_storage_volume is None:
        return None # irrelevant for confined aquifer
    
    percentage = 100.0*annual_confined_storage_volume / np.sum(source_water_volume)
    if percentage > 100.0:
        return 100.0
    else:
        return percentage

def compute_leakage_significance(rechargability, strat_df):
    """Leakance is taken from the aquitard(s) bounding the recharge-target layer.

    Uses ``recharge_target_layer_row_index`` rather than fixed layer positions, so this
    works for any stratigraphy length/target position (see ``infer_dashboard_aquifer_type``,
    which already generalizes the same way). When the target is the bottom layer, there is
    no underlying unit, so leakance comes from the top aquitard only.
    """
    if rechargability is None:
        return None # irrelevant for unconfined aquifer

    target_layer_index = recharge_target_layer_row_index(strat_df)

    top_confined_layer_k = strat_df.iloc[target_layer_index - 1]["K"]
    top_confined_layer_thickness = strat_df.iloc[target_layer_index - 1]["thickness"]
    leakance_top = top_confined_layer_k / top_confined_layer_thickness

    is_bottom_target = target_layer_index >= len(strat_df) - 1
    if is_bottom_target:
        leakance = leakance_top
    else:
        bottom_confined_layer_k = strat_df.iloc[target_layer_index + 1]["K"]
        bottom_confined_layer_thickness = strat_df.iloc[target_layer_index + 1]["thickness"]
        leakance_bottom = bottom_confined_layer_k / bottom_confined_layer_thickness
        leakance = max(leakance_top, leakance_bottom)

    k_aquifer = strat_df.iloc[target_layer_index]["K"]
    aquifer_thickness = strat_df.iloc[target_layer_index]["thickness"]
    transmissivity = k_aquifer * aquifer_thickness

    BB = np.sqrt(transmissivity / leakance)
    leakage_significance = BB / get_default("leakage_radius")
    if leakage_significance> 20.0:
        return "low"
    elif leakage_significance<20.0 and leakage_significance>1:
        return "medium"
    else:
        return "high"


def compute_depth_significance(confined, strat_df):
    if not (confined):
        return None # irrelevant for unconfined aquifer

    target_layer_index = recharge_target_layer_row_index(strat_df)
    aquifer_depth = strat_df.iloc[0:target_layer_index]["thickness"].sum()

    _eda = get_default("excessive_deep_aquifer")
    # _eda[0] = start of Moderate Deep (ft); _eda[1] = start of Too Deep (ft).
    # Must satisfy _eda[0] < _eda[1] (shallower threshold first).
    if aquifer_depth > _eda[1]:
        return "Too Deep"
    elif aquifer_depth > _eda[0] and aquifer_depth <= _eda[1]:
        return "Moderate Deep"
    else:
        return "Low Depth"

def compute_gs_slope_significance(unconfined, gs_slope):
    if not (unconfined):
        return None # irrelevant for confined aquifer
    if gs_slope < 2.0:
        return "Gentle"
    elif gs_slope >= 2.0 and gs_slope < 5.0:
        return "Moderate"
    else:
        return "Steep"
    

def compute_surface_recharge_suitability(gs_slope_significance, inflitration_significance, rechargability, remediate):
    if rechargability is None:
        return None
    surface_recharge_percentage = rechargability["surface_recharge_percentage"]
    surface_recharge_suitability = True
    if (inflitration_significance is None) or (not inflitration_significance):
        surface_recharge_suitability = False
        return surface_recharge_suitability
        
    if gs_slope_significance is None or not (gs_slope_significance in ["Gentle", "Moderate"]):
        surface_recharge_suitability = False
        return surface_recharge_suitability
    
    if surface_recharge_percentage < get_default("maximum_rechargability"):
        surface_recharge_suitability = False
        return surface_recharge_suitability
    
    if remediate:  # vadose zone remediation needed → not suitable for surface recharge
        surface_recharge_suitability = False

    return surface_recharge_suitability
    
def get_stratigraphy_table(stratigraphy_table):
    """
    Convert the stratigraphy table to a pandas DataFrame.

    Each row may be 3 values (thickness, K, sy/ss) or 4 values, with the last being
    a boolean for the recharge target layer (same meaning as the Hydrogeology UI column
    "Recharge Target Layer").

    Parameters
    ----------
    stratigraphy_table : list of list
        Rows of [thickness, K, sy/ss] or [thickness, K, sy/ss, recharge_target_bool].

    Returns
    -------
    pandas.DataFrame
        Columns: thickness, K, sy/ss, and when 4 values are present, "Recharge Target Layer".
    """
    base_columns = ["thickness", "K", "sy/ss"]
    if not isinstance(stratigraphy_table, list) or not stratigraphy_table:
        raise ValueError("Invalid stratigraphy table format. Must be a non-empty list of lists.")

    ncols = len(stratigraphy_table[0])
    if ncols not in (3, 4):
        raise ValueError(
            "Each row must have 3 columns (thickness, K, sy/ss) or 4 when including "
            "recharge target (boolean)."
        )
    if not all(len(row) == ncols for row in stratigraphy_table):
        raise ValueError("All stratigraphy rows must have the same number of columns.")

    if ncols == 3:
        return pd.DataFrame(stratigraphy_table, columns=base_columns)

    columns = base_columns + ["Recharge Target Layer"]
    return pd.DataFrame(stratigraphy_table, columns=columns)


def dashboard_stratigraphy_to_dataframe(stratigraphy_data, aquifer_type=None):
    """
    Convert Hydro tab ``stratigraphy_data`` (list of dicts) into a DataFrame with
    columns ``thickness``, ``K``, ``sy/ss``, and ``Recharge Target Layer`` where applicable.

    ``sy/ss`` is filled from the dashboard by **aquifer type**:

    - **confined**: Specific Storage → ``storage`` (1/ft).
    - **unconfined**: Specific Yield → ``yield`` (dimensionless).

    Other / missing ``aquifer_type``: prefer ``storage``, then ``yield``, matching legacy behavior.
    """
    if stratigraphy_data is None:
        return None
    aq_l = str(aquifer_type or "").strip().lower()

    def _storage_term_scalar(row_like):
        if not isinstance(row_like, dict):
            return 0.0001
        if aq_l == "unconfined":
            v = row_like.get("yield", row_like.get("specific_yield"))
        elif aq_l == "confined":
            v = row_like.get("storage", row_like.get("sy/ss"))
        else:
            v = row_like.get("storage", row_like.get("sy/ss"))
            if v is None or v == "":
                v = row_like.get("yield")
        if v is None or v == "":
            return 0.0001
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0001

    if isinstance(stratigraphy_data, pd.DataFrame):
        df = stratigraphy_data.copy()
        if "conductivity" in df.columns and "K" not in df.columns:
            df = df.rename(columns={"conductivity": "K"})

        if aq_l == "unconfined" and "yield" in df.columns:
            df["sy/ss"] = pd.to_numeric(df["yield"], errors="coerce").fillna(0.0001)
        elif aq_l == "confined" and "storage" in df.columns:
            df["sy/ss"] = pd.to_numeric(df["storage"], errors="coerce").fillna(0.0001)
        elif "storage" in df.columns:
            df["sy/ss"] = pd.to_numeric(df["storage"], errors="coerce").fillna(0.0001)
        elif "yield" in df.columns:
            df["sy/ss"] = pd.to_numeric(df["yield"], errors="coerce").fillna(0.0001)
        elif "sy/ss" in df.columns:
            df["sy/ss"] = pd.to_numeric(df["sy/ss"], errors="coerce").fillna(0.0001)
        else:
            df["sy/ss"] = 0.0001

        df["sy/ss"] = df["sy/ss"].clip(lower=1e-12)

        if "Recharge Target Layer" not in df.columns:
            if "recharge_target" in df.columns:
                df["Recharge Target Layer"] = df["recharge_target"].fillna(False).astype(bool)
            else:
                df["Recharge Target Layer"] = False
        return df
    if not isinstance(stratigraphy_data, list) or not stratigraphy_data:
        return None
    rows = []
    for r in stratigraphy_data:
        if not isinstance(r, dict):
            continue
        rows.append(
            {
                "thickness": float(r.get("thickness") or 0.0),
                "K": float(r.get("conductivity", r.get("K")) or 0.0),
                "sy/ss": max(_storage_term_scalar(r), 1e-12),
                "Recharge Target Layer": bool(r.get("recharge_target", False)),
            }
        )
    if not rows:
        return None
    return pd.DataFrame(rows)


def build_confined_theis_xy_plot_dict(
    stratigraphy_input,
    half_length_ft,
    half_width_ft,
    nx=48,
    ny=48,
    t_days=50.0,
    well_r_ft=1.0,
):
    """
    Build a dictionary of confined-aquifer drawdown on a grid using the Theis solution
    (:func:`theis_drawdown_or_Q` at each radius). Suitable for ``go.Contour`` in the XY view.

    Returns
    -------
    dict
        ``ok`` (bool), and on success: ``x``, ``y`` (1-D, ft), ``drawdown_ft`` (2-D), ``Q_ft3_per_day``,
        ``transmissivity_ft2_per_day``, ``storativity``, ``time_days``, ``Hmax_ft``,
        ``reference_radius_ft``, plus values passed through from the confined injection-well sizing logic.
    """
    out: dict = {"ok": False}
    strat_df = dashboard_stratigraphy_to_dataframe(stratigraphy_input, aquifer_type="confined")
    if strat_df is None or len(strat_df) == 0:
        out["error"] = "No stratigraphy data."
        return out

    try:
        ti = recharge_target_layer_row_index(strat_df)
        depth_of_confined_unit = float(strat_df.iloc[0:ti]["thickness"].sum())
        Hmax = depth_of_confined_unit * 0.6 * 2.31
        kaq = float(strat_df.iloc[ti]["K"])
        B = float(strat_df.iloc[ti]["thickness"])
        Ss_col = float(strat_df.iloc[ti]["sy/ss"])
        transmissivity = kaq * B
        S = Ss_col * B
        if transmissivity <= 0 or S <= 0:
            out["error"] = "Transmissivity or storativity must be positive."
            return out

        Qmax = float(get_default("max_injection_Q_per_well"))
        q_cap = theis_drawdown_or_Q(
            Q_or_dh=Hmax,
            T=transmissivity,
            S=S,
            r=well_r_ft,
            t=t_days,
            compute_Q=True,
        )
        Q = float(min(Qmax, q_cap))

        x = np.linspace(-float(half_length_ft), float(half_length_ft), int(nx))
        y = np.linspace(-float(half_width_ft), float(half_width_ft), int(ny))
        X, Y = np.meshgrid(x, y, indexing="xy")
        R = np.sqrt(X**2 + Y**2)
        R = np.maximum(R, 0.1)

        def _dh(rr):
            return float(
                theis_drawdown_or_Q(
                    Q_or_dh=Q,
                    T=transmissivity,
                    S=S,
                    r=float(rr),
                    t=t_days,
                    compute_Q=False,
                )
            )

        drawdown = np.vectorize(_dh)(R)

        out.update(
            {
                "ok": True,
                "x": x,
                "y": y,
                "drawdown_ft": drawdown,
                "Q_ft3_per_day": Q,
                "transmissivity_ft2_per_day": transmissivity,
                "storativity": S,
                "time_days": float(t_days),
                "Hmax_ft": float(Hmax),
                "reference_radius_ft": float(well_r_ft),
                "confined_unit_thickness_above_target_ft": float(depth_of_confined_unit),
                "recharge_target_row_index": int(ti),
            }
        )
        return out
    except Exception as ex:
        out["error"] = str(ex)
        return out


def _unconfined_saturated_k_sy_b(strat_df, avg_gw_depth_bgs):
    """Layer-weighted K, Sy, and saturated thickness below the water table (feet)."""
    layer_depths = strat_df["thickness"].cumsum()
    saturated = layer_depths - float(avg_gw_depth_bgs)
    saturated = saturated[saturated > 0]
    if len(saturated) == 0:
        raise ValueError(
            "Water table is below the bottom of the stratigraphy column (no saturated column)."
        )
    b = float(saturated.sum())
    sat_thks = saturated.diff()
    sat_thks.iloc[0] = saturated.iloc[0]
    n = len(sat_thks)
    sy_s = strat_df.iloc[-n:]["sy/ss"]
    k_s = strat_df.iloc[-n:]["K"]
    denom = float(sat_thks.values.sum())
    k_mean = float((k_s.values * sat_thks.values).sum() / denom)
    sy_mean = float((sy_s.values * sat_thks.values).sum() / denom)
    if k_mean <= 0 or sy_mean <= 0 or b <= 0:
        raise ValueError("Saturated K, Sy, or thickness must be positive for unconfined mounding.")
    return k_mean, sy_mean, b


def build_unconfined_mounding_xy_plot_dict(
    stratigraphy_input,
    design_sizing_result,
    Lx,
    Ly,
    groundwater_rows,
    ground_surface_elevation_ft,
    # *,
    # op_gw_depth_ft=None,
    # t_days=50.0,
    # xy_pad_factor=1.35,
):
    """
    Plan-view mound (ft) on a grid using Hantush-type rectangular recharge
    (:func:`compute_mounding_grid`, same kernel as ``mymound.py`` / :func:`compute_spread_area`).

    Recharge half-size matches the MAR footprint (``half_length_ft``, ``half_width_ft``).
    Recharge strength ``w`` is set so the mound at the origin matches the unconfined
    head-rise target from average vs operational water-table depth (same spirit as
    :func:`compute_number_of_injection_wells` unconfined block).

    Returns
    -------
    dict
        ``ok``, ``drawdown_ft`` (mound increment, ft), matching ``x_grid`` and ``y_grid`` (2‑D);
        ``x`` / ``y`` are 1‑D center-line slices (for inspection only). Also ``w_ft_per_day``,
        ``k_mean``, ``sy_mean``, ``saturated_thickness_ft``, ``time_days``, etc.
    """
    out = {"ok": False}
    strat_df = dashboard_stratigraphy_to_dataframe(stratigraphy_input, aquifer_type="unconfined")
    if strat_df is None or len(strat_df) == 0:
        out["error"] = "No stratigraphy data."
        return out
    if groundwater_rows is None or (isinstance(groundwater_rows, list) and len(groundwater_rows) == 0):
        out["error"] = "Groundwater elevations are required for unconfined mounding."
        return out
    try:
        gs = float(ground_surface_elevation_ft)
    except (TypeError, ValueError):
        out["error"] = "Ground surface elevation is required for unconfined mounding."
        return out

    try:
        gw_df = pd.DataFrame(list(groundwater_rows))
        if "elevation" not in gw_df.columns:
            out["error"] = "Groundwater data must include an 'elevation' column."
            return out
        monthly_depth_bgs = (gs - gw_df["elevation"].astype(float).values).astype(float)
        avg_gw = float(np.mean(monthly_depth_bgs))

        # if op_gw_depth_ft is None:
        #     op_ft = max(0.0, avg_gw - 5.0)
        # else:
        #     op_ft = float(op_gw_depth_ft)

        # dh = avg_gw - op_ft
        # if dh <= 0:
        #     out["error"] = (
        #         "Average water-table depth must be greater than operational depth "
        #         "to build a positive mound (check operational water level)."
        #     )
        #     return out

        k_mean, sy_mean, b = _unconfined_saturated_k_sy_b(strat_df, avg_gw)
        #dh_corrected = dh - (dh * dh) / (2.0 * b) if b > 0 else dh
        #dh_target = max(float(dh_corrected), 1e-4)

        area = design_sizing_result["spread_area"]
        l_h = area**0.5
        a_h = l_h
        

        t = 50.0
        # s0 = float(
        #     mounding_integral_sum_at_point(0.0, 0.0, l_h, a_h, t, k_mean, b, sy_mean)
        # )
        # if s0 <= 1e-30:
        #     out["error"] = "Mounding kernel is zero at the origin (check time and aquifer parameters)."
        #     return out

        #v1 = k_mean * b / sy_mean
        w = design_sizing_result["infl_rate"]

        # pad = 1.
        # Lx = max(l_h * pad, l_h + 20.0)
        # Ly = max(a_h * pad, a_h + 20.0)

        x2, y2, h_inc = compute_mounding_grid(
            Lx,
            Ly,
            20,
            l_h,
            a_h,
            t,
            b,
            w,
            k_mean,
            sy_mean,
            0.0,
        )
        z_arr = np.asarray(h_inc, dtype=float)
        x_grid = np.asarray(x2, dtype=float)
        y_grid = np.asarray(y2, dtype=float)
        if z_arr.shape != x_grid.shape or z_arr.shape != y_grid.shape:
            out["error"] = (
                "Internal grid shape mismatch in unconfined mounding plot; "
                f"z {z_arr.shape}, x {x_grid.shape}, y {y_grid.shape}."
            )
            return out

        # 1-D slices for callers that only need axes (legacy Plotly path used full x_grid/y_grid).
        mid_r = z_arr.shape[0] // 2
        mid_c = z_arr.shape[1] // 2
        x1d = np.asarray(x2[mid_r, :], dtype=float)
        y1d = np.asarray(y2[:, mid_c], dtype=float)

        out.update(
            {
                "ok": True,
                "x": x1d,
                "y": y1d,
                "x_grid": x_grid,
                "y_grid": y_grid,
                "drawdown_ft": z_arr.astype(float),
                "w_ft_per_day": float(w),
                "k_mean_ft_per_day": float(k_mean),
                "sy_mean": float(sy_mean),
                "saturated_thickness_ft": float(b),
                "time_days": float(t),
                "half_length_ft": l_h,
                "half_width_ft": a_h,
                "avg_gw_depth_bgs_ft": float(avg_gw)
            }
        )
        return out
    except Exception as ex:
        out["error"] = str(ex)
        return out
  