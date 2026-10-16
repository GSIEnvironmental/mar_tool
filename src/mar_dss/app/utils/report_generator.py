"""Build and save the MAR prefeasibility summary HTML and PDF reports."""

from __future__ import annotations

import base64
import html
import io
import math
import re
from datetime import datetime
from typing import Any, Literal

import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.callbacks.feasibilities_callbacks import (
    MAR_ENGINEERING_OPTIONS,
    _categorize_options,
    _collect_engineering_option_economics,
    _format_currency,
    _format_per_acre_ft,
    _format_volume_acre_ft,
)
from mar_dss.app.components.decision_interpretation_tab import _get_status_interpretation
from mar_dss.app.components.hydro_tab import (
    GROUNDWATER_MONTH_NAMES,
    normalize_groundwater_data,
    normalize_stratigraphy_list_from_raw,
)
from mar_dss.app.components.overview_tab import get_overview_map_basemap
from mar_dss.app.components.water_source_tab import (
    WATER_SOURCE_LABELS,
    build_water_source_location_map_figure,
    ensure_water_source_site_coordinates,
    _haversine_miles,
)

ReportFormat = Literal["html", "pdf"]

_RESPONSE_LABELS = {
    0: "Acceptable",
    1: "Acceptable with additional Cost",
    2: "Warning",
    3: "Mitigation",
    4: "Reject",
}

_INPUT_SUMMARY_FIELDS = (
    ("project_name", "Project Name"),
    ("project_location", "Project Location"),
    ("analysis_date", "Analysis Date"),
    ("mar_purpose", "MAR Purpose"),
    ("land_use", "Land Use"),
    ("max_available_area", "Max Available Area (acres)"),
    ("ground_surface_slope", "Ground Surface Slope"),
    ("total_runoff_ft3", "Design Event Flow (ft³/day)"),
    ("design_events_per_month", "Design Events per Month"),
    ("fraction_flow_capture", "Fraction Flow Capture (fixed at 1)"),
    ("conveyance_method", "Conveyance Method (source → recharge)"),
    ("distance_to_sediment", "Conveyance Length (miles, source → recharge)"),
    ("distance_to_storage_pond_ft", "Distance to Storage Pond (ft)"),
    ("max_infiltration_area", "Max Infiltration Area"),
    ("wq_source_contaminants", "Source Water Contaminants"),
    ("wq_source_turbidity", "Source Water Turbidity"),
    ("wq_vadose_impacted", "Vadose / Unsaturated Zone Impacted"),
    ("wq_aquifer_anthropogenic", "Target Aquifer Anthropogenic Contaminants"),
    ("wq_aquifer_natural", "Target Aquifer Naturally Occurring Contaminants"),
)

_MONTH_LABELS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

_EXEC_SUMMARY_INTRO = (
    "The table below ranks MAR engineering options using DSS analysis results. "
    "Feasible options (Pass and Conditional) are listed first by benefit score; "
    "not-feasible options follow. Capital cost, annual recharge volume, and capital cost "
    "per acre-foot recharged are shown for each option."
)

_JUSTIFICATION_INTRO = (
    "Detailed DSS decision interpretation for each engineering option, "
    "including status rationale, warnings, mitigations, and constraint evaluation."
)

_WATER_SOURCE_INTRO = (
    "Water source configuration and site locations from the Water Source tab, "
    "including source and recharge coordinates and monthly flow estimates."
)

_HYDROGEOLOGY_INTRO = (
    "Hydrogeologic settings from the Hydrogeology tab, including aquifer type, "
    "stratigraphy layers, and seasonal groundwater elevations."
)

_INPUT_SUMMARY_INTRO = (
    "Additional project inputs entered across MAR DSS tabs used in this prefeasibility analysis."
)


