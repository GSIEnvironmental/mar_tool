"""
Dashboard launcher for MAR DSS.
"""

from __future__ import annotations

import logging
import os
import webbrowser

from mar_dss.app.main import DashboardApp

logger = logging.getLogger(__name__)


def launch_dashboard(debug=True, port=8050):
    """
    Launch the MAR DSS dashboard.

    Args:
        debug (bool): Run in debug mode
        port (int): Port number to run the dashboard on
    """
    dashboard = DashboardApp()
    dashboard.run(debug=debug, port=port)


def launch_dashboard_waitress(
    port: int = 8050,
    host: str = "127.0.0.1",
    threads: int = 4,
    open_browser: bool = True,
) -> None:
    """
    Run the dashboard behind Waitress (WSGI). The `mar_dss` command and the
    Docker image use this.

    Args:
        port: Listen port.
        host: Bind address (use ``0.0.0.0`` to accept connections from other machines).
        threads: Waitress worker threads.
        open_browser: If True, open the local URL once at startup.
    """
    from waitress import serve

    dashboard = DashboardApp()

    # Behind a proxy, MAR_PUBLIC_URL is the address users open.
    public_url = os.environ.get("MAR_PUBLIC_URL")
    if public_url:
        logger.info(f"MAR-Tool is running at {public_url}")
    else:
        display_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        logger.info(f"Dashboard (Waitress) at: http://{display_host}:{port}/")
        if host == "0.0.0.0":
            logger.info("Listening on all interfaces (0.0.0.0).")

    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}/")

    serve(dashboard.app.server, host=host, port=port, threads=threads)


if __name__ == "__main__":
    launch_dashboard()
