"""Helpers for combined project CSV/JSON path (workspace + filename in storage)."""

import os


def format_project_path(workspace, filename) -> str:
    """Single display string from stored workspace and filename."""
    ws = workspace.strip() if isinstance(workspace, str) else ""
    fn = filename.strip() if isinstance(filename, str) else ""
    if not ws and not fn:
        return ""
    if ws and fn:
        return os.path.normpath(os.path.join(ws, fn))
    return ws or fn


def split_project_path(full_path: str) -> tuple[str, str]:
    """Split a user/full path into (workspace_dir, filename) for storage."""
    raw = (full_path or "").strip()
    if not raw:
        return "", ""
    norm = os.path.normpath(raw)
    directory = os.path.dirname(norm)
    basename = os.path.basename(norm)
    workspace_dir = directory if directory else ""
    # norm was a bare filename → dirname ""; basename is the file
    return workspace_dir, basename