def _esc(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _format_input_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "—"
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        return f"{value:,.4g}"
    if isinstance(value, (list, tuple)):
        parts = [_format_input_value(v) for v in value if v is not None]
        return ", ".join(p for p in parts if p and p != "—") or "—"
    if isinstance(value, dict):
        return ", ".join(f"{k}: {_format_input_value(v)}" for k, v in value.items())
    text = str(value).strip()
    return text if text else "—"


def _location_name() -> str:
    loc = dash_storage.get_data("project_location")
    if loc is None:
        return "Unspecified Location"
    text = str(loc).strip()
    return text if text else "Unspecified Location"


def _default_report_filename(report_format: ReportFormat = "html") -> str:
    loc = _location_name()
    slug = re.sub(r"[^\w\-]+", "_", loc)[:40].strip("_") or "Project"
    stamp = datetime.now().strftime("%Y%m%d")
    ext = "pdf" if report_format == "pdf" else "html"
    return f"MAR_Prefeasibility_Report_{slug}_{stamp}.{ext}"


def _build_ranked_executive_rows(results: dict, filters: dict) -> list[dict]:
    categorized = _categorize_options(results, filters)
    economics = {row["name"]: row for row in _collect_engineering_option_economics()}

    def _row(name: str, tier: str) -> dict:
        result = results.get(name, {})
        econ = economics.get(name, {})
        benefit = float(result.get("benefit_score", 0.0) or 0.0) * 100
        return {
            "name": name,
            "tier": tier,
            "status": result.get("status", "Unknown"),
            "benefit_score": benefit,
            "capital": econ.get("capital", 0.0),
            "acre_ft": econ.get("acre_ft", 0.0),
            "capital_per_acre_ft": econ.get("capital_per_acre_ft"),
        }

    feasible: list[dict] = []
    for opt in categorized.get("recommended", []):
        feasible.append(_row(opt["name"], "Pass"))
    for opt in categorized.get("conditional", []):
        feasible.append(_row(opt["name"], "Conditional"))
    feasible.sort(key=lambda r: r["benefit_score"], reverse=True)

    rejected = [_row(opt["name"], "Not feasible") for opt in categorized.get("rejected", [])]

    ranked = feasible + rejected
    for idx, row in enumerate(ranked, start=1):
        row["rank"] = idx
    return ranked


def _format_option_justification(option_name: str, result: dict, filters: dict) -> str:
    status = result.get("status", "Unknown")
    benefit_score = float(result.get("benefit_score", 0.0) or 0.0) * 100
    cost = result.get("cost", 0)
    warnings = result.get("warnings", []) or []
    mitigations = result.get("mitigations", []) or []

    lines = [
        f"Option: {option_name}",
        f"Status: {status}",
        f"Benefit Score: {benefit_score:.1f}%",
        "",
        "Status Interpretation",
        _get_status_interpretation(status, warnings, mitigations),
        "",
    ]

    if isinstance(cost, (int, float)) and cost:
        lines.extend([f"Total Evaluated Cost: ${float(cost):,.0f}", ""])
    elif isinstance(cost, list) and cost:
        lines.extend(["Cost Items:"] + [f"  • {c}" for c in cost] + [""])

    if warnings:
        lines.append("Warnings")
        lines.extend(f"  • {w}" for w in warnings)
        lines.append("")

    if mitigations:
        lines.append("Required Mitigations")
        lines.extend(f"  • {m}" for m in mitigations)
        lines.append("")

    filter_data = filters.get(option_name, {}) if filters else {}
    hard_constraints = filter_data.get("hard", []) or []
    soft_constraints = filter_data.get("soft", []) or []

    if hard_constraints:
        lines.append("Hard Constraints")
        for hc in hard_constraints:
            name = hc.get("name", "Unknown")
            passed = hc.get("pass", False)
            why = hc.get("why", "")
            status_txt = "Pass" if passed else "Fail"
            detail = f" — {why}" if why else ""
            lines.append(f"  • {name}: {status_txt}{detail}")
        lines.append("")

    if soft_constraints:
        lines.append("Soft Constraints")
        for sc in soft_constraints:
            response = sc.get("response", 0)
            if response == -1:
                continue
            name = sc.get("name", "Unknown")
            label = _RESPONSE_LABELS.get(response, "Unknown")
            penalty = sc.get("penalty", [])
            lines.append(f"  • {name}: {label}")
            if isinstance(penalty, list):
                for p in penalty:
                    lines.append(f"      - {p}")
            elif penalty:
                lines.append(f"      - {penalty}")
        lines.append("")

    benefits = filter_data.get("benefits", []) or []
    if benefits:
        lines.append("Benefits")
        for benefit in benefits:
            bname = benefit.get("name", "Unknown")
            value = float(benefit.get("value", 0.0) or 0.0) * 100
            weight = benefit.get("weight", 0.0)
            lines.append(f"  • {bname}: {value:.1f}% (weight {weight})")
        lines.append("")

    return "\n".join(lines).strip()


def _collect_input_summary_rows() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for key, label in _INPUT_SUMMARY_FIELDS:
        value = dash_storage.get_data(key)
        if value is None:
            continue
        formatted = _format_input_value(value)
        if formatted == "—":
            continue
        rows.append((label, formatted))
    return rows


def _water_source_label(raw: Any) -> str:
    key = str(raw or "surface_water_sources").strip()
    return WATER_SOURCE_LABELS.get(key, key.replace("_", " ").title())


def _aquifer_type_label(raw: Any) -> str:
    text = str(raw or "unconfined").strip()
    return text.replace("-", " ").replace("_", " ").title()


def _append_storage_row(
    rows: list[tuple[str, str]],
    label: str,
    key: str,
) -> None:
    value = dash_storage.get_data(key)
    if value is None:
        return
    formatted = _format_input_value(value)
    if formatted == "—":
        return
    rows.append((label, formatted))


def _collect_water_source_summary_rows() -> list[tuple[str, str]]:
    slat, slon, rlat, rlon = ensure_water_source_site_coordinates()
    dist_mi = _haversine_miles(slat, slon, rlat, rlon)
    rows = [
        ("Water Source", _water_source_label(dash_storage.get_data("water_source"))),
        ("Source Site Coordinate (Lat, Lon)", f"{slat:.6f}, {slon:.6f}"),
        ("Recharge Site Coordinate (Lat, Lon)", f"{rlat:.6f}, {rlon:.6f}"),
        (
            "Distance from Water Source to MAR Project Site (mi)",
            f"{dist_mi:.2f}",
        ),
    ]
    monthly = dash_storage.get_data("monthly_flow")
    if isinstance(monthly, list) and len(monthly) == 12:
        try:
            flows = [float(v or 0) for v in monthly]
            annual = sum(flows)
            rows.append(("Total Annual Flow (ft³/year)", f"{annual:,.0f}"))
        except (TypeError, ValueError):
            pass
    return rows


def _collect_water_source_flow_rows() -> list[list[str]]:
    monthly = dash_storage.get_data("monthly_flow")
    if not isinstance(monthly, list) or len(monthly) != 12:
        return []
    rows: list[list[str]] = []
    for month, value in zip(_MONTH_LABELS, monthly):
        try:
            flow = float(value or 0)
            rows.append([month, f"{flow:,.0f}"])
        except (TypeError, ValueError):
            rows.append([month, "—"])
    return rows


def _collect_hydrogeology_summary_rows() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    aq_type = dash_storage.get_data("aq_type")
    if aq_type is not None:
        rows.append(("Aquifer Type", _aquifer_type_label(aq_type)))
    for label, key in (
        ("Ground Surface Elevation (ft)", "ground_surface_elevation"),
        ("Max MAR Storage Depth (ft)", "max_mar_storage_depth"),
        ("Max Dry Well Depth (ft)", "max_dry_well_depth_ft"),
        ("Confined Aquifer Head (ft)", "confined_aquifer_head_ft"),
        ("Aquitard Conductivity (ft/day)", "aquitard_conductivity_ft_day"),
        ("Extension Length (ft)", "extension_length"),
        ("Extension Width (ft)", "extension_width"),
        ("Extension Rotation (deg)", "extension_rotation"),
    ):
        _append_storage_row(rows, label, key)
    return rows


def _collect_stratigraphy_table_rows() -> list[list[str]]:
    raw = dash_storage.get_data("stratigraphy_data")
    layers = normalize_stratigraphy_list_from_raw(raw)
    if not layers:
        return []
    rows: list[list[str]] = []
    for layer in layers:
        recharge = "Yes" if layer.get("recharge_target") else "No"
        rows.append([
            _format_input_value(layer.get("layer")),
            _format_input_value(layer.get("thickness")),
            _format_input_value(layer.get("conductivity")),
            _format_input_value(layer.get("storage")),
            _format_input_value(layer.get("yield")),
            recharge,
        ])
    return rows


def _collect_groundwater_table_rows() -> list[list[str]]:
    raw = dash_storage.get_data("groundwater_data")
    data = normalize_groundwater_data(raw if raw else [])
    rows: list[list[str]] = []
    for entry in data:
        month = entry.get("month", "")
        elevation = entry.get("elevation")
        rows.append([str(month), _format_input_value(elevation)])
    if not rows:
        for month in GROUNDWATER_MONTH_NAMES:
            rows.append([month, "—"])
    return rows


def _build_water_source_map_png() -> bytes | None:
    """Render the Water Source tab location map as PNG bytes."""
    try:
        fig = build_water_source_location_map_figure(get_overview_map_basemap())
        fig.update_layout(width=900, height=500, autosize=False)
        return fig.to_image(format="png")
    except Exception:
        return None


def _water_source_map_html(*, compact: bool = False) -> str:
    png = _build_water_source_map_png()
    if not png:
        return (
            "<p class='lead map-unavailable'>Project map could not be generated. "
            "Open the Water Source tab and verify map settings, then regenerate the report.</p>"
        )
    encoded = base64.b64encode(png).decode("ascii")
    css_class = "report-map report-map-compact" if compact else "report-map"
    return (
        f'<img class="{css_class}" src="data:image/png;base64,{encoded}" '
        'alt="Water source and recharge site map"/>'
    )


def _pdf_water_source_map_flowable(width: float, height: float, body_style) -> Any:
    from reportlab.platypus import Image

    png = _build_water_source_map_png()
    if png:
        return Image(io.BytesIO(png), width=width, height=height)
    return _pdf_paragraph(
        "Project map could not be generated. Open the Water Source tab "
        "and verify map settings, then regenerate the report.",
        body_style,
    )


def _html_report_header_section(project_name: str, generated_at: str) -> str:
    return (
        "<div class='report-header-row'>"
        "<div class='report-meta'>"
        f"<div><strong>Project:</strong> {_esc(project_name)}</div>"
        f"<div><strong>Generated:</strong> {_esc(generated_at)}</div>"
        "</div>"
        f"<div class='report-header-map'>{_water_source_map_html(compact=True)}"
        "<p class='map-caption'>Source and recharge sites (Water Source tab)</p>"
        "</div>"
        "</div>"
    )


def _html_executive_summary_section(data: dict[str, Any]) -> str:
    exec_table = _html_table(
        [
            "Rank",
            "Engineering Option",
            "DSS Status",
            "Feasibility Tier",
            "Capital Cost",
            "Annual Recharge Volume",
            "Capital Cost / Acre-Ft Recharged",
        ],
        data["exec_table_rows"],
    )
    return (
        "<h2>Executive Summary</h2>"
        f"<p class='lead'>{_esc(_EXEC_SUMMARY_INTRO)}</p>"
        f"{exec_table}"
    )


def _pdf_label_value_paragraph(label: str, value: str, style) -> Any:
    from reportlab.platypus import Paragraph

    safe = f"<b>{html.escape(label)}:</b> {html.escape(str(value))}"
    return Paragraph(safe, style)


def _pdf_report_header_section(
    story: list[Any],
    data: dict[str, Any],
    *,
    meta_style,
    body_style,
) -> None:
    from reportlab.lib.units import inch
    from reportlab.platypus import Spacer, Table, TableStyle

    meta_table = Table(
        [
            [_pdf_label_value_paragraph("Project", data["project_name"], meta_style)],
            [_pdf_label_value_paragraph("Generated", data["generated_at"], meta_style)],
        ],
        colWidths=[3.4 * inch],
    )
    meta_table.setStyle(
        TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )

    map_width = 3.1 * inch
    map_height = 1.72 * inch
    map_flowable = _pdf_water_source_map_flowable(map_width, map_height, body_style)

    header_row = Table(
        [[meta_table, map_flowable]],
        colWidths=[3.4 * inch, map_width],
    )
    header_row.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ])
    )
    story.append(header_row)
    story.append(Spacer(1, 0.2 * inch))


