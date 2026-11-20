"""
Analysis tab component with all analysis sub-tabs.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from mar_dss.app.utils.tab_tooltips import tab_nav_id, tab_tooltip

# Import all the analysis components
try:
    from mar_dss.app.components.ai_generated_decision_tab import create_ai_generated_decision_content
    from mar_dss.app.components.data_export_tab import create_data_export_content
    from mar_dss.app.components.decision_interpretation_tab import create_decision_interpretation_content
    from mar_dss.app.components.engineering_options_tab import create_cost_content
    from mar_dss.app.components.feasibilities_tab import create_feasibilities_content
except ImportError:
    from .engineering_options_tab import create_cost_content
    from .feasibilities_tab import create_feasibilities_content

# Same sub-tab palette as Regulations / Hydrogeology
_TAB_COLORS = (
    ("#0d6efd", "#0b5ed7"),  # blue
    ("#5dade2", "#4a9fd1"),  # light blue
    ("#17a2b8", "#138496"),  # cyan
)


def _subtab_styles(index: int) -> dict:
    bg, active_bg = _TAB_COLORS[index % len(_TAB_COLORS)]
    return {
        "label_style": {
            "color": "#ffffff",
            "fontWeight": "bold",
            "backgroundColor": bg,
            "border": f"1px solid {bg}",
        },
        "active_label_style": {
            "color": "#ffffff",
            "backgroundColor": active_bg,
            "border": f"1px solid {active_bg}",
        },
    }


def create_analysis_tab_content():
    """Create the Analysis tab with lazy-loaded sub-tabs."""
    analysis_subtabs = html.Div(
        [
            dbc.Tabs(
                [
                    dbc.Tab(
                        label="(7.1) Feasibility Summary",
                        id=tab_nav_id("analysis-feasibilities"),
                        tab_id="analysis-feasibilities",
                        children=create_feasibilities_content(),  # Load immediately
                        **_subtab_styles(0),
                    ),
                    dbc.Tab(
                        label="(7.2) Cost Analysis",
                        id=tab_nav_id("analysis-cost"),
                        tab_id="analysis-cost",
                        children=create_cost_content(),
                        **_subtab_styles(1),
                    ),
                    dbc.Tab(
                        label="(7.3) Decision Interpretation",
                        id=tab_nav_id("analysis-decision-interpretation"),
                        tab_id="analysis-decision-interpretation",
                        children=[
                            html.Div(id="analysis-decision-interpretation-content", children="Loading..."),
                        ],  # Lazy load
                        **_subtab_styles(2),
                    ),
                    dbc.Tab(
                        label="(7.4) AI Generated Decision",
                        id=tab_nav_id("analysis-ai-decision"),
                        tab_id="analysis-ai-decision",
                        children=[html.Div(id="analysis-ai-decision-content", children="Loading...")],  # Lazy load
                        **_subtab_styles(0),
                    ),
                    dbc.Tab(
                        label="(7.5) Generate Report",
                        id=tab_nav_id("analysis-data-export"),
                        tab_id="analysis-data-export",
                        children=[html.Div(id="analysis-data-export-content", children="Loading...")],  # Lazy load
                        **_subtab_styles(1),
                    ),
                ],
                id="analysis-tabs",
                active_tab="analysis-feasibilities",
            ),
            tab_tooltip(
                "analysis-feasibilities",
                "Feasibility summary of MAR option economics, with feasibility details below",
            ),
            tab_tooltip(
                "analysis-cost",
                "Capital and maintenance cost tables with NPV analysis",
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
                ],
            ),
        ),
        # Hidden store to trigger knowledge graph initialization
        dcc.Store(id="knowledge-graph-store", data={"initialized": False}),
        # Store for feasibility metrics
        dcc.Store(id="feasibility-metrics-store", data={"score": "0%", "cost": "$0 - $0"}),
        # Bumped when Capital Cost unit prices change so Feasibility Summary refreshes
        dcc.Store(id="cost-economics-revision", data=0),
    ]
