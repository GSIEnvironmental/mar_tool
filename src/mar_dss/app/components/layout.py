"""
Layout setup for the MAR DSS dashboard.

This module provides a function to build and assign the Dash layout using
the provided application context (the main DashboardApp instance).
"""

import dash_bootstrap_components as dbc
from dash import dcc, html
from mar_dss.app.utils.defaults import defaults
import mar_dss.app.utils.data_storage as dash_storage
from mar_dss.app.utils.tab_tooltips import tab_nav_id, tab_tooltip


def setup_layout(app_ctx):
    """Set up the main dashboard layout on the given app context.

    The app_ctx is expected to provide ``app`` (Dash instance). Main tabs use
    stacked panels under ``#main-content`` (see :data:`MAIN_TAB_IDS`); each panel
    is filled once when first selected and kept mounted for faster switching.
    """
    app_ctx.app.layout = _build_root_layout()


# Top-level tab ids — keep in sync with ``_build_tabs`` tab_id values.
MAIN_TAB_IDS = (
    "overview",
    "water-source",
    "hydrogeology",
    "environmental",
    "legal",
    "engineering-options",
    "analysis",
)


def main_tab_panel_id(tab_id: str) -> str:
    """Dash component id for the lazy-loaded panel for ``tab_id``."""
    return f"main-tab-panel-{tab_id}"


# ------------------------------
# Theme helpers
# ------------------------------

_THEME_URLS = {
    "CERULEAN": (
        "https://cdn.jsdelivr.net/npm/bootswatch@5.3.2/dist/"
        "cerulean/bootstrap.min.css"
    ),
    "DARKLY": (
        "https://cdn.jsdelivr.net/npm/bootswatch@5.3.2/dist/"
        "darkly/bootstrap.min.css"
    ),
    "FLATLY": (
        "https://cdn.jsdelivr.net/npm/bootswatch@5.3.2/dist/"
        "flatly/bootstrap.min.css"
    ),
    "CYBORG": (
        "https://cdn.jsdelivr.net/npm/bootswatch@5.3.2/dist/"
        "cyborg/bootstrap.min.css"
    ),
    "SLATE": (
        "https://cdn.jsdelivr.net/npm/bootswatch@5.3.2/dist/"
        "slate/bootstrap.min.css"
    ),
}


def _get_theme_url(theme_name: str) -> str:
    return _THEME_URLS.get(theme_name.upper(), _THEME_URLS["CERULEAN"])


def _create_theme_link(initial_theme: str = "CERULEAN") -> html.Link:
    return html.Link(
        id="theme-css",
        rel="stylesheet",
        href=_get_theme_url(initial_theme),
    )


def _create_black_text_override_link() -> html.Link:
    """Must follow theme-css so Bootswatch muted greys are overridden."""
    return html.Link(
        id="black-text-override-css",
        rel="stylesheet",
        href="/assets/force_black_text.css?v=2",
    )


# ------------------------------
# Header builders
# ------------------------------

def _build_title_block() -> html.Div:
    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Img(
                                src="assets/logo2.png",
                                alt="MAR DSS Logo 2",
                                style={
                                    "height": "60px",
                                    "width": "auto",
                                    "vertical-align": "middle",
                                },
                            )
                        ],
                        width=3,
                        className="d-flex align-items-center justify-content-start"
                    ),
                    dbc.Col(
                        [
                            html.H1(
                                "Managed Aquifer Recharge Tool",
                                className="text-center mb-0",
                                style={
                                    "font-family": ("'Segoe UI', Tahoma, sans-serif"),
                                    "font-size": "2.1rem",
                                    "line-height": "1.1",
                                    "font-weight": "700",
                                    "color": "#2C3E50",
                                    "background-color": "transparent",
                                    "padding": "0px",
                                    "border-radius": "8px",
                                    "border": "none",
                                    "vertical-align": "middle",
                                },
                            )
                        ],
                        width=6,
                        className="d-flex align-items-center justify-content-center"
                    ),
                    dbc.Col(
                        [
                            html.Div([
                                html.Img(
                                    src="assets/logos.jpg",
                                    alt="Partner Logos",
                                    style={
                                        "height": "70px",
                                        "width": "auto",
                                        "vertical-align": "middle",
                                    },
                                )
                            ], className="d-flex align-items-center justify-content-center")
                        ],
                        width=3,
                        className="d-flex align-items-center justify-content-center"
                    )
                ],
                className="align-items-center"
            )
        ],
        style={
            "min-height": "0px",
            "width": "100%",
            "padding": "8px 0",
        },
    )


