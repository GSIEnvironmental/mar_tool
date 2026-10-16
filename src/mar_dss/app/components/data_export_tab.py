"""
Generate Report tab content for MAR DSS dashboard (Analysis sub-tab).
"""

import dash_bootstrap_components as dbc
from dash import html


def create_data_export_content():
    """Create content for the Generate Report sub-tab."""
    return html.Div(
        [
            html.H3("Generate Report", className="mb-2 text-primary"),
            html.P(
                "Create a prefeasibility summary report from DSS analysis, decision interpretation, "
                "and project inputs. Choose HTML or PDF format and where to save the report.",
                className="text-muted mb-4",
            ),
            dbc.Card(
                [
                    dbc.CardHeader(
                        "Prefeasibility Summary Report",
                        className="fw-bold bg-primary text-white py-2",
                    ),
                    dbc.CardBody(
                        [
                            html.P(
                                "The report includes:",
                                className="fw-semibold mb-2",
                            ),
                            html.Ul(
                                [
                                    html.Li(
                                        'Title: "Summary Report for Prefeasibility Analysis at {location}"'
                                    ),
                                    html.Li(
                                        "Executive summary — engineering options ranked from DSS analysis "
                                        "with capital cost, recharge volume, and cost per acre-foot recharged"
                                    ),
                                    html.Li(
                                        "Feasibility Analysis Justification — decision interpretation "
                                        "for each option (status, warnings, mitigations, constraints)"
                                    ),
                                    html.Li(
                                        "Water Source — project map, site coordinates, and monthly flow estimates"
                                    ),
                                    html.Li(
                                        "Hydrogeology — aquifer type, stratigraphy layers, and groundwater elevations"
                                    ),
                                    html.Li(
                                        "Project Input Summary — key parameters from remaining MAR DSS tabs"
                                    ),
                                ],
                                className="mb-3",
                            ),
                            html.Label("Report format", className="fw-semibold mb-2"),
                            dbc.RadioItems(
                                options=[
                                    {"label": " HTML (browser)", "value": "html"},
                                    {"label": " PDF (print-ready)", "value": "pdf"},
                                ],
                                value="html",
                                id="generate-report-format",
                                inline=True,
                                className="mb-3",
                            ),
                            dbc.Button(
                                [
                                    html.I(className="fas fa-file-export me-2"),
                                    "Generate Report",
                                ],
                                id="generate-report-btn",
                                color="success",
                                size="lg",
                                n_clicks=0,
                            ),
                            html.Div(id="generate-report-feedback", className="mt-3"),
                            html.Small(
                                "Requires feasibility analysis to be run first"
                                "HTML opens in any browser; PDF is generated directly for sharing or printing.",
                                className="text-muted d-block mt-3",
                            ),
                        ],
                        className="p-3",
                    ),
                ],
                className="mb-3",
            ),
        ]
    )


# Alias for clearer imports
create_generate_report_content = create_data_export_content
