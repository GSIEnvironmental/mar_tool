"""Callbacks for the Generate Report sub-tab."""

import os
import tempfile

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, dcc, html

from mar_dss.app.utils.report_generator import (
    _default_report_filename,
    save_prefeasibility_report,
)


def setup_generate_report_callbacks(app):
    """Register Generate Report button callback."""

    @app.callback(
        Output("generate-report-feedback", "children"),
        Output("download-report", "data"),
        Input("generate-report-btn", "n_clicks"),
        State("generate-report-format", "value"),
        prevent_initial_call=True,
    )
    def generate_prefeasibility_report(n_clicks, report_format):
        if not n_clicks:
            return dash.no_update, dash.no_update

        fmt = "pdf" if str(report_format or "").lower() == "pdf" else "html"
        filename = _default_report_filename(fmt)

        try:
            # Build the report in a temp folder and send it to the browser as a
            # download, so nothing is left on the server.
            with tempfile.TemporaryDirectory() as tmp:
                written = save_prefeasibility_report(os.path.join(tmp, filename), report_format=fmt)
                with open(written, "rb") as handle:
                    payload = handle.read()
            label = "PDF" if fmt == "pdf" else "HTML"
            return (
                dbc.Alert(
                    [
                        html.I(className="fas fa-check-circle me-2"),
                        html.Strong(f"{label} report downloaded. "),
                        html.Span(os.path.basename(written)),
                    ],
                    color="success",
                    className="mb-0 py-2",
                ),
                dcc.send_bytes(payload, os.path.basename(written)),
            )
        except ImportError:
            return dbc.Alert(
                "PDF generation requires the reportlab package. Install it with: pip install reportlab",
                color="warning",
                className="mb-0 py-2",
            ), dash.no_update
        except ValueError as exc:
            return dbc.Alert(str(exc), color="warning", className="mb-0 py-2"), dash.no_update
        except OSError as exc:
            return dbc.Alert(
                f"Could not write the report file: {exc}",
                color="danger",
                className="mb-0 py-2",
            ), dash.no_update
        except Exception as exc:
            return dbc.Alert(
                f"Unexpected error generating report: {exc}",
                color="danger",
                className="mb-0 py-2",
            ), dash.no_update
