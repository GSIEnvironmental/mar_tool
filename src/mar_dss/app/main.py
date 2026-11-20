"""
Main dashboard application for MAR DSS.
"""

import logging
import webbrowser
from pathlib import Path

import dash
import dash_bootstrap_components as dbc

logger = logging.getLogger(__name__)


_APP_DIR = Path(__file__).resolve().parent


def _resolve_assets_folder() -> str:
    """Return the path to app/assets."""
    return str(_APP_DIR / "assets")


try:
    # Try absolute imports first (when run as module)
    from mar_dss.app.callbacks.hydro_callbacks import setup_hydro_callbacks
    from mar_dss.app.components.ai_generated_decision_tab import (
        create_ai_generated_decision_content,
    )
    from mar_dss.app.components.dashboard_tab import create_dashboard_content
    from mar_dss.app.components.data_export_tab import (
        create_data_export_content,
    )
    from mar_dss.app.components.decision_interpretation_tab import (
        create_decision_interpretation_content,
    )
    from mar_dss.app.components.hydro_tab import create_hydro_tab_content
    from mar_dss.app.components.scenarios_comparison_tab import (
        create_scenarios_comparison_content,
    )
    from mar_dss.app.components.water_source_tab import (
        create_general_tab_content,
    )
except ImportError:
    # Fallback to relative imports (when run directly)
    pass


class DashboardApp:
    """Main dashboard application class."""

    def __init__(self):
        """Initialize the dashboard application."""
        # dash.Dash() reads the DASH_REQUESTS_PATHNAME_PREFIX environment variable
        # on its own. The compose files set it to /MAR-Tool/ so the page loads its
        # files from under that path. Locally it isn't set, and the app runs at /.
        self.app = dash.Dash(
            __name__,
            title="MAR-Tool Dashboard",
            external_stylesheets=["https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css"],
            suppress_callback_exceptions=True,
            assets_folder=_resolve_assets_folder(),
        )
        # Browser tab icon (served from assets/)
        self.app._favicon = "mar_icon2.PNG"

        # Each browser gets its own data storage (see data_storage.py).
        try:
            from mar_dss.app.utils import data_storage
        except ImportError:
            from .utils import data_storage
        data_storage.init_app(self.app.server)

        @self.app.server.route("/health")
        def _health():
            # Simple health check we can ping to verify the app is running.
            return "ok"

        self.current_theme = "CERULEAN"
        self.setup_layout()
        self.setup_callbacks()

        # Set up hydrogeology callbacks
        setup_hydro_callbacks(self.app)

        # Set up runoff calculator callbacks
        try:
            from mar_dss.app.callbacks.runoff_callbacks import (
                setup_runoff_callbacks,
            )
        except ImportError:
            from .callbacks.runoff_callbacks import setup_runoff_callbacks
        setup_runoff_callbacks(self.app)

        # Set up analysis tab lazy loading callbacks
        try:
            from mar_dss.app.callbacks.analysis_callbacks import (
                setup_analysis_callbacks,
            )
        except ImportError:
            from .callbacks.analysis_callbacks import setup_analysis_callbacks
        setup_analysis_callbacks(self.app)

        # Set up feasibilities tab callbacks
        try:
            from mar_dss.app.callbacks.feasibilities_callbacks import (
                setup_feasibilities_callbacks,
            )
        except ImportError:
            from .callbacks.feasibilities_callbacks import setup_feasibilities_callbacks
        setup_feasibilities_callbacks(self.app)

        # Set up environmental impact callbacks
        try:
            from mar_dss.app.callbacks.environmental_impact_callbacks import (
                setup_environmental_impact_callbacks,
            )
        except ImportError:
            from .callbacks.environmental_impact_callbacks import setup_environmental_impact_callbacks
        setup_environmental_impact_callbacks(self.app)

        # Set up legal constraints callbacks
        try:
            from mar_dss.app.callbacks.legal_constraints_callbacks import (
                setup_legal_constraints_callbacks,
            )
        except ImportError:
            from .callbacks.legal_constraints_callbacks import setup_legal_constraints_callbacks
        setup_legal_constraints_callbacks(self.app)

        # Set up AI Generated Decision callbacks
        try:
            from mar_dss.app.callbacks.ai_decision_callbacks import (
                setup_ai_decision_callbacks,
            )
        except ImportError:
            from .callbacks.ai_decision_callbacks import setup_ai_decision_callbacks
        setup_ai_decision_callbacks(self.app)

        # Set up Generate Report callbacks
        try:
            from mar_dss.app.callbacks.generate_report_callbacks import (
                setup_generate_report_callbacks,
            )
        except ImportError:
            from .callbacks.generate_report_callbacks import setup_generate_report_callbacks
        setup_generate_report_callbacks(self.app)

        # Set up cost callbacks
        try:
            from mar_dss.app.callbacks.cost_callbacks import (
                setup_cost_callbacks,
            )
        except ImportError:
            from .callbacks.cost_callbacks import setup_cost_callbacks
        setup_cost_callbacks(self.app)

    def setup_layout(self):
        """Set up the main dashboard layout by delegating to layout module."""
        # Import locally to avoid potential circular imports
        try:
            from mar_dss.app.components.layout import (
                setup_layout as _setup_layout,
            )
        except ImportError:
            from .components.layout import setup_layout as _setup_layout

        _setup_layout(self)

    def setup_callbacks(self):
        """Set up dashboard callbacks."""
        # Import and set up main callbacks
        try:
            from mar_dss.app.callbacks.main_callbacks import setup_main_callbacks
        except ImportError:
            from .callbacks.main_callbacks import setup_main_callbacks

        setup_main_callbacks(self.app, self)

    def get_theme_css(self, theme_name):
        """Get CSS for the selected theme."""
        theme_map = {
            "CERULEAN": dbc.themes.CERULEAN,
            "DARKLY": dbc.themes.DARKLY,
            "FLATLY": dbc.themes.FLATLY,
            "CYBORG": dbc.themes.CYBORG,
            "SLATE": dbc.themes.SLATE,
        }
        return theme_map.get(theme_name, dbc.themes.CERULEAN)

    def run(self, debug=True, port=8050, open_browser=True):
        """Run the Flask development server (local use only)."""
        url = f"http://127.0.0.1:{port}/"
        logger.info(f"Dashboard running at: {url}")
        logger.info("Open the URL in your browser to view the dashboard.")

        if open_browser:
            logger.info(f"Opening browser to: {url}")
            webbrowser.open(url)

        try:
            self.app.run(debug=debug, port=port, host="127.0.0.1")

        except OSError as e:
            if "Address already in use" in str(e):
                logger.error(f"Port {port} is already in use. Please close other instances or use a different port.")
            else:
                raise e


def main(port: int = 8050, open_browser: bool = True):
    """Run the dashboard locally with the debug server.

    The debug server isn't safe to expose, so it only listens on 127.0.0.1.
    """
    dashboard = DashboardApp()
    dashboard.run(debug=True, port=port, open_browser=open_browser)


if __name__ == "__main__":
    main()
