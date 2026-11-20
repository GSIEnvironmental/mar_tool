from typing import Any


def _strip_soft_penalty_prefix(detail: str) -> str:
    """Remove leading Warning:/Mitigation:/Cost:/Action:/Reject: tags from penalty text."""
    text = (detail or "").strip()
    lower = text.lower()
    for prefix in (
        "warning: data gap — ",
        "warning: data gap - ",
        "warning: data gap—",
        "warning: data gap-",
        "warning: data gap:",
        "warning: ",
        "mitigation: ",
        "cost: ",
        "action: ",
        "reject: ",
        "reject :: ",
    ):
        if lower.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def _format_soft_issue_message(sm: dict[str, Any]) -> str:
    """Build a specific warning/mitigation label from a soft metric.

    Distinguishes data-gap Unknown answers from confirmed findings (e.g.
    contamination) using the soft-constraint penalty text.
    """
    name = sm.get("name") or "Constraint"
    penalties = sm.get("penalty") or []
    detail = ""
    if isinstance(penalties, (list, tuple)) and penalties:
        first = penalties[0]
        detail = (first if isinstance(first, str) else str(first)).strip()
    elif isinstance(penalties, str):
        detail = penalties.strip()

    if not detail:
        return name

    detail_lower = detail.lower()
    cleaned = _strip_soft_penalty_prefix(detail)

    if "data gap" in detail_lower:
        # Ensure the label itself says "data gap" even if the body is long.
        if cleaned.lower().startswith("data gap"):
            return f"{name}: {cleaned}"
        return f"{name}: data gap — {cleaned}"

    # Confirmed contaminant findings: lead with contamination when the body says so.
    if any(token in detail_lower for token in ("contaminant", "contamination", "pollution")):
        return f"{name}: contamination — {cleaned}"

    return f"{name}: {cleaned}"


def _numeric_cost_penalty(sm: dict[str, Any]) -> float:
    """Return the dollar amount to add for a soft metric (non-numeric → 0).

    ``soft_constraints`` uses ``penalty`` for human-readable messages (often a
    ``list[str]``). Only real numbers (or a list/tuple of numbers) contribute to
    ``cost``; optional ``numeric_penalty`` / ``cost_penalty`` override when set.
    """
    for key in ("numeric_penalty", "cost_penalty"):
        if key in sm and sm[key] is not None:
            try:
                return float(sm[key])
            except (TypeError, ValueError):
                pass
    p = sm.get("penalty", 0)
    if isinstance(p, (int, float)) and not isinstance(p, bool):
        try:
            return float(p)
        except (TypeError, ValueError):
            return 0.0
    if isinstance(p, (list, tuple)):
        total = 0.0
        for x in p:
            if isinstance(x, (int, float)) and not isinstance(x, bool):
                try:
                    total += float(x)
                except (TypeError, ValueError):
                    continue
        return total
    return 0.0


