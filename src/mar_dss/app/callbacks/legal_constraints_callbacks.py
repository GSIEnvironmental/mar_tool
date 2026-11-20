"""
Callbacks for Legal Constraints tab - AI regulations prompt builder (5.2).

Basic Regulation Feasibility (5.1) is informational only and no longer scored.
In-app Gemini API generation has been removed; users build and copy prompts
for an external AI model. Location comes from Overview (project_location).
"""

import dash
import dash_bootstrap_components as dbc
from dash import MATCH, Input, Output, State, html

import mar_dss.app.utils.data_storage as data_storage
from mar_dss.app.callbacks.ai_environment import _location_text
from mar_dss.app.callbacks.ai_regulations import build_mar_regulations_prompt


def setup_legal_constraints_callbacks(app):
    """Set up callbacks for the Legal Constraints tab."""

    @app.callback(
        Output({"type": "reg-detail-collapse", "index": MATCH}, "is_open"),
        Output({"type": "reg-detail-toggle", "index": MATCH}, "children"),
        Input({"type": "reg-detail-toggle", "index": MATCH}, "n_clicks"),
        State({"type": "reg-detail-collapse", "index": MATCH}, "is_open"),
        prevent_initial_call=True,
    )
    def toggle_regulatory_consideration_detail(n_clicks, is_open):
        """Expand/collapse detail for a single regulatory consideration."""
        if not n_clicks:
            return dash.no_update, dash.no_update
        new_open = not bool(is_open)
        label = [
            html.I(className=("fas fa-chevron-up me-1" if new_open else "fas fa-chevron-down me-1")),
            "View less" if new_open else "View more",
        ]
        return new_open, label

    @app.callback(
        [
            Output("mar-regs-prompt-display", "value"),
            Output("mar-regs-prompt-feedback", "children"),
        ],
        Input("build-mar-regs-prompt-btn", "n_clicks"),
        State("project-location-store", "data"),
        prevent_initial_call=True,
    )
    def build_mar_regs_prompt_display(n_clicks, store_location):
        """Fill the regulations prompt using Overview Project Location."""
        if not n_clicks:
            return dash.no_update, dash.no_update

        location = _location_text(store_location) or _location_text(data_storage.get_data("project_location"))
        if not location:
            return "", dbc.Alert(
                "Set Project Location on the (1) Overview tab before building the prompt.",
                color="warning",
                className="py-2 mb-0 small",
            )

        prompt = build_mar_regulations_prompt(location)
        feedback = html.Small(
            f"Prompt ready for {location}. Click Copy Prompt, then paste it into your preferred AI model.",
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
        Output("mar-regs-prompt-feedback", "children", allow_duplicate=True),
        Input("copy-mar-regs-prompt-btn", "n_clicks"),
        State("mar-regs-prompt-display", "value"),
        prevent_initial_call=True,
    )
