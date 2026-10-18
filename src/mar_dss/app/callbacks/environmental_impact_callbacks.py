"""
Callbacks for Environmental Impact tab - MAR Source Water Suitability Assessment.
"""

import dash
from dash import Input, Output, html, State, dcc, dash_table
import plotly.graph_objects as go
import pandas as pd
import dash_bootstrap_components as dbc
from mar_dss.app.components.environmental_impact_tab import (
    DECISION_LOGIC,
    TREATMENT_OPTIONS,
    TREATMENT_COST_MAP,
    VADOSE_REMEDIATION_COSTS,
    COST_SCALE_TO_SCORE,
    ASSESSMENT_QUESTION_LABELS,
    DEFAULT_WATER_QUALITY_RISK,
    TREATMENT_COST_FT3_MAX,
    WQ_BENIGN_ANSWERS,
    WQ_COLOR_HEX,
    WQ_COLOR_LABELS,
    WQ_COLOR_YELLOW,
    WQ_COMPONENT_IDS,
    WQ_LOGIC_KEYS,
    WQ_NO,
    WQ_QUESTIONS,
    WQ_TURBIDITY_LOW,
    WQ_UNKNOWN,
    WQ_YES,
    classify_wq_color,
    persist_wq_answer,
    _FT3_PER_M3,
)
from mar_dss.app.callbacks.ai_environment import (
    build_mar_factors_prompt,
    _location_text,
)
import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.utils.excel_table import (
    datatable_base_style_cell,
    datatable_base_style_header,
    datatable_computed_data_style,
)

def _format_usd_per_ft3(cost) -> str:
    """
    Format a $/ft³ estimate for display.

    Low unit costs (after m³→ft³ conversion) stay unrounded so they do not
    collapse to $0.00; larger values use four decimal places.
    """
    value = float(cost or 0.0)
    if value == 0:
        return "$0.00/ft³"
    if abs(value) < 0.01:
        text = f"{value:.10f}".rstrip("0").rstrip(".")
        return f"${text}/ft³"
    return f"${value:.4f}/ft³"


def _plotly_usd_per_ft3_format(cost) -> str:
    """Plotly d3 number format: extra decimals when the cost is very small."""
    value = float(cost or 0.0)
    if 0 < abs(value) < 0.01:
        return "$,.6f"
    return "$,.4f"