def _build_file_toolbar() -> html.Div:
    """Desktop-style file commands in one row (Open/Save As use native file dialogs)."""
    return html.Div(
        dbc.ButtonGroup(
            [
                dbc.Button(
                    [html.I(className="fas fa-file me-1"), "New"],
                    id="btn-new",
                    color="outline-secondary",
                    size="sm",
                    title="Start a new project with default values",
                ),
                dbc.Button(
                    [html.I(className="fas fa-folder-open me-1"), "Open"],
                    id="btn-open",
                    color="outline-secondary",
                    size="sm",
                    title="Browse for a CSV/JSON project file to open",
                ),
                dbc.Button(
                    [html.I(className="fas fa-times me-1"), "Close"],
                    id="btn-close",
                    color="outline-secondary",
                    size="sm",
                    title="Close MAR DSS (attempts to close this browser tab)",
                ),
                dbc.Button(
                    [html.I(className="fas fa-save me-1"), "Save"],
                    id="btn-save",
                    color="outline-secondary",
                    size="sm",
                    title="Save to the project file path (or browse if path is empty)",
                ),
                dbc.Button(
                    [html.I(className="fas fa-file-export me-1"), "Save As..."],
                    id="btn-save-as",
                    color="outline-secondary",
                    size="sm",
                    title="Browse for a location and file name to save the project",
                ),
                dbc.Button(
                    [html.I(className="fas fa-info-circle me-1"), "About"],
                    id="btn-about",
                    color="outline-secondary",
                    size="sm",
                    title="About MAR-Tool",
                ),
            ],
            size="sm",
        ),
        className="mar-file-toolbar mt-2",
    )


def _build_close_project_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Close MAR DSS")),
            dbc.ModalBody(
                "Close MAR DSS? This will try to close this browser tab. "
                "If your browser blocks that, the page will show a closed message "
                "and you can close the tab manually."
            ),
            dbc.ModalFooter(
                [
                    dbc.Button(
                        "Cancel",
                        id="btn-close-cancel",
                        color="secondary",
                        n_clicks=0,
                    ),
                    dbc.Button(
                        "Close",
                        id="btn-close-confirm",
                        color="primary",
                        n_clicks=0,
                    ),
                ]
            ),
        ],
        id="close-project-modal",
        is_open=False,
        centered=True,
    )


def _build_about_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("About MAR-Tool")),
            dbc.ModalBody(
                [
                    html.P(
                        "MAR-Tool (Managed Aquifer Recharge Prefeasibility Decision Support "
                        "System) is a web-based dashboard for evaluating Managed Aquifer "
                        "Recharge (MAR) projects. It guides users from project setup and site "
                        "characterization through water source assessment, hydrogeology, "
                        "environmental and regulatory review, engineering options, integrated "
                        "feasibility analysis, and decision support.",
                        className="mb-3",
                    ),
                    html.P(
                        [
                            "MAR-Tool was developed in cooperation between the ",
                            html.Strong(
                                "Environmental Security Technology Certification Program (ESTCP)"
                            ),
                            ", ",
                            html.Strong(
                                "Naval Facilities Engineering Systems Command (NAVFAC)"
                            ),
                            ", and ",
                            html.Strong("GSI Environmental Inc."),
                        ],
                        className="mb-0",
                    ),
                ]
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id="btn-about-close",
                    color="secondary",
                    n_clicks=0,
                )
            ),
        ],
        id="about-modal",
        is_open=False,
        centered=True,
        scrollable=True,
    )


def _build_theme_selector_and_logo() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Label("Theme", className=("small text-muted")),
                    dbc.Select(
                        id="theme-selector",
                        options=[
                            {"label": "Cerulean", "value": "CERULEAN"},
                            {"label": "Darkly", "value": "DARKLY"},
                            {"label": "Flatly", "value": "FLATLY"},
                            {"label": "Cyborg", "value": "CYBORG"},
                            {"label": "Slate", "value": "SLATE"},
                        ],
                        value="CERULEAN",
                        size="sm",
                        style={"width": "120px"},
                    ),
                ],
                style={"display": "inline-block", "margin-right": "20px"},
            ),
            html.Img(
                src="assets/logo.jpg",
                alt="MAR DSS Logo",
                style={
                    "height": "160px",
                    "width": "auto",
                    "max-width": "300px",
                    "vertical-align": "middle",
                },
            ),
        ],
        className="position-absolute",
        style={"top": "10px", "right": "20px"},
    )


def _build_header() -> dbc.Row:
    return dbc.Row(
        [
            dbc.Col(
                [
                    html.Div(
                        [_build_title_block(), _build_file_toolbar()],
                        className="position-relative",
                    ),
                    html.Hr(className="my-2"),
                ]
            )
        ]
    )


# ------------------------------
# Main content builders
# ------------------------------

