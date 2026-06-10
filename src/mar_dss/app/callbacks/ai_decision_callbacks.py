"""Dash callbacks for the AI Generated Decision sub-tab."""

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, dcc, dash_table, html

import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.callbacks.ai_engineering_decision import (
    build_engineering_decision_prompt,
    get_engineering_decision_scores,
    summarize_project_context,
)
from mar_dss.app.callbacks.ai_environment import (
    _location_text,
    _normalize_stored_string,
)

data_storage = dash_storage

_RANK_COLORS = {1: "#198754", 2: "#ffc107", 3: "#dc3545"}

_CATEGORY_COLORS = {
    "Warning": {"bg": "#f8d7da", "text": "#721c24"},
    "Recommendation": {"bg": "#d4edda", "text": "#155724"},
    "Key Finding": {"bg": "#cfe2ff", "text": "#084298"},
    "Decision Rationale": {"bg": "#e2e3e5", "text": "#41464b"},
    "Mitigation": {"bg": "#fff3cd", "text": "#856404"},
    "Data Gap": {"bg": "#f8d7da", "text": "#721c24"},
}


def _ai_decision_success_banner(location: str, top_option: str, top_score: float) -> dbc.Alert:
    return dbc.Alert(
        [
            html.H5("AI decision scores generated", className="alert-heading mb-2"),
            html.P(
                [
                    html.Strong(f"Top-ranked option: {top_option}"),
                    html.Span(f" (feasibility score {top_score:.1f}/100) for {location}."),
                ],
                className="mb-0",
            ),
        ],
        color="success",
        className="py-2 mb-3",
    )


def _build_scores_chart(scores_df):
    """Bar chart of feasibility scores sorted by rank."""
    df = scores_df.copy()
    if "rank" in df.columns:
        df = df.sort_values("rank")
    options = df["engineering_option"].astype(str).tolist()
    scores = df["feasibility_score"].astype(float).tolist()
    ranks = df["rank"].astype(int).tolist() if "rank" in df.columns else [1] * len(scores)
    colors = [_RANK_COLORS.get(r, "#6c757d") for r in ranks]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=options,
            y=scores,
            marker_color=colors,
            text=[f"{s:.1f}" for s in scores],
            textposition="auto",
            hovertemplate="%{x}<br>Score: %{y:.1f}<extra></extra>",
        )
    )
    fig.update_layout(
        title="Engineering Option Feasibility Scores",
        xaxis_title="Engineering Option",
        yaxis=dict(title="Feasibility Score (0–100)", range=[0, 100]),
        template="plotly_white",
        height=420,
        margin=dict(l=40, r=20, t=50, b=80),
    )
    return fig


def _scores_datatable(scores_df):
    display_df = scores_df.copy()
    if "feasibility_score" in display_df.columns:
        display_df["feasibility_score"] = display_df["feasibility_score"].round(1)

    style_data_conditional = []
    for idx, row in display_df.iterrows():
        rank_val = row.get("rank", 0)
        rank = int(rank_val) if pd.notna(rank_val) else 0
        color = _RANK_COLORS.get(rank, "#6c757d")
        style_data_conditional.append(
            {
                "if": {"row_index": idx, "column_id": "rank"},
                "backgroundColor": color,
                "color": "white",
                "fontWeight": "bold",
            }
        )

    return dash_table.DataTable(
        id="ai-decision-scores-datatable",
        columns=[
            {"name": "Engineering Option", "id": "engineering_option"},
            {"name": "Feasibility Score (0–100)", "id": "feasibility_score"},
            {"name": "Rank (1 = best)", "id": "rank"},
            {"name": "Score Summary", "id": "score_summary"},
        ],
        data=display_df.to_dict("records"),
        style_header={
            "backgroundColor": "#0d6efd",
            "color": "white",
            "fontWeight": "bold",
            "textAlign": "left",
            "border": "1px solid #dee2e6",
            "fontSize": "14px",
        },
        style_cell={
            "textAlign": "left",
            "padding": "12px",
            "fontFamily": "Arial, sans-serif",
            "fontSize": "14px",
            "whiteSpace": "normal",
            "height": "auto",
            "border": "1px solid #dee2e6",
            "minWidth": "120px",
            "maxWidth": "420px",
        },
        style_data={"border": "1px solid #dee2e6"},
        style_data_conditional=style_data_conditional,
        sort_action="native",
        export_format="csv",
    )


