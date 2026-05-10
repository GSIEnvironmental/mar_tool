"""Native desktop file dialogs (Tk). Use when the Dash server runs on the user's machine.

Return conventions for :func:`ask_open_project_path`:

- Non-empty ``str``: user chose a path.
- ``""``: dialog was shown and the user cancelled (do not fall back silently).
- ``None``: Tk is unavailable or failed before selection (caller may fall back to manual paths).
"""


def ask_open_project_path():
    """Open an OS-native file picker for MAR DSS project CSV/JSON."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return None

    try:
        root = tk.Tk()
    except tk.TclError:
        return None
    root.withdraw()
    path = ""
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
        except tk.TclError:
            path = ""
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass

    if path:
        return str(path).strip()
    # Empty tuple / cancel -> ""
    return ""
