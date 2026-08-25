"""Console startup banner for the PyInstaller / distribution build."""

from __future__ import annotations

import sys
from datetime import datetime

_BANNER_WIDTH = 72

_APP_TITLE = "MAR-TOOL"
_APP_SUBTITLE = "Managed Aquifer Recharge Prefeasibility Decision Support System"
_DEVELOPER = "GSI Environmental Inc."
_FUNDING = "Environmental Security Technology Certification Program (ESTCP)"
_SPONSOR = "Naval Facilities Engineering Systems Command (NAVFAC)"


def is_frozen_distribution() -> bool:
    return bool(getattr(sys, "frozen", False))


def _app_version() -> str:
    try:
        from importlib.metadata import version

        return version("mar_dss")
    except Exception:
        return "0.1.0"


def _center(text: str, width: int = _BANNER_WIDTH) -> str:
    text = text.strip()
    if len(text) >= width:
        return text[:width]
    pad = width - len(text)
    left = pad // 2
    return (" " * left) + text + (" " * (pad - left))


def _border() -> str:
    return "+" + ("-" * _BANNER_WIDTH) + "+"


def _row(text: str) -> str:
    return "|" + _center(text) + "|"


def _wrap(text: str, width: int = _BANNER_WIDTH) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        add = len(word) + (1 if current else 0)
        if current and current_len + add > width:
            lines.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += add
    if current:
        lines.append(" ".join(current))
    return lines


def _rows(text: str) -> list[str]:
    return [_row(line) for line in _wrap(text)]


def print_distribution_header() -> None:
    """Print the branded startup banner (distribution / frozen runs only)."""
    if not is_frozen_distribution():
        return

    year = datetime.now().year
    version = _app_version()

    lines = [
        "",
        _border(),
        _row(_APP_TITLE),
        *_rows(_APP_SUBTITLE),
        _border(),
        _row(f"Version {version}"),
        _row(""),
        *_rows(f"Developed by {_DEVELOPER}"),
        *_rows(f"Funded by {_FUNDING}"),
        *_rows(f"and {_SPONSOR}"),
        _border(),
        "",
        f"  (c) {year} {_DEVELOPER.rstrip('.')}. All rights reserved.",
        "",
    ]

    for line in lines:
        print(line, flush=True)


def print_startup_status(message: str) -> None:
    """Print an indented startup status line (distribution runs only)."""
    if not is_frozen_distribution():
        return
    print(f"  * {message}", flush=True)


def print_startup_footer(*, url: str, open_browser: bool) -> None:
    """Print ready-state instructions after the dashboard is listening."""
    if not is_frozen_distribution():
        return

    print("", flush=True)
    print_startup_status(f"Dashboard ready at: {url}")
    if open_browser:
        print_startup_status("Opening your default web browser...")
    print_startup_status("Keep this window open while using MAR-TOOL.")
    print_startup_status("Press Ctrl+C to stop the application.")
    print("", flush=True)
