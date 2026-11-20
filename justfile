# Justfile for mar_dss
# Usage:   just <recipe>      Run `just` with no args to list all recipes.

set quiet

# List available recipes
[private]
default:
    just --list --unsorted

# -- quality ------------------------------------------------------------------

# Run all the formatting, linting, and testing commands
[group: 'quality']
qa:
    uv run --python=3.13 --locked --extra test pre-commit run --all-files
    # uv run --python=3.13 --extra test ty check .
    just test

# Run all the tests, but allow for arguments to be passed
[group: 'quality']
[positional-arguments]
test *ARGS:
    uv run --python=3.13 --locked --extra test tox run -e py313 -- "$@"

# Run the test suite across Python 3.10-3.13 in parallel
[group: 'quality']
testall:
    uv run --python=3.13 --locked --extra test tox run-parallel

# Run all the tests, but on failure, drop into the debugger
[group: 'quality']
[positional-arguments]
pdb *ARGS:
    uv run --python=3.13 --locked --extra test tox run -e py313 -- --no-cov --pdb --maxfail=10 --pdbcls=IPython.terminal.debugger:TerminalPdb "$@"

# Run coverage, and build to HTML
[group: 'quality']
coverage:
    uv run --python=3.13 --locked --extra test tox run -e py313 -- --cov-report=html

# -- build --------------------------------------------------------------------

# Build the project, useful for checking that packaging is correct
[group: 'build']
build:
    rm -rf build
    rm -rf dist
    uv build

# -- versioning ---------------------------------------------------------------

# Show what each bump level (patch / minor / major) would produce
[group: 'versioning']
bump:
    uv run --extra test bump-my-version show-bump

# Bump patch version (e.g. 1.2.3 to 1.2.4)
[group: 'versioning']
bump-patch:
    uv run --extra test bump-my-version bump patch

# Bump minor version (e.g. 1.2.3 to 1.3.0)
[group: 'versioning']
bump-minor:
    uv run --extra test bump-my-version bump minor

# Bump major version (e.g. 1.2.3 to 2.0.0)
[group: 'versioning']
bump-major:
    uv run --extra test bump-my-version bump major

# Push main and the tag from the last bump. Pushing the tag deploys to production.
[group: 'versioning']
tag:
    #!/usr/bin/env bash
    set -euo pipefail
    version=$(uv run --extra test bump-my-version show current_version)
    git rev-parse --verify --quiet "refs/tags/v${version}" >/dev/null \
        || { echo "No tag v${version}. Run just bump-patch (or -minor/-major) first."; exit 1; }
    git push origin main
    git push origin "v${version}"

# -- cleanup ------------------------------------------------------------------

# Remove build, Python cache, tox, test, and coverage artifacts
[group: 'cleanup']
clean: clean-build clean-pyc clean-test

# Remove build artifacts
[group: 'cleanup']
clean-build:
    rm -rf build/ dist/ .eggs/
    find . \( -name .git -o -name .venv -o -name .tox \) -prune -o -name '*.egg-info' -prune -exec rm -rf {} +
    find . \( -name .git -o -name .venv -o -name .tox \) -prune -o -name '*.egg' -exec rm -f {} +

# Remove Python file artifacts
[group: 'cleanup']
clean-pyc:
    find . \( -name .git -o -name .venv -o -name .tox \) -prune -o \
        \( -name '*.pyc' -o -name '*.pyo' -o -name '*~' \) -exec rm -f {} +
    find . \( -name .git -o -name .venv -o -name .tox \) -prune -o -name '__pycache__' -prune -exec rm -rf {} +

# Remove tox environments, test caches, and coverage reports
[group: 'cleanup']
clean-test:
    rm -f .coverage .coverage.* coverage.xml
    rm -rf .tox/ .pytest_cache/ htmlcov/
