"""
Build a PyInstaller onedir distribution for MAR-DSS.

Sets MAR_DSS_PYINSTALLER_NAME so mar_dss.spec names the EXE and output folder.

Edit the configuration below, then run:
  python build_distribution.py

Recommended build environment (from repo root):
  pip install -e ".[exe]"
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import stat
import subprocess
import sys
import time
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

# Files that must exist in the source tree before packaging.
_REQUIRED_SOURCE_FILES = (
    Path("src/mar_dss/app/assets/force_black_text.css"),
    Path("src/mar_dss/app/assets/custom.css"),
    Path("src/mar_dss/app/assets/Engineering2.jpg"),
    Path("src/mar_dss/app/assets/mar_icon2.PNG"),
    Path("src/mar_dss/knowledge/rules.yaml"),
    Path("src/mar_dss/knowledge/input.yaml"),
    Path("frozen_launcher.py"),
    Path("mar_dss.spec"),
)

# Relative paths under the onedir bundle that must exist after a successful build.
# PyInstaller 6+ places package data under `_internal/`.
_REQUIRED_BUNDLE_RELATIVE = (
    Path("_internal/mar_dss/app/assets/force_black_text.css"),
    Path("_internal/mar_dss/app/assets/custom.css"),
    Path("_internal/mar_dss/app/assets/Engineering2.jpg"),
    Path("_internal/mar_dss/app/assets/mar_icon2.PNG"),
    Path("_internal/mar_dss/knowledge/rules.yaml"),
    Path("_internal/mar_dss/knowledge/input.yaml"),
)

_REQUIRED_MODULES = (
    "PyInstaller",
    "waitress",
    "dash",
    "dash_bootstrap_components",
    "plotly",
    "reportlab",
)

_DIST_README = """MAR-DSS distribution
====================

Run MAR-DSS.exe to start the local dashboard (Waitress on http://127.0.0.1:8050/).
Keep the console window open while using the application. Press Ctrl+C to stop.

Notes
-----
- Dark/light theme contrast CSS is bundled as force_black_text.css.
- PDF report export requires reportlab (included in this build when built with [exe] extras).
- An internet connection is used for Bootswatch theme CSS and Font Awesome from CDNs.
"""


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


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _preflight(root: Path) -> None:
    missing_modules = [m for m in _REQUIRED_MODULES if not _module_available(m)]
    if missing_modules:
        sys.exit(
            "Missing packages required for the distribution build:\n  - "
            + "\n  - ".join(missing_modules)
            + '\n\nInstall with:  pip install -e ".[exe]"'
        )

    missing_files = [p for p in _REQUIRED_SOURCE_FILES if not (root / p).is_file()]
    if missing_files:
        sys.exit(
            "Missing source files required for packaging:\n  - "
            + "\n  - ".join(str(p) for p in missing_files)
        )


def _verify_bundle(dist_folder: Path, exe_name: str) -> list[str]:
    """Return a list of problem descriptions (empty if OK)."""
    problems: list[str] = []
    exe = dist_folder / f"{exe_name}.exe"
    if not exe.is_file():
        problems.append(f"Executable not found: {exe}")

    for rel in _REQUIRED_BUNDLE_RELATIVE:
        path = dist_folder / rel
        if not path.is_file():
            # Older PyInstaller layouts without `_internal/`
            alt = dist_folder / Path(*rel.parts[1:])
            if not alt.is_file():
                problems.append(f"Bundled file missing: {rel}")
    return problems


def _write_dist_readme(dist_folder: Path) -> None:
    readme = dist_folder / "README.txt"
    readme.write_text(_DIST_README, encoding="utf-8")


def _on_rm_error(func, path, exc_info):
    """Clear read-only bit and retry (common on Windows PyInstaller work dirs)."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _rmtree_robust(path: Path, *, label: str, attempts: int = 5) -> None:
    """Remove a directory tree, retrying through transient Windows locks."""
    if not path.exists():
        return

    last_err: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            shutil.rmtree(path, onerror=_on_rm_error)
            if not path.exists():
                return
        except OSError as exc:
            last_err = exc
        if attempt < attempts:
            wait = 0.4 * attempt
            print(
                f"  {label}: locked (attempt {attempt}/{attempts}); "
                f"retrying in {wait:.1f}s..."
            )
            time.sleep(wait)

    if path.exists():
        hint = (
            "Close MAR-DSS.exe / Explorer windows on that folder, "
            "or set CLEAN = False and delete it manually."
        )
        if last_err is not None:
            raise PermissionError(f"Could not remove {path}: {last_err}\n{hint}") from last_err
        raise PermissionError(f"Could not remove {path}.\n{hint}")


def main() -> None:
    name = DIST_NAME
    _validate_dist_name(name)

    root = _repo_root()
    spec = root / "mar_dss.spec"
    if not spec.is_file():
        sys.exit(f"Spec file not found: {spec}")

    _preflight(root)

    output_dir = OUTPUT_DIR.expanduser().resolve()
    work_dir = WORK_DIR.expanduser().resolve()

    dist_folder = output_dir / name

    if CLEAN:
        if work_dir.exists():
            print(f"Cleaning work dir: {work_dir}")
            try:
                _rmtree_robust(work_dir, label="work dir")
            except PermissionError as exc:
                # Fall back to a fresh workpath so the build can continue.
                stamp = time.strftime("%Y%m%d-%H%M%S")
                work_dir = work_dir.parent / f"{work_dir.name}-{stamp}"
                print(f"  Warning: {exc}")
                print(f"  Using alternate work dir: {work_dir}")
        if dist_folder.exists():
            print(f"Cleaning previous distribution: {dist_folder}")
            _rmtree_robust(dist_folder, label="distribution folder")

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
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)

    if not dist_folder.is_dir():
        sys.exit(f"Build finished but distribution folder was not created: {dist_folder}")

    problems = _verify_bundle(dist_folder, name)
    if problems:
        print("\nBuild completed, but package verification failed:")
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(1)

    _write_dist_readme(dist_folder)
    print("\nDistribution build OK.")
    print(f"  Folder: {dist_folder}")
    print(f"  Launch: {dist_folder / (name + '.exe')}")


if __name__ == "__main__":
    main()
