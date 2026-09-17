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
    RISK_SCORE_MAX,
    RISK_SCORE_SUITABLE_MAX,
    RISK_SCORE_CONDITIONAL_MAX,
    RISK_SCORE_UNSUITABLE_MIN,
    TREATMENT_COST_FT3_MAX,
    WQ_BENIGN_ANSWERS,
    WQ_COMPONENT_IDS,
    WQ_LOGIC_KEYS,
    WQ_NO,
    WQ_QUESTIONS,
    WQ_UNKNOWN,
    WQ_YES,
    persist_wq_answer,
    _FT3_PER_M3,
)
from mar_dss.app.callbacks.ai_environment import (
    get_mar_factors,
    _normalize_stored_string,
    build_mar_factors_prompt,
    _location_text,
)
from mar_dss.app.utils.tab_tooltips import dash_table_tooltip_kwargs
import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.utils.excel_table import (
    datatable_base_style_cell,
    datatable_base_style_header,
    datatable_computed_data_style,
)

_WQ_DETAIL_BG = {
    WQ_UNKNOWN: "#e2e3e5",
    WQ_NO: "#d4edda",
    "<5 NTU": "#d4edda",
    "5-20 NTU": "#fff3cd",
    ">20 NTU": "#f8d7da",
    WQ_YES: "#f8d7da",
}
_WQ_DETAIL_FG = {
    WQ_UNKNOWN: "#383d41",
    WQ_NO: "#155724",
    "<5 NTU": "#155724",
    "5-20 NTU": "#856404",
    ">20 NTU": "#721c24",
    WQ_YES: "#721c24",
}


def _mar_factors_success_banner(location, count):
    """Green banner shown after Gemini successfully returns factors."""
    return dbc.Alert(
        [
            html.I(className="fas fa-check-circle me-2"),
            html.Strong("Generation complete. "),
            html.Span(
                f"{count} MAR factors were generated for {location}. ",
            ),
            html.Span(
                "Review the results below.",
                className="fw-semibold",
            ),
        ],
        color="success",
        className="mb-3",
    )


def _wq_detail_colors(value):
    """Background and text colors for a screening answer in the score-details list."""
    return (
        _WQ_DETAIL_BG.get(value, "#f8f9fa"),
        _WQ_DETAIL_FG.get(value, "#000000"),
    )


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
    
    return round(water_treatment_cost_per_ft3, 2), round(vadose_remediation_total_cost, 2), cost_details


