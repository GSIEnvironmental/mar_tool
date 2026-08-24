"""
Entry script for PyInstaller: serves the Dash app with Waitress (no Flask dev server).

Also supports Tk file-dialog worker modes invoked by
:mod:`mar_dss.app.utils.native_file_dialog` when the app is frozen:

  MAR-DSS.exe --mar-dss-tk-open-project
  MAR-DSS.exe --mar-dss-tk-save-project [default_name]
  MAR-DSS.exe --mar-dss-tk-save-report [default_name] [html|pdf]
"""
from __future__ import annotations

import multiprocessing
import sys


def _run_tk_worker(flag: str) -> bool:
    if len(sys.argv) < 2 or sys.argv[1] != flag:
        return False

    # Worker scripts expect argv[1:] to be their own arguments (not the flag).
    sys.argv = [sys.argv[0], *sys.argv[2:]]

    if flag == "--mar-dss-tk-open-project":
        from mar_dss.app.utils._tk_open_project_dialog import main as open_main

        open_main()
        return True

    if flag == "--mar-dss-tk-save-project":
        from mar_dss.app.utils._tk_save_project_dialog import main as save_project_main

        save_project_main()
        return True

    if flag == "--mar-dss-tk-save-report":
        from mar_dss.app.utils._tk_save_report_dialog import main as save_main

        save_main()
        return True

    return False


def _main() -> None:
    from mar_dss.dashboard import launch_dashboard_waitress
    from mar_dss.startup_banner import print_distribution_header, print_startup_status

    print_distribution_header()
    print_startup_status("Initializing the dashboard...")
    launch_dashboard_waitress(port=8050)


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        multiprocessing.freeze_support()

    if _run_tk_worker("--mar-dss-tk-open-project") or _run_tk_worker(
        "--mar-dss-tk-save-project"
    ) or _run_tk_worker("--mar-dss-tk-save-report"):
        sys.exit(0)

    _main()
