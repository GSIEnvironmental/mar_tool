"""Subprocess worker: Tk save-as dialog for MAR prefeasibility report export."""

from __future__ import annotations

import sys


def _dialog_config(report_format: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    if report_format == "pdf":
        return ".pdf", (
            ("PDF Report", "*.pdf"),
            ("All files", "*.*"),
        )
    return ".html", (
        ("HTML Report", "*.html"),
        ("All files", "*.*"),
    )


def main() -> None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        sys.stdout.write("\n")
        sys.stdout.flush()
        return

    default_name = "MAR_Prefeasibility_Report.html"
    if len(sys.argv) > 1 and sys.argv[1].strip():
        default_name = sys.argv[1].strip()

    report_format = "html"
    if len(sys.argv) > 2 and sys.argv[2].strip().lower() == "pdf":
        report_format = "pdf"

    default_extension, filetypes = _dialog_config(report_format)

    root = tk.Tk()
    root.withdraw()
    try:
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        try:
            path = filedialog.asksaveasfilename(
                title="Save MAR Prefeasibility Report",
                defaultextension=default_extension,
                initialfile=default_name,
                filetypes=filetypes,
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
