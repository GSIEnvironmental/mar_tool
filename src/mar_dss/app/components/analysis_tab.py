"""
Analysis tab component with all analysis sub-tabs.
"""

import dash_bootstrap_components as dbc
from dash import html, dcc
from mar_dss.app.utils.tab_tooltips import tab_nav_id, tab_tooltip

# Import all the analysis components
try:
    from mar_dss.app.components.feasibilities_tab import create_feasibilities_content
    from mar_dss.app.components.dss_algorithm_tab import create_dss_algorithm_content
    from mar_dss.app.components.decision_sensitivity_tab import create_decision_sensitivity_content
    from mar_dss.app.components.decision_interpretation_tab import create_decision_interpretation_content
    from mar_dss.app.components.ai_generated_decision_tab import create_ai_generated_decision_content
    from mar_dss.app.components.data_export_tab import create_data_export_content
    from mar_dss.app.components.engineering_options_tab import create_cost_content
except ImportError:
    from .feasibilities_tab import create_feasibilities_content
    from .dss_algorithm_tab import create_dss_algorithm_content
    from .decision_sensitivity_tab import create_decision_sensitivity_content
    from .decision_interpretation_tab import create_decision_interpretation_content
    from .ai_generated_decision_tab import create_ai_generated_decision_content
    from .data_export_tab import create_data_export_content
    from .engineering_options_tab import create_cost_content


def create_analysis_tab_content():
    """Create the Analysis tab with lazy-loaded sub-tabs."""
    analysis_subtabs = html.Div(
        [
            dbc.Tabs(
                [
                dbc.Tab(
                    label="Feasibilities", id=tab_nav_id("analysis-feasibilities"),
                    tab_id="analysis-feasibilities",
                    children=create_feasibilities_content(),  # Load immediately
                    label_style={
                        "color": "#ffffff", 
                        "fontWeight": "bold",
                        "backgroundColor": "#dc3545",
                        "border": "1px solid #dc3545"
                    },
                    active_label_style={
                        "color": "#ffffff", 
                        "backgroundColor": "#c82333",
                        "border": "1px solid #c82333"
                    },
                ),
                dbc.Tab(
                    label="Cost Analysis", id=tab_nav_id("analysis-cost"),
                    tab_id="analysis-cost",
                    children=create_cost_content(),
                    label_style={
                        "color": "#ffffff", 
                        "fontWeight": "bold",
                        "backgroundColor": "#20c997",
                        "border": "1px solid #20c997"
                    },
                    active_label_style={
                        "color": "#ffffff", 
                        "backgroundColor": "#1aa179",
                        "border": "1px solid #1aa179"
                    },
                ),
                dbc.Tab(
                    label="DSS Algorithm", id=tab_nav_id("analysis-dss-algorithm"),
                    tab_id="analysis-dss-algorithm",
                    children=[html.Div(id="analysis-dss-algorithm-content", children="Loading...")],  # Lazy load
                    label_style={
                        "color": "#ffffff", 
                        "fontWeight": "bold",
                        "backgroundColor": "#28a745",
                        "border": "1px solid #28a745"
                    },
                    active_label_style={
                        "color": "#ffffff", 
                        "backgroundColor": "#1e7e34",
                        "border": "1px solid #1e7e34"
                    },
                ),
                dbc.Tab(
                    label="Decision Sensitivity", id=tab_nav_id("analysis-decision-sensitivity"),
                    tab_id="analysis-decision-sensitivity",
                    children=[html.Div(id="analysis-decision-sensitivity-content", children="Loading...")],  # Lazy load
                    label_style={
                        "color": "#ffffff", 
                        "fontWeight": "bold",
                        "backgroundColor": "#ffc107",
                        "border": "1px solid #ffc107"
                    },
                    active_label_style={
                        "color": "#ffffff", 
                        "backgroundColor": "#e0a800",
                        "border": "1px solid #e0a800"
                    },
                ),
                dbc.Tab(
                    label="Decision Interpretation", id=tab_nav_id("analysis-decision-interpretation"),
                    tab_id="analysis-decision-interpretation",
                    children=[html.Div(id="analysis-decision-interpretation-content", children="Loading...")],  # Lazy load
                    label_style={
                        "color": "#ffffff", 
                        "fontWeight": "bold",
                        "backgroundColor": "#17a2b8",
                        "border": "1px solid #17a2b8"
                    },
                    active_label_style={
                        "color": "#ffffff", 
                        "backgroundColor": "#138496",
                        "border": "1px solid #138496"
                    },
                ),
                dbc.Tab(
                    label="AI Generated Decision", id=tab_nav_id("analysis-ai-decision"),
                    tab_id="analysis-ai-decision",
                    children=[html.Div(id="analysis-ai-decision-content", children="Loading...")],  # Lazy load
                    label_style={
                        "color": "#ffffff", 
                        "fontWeight": "bold",
                        "backgroundColor": "#fd7e14",
                        "border": "1px solid #fd7e14"
                    },
                    active_label_style={
                        "color": "#ffffff", 
                        "backgroundColor": "#e8590c",
                        "border": "1px solid #e8590c"
                    },
                ),
                dbc.Tab(
                    label="Data Export", id=tab_nav_id("analysis-data-export"),
                    tab_id="analysis-data-export",
                    children=[html.Div(id="analysis-data-export-content", children="Loading...")],  # Lazy load
                    label_style={
                        "color": "#ffffff", 
                        "fontWeight": "bold",
                        "backgroundColor": "#6c757d",
                        "border": "1px solid #6c757d"
                    },
                    active_label_style={
                        "color": "#ffffff", 
                        "backgroundColor": "#545b62",
                        "border": "1px solid #545b62"
                    },
                ),
            ],
            id="analysis-tabs",
            active_tab="analysis-feasibilities",
        ),
        tab_tooltip(
            "analysis-feasibilities",
            "Technology feasibility categories and overall project viability scores",
        ),
        tab_tooltip(
            "analysis-cost",
            "Capital and maintenance cost tables with NPV analysis",
        ),
        tab_tooltip(
            "analysis-dss-algorithm",
            "Multi-criteria decision support algorithm configuration and results",
        ),
        tab_tooltip(
            "analysis-decision-sensitivity",
            "How input parameter changes affect feasibility outcomes",
        ),
        tab_tooltip(
            "analysis-decision-interpretation",
            "Detailed explanation of decision algorithm results and rankings",
        ),
        tab_tooltip(
            "analysis-ai-decision",
            "AI-powered decision support and technology recommendations",
        ),
        tab_tooltip(
            "analysis-data-export",
            "Export project data, reports, and analysis results",
        ),
        ],
    )

    return [
        dcc.Loading(
            id="analysis-run-loading",
            type="circle",
            color="#0d6efd",
            parent_style={"minHeight": "48px"},
            children=html.Div(
                [
                    html.Div(
                        id="analysis-run-status-row",
                        className="analysis-run-status-row mb-2",
                    ),
                    analysis_subtabs,
                ]
            ),
        ),
        # Hidden store to trigger knowledge graph initialization
        dcc.Store(id="knowledge-graph-store", data={"initialized": False}),
        # Store for feasibility metrics
        dcc.Store(id="feasibility-metrics-store", data={"score": "0%", "cost": "$0 - $0"}),
    ]