def _explanations_datatable(explanations_df):
    style_data_conditional = []
    for idx, row in explanations_df.iterrows():
        category = str(row.get("category", "")).strip()
        colors = _CATEGORY_COLORS.get(category)
        if colors:
            style_data_conditional.append(
                {
                    "if": {"row_index": idx, "column_id": "category"},
                    "backgroundColor": colors["bg"],
                    "color": colors["text"],
                    "fontWeight": "bold",
                }
            )
        if idx % 2 == 0:
            for col in ("topic", "detail", "related_option"):
                style_data_conditional.append(
                    {
                        "if": {"row_index": idx, "column_id": col},
                        "backgroundColor": "#f8f9fa",
                    }
                )

    return dash_table.DataTable(
        id="ai-decision-explanations-datatable",
        columns=[
            {"name": "Category", "id": "category"},
            {"name": "Topic", "id": "topic"},
            {"name": "Detail", "id": "detail"},
            {"name": "Related Option", "id": "related_option"},
        ],
        data=explanations_df.to_dict("records"),
        style_header={
            "backgroundColor": "#495057",
            "color": "white",
            "fontWeight": "bold",
            "textAlign": "left",
            "border": "1px solid #dee2e6",
            "fontSize": "14px",
        },
        style_cell={
            "textAlign": "left",
            "padding": "12px",
            "fontFamily": "Arial, sans-serif",
            "fontSize": "14px",
            "whiteSpace": "normal",
            "height": "auto",
            "border": "1px solid #dee2e6",
            "minWidth": "120px",
            "maxWidth": "480px",
        },
        style_data={"border": "1px solid #dee2e6"},
        style_data_conditional=style_data_conditional,
        page_size=15,
        sort_action="native",
        filter_action="native",
        export_format="csv",
    )