def _pdf_executive_summary_section(
    story: list[Any],
    data: dict[str, Any],
    *,
    heading_style,
    body_style,
) -> None:
    from reportlab.lib.units import inch
    from reportlab.platypus import Spacer, Table, TableStyle

    story.append(_pdf_paragraph("Executive Summary", heading_style))
    story.append(_pdf_paragraph(_EXEC_SUMMARY_INTRO, body_style))

    exec_headers = [
        "Rank",
        "Engineering Option",
        "DSS Status",
        "Feasibility Tier",
        "Capital Cost",
        "Annual Recharge Volume",
        "Capital Cost / Acre-Ft",
    ]
    exec_table = Table([exec_headers, *data["exec_table_rows"]], repeatRows=1)
    exec_table.setStyle(TableStyle(_pdf_table_style()))
    story.append(exec_table)
    story.append(Spacer(1, 0.2 * inch))


def _gather_report_data() -> dict[str, Any]:
    """Collect shared report content from dash_storage and DSS results."""
    location = _location_name()
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    project_name = _format_input_value(dash_storage.get_data("project_name"))

    dss_results = dash_storage.get_data("dss_results")
    if dss_results is None or not getattr(dss_results, "results", None):
        raise ValueError(
            "No DSS analysis results found. Run feasibility analysis on the Analysis tab first."
        )

    results = dss_results.results
    filters = getattr(dss_results, "filters", {}) or {}

    exec_rows = _build_ranked_executive_rows(results, filters)
    exec_table_rows = []
    for row in exec_rows:
        exec_table_rows.append([
            str(row["rank"]),
            row["name"],
            row["status"],
            row["tier"],
            _format_currency(row["capital"]) if row["capital"] else "—",
            _format_volume_acre_ft(row["acre_ft"]),
            _format_per_acre_ft(row["capital_per_acre_ft"]),
        ])

    justification_blocks: list[tuple[str, str]] = []
    for option_name in MAR_ENGINEERING_OPTIONS:
        if option_name not in results:
            continue
        text = _format_option_justification(option_name, results[option_name], filters)
        justification_blocks.append((option_name, text))

    input_rows = _collect_input_summary_rows()
    if not input_rows:
        input_rows = [("Note", "No additional project inputs were stored.")]

    water_source_rows = _collect_water_source_summary_rows()
    water_source_flow_rows = _collect_water_source_flow_rows()
    hydro_summary_rows = _collect_hydrogeology_summary_rows()
    stratigraphy_rows = _collect_stratigraphy_table_rows()
    groundwater_rows = _collect_groundwater_table_rows()

    return {
        "location": location,
        "generated_at": generated_at,
        "project_name": project_name,
        "exec_table_rows": exec_table_rows,
        "justification_blocks": justification_blocks,
        "input_rows": input_rows,
        "water_source_rows": water_source_rows,
        "water_source_flow_rows": water_source_flow_rows,
        "hydro_summary_rows": hydro_summary_rows,
        "stratigraphy_rows": stratigraphy_rows,
        "groundwater_rows": groundwater_rows,
    }


