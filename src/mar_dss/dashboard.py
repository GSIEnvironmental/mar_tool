"""
Dashboard launcher for MAR DSS.
"""

from __future__ import annotations

import webbrowser

from mar_dss.app.main import DashboardApp


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
    Run the dashboard behind Waitress (WSGI). Intended for frozen/production-style runs.

    Args:
        port: Listen port.
        host: Bind address (use ``0.0.0.0`` to accept connections from other machines).
        threads: Waitress worker threads.
        open_browser: If True, open the local URL once at startup.
    """
    from waitress import serve

    dashboard = DashboardApp()
    display_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{display_host}:{port}/"
    print(f"Dashboard (Waitress) at: {url}")
    if host == "0.0.0.0":
        print("Listening on all interfaces (0.0.0.0).")

    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}/")

    serve(dashboard.app.server, host=host, port=port, threads=threads)


if __name__ == "__main__":
    launch_dashboard()
