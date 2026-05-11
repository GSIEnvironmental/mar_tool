"""
Entry script for PyInstaller: serves the Dash app with Waitress (no Flask dev server).
"""
from __future__ import annotations

import multiprocessing
import sys


def _main() -> None:
    from mar_dss.dashboard import launch_dashboard_waitress

    launch_dashboard_waitress(port=8050)


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        multiprocessing.freeze_support()
    _main()
