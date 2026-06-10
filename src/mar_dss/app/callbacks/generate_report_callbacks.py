"""Callbacks for the Generate Report sub-tab."""

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, html

from mar_dss.app.utils.native_file_dialog import ask_save_report_path
from mar_dss.app.utils.report_generator import (
    _default_report_filename,
    save_prefeasibility_report,
)


def setup_generate_report_callbacks(app):
    """Register Generate Report button callback."""

    @app.callback(
        Output("generate-report-feedback", "children"),
        Input("generate-report-btn", "n_clicks"),
        State("generate-report-format", "value"),
        prevent_initial_call=True,
    )
    def generate_prefeasibility_report(n_clicks, report_format):
        if not n_clicks:
            return dash.no_update

        fmt = "pdf" if str(report_format or "").lower() == "pdf" else "html"
        default_name = _default_report_filename(fmt)
        save_path = ask_save_report_path(default_name, report_format=fmt)

        if save_path is None:
            return dbc.Alert(
                "Could not open the save dialog on this system. "
                "Run the dashboard locally on Windows with Tk available.",
                color="warning",
                className="mb-0 py-2",
            )

        if save_path == "":
            return dbc.Alert(
                "Report generation cancelled — no file was saved.",
                color="secondary",
                className="mb-0 py-2",
            )

        try:
            written = save_prefeasibility_report(save_path, report_format=fmt)
            label = "PDF" if fmt == "pdf" else "HTML"
            return dbc.Alert(
                [
                    html.I(className="fas fa-check-circle me-2"),
                    html.Strong(f"{label} report saved successfully. "),
                    html.Span(written),
                ],
                color="success",
                className="mb-0 py-2",
            )
        except ImportError:
            return dbc.Alert(
                "PDF generation requires the reportlab package. "
                "Install it with: pip install reportlab",
                color="warning",
                className="mb-0 py-2",
            )
        except ValueError as exc:
            return dbc.Alert(str(exc), color="warning", className="mb-0 py-2")
        except OSError as exc:
            return dbc.Alert(
                f"Could not write the report file: {exc}",
                color="danger",
                className="mb-0 py-2",
            )
        except Exception as exc:
            return dbc.Alert(
                f"Unexpected error generating report: {exc}",
                color="danger",
                className="mb-0 py-2",
            )