def calculate_cost_score(risks_and_treatments):
    """
    Calculate total costs based on required treatments.
    Separates vadose zone remediation costs from water treatment costs.
    Returns: (water_treatment_cost_per_ft3, vadose_remediation_total_cost, cost_details)
    - water_treatment_cost_per_ft3: estimated water treatment cost per ft³
    - vadose_remediation_total_cost: fixed estimate of $200,000 for vadose zone remediation
      (actual costs can vary from $50K to $10M depending on site conditions)
    - cost_details: list of cost breakdown details with sections
    """
    if not risks_and_treatments:
        return 0, 0, {'water_treatment': [], 'vadose_remediation': []}
    
    water_treatment_cost_per_m3 = 0
    vadose_remediation_cost_per_acreft = 0
    water_treatment_details = []
    vadose_remediation_details = []
    
    # Collect all treatments and their costs
    # For each risk factor, use the most expensive treatment option
    # Then sum across all risk factors (since multiple treatments may be needed)
    for risk_factor, treatments in risks_and_treatments:
        max_cost_for_risk = 0
        best_tech = None
        best_scale = None
        
        for tech_name, cost_scale in treatments:
            # Check if this is a vadose zone remediation treatment
            is_vadose_remediation = tech_name in VADOSE_REMEDIATION_COSTS
            
            if is_vadose_remediation:
                # Get cost from vadose remediation mapping (already in $/acre-ft)
                cost = VADOSE_REMEDIATION_COSTS.get(tech_name, 0)
            elif tech_name in TREATMENT_COST_MAP:
                # Get cost from water treatment mapping (in $/m³)
                cost = TREATMENT_COST_MAP[tech_name]
            else:
                # Try to extract from cost scale
                cost = COST_SCALE_TO_SCORE.get(cost_scale, 0) * 50  # Rough estimate: score * 50 ($/m³)
            
            # Track the most expensive treatment for this risk factor
            if cost > max_cost_for_risk:
                max_cost_for_risk = cost
                best_tech = tech_name
                best_scale = cost_scale
        
        if max_cost_for_risk > 0:
            # Separate vadose zone remediation from water treatment
            is_vadose = best_tech in VADOSE_REMEDIATION_COSTS
            if is_vadose:
                vadose_remediation_cost_per_acreft += max_cost_for_risk
                vadose_remediation_details.append({
                    'risk_factor': risk_factor,
                    'technology': best_tech,
                    'cost_per_acreft': max_cost_for_risk,
                    'cost_scale': best_scale
                })
            else:
                water_treatment_cost_per_m3 += max_cost_for_risk
                water_treatment_details.append({
                    'risk_factor': risk_factor,
                    'technology': best_tech,
                    'cost_per_m3': max_cost_for_risk,
                    'cost_scale': best_scale
                })
    
    # Convert water treatment cost from $/m³ to $/ft³
    water_treatment_cost_per_ft3 = (
        water_treatment_cost_per_m3 / _FT3_PER_M3 if water_treatment_cost_per_m3 > 0 else 0
    )
    
    # Update water treatment details to show cost per ft³
    for detail in water_treatment_details:
        if 'cost_per_m3' in detail:
            detail['cost_per_ft3'] = detail['cost_per_m3'] / _FT3_PER_M3
    
    # Vadose zone remediation is a one-time site cost
    # Use fixed total cost estimate of $200,000
    # Note: Actual costs can vary by orders of magnitude ($50K - $10M) depending on:
    # - Contaminant type and concentration
    # - Site size and depth
    # - Remediation technology required
    # - Regulatory requirements
    vadose_remediation_total_cost = 200000 if vadose_remediation_cost_per_acreft > 0 else 0
    
    # Combine cost details with sections
    cost_details = {
        'water_treatment': water_treatment_details,
        'vadose_remediation': vadose_remediation_details
    }
    
    # Return unrounded $/ft³ so low unit costs remain visible in reporting.
    return (
        float(water_treatment_cost_per_ft3),
        round(vadose_remediation_total_cost, 2),
        cost_details,
    )


def generate_required_treatment_summary(risks_and_treatments):
    """Generate the treatment summary table."""
    if not risks_and_treatments:
        return html.P("No specific treatment required based on inputs", className="text-muted")

    df_data = []
    for risk, treatments in risks_and_treatments:
        for tech, cost in treatments:
            df_data.append({
                "Question": risk,
                "Treatment Technology": tech,
                "Cost Scale": cost,
            })
    
    if not df_data:
        return html.P("No specific treatment required based on inputs", className="text-muted")

    import pandas as pd
    df = pd.DataFrame(df_data).drop_duplicates()
    
    # Sort by a custom cost scale (heuristic)
    cost_order = {
        "Low": 1, 
        "Low to Moderate": 2, 
        "Moderate": 3, 
        "Moderate to High": 4, 
        "High": 5, 
        "Very High": 6, 
        "Very High - Prohibitive": 7, 
        "Moderate + High Study": 3.5, 
        "Moderate Study Cost": 3
    }
    df['Sort_Order'] = df['Cost Scale'].apply(lambda x: cost_order.get(x, 10))
    df = df.sort_values(by=['Sort_Order', 'Question']).drop(columns=['Sort_Order'])

    return html.Div(
        dash_table.DataTable(
            id='env-treatment-summary-table',
            columns=[{"name": i, "id": i} for i in df.columns],
            data=df.to_dict('records'),
            style_header=datatable_base_style_header(textAlign='left'),
            style_cell=datatable_base_style_cell(
                textAlign='left',
                minWidth='100px',
                width='100px',
                maxWidth='300px',
                whiteSpace='normal',
            ),
            style_data=datatable_computed_data_style(whiteSpace='normal'),
        ),
        className='treatment-table'
    )


