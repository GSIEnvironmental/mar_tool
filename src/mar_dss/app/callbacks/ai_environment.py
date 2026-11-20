"""Prompt builders for MAR environmental, ecological, and cultural factors.

In-app Gemini API calls have been removed; these helpers build prompts for
copy/paste into an external AI model.
"""

import textwrap


def _normalize_stored_string(value):
    """Treat None, NaN, and empty CSV sentinels as missing; else return stripped str."""
    from mar_dss.app.utils.project_storage import normalize_stored_string

    return normalize_stored_string(value)


def _location_text(value):
    """Coerce stored or UI location values to a stripped string."""
    return _normalize_stored_string(value)


def downloadable_html_deliverable_instructions(
    report_title: str,
    *,
    context_line: str = "",
) -> str:
    """Shared prompt text asking the AI to return a neat downloadable HTML report."""
    context = f"\n        - Context line in the header: {context_line}" if context_line else ""
    return textwrap.dedent(
        f"""
        **FINAL DELIVERABLE — DOWNLOADABLE HTML REPORT:**
        Produce a complete, self-contained HTML document that the user can download
        and open in any browser. Do **not** use Markdown-only tables as the final answer.

        Requirements:
        1. Valid HTML5 with `<!DOCTYPE html>`, `<html>`, `<head>`, and `<body>`.
        2. Put all CSS in a `<style>` block inside `<head>` (no external CSS/JS required).
        3. Professional, neat layout: clear title (**{report_title}**), short intro,
           readable typography, spaced sections, and well-formatted HTML tables with
           distinct header styling.{context}
        4. Include a generation date in the report header.
        5. Use light visual hierarchy (for example color accents for High / Medium / Low
           priority or rank). Tables should remain readable on screen and when printed.
        6. Return the **full HTML source** in one fenced code block labeled
           `html` so the user can copy it into a file named something like
           `report.html` and download/open it locally.
        7. After the code block, add one short sentence telling the user to save the
           code as an `.html` file and open it in a browser.
        """,
    ).strip()


def build_mar_factors_prompt(location):
    """Build the MAR environmental factors prompt for any external AI model."""
    location = str(location).strip() if location is not None else ""
    if not location:
        raise ValueError("Location is required.")

    html_instructions = downloadable_html_deliverable_instructions(
        f"MAR Environmental, Ecological, and Cultural Factors — {location}",
        context_line=f"Project location: {location}",
    )

    return textwrap.dedent(
        "\n        **ROLE:** Multidisciplinary Managed Aquifer Recharge (MAR) Project Planning Expert "
        "(Hydrogeologist, Ecologist, Community Engagement Specialist).\n"
        "        **GOAL:** Generate a comprehensive, *prioritized* list of *actionable* data points, metrics, or "
        f"factors that *must* be collected and analyzed for an MAR project at **{location}**. The focus is strictly "
        "on **Environmental, Ecological, and Cultural impacts and viability** relevant to the specified geographic "
        "context.\n"
        "\n"
        f"        **LOCATION:** {location}\n"
        "        **CONTEXT CONSTRAINT:** All data points/factors must be relevant to the unique geographic, "
        f"regulatory, and ecological context of the {location} area.\n"
        "\n"
        "        **TASK INSTRUCTIONS (Follow Step-by-Step):**\n"
        "        1.  **Environmental Factors (Geochemistry):** Identify critical factors and actionable data points "
        "concerning chemical compatibility and sustainability (e.g., water quality degradation, geo-chemical "
        "reactions).\n"
        "        2.  **Ecological Factors (Ecosystem Health):** Identify critical factors and actionable data "
        "points related to the impact on Groundwater-Dependent Ecosystems (GDEs) like wetlands, riparian zones, and "
        "surface water bodies (e.g., changes to habitat or species).\n"
        "        3.  **Cultural Factors (Socio-economic/Governance):** Identify critical factors and actionable "
        "data points related to community impact, land use, legal/regulatory framework, and heritage preservation.\n"
        "        4.  **Prioritization and Justification:** For each identified item, assign a prioritization "
        f"(High/Medium/Low) based on its criticality for the {location} context and provide a brief rationale.\n"
        "\n"
        "        **CONTENT CONSTRAINTS:**\n"
        "        * **Quantification:** Provide a minimum of four specific factors/data points for *each* of the "
        "three categories (Environmental, Ecological, Cultural), for a total of at least 12 rows.\n"
        '        * **Precision:** Focus on actionable data points (e.g., "Groundwater-Surface Water Interaction '
        'Flow Rate," not just "Hydrology").\n'
        "        * **Table columns (in the HTML report):** Category (Environmental, Ecological, or Cultural); "
        "Actionable Data Point/Factor; Priority (High, Medium, or Low); Justification/Rationale (why this is "
        f"critical for the {location} project).\n"
        "\n"
        f"        {html_instructions}\n        ",
    ).strip()