_TOP_TAB_TOOLTIPS = {
    "overview": (
        "Project setup: name, location, MAR purpose, and site characteristics"
    ),
    "water-source": (
        "Water source availability, quality, flow data, and runoff calculations"
    ),
    "hydrogeology": (
        "Subsurface conditions: stratigraphy, aquifer type, groundwater, and storage"
    ),
    "environmental": (
        "Five screening questions on source water, vadose zone, and target aquifer quality"
    ),
    "legal": (
        "Legal and regulatory feasibility, permits, water rights, and "
        "AI environmental considerations"
    ),
    "engineering-options": (
        "Engineering design parameters and cost estimation (capital, O&M, NPV)"
    ),
    "analysis": (
        "Feasibility assessment, decision support, sensitivity, and data export"
    ),
}


def _build_tabs():
    tabs = dbc.Tabs(
        [
            dbc.Tab(
                label="(1) Overview",
                id=tab_nav_id("overview"),
                tab_id="overview",
                label_style={
                    "color": "#ffffff", 
                    "fontWeight": "bold",
                    "backgroundColor": "#6f42c1",
                    "border": "1px solid #6f42c1"
                },
                active_label_style={
                    "color": "#ffffff", 
                    "backgroundColor": "#5a32a3",
                    "border": "1px solid #5a32a3"
                }
            ),
            dbc.Tab(
                label="(2) Water Source",
                id=tab_nav_id("water-source"),
                tab_id="water-source",
                label_style={
                    "color": "#ffffff", 
                    "fontWeight": "bold",
                    "backgroundColor": "#8e44ad",
                    "border": "1px solid #8e44ad"
                },
                active_label_style={
                    "color": "#ffffff", 
                    "backgroundColor": "#7d3c98",
                    "border": "1px solid #7d3c98"
                }
            ),
            dbc.Tab(
                label="(3) Hydrogeology",
                id=tab_nav_id("hydrogeology"),
                tab_id="hydrogeology",
                label_style={
                    "color": "#ffffff", 
                    "fontWeight": "bold",
                    "backgroundColor": "#a569bd",
                    "border": "1px solid #a569bd"
                },
                active_label_style={
                    "color": "#ffffff", 
                    "backgroundColor": "#9b59b6",
                    "border": "1px solid #9b59b6"
                }
            ),
            dbc.Tab(
                label="(4) Water Quality",
                id=tab_nav_id("environmental"),
                tab_id="environmental",
                label_style={
                    "color": "#ffffff", 
                    "fontWeight": "bold",
                    "backgroundColor": "#3498db",
                    "border": "1px solid #3498db"
                },
                active_label_style={
                    "color": "#ffffff", 
                    "backgroundColor": "#2980b9",
                    "border": "1px solid #2980b9"
                }
            ),
            dbc.Tab(
                label="(5) Regulations",
                id=tab_nav_id("legal"),
                tab_id="legal",
                label_style={
                    "color": "#ffffff", 
                    "fontWeight": "bold",
                    "backgroundColor": "#5dade2",
                    "border": "1px solid #5dade2"
                },
                active_label_style={
                    "color": "#ffffff", 
                    "backgroundColor": "#4a9fd1",
                    "border": "1px solid #4a9fd1"
                }
            ),
            dbc.Tab(
                label="(6) Engineering",
                id=tab_nav_id("engineering-options"),
                tab_id="engineering-options",
                label_style={
                    "color": "#ffffff", 
                    "fontWeight": "bold",
                    "backgroundColor": "#85c1e9",
                    "border": "1px solid #85c1e9"
                },
                active_label_style={
                    "color": "#ffffff", 
                    "backgroundColor": "#73b3e0",
                    "border": "1px solid #73b3e0"
                }
            ),
            dbc.Tab(
                label="(7) Analysis",
                id=tab_nav_id("analysis"),
                tab_id="analysis",
                label_style={
                    "color": "#ffffff", 
                    "fontWeight": "bold",
                    "backgroundColor": "#85c1e9",
                    "border": "1px solid #85c1e9"
                },
                active_label_style={
                    "color": "#ffffff", 
                    "backgroundColor": "#73b3e0",
                    "border": "1px solid #73b3e0"
                }
            ),
        ],
        id="top-tabs",
        active_tab="overview",
    )
    return html.Div(
        [
            tabs,
            *[
                tab_tooltip(tab_id, text, placement="bottom")
                for tab_id, text in _TOP_TAB_TOOLTIPS.items()
            ],
        ]
    )


def _build_main_card_body() -> list:
    """Stacked tab panels + flash row; panels mount once via lazy callback."""
    tab_panels = [
        html.Div(
            id=main_tab_panel_id(tid),
            style={"display": "block" if tid == "overview" else "none"},
            children=[],
            className="main-tab-panel",
        )
        for tid in MAIN_TAB_IDS
    ]
    return [
        html.Div(
            id="main-content",
            children=[
                dcc.Store(id="main-tab-clientside-sync", data=0),
                html.Div(
                    id="main-content-flash",
                    className="mb-2 mar-main-content-flash",
                ),
                html.Div(id="main-tab-panels-wrapper", children=tab_panels),
            ],
        )
    ]


