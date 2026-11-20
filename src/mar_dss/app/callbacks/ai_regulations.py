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
        f"""
        **ROLE:** Multidisciplinary Managed Aquifer Recharge (MAR) Regulatory and Permitting Expert (Water Resources Attorney, Hydrogeologist, Environmental Planner, Regulatory Compliance Specialist)

        **GOAL:** Generate a comprehensive, *prioritized* list of all regulatory requirements, permits, agency coordination needs, and legal considerations relevant to developing and operating a **Managed Aquifer Recharge (MAR)** project at **{location_us}**. The focus is strictly on **local, county, state, and federal regulatory compliance, permitting, governance, and legal feasibility** relevant to the specified geographic context.

        **LOCATION:** {location}

        **CONTEXT CONSTRAINT:** All regulations, permits, agencies, and legal considerations must be directly relevant to the geographic, hydrogeologic, land-use, and regulatory context of the specified location. Do not provide generic national guidance unless it specifically applies to the project location.

        ---

        ### TASK INSTRUCTIONS (Follow Step-by-Step)

        #### 1. Local and County Regulatory Requirements

        Identify all applicable local and county-level regulations, ordinances, plans, and approval processes that may affect MAR project planning, construction, operation, or maintenance, including:

        * Zoning and land-use requirements
        * County environmental review requirements
        * Floodplain and drainage regulations
        * Groundwater management plans
        * Local water district or irrigation district requirements
        * County grading, encroachment, and construction permits

        #### 2. State Regulatory Requirements

        Identify all applicable state-level laws, regulations, policies, and planning requirements relevant to MAR, including:

        * Water rights requirements
        * Groundwater management regulations
        * Water quality regulations
        * Environmental review requirements
        * Wetland and habitat protection requirements
        * Dam safety or recharge facility regulations
        * Drinking water protection requirements
        * Any MAR-specific guidance, policies, or regulatory frameworks

        #### 3. Federal Regulatory Requirements

        Identify all applicable federal laws, regulations, consultations, and permitting requirements relevant to MAR, including:

        * Clean Water Act requirements
        * Endangered Species Act requirements
        * National Historic Preservation Act requirements
        * National Environmental Policy Act requirements
        * Army Corps permitting requirements
        * EPA regulatory oversight
        * Federal land management considerations
        * Federal funding compliance requirements (if applicable)

        #### 4. Required Permits and Approvals

        Identify every permit, authorization, approval, certification, consultation, agreement, or determination that may be required for the MAR project, including:

        * Permit name
        * Responsible agency
        * Trigger condition (why the permit may be needed)
        * Typical project phase when required (planning, design, construction, operation)

        #### 5. Agency Coordination Requirements

        Identify all agencies, districts, tribes, utilities, and regulatory entities that should be contacted or coordinated with during project development, including:

        * Agency name
        * Jurisdiction
        * Primary role in MAR review or approval
        * Level of involvement (Required, Recommended, or Conditional)

        #### 6. Legal and Governance Considerations

        Identify key legal considerations that could affect MAR feasibility, implementation, ownership, operation, or long-term management, including:

        * Water rights and ownership of recharged water
        * Groundwater accounting and recovery rights
        * Sustainable groundwater management requirements
        * Liability considerations
        * Water quality degradation liability
        * Landowner agreements and easements
        * Environmental compliance risks
        * Tribal consultation requirements
        * Public trust considerations
        * Long-term monitoring and reporting obligations

        #### 7. Prioritization and Justification

        For each identified regulation, permit, agency, or legal consideration:

        * Assign a priority (**High, Medium, Low**)
        * Provide a concise rationale explaining why it is important for MAR project decision-making at the specified location.

        ---

        ### OUTPUT CONSTRAINTS

        #### Quantification

        Provide a minimum of:

        * 5 Local/County regulatory items
        * 8 State regulatory items
        * 5 Federal regulatory items
        * 10 Required permits/approvals
        * 10 Agencies/entities for coordination
        * 8 Legal considerations

        #### Precision

        Focus on specific, actionable regulatory requirements rather than broad topics. For example:

        * Use "Clean Water Act Section 404 Permit" rather than "Federal permitting"
        * Use "Groundwater Sustainability Agency Coordination" rather than "Groundwater management"

        #### Format

        Present the results inside a downloadable HTML report (see Final Deliverable).
        The HTML must include one primary results table with exactly these columns:

        | Category | Regulation / Permit / Agency / Legal Consideration | Responsible Agency | Priority (High/Medium/Low) | Requirement Level (Mandatory/Potentially Required/Recommended) | Trigger or Applicability | Why It Matters for MAR Decision-Making |

        Each row must represent one item.

        #### Additional Requirements

        1. Identify whether each item is **Mandatory**, **Potentially Required**, or **Recommended**.
        2. Cite the specific law, regulation, program, or agency authority whenever possible.
        3. Tailor all recommendations to {location}.
        4. Highlight high-risk items that could delay, prevent, or significantly increase project cost using **High** priority within the table rows.

        {html_instructions}
        """,
    ).strip()
