"""
Initial hydrologic feasibility traffic-light classification from MAR hard/soft constraints.

Red: any hard constraint fails, or any soft constraint has response level 4.
Orange (Pass with Warnings): not red, and at least one soft response in {1, 2, 3}.
Green: otherwise (only acceptable / irrelevant soft responses, all hard pass).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Tuple

RESPONSE_LABELS = {
    -1: "Irrelevant",
    0: "Acceptable",
    1: "Acceptable with additional cost",
    2: "Warning",
    3: "Mitigation required",
    4: "Reject",
}

TrafficColor = Literal["green", "orange", "red"]

# Soft constraints use "environmental" for Water Quality screening items.
# Hard constraints use "water_quality" for the same domain.
HYDROGEOLOGIC_CONSTRAINT_TYPES = frozenset({"hydrogeologic"})


def _constraint_type(constraint: Dict[str, Any]) -> str:
    raw = constraint.get("type")
    if raw is None or str(raw).strip() == "":
        return "hydrogeologic"
    return str(raw).strip().lower()


def filter_constraints_by_type(
    constraints: Sequence[Dict[str, Any]],
    allowed_types: Optional[Iterable[str]],
) -> List[Dict[str, Any]]:
    """Keep constraints whose ``type`` is in *allowed_types* (case-insensitive).

    If *allowed_types* is None, return all constraints unchanged.
    Constraints without a ``type`` are treated as hydrogeologic.
    """
    if allowed_types is None:
        return list(constraints)
    allowed = {str(t).strip().lower() for t in allowed_types}
    return [c for c in constraints if _constraint_type(c) in allowed]


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
    *,
    allowed_types: Optional[Iterable[str]] = None,
) -> Tuple[TrafficColor, str]:
    """Run MAR constraint builders for one option and classify.

    Parameters
    ----------
    allowed_types:
        If set (e.g. ``HYDROGEOLOGIC_CONSTRAINT_TYPES``), only constraints whose
        ``type`` is in this set are used. Water quality / environmental items are
        omitted from the Initial Hydrogeologic Feasibility screen.
    """
    hc_list = filter_constraints_by_type(
        hard_constraints_fn(option), allowed_types
    )
    sc_list = filter_constraints_by_type(
        soft_constraints_fn(option), allowed_types
    )
    return classify_constraints_traffic_light(hc_list, sc_list)
