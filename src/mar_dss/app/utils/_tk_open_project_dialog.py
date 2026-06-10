"""Subprocess worker: run a Tk open-file dialog and print the chosen path (one line) to stdout.

Invoked by :mod:`mar_dss.app.utils.native_file_dialog` so the dialog runs in a process
whose main thread owns Tk (Dash callbacks cannot use ``filedialog`` in-process).
"""

from __future__ import annotations

import sys


def main() -> None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        sys.stdout.write("\n")
        sys.stdout.flush()
        return

    root = tk.Tk()
    root.withdraw()
    try:
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        try:
            path = filedialog.askopenfilename(
                title="Select MAR DSS project file",
                filetypes=(
                    ("Project CSV", "*.csv"),
                    ("Project JSON", "*.json"),
                    ("All files", "*.*"),
                ),
            )
        except (tk.TclError, RuntimeError):
            path = ""
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass

    line = (str(path).strip() if path else "") + "\n"
    sys.stdout.write(line)
    sys.stdout.flush()


if __name__ == "__main__":
    main()
