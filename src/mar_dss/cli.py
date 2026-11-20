"""Console script for mar_dss."""

import logging
import os

import typer

app = typer.Typer()


@app.command()
def main(
    host: str = typer.Option("127.0.0.1", help="Address to listen on. Use 0.0.0.0 in Docker."),
    port: int = typer.Option(8050, help="Port to listen on."),
    threads: int = typer.Option(8, help="Number of worker threads."),
    open_browser: bool = typer.Option(True, help="Open the dashboard in a browser."),
    dev: bool = typer.Option(False, help="Use Dash's debug server, which reloads on code changes. Local use only."),
):
    """Serve the MAR DSS dashboard with Waitress, or with the debug server if --dev is set."""
    if dev:
        from mar_dss.app.main import DashboardApp

        dash_app = DashboardApp().app
        public_url = os.environ.get("MAR_PUBLIC_URL")
        if public_url:
            # Behind Caddy, Dash's own "running on" line shows the container's
            # address, which a browser can't open. Show the real one instead.
            # (Set after the app is created, since Dash sets this level itself.)
            dash_app.logger.setLevel(logging.WARNING)
            # The debug server runs the app in a child process; only it prints.
            if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
                print(f"MAR-Tool is running at {public_url}", flush=True)
        dash_app.run(debug=True, host=host, port=port)
        return

    from mar_dss.dashboard import launch_dashboard_waitress

    launch_dashboard_waitress(port=port, host=host, threads=threads, open_browser=open_browser)


if __name__ == "__main__":
    app()
