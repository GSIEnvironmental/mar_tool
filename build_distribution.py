"""
Build a PyInstaller onedir distribution for MAR-DSS.

Sets MAR_DSS_PYINSTALLER_NAME so mar_dss.spec names the EXE and output folder.

Edit the configuration below, then run:
  python build_distribution.py
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# --- configuration (edit before running) ---------------------------------

# Parent directory for the onedir bundle (PyInstaller --distpath).
OUTPUT_DIR = Path(__file__).resolve().parent / "dist"

# Folder name and base name of the executable (no extension).
DIST_NAME = "MAR-DSS"

# PyInstaller work/cache directory (--workpath).
WORK_DIR = Path(__file__).resolve().parent / "build" / "pyinstaller"

# Remove work dir and an existing output folder with the same name before building.
CLEAN = True

# ---------------------------------------------------------------------------

_ENV_DIST_NAME = "MAR_DSS_PYINSTALLER_NAME"
_WIN_INVALID = re.compile(r'[<>:"/\\|?*]|\.\.')


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _validate_dist_name(name: str) -> None:
    stripped = name.strip()
    if not stripped:
        sys.exit("DIST_NAME must not be empty.")
    if stripped != name:
        sys.exit("DIST_NAME must not have leading or trailing whitespace.")
    if _WIN_INVALID.search(name):
        sys.exit(
            "DIST_NAME contains invalid characters for Windows paths "
            '(or ".."): use a simple folder/exe name.'
        )


def main() -> None:
    name = DIST_NAME
    _validate_dist_name(name)

    root = _repo_root()
    spec = root / "mar_dss.spec"
    if not spec.is_file():
        sys.exit(f"Spec file not found: {spec}")

    output_dir = OUTPUT_DIR.expanduser().resolve()
    work_dir = WORK_DIR.expanduser().resolve()

    dist_folder = output_dir / name

    if CLEAN:
        if work_dir.exists():
            shutil.rmtree(work_dir)
        if dist_folder.exists():
            shutil.rmtree(dist_folder)

    output_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env[_ENV_DIST_NAME] = name

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(spec),
        "--distpath",
        str(output_dir),
        "--workpath",
        str(work_dir),
        "--noconfirm",
    ]

    print("Running:", " ".join(cmd))
    print(f"{_ENV_DIST_NAME}={name!r}")
    print(f"Distribution folder (expected): {dist_folder}")
    print(f"Executable (expected): {dist_folder / (name + '.exe')}")

    proc = subprocess.run(cmd, cwd=str(root), env=env)
    raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