def _html_table(headers: list[str], body_rows: list[list[str]]) -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body_parts = []
    for row in body_rows:
        cells = "".join(f"<td>{_esc(cell)}</td>" for cell in row)
        body_parts.append(f"<tr>{cells}</tr>")
    body = "".join(body_parts)
    return f'<table class="report-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def build_prefeasibility_report_html() -> str:
    """Assemble the full HTML report from current dash_storage and DSS results."""
    data = _gather_report_data()
    location = data["location"]
    generated_at = data["generated_at"]
    project_name = data["project_name"]
    justification_blocks = data["justification_blocks"]
    input_rows = data["input_rows"]

    html_justifications = []
    for option_name, text in justification_blocks:
        html_justifications.append(
            f'<div class="justification-block"><h3>{_esc(option_name)}</h3>'
            f'<pre class="justification-text">{_esc(text)}</pre></div>'
        )

    parts = [
        "<!DOCTYPE html>",
        "<html lang='en'><head>",
        "<meta charset='utf-8'/>",
        f"<title>Summary Report for Prefeasibility Analysis at {_esc(location)}</title>",
        "<style>",
        "body { font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; color: #212529; line-height: 1.5; }",
        "h1 { color: #0d6efd; border-bottom: 3px solid #0d6efd; padding-bottom: 8px; }",
        "h2 { color: #0d6efd; margin-top: 32px; }",
        "h3 { color: #495057; margin-top: 16px; }",
        ".report-header-row { display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start; "
        "margin: 0 0 28px; }",
        ".report-meta { flex: 1 1 240px; color: #6c757d; font-size: 15px; line-height: 1.8; }",
        ".report-meta strong { color: #495057; }",
        ".report-header-map { flex: 1 1 320px; max-width: 420px; }",
        ".report-table { width: 100%; border-collapse: collapse; margin: 16px 0 24px; font-size: 14px; }",
        ".report-table th { background: #0d6efd; color: #fff; text-align: left; padding: 10px; }",
        ".report-table td { border: 1px solid #dee2e6; padding: 8px 10px; vertical-align: top; }",
        ".report-table tr:nth-child(even) td { background: #f8f9fa; }",
        ".justification-block { margin-bottom: 24px; }",
        ".justification-text { white-space: pre-wrap; background: #f8f9fa; border: 1px solid #dee2e6; "
        "border-radius: 4px; padding: 12px; font-family: Consolas, monospace; font-size: 13px; }",
        "p.lead { font-size: 15px; }",
        ".report-map { max-width: 100%; height: auto; border: 1px solid #dee2e6; border-radius: 4px; }",
        ".report-map-compact { width: 100%; }",
        ".map-caption { font-size: 12px; color: #6c757d; margin: 8px 0 0; text-align: center; }",
        ".map-unavailable { color: #6c757d; font-style: italic; }",
        "</style>",
        "</head><body>",
        f"<h1>Summary Report for Prefeasibility Analysis at {_esc(location)}</h1>",
        _html_report_header_section(project_name, generated_at),
        _html_executive_summary_section(data),
        "<h2>Feasibility Analysis Justification</h2>",
        f"<p class='lead'>{_esc(_JUSTIFICATION_INTRO)}</p>",
        "".join(html_justifications),
        "<h2>Water Source</h2>",
        f"<p class='lead'>{_esc(_WATER_SOURCE_INTRO)}</p>",
        _html_table(["Parameter", "Value"], [[a, b] for a, b in data["water_source_rows"]]),
        (
            _html_table(["Month", "Flow (ft³/month)"], data["water_source_flow_rows"])
            if data["water_source_flow_rows"]
            else ""
        ),
        "<h2>Hydrogeology</h2>",
        f"<p class='lead'>{_esc(_HYDROGEOLOGY_INTRO)}</p>",
        _html_table(["Parameter", "Value"], [[a, b] for a, b in data["hydro_summary_rows"]]),
        "<h3>Stratigraphy Layers</h3>",
        (
            _html_table(
                [
                    "Layer",
                    "Thickness (ft)",
                    "Hydraulic Conductivity",
                    "Storage Term",
                    "Specific Yield",
                    "Recharge Target",
                ],
                data["stratigraphy_rows"],
            )
            if data["stratigraphy_rows"]
            else f"<p class='lead'>{_esc('No stratigraphy layers stored.')}</p>"
        ),
        "<h3>Seasonal Groundwater Elevations</h3>",
        _html_table(["Month", "Elevation (ft)"], data["groundwater_rows"]),
        "<h2>Project Input Summary</h2>",
        f"<p class='lead'>{_esc(_INPUT_SUMMARY_INTRO)}</p>",
        _html_table(["Parameter", "Value"], [[a, b] for a, b in input_rows]),
        "</body></html>",
    ]
    return "\n".join(parts)


