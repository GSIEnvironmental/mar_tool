"""Dash callbacks for the AI Generated Decision sub-tab (prompt builder only).

In-app Gemini API generation has been removed; users build and copy prompts
for an external AI model.
"""

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, html

import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.callbacks.ai_engineering_decision import (
    build_engineering_decision_prompt,
    summarize_project_context,
)
from mar_dss.app.callbacks.ai_environment import _location_text

data_storage = dash_storage


def setup_ai_decision_callbacks(app):
    """Register callbacks for AI Generated Decision sub-tab."""

    @app.callback(
        Output("ai-decision-location-input", "value"),
        [
            Input("project-location-store", "data"),
            Input("ai-decision-location-input", "id"),
        ],
        prevent_initial_call=False,
    )
    def sync_ai_decision_location_from_project(store_location, _component_id):
        return _location_text(store_location or data_storage.get_data("project_location"))

    @app.callback(
        [
            Output("ai-decision-prompt-display", "value"),
            Output("ai-decision-prompt-feedback", "children"),
        ],
        Input("build-ai-decision-prompt-btn", "n_clicks"),
        State("ai-decision-location-input", "value"),
        prevent_initial_call=True,
    )
    def build_ai_decision_prompt_display(n_clicks, location):
        if not n_clicks:
            return dash.no_update, dash.no_update

        context = summarize_project_context()
        loc = _location_text(location) or _location_text(context.get("project_location"))
        if loc:
            context["project_location"] = loc
        elif not context.get("project_location"):
            return "", dbc.Alert(
                "Set Project Location on the Overview tab for better context, "
                "or enter a location above before building the prompt.",
                color="warning",
                className="py-2 mb-0 small",
            )

        prompt = build_engineering_decision_prompt(context)
        feedback = html.Small(
            "Prompt ready with full project context. Click Copy Prompt, then paste "
            "it into your preferred AI model.",
            className="text-success",
        )
        return prompt, feedback

    app.clientside_callback(
        """
        function(n_clicks, prompt_text) {
            if (!n_clicks) {
                return window.dash_clientside.no_update;
            }
            if (!prompt_text) {
                return "Build the prompt first, then click Copy Prompt.";
            }
            navigator.clipboard.writeText(prompt_text).catch(function() {});
            return "Prompt copied to clipboard.";
        }
        """,
        Output("ai-decision-prompt-feedback", "children", allow_duplicate=True),
        Input("copy-ai-decision-prompt-btn", "n_clicks"),
        State("ai-decision-prompt-display", "value"),
        prevent_initial_call=True,
    )