def setup_environmental_impact_callbacks(app):
    """Set up callbacks for the Environmental Impact tab."""

    @app.callback(
        Output("treatment-cost-guidance-collapse", "is_open"),
        Input("view-treatment-cost-guidance-check", "value"),
        prevent_initial_call=True,
    )
    def toggle_treatment_cost_guidance(view_costs):
        """Show or hide Treatment Cost Estimates when the view checkbox changes."""
        checked = bool(view_costs)
        dash_storage.set_data("view_treatment_cost_guidance", checked)
        return checked

    @app.callback(
        [
            Output('env-wq-color-scale', 'children'),
            Output('env-cost-gauge', 'figure'),
            Output('env-cost-details-output', 'children'),
            Output('env-treatment-summary-output', 'children'),
            Output('env-recommendations-list', 'children')
        ],
        [
            Input(component_id, "value")
            for component_id in WQ_COMPONENT_IDS
        ] + [Input("app-container", "className")],
    )
    def update_dashboard(*args):
        """Update the dashboard based on input selections."""
        if len(args) == len(WQ_COMPONENT_IDS) + 1:
            inputs = list(args[:-1])
            container_class = args[-1]
        else:
            inputs = list(args)
            container_class = ""
        is_dark = "mar-theme-dark" in str(container_class or "")
        gauge_font = "#f8f9fa" if is_dark else "#212529"

        # Validate inputs - ensure they're not None
        inputs = [
            inp if inp is not None else DEFAULT_WATER_QUALITY_RISK
            for inp in inputs
        ]
        
        # Map inputs to logic keys
        input_keys = list(WQ_LOGIC_KEYS)
        answers = dict(zip(input_keys, inputs))
        wq_color = classify_wq_color(answers)

        # Collect all required treatments and recommendations
        required_treatments_raw = []
        recommendations_list = []

        # 1. Collect per-question details (treatments / recommendations)
        for key, value in zip(input_keys, inputs):
            step_logic = DECISION_LOGIC[key]
            score_data = step_logic.get(value, {"score": 0, "color": "dark", "treatment_key": "", "rec": "No data."})
            
            treatment_key = score_data['treatment_key']
            recommendation = score_data['rec']
            
            # Aggregate treatments
            if treatment_key in TREATMENT_OPTIONS:
                risk_factor_name = ASSESSMENT_QUESTION_LABELS.get(key, key)
                required_treatments_raw.append((risk_factor_name, TREATMENT_OPTIONS[treatment_key]))
            
            # Aggregate recommendations
            if value == WQ_UNKNOWN and recommendation:
                recommendations_list.append(
                    html.Li(
                        f"**{ASSESSMENT_QUESTION_LABELS.get(key, key)}: {value}** - {recommendation}",
                        className="list-group-item list-group-item-action list-group-item-warning",
                    )
                )
            elif value not in WQ_BENIGN_ANSWERS and recommendation:
                recommendations_list.append(
                    html.Li(
                        f"**{ASSESSMENT_QUESTION_LABELS.get(key, key)}: {value}** - {recommendation}", 
                        className="list-group-item list-group-item-action list-group-item-" + score_data['color']
                    )
                )

        # 2. Color scale indicator
        color_hex = WQ_COLOR_HEX[wq_color]
        label_text = WQ_COLOR_LABELS[wq_color]
        text_on_swatch = "#212529" if wq_color == WQ_COLOR_YELLOW else "#ffffff"

        color_scale_children = html.Div(
            [
                html.Div(
                    label_text,
                    className="fw-bold text-center py-4 px-3 rounded",
                    style={
                        "backgroundColor": color_hex,
                        "color": text_on_swatch,
                        "fontSize": "1.15rem",
                        "border": "1px solid #ced4da",
                    },
                ),
                html.Ul(
                    [
                        html.Li("Green: all No and turbidity <5 NTU"),
                        html.Li("Yellow: Yes on question 1, 3, or 5 (or Unknown / elevated turbidity)"),
                        html.Li("Red: Yes on question 4"),
                    ],
                    className="small text-muted mt-2 mb-0 ps-3",
                ),
            ]
        )

        # 3. Calculate Costs
        water_treatment_cost_per_ft3, vadose_remediation_total_cost, cost_details = calculate_cost_score(required_treatments_raw)
        
        # 4. Create Cost Gauge Plot (axis max = theoretical worst-case $/ft³)
        try:
            # Never clip the needle: expand if an unexpected value exceeds the map max
            cost_axis_max = max(
                float(TREATMENT_COST_FT3_MAX),
                float(water_treatment_cost_per_ft3) * 1.05,
                0.05,
            )
            usd_ft3_format = _plotly_usd_per_ft3_format(water_treatment_cost_per_ft3)
            cost_gauge_fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=water_treatment_cost_per_ft3,
                domain={'x': [0, 1], 'y': [0, 1]},
                title={
                    'text': "Estimated Water Treatment Cost ($/ft³)",
                    'font': {'size': 16, 'color': gauge_font},
                },
                number={
                    'valueformat': usd_ft3_format,
                    'suffix': '/ft³',
                    'font': {'color': gauge_font},
                },
                gauge={
                    'axis': {
                        'range': [0, cost_axis_max],
                        'tickwidth': 1,
                        'tickcolor': gauge_font,
                        'tickformat': usd_ft3_format,
                    },
                    'bar': {'color': "darkorange"},
                    'bgcolor': "white",
                    'borderwidth': 2,
                    'bordercolor': "gray",
                    'steps': [
                        {'range': [0, cost_axis_max * 0.2], 'color': 'lightgreen'},
                        {'range': [cost_axis_max * 0.2, cost_axis_max * 0.4], 'color': 'yellow'},
                        {'range': [cost_axis_max * 0.4, cost_axis_max * 0.6], 'color': 'orange'},
                        {'range': [cost_axis_max * 0.6, cost_axis_max * 0.8], 'color': 'lightcoral'},
                        {'range': [cost_axis_max * 0.8, cost_axis_max], 'color': 'red'},
                    ],
                    'threshold': {
                        'line': {'color': "red", 'width': 4},
                        'thickness': 0.75,
                        'value': min(water_treatment_cost_per_ft3, cost_axis_max),
                    },
                },
            ))
            cost_gauge_fig.update_layout(
                margin=dict(l=10, r=10, t=60, b=10), 
                height=250,
                autosize=True,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font={'color': gauge_font},
            )
        except Exception as e:
            # Fallback figure if there's an error
            cost_gauge_fig = go.Figure()
            cost_gauge_fig.add_annotation(
                text=f"Error creating cost gauge: {str(e)}",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False
            )
            cost_gauge_fig.update_layout(height=250)
        
        # 5. Generate Cost Details Output (with two sections)
        cost_details_html = []
        
        # Section 1: Water Treatment Costs
        water_treatment_details = cost_details.get('water_treatment', [])
        vadose_remediation_details = cost_details.get('vadose_remediation', [])
        
        if water_treatment_details or vadose_remediation_details:
            # Water Treatment Section
            if water_treatment_details:
                cost_details_html.append(html.H6("Estimated Water Treatment Costs (per ft3 of water)", className="font-weight-bold mt-3 mb-2 text-primary"))
                cost_details_html.append(html.P(
                    f"Total Water Treatment Cost: {_format_usd_per_ft3(water_treatment_cost_per_ft3)}",
                    className="font-weight-bold mb-2",
                ))
                for detail in water_treatment_details:
                    cost_per_ft3 = detail.get('cost_per_ft3', 0)
                    if cost_per_ft3 > 0:
                        cost_details_html.append(html.Div([
                            html.Span(f"{detail['risk_factor']}: {detail['technology']}", className="font-weight-bold"),
                            html.Span(
                                _format_usd_per_ft3(cost_per_ft3),
                                className="fw-semibold",
                                style={"color": "#000"},
                            ),
                        ], className="d-flex justify-content-between mb-1 p-2 rounded", style={
                            "background-color": "#fff3cd",
                            "border-left": "4px solid #ffc107",
                            "color": "#000",
                        }))
            
            # Vadose Zone Remediation Section
            if vadose_remediation_details:
                cost_details_html.append(html.H6("(2) Vadose Zone Remediation Costs (Total Project Cost)", className="font-weight-bold mt-3 mb-2 text-danger"))
                cost_details_html.append(html.P([
                    html.Strong(f"Estimated Total Vadose Zone Remediation Cost: ${vadose_remediation_total_cost:,.0f}"),
                ], className="font-weight-bold mb-2"))
                cost_details_html.append(html.Div([
                    html.P([
                        html.Strong("Note: "),
                        "This is a one-time total project cost estimate, not a per-volume ($/ft³) unit cost, "
                        "so it is not included on the Estimated Water Treatment Cost gauge. "
                        "Vadose zone remediation costs can vary by orders of magnitude depending on contaminant type, "
                        "site size, depth, remediation technology, and regulatory requirements. "
                        "Typical range: $50,000 - $10,000,000. "
                        "The estimate above ($200,000) represents a mid-range scenario. "
                        "Consult with remediation specialists for site-specific cost estimates."
                    ], className="text-muted mb-2", style={"fontSize": "0.9rem", "fontStyle": "italic"})
                ], className="alert alert-warning mb-3"))
                for detail in vadose_remediation_details:
                    cost_per_acreft = detail.get('cost_per_acreft', 0)
                    if cost_per_acreft > 0:
                        cost_details_html.append(html.Div([
                            html.Span(f"{detail['risk_factor']}: {detail['technology']}", className="font-weight-bold"),
                            html.Span(
                                f"${cost_per_acreft:,.0f}/acre-ft",
                                className="fw-semibold",
                                style={"color": "#000"},
                            ),
                        ], className="d-flex justify-content-between mb-1 p-2 rounded", style={
                            "background-color": "#f8d7da",
                            "border-left": "4px solid #dc3545",
                            "color": "#000",
                        }))
        else:
            cost_details_html = [
                html.P("No treatment required. Water Treatment Cost: $0.00/ft³", className="text-muted")
            ]
        
        # 6. Generate Treatment Summary Table
        treatment_summary_table = generate_required_treatment_summary(required_treatments_raw)
        
        # 7. Format Recommendations
        if not recommendations_list:
            if all(v in (WQ_UNKNOWN, WQ_NO, WQ_TURBIDITY_LOW) for v in inputs):
                has_unknown = any(v == WQ_UNKNOWN for v in inputs)
                recommendations_list = [
                    html.Li(
                        "All screening answers are Unknown or No (or turbidity <5 NTU). "
                        "Collect water quality data where marked Unknown.",
                        className=(
                            "list-group-item list-group-item-warning"
                            if has_unknown
                            else "list-group-item list-group-item-secondary"
                        ),
                    )
                ]
            else:
                recommendations_list = [
                    html.Li(
                        "No treatment recommendations were triggered by the current answers.",
                        className="list-group-item list-group-item-success",
                    )
                ]
            
        return (
            color_scale_children,
            cost_gauge_fig,
            cost_details_html,
            treatment_summary_table,
            recommendations_list,
        )
    
    # Callbacks to save water quality inputs to data storage
    def _register_wq_persist(storage_key, component_id):
        @app.callback(
            Output(component_id, "value"),
            Input(component_id, "value"),
            prevent_initial_call=False,
        )
        def _handle_wq_answer(value):
            return persist_wq_answer(storage_key, value)

        return _handle_wq_answer

    for _wq_question in WQ_QUESTIONS:
        _register_wq_persist(
            _wq_question["storage_key"],
            _wq_question["component_id"],
        )


    @app.callback(
        [
            Output("mar-factors-prompt-display", "value"),
            Output("mar-prompt-feedback", "children"),
        ],
        Input("build-mar-factors-prompt-btn", "n_clicks"),
        State("project-location-store", "data"),
        prevent_initial_call=True,
    )
    def build_mar_factors_prompt_display(n_clicks, store_location):
        """Fill the prompt textarea using Overview Project Location."""
        if not n_clicks:
            return dash.no_update, dash.no_update

        location = _location_text(store_location) or _location_text(
            dash_storage.get_data("project_location")
        )
        if not location:
            return "", dbc.Alert(
                "Set Project Location on the (1) Overview tab before building the prompt.",
                color="warning",
                className="py-2 mb-0 small",
            )

        prompt = build_mar_factors_prompt(location)
        feedback = html.Small(
            f"Prompt ready for {location}. Click Copy Prompt, then paste it into "
            "your preferred AI model.",
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
        Output("mar-prompt-feedback", "children", allow_duplicate=True),
        Input("copy-mar-factors-prompt-btn", "n_clicks"),
        State("mar-factors-prompt-display", "value"),
        prevent_initial_call=True,
    )