def _pdf_table_style() -> list[tuple]:
    from reportlab.lib import colors

    return [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]


def _pdf_paragraph(text: str, style) -> Any:
    from reportlab.platypus import Paragraph

    safe = html.escape(str(text)).replace("\n", "<br/>")
    return Paragraph(safe, style)


def build_prefeasibility_report_pdf(destination_path: str) -> str:
    """Write the PDF report to ``destination_path`` and return the path."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

    data = _gather_report_data()
    path = str(destination_path).strip()
    if not path:
        raise ValueError("Report destination path is empty.")
    if not path.lower().endswith(".pdf"):
        path = f"{path}.pdf"

    doc = SimpleDocTemplate(
        path,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title=f"Summary Report for Prefeasibility Analysis at {data['location']}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor("#0d6efd"),
        spaceAfter=12,
        alignment=TA_LEFT,
    )
    heading_style = ParagraphStyle(
        "ReportHeading",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=colors.HexColor("#0d6efd"),
        spaceBefore=18,
        spaceAfter=8,
        alignment=TA_LEFT,
    )
    subheading_style = ParagraphStyle(
        "ReportSubheading",
        parent=styles["Heading3"],
        fontSize=11,
        textColor=colors.HexColor("#495057"),
        spaceBefore=12,
        spaceAfter=6,
        alignment=TA_LEFT,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        spaceAfter=8,
        alignment=TA_LEFT,
    )
    meta_style = ParagraphStyle(
        "ReportMeta",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#6c757d"),
        spaceAfter=4,
        alignment=TA_LEFT,
    )

    story: list[Any] = []
    location = data["location"]
    story.append(_pdf_paragraph(f"Summary Report for Prefeasibility Analysis at {location}", title_style))
    _pdf_report_header_section(
        story,
        data,
        meta_style=meta_style,
        body_style=body_style,
    )

    _pdf_executive_summary_section(
        story,
        data,
        heading_style=heading_style,
        body_style=body_style,
    )

    story.append(_pdf_paragraph("Feasibility Analysis Justification", heading_style))
    story.append(_pdf_paragraph(_JUSTIFICATION_INTRO, body_style))
    for option_name, text in data["justification_blocks"]:
        story.append(_pdf_paragraph(option_name, subheading_style))
        story.append(Preformatted(text, body_style, maxLineLength=120))
        story.append(Spacer(1, 0.1 * inch))

    story.append(_pdf_paragraph("Water Source", heading_style))
    story.append(_pdf_paragraph(_WATER_SOURCE_INTRO, body_style))
    ws_table = Table([["Parameter", "Value"], *list(data["water_source_rows"])], repeatRows=1)
    ws_table.setStyle(TableStyle(_pdf_table_style()))
    story.append(ws_table)
    if data["water_source_flow_rows"]:
        story.append(Spacer(1, 0.1 * inch))
        flow_table = Table(
            [["Month", "Flow (ft³/month)"], *data["water_source_flow_rows"]],
            repeatRows=1,
        )
        flow_table.setStyle(TableStyle(_pdf_table_style()))
        story.append(flow_table)
    story.append(Spacer(1, 0.15 * inch))

    story.append(_pdf_paragraph("Hydrogeology", heading_style))
    story.append(_pdf_paragraph(_HYDROGEOLOGY_INTRO, body_style))
    if data["hydro_summary_rows"]:
        hydro_table = Table([["Parameter", "Value"], *list(data["hydro_summary_rows"])], repeatRows=1)
        hydro_table.setStyle(TableStyle(_pdf_table_style()))
        story.append(hydro_table)
        story.append(Spacer(1, 0.1 * inch))
    story.append(_pdf_paragraph("Stratigraphy Layers", subheading_style))
    if data["stratigraphy_rows"]:
        strat_table = Table(
            [
                [
                    "Layer",
                    "Thickness (ft)",
                    "Hydraulic Conductivity",
                    "Storage Term",
                    "Specific Yield",
                    "Recharge Target",
                ],
                *data["stratigraphy_rows"],
            ],
            repeatRows=1,
        )
        strat_table.setStyle(TableStyle(_pdf_table_style()))
        story.append(strat_table)
    else:
        story.append(_pdf_paragraph("No stratigraphy layers stored.", body_style))
    story.append(Spacer(1, 0.1 * inch))
    story.append(_pdf_paragraph("Seasonal Groundwater Elevations", subheading_style))
    gw_table = Table([["Month", "Elevation (ft)"], *data["groundwater_rows"]], repeatRows=1)
    gw_table.setStyle(TableStyle(_pdf_table_style()))
    story.append(gw_table)
    story.append(Spacer(1, 0.15 * inch))

    story.append(_pdf_paragraph("Project Input Summary", heading_style))
    story.append(_pdf_paragraph(_INPUT_SUMMARY_INTRO, body_style))
    input_table = Table([["Parameter", "Value"], *list(data["input_rows"])], repeatRows=1)
    input_table.setStyle(TableStyle(_pdf_table_style()))
    story.append(input_table)

    doc.build(story)
    return path


def _normalize_report_format(report_format: str | None) -> ReportFormat:
    if str(report_format or "").lower() == "pdf":
        return "pdf"
    return "html"


def save_prefeasibility_report(
    destination_path: str,
    report_format: ReportFormat | str = "html",
) -> str:
    """Write the report to ``destination_path`` and return the path."""
    fmt = _normalize_report_format(report_format)
    path = str(destination_path).strip()
    if not path:
        raise ValueError("Report destination path is empty.")

    if fmt == "pdf":
        return build_prefeasibility_report_pdf(path)

    if not path.lower().endswith(".html"):
        path = f"{path}.html"
    content = build_prefeasibility_report_html()
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path
