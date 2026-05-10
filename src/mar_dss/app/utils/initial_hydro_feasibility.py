"""
Initial hydrologic feasibility traffic-light classification from MAR hard/soft constraints.

Red: any hard constraint fails, or any soft constraint has response level 4.
Orange (Pass with Warnings): not red, and at least one soft response in {1, 2, 3}.
Green: otherwise (only acceptable / irrelevant soft responses, all hard pass).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Tuple

RESPONSE_LABELS = {
    -1: "Irrelevant",
    0: "Acceptable",
    1: "Acceptable with additional cost",
    2: "Warning",
    3: "Mitigation required",
    4: "Reject",
}

TrafficColor = Literal["green", "orange", "red"]


def classify_constraints_traffic_light(
    hard_list: List[Dict[str, Any]],
    soft_list: List[Dict[str, Any]],
) -> Tuple[TrafficColor, str]:
    """
    Returns (color, short status line).

    Orange reporting uses the soft constraint with the highest response among {1,2,3};
    ties pick any one.
    """
    failed_hard = [hc for hc in hard_list if not hc.get("pass", True)]
    if failed_hard:
        hc = failed_hard[0]
        detail = hc.get("why") or hc.get("name") or "Hard constraint failed"
        return ("red", f"Fail - {detail}")

    soft_relevant = [
        sm
        for sm in soft_list
        if sm.get("response") is not None and sm.get("response") != -1
    ]

    reject_soft = [sm for sm in soft_relevant if sm.get("response") == 4]
    if reject_soft:
        sm = reject_soft[0]
        penalties = sm.get("penalty") or []
        if penalties:
            detail = penalties[0] if isinstance(penalties[0], str) else str(penalties[0])
        else:
            detail = sm.get("name") or "Soft reject"
        return ("red", f"Fail - {detail}")

    warn_soft = [
        sm
        for sm in soft_list
        if sm.get("response") in (1, 2, 3)
    ]
    if warn_soft:
        max_r = max(sm["response"] for sm in warn_soft)
        worst = [sm for sm in warn_soft if sm.get("response") == max_r]
        chosen = worst[0]
        label = RESPONSE_LABELS.get(max_r, str(max_r))
        name = chosen.get("name") or "Constraint"
        return (
            "orange",
            f"Pass with Warnings - {name}: {label}",
        )

    return ("green", "Pass")


def evaluate_option_traffic_light(
    option: Any,
    hard_constraints_fn,
    soft_constraints_fn,
) -> Tuple[TrafficColor, str]:
    """Run MAR constraint builders for one option and classify."""
    hc_list = hard_constraints_fn(option)
    sc_list = soft_constraints_fn(option)
    return classify_constraints_traffic_light(hc_list, sc_list)
