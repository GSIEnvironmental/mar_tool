"""Native desktop file dialogs (Tk). Use when the Dash server runs on the user's machine.

Tk ``filedialog`` must run on a thread that owns the Tcl interpreter main loop. Dash
callbacks run on Flask worker threads (or without Tk's main loop), so dialogs are shown
via a short-lived subprocess (:mod:`mar_dss.app.utils._tk_open_project_dialog`).

In PyInstaller builds, ``sys.executable`` is the app EXE (not Python) and worker
``.py`` files are not loose on disk. The frozen launcher handles
``--mar-dss-tk-open-project`` / ``--mar-dss-tk-save-report`` modes instead.

Return conventions for :func:`ask_open_project_path`:

- Non-empty ``str``: user chose a path.
- ``""``: dialog was shown and the user cancelled (do not fall back silently).
- ``None``: Tk is unavailable or failed before selection (caller may fall back to manual paths).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_WORKER = Path(__file__).resolve().parent / "_tk_open_project_dialog.py"
_SAVE_REPORT_WORKER = Path(__file__).resolve().parent / "_tk_save_report_dialog.py"

_TK_OPEN_PROJECT_FLAG = "--mar-dss-tk-open-project"
_TK_SAVE_REPORT_FLAG = "--mar-dss-tk-save-report"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _dialog_command(worker: Path, *args: str) -> list[str] | None:
    """Build subprocess argv for a Tk dialog worker."""
    if _is_frozen():
        if worker.name == _WORKER.name:
            return [sys.executable, _TK_OPEN_PROJECT_FLAG, *args]
        if worker.name == _SAVE_REPORT_WORKER.name:
            return [sys.executable, _TK_SAVE_REPORT_FLAG, *args]
        return None
    if not worker.is_file():
        return None
    return [sys.executable, "-u", str(worker), *args]


def _run_dialog_subprocess(cmd: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if completed.returncode != 0:
        return None

    out = (completed.stdout or "").strip()
    if not out:
        return ""
    path = out.splitlines()[0].strip()
    if path:
        return path
    return ""


def ask_open_project_path():
    """Open an OS-native file picker for MAR DSS project CSV/JSON."""
    cmd = _dialog_command(_WORKER)
    if cmd is None:
        return None
    return _run_dialog_subprocess(cmd)


def ask_save_report_path(default_filename="MAR_Prefeasibility_Report.html", report_format="html"):
    """Open an OS-native save dialog for the prefeasibility HTML or PDF report."""
    fmt = "pdf" if str(report_format or "").lower() == "pdf" else "html"
    cmd = _dialog_command(_SAVE_REPORT_WORKER, default_filename, fmt)
    if cmd is None:
        return None
    return _run_dialog_subprocess(cmd)
