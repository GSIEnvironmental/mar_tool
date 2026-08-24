from google import genai
import json
import textwrap
from pydantic import BaseModel, Field
from typing import List, Optional
import pandas as pd
import os # Import os for environment variable management
import mar_dss.app.utils.data_storage as dash_storage


def _normalize_stored_string(value):
    """Treat None, NaN, and empty CSV sentinels as missing; else return stripped str."""
    from mar_dss.app.utils.project_storage import normalize_stored_string

    return normalize_stored_string(value)


def _normalize_api_key(value):
    """Return a usable API key string, or None if missing/invalid."""
    key = _normalize_stored_string(value)
    return key or None


def _location_text(value):
    """Coerce stored or UI location values to a stripped string."""
    return _normalize_stored_string(value)


def _resolve_gemini_api_key():
    """Resolve Gemini API key from storage, file, or environment."""
    api_key = _normalize_api_key(dash_storage.get_data("gemini_api_key"))
    if not api_key:
        api_file = _normalize_stored_string(dash_storage.get_data("gemini_api_file"))
        if not api_file:
            api_file = r"C:\workspace\api\gemini.txt"
        if os.path.exists(api_file):
            with open(api_file, "r") as f:
                api_key = _normalize_api_key(f.read())
    if not api_key:
        api_key = _normalize_api_key(os.getenv("GEMINI_API_KEY"))
    return api_key


# --- REVISED MAR PROMPT ---

def build_mar_factors_prompt(location):
    """Build the MAR environmental factors prompt for Gemini or any external AI model."""
    location = str(location).strip() if location is not None else ""
    if not location:
        raise ValueError("Location is required.")

    return textwrap.dedent(
        f"""
        **ROLE:** Multidisciplinary Managed Aquifer Recharge (MAR) Project Planning Expert (Hydrogeologist, Ecologist, Community Engagement Specialist).
        **GOAL:** Generate a comprehensive, *prioritized* list of *actionable* data points, metrics, or factors that *must* be collected and analyzed for an MAR project at **{location}**. The focus is strictly on **Environmental, Ecological, and Cultural impacts and viability** relevant to the specified geographic context.

        **LOCATION:** {location}
        **CONTEXT CONSTRAINT:** All data points/factors must be relevant to the unique geographic, regulatory, and ecological context of the {location} area.

        **TASK INSTRUCTIONS (Follow Step-by-Step):**
        1.  **Environmental Factors (Geochemistry):** Identify critical factors and actionable data points concerning chemical compatibility and sustainability (e.g., water quality degradation, geo-chemical reactions).
        2.  **Ecological Factors (Ecosystem Health):** Identify critical factors and actionable data points related to the impact on Groundwater-Dependent Ecosystems (GDEs) like wetlands, riparian zones, and surface water bodies (e.g., changes to habitat or species).
        3.  **Cultural Factors (Socio-economic/Governance):** Identify critical factors and actionable data points related to community impact, land use, legal/regulatory framework, and heritage preservation.
        4.  **Prioritization and Justification:** For each identified item, assign a prioritization (High/Medium/Low) based on its criticality for the {location} context and provide a brief rationale.

        **OUTPUT CONSTRAINTS:**
        * **Quantification:** Provide a minimum of four specific factors/data points for *each* of the three categories (Environmental, Ecological, Cultural), for a total of at least 12 rows.
        * **Precision:** Focus on actionable data points (e.g., "Groundwater-Surface Water Interaction Flow Rate," not just "Hydrology").
        * **Format:** Present the final output as a single, organized **Markdown Table** with the following four columns:
            * **Category** (Environmental, Ecological, or Cultural)
            * **Actionable Data Point/Factor**
            * **Priority** (High, Medium, or Low)
            * **Justification/Rationale** (Why is this critical for the {location} project?)
        """
    ).strip()


def get_mar_factors(location, model="gemini-2.5-flash", temperature=0.5):
    """
    Get the MAR factors for a given location.
    
    Parameters:
    -----------
    location : str
        The location for which to generate MAR factors
    model : str, optional
        The Gemini model version to use (default: "gemini-2.5-flash")
    temperature : float, optional
        The temperature parameter for generation (default: 0.5, range: 0.0-2.0)
    """
    mar_prompt = build_mar_factors_prompt(location)
    # -----------------------------

    # 1. Define the schema for a single row in your table (REVISED STRUCTURE)
    class MARFactor(BaseModel):
        """A structured representation of a single factor/data point for the MAR project."""
        category: str = Field(description="The category of the factor: 'Environmental', 'Ecological', or 'Cultural'.")
        data_point: str = Field(description="The actionable data point or factor that needs to be collected/analyzed.")
        priority: str = Field(description="The assessed priority: 'High', 'Medium', or 'Low'.")
        justification: str = Field(description="A brief rationale for the factor's criticality at the site.")

    # 2. Define the schema for the final output (A list of rows) (REVISED STRUCTURE)
    class MARFactorList(BaseModel):
        """A list of factors/data points for the MAR project."""
        factors: List[MARFactor] = Field(description="A list of factors and data points matching the request's constraints.")


    # --- API Configuration and Execution ---
    api_key = _resolve_gemini_api_key()
    if not api_key:
        raise ValueError("API Key not found. Please enter your Gemini API key in the control panel, set GEMINI_API_KEY environment variable, or check the file path.")

    client = genai.Client(api_key=api_key)

    # The model must be one that supports structured output (e.g., gemini-2.5-flash)
    response = client.models.generate_content(
        model=model,
        contents=mar_prompt,  # Use the revised MAR prompt
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=MARFactorList,  # Use the revised Pydantic schema
            temperature=temperature,
        ),
    )

    # The response.text will be a valid JSON string
    json_data = json.loads(response.text)

    # Ensure the DataFrame is created from the correct list key ('factors')
    df = pd.DataFrame(json_data['factors'])
    #df.to_csv(f"mar_factors_{location}.csv", index=False)
    
    return df

# Uncomment to test:
# get_mar_factors("China Lake, ca")