def setup_ai_decision_callbacks(app):
    """Register callbacks for AI Generated Decision sub-tab."""

    @app.callback(
        Output("ai-decision-gemini-api-key-input", "value"),
        [
            Input("ai-decision-gemini-api-key-input", "value"),
            Input("ai-decision-gemini-api-key-input", "n_blur"),
            Input("ai-decision-gemini-api-key-input", "n_submit"),
            Input("ai-decision-gemini-api-key-input", "id"),
        ],
        prevent_initial_call=False,
    )
    def handle_ai_decision_gemini_api_key(value, n_blur, n_submit, component_id):
        ctx = dash.callback_context
        if not ctx.triggered:
            saved_key = _normalize_stored_string(data_storage.get_data("gemini_api_key"))
            data_storage.set_data("gemini_api_key", saved_key)
            return saved_key
        current_value = _normalize_stored_string(value)
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1]
        if trigger_prop != "id":
            data_storage.set_data("gemini_api_key", current_value)
        return current_value

    @app.callback(
        Output("ai-decision-gemini-api-file-input", "value"),
        [
            Input("ai-decision-gemini-api-file-input", "value"),
            Input("ai-decision-gemini-api-file-input", "n_blur"),
            Input("ai-decision-gemini-api-file-input", "n_submit"),
            Input("ai-decision-gemini-api-file-input", "id"),
        ],
        prevent_initial_call=False,
    )
    def handle_ai_decision_gemini_api_file(value, n_blur, n_submit, component_id):
        ctx = dash.callback_context
        default_file = r"C:\workspace\api\gemini.txt"
        if not ctx.triggered:
            saved_file = data_storage.get_data("gemini_api_file") or default_file
            data_storage.set_data("gemini_api_file", saved_file)
            return saved_file
        current_value = value if value else default_file
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1]
        if trigger_prop != "id":
            data_storage.set_data("gemini_api_file", current_value)
        return current_value

    @app.callback(
        [
            Output("ai-decision-gemini-model-select", "value"),
            Output("ai-decision-temperature-slider", "value"),
        ],
        [
            Input("ai-decision-gemini-model-select", "value"),
            Input("ai-decision-temperature-slider", "value"),
        ],
        prevent_initial_call=False,
    )
    def save_ai_decision_gemini_settings(model, temperature):
        ctx = dash.callback_context
        if not ctx.triggered:
            saved_model = data_storage.get_data("gemini_model") or "gemini-2.5-flash"
            saved_temp = float(data_storage.get_data("gemini_temperature") or 0.5)
            data_storage.set_data("gemini_model", saved_model)
            data_storage.set_data("gemini_temperature", saved_temp)
            return saved_model, saved_temp
        if model:
            data_storage.set_data("gemini_model", model)
        if temperature is not None:
            data_storage.set_data("gemini_temperature", float(temperature))
        current_model = data_storage.get_data("gemini_model") or "gemini-2.5-flash"
        current_temp = float(data_storage.get_data("gemini_temperature") or 0.5)
        return current_model, current_temp

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
            "Prompt ready with full project context. Copy and paste into your AI model.",
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

    @app.callback(
        Output("ai-decision-results-container", "children"),
        Input("generate-ai-decision-btn", "n_clicks"),
        [
            State("ai-decision-location-input", "value"),
            State("ai-decision-gemini-model-select", "value"),
            State("ai-decision-temperature-slider", "value"),
        ],
        prevent_initial_call=True,
    )
    def generate_ai_decision_results(n_clicks, location, model, temperature):
        if not n_clicks:
            return dash.no_update

        context = summarize_project_context()
        loc = _location_text(location) or _location_text(context.get("project_location"))
        if loc:
            context["project_location"] = loc
        display_location = loc or "this project"

        if not context or len(context) <= 1:
            return html.Div(
                [
                    dbc.Alert(
                        [
                            html.H5("Limited project data", className="alert-heading"),
                            html.P(
                                "Enter project data on Overview, Water Source, Hydro, Engineering, "
                                "and other tabs before generating AI scores.",
                                className="mb-0",
                            ),
                        ],
                        color="warning",
                    ),
                ]
            )

        try:
            model = model or data_storage.get_data("gemini_model") or "gemini-2.5-flash"
            temperature = (
                temperature
                if temperature is not None
                else data_storage.get_data("gemini_temperature") or 0.5
            )
            scores_df, explanations_df = get_engineering_decision_scores(
                model=model,
                temperature=temperature,
                context=context,
            )

            if scores_df is None or scores_df.empty:
                return html.Div(
                    [
                        dbc.Alert(
                            [
                                html.H5("No scores generated", className="alert-heading"),
                                html.P(
                                    "The model returned no feasibility scores. Try again or use Build Prompt.",
                                    className="mb-0",
                                ),
                            ],
                            color="warning",
                        ),
                    ]
                )

            top_row = scores_df.sort_values("rank").iloc[0] if "rank" in scores_df.columns else scores_df.iloc[0]
            top_option = str(top_row.get("engineering_option", "N/A"))
            top_score = float(top_row.get("feasibility_score", 0))

            return html.Div(
                [
                    _ai_decision_success_banner(display_location, top_option, top_score),
                    dbc.Alert(
                        [
                            html.P(
                                [
                                    html.Strong("Important Disclaimer: "),
                                    "These feasibility scores were produced by a Large Language Model "
                                    f"using MAR DSS project data for {display_location}. They support "
                                    "decision-making but do not replace engineering analysis, regulatory "
                                    "review, or site-specific design. Confirm conclusions with qualified "
                                    "professionals.",
                                ],
                                className="mb-0",
                            ),
                        ],
                        color="warning",
                        className="mb-3 py-2",
                    ),
                    html.H5("Option Feasibility Scores", className="mb-2"),
                    html.Div(
                        _scores_datatable(scores_df),
                        style={"overflowX": "auto", "width": "100%"},
                        className="mb-4",
                    ),
                    dcc.Graph(
                        id="ai-decision-scores-chart",
                        figure=_build_scores_chart(scores_df),
                        config={"displayModeBar": True, "responsive": True},
                    ),
                    html.Hr(className="my-4"),
                    html.H5("Decision Explanation", className="mb-2"),
                    html.P(
                        "Warnings, recommendations, rationale, and data gaps supporting the scores above.",
                        className="text-muted small mb-3",
                    ),
                    html.Div(
                        _explanations_datatable(explanations_df)
                        if explanations_df is not None and not explanations_df.empty
                        else dbc.Alert(
                            "No explanation rows were returned by the model.",
                            color="info",
                            className="py-2",
                        ),
                        style={"overflowX": "auto", "width": "100%"},
                    ),
                ]
            )

        except Exception as exc:
            return html.Div(
                [
                    dbc.Alert(
                        [
                            html.H5("Error generating AI decision scores", className="alert-heading"),
                            html.P(str(exc), className="mb-0"),
                        ],
                        color="danger",
                    ),
                ]
            )

    @app.callback(
        Output("ai-decision-temperature-display", "children"),
        Input("ai-decision-temperature-slider", "value"),
    )
    def update_ai_decision_temperature_display(temperature):
        if temperature is not None:
            return html.Span(f"Current value: {temperature:.1f}", className="text-muted")
        return html.Span("Current value: 0.5", className="text-muted")
