"""
AI Generated Decision tab content for MAR DSS dashboard.

Prompt-builder only — in-app Gemini API generation has been removed.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from mar_dss.app.callbacks.ai_environment import _normalize_stored_string
import mar_dss.app.utils.data_storage as dash_storage


def create_ai_generated_decision_content():
    """Create content for AI Generated Decision sub-tab (prompt builder)."""
    project_location = _normalize_stored_string(dash_storage.get_data("project_location"))

    return html.Div(
        [
            html.H3("AI Generated Decision", className="mb-2"),
            html.P(
                "Build a prompt that summarizes MAR DSS project data for ranking "
                "Surface Recharge, Injection Well, and Dry Well. Internal unit prices "
                "and cost estimates are excluded — the prompt includes engineering "
                "quantities only so an external AI can research location-specific costs.",
                className="text-muted mb-3",
            ),
            dbc.Alert(
                [
                    html.Div(
                        "Build the prompt, then paste it into your preferred AI model. "
                        "Results are generated as an HTML file that can be opened in any "
                        "browser.",
                        className="mb-0",
                    ),
                ],
                color="light",
                className="border mb-3 py-2",
            ),
            dbc.Card(
                [
                    dbc.CardHeader(
                        "Project Location",
                        className="fw-bold bg-primary text-white py-2",
                    ),
                    dbc.CardBody(
                        [
                            html.Label("Project Location", className="fw-bold small mb-1"),
                            dbc.Input(
                                id="ai-decision-location-input",
                                type="text",
                                value=project_location,
                                placeholder="City, State or City, Country",
                                size="sm",
                                className="mb-1",
                            ),
                            html.Small(
                                "Included in the prompt context; synced from Overview",
                                className="text-muted",
                            ),
                        ],
                        className="p-3",
                    ),
                ],
                className="mb-3",
            ),
            dbc.Card(
                [
                    dbc.CardHeader(
                        "Build Engineering Decision Prompt",
                        className="fw-bold bg-primary text-white py-2",
                    ),
                    dbc.CardBody(
                        [
                            html.Small(
                                "Create a prompt that summarizes all MAR DSS project data, "
                                "then paste it into your preferred AI model.",
                                className="text-muted d-block mb-2",
                            ),
                            dbc.ButtonGroup(
                                [
                                    dbc.Button(
                                        [html.I(className="fas fa-file-alt me-1"), "Build Prompt"],
                                        id="build-ai-decision-prompt-btn",
                                        color="outline-primary",
                                        size="sm",
                                        n_clicks=0,
                                    ),
                                    dbc.Button(
                                        [html.I(className="fas fa-copy me-1"), "Copy Prompt"],
                                        id="copy-ai-decision-prompt-btn",
                                        color="outline-secondary",
                                        size="sm",
                                        n_clicks=0,
                                    ),
                                ],
                                className="mb-2",
                            ),
                            html.Div(id="ai-decision-prompt-feedback", className="mb-2"),
                            dcc.Textarea(
                                id="ai-decision-prompt-display",
                                value="",
                                readOnly=True,
                                placeholder=(
                                    "Click Build Prompt to generate the full project "
                                    "context prompt…"
                                ),
                                style={
                                    "width": "100%",
                                    "minHeight": "260px",
                                    "fontFamily": "monospace",
                                    "fontSize": "12px",
                                    "resize": "vertical",
                                },
                            ),
                        ],
                        className="p-3",
                    ),
                ],
                className="mb-3",
            ),
            dbc.Tooltip(
                "Plain-language place name included in the prompt",
                target="ai-decision-location-input",
                placement="top",
            ),
            dbc.Tooltip(
                "Create the engineering decision prompt from current project data",
                target="build-ai-decision-prompt-btn",
                placement="top",
            ),
            dbc.Tooltip(
                "Copy the prompt below to your clipboard",
                target="copy-ai-decision-prompt-btn",
                placement="top",
            ),
        ]
    )