def _build_main_card() -> dbc.Card:
    return dbc.Card([
        dbc.CardHeader([
            dbc.Row([
                dbc.Col([_build_tabs()], width=9),
                dbc.Col([
                    html.Div([
                        html.Label("Theme:", className="me-2 mb-0"),
                        dbc.Select(
                            id="theme-selector",
                            options=[
                                {"label": "Cerulean", "value": "CERULEAN"},
                                {"label": "Darkly", "value": "DARKLY"},
                                {"label": "Flatly", "value": "FLATLY"},
                                {"label": "Cyborg", "value": "CYBORG"},
                                {"label": "Slate", "value": "SLATE"},
                            ],
                            value="CERULEAN",
                            size="sm",
                            style={"width": "150px"},
                        ),
                        dbc.Tooltip(
                            "Bootstrap/Bootswatch color theme for the dashboard",
                            target="theme-selector",
                            placement="bottom",
                        ),
                    ], className="d-flex align-items-center justify-content-end")
                ], width=3)
            ])
        ]),
        dbc.CardBody(_build_main_card_body()),
    ])


# ------------------------------
# Sidebar builders
# ------------------------------

def _build_sidebar_nav() -> dbc.Nav:
    return dbc.Nav(
        [
            dbc.NavItem([
                dbc.NavLink("Dashboard", id=("nav-dashboard"), href="#",
                            active=True)
            ]),
            dbc.NavItem([
                dbc.NavLink("DSS Algorithm", id=("nav-water-levels"),
                            href="#")
            ]),
            dbc.NavItem([
                dbc.NavLink("Decision Sensitivity", id=("nav-recharge"),
                            href="#")
            ]),
            dbc.NavItem([
                dbc.NavLink("Decision Interpretation", id=("nav-quality"),
                            href="#")
            ]),
            dbc.NavItem([
                dbc.NavLink("Scenarios Comparison", id=("nav-scenarios"),
                            href="#")
            ]),
            dbc.NavItem([
                dbc.NavLink("AI Generated Decision", id=("nav-ai-decision"),
                            href="#")
            ]),
            dbc.NavItem([
                dbc.NavLink("Data Export", id=("nav-export"), href="#")
            ]),
        ],
        vertical=True,
        pills=True,
    )


def _build_sidebar() -> dbc.Col:
    return dbc.Col(
        [
            dbc.Card(
                [
                    dbc.CardHeader("Analysis", className="fw-bold"),
                    dbc.CardBody([_build_sidebar_nav()]),
                ]
            )
        ],
        width=3,
        style={"flex": "0 0 20%", "maxWidth": "20%"},
    )


# ------------------------------
# Page layout builders
# ------------------------------

def _build_content_area() -> dbc.Row:
    return dbc.Row(
        [
            dbc.Col(
                [_build_main_card()],
                width=12,  # Full width since sidebar is removed
            ),
        ]
    )


def _build_root_layout() -> html.Div:
    # Stratigraphy and groundwater stores live here (not inside lazy-loaded hydro panels)
    # so project Load/New callbacks and dash_storage stay in sync before Hydro is opened.
    from mar_dss.app.components.hydro_tab import _get_groundwater_data, _get_stratigraphy_data

    stratigraphy_store_initial = _get_stratigraphy_data()
    groundwater_store_initial = _get_groundwater_data()
    return html.Div(
        [
            _create_theme_link("CERULEAN"),
            _create_black_text_override_link(),
            dbc.Container(
                [
                    _build_header(),
                    _build_content_area(),
                ],
                fluid=True,
                id="app-container",
                className="mar-theme-light",
            ),
            dcc.Store(
                id="stratigraphy-data-store",
                data=stratigraphy_store_initial,
                storage_type="memory",
            ),
            dcc.Store(
                id="groundwater-data-store",
                data=groundwater_store_initial,
                storage_type="memory",
            ),
            # Bumped when stratigraphy / groundwater is copied into dash_storage (avoid
            # circular callbacks that write the same dcc.Store they listen to).
            dcc.Store(id="stratigraphy-dash-sync-ping", data=0),
            dcc.Store(id="groundwater-dash-sync-ping", data=0),
            # Incremented on every (7) Analysis top-tab click (including re-clicks).
            dcc.Store(id="analysis-rerun-count", data=0),
            dcc.Store(
                id="project-location-store",
                data=dash_storage.get_data("project_location") or "",
                storage_type="memory",
            ),
            dcc.Store(id="peak-runoff-engineering-sync", data=None),
            html.Div(id="close-browser-hook", style={"display": "none"}),
            _build_close_project_modal(),
            _build_about_modal(),
        ]
    )


