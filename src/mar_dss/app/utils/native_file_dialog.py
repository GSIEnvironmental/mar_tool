"""Native desktop file dialogs (Tk). Use when the Dash server runs on the user's machine.

Tk ``filedialog`` must run on a thread that owns the Tcl interpreter main loop. Dash
callbacks run on Flask worker threads (or without Tk's main loop), so dialogs are shown
via a short-lived subprocess (:mod:`mar_dss.app.utils._tk_open_project_dialog`).

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


def ask_open_project_path():
    """Open an OS-native file picker for MAR DSS project CSV/JSON."""
    if not _WORKER.is_file():
        return None

    try:
        completed = subprocess.run(
            [sys.executable, "-u", str(_WORKER)],
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
    # First line only (ignore accidental extra output)
    path = out.splitlines()[0].strip()
    if path:
        return path
    return ""
