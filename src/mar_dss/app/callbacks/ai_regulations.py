"""Prompt builders for MAR regulatory and permitting matrices.

In-app Gemini API calls have been removed; these helpers build prompts for
copy/paste into an external AI model.
"""

import re
import textwrap

from mar_dss.app.callbacks.ai_environment import (
    _location_text,
    downloadable_html_deliverable_instructions,
)


def _location_display(location):
    """Format location for US regulatory context when country is omitted."""
    location = _location_text(location)
    if not location:
        raise ValueError("Location is required.")
    if re.search(r"\b(united states|usa|u\.s\.)\b", location, re.I):
        return location
    return f"{location}, United States"


def build_mar_regulations_prompt(location):
    """Build the MAR regulatory and permitting prompt for an external AI model."""
    location = _location_text(location)
    if not location:
        raise ValueError("Location is required.")
    location_us = _location_display(location)
    html_instructions = downloadable_html_deliverable_instructions(
        f"MAR Regulatory and Permitting Factors — {location}",
        context_line=f"Project location: {location}",
    )

    return textwrap.dedent(
        "\n        **ROLE:** Multidisciplinary Managed Aquifer Recharge (MAR) Regulatory and Permitting Expert (Water "
        "Resources Attorney, Hydrogeologist, Environmental Planner, Regulatory Compliance Specialist)\n"
        "\n"
        "        **GOAL:** Generate a comprehensive, *prioritized* list of all regulatory requirements, permits, "
        "agency coordination needs, and legal considerations relevant to developing and operating a **Managed "
        f"Aquifer Recharge (MAR)** project at **{location_us}**. The focus is strictly on **local, county, state, "
        "and federal regulatory compliance, permitting, governance, and legal feasibility** relevant to the "
        "specified geographic context.\n"
        "\n"
        f"        **LOCATION:** {location}\n"
        "\n"
        "        **CONTEXT CONSTRAINT:** All regulations, permits, agencies, and legal considerations must be "
        "directly relevant to the geographic, hydrogeologic, land-use, and regulatory context of the specified "
        "location. Do not provide generic national guidance unless it specifically applies to the project "
        "location.\n"
        "\n"
        "        ---\n"
        "\n"
        "        ### TASK INSTRUCTIONS (Follow Step-by-Step)\n"
        "\n"
        "        #### 1. Local and County Regulatory Requirements\n"
        "\n"
        "        Identify all applicable local and county-level regulations, ordinances, plans, and approval "
        "processes that may affect MAR project planning, construction, operation, or maintenance, including:\n"
        "\n"
        "        * Zoning and land-use requirements\n"
        "        * County environmental review requirements\n"
        "        * Floodplain and drainage regulations\n"
        "        * Groundwater management plans\n"
        "        * Local water district or irrigation district requirements\n"
        "        * County grading, encroachment, and construction permits\n"
        "\n"
        "        #### 2. State Regulatory Requirements\n"
        "\n"
        "        Identify all applicable state-level laws, regulations, policies, and planning requirements "
        "relevant to MAR, including:\n"
        "\n"
        "        * Water rights requirements\n"
        "        * Groundwater management regulations\n"
        "        * Water quality regulations\n"
        "        * Environmental review requirements\n"
        "        * Wetland and habitat protection requirements\n"
        "        * Dam safety or recharge facility regulations\n"
        "        * Drinking water protection requirements\n"
        "        * Any MAR-specific guidance, policies, or regulatory frameworks\n"
        "\n"
        "        #### 3. Federal Regulatory Requirements\n"
        "\n"
        "        Identify all applicable federal laws, regulations, consultations, and permitting requirements "
        "relevant to MAR, including:\n"
        "\n"
        "        * Clean Water Act requirements\n"
        "        * Endangered Species Act requirements\n"
        "        * National Historic Preservation Act requirements\n"
        "        * National Environmental Policy Act requirements\n"
        "        * Army Corps permitting requirements\n"
        "        * EPA regulatory oversight\n"
        "        * Federal land management considerations\n"
        "        * Federal funding compliance requirements (if applicable)\n"
        "\n"
        "        #### 4. Required Permits and Approvals\n"
        "\n"
        "        Identify every permit, authorization, approval, certification, consultation, agreement, or "
        "determination that may be required for the MAR project, including:\n"
        "\n"
        "        * Permit name\n"
        "        * Responsible agency\n"
        "        * Trigger condition (why the permit may be needed)\n"
        "        * Typical project phase when required (planning, design, construction, operation)\n"
        "\n"
        "        #### 5. Agency Coordination Requirements\n"
        "\n"
        "        Identify all agencies, districts, tribes, utilities, and regulatory entities that should be "
        "contacted or coordinated with during project development, including:\n"
        "\n"
        "        * Agency name\n"
        "        * Jurisdiction\n"
        "        * Primary role in MAR review or approval\n"
        "        * Level of involvement (Required, Recommended, or Conditional)\n"
        "\n"
        "        #### 6. Legal and Governance Considerations\n"
        "\n"
        "        Identify key legal considerations that could affect MAR feasibility, implementation, ownership, "
        "operation, or long-term management, including:\n"
        "\n"
        "        * Water rights and ownership of recharged water\n"
        "        * Groundwater accounting and recovery rights\n"
        "        * Sustainable groundwater management requirements\n"
        "        * Liability considerations\n"
        "        * Water quality degradation liability\n"
        "        * Landowner agreements and easements\n"
        "        * Environmental compliance risks\n"
        "        * Tribal consultation requirements\n"
        "        * Public trust considerations\n"
        "        * Long-term monitoring and reporting obligations\n"
        "\n"
        "        #### 7. Prioritization and Justification\n"
        "\n"
        "        For each identified regulation, permit, agency, or legal consideration:\n"
        "\n"
        "        * Assign a priority (**High, Medium, Low**)\n"
        "        * Provide a concise rationale explaining why it is important for MAR project decision-making at "
        "the specified location.\n"
        "\n"
        "        ---\n"
        "\n"
        "        ### OUTPUT CONSTRAINTS\n"
        "\n"
        "        #### Quantification\n"
        "\n"
        "        Provide a minimum of:\n"
        "\n"
        "        * 5 Local/County regulatory items\n"
        "        * 8 State regulatory items\n"
        "        * 5 Federal regulatory items\n"
        "        * 10 Required permits/approvals\n"
        "        * 10 Agencies/entities for coordination\n"
        "        * 8 Legal considerations\n"
        "\n"
        "        #### Precision\n"
        "\n"
        "        Focus on specific, actionable regulatory requirements rather than broad topics. For example:\n"
        "\n"
        '        * Use "Clean Water Act Section 404 Permit" rather than "Federal permitting"\n'
        '        * Use "Groundwater Sustainability Agency Coordination" rather than "Groundwater management"\n'
        "\n"
        "        #### Format\n"
        "\n"
        "        Present the results inside a downloadable HTML report (see Final Deliverable).\n"
        "        The HTML must include one primary results table with exactly these columns:\n"
        "\n"
        "        | Category | Regulation / Permit / Agency / Legal Consideration | Responsible Agency | Priority "
        "(High/Medium/Low) | Requirement Level (Mandatory/Potentially Required/Recommended) | Trigger or "
        "Applicability | Why It Matters for MAR Decision-Making |\n"
        "\n"
        "        Each row must represent one item.\n"
        "\n"
        "        #### Additional Requirements\n"
        "\n"
        "        1. Identify whether each item is **Mandatory**, **Potentially Required**, or **Recommended**.\n"
        "        2. Cite the specific law, regulation, program, or agency authority whenever possible.\n"
        f"        3. Tailor all recommendations to {location}.\n"
        "        4. Highlight high-risk items that could delay, prevent, or significantly increase project cost "
        "using **High** priority within the table rows.\n"
        "\n"
        f"        {html_instructions}\n        ",
    ).strip()
