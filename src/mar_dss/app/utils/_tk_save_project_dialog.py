"""Subprocess worker: Tk save-as dialog for MAR DSS project export."""

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

    default_name = "mar_dss_project.csv"
    if len(sys.argv) > 1 and sys.argv[1].strip():
        default_name = sys.argv[1].strip()

    default_extension = ".csv"
    if default_name.lower().endswith(".json"):
        default_extension = ".json"

    root = tk.Tk()
    root.withdraw()
    try:
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        try:
            path = filedialog.asksaveasfilename(
                title="Save MAR DSS project as",
                defaultextension=default_extension,
                initialfile=default_name,
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