def generate_required_treatment_summary(risks_and_treatments):
    """Generate the treatment summary table."""
    if not risks_and_treatments:
        return html.P("No specific treatment required based on inputs.", className="text-muted")

    df_data = []
    for risk, treatments in risks_and_treatments:
        for tech, cost in treatments:
            df_data.append({
                "Risk Factor": risk,
                "Treatment Technology": tech,
                "Cost Scale": cost,
            })
    
    if not df_data:
        return html.P("No specific treatment required based on inputs.", className="text-muted")

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
    df = df.sort_values(by=['Sort_Order', 'Risk Factor']).drop(columns=['Sort_Order'])

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
        [
            Output('env-final-decision-output', 'children'),
            Output('env-final-decision-output', 'style'),
            Output('env-score-gauge', 'figure'),
            Output('env-cost-gauge', 'figure'),
            Output('env-score-details-output', 'children'),
            Output('env-cost-details-output', 'children'),
            Output('env-treatment-summary-output', 'children'),
            Output('env-recommendations-list', 'children')
        ],
        [
            Input(component_id, "value")
            for component_id in WQ_COMPONENT_IDS
        ]
    )
    def update_dashboard(*inputs):
        """Update the dashboard based on input selections."""
        # Validate inputs - ensure they're not None
        inputs = [
            inp if inp is not None else DEFAULT_WATER_QUALITY_RISK
            for inp in inputs
        ]
        
        # Map inputs to logic keys
        input_keys = list(WQ_LOGIC_KEYS)
        
        total_score = 0
        risk_details = []
        
        # Critical flags tracking
        critical_flags = []
        
        # Collect all required treatments and recommendations
        required_treatments_raw = []
        recommendations_list = []

        # 1. Calculate Score and Collect Details
        for key, value in zip(input_keys, inputs):
            step_logic = DECISION_LOGIC[key]
            score_data = step_logic.get(value, {"score": 0, "color": "dark", "treatment_key": "", "rec": "No data."})
            
            score = score_data['score']
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
                        className="list-group-item list-group-item-action list-group-item-secondary",
                    )
                )
            elif value not in WQ_BENIGN_ANSWERS and recommendation:
                recommendations_list.append(
                    html.Li(
                        f"**{ASSESSMENT_QUESTION_LABELS.get(key, key)}: {value}** - {recommendation}", 
                        className="list-group-item list-group-item-action list-group-item-" + score_data['color']
                    )
                )
            
            # Only add to total score if not a critical flag
            if score > 0:
                total_score += score
            
            bg_color, text_color = _wq_detail_colors(value)
            
            risk_details.append(html.Div([
                html.Span(
                    f"{ASSESSMENT_QUESTION_LABELS.get(key, key)}: {value}",
                    className="font-weight-bold",
                ),
                html.Span(
                    f"Score: {score} pt(s)",
                    className="fw-semibold",
                    style={"color": "#000"},
                ),
            ], className="d-flex justify-content-between mb-1 p-2 rounded", style={
                "background-color": bg_color,
                "color": text_color,
                "border-left": f"4px solid {text_color}"
            }))

        # 2. Determine Final Decision
        result_style = {
            "padding": "20px",
            "border-radius": "8px",
            "color": "white",
            "text-align": "center"
        }
        
        # Check Critical Flags first
        if critical_flags or total_score >= RISK_SCORE_UNSUITABLE_MIN:
            result_style["background-color"] = "#dc3545"  # Red for not suitable
            
            reasons_for_rejection = [
                html.P("The source water is **NOT SUITABLE** for MAR at this location.", className="lead font-weight-bold")
            ]
            reasons_for_rejection.append(html.P(f"Total Risk Score: {total_score} points (Threshold: {RISK_SCORE_UNSUITABLE_MIN}+)", className="mb-2"))
            
            if critical_flags:
                reasons_for_rejection.append(html.H6("⚠️ Critical Flags Triggered:"))
                reasons_for_rejection.extend([html.Li(flag, className="text-white text-left") for flag in critical_flags])
            
            reasons_for_rejection.append(
                html.P("Recommended Action: **Evaluate alternative sources/locations.**", className="mt-3 font-weight-bold")
            )
            
            decision_content = reasons_for_rejection

        elif RISK_SCORE_SUITABLE_MAX < total_score <= RISK_SCORE_CONDITIONAL_MAX:
            result_style["background-color"] = "#ffc107"  # Orange/Yellow for conditionally suitable
            result_style["color"] = "#343a40"  # Dark text for better contrast
            
            decision_content = [
                html.P("The source water is **CONDITIONALLY SUITABLE** for MAR.", className="lead font-weight-bold"),
                html.P(f"Total Risk Score: {total_score} points (Range: {RISK_SCORE_SUITABLE_MAX + 1}–{RISK_SCORE_CONDITIONAL_MAX})"),
                html.P("Requires specific treatment and further studies to confirm economic viability and technical feasibility.", className="mt-2"),
                html.P("Action: **Proceed to required treatability/modeling studies.**", className="mt-3 font-weight-bold")
            ]
            
        else:  # total_score <= RISK_SCORE_SUITABLE_MAX
            result_style["background-color"] = "#28a745"  # Green for suitable
            
            decision_content = [
                html.P("The source water is **SUITABLE** for MAR implementation.", className="lead font-weight-bold"),
                html.P(f"Total Risk Score: {total_score} points (Range: 0–{RISK_SCORE_SUITABLE_MAX})"),
                html.P("Minimal to no treatment required. Low implementation cost.", className="mt-2")
            ]

        # 3. Create Gauge Plot (axis max = theoretical max sum of all step scores)
        try:
            gauge_fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=total_score,
                domain={'x': [0, 1], 'y': [0, 1]},
                title={
                    'text': f"Total Risk Score (max {RISK_SCORE_MAX})",
                    'font': {'size': 18},
                },
                gauge={
                    'axis': {
                        'range': [0, RISK_SCORE_MAX],
                        'tickwidth': 1,
                        'tickcolor': "darkblue",
                        'dtick': 5,
                    },
                    'bar': {'color': "darkslategray"},
                    'bgcolor': "white",
                    'borderwidth': 2,
                    'bordercolor': "gray",
                    'steps': [
                        {
                            'range': [0, RISK_SCORE_SUITABLE_MAX + 1],
                            'color': 'lightgreen',
                        },
                        {
                            'range': [
                                RISK_SCORE_SUITABLE_MAX + 1,
                                RISK_SCORE_UNSUITABLE_MIN,
                            ],
                            'color': 'yellow',
                        },
                        {
                            'range': [RISK_SCORE_UNSUITABLE_MIN, RISK_SCORE_MAX],
                            'color': 'red',
                        },
                    ],
                    'threshold': {
                        'line': {'color': "red", 'width': 4},
                        'thickness': 0.75,
                        'value': min(total_score, RISK_SCORE_MAX),
                    },
                },
            ))
            gauge_fig.update_layout(
                margin=dict(l=10, r=10, t=50, b=10), 
                height=250,
                autosize=True,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
        except Exception as e:
            # Fallback figure if there's an error
            gauge_fig = go.Figure()
            gauge_fig.add_annotation(
                text=f"Error creating gauge: {str(e)}",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False
            )
            gauge_fig.update_layout(height=250)

        # 4. Calculate Costs
        water_treatment_cost_per_ft3, vadose_remediation_total_cost, cost_details = calculate_cost_score(required_treatments_raw)
        
        # 5. Create Cost Gauge Plot (axis max = theoretical worst-case $/ft³)
        try:
            # Never clip the needle: expand if an unexpected value exceeds the map max
            cost_axis_max = max(
                float(TREATMENT_COST_FT3_MAX),
                float(water_treatment_cost_per_ft3) * 1.05,
                0.05,
            )
            cost_gauge_fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=water_treatment_cost_per_ft3,
                domain={'x': [0, 1], 'y': [0, 1]},
                title={
                    'text': (
                        f"Water Treatment Cost ($/ft³)<br>"
                        f"<span style='font-size:12px'>scale max ${cost_axis_max:.2f}/ft³</span>"
                    ),
                    'font': {'size': 16},
                },
                number={'valueformat': '$,.2f', 'suffix': '/ft³'},
                gauge={
                    'axis': {
                        'range': [0, cost_axis_max],
                        'tickwidth': 1,
                        'tickcolor': "darkblue",
                        'tickformat': '$,.2f',
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
                plot_bgcolor='rgba(0,0,0,0)'
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
        
        # 6. Generate Cost Details Output (with two sections)
        cost_details_html = []
        
        # Section 1: Water Treatment Costs
        water_treatment_details = cost_details.get('water_treatment', [])
        vadose_remediation_details = cost_details.get('vadose_remediation', [])
        
        if water_treatment_details or vadose_remediation_details:
            # Water Treatment Section
            if water_treatment_details:
                cost_details_html.append(html.H6("(1) Water Treatment Costs (per ft³ of source water)", className="font-weight-bold mt-3 mb-2 text-primary"))
                cost_details_html.append(html.P(f"Total Water Treatment Cost: ${water_treatment_cost_per_ft3:.2f}/ft³", className="font-weight-bold mb-2"))
                for detail in water_treatment_details:
                    cost_per_ft3 = detail.get('cost_per_ft3', 0)
                    if cost_per_ft3 > 0:
                        cost_details_html.append(html.Div([
                            html.Span(f"{detail['risk_factor']}: {detail['technology']}", className="font-weight-bold"),
                            html.Span(
                                f"${cost_per_ft3:.2f}/ft³",
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
        
        # 7. Generate Treatment Summary Table
        treatment_summary_table = generate_required_treatment_summary(required_treatments_raw)
        
        # 8. Format Recommendations
        if not recommendations_list:
            if all(v in (WQ_UNKNOWN, WQ_NO, "<5 NTU") for v in inputs):
                recommendations_list = [
                    html.Li(
                        "All screening answers are Unknown or No (or turbidity <5 NTU). "
                        "Collect water quality data where marked Unknown.",
                        className="list-group-item list-group-item-secondary",
                    )
                ]
            else:
                recommendations_list = [
                    html.Li(
                        "No treatment recommendations were triggered by the current answers.",
                        className="list-group-item list-group-item-success",
                    )
                ]
            
        return decision_content, result_style, gauge_fig, cost_gauge_fig, risk_details, cost_details_html, treatment_summary_table, recommendations_list
    
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

    # Callback to load and auto-save Gemini API key
    @app.callback(
        Output('gemini-api-key-input', 'value'),
        [
            Input('gemini-api-key-input', 'value'),
            Input('gemini-api-key-input', 'n_blur'),
            Input('gemini-api-key-input', 'n_submit'),
            Input('gemini-api-key-input', 'id')
        ],
        prevent_initial_call=False
    )
    def handle_gemini_api_key(value, n_blur, n_submit, component_id):
        """Handle Gemini API key input and save to data storage."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved value or use default
            saved_key = _normalize_stored_string(dash_storage.get_data("gemini_api_key"))
            dash_storage.set_data("gemini_api_key", saved_key)
            return saved_key
        
        # Get the current value
        current_value = _normalize_stored_string(value)
        
        # Determine which trigger caused the callback
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1]
        
        # Save for all triggers except initial load
        if trigger_prop != "id":
            dash_storage.set_data("gemini_api_key", current_value)
        
        return current_value
    
    # Callback to load and auto-save Gemini API file path
    @app.callback(
        Output('gemini-api-file-input', 'value'),
        [
            Input('gemini-api-file-input', 'value'),
            Input('gemini-api-file-input', 'n_blur'),
            Input('gemini-api-file-input', 'n_submit'),
            Input('gemini-api-file-input', 'id')
        ],
        prevent_initial_call=False
    )
    def handle_gemini_api_file(value, n_blur, n_submit, component_id):
        """Handle Gemini API file path input and save to data storage."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved value or use default
            saved_file = dash_storage.get_data("gemini_api_file") or r"C:\workspace\api\gemini.txt"
            dash_storage.set_data("gemini_api_file", saved_file)
            return saved_file
        
        # Get the current value
        current_value = value if value else r"C:\workspace\api\gemini.txt"
        
        # Determine which trigger caused the callback
        trigger_prop = ctx.triggered[0]["prop_id"].split(".")[1]
        
        # Save for all triggers except initial load
        if trigger_prop != "id":
            dash_storage.set_data("gemini_api_file", current_value)
        
        return current_value
    
    # Callback to save Gemini model and temperature
    @app.callback(
        [
            Output('gemini-model-select', 'value'),
            Output('temperature-slider', 'value')
        ],
        [
            Input('gemini-model-select', 'value'),
            Input('temperature-slider', 'value')
        ],
        prevent_initial_call=False
    )
    def save_gemini_settings(model, temperature):
        """Save Gemini model and temperature settings to data storage."""
        ctx = dash.callback_context
        
        if not ctx.triggered:
            # Initial load - get saved values or use defaults
            saved_model = dash_storage.get_data("gemini_model") or "gemini-2.5-flash"
            saved_temp = float(dash_storage.get_data("gemini_temperature") or 0.5)
            dash_storage.set_data("gemini_model", saved_model)
            dash_storage.set_data("gemini_temperature", saved_temp)
            return saved_model, saved_temp
        
        # Save current values
        if model:
            dash_storage.set_data("gemini_model", model)
        if temperature is not None:
            dash_storage.set_data("gemini_temperature", float(temperature))
        
        # Get current values from storage
        current_model = dash_storage.get_data("gemini_model") or "gemini-2.5-flash"
        current_temp = float(dash_storage.get_data("gemini_temperature") or 0.5)
        return current_model, current_temp
    
    @app.callback(
        Output("mar-location-input", "value"),
        [
            Input("project-location-store", "data"),
            Input("mar-location-input", "id"),
        ],
        prevent_initial_call=False,
    )
    def sync_mar_location_from_project_location(store_location, _component_id):
        """Keep tab 4.2 location aligned with Overview Project Location."""
        loc = _location_text(store_location or dash_storage.get_data("project_location"))
        return loc

    @app.callback(
        [
            Output("mar-factors-prompt-display", "value"),
            Output("mar-prompt-feedback", "children"),
        ],
        Input("build-mar-factors-prompt-btn", "n_clicks"),
        State("mar-location-input", "value"),
        prevent_initial_call=True,
    )
    def build_mar_factors_prompt_display(n_clicks, location):
        """Fill the prompt textarea for copy/paste into an external AI model."""
        if not n_clicks:
            return dash.no_update, dash.no_update

        location = _location_text(location) or _location_text(
            dash_storage.get_data("project_location")
        )
        if not location:
            return "", dbc.Alert(
                "Enter a location first, or set Project Location on the Overview tab.",
                color="warning",
                className="py-2 mb-0 small",
            )

        prompt = build_mar_factors_prompt(location)
        feedback = html.Small(
            "Prompt ready. Click Copy Prompt or select all text and paste into your AI model.",
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

    # Callback for MAR Factors Generation (Tab 4.2)
    @app.callback(
        Output('mar-factors-table-container', 'children'),
        [
            Input('generate-mar-factors-btn', 'n_clicks')
        ],
        [
            State('mar-location-input', 'value'),
            State('gemini-model-select', 'value'),
            State('temperature-slider', 'value')
        ],
        prevent_initial_call=True
    )
    def generate_mar_factors_table(n_clicks, location, model, temperature):
        """Generate MAR factors table using AI."""
        if not n_clicks:
            return dash.no_update

        location = _location_text(location) or _location_text(
            dash_storage.get_data("project_location")
        )
        if not location:
            return html.Div([
                dbc.Alert([
                    html.H5("Location required", className="alert-heading"),
                    html.P(
                        "Enter a location above, or set Project Location on the Overview tab.",
                        className="mb-0",
                    ),
                ], color="warning"),
            ])
        
        try:
            # Get API key from data storage
            # check if api file exist in C:\workspace\projects\MAR_ESCTP\scripts\mar_dss\src\mar_dss\app
            
            api_key = dash_storage.get_data("gemini_api_key")
            # if not api_key:
            #     return html.Div([
            #         dbc.Alert([
            #             html.H5("API Key Required", className="alert-heading"),
            #             html.P("Please enter and save your Gemini API key in the control panel above before generating MAR factors.", className="mb-0")
            #         ], color="warning")
            #     ])
            # else:
            #     pass
            # Get model and temperature from storage or use provided values
            model = model or dash_storage.get_data("gemini_model") or "gemini-2.5-flash"
            temperature = temperature if temperature is not None else dash_storage.get_data("gemini_temperature") or 0.5
            
            # Call the AI function (this may take a moment)
            df = get_mar_factors(location, model=model, temperature=temperature)
            
            if df is None or df.empty:
                return html.Div([
                    dbc.Alert([
                        html.H5("No Data Generated", className="alert-heading"),
                        html.P("No factors were generated. Please try again with a different location.", className="mb-0")
                    ], color="warning")
                ])
            
            # Create styled table with colors based on priority (only for Priority column)
            # Define color schemes for priority
            priority_colors = {
                'High': {'bg': '#f8d7da', 'text': '#721c24'},
                'Medium': {'bg': '#fff3cd', 'text': '#856404'},
                'Low': {'bg': '#d4edda', 'text': '#155724'}
            }
            
            # Create conditional styling for Priority column cells only
            style_data_conditional = []
            for idx, row in df.iterrows():
                priority = str(row.get('priority', '')).strip()
                if priority in priority_colors:
                    colors = priority_colors[priority]
                    style_data_conditional.append({
                        'if': {
                            'row_index': idx,
                            'column_id': 'priority'
                        },
                        'backgroundColor': colors['bg'],
                        'color': colors['text'],
                        'fontWeight': 'bold'
                    })
            
            # Create the table
            table = dash_table.DataTable(
                id='mar-factors-datatable',
                columns=[
                    {"name": "Category", "id": "category"},
                    {"name": "Data Point/Factor", "id": "data_point"},
                    {"name": "Priority", "id": "priority"},
                    {"name": "Justification", "id": "justification"}
                ],
                data=df.to_dict('records'),
                style_header=datatable_base_style_header(
                    textAlign='left',
                    fontSize='16px',
                ),
                style_cell=datatable_base_style_cell(
                    textAlign='left',
                    padding='12px',
                    fontSize='15px',
                    whiteSpace='normal',
                    height='auto',
                ),
                style_data=datatable_computed_data_style(),
                style_data_conditional=style_data_conditional,
                page_size=20,
                sort_action="native",
                filter_action="none",
                export_format="csv",
                **dash_table_tooltip_kwargs([
                    {
                        column: {'value': str(value), 'type': 'markdown'}
                        for column, value in row.items()
                    } for row in df.to_dict('records')
                ]),
            )
            
            # Wrap table in a card with summary - in its own full-width row
            return html.Div([
                _mar_factors_success_banner(location, len(df)),
                dbc.Row([
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader([
                                html.H5(f"MAR Factors for {location}", className="mb-0 text-primary"),
                                html.Small(f"Total factors: {len(df)}", className="text-muted")
                            ], className="bg-light"),
                            dbc.CardBody([
                                # Disclaimer
                                dbc.Alert([
                                    html.P([
                                        html.Strong("Important Disclaimer: "),
                                        f"The analysis of Managed Aquifer Recharge (MAR) factors specific to {location} was produced using the Google Gemini Large Language Model (LLM). Although this generation incorporates site-specific parameters, we cannot guarantee its accuracy or completeness. The data provided in the matrix below should be used with caution, as it is intended only to offer general guidance regarding MAR's potential environmental, ecological, and cultural considerations."
                                    ], className="mb-0")
                                ], color="warning", className="mb-4"),
                                
                                html.Div([
                                    html.P([
                                        html.Strong("Categories: "),
                                        html.Span(f"Environmental: {len(df[df['category'] == 'Environmental'])}, ", className="text-info"),
                                        html.Span(f"Ecological: {len(df[df['category'] == 'Ecological'])}, ", className="text-success"),
                                        html.Span(f"Cultural: {len(df[df['category'] == 'Cultural'])}", className="text-warning")
                                    ], className="mb-3"),
                                    html.P([
                                        html.Strong("Priorities: "),
                                        html.Span(f"High: {len(df[df['priority'].astype(str).str.strip() == 'High'])}, ", className="text-danger"),
                                        html.Span(f"Medium: {len(df[df['priority'].astype(str).str.strip() == 'Medium'])}, ", className="text-warning"),
                                        html.Span(f"Low: {len(df[df['priority'].astype(str).str.strip() == 'Low'])}", className="text-success")
                                    ], className="mb-3")
                                ]),
                                html.Div(
                                    table, 
                                    style={
                                        'overflowX': 'auto',
                                        'width': '100%'
                                    }
                                )
                            ])
                        ], className="mt-3")
                    ], width=12)
                ]),
            ])
            
        except Exception as e:
            error_msg = str(e)
            return html.Div([
                dbc.Alert([
                    html.H5("Error generating MAR factors", className="alert-heading"),
                    html.P(f"An error occurred: {error_msg}", className="mb-0")
                ], color="danger")
            ])

    # Callback to display temperature value
    @app.callback(
        Output('temperature-value-display', 'children'),
        [Input('temperature-slider', 'value')]
    )
    def update_temperature_display(temperature):
        """Display the current temperature value."""
        if temperature is not None:
            return html.Span(f"Current value: {temperature:.1f}", className="text-muted")
        return html.Span("Current value: 0.5", className="text-muted")

