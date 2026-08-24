"""
AI Generated Decision tab content for MAR DSS dashboard.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from mar_dss.app.callbacks.ai_environment import _normalize_stored_string
import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.utils.tab_tooltips import slider_tooltip_kwargs


def create_ai_generated_decision_content():
    """Create content for AI Generated Decision sub-tab."""
    gemini_api_key = _normalize_stored_string(dash_storage.get_data("gemini_api_key"))
    gemini_api_file = _normalize_stored_string(dash_storage.get_data("gemini_api_file"))
    if not gemini_api_file:
        gemini_api_file = r"C:\workspace\api\gemini.txt"
    project_location = _normalize_stored_string(dash_storage.get_data("project_location"))

    return html.Div(
        [
            html.H3("AI Generated Decision", className="mb-2"),
            html.P(
                "AI-assisted ranking of Surface Recharge, Injection Well, and Dry Well "
                "using project data from all MAR DSS tabs. Internal unit prices and cost "
                "estimates are excluded — the AI receives engineering quantities only and "
                "is asked to research location-specific costs independently.",
                className="text-muted mb-3",
            ),
            dbc.Alert(
                [
                    html.Div(
                        "Choose how to generate engineering option feasibility scores:",
                        className="fw-bold mb-2",
                    ),
                    html.Ul(
                        [
                            html.Li(
                                [
                                    html.Span("Option 1 — ", className="fw-bold"),
                                    html.Span("Gemini with personal API", className="fw-bold text-success"),
                                    html.Span(
                                        ": enter your API key (right), then click ",
                                        className="text-muted",
                                    ),
                                    html.Span("Generate AI Decision Scores", className="fw-semibold"),
                                    html.Span(".", className="text-muted"),
                                ],
                                className="mb-2",
                            ),
                            html.Li(
                                [
                                    html.Span("Option 2 — ", className="fw-bold"),
                                    html.Span(
                                        "Create the prompt and use it in your chosen AI model",
                                        className="fw-bold text-primary",
                                    ),
                                    html.Span(": click ", className="text-muted"),
                                    html.Span("Build Prompt", className="fw-semibold"),
                                    html.Span(", then ", className="text-muted"),
                                    html.Span("Copy Prompt", className="fw-semibold"),
                                    html.Span(
                                        " and paste into ChatGPT, Claude, Copilot, or another tool.",
                                        className="text-muted",
                                    ),
                                ],
                                className="mb-0",
                            ),
                        ],
                        className="mb-0 ps-3",
                    ),
                ],
                color="light",
                className="border mb-3 py-2",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Card(
                                [
                                    dbc.CardHeader(
                                        "AI Engineering Option Feasibility Scores",
                                        className="fw-bold bg-primary text-white py-2",
                                    ),
                                    dbc.CardBody(
                                        [
                                            html.Label("Project Location:", className="fw-bold small mb-1"),
                                            dbc.Input(
                                                id="ai-decision-location-input",
                                                type="text",
                                                value=project_location,
                                                placeholder="City, State or City, Country",
                                                size="sm",
                                                className="mb-1",
                                            ),
                                            html.Small(
                                                "Included in the prompt context; synced from Overview.",
                                                className="text-muted d-block mb-2",
                                            ),
                                            dbc.Button(
                                                [
                                                    html.I(className="fas fa-robot me-1"),
                                                    "Generate AI Decision Scores",
                                                ],
                                                id="generate-ai-decision-btn",
                                                color="success",
                                                size="sm",
                                                n_clicks=0,
                                                className="mb-3",
                                            ),
                                            dcc.Loading(
                                                id="ai-decision-loading",
                                                type="circle",
                                                color="#198754",
                                                parent_style={"minHeight": "80px"},
                                                children=html.Div(
                                                    id="ai-decision-results-container",
                                                    className="mb-2",
                                                ),
                                            ),
                                            dbc.Row(
                                                [
                                                    dbc.Col(
                                                        [
                                                            html.Label(
                                                                "Model:",
                                                                className="fw-bold small mb-1",
                                                            ),
                                                            dcc.Dropdown(
                                                                id="ai-decision-gemini-model-select",
                                                                options=[
                                                                    {
                                                                        "label": "gemini-2.5-flash",
                                                                        "value": "gemini-2.5-flash",
                                                                    },
                                                                    {
                                                                        "label": "gemini-1.5-flash",
                                                                        "value": "gemini-1.5-flash",
                                                                    },
                                                                    {
                                                                        "label": "gemini-1.5-pro",
                                                                        "value": "gemini-1.5-pro",
                                                                    },
                                                                    {
                                                                        "label": "gemini-pro",
                                                                        "value": "gemini-pro",
                                                                    },
                                                                ],
                                                                value=dash_storage.get_data("gemini_model")
                                                                or "gemini-2.5-flash",
                                                                clearable=False,
                                                            ),
                                                        ],
                                                        xs=12,
                                                        md=6,
                                                    ),
                                                    dbc.Col(
                                                        [
                                                            html.Label(
                                                                "Temperature:",
                                                                className="fw-bold small mb-1",
                                                            ),
                                                            dcc.Slider(
                                                                id="ai-decision-temperature-slider",
                                                                min=0.0,
                                                                max=2.0,
                                                                step=0.1,
                                                                value=float(
                                                                    dash_storage.get_data("gemini_temperature")
                                                                    or 0.5
                                                                ),
                                                                marks={0.0: "0", 1.0: "1", 2.0: "2"},
                                                                tooltip=slider_tooltip_kwargs(),
                                                            ),
                                                            html.Div(
                                                                id="ai-decision-temperature-display",
                                                                className="mt-1",
                                                            ),
                                                        ],
                                                        xs=12,
                                                        md=6,
                                                        className="mt-2 mt-md-0",
                                                    ),
                                                ],
                                                className="g-2",
                                            ),
                                        ],
                                        className="p-3",
                                    ),
                                ],
                            ),
                        ],
                        xs=12,
                        lg=7,
                        className="mb-3 mb-lg-0",
                    ),
                    dbc.Col(
                        [
                            dbc.Card(
                                [
                                    dbc.CardHeader(
                                        "Gemini API Settings",
                                        className="fw-bold bg-primary text-white py-2",
                                    ),
                                    dbc.CardBody(
                                        [
                                            html.Label(
                                                "Gemini API Key:",
                                                className="fw-bold small mb-1",
                                            ),
                                            dbc.Input(
                                                id="ai-decision-gemini-api-key-input",
                                                type="password",
                                                value=gemini_api_key,
                                                placeholder="Enter API key (optional if file/env set)",
                                                debounce=True,
                                                size="sm",
                                                className="mb-1",
                                            ),
                                            html.Small(
                                                "Optional if using Gemini here. Stored locally. "
                                                "Get a key at aistudio.google.com/apikey",
                                                className="text-muted d-block mb-3",
                                            ),
                                            html.Label(
                                                "API Key File Path:",
                                                className="fw-bold small mb-1",
                                            ),
                                            dbc.Input(
                                                id="ai-decision-gemini-api-file-input",
                                                type="text",
                                                value=gemini_api_file,
                                                placeholder=r"C:\workspace\api\gemini.txt",
                                                debounce=True,
                                                size="sm",
                                                className="mb-1",
                                            ),
                                            html.Small(
                                                "Fallback file if key is not entered above.",
                                                className="text-muted",
                                            ),
                                        ],
                                        className="p-3",
                                    ),
                                ],
                                className="h-100",
                            ),
                        ],
                        xs=12,
                        lg=5,
                        className="mb-3 mb-lg-0",
                    ),
                ],
                className="mb-3 g-3 align-items-stretch",
            ),
            dbc.Card(
                [
                    dbc.CardHeader(
                        "Use Your Own AI Model",
                        className="fw-bold bg-primary text-white py-2",
                    ),
                    dbc.CardBody(
                        [
                            html.Small(
                                "Build a prompt that summarizes all MAR DSS project data, then copy "
                                "and paste it into ChatGPT, Claude, Copilot, or another AI tool.",
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
                                placeholder="Click Build Prompt to generate the full project context prompt…",
                                style={
                                    "width": "100%",
                                    "minHeight": "220px",
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
        ]
    )
