"""
Format decision graph computation traces for the Detailed calculations workbook UI.

Developers can adjust wording by editing :func:`format_computation_log_entries` or the
``calculation`` strings appended in :meth:`mar_dss.base.DecisionGraph.evaluate_node`.
"""

from __future__ import annotations

from typing import Any


def safe_repr(value: Any, max_len: int = 240) -> str:
    """Short string for logs; truncates large arrays or nested structures."""
    try:
        if value is None:
            return "None"
        if isinstance(value, (int, float, bool)):
            return repr(value)
        if isinstance(value, str):
            s = value if len(value) <= max_len else value[: max_len - 3] + "..."
            return repr(s)
        if hasattr(value, "tolist"):
            try:
                arr = value.tolist()
                s = repr(arr)
            except Exception:
                s = repr(value)
        else:
            s = repr(value)
        if len(s) > max_len:
            return s[: max_len - 3] + "..."
        return s
    except Exception:
        return "<unprintable>"


def format_computation_log_entries(entries: list[dict[str, Any]] | None) -> str:
    """Plain-text workbook from trace entries (developer-editable layout)."""
    if not entries:
        return (
            "No calculation log yet. Run feasibility / integrated analysis from the "
            "Analysis tab so the decision graph is evaluated."
        )

    lines: list[str] = []
    lines.append("Detailed calculations workbook")
    lines.append("=" * 52)
    for i, e in enumerate(entries, 1):
        nid = e.get("node_id", "?")
        name = e.get("name", nid)
        kind = e.get("kind", "step")
        lines.append("")
        lines.append(f"{i}. [{kind}] {name}  (id: {nid})")
        if e.get("cached"):
            lines.append(f"    (cached) → {safe_repr(e.get('result'))}")
            continue
        if e.get("group"):
            lines.append(f"    Group: {e['group']}")
        ins = e.get("inputs")
        if ins is not None:
            lines.append("    Inputs:")
            if isinstance(ins, dict):
                for k, v in ins.items():
                    lines.append(f"      {k}: {safe_repr(v)}")
            else:
                lines.append(f"      {safe_repr(ins)}")
        calc = e.get("calculation")
        if calc:
            lines.append(f"    Calculation: {calc}")
        lines.append(f"    Result: {safe_repr(e.get('result'))}")

    lines.append("")
    lines.append(f"Total steps: {len(entries)}")
    return "\n".join(lines)