class DecisionSupportSystem:
    """
    Generic rule-based Decision Support System (DSS).

    Features:
    - Hard-constraint feasibility screening
    - Soft-metric response logic (cost penalties, warnings, mitigations, rejection)
    - Benefit aggregation
    - Deterministic decision classification

    Response levels for soft metrics:
        0 = Normal
        1 = Cost penalty
        2 = Warning
        3 = Mitigation required
        4 = Reject
    """

    def __init__(
        self,
        hard_constraints: list[dict[str, bool]],
        soft_metrics: list[dict[str, Any]],
        benefit_metrics: list[dict[str, float]],
    ):
        """
        hard_constraints:
            [{ "name": str, "pass": bool }]

        soft_metrics:
            [{
                "name": str,
                "response": int,   # 0–4
                "penalty": float | list[str]   # optional dollar bump, else messages only
            }]

        benefit_metrics:
            [{
                "name": str,
                "value": float,    # normalized [0,1]
                "weight": float
            }]
        """
        self.hard_constraints = hard_constraints
        self.soft_metrics = soft_metrics
        self.benefit_metrics = benefit_metrics

    def evaluate(self, option) -> dict[str, Any]:
        """
        Evaluate a single alternative.

        option must define:
            option.base_cost
            option.data (dict-like)
        """

        # ---------- 1. Hard-constraint screening ----------
        for hc in self.hard_constraints:
            if not hc["pass"]:
                return {
                    "status": "Rejected",
                    "cost": 0.0,
                    "benefit_score": 0.0,
                    "warnings": [],
                    "mitigations": [],
                }

        # ---------- 2. Initialization ----------
        cost = float(option.base_cost)
        warnings = []
        mitigations = []

        # ---------- 3. Soft-metric evaluation ----------
        for sm in self.soft_metrics:
            level = sm["response"]

            # Skip irrelevant constraints (response = -1)
            if level == -1:
                continue

            # mandatory = False → behaves soft
            # mandatory = True → violation becomes hard rejection
            """
            Hard + acceptable	->allowed
            Hard + Warning	->Rejected
            Hard + Mitigation	-> Rejected
            Hard + Reject	-> Rejected
            Soft + Warning	Allowed
            Soft + Mitigation	Allowed
            Soft + Reject	rejected
            """

            # ---------- Promotion to hard constraint ----------
            if sm.get("hard", False) and level >= 2:
                return {
                    "status": "Rejected",
                    "cost": option.base_cost,
                    "benefit_score": 0.0,
                    "warnings": [],
                    "mitigations": [],
                }

            if level >= 1:
                cost += _numeric_cost_penalty(sm)

            if level == 2:
                warnings.append(_format_soft_issue_message(sm))

            elif level == 3:
                mitigations.append(_format_soft_issue_message(sm))

            elif level == 4:
                return {
                    "status": "Rejected",
                    "cost": cost,
                    "benefit_score": 0.0,
                    "warnings": warnings,
                    "mitigations": mitigations,
                }

        # ---------- 4. Benefit aggregation ----------
        benefit_score = sum(bm["weight"] * bm["value"] for bm in self.benefit_metrics)

        # ---------- 5. Decision classification ----------
        if mitigations:
            status = "Conditionally Recommended"
        elif warnings:
            status = "Recommended with Warnings"
        else:
            status = "Recommended"

        return {
            "status": status,
            "cost": cost,
            "benefit_score": benefit_score,
            "warnings": warnings,
            "mitigations": mitigations,
        }

    def _get_constraint_points(self, response_level: int) -> float:
        """Convert response level to points.

        Point system:
        - 0 (Acceptable): 10 points
        - 1 (Cost penalty): 9 points
        - 2 (Warning): 8 points
        - 3 (Mitigation): 7 points
        - 4 (Reject): 0 points
        """
        point_map = {
            0: 10.0,  # Acceptable
            1: 9.0,  # Cost penalty
            2: 8.0,  # Warning
            3: 7.0,  # Mitigation
            4: 0.0,  # Reject
        }
        return point_map.get(response_level, 0.0)

    def calculate_type_scores(self) -> dict[str, float]:
        """
        Calculate type-specific scores for the option.

        Scoring system:
        - Constraints: 10 points (acceptable), 9 (cost), 8 (warning), 7 (mitigation), 0 (reject)
        - Benefits: Convert percentage to points (100% = 10 points)
        - Score = (actual_points / ideal_points) × 100%

        Hard constraints in MAR DSS are physical / hydrogeologic feasibility checks only
        (see ``mar.hard_constraints``). If any fail, the option is rejected in
        :meth:`evaluate`, but environmental scores are still derived from soft metrics
        so dashboards (e.g. spider plots) can show that dimension.
        In that case only ``hydrogeologic`` is forced to 0.0 here.
        Regulation questionnaire scoring is not included (informational only).

        Returns:
            {
                "hydrogeologic": float (0-100),
                "environmental": float (0-100),
            }
        """
        hard_fail = any(not hc.get("pass", True) for hc in self.hard_constraints)

        # Group soft constraints by type (regulation intentionally omitted)
        type_constraints = {
            "hydrogeologic": [],
            "environmental": [],
        }

        for sm in self.soft_metrics:
            constraint_type = sm.get("type", "").lower()

            if constraint_type in type_constraints:
                response_level = sm.get("response", 0)
                # Skip irrelevant constraints (response = -1) - they should not be part of score calculation
                if response_level == -1:
                    continue
                points = self._get_constraint_points(response_level)
                type_constraints[constraint_type].append(points)

        # Step 3: Calculate benefit points
        # Benefits apply to all types
        benefit_points = []
        for bm in self.benefit_metrics:
            benefit_value = bm.get("value", 0.0)  # Normalized [0, 1]
            points = benefit_value * 10.0
            benefit_points.append(points)

        # Step 4: Calculate scores for each type
        scores = {}
        num_benefits = len(self.benefit_metrics)

        for constraint_type, constraint_points_list in type_constraints.items():
            num_constraints = len(constraint_points_list)
            actual_constraint_points = sum(constraint_points_list)
            actual_benefit_points = sum(benefit_points)

            # Calculate ideal points
            ideal_constraint_points = num_constraints * 10.0
            ideal_benefit_points = num_benefits * 10.0
            ideal_total = ideal_constraint_points + ideal_benefit_points

            # Calculate actual points
            actual_total = actual_constraint_points + actual_benefit_points

            # Calculate score
            if ideal_total > 0:
                type_score = (actual_total / ideal_total) * 100.0
            else:
                # No constraints or benefits - default to 100%
                type_score = 100.0

            # Clamp to [0, 100]
            scores[constraint_type] = max(0.0, min(100.0, type_score))

        if hard_fail:
            scores["hydrogeologic"] = 0.0

        return scores
